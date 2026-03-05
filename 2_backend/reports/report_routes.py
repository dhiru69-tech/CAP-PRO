"""
ReconMind Backend — reports/report_routes.py

Phase 6: Report API Routes.

Endpoints:
  POST /api/reports/generate/{scan_id}  → Generate report for a scan
  GET  /api/reports/{scan_id}           → Get existing report metadata
  GET  /api/reports/{scan_id}/download  → Download HTML report file
  GET  /api/reports/                    → List all reports for current user
"""

import os
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.db import get_db
from database.models import User, Scan, Report, ScanStatus
from auth.jwt_handler import get_current_user
from reports.report_generator import ReportGenerator
from utils.logger import get_logger

logger = get_logger("report_routes")
router = APIRouter()
generator = ReportGenerator()


# ─────────────────────────────────────────
# POST /api/reports/generate/{scan_id}
# ─────────────────────────────────────────
@router.post(
    "/generate/{scan_id}",
    summary="Generate a report for a completed, AI-analyzed scan"
)
async def generate_report(
    scan_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a JSON + HTML report for a completed scan.
    
    Requirements:
    - Scan must be COMPLETED
    - AI analysis should be done (ai_summary populated)
    
    Returns report metadata including download paths.
    """
    # Verify scan
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
            detail=f"Scan must be COMPLETED to generate a report. Status: {scan.status.value}"
        )

    # Generate report
    try:
        report_info = await generator.generate(
            scan_id=str(scan_id),
            db=db,
            formats=["json", "html"],
        )
        logger.info(f"Report generated for scan {scan_id} by {current_user.email}")
        return {
            "message": "Report generated successfully.",
            **report_info,
        }

    except Exception as e:
        logger.error(f"Report generation failed: {scan_id} | {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation failed: {str(e)}"
        )


# ─────────────────────────────────────────
# GET /api/reports/{scan_id}
# ─────────────────────────────────────────
@router.get(
    "/{scan_id}",
    summary="Get report metadata for a scan"
)
async def get_report(
    scan_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns report metadata if a report exists for this scan."""
    # Verify ownership via scan
    scan_result = await db.execute(
        select(Scan).where(
            Scan.id == scan_id,
            Scan.user_id == current_user.id,
        )
    )
    scan = scan_result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found.")

    # Get report
    report_result = await db.execute(
        select(Report).where(Report.scan_id == scan_id)
    )
    report = report_result.scalar_one_or_none()

    if not report:
        raise HTTPException(
            status_code=404,
            detail="No report generated yet. POST /api/reports/generate/{scan_id} first."
        )

    return {
        "report_id": str(report.id),
        "scan_id": str(scan_id),
        "target": scan.target,
        "summary": report.summary,
        "generated_at": report.generated_at.isoformat(),
        "has_html": bool(report.file_path and report.file_path.endswith(".html")),
        "download_url": f"/api/reports/{scan_id}/download",
    }


# ─────────────────────────────────────────
# GET /api/reports/{scan_id}/download
# ─────────────────────────────────────────
@router.get(
    "/{scan_id}/download",
    summary="Download the HTML report file"
)
async def download_report(
    scan_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serves the generated HTML report as a downloadable file."""
    # Verify ownership
    scan_result = await db.execute(
        select(Scan).where(Scan.id == scan_id, Scan.user_id == current_user.id)
    )
    scan = scan_result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found.")

    # Get report file path
    report_result = await db.execute(
        select(Report).where(Report.scan_id == scan_id)
    )
    report = report_result.scalar_one_or_none()

    if not report or not report.file_path:
        raise HTTPException(
            status_code=404,
            detail="Report file not found. Generate the report first."
        )

    if not os.path.exists(report.file_path):
        raise HTTPException(
            status_code=404,
            detail="Report file has been deleted from disk. Regenerate the report."
        )

    filename = f"reconmind_{scan.target.replace('.', '_')}_report.html"
    return FileResponse(
        path=report.file_path,
        media_type="text/html",
        filename=filename,
    )


# ─────────────────────────────────────────
# GET /api/reports/
# List all reports for current user
# ─────────────────────────────────────────
@router.get(
    "/",
    summary="List all reports for the current user"
)
async def list_reports(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns all generated reports for the authenticated user."""
    # Get user's scans that have reports
    scans_result = await db.execute(
        select(Scan)
        .options(selectinload(Scan.results))
        .where(Scan.user_id == current_user.id)
        .order_by(Scan.created_at.desc())
    )
    user_scans = scans_result.scalars().all()
    scan_ids = [s.id for s in user_scans]
    scan_map = {s.id: s for s in user_scans}

    if not scan_ids:
        return {"reports": [], "total": 0}

    reports_result = await db.execute(
        select(Report).where(Report.scan_id.in_(scan_ids))
        .order_by(Report.generated_at.desc())
    )
    reports = reports_result.scalars().all()

    return {
        "total": len(reports),
        "reports": [
            {
                "report_id": str(r.id),
                "scan_id": str(r.scan_id),
                "target": scan_map[r.scan_id].target if r.scan_id in scan_map else "?",
                "summary": (r.summary or "")[:150],
                "generated_at": r.generated_at.isoformat(),
                "download_url": f"/api/reports/{r.scan_id}/download",
            }
            for r in reports
        ]
    }
