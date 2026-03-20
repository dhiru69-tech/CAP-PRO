"""
ReconMind — scanner/config.py
All scanner configuration from environment variables.
"""

import os

# ── Database ──────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:cap69@localhost:5432/reconmind"
)

# ── Search API ────────────────────────────────────────────────────
# Get free API key at: https://serpapi.com
# If not set, DuckDuckGo HTML scraping is used as fallback
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# ── Discovery ─────────────────────────────────────────────────────
DISCOVERY_TIMEOUT     = int(os.getenv("DISCOVERY_TIMEOUT", "15"))
DISCOVERY_DELAY       = float(os.getenv("DISCOVERY_DELAY", "2.0"))
DISCOVERY_MAX_RESULTS = int(os.getenv("DISCOVERY_MAX_RESULTS", "10"))

# ── Validation ────────────────────────────────────────────────────
VALIDATE_TIMEOUT    = int(os.getenv("VALIDATE_TIMEOUT", "10"))
VALIDATE_CONCURRENT = int(os.getenv("VALIDATE_CONCURRENT", "10"))

# ── Worker ────────────────────────────────────────────────────────
SCANNER_POLL_INTERVAL  = int(os.getenv("SCANNER_POLL_INTERVAL", "5"))
SCANNER_MAX_CONCURRENT = int(os.getenv("SCANNER_MAX_CONCURRENT", "2"))

# ── Debug ─────────────────────────────────────────────────────────
SCANNER_DEBUG = os.getenv("SCANNER_DEBUG", "true").lower() == "true"
