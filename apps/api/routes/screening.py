"""Real-time claim screening routes. Submitted values are evaluated in memory."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response

from apps.api.middleware.auth import authenticate, configured_roles
from apps.api.schemas.screening import ClaimScreening
from apps.api.services.screening import evaluate_screening, load_policies, policy_mode

router = APIRouter(prefix="/api/screening", tags=["Claim screening"])


@router.get("/capabilities")
def capabilities(response: Response):
    response.headers["Cache-Control"] = "no-store"
    roles = tuple(configured_roles().values())
    return {"available": len(set(roles)) == 2 and all(len(token) >= 24 for token in roles),
            "policy_mode": policy_mode()}


@router.post("", dependencies=[Depends(authenticate)])
def screen(claim: ClaimScreening, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        policies = load_policies()
    except (OSError, ValueError) as problem:
        raise HTTPException(503, "The screening policy catalog is unavailable or invalid.") from problem
    return {"evaluated_at": datetime.now(timezone.utc), "policy_mode": policy_mode(),
            **evaluate_screening(claim, policies)}
