from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config.settings import settings

security = HTTPBasic(auto_error=False)


def _auth_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Basic"},
    )


def require_admin_access(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(security)],
) -> str:
    if not settings.admin_prompt_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin prompt editing is not configured.",
        )

    if credentials is None:
        raise _auth_error("Admin authentication required.")

    username_ok = secrets.compare_digest(
        credentials.username,
        settings.admin_prompt_username,
    )
    password_ok = secrets.compare_digest(
        credentials.password,
        settings.admin_prompt_password,
    )
    if not (username_ok and password_ok):
        raise _auth_error("Invalid admin credentials.")

    return credentials.username
