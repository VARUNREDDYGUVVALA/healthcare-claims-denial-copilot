"""Authenticated investigation lifecycle and durable human-review checkpoint."""
from contextlib import contextmanager
import json
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from agentic_ai.workflows.investigation import investigate
from machine_learning.feature_engineering.claims import claim_lines
from machine_learning.training.pipeline import serialize


from apps.api.middleware.auth import authenticate
from apps.api.schemas.investigations import ReviewDecision, StartReview


def initialize(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS investigation_runs (
            id VARCHAR PRIMARY KEY, line_id VARCHAR NOT NULL, status VARCHAR NOT NULL,
            payload JSON NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS investigation_audit (
            run_id VARCHAR NOT NULL, ordinal INTEGER NOT NULL, actor_role VARCHAR NOT NULL,
            event VARCHAR NOT NULL, note VARCHAR, recorded_at TIMESTAMPTZ DEFAULT current_timestamp,
            PRIMARY KEY (run_id, ordinal)
        )
    """)


@contextmanager
def transaction(db):
    db.execute("BEGIN")
    try:
        yield
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def snapshot(db, run_id):
    record = db.execute(
        "SELECT status, payload FROM investigation_runs WHERE id = ?", [run_id]
    ).fetchone()
    if not record:
        raise HTTPException(404, "Investigation not found.")
    status, payload = record
    events = db.execute("""
        SELECT actor_role, event, note, strftime(recorded_at AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%M:%SZ') FROM investigation_audit
        WHERE run_id = ? ORDER BY ordinal
    """, [run_id]).fetchall()
    return {"id": run_id, "status": status, **json.loads(payload), "audit": [
        {"role": role, "event": event, "note": note, "at": at} for role, event, note, at in events
    ]}


def router(database):
    routes = APIRouter(prefix="/api/investigations", tags=["Enterprise investigation"])
    actor = Annotated[str, Depends(authenticate)]

    @routes.post("", status_code=201)
    def create(request: StartReview, role: actor):
        with database() as db:
            line = next((item for item in claim_lines(db) if item["id"] == request.line_id), None)
            if not line:
                raise HTTPException(404, "Claim line not found.")
            if line["status"] != "denied":
                raise HTTPException(409, "Investigations require a recorded denial.")
            result = investigate(db, line)
            run_id = str(uuid4())
            with transaction(db):
                initialize(db)
                db.execute("INSERT INTO investigation_runs VALUES (?, ?, 'awaiting_review', ?)", [
                    run_id, line["id"], json.dumps(result, default=serialize)
                ])
                db.execute("INSERT INTO investigation_audit VALUES (?, 1, ?, 'investigation_prepared', NULL, DEFAULT)",
                           [run_id, role])
            return snapshot(db, run_id)

    @routes.get("/{run_id}")
    def get(run_id: UUID, role: actor):
        with database() as db:
            initialize(db)
            return snapshot(db, str(run_id))

    @routes.post("/{run_id}/decision")
    def decide(run_id: UUID, request: ReviewDecision, role: actor):
        if role != "supervisor":
            raise HTTPException(403, "Only the supervisor role can record a final review decision.")
        note = request.note.strip()
        if not note:
            raise HTTPException(422, "Provide a review note.")
        run_id = str(run_id)
        with database() as db:
            with transaction(db):
                initialize(db)
                item = snapshot(db, run_id)
                if item["status"] != "awaiting_review":
                    raise HTTPException(409, "This investigation already has a final review decision.")
                status = "approved" if request.decision == "approve" else "rejected"
                db.execute("UPDATE investigation_runs SET status = ? WHERE id = ?", [status, run_id])
                db.execute("INSERT INTO investigation_audit VALUES (?, 2, ?, ?, ?, DEFAULT)",
                           [run_id, role, "review_" + status, note])
            return snapshot(db, run_id)

    return routes
