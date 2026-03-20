"""
ReconMind — scanner/engine/worker.py

Background worker that continuously polls the database for PENDING scans
and dispatches them to ScanRunner one at a time (or concurrently).

Run this as a separate process alongside the FastAPI backend:
    python -m scanner.engine.worker

Architecture:
    FastAPI (backend) → writes PENDING scan to DB
    Worker (scanner)  → picks up PENDING → runs pipeline → writes results
"""

import asyncio
from concurrent.futures.thread import _shutdown
import os
import signal
import sys
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, update

from scanner.engine.scan_runner import ScanRunner
from scanner.utils.logger import get_logger
from scanner.utils.models import ScanTask, ScanStatus

logger = get_logger("worker")

# ─────────────────────────────────────────
# Config
# ─────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:password@localhost:5432/reconmind"
)
POLL_INTERVAL_SECONDS = int(os.getenv("SCANNER_POLL_INTERVAL", "5"))
MAX_CONCURRENT_SCANS = int(os.getenv("SCANNER_MAX_CONCURRENT", "2"))


class ScanWorker:
    """
    Continuously polls for PENDING scans and runs them.

    Flow:
        poll_db() → find PENDING scans
             ↓
        claim scan (set RUNNING atomically)
             ↓
        ScanRunner.run(task)
             ↓
        results stored → COMPLETED / FAILED
    """

    def __init__(self):
        self.db_url = DATABASE_URL
        self.running = True
        self.active_tasks: set = set()

        # DB engine
        self.engine = create_async_engine(self.db_url, echo=False)
        self.SessionLocal = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    # ─────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────
    async def start(self):
        """Main event loop. Poll and dispatch scans."""
        logger.info("═" * 50)
        logger.info("  ReconMind Scanner Worker — Started")
        logger.info(f"  Poll interval : {POLL_INTERVAL_SECONDS}s")
        logger.info(f"  Max concurrent: {MAX_CONCURRENT_SCANS}")
        logger.info("═" * 50)

        while self.running:
            try:
                # Only pick up new scans if we have capacity
                if len(self.active_tasks) < MAX_CONCURRENT_SCANS:
                    await self._poll_and_dispatch()
                else:
                    logger.debug(
                        f"At capacity ({len(self.active_tasks)} active). Waiting..."
                    )

            except Exception as e:
                logger.error(f"Worker poll error: {e}", exc_info=True)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        logger.info("Worker stopped cleanly.")

    # ─────────────────────────────────────────
    # Poll DB for one PENDING scan
    # ─────────────────────────────────────────
    async def _poll_and_dispatch(self):
        """
        Find one PENDING scan and dispatch it to ScanRunner.
        Uses a SELECT FOR UPDATE SKIP LOCKED to safely claim
        the scan in a concurrent environment.
        """
        async with self.SessionLocal() as db:
            # We import the ORM model here to avoid circular imports
            # In production, use a shared models package
            from scanner.utils.db_models import ScanORM, DorkORM

            # Claim one PENDING scan atomically
            result = await db.execute(
                select(ScanORM)
                .where(ScanORM.status == "pending")
                .order_by(ScanORM.created_at.asc())   # FIFO
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            scan_row = result.scalar_one_or_none()

            if not scan_row:
                logger.debug("No PENDING scans found. Polling again...")
                return

            # Immediately set to RUNNING to prevent double-processing
            scan_row.status = "running"
            scan_row.started_at = datetime.now(timezone.utc)
            await db.commit()

            # Fetch pre-generated dorks
            dork_result = await db.execute(
                select(DorkORM).where(DorkORM.scan_id == scan_row.id)
            )
            dork_rows = dork_result.scalars().all()
            dorks = [
                {"category": d.category, "query": d.query, "dork_id": str(d.id)}
                for d in dork_rows
            ]

        # Build task
        task = ScanTask(
            scan_id=str(scan_row.id),
            target=scan_row.target,
            depth=scan_row.depth,
            dork_categories=(
                scan_row.dork_categories.split(",")
                if scan_row.dork_categories else []
            ),
            dorks=dorks,
        )

        logger.info(
            f"Dispatching scan: {task.scan_id} | "
            f"target={task.target} | dorks={len(dorks)}"
        )

        # Run in background task
        asyncio_task = asyncio.create_task(
            self._run_scan(task),
            name=f"scan-{task.scan_id[:8]}"
        )
        self.active_tasks.add(asyncio_task)
        asyncio_task.add_done_callback(self.active_tasks.discard)

    # ─────────────────────────────────────────
    # Run a single scan
    # ─────────────────────────────────────────
    async def _run_scan(self, task: ScanTask):
        """Execute one scan via ScanRunner."""
        runner = ScanRunner(db_url=self.db_url)
        try:
            summary = await runner.run(task)
            logger.info(
                f"Scan finished: {task.scan_id} | "
                f"status={summary.get('status')} | "
                f"alive={summary.get('urls_alive', 0)}"
            )
        except Exception as e:
            logger.error(f"Scan task crashed: {task.scan_id} | {e}")

    # ─────────────────────────────────────────
    # Graceful shutdown
    # ─────────────────────────────────────────
    def stop(self):
        logger.info("Shutdown signal received. Stopping worker...")
        self.running = False


# ─────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────
async def main():
    worker = ScanWorker()

    # Handle Ctrl+C and SIGTERM
    loop = asyncio.get_running_loop()

    def _shutdown():
        worker.stop()

    import platform
    if platform.system() != "Windows":
        loop.add_signal_handler(signal.SIGINT, _shutdown)
        loop.add_signal_handler(signal.SIGTERM, _shutdown)

    await worker.start()

if __name__ == "__main__":
    asyncio.run(main())
