"""
ReconMind Backend — ai/ai_service.py

Phase 6: AI Service Layer.

This is the bridge between the FastAPI backend and the local AI model.
It wraps InferenceEngine and provides high-level async methods
that the backend routes and the AI worker can call.

Responsibilities:
  - Load and hold the AI model in memory (singleton)
  - analyze_result()    → classify + explain a single finding
  - analyze_scan()      → process all results of a completed scan
  - generate_summary()  → write AI summary for the scan row
  - health_check()      → is the model loaded and healthy?
"""

import sys
import os
import asyncio
from typing import Optional, List, Dict, Any

# Add ai-model to path
AI_MODEL_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "ai-model")
)
if AI_MODEL_PATH not in sys.path:
    sys.path.insert(0, AI_MODEL_PATH)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from database.models import Scan, Result, ScanStatus, FindingRisk
from utils.logger import get_logger

logger = get_logger("ai_service")


# ─────────────────────────────────────────
# Lazy import of InferenceEngine
# (avoids hard torch dependency at startup)
# ─────────────────────────────────────────
_inference_engine = None
_engine_loading   = False
_engine_loaded    = False


def _get_engine():
    global _inference_engine
    if _inference_engine is None:
        try:
            from inference.inference_engine import InferenceEngine
            _inference_engine = InferenceEngine()
        except ImportError:
            logger.warning("InferenceEngine not available. Using fallback mode.")
            _inference_engine = _FallbackEngine()
    return _inference_engine


class _FallbackEngine:
    """Used when the AI model package is not installed."""
    loaded = False

    async def load(self): pass

    async def analyze_finding(self, finding):
        from inference.inference_engine import FindingAnalysis
        return FindingAnalysis(
            risk_level="info",
            title="AI Model Not Loaded",
            explanation="AI model not yet trained or loaded. Heuristic risk level used.",
            impact="Unknown — manual review required.",
            remediation=["Train and load the AI model (Phase 5)."],
            confidence=0.0,
        )

    async def summarize_scan(self, scan_data):
        from inference.inference_engine import ScanSummary
        return ScanSummary(
            overall_risk="unknown",
            summary="AI analysis not available. Please train the model (Phase 5).",
            key_concerns=["AI model not loaded"],
            immediate_actions=["Load and start the AI model"],
            risk_score=0.0,
        )


# ─────────────────────────────────────────
# AI Service
# ─────────────────────────────────────────
class AIService:
    """
    High-level AI service for the backend.
    Instantiate once per process and reuse.
    """

    def __init__(self):
        self._engine = None

    async def startup(self):
        """Load the AI model at application startup."""
        global _engine_loading, _engine_loaded
        if _engine_loaded:
            return

        _engine_loading = True
        logger.info("Loading AI model...")
        try:
            self._engine = _get_engine()
            await self._engine.load()
            _engine_loaded = True
            logger.info(f"AI model ready. Loaded: {self._engine.loaded}")
        except Exception as e:
            logger.error(f"AI model load failed: {e}")
            self._engine = _FallbackEngine()
        finally:
            _engine_loading = False

    def is_loaded(self) -> bool:
        return _engine_loaded and getattr(self._engine, "loaded", False)

    async def health(self) -> Dict[str, Any]:
        return {
            "model_loaded": self.is_loaded(),
            "model_path": getattr(self._engine, "model_path", "N/A"),
            "fallback_mode": not self.is_loaded(),
        }

    # ─────────────────────────────────────────
    # Analyze a single Result row
    # ─────────────────────────────────────────
    async def analyze_result(
        self,
        result_row: Result,
        dork_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run AI analysis on a single scan Result.
        Returns a dict with risk_level, explanation, remediation.
        """
        try:
            from inference.inference_engine import FindingInput
            finding = FindingInput(
                url=result_row.url,
                category=result_row.category if hasattr(result_row, "category") else "unknown",
                http_status=result_row.http_status,
                title=result_row.title,
                snippet=result_row.snippet,
                dork_used=dork_query,
            )
        except ImportError:
            return self._heuristic_result(result_row)

        engine = self._engine or _get_engine()
        analysis = await engine.analyze_finding(finding)

        return {
            "risk_level": analysis.risk_level,
            "explanation": analysis.explanation,
            "impact": analysis.impact,
            "remediation": analysis.remediation,
            "confidence": analysis.confidence,
        }

    # ─────────────────────────────────────────
    # Analyze all results for a completed scan
    # ─────────────────────────────────────────
    async def analyze_scan(
        self,
        scan_id: str,
        db: AsyncSession,
        batch_size: int = 10,
    ) -> Dict[str, Any]:
        """
        Process all Result rows for a completed scan:
        1. Load alive results from DB
        2. Run AI analysis on each
        3. Update risk_level + ai_explanation in DB
        4. Generate scan summary
        5. Update scan.ai_summary

        Returns summary dict.
        """
        import uuid
        from sqlalchemy.orm import selectinload

        scan_uuid = uuid.UUID(scan_id)

        # Load scan + results
        result = await db.execute(
            select(Scan)
            .options(selectinload(Scan.results), selectinload(Scan.dorks))
            .where(Scan.id == scan_uuid)
        )
        scan = result.scalar_one_or_none()
        if not scan:
            raise ValueError(f"Scan {scan_id} not found")

        alive_results = [r for r in scan.results if r.is_alive]
        logger.info(
            f"[{scan_id}] AI analysis starting: {len(alive_results)} alive results"
        )

        # Build dork lookup: dork_id → query string
        dork_lookup = {str(d.id): d.query for d in scan.dorks}

        # Analyze each result in batches
        risk_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        analyzed = 0

        for i in range(0, len(alive_results), batch_size):
            batch = alive_results[i: i + batch_size]
            tasks = [
                self.analyze_result(
                    r,
                    dork_query=dork_lookup.get(str(r.dork_id)),
                )
                for r in batch
            ]
            analyses = await asyncio.gather(*tasks)

            # Write back to DB
            for result_row, analysis in zip(batch, analyses):
                risk_str = analysis.get("risk_level", "info")
                try:
                    risk_enum = FindingRisk[risk_str.upper()]
                except KeyError:
                    risk_enum = FindingRisk.INFO

                result_row.risk_level = risk_enum
                result_row.ai_explanation = analysis.get("explanation", "")[:2000]
                risk_counts[risk_str] = risk_counts.get(risk_str, 0) + 1
                analyzed += 1

            await db.commit()
            logger.info(
                f"[{scan_id}] Analyzed batch {i//batch_size + 1}: "
                f"{analyzed}/{len(alive_results)} done"
            )

        # Update scan total_findings
        total_findings = sum(
            risk_counts[k] for k in ("critical", "high", "medium")
        )
        await db.execute(
            update(Scan)
            .where(Scan.id == scan_uuid)
            .values(total_findings=total_findings)
        )

        # Generate AI summary for the scan
        summary_text = await self._generate_scan_summary(scan, risk_counts)

        await db.execute(
            update(Scan)
            .where(Scan.id == scan_uuid)
            .values(ai_summary=summary_text)
        )
        await db.commit()

        logger.info(f"[{scan_id}] AI analysis complete. Risk counts: {risk_counts}")

        return {
            "scan_id": scan_id,
            "analyzed": analyzed,
            "risk_counts": risk_counts,
            "total_findings": total_findings,
            "summary_preview": summary_text[:200],
        }

    # ─────────────────────────────────────────
    # Generate scan-level AI summary
    # ─────────────────────────────────────────
    async def _generate_scan_summary(
        self,
        scan: Scan,
        risk_counts: Dict[str, int],
    ) -> str:
        """Generate a natural-language AI summary for the scan."""
        scan_data = {
            "target": scan.target,
            "total_urls_found": scan.total_urls_found,
            "total_alive": len([r for r in scan.results if r.is_alive]),
            "findings_by_risk": risk_counts,
            "top_findings": [
                {
                    "url": r.url,
                    "risk": r.risk_level.value if r.risk_level else "info",
                    "category": str(r.dork_id),
                }
                for r in sorted(
                    scan.results,
                    key=lambda r: ["critical","high","medium","low","info"].index(
                        r.risk_level.value if r.risk_level else "info"
                    )
                )[:3]
            ],
        }

        engine = self._engine or _get_engine()
        try:
            summary = await engine.summarize_scan(scan_data)
            return summary.summary
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            critical = risk_counts.get("critical", 0)
            high     = risk_counts.get("high", 0)
            return (
                f"Scan of {scan.target} completed. "
                f"Found {critical} critical and {high} high severity issues. "
                f"Immediate review recommended."
            )

    # ─────────────────────────────────────────
    # Heuristic fallback
    # ─────────────────────────────────────────
    def _heuristic_result(self, result_row: Result) -> Dict[str, Any]:
        url = result_row.url.lower()
        status = result_row.http_status or 0

        if any(x in url for x in [".env", ".sql", "private_key", "aws_access"]):
            risk = "critical"
        elif any(x in url for x in ["admin", "phpmyadmin", "wp-admin", ".bak"]):
            risk = "high" if status == 200 else "medium"
        elif any(x in url for x in [".log", ".cfg", ".ini", ".xml"]):
            risk = "medium"
        elif status == 200:
            risk = "low"
        else:
            risk = "info"

        return {
            "risk_level": risk,
            "explanation": f"Heuristic analysis: {result_row.url} classified as {risk} risk.",
            "impact": "Review required.",
            "remediation": ["Restrict public access to this resource."],
            "confidence": 0.5,
        }


# ─────────────────────────────────────────
# Singleton instance (shared across requests)
# ─────────────────────────────────────────
ai_service = AIService()
