"""Role tokens for the local synthetic API."""
import os
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


def configured_roles():
    return {role: os.getenv(f"COPILOT_{role.upper()}_TOKEN", "") for role in ("analyst", "supervisor")}


def authenticate(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    roles = configured_roles()
    if any(len(token) < 24 for token in roles.values()) or len(set(roles.values())) != len(roles):
        raise HTTPException(503, "Configure distinct analyst and supervisor bearer tokens (at least 24 characters each).")
    supplied = (credentials.credentials if credentials else "").encode("utf-8")
    matches = [role for role, token in roles.items() if compare_digest(supplied, token.encode("utf-8"))]
    if not matches:
        raise HTTPException(401, "Valid bearer token required.", headers={"WWW-Authenticate": "Bearer"})
    return matches[0]


def protect_legacy_api(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if any(configured_roles().values()):
        authenticate(credentials)
