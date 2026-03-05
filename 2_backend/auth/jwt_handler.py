"""
ReconMind Backend — auth/jwt_handler.py
JWT token creation, verification, and current user extraction.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from database.db import get_db
from database.models import User
from utils.logger import get_logger

logger = get_logger(__name__)

# HTTP Bearer scheme — reads "Authorization: Bearer <token>"
bearer_scheme = HTTPBearer(auto_error=False)


# ─────────────────────────────────────────
# Token payload structure
# ─────────────────────────────────────────
# {
#   "sub": "user-uuid-string",
#   "email": "user@gmail.com",
#   "name": "User Name",
#   "iat": 1700000000,
#   "exp": 1700086400,
#   "type": "access"
# }


# ─────────────────────────────────────────
# Create JWT Token
# ─────────────────────────────────────────
def create_access_token(user: User) -> str:
    """
    Generate a signed JWT token for the given user.
    Token expires based on settings.JWT_EXPIRE_HOURS.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.JWT_EXPIRE_HOURS)

    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "iat": now,
        "exp": expire,
        "type": "access",
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    logger.debug(f"Token created for user: {user.email}")
    return token


# ─────────────────────────────────────────
# Verify JWT Token
# ─────────────────────────────────────────
def verify_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT token.
    Returns the payload dict if valid, None if invalid/expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        # Ensure it's an access token
        if payload.get("type") != "access":
            return None
        return payload

    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None


# ─────────────────────────────────────────
# Get Current User (FastAPI Dependency)
# ─────────────────────────────────────────
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    FastAPI dependency that:
    1. Extracts Bearer token from Authorization header
    2. Verifies the token
    3. Fetches the user from DB
    4. Returns the User object

    Raises HTTP 401 if token is missing, invalid, or user not found.

    Usage in routes:
        async def my_route(current_user: User = Depends(get_current_user)):
            ...
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Please sign in.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # No token provided
    if not credentials:
        raise credentials_exception

    # Verify token
    payload = verify_token(credentials.credentials)
    if not payload:
        raise credentials_exception

    # Extract user_id from payload
    user_id_str: str = payload.get("sub")
    if not user_id_str:
        raise credentials_exception

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact support."
        )

    return user


# ─────────────────────────────────────────
# Optional auth (returns None if not logged in)
# ─────────────────────────────────────────
async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Like get_current_user but returns None instead of raising 401.
    Use for public endpoints that have optional personalization.
    """
    if not credentials:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
