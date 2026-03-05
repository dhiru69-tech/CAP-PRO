"""
ReconMind Backend — scans/scan_service.py
Business logic for creating and managing scans.
Scanner engine integration will be added in Phase 4.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc
from sqlalchemy.orm import selectinload

from database.models import Scan, User, Dork, Result, ScanStatus, ScanDepth
from dorks.dork_generator import DorkGenerator
from utils.logger import get_logger

logger = get_logger(__name__)


class ScanService:
    """
    Handles all scan lifecycle operations:
    - create_scan: register a new scan in DB, generate dorks
    - get_scan: fetch scan by ID (user-scoped)
    - list_scans: list all scans for a user
    - cancel_scan: mark scan as cancelled

    Scanner engine integration: Phase 4
    AI analysis integration: Phase 6
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─────────────────────────────────────────
    # Create a new scan
    # ─────────────────────────────────────────
    async def create_scan(
        self,
        user: User,
        target: str,
        depth: str,
        dork_categories: List[str],
    ) -> Scan:
        """
        1. Create scan record (status=PENDING)
        2. Generate dorks for selected categories
        3. Store dorks in DB
        4. Return scan (scanner will pick it up in Phase 4)
        """
        # Map depth string to enum
        depth_enum = ScanDepth[depth.upper()]

        # Create scan record
        scan = Scan(
            user_id=user.id,
            target=target,
            depth=depth_enum,
            status=ScanStatus.PENDING,
            dork_categories=",".join(dork_categories),
        )
        self.db.add(scan)
        await self.db.flush()  # Get scan.id without committing

        # Generate dorks
        generator = DorkGenerator(target=target)
        generated_dorks = generator.generate(categories=dork_categories)

        dork_records = []
        for dork_data in generated_dorks:
            dork = Dork(
                scan_id=scan.id,
                category=dork_data["category"],
                query=dork_data["query"],
            )
            self.db.add(dork)
            dork_records.append(dork)

        scan.total_dorks = len(dork_records)

        await self.db.commit()
        await self.db.refresh(scan)

        # Increment user scan count
        await self.db.execute(
            update(User).where(User.id == user.id).values(scan_count=User.scan_count + 1)
        )
        await self.db.commit()

        logger.info(
            f"Scan created: {scan.id} | target={target} | "
            f"dorks={len(dork_records)} | user={user.email}"
        )

        return scan

    # ─────────────────────────────────────────
    # Get scan by ID (must belong to user)
    # ─────────────────────────────────────────
    async def get_scan(self, scan_id: UUID, user_id: UUID) -> Optional[Scan]:
        """
        Fetch a scan with its dorks and results.
        Returns None if not found or doesn't belong to user.
        """
        result = await self.db.execute(
            select(Scan)
            .options(
                selectinload(Scan.dorks),
                selectinload(Scan.results)
            )
            .where(
                Scan.id == scan_id,
                Scan.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    # ─────────────────────────────────────────
    # List all scans for a user
    # ─────────────────────────────────────────
    async def list_scans(
        self,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Scan]:
        """
        Return paginated list of scans for a user, newest first.
        """
        result = await self.db.execute(
            select(Scan)
            .where(Scan.user_id == user_id)
            .order_by(desc(Scan.created_at))
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    # ─────────────────────────────────────────
    # Cancel a scan
    # ─────────────────────────────────────────
    async def cancel_scan(self, scan_id: UUID, user_id: UUID) -> bool:
        """
        Cancel a scan that is PENDING or RUNNING.
        Returns True if cancelled, False if not found/not cancellable.
        """
        result = await self.db.execute(
            select(Scan).where(
                Scan.id == scan_id,
                Scan.user_id == user_id,
                Scan.status.in_([ScanStatus.PENDING, ScanStatus.RUNNING])
            )
        )
        scan = result.scalar_one_or_none()

        if not scan:
            return False

        scan.status = ScanStatus.CANCELLED
        await self.db.commit()

        logger.info(f"Scan cancelled: {scan_id} by user {user_id}")
        return True

    # ─────────────────────────────────────────
    # [Phase 4] Update scan status
    # Called by Scanner Engine
    # ─────────────────────────────────────────
    async def update_scan_status(
        self,
        scan_id: UUID,
        status: ScanStatus,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Update scan status. Called internally by scanner engine (Phase 4).
        """
        values = {"status": status}

        if status == ScanStatus.RUNNING:
            values["started_at"] = datetime.now(timezone.utc)
        elif status in {ScanStatus.COMPLETED, ScanStatus.FAILED}:
            values["completed_at"] = datetime.now(timezone.utc)

        if error_message:
            values["error_message"] = error_message

        await self.db.execute(
            update(Scan).where(Scan.id == scan_id).values(**values)
        )
        await self.db.commit()
        logger.info(f"Scan {scan_id} → status: {status.value}")
