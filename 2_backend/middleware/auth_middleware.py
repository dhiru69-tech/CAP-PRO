"""
ReconMind Backend — middleware/auth_middleware.py
Middleware that protects all /api/* routes from unauthenticated access.
"""

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from auth.jwt_handler import verify_token
from utils.logger import get_logger

logger = get_logger(__name__)

# Routes that DON'T require authentication
PUBLIC_ROUTES = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/google/login",
    "/auth/google/callback",
}

# Route PREFIXES that are public (startswith check)
PUBLIC_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi",
    "/auth/",
)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Global middleware that checks JWT token for all protected routes.
    
    Protected routes: /api/*
    Public routes: /, /health, /auth/*, /docs
    
    If token is missing or invalid on a protected route → 401.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # ── Allow public routes ───────────────────
        if path in PUBLIC_ROUTES:
            return await call_next(request)

        if any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
            return await call_next(request)

        # ── Only enforce auth on /api/* ───────────
        if not path.startswith("/api/"):
            return await call_next(request)

        # ── Extract token ─────────────────────────
        auth_header = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning(f"Unauthenticated request to: {path}")
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Authentication required. Please sign in.",
                    "code": "NOT_AUTHENTICATED"
                }
            )

        token = auth_header.split(" ", 1)[1]

        # ── Verify token ──────────────────────────
        payload = verify_token(token)
        if not payload:
            logger.warning(f"Invalid/expired token on: {path}")
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Session expired. Please sign in again.",
                    "code": "TOKEN_EXPIRED"
                }
            )

        # ── Attach user info to request state ─────
        # Routes can access this via request.state.user_id
        request.state.user_id = payload.get("sub")
        request.state.user_email = payload.get("email")

        logger.debug(f"Authenticated request: {payload.get('email')} → {path}")

        return await call_next(request)
