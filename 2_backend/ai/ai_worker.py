"""
ReconMind Backend — ai/ai_worker.py

Phase 6: AI Analysis Worker.

Runs as a separate process. Polls the database for COMPLETED scans
that haven't been AI-analyzed yet (ai_summary IS NULL).
Automatically runs analysis on each without manual API calls.

Flow:
  Scanner completes scan (status=COMPLETED)
       ↓
  AI Worker picks up (ai_summary IS NULL)
       ↓
  analyze_scan() → updates risk_level per result
       ↓
  generate_summary() → updates scan.ai_summary
       ↓
  Frontend shows AI analysis ✅

Run:
  python -m ai.ai_worker
  (separate terminal from backend and scanner)
"""

import asyncio
import os
import signal
import sys

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from database.models import Scan, ScanStatus
from ai.ai_service import ai_service
from utils.logger import get_logger

logger = get_logger("ai_worker")

DATABASE_URL       = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/reconmind")
POLL_INTERVAL      = int(os.getenv("AI_WORKER_POLL_INTERVAL", "10"))
MAX_CONCURRENT     = int(os.getenv("AI_WORKER_MAX_CONCURRENT", "1"))   # AI is heavy, keep at 1


class AIWorker:
    """
    Polls for COMPLETED scans without AI analysis and processes them.
    """

    def __init__(self):
        self.running = True
        self.engine  = create_async_engine(DATABASE_URL, echo=False)
        self.Session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.active_tasks: set = set()

    async def start(self):
        logger.info("═" * 50)
        logger.info("  ReconMind AI Worker — Started")
        logger.info(f"  Poll interval: {POLL_INTERVAL}s")
        logger.info("═" * 50)

        # Load AI model once at startup
        logger.info("Loading AI model...")
        await ai_service.startup()
        health = await ai_service.health()
        logger.info(f"AI model status: {health}")

        while self.running:
            try:
                if len(self.active_tasks) < MAX_CONCURRENT:
                    await self._poll_and_dispatch()
                else:
                    logger.debug(f"At capacity ({len(self.active_tasks)} active). Waiting...")
            except Exception as e:
                logger.error(f"Worker poll error: {e}", exc_info=True)

            await asyncio.sleep(POLL_INTERVAL)

        logger.info("AI Worker stopped.")

    async def _poll_and_dispatch(self):
        """Find one COMPLETED scan with no AI analysis and process it."""
        async with self.Session() as db:
            result = await db.execute(
                select(Scan)
                .where(
                    Scan.status == ScanStatus.COMPLETED,
                    Scan.ai_summary.is_(None),
                    Scan.total_urls_found > 0,
                )
                .order_by(Scan.completed_at.asc())   # Oldest first
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            scan = result.scalar_one_or_none()

            if not scan:
                logger.debug("No scans pending AI analysis.")
                return

            scan_id   = str(scan.id)
            scan_target = scan.target
            # Claim it by setting a placeholder summary
            scan.ai_summary = "__processing__"
            await db.commit()

        logger.info(f"Dispatching AI analysis for scan: {scan_id} ({scan_target})")

        task = asyncio.create_task(
            self._analyze(scan_id),
            name=f"ai-{scan_id[:8]}"
        )
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)

    async def _analyze(self, scan_id: str):
        async with self.Session() as db:
            try:
                result = await ai_service.analyze_scan(scan_id=scan_id, db=db)
                logger.info(
                    f"AI analysis complete: {scan_id} | "
                    f"analyzed={result.get('analyzed')} | "
                    f"findings={result.get('total_findings')}"
                )
            except Exception as e:
                logger.error(f"AI analysis failed for {scan_id}: {e}", exc_info=True)
                # Clear placeholder so it can be retried
                from sqlalchemy import update
                await db.execute(
                    update(Scan)
                    .where(Scan.id == scan_id)
                    .values(ai_summary=None)
                )
                await db.commit()

    def stop(self):
        logger.info("Shutdown received. Stopping AI worker...")
        self.running = False


async def main():
    worker = AIWorker()
    loop = asyncio.get_running_loop()

    def _shutdown():
        worker.stop()

    loop.add_signal_handler(signal.SIGINT, _shutdown)
    loop.add_signal_handler(signal.SIGTERM, _shutdown)

    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
