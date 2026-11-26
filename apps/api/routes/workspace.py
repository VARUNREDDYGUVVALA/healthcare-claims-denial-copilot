"""Single-organization screening and review workspace."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from time import time
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from apps.api.schemas.screening import ClaimScreening
from apps.api.services.screening import evaluate_screening, load_policies, policy_mode

router = APIRouter(prefix="/api/workspace", tags=["Claim workspace"])
bearer = HTTPBearer(auto_error=False)
Role = Literal["customer", "analyst", "manager"]
Username = Annotated[str, Field(pattern=r"^[a-z0-9_.-]{3,64}$")]
Outcome = Literal["ready_for_review", "correct_before_submission", "needs_review"]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Username
    password: Annotated[str, Field(min_length=12, max_length=128)]


class Assignment(BaseModel):
    analyst: Username


class Review(BaseModel):
    outcome: Outcome


@contextmanager
def database():
    path = os.environ.get("COPILOT_WORKSPACE_DB")
    if not path:
        raise HTTPException(503, "The claim workspace is disabled.")
    db = sqlite3.connect(path, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                username TEXT PRIMARY KEY, role TEXT NOT NULL, password TEXT NOT NULL,
                failures INTEGER NOT NULL DEFAULT 0, retry_after REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions (
                digest TEXT PRIMARY KEY, username TEXT NOT NULL REFERENCES accounts, expires REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES accounts,
                analyst TEXT REFERENCES accounts, status TEXT NOT NULL,
                claim TEXT NOT NULL, screening TEXT NOT NULL, outcome TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases,
                actor TEXT NOT NULL REFERENCES accounts, action TEXT NOT NULL,
                value TEXT, occurred_at TEXT NOT NULL
            );
        """)
        yield db
    finally:
        db.close()


def hashed_password(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()


def provision(db, credentials: Credentials, role: Role):
    salt = secrets.token_bytes(16)
    try:
        db.execute(
            "INSERT INTO accounts(username, role, password) VALUES (?, ?, ?)",
            (credentials.username, role, salt.hex() + ":" + hashed_password(credentials.password, salt)),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "That username already exists.") from None


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials and re.fullmatch(r"[A-Za-z0-9_-]{43}", credentials.credentials):
        with database() as db:
            user = db.execute("""
                SELECT a.username, a.role, s.digest
                FROM sessions s JOIN accounts a USING(username)
                WHERE s.digest = ? AND s.expires > ?
            """, (digest(credentials.credentials), time())).fetchone()
            if user:
                return dict(user)
    raise HTTPException(401, "Sign in to access the claim workspace.")


def require(user, role):
    if user["role"] != role:
        raise HTTPException(403, "Your account cannot perform this action.")


@router.get("/capabilities")
def capabilities():
    return {"available": bool(os.environ.get("COPILOT_WORKSPACE_DB")), "policy_mode": policy_mode()}


@router.post("/sessions")
def sign_in(credentials: Credentials, response: Response):
    response.headers["Cache-Control"] = "no-store"
    with database() as db:
        user = db.execute("SELECT * FROM accounts WHERE username = ?", (credentials.username,)).fetchone()
        if user and user["retry_after"] > time():
            raise HTTPException(429, "Too many attempts. Try again in five minutes.")
        salt, expected = user["password"].split(":") if user else ("00" * 16, "")
        valid = hmac.compare_digest(hashed_password(credentials.password, bytes.fromhex(salt)), expected)
        if not user or not valid:
            if user:
                db.execute("""
                    UPDATE accounts SET failures = CASE WHEN failures >= 4 THEN 0 ELSE failures + 1 END,
                    retry_after = CASE WHEN failures >= 4 THEN ? ELSE 0 END WHERE username = ?
                """, (time() + 300, credentials.username))
            raise HTTPException(401, "Invalid username or password.")
        token = secrets.token_urlsafe(32)
        db.execute("UPDATE accounts SET failures=0, retry_after=0 WHERE username=?", (credentials.username,))
        db.execute("DELETE FROM sessions WHERE expires <= ?", (time(),))
        db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (digest(token), credentials.username, time() + 8 * 3600))
        return {"token": token, "username": user["username"], "role": user["role"]}


@router.delete("/sessions/current", status_code=204)
def sign_out(user=Depends(identity)):
    with database() as db:
        db.execute("DELETE FROM sessions WHERE digest=?", (user["digest"],))


@router.post("/analysts", status_code=201)
def verify_analyst(credentials: Credentials, user=Depends(identity)):
    require(user, "manager")
    with database() as db:
        provision(db, credentials, "analyst")
    return {"username": credentials.username}


def record(db, case_id, user, action, value=None):
    db.execute("INSERT INTO events(case_id, actor, action, value, occurred_at) VALUES (?, ?, ?, ?, ?)",
               (case_id, user["username"], action, value, datetime.now(timezone.utc).isoformat()))


def screen_claim(claim):
    try:
        policies = load_policies()
    except (ValueError, OSError):
        raise HTTPException(503, "The screening policy catalogue is unavailable.") from None
    return jsonable_encoder({**evaluate_screening(claim, policies), "policy_mode": policy_mode()})


@router.post("/screening")
def preview(claim: ClaimScreening, user=Depends(identity)):
    require(user, "customer")
    return screen_claim(claim)


@router.post("/cases", status_code=201)
def submit(claim: ClaimScreening, user=Depends(identity)):
    require(user, "customer")
    screening = screen_claim(claim)
    case_id = str(uuid4())
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO cases VALUES (?, ?, NULL, 'submitted', ?, ?, NULL)",
                   (case_id, user["username"], claim.model_dump_json(), json.dumps(screening)))
        record(db, case_id, user, "submitted")
        db.commit()
    return {"id": case_id}


def visible_cases(db, user, case_id=None):
    conditions = []
    args = []
    if user["role"] != "manager":
        conditions.append("owner = ?" if user["role"] == "customer" else "analyst = ?")
        args.append(user["username"])
    if case_id:
        conditions.append("id = ?")
        args.append(case_id)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    return db.execute("SELECT * FROM cases" + where + " ORDER BY rowid DESC", args)


@router.get("/cases")
def queue(user=Depends(identity)):
    with database() as db:
        cases = [
            {**{key: row[key] for key in ("id", "status", "analyst", "outcome")},
             "procedure": json.loads(row["claim"])["procedure_code"],
             "recommendation": json.loads(row["screening"])["recommendation"]}
            for row in visible_cases(db, user)
        ]
        analysts = ([row["username"] for row in db.execute(
            "SELECT username FROM accounts WHERE role = 'analyst' ORDER BY username")]
            if user["role"] == "manager" else [])
        return {"cases": cases, "analysts": analysts}


@router.get("/cases/{case_id}")
def detail(case_id: str, user=Depends(identity)):
    with database() as db:
        row = visible_cases(db, user, case_id).fetchone()
        if not row:
            raise HTTPException(404, "Claim submission not found.")
        events = [dict(event) for event in db.execute(
            "SELECT actor, action, value, occurred_at FROM events WHERE case_id=? ORDER BY seq", (case_id,)
        )]
        if user["role"] == "customer":
            events = [{"action": event["action"], "occurred_at": event["occurred_at"]} for event in events]
        return {"id": row["id"], "status": row["status"], "outcome": row["outcome"],
                "claim": json.loads(row["claim"]), "screening": json.loads(row["screening"]), "events": events}


def change(case_id, user, action, value=None):
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        row = visible_cases(db, user, case_id).fetchone()
        if not row:
            raise HTTPException(404, "Claim submission not found.")
        if action == "assigned" and row["status"] in ("submitted", "assigned"):
            if not db.execute(
                "SELECT 1 FROM accounts WHERE username=? AND role='analyst'", (value,)
            ).fetchone():
                raise HTTPException(422, "Choose a verified analyst.")
            db.execute("UPDATE cases SET analyst=?, status='assigned' WHERE id=?", (value, case_id))
        elif action == "escalated" and row["status"] == "assigned":
            db.execute("UPDATE cases SET status='escalated' WHERE id=?", (case_id,))
        elif ((action == "reviewed" and row["status"] == "assigned") or
              (action == "resolved" and row["status"] == "escalated")):
            db.execute("UPDATE cases SET status='reviewed', outcome=? WHERE id=?", (value, case_id))
        else:
            raise HTTPException(409, "The claim has moved to another workflow stage.")
        record(db, case_id, user, action, value)
        db.commit()


@router.post("/cases/{case_id}/assignment", status_code=204)
def assign(case_id: str, assignment: Assignment, user=Depends(identity)):
    require(user, "manager")
    change(case_id, user, "assigned", assignment.analyst)


@router.post("/cases/{case_id}/review", status_code=204)
def review(case_id: str, review: Review, user=Depends(identity)):
    require(user, "analyst")
    change(case_id, user, "reviewed", review.outcome)


@router.post("/cases/{case_id}/escalation", status_code=204)
def escalate(case_id: str, user=Depends(identity)):
    require(user, "analyst")
    change(case_id, user, "escalated")


@router.post("/cases/{case_id}/resolution", status_code=204)
def resolve(case_id: str, review: Review, user=Depends(identity)):
    require(user, "manager")
    change(case_id, user, "resolved", review.outcome)
