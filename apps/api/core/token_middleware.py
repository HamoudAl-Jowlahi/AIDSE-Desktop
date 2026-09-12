"""
AIDSE Platform — Internal session token verification

The sidecar listens on loopback, which any process running as the same user can
reach. The token is what separates "the shell that started me" from "anything
else on this machine": the Tauri shell generates 256 bits at launch, passes them
to the sidecar over argv, and hands them to its own window through the
get_sidecar_config command. Nothing else ever sees the value.

Two things are worth being explicit about:

1. Enforcement is conditional on a token being configured. That is not a
   loophole left open for convenience — it is what lets the test suite and a
   developer running the backend directly work at all.

2. The Edge-based launcher (Launch-AIDSE.vbs) cannot use this. A plain browser
   window cannot be told to attach a custom header to its requests, so that
   path runs without a token and therefore without this protection. Only the
   Tauri shell can supply one. Until the Tauri build replaces the launcher,
   an installed copy started through the .vbs is reachable by any local
   process — hence the warning logged at startup.
"""
from __future__ import annotations

import hmac
import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("aidse.security")

# Reachable without a token. The launcher polls /health to know when the
# backend is up and cannot send headers; it reveals only that the app is
# running, which the open port already does.
_UNPROTECTED_PATHS = frozenset({"/health"})


def warn_if_unprotected() -> None:
    """Say plainly, once at startup, when the API is open to local processes."""
    if os.getenv("AIDSE_INTERNAL_TOKEN"):
        return
    if os.getenv("AIDSE_DESKTOP_MODE") != "1":
        return
    logger.warning(
        "No AIDSE_INTERNAL_TOKEN is set, so the local API accepts requests from "
        "any process running as this user. The Tauri shell supplies one; the "
        "Edge launcher cannot."
    )


class InternalTokenMiddleware(BaseHTTPMiddleware):
    """Require the shared internal token on every request, when one is configured."""

    async def dispatch(self, request: Request, call_next) -> Response:
        expected_token = os.getenv("AIDSE_INTERNAL_TOKEN", "")

        # Unconfigured: dev, tests, and the Edge launcher. warn_if_unprotected()
        # has already said so at startup.
        if not expected_token:
            return await call_next(request)

        if request.method == "OPTIONS":  # CORS preflight carries no custom headers
            return await call_next(request)

        if request.url.path in _UNPROTECTED_PATHS:
            return await call_next(request)

        provided_token = request.headers.get("X-AIDSE-Internal-Token") or ""

        if not provided_token:
            auth_val = request.headers.get("authorization", "")
            if auth_val.startswith("Bearer "):
                provided_token = auth_val[7:]

        # compare_digest keeps the comparison time independent of how much of
        # the token matched.
        if not provided_token or not hmac.compare_digest(provided_token, expected_token):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "Access denied: Missing or invalid internal session token.",
                    }
                },
            )

        return await call_next(request)
