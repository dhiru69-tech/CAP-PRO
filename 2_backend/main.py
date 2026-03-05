"""
ReconMind Backend — main.py
FastAPI application entry point.

Phase 6 additions:
  - AI model loaded at startup
  - /api/ai/* routes (analysis, summary, health)
  - /api/reports/* routes (generate, download, list)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database.db import init_db
from auth.auth_routes import router as auth_router
from scans.scan_routes import router as scan_router
from ai.ai_routes import router as ai_router
from reports.report_routes import router as report_router
from ai.ai_service import ai_service
from utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────
# App
# ─────────────────────────────────────────
app = FastAPI(
    title="ReconMind API",
    description="AI-Powered Reconnaissance Platform — Backend API",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─────────────────────────────────────────
# CORS
# ─────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────
# Startup
# ─────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    logger.info("ReconMind backend starting... (Phase 6 — AI Integration)")

    await init_db()
    logger.info("Database initialized.")

    import asyncio
    asyncio.create_task(ai_service.startup())
    logger.info("AI model loading in background...")

# ─────────────────────────────────────────
# Routers
# ─────────────────────────────────────────
app.include_router(auth_router,   prefix="/auth",         tags=["Authentication"])
app.include_router(scan_router,   prefix="/api/scans",    tags=["Scans"])
app.include_router(ai_router,     prefix="/api/ai",       tags=["AI Analysis"])
app.include_router(report_router, prefix="/api/reports",  tags=["Reports"])

# ─────────────────────────────────────────
# Health check
# ─────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    ai_health = await ai_service.health()
    return {
        "status": "ok",
        "service": "ReconMind API",
        "version": "0.2.0",
        "ai_model": "ready" if ai_health["model_loaded"] else "loading",
    }

@app.get("/health", tags=["Health"])
async def health_check():
    ai_health = await ai_service.health()
    return {
        "status": "healthy",
        "database": "connected",
        "ai_model": ai_health,
    }

# ─────────────────────────────────────────
# Global exception handler
# ─────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Check backend logs."}
    )
