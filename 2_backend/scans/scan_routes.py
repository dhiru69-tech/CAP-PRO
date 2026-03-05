"""
ReconMind Backend — scans/scan_routes.py
Scan management API: create, list, get, cancel.
All routes require authentication.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_db
from database.models import User
from auth.jwt_handler import get_current_user
from scans.scan_service import ScanService
from scans.scan_models import (
    CreateScanRequest,
    ScanSummary,
    ScanDetail,
    ScanWithResults,
)
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ─────────────────────────────────────────
# Helper: scan → response dict
# ─────────────────────────────────────────
def scan_to_dict(scan) -> dict:
    return {
        "id": str(scan.id),
        "target": scan.target,
        "status": scan.status.value,
        "depth": scan.depth.value,
        "dork_categories": scan.dork_categories,
        "created_at": scan.created_at.isoformat(),
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
        "total_dorks": scan.total_dorks,
        "total_urls_found": scan.total_urls_found,
        "total_findings": scan.total_findings,
        "error_message": scan.error_message,
        "ai_summary": scan.ai_summary,
    }


# ─────────────────────────────────────────
# POST /api/scans — Create new scan
# ─────────────────────────────────────────
@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new scan"
)
async def create_scan(
    body: CreateScanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new reconnaissance scan.
    
    - Validates the target domain
    - Generates dorks for selected categories
    - Stores scan in DB with status=PENDING
    - Scanner engine will pick it up (Phase 4)
    
    Requires: Bearer token
    """
    service = ScanService(db)

    scan = await service.create_scan(
        user=current_user,
        target=body.target,
        depth=body.depth,
        dork_categories=body.dork_categories,
    )

    logger.info(f"New scan created by {current_user.email}: {scan.id}")

    return {
        "message": "Scan created successfully.",
        "scan": scan_to_dict(scan),
        "dorks_generated": scan.total_dorks,
        "note": "Scanner engine will process this scan in Phase 4.",
    }


# ─────────────────────────────────────────
# GET /api/scans — List user's scans
# ─────────────────────────────────────────
@router.get(
    "/",
    summary="List all scans for current user"
)
async def list_scans(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns paginated list of the current user's scans (newest first).
    Requires: Bearer token
    """
    service = ScanService(db)
    scans = await service.list_scans(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )

    return {
        "total": len(scans),
        "limit": limit,
        "offset": offset,
        "scans": [scan_to_dict(s) for s in scans],
    }


# ─────────────────────────────────────────
# GET /api/scans/{scan_id} — Get scan detail
# ─────────────────────────────────────────
@router.get(
    "/{scan_id}",
    summary="Get full scan details with dorks and results"
)
async def get_scan(
    scan_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns full scan details including generated dorks and discovered results.
    Only returns the scan if it belongs to the current user.
    Requires: Bearer token
    """
    service = ScanService(db)
    scan = await service.get_scan(scan_id=scan_id, user_id=current_user.id)

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found."
        )

    # Build dork list
    dorks = [
        {
            "id": str(d.id),
            "category": d.category,
            "query": d.query,
            "generated_at": d.generated_at.isoformat(),
        }
        for d in scan.dorks
    ]

    # Build results list
    results = [
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
        for r in scan.results
    ]

    return {
        **scan_to_dict(scan),
        "dorks": dorks,
        "results": results,
    }


# ─────────────────────────────────────────
# DELETE /api/scans/{scan_id} — Cancel scan
# ─────────────────────────────────────────
@router.delete(
    "/{scan_id}",
    summary="Cancel a pending or running scan"
)
async def cancel_scan(
    scan_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cancel a scan that is still PENDING or RUNNING.
    Completed/failed scans cannot be cancelled.
    Requires: Bearer token
    """
    service = ScanService(db)
    cancelled = await service.cancel_scan(scan_id=scan_id, user_id=current_user.id)

    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found or cannot be cancelled (already completed/failed)."
        )

    return {"message": "Scan cancelled successfully.", "scan_id": str(scan_id)}
