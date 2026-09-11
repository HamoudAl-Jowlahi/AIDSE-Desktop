"""
AIDSE Platform — Internal Session Token Verification Middleware
Section 3: Local Network Isolation & Process Authorization

Enforces that every API request to the FastAPI sidecar includes a valid
internal session token shared strictly between the Tauri shell and sidecar.
"""
from __future__ import annotations

import hmac
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class InternalTokenMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces internal session token authorization on incoming API requests.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        expected_token = os.getenv("AIDSE_INTERNAL_TOKEN", "")

        if not expected_token:
            # If no internal token configured (e.g. standard local test dev mode), pass through
            return await call_next(request)

        # Allow CORS preflight OPTIONS requests
        if request.method == "OPTIONS":
            return await call_next(request)

        # Extract internal token from header
        provided_token = request.headers.get("X-AIDSE-Internal-Token") or ""

        # Support Bearer token fallback if provided as Authorization header
        if not provided_token and "authorization" in request.headers:
            auth_val = request.headers.get("authorization", "")
            if auth_val.startswith("Bearer "):
                provided_token = auth_val[7:]

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
