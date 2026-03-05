"""
ReconMind Backend — auth/auth_routes.py
Authentication API routes: login, callback, logout, me.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.db import get_db
from database.models import User
from auth.google_oauth import get_google_auth_url, authenticate_with_google
from auth.jwt_handler import create_access_token, get_current_user
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ─────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────
class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None
    picture: str | None
    scan_count: int
    created_at: str
    last_login: str | None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ─────────────────────────────────────────
# GET /auth/google/login
# Redirect user to Google OAuth
# ─────────────────────────────────────────
@router.get("/google/login")
async def google_login():
    """
    Redirect the user to Google's OAuth consent screen.
    Frontend calls this when user clicks "Continue with Google".
    """
    auth_url = get_google_auth_url()
    logger.info("Redirecting user to Google OAuth")
    return RedirectResponse(url=auth_url)


# ─────────────────────────────────────────
# GET /auth/google/callback
# Handle Google's redirect after login
# ─────────────────────────────────────────
@router.get("/google/callback")
async def google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    db: AsyncSession = Depends(get_db)
):
    """
    Google redirects here after user authenticates.
    1. Exchange code for user info
    2. Create or update user in DB
    3. Generate JWT
    4. Redirect to frontend with token
    """
    # Step 1: Authenticate with Google
    google_user = await authenticate_with_google(code)

    if not google_user:
        logger.error("Google OAuth failed — could not authenticate")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google authentication failed. Please try again."
        )

    if not google_user.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account email is not verified."
        )

    # Step 2: Find or create user
    email = google_user["email"]
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user:
        # Existing user — update profile & last_login
        user.name = google_user.get("name") or user.name
        user.picture = google_user.get("picture") or user.picture
        user.google_id = google_user.get("google_id") or user.google_id
        user.last_login = datetime.now(timezone.utc)
        logger.info(f"Existing user logged in: {email}")
    else:
        # New user — create record
        user = User(
            email=email,
            name=google_user.get("name"),
            picture=google_user.get("picture"),
            google_id=google_user.get("google_id"),
            last_login=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()  # Get the new user's ID
        logger.info(f"New user created: {email}")

    await db.commit()
    await db.refresh(user)

    # Step 3: Generate JWT
    token = create_access_token(user)

    # Step 4: Redirect to frontend with token
    # Frontend reads token from URL and stores it securely
    redirect_url = f"{settings.FRONTEND_URL}/auth/callback?token={token}"
    logger.info(f"Redirecting user to frontend dashboard: {email}")
    return RedirectResponse(url=redirect_url)


# ─────────────────────────────────────────
# GET /auth/me
# Get current logged-in user info
# ─────────────────────────────────────────
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Returns the currently authenticated user's profile.
    Requires a valid Bearer token.
    
    Frontend calls this on page load to restore the session.
    """
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        picture=current_user.picture,
        scan_count=current_user.scan_count,
        created_at=current_user.created_at.isoformat(),
        last_login=current_user.last_login.isoformat() if current_user.last_login else None,
    )


# ─────────────────────────────────────────
# POST /auth/logout
# Client-side logout (JWT is stateless)
# ─────────────────────────────────────────
@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logout endpoint. Since JWT is stateless, the token is
    invalidated on the client side by deleting it from storage.
    
    For production: implement a token blacklist in Redis.
    """
    logger.info(f"User logged out: {current_user.email}")
    return {"message": "Logged out successfully."}
