"""Local API backed by the generated DuckDB database and trained model."""
from contextlib import contextmanager
import json
from threading import Lock
from typing import Literal
from uuid import uuid4

import joblib
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .data import PROCEDURES, connect, rows
from .pipeline import ARTIFACTS, claim_lines, explain, features

app = FastAPI(title="Healthcare Claims Denial Copilot")
db_lock = Lock()

@contextmanager
def database():
    path = ARTIFACTS / "claims.duckdb"
    if not path.is_file():
        raise HTTPException(503, "Initialize artifacts with python -m copilot.pipeline")
    with db_lock, connect(path) as db:
        yield db

@app.get("/api/queue")
def queue(limit: int = Query(30, ge=1, le=250)):
    with database() as db:
        lines = claim_lines(db)
        model = joblib.load(ARTIFACTS / "model.joblib")
        scores = model.predict_proba([features(line) for line in lines])[:, 1]
        ranked = sorted(zip(lines, scores, strict=True), key=lambda item: (-item[1], item[0]["id"]))
        return [{**{key: line[key] for key in ("id", "payer", "procedure", "service", "amount")},
                 "risk": float(score)} for line, score in ranked[:limit]]

@app.get("/api/metrics")
def metrics():
    path = ARTIFACTS / "metrics.json"
    if not path.is_file():
        raise HTTPException(503, "Initialize artifacts with python -m copilot.pipeline")
    return json.loads(path.read_text())

@app.get("/api/unmatched-responses")
def unmatched():
    with database() as db:
        return rows(db, "SELECT r.* FROM responses r LEFT JOIN lines l ON l.id=r.line_id WHERE l.id IS NULL ORDER BY r.id")

@app.get("/api/lines/{line_id}")
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

@app.post("/api/lines/{line_id}/decisions", status_code=201)
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
