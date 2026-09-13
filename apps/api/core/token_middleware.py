"""
AIDSE Platform — Internal session token verification

The sidecar listens on loopback, which any process running as the same user can
reach. The token is what separates "the shell that started me" from "anything
else on this machine": the Tauri shell generates 256 bits at launch, passes them
to the sidecar over argv, and hands them to its own window through the
get_sidecar_config command. Nothing else ever sees the value.

Enforcement is conditional on a token being configured, which is what lets the
test suite and a developer running the API directly work at all. That is not a
hole in the shipped app: sidecar_entry.py — the only entry point that ships —
refuses to start without one.

It used to be a hole. The Edge-based launcher opened a plain browser window,
which cannot be told to attach a custom header, so an installed copy started
that way ran with no token and was reachable by any local process. The launcher
has been removed in favour of the Tauri shell, which always supplies one.
"""
from __future__ import annotations

import hmac
import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("aidse.security")

# Reachable without a token. It reveals only that the app is running, which an
# open port already does, and the shell needs a way to wait for readiness
# before the window makes its first real request.
_UNPROTECTED_PATHS = frozenset({"/health"})


def warn_if_unprotected() -> None:
    """Say plainly, once at startup, when the API is open to local processes."""
    if os.getenv("AIDSE_INTERNAL_TOKEN"):
        return
    if os.getenv("AIDSE_DESKTOP_MODE") != "1":
        return
    logger.warning(
        "No AIDSE_INTERNAL_TOKEN is set, so the local API accepts requests from "
        "any process running as this user. sidecar_entry.py refuses to start in "
        "this state, so reaching here means the app was started some other way."
    )


class InternalTokenMiddleware(BaseHTTPMiddleware):
    """Require the shared internal token on every request, when one is configured."""

    async def dispatch(self, request: Request, call_next) -> Response:
        expected_token = os.getenv("AIDSE_INTERNAL_TOKEN", "")

        # Unconfigured: dev and tests only — sidecar_entry.py will not start
        # without one. warn_if_unprotected() has already said so at startup.
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
