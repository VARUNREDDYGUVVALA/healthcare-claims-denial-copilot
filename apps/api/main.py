"""Local API backed by the generated DuckDB database and trained model."""
from contextlib import contextmanager
import json
import os
from threading import Lock
from typing import Literal
from uuid import uuid4

import joblib
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from data.generator.claims import PROCEDURES
from data_engineering.ingestion.duckdb_extract import connect, rows
from machine_learning.training.pipeline import ARTIFACTS, ROOT
from machine_learning.feature_engineering.claims import claim_lines, features
from generative_ai.retrieval.policies import explain
from apps.api.routes.investigations import router as investigation_router
from apps.api.routes.screening import router as screening_router
from apps.api.middleware.auth import protect_legacy_api

app = FastAPI(title="Healthcare Claims Denial Copilot")
db_lock = Lock()
legacy = APIRouter(dependencies=[Depends(protect_legacy_api)])


@app.get("/health")
def health():
    if not all((ARTIFACTS / name).is_file() for name in ("claims.duckdb", "model.joblib", "metrics.json")):
        raise HTTPException(503, "Artifacts are initializing.")
    return {"status": "ready"}


@contextmanager
def database():
    path = ARTIFACTS / "claims.duckdb"
    if not path.is_file():
        raise HTTPException(503, "Initialize artifacts with python -m scripts.export_demo")
    with db_lock, connect(path) as db:
        yield db

@legacy.get("/api/queue")
def queue(limit: int = Query(30, ge=1, le=250)):
    with database() as db:
        lines = claim_lines(db)
        model = joblib.load(ARTIFACTS / "model.joblib")
        scores = model.predict_proba([features(line) for line in lines])[:, 1]
        ranked = sorted(zip(lines, scores, strict=True), key=lambda item: (-item[1], item[0]["id"]))
        return [{**{key: line[key] for key in ("id", "payer", "procedure", "service", "amount")},
                 "risk": float(score)} for line, score in ranked[:limit]]

@legacy.get("/api/metrics")
def metrics():
    path = ARTIFACTS / "metrics.json"
    if not path.is_file():
        raise HTTPException(503, "Initialize artifacts with python -m scripts.export_demo")
    return json.loads(path.read_text())

@legacy.get("/api/unmatched-responses")
def unmatched():
    with database() as db:
        return rows(db, "SELECT r.* FROM responses r LEFT JOIN lines l ON l.id=r.line_id WHERE l.id IS NULL ORDER BY r.id")

@legacy.get("/api/lines/{line_id}")
def detail(line_id: str):
    with database() as db:
        line = next((line for line in claim_lines(db) if line["id"] == line_id), None)
        if line is None:
            raise HTTPException(404, "Claim line not found")
        return {**line, "description": PROCEDURES[line["procedure"]], "explanation": explain(db, line),
                "decisions": rows(db, "SELECT * FROM decisions WHERE line_id=? ORDER BY id", [line_id])}

class Decision(BaseModel):
    action: Literal["Verify authorization", "Verify coverage", "Check for duplicate",
                    "Request payer clarification", "Close review"]
    note: str = Field(default="", max_length=2000)

@legacy.post("/api/lines/{line_id}/decisions", status_code=201)
def save_decision(line_id: str, decision: Decision):
    with database() as db:
        response = db.execute("SELECT r.status FROM responses r JOIN lines l ON l.id=r.line_id WHERE l.id=?", [line_id]).fetchone()
        if response is None:
            raise HTTPException(404, "Matched payer response not found")
        if response[0] != "denied":
            raise HTTPException(409, "Decisions require a denied line")
        key = f"D-{uuid4()}"
        db.execute("INSERT INTO decisions VALUES (?, ?, ?, ?)", [key, line_id, decision.action, decision.note])
        return {"id": key, "line_id": line_id, **decision.model_dump()}

app.include_router(legacy)
app.include_router(screening_router)
app.include_router(investigation_router(database))

if os.getenv("COPILOT_SERVE_UI") == "1":
    app.mount("/", StaticFiles(directory=ROOT / "apps/frontend/dist", html=True), name="ui")
