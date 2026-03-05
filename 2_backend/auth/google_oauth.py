"""
ReconMind Backend — auth/google_oauth.py
Google OAuth 2.0 flow: login URL + callback token exchange.
"""

import httpx
from urllib.parse import urlencode
from typing import Optional

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


# ─────────────────────────────────────────
# Step 1: Build Google Login URL
# ─────────────────────────────────────────
def get_google_auth_url() -> str:
    """
    Returns the URL to redirect the user to for Google authentication.
    Frontend redirects user here when they click "Continue with Google".
    """
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",         # Always show account picker
    }
    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    logger.debug(f"Generated Google auth URL")
    return url


# ─────────────────────────────────────────
# Step 2: Exchange auth code for tokens
# ─────────────────────────────────────────
async def exchange_code_for_token(code: str) -> Optional[dict]:
    """
    After Google redirects back with ?code=...,
    exchange the code for access_token and id_token.
    Returns the token response dict or None on failure.
    """
    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
        "code": code,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(GOOGLE_TOKEN_URL, data=data, timeout=10.0)
            response.raise_for_status()
            token_data = response.json()
            logger.debug("Successfully exchanged code for Google token")
            return token_data

        except httpx.HTTPStatusError as e:
            logger.error(f"Google token exchange failed: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Google token exchange error: {e}")
            return None


# ─────────────────────────────────────────
# Step 3: Fetch user info from Google
# ─────────────────────────────────────────
async def get_google_user_info(access_token: str) -> Optional[dict]:
    """
    Use the access_token to fetch the user's profile info from Google.
    
    Returns dict with keys:
        sub, email, name, picture, email_verified
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(GOOGLE_USERINFO_URL, headers=headers, timeout=10.0)
            response.raise_for_status()
            user_info = response.json()
            logger.debug(f"Fetched Google user info for: {user_info.get('email')}")
            return user_info

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to fetch Google user info: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Google user info error: {e}")
            return None


# ─────────────────────────────────────────
# Combined: code → user info
# ─────────────────────────────────────────
async def authenticate_with_google(code: str) -> Optional[dict]:
    """
    Full Google OAuth flow:
    1. Exchange auth code for tokens
    2. Fetch user info
    3. Return user profile
    
    Returns user info dict or None on any failure.
    Expected return format:
    {
        "google_id": "...",
        "email": "user@gmail.com",
        "name": "Full Name",
        "picture": "https://...",
        "email_verified": True
    }
    """
    # Exchange code for tokens
    token_data = await exchange_code_for_token(code)
    if not token_data:
        logger.error("Failed at token exchange step")
        return None

    access_token = token_data.get("access_token")
    if not access_token:
        logger.error("No access_token in Google response")
        return None

    # Fetch user profile
    user_info = await get_google_user_info(access_token)
    if not user_info:
        logger.error("Failed at user info step")
        return None

    # Normalize the response
    return {
        "google_id": user_info.get("sub"),
        "email": user_info.get("email"),
        "name": user_info.get("name"),
        "picture": user_info.get("picture"),
        "email_verified": user_info.get("email_verified", False),
    }
