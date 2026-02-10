"""Bearer token authentication for the Dashboard API."""

import hmac
import logging
import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

DASHBOARD_AUTH_TOKEN = os.environ.get("DASHBOARD_AUTH_TOKEN", "")

if not DASHBOARD_AUTH_TOKEN:
    logger.warning(
        "DASHBOARD_AUTH_TOKEN not set -- dashboard API has NO authentication. "
        "Set DASHBOARD_AUTH_TOKEN env var to secure the endpoint."
    )

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Validate the bearer token on protected endpoints.

    If DASHBOARD_AUTH_TOKEN is unset, all requests pass through (open mode).
    When set, requests must include a matching Authorization: Bearer <token> header.

    Parameters
    ----------
    credentials : HTTPAuthorizationCredentials | None
        Extracted from the Authorization header by HTTPBearer.

    Raises
    ------
    HTTPException
        401 if no token provided or token does not match.
    """
    if not DASHBOARD_AUTH_TOKEN:
        return

    if credentials is None or not hmac.compare_digest(
        credentials.credentials, DASHBOARD_AUTH_TOKEN
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
