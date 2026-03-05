"""
ReconMind Backend — ai/ai_routes.py

Phase 6: AI Analysis API Routes.

Endpoints:
  GET  /api/ai/health              → Is AI model loaded?
  POST /api/ai/analyze/{scan_id}   → Trigger AI analysis for a completed scan
  GET  /api/ai/results/{scan_id}   → Get AI-analyzed results for a scan
  GET  /api/ai/summary/{scan_id}   → Get AI summary for a scan
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.db import get_db
from database.models import User, Scan, Result, ScanStatus
from auth.jwt_handler import get_current_user
from ai.ai_service import ai_service
from utils.logger import get_logger

logger = get_logger("ai_routes")
router = APIRouter()


# ─────────────────────────────────────────
# GET /api/ai/health
# ─────────────────────────────────────────
@router.get("/health", summary="AI model health status")
async def ai_health():
    """
    Returns whether the AI model is loaded and ready.
    Frontend uses this to show 'AI Ready' or 'AI Not Available' status.
    """
    health = await ai_service.health()
    return {
        "status": "ready" if health["model_loaded"] else "fallback",
        **health,
    }


# ─────────────────────────────────────────
# POST /api/ai/analyze/{scan_id}
# Trigger AI analysis for a completed scan
# ─────────────────────────────────────────
@router.post(
    "/analyze/{scan_id}",
    summary="Run AI analysis on a completed scan"
)
async def trigger_analysis(
    scan_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Triggers AI analysis for a completed scan.
    
    - Verifies scan belongs to user and is COMPLETED
    - Runs AI analysis in the background (non-blocking)
    - Returns immediately with a job accepted message
    
    Frontend should poll GET /api/scans/{scan_id} to check when
    ai_summary is populated.
    """
    # Fetch and verify scan
    result = await db.execute(
        select(Scan).where(
            Scan.id == scan_id,
            Scan.user_id == current_user.id,
        )
    )
    scan = result.scalar_one_or_none()

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found."
        )

    if scan.status != ScanStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Scan must be COMPLETED to run AI analysis. Current status: {scan.status.value}"
        )

    if scan.ai_summary:
        return {
            "message": "AI analysis already completed for this scan.",
            "scan_id": str(scan_id),
            "already_done": True,
        }

    # Run in background — non-blocking
    background_tasks.add_task(
        _run_analysis_background,
        scan_id=str(scan_id),
    )

    logger.info(f"AI analysis triggered for scan {scan_id} by {current_user.email}")

    return {
        "message": "AI analysis started. Poll GET /api/scans/{id} for completion.",
        "scan_id": str(scan_id),
        "status": "processing",
    }


async def _run_analysis_background(scan_id: str):
    """Background task: run AI analysis with its own DB session."""
    from database.db import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            result = await ai_service.analyze_scan(scan_id=scan_id, db=db)
            logger.info(f"Background AI analysis done: {scan_id} | {result}")
        except Exception as e:
            logger.error(f"Background AI analysis failed: {scan_id} | {e}")


# ─────────────────────────────────────────
# GET /api/ai/results/{scan_id}
# Get AI-analyzed results (with risk + explanation)
# ─────────────────────────────────────────
@router.get(
    "/results/{scan_id}",
    summary="Get AI-analyzed results for a scan"
)
async def get_ai_results(
    scan_id: UUID,
    risk_filter: str = None,   # optional: "critical" | "high" | "medium" | "low"
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all scan results enriched with AI risk classification
    and explanation.
    
    Optional query param: ?risk_filter=critical
    """
    # Verify scan belongs to user
    scan_result = await db.execute(
        select(Scan)
        .options(selectinload(Scan.results))
        .where(Scan.id == scan_id, Scan.user_id == current_user.id)
    )
    scan = scan_result.scalar_one_or_none()

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found."
        )

    results = scan.results

    # Filter by risk if requested
    if risk_filter:
        results = [
            r for r in results
            if r.risk_level and r.risk_level.value == risk_filter.lower()
        ]

    # Sort: critical first
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    results = sorted(
        results,
        key=lambda r: risk_order.get(r.risk_level.value if r.risk_level else "info", 5)
    )

    return {
        "scan_id": str(scan_id),
        "target": scan.target,
        "total": len(results),
        "ai_analyzed": sum(1 for r in results if r.ai_explanation),
        "results": [
            {
                "id": str(r.id),
                "url": r.url,
                "title": r.title,
                "snippet": r.snippet,
                "http_status": r.http_status,
                "is_alive": r.is_alive,
                "risk_level": r.risk_level.value if r.risk_level else None,
                "ai_explanation": r.ai_explanation,
                "found_at": r.found_at.isoformat(),
            }
            for r in results
        ]
    }


# ─────────────────────────────────────────
# GET /api/ai/summary/{scan_id}
# Get the AI narrative summary for a scan
# ─────────────────────────────────────────
@router.get(
    "/summary/{scan_id}",
    summary="Get AI-generated summary for a scan"
)
async def get_ai_summary(
    scan_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the AI-generated narrative summary for a scan.
    Includes risk breakdown, key concerns, and action items.
    """
    scan_result = await db.execute(
        select(Scan)
        .options(selectinload(Scan.results))
        .where(Scan.id == scan_id, Scan.user_id == current_user.id)
    )
    scan = scan_result.scalar_one_or_none()

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found."
        )

    # Count risks
    risk_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for r in scan.results:
        if r.risk_level:
            risk_counts[r.risk_level.value] = risk_counts.get(r.risk_level.value, 0) + 1

    # Overall risk
    if risk_counts["critical"] > 0:
        overall = "critical"
    elif risk_counts["high"] > 0:
        overall = "high"
    elif risk_counts["medium"] > 0:
        overall = "medium"
    else:
        overall = "low"

    return {
        "scan_id": str(scan_id),
        "target": scan.target,
        "status": scan.status.value,
        "overall_risk": overall,
        "risk_counts": risk_counts,
        "ai_summary": scan.ai_summary,
        "ai_analyzed": bool(scan.ai_summary),
        "total_urls_found": scan.total_urls_found,
        "total_findings": scan.total_findings,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
    }
