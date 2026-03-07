"""
ReconMind — scanner/evidence/evidence_store.py

Evidence Store: writes validated scan results back to PostgreSQL.
Also handles scan status updates (RUNNING / COMPLETED / FAILED).

This is the final step in the scanner pipeline.
After results are stored here, the AI model (Phase 6) can
read them from the DB and run analysis.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import update

from scanner.utils.db_models import ScanORM, ResultORM
from scanner.utils.models import ValidatedURL, ScanStatus
from scanner.utils.logger import get_logger

logger = get_logger("evidence_store")


class EvidenceStore:
    """
    Persists scanner output to PostgreSQL.

    Usage:
        store = EvidenceStore(db_url="postgresql+asyncpg://...")
        await store.store_results(scan_id, validated_urls)
        await store.update_scan_status(scan_id, ScanStatus.COMPLETED)
    """

    def __init__(self, db_url: str):
        self.engine = create_async_engine(db_url, echo=False)
        self.SessionLocal = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    # ─────────────────────────────────────────
    # Store results
    # ─────────────────────────────────────────
    async def store_results(
        self,
        scan_id: str,
        results: List[ValidatedURL],
        batch_size: int = 50,
    ) -> int:
        """
        Insert all ValidatedURL objects as Result rows in the DB.
        Processes in batches to avoid overwhelming the DB.
        Returns the count of rows inserted.
        """
        if not results:
            logger.info(f"[{scan_id}] No results to store.")
            return 0

        scan_uuid = uuid.UUID(scan_id)
        stored = 0

        async with self.SessionLocal() as db:
            for i in range(0, len(results), batch_size):
                batch = results[i : i + batch_size]
                rows = []

                for r in batch:
                    row = ResultORM(
                        id=uuid.uuid4(),
                        scan_id=scan_uuid,
                        dork_id=uuid.UUID(r.dork_id) if r.dork_id else None,
                        url=r.url,
                        title=r.title,
                        snippet=r.snippet,
                        http_status=r.http_status,
                        is_alive=r.is_alive,
                        risk_level=r.risk_level.value if r.risk_level else None,
                        # ai_explanation filled in Phase 6
                    )
                    rows.append(row)

                db.add_all(rows)
                await db.commit()
                stored += len(rows)
                logger.debug(f"[{scan_id}] Stored batch {i//batch_size + 1}: {len(rows)} results")

        logger.info(f"[{scan_id}] Evidence stored: {stored} results in DB")
        return stored

    # ─────────────────────────────────────────
    # Update scan status
    # ─────────────────────────────────────────
    async def update_scan_status(
        self,
        scan_id: str,
        status: ScanStatus,
        error_message: Optional[str] = None,
        total_urls_found: Optional[int] = None,
        total_findings: Optional[int] = None,
    ) -> None:
        """
        Update the scan row's status and relevant timestamps/counts.
        """
        scan_uuid = uuid.UUID(scan_id)
        now = datetime.now(timezone.utc)

        values: dict = {"status": status.value}

        if status == ScanStatus.RUNNING:
            values["started_at"] = now

        elif status in (ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED):
            values["completed_at"] = now

        if error_message:
            values["error_message"] = error_message[:1000]

        if total_urls_found is not None:
            values["total_urls_found"] = total_urls_found

        if total_findings is not None:
            values["total_findings"] = total_findings

        async with self.SessionLocal() as db:
            await db.execute(
                update(ScanORM).where(ScanORM.id == scan_uuid).values(**values)
            )
            await db.commit()

        logger.info(f"[{scan_id}] Status → {status.value}")
