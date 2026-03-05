"""
ReconMind Backend — reports/report_generator.py

Phase 6: Report Generator.

Generates structured reports from AI-analyzed scan data.

Output formats:
  - JSON  → machine-readable (always generated)
  - HTML  → styled, printable report
  - PDF   → via html2pdf (requires weasyprint or pdfkit)

Usage:
    generator = ReportGenerator()
    report = await generator.generate(scan_id, db)
    # Returns Report object with paths to generated files
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.models import Scan, Result, Report, FindingRisk
from utils.logger import get_logger

logger = get_logger("report_generator")

REPORTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "reports", "generated")
)
os.makedirs(REPORTS_DIR, exist_ok=True)

RISK_COLORS = {
    "critical": "#dc2626",
    "high":     "#ea580c",
    "medium":   "#ca8a04",
    "low":      "#16a34a",
    "info":     "#6b7280",
}

RISK_BADGES = {
    "critical": "🔴 CRITICAL",
    "high":     "🟠 HIGH",
    "medium":   "🟡 MEDIUM",
    "low":      "🟢 LOW",
    "info":     "ℹ️ INFO",
}


class ReportGenerator:
    """
    Generates scan reports in multiple formats.
    """

    async def generate(
        self,
        scan_id: str,
        db: AsyncSession,
        formats: List[str] = ("json", "html"),
    ) -> Dict[str, Any]:
        """
        Generate reports for a scan. Returns paths to generated files.
        """
        scan_uuid = uuid.UUID(scan_id)

        # Load scan with all data
        result = await db.execute(
            select(Scan)
            .options(
                selectinload(Scan.results),
                selectinload(Scan.dorks),
                selectinload(Scan.user),
            )
            .where(Scan.id == scan_uuid)
        )
        scan = result.scalar_one_or_none()
        if not scan:
            raise ValueError(f"Scan {scan_id} not found")

        # Build report data
        report_data = self._build_report_data(scan)
        generated_at = datetime.now(timezone.utc).isoformat()
        report_id = str(uuid.uuid4())[:8]
        base_name = f"reconmind_{scan.target.replace('.', '_')}_{report_id}"

        paths = {}

        # ── JSON report ───────────────────────────────
        if "json" in formats:
            json_path = os.path.join(REPORTS_DIR, f"{base_name}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            paths["json"] = json_path
            logger.info(f"JSON report: {json_path}")

        # ── HTML report ───────────────────────────────
        if "html" in formats:
            html_path = os.path.join(REPORTS_DIR, f"{base_name}.html")
            html = self._render_html(report_data)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            paths["html"] = html_path
            logger.info(f"HTML report: {html_path}")

        # ── Save to DB ────────────────────────────────
        # Check if report already exists for this scan
        existing = await db.execute(
            select(Report).where(Report.scan_id == scan_uuid)
        )
        existing_report = existing.scalar_one_or_none()

        if existing_report:
            existing_report.file_path = paths.get("html") or paths.get("json")
            existing_report.summary = report_data["executive_summary"]["summary"]
            existing_report.ai_analysis = scan.ai_summary
        else:
            new_report = Report(
                scan_id=scan_uuid,
                summary=report_data["executive_summary"]["summary"],
                ai_analysis=scan.ai_summary,
                recommendations=json.dumps(report_data.get("recommendations", [])),
                file_path=paths.get("html") or paths.get("json"),
            )
            db.add(new_report)

        await db.commit()

        return {
            "scan_id": scan_id,
            "target": scan.target,
            "generated_at": generated_at,
            "files": paths,
            "summary": report_data["executive_summary"]["summary"][:300],
        }

    def _build_report_data(self, scan: Scan) -> Dict[str, Any]:
        """Build the complete report data structure."""
        alive_results = [r for r in scan.results if r.is_alive]

        # Risk breakdown
        risk_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for r in alive_results:
            level = r.risk_level.value if r.risk_level else "info"
            risk_counts[level] = risk_counts.get(level, 0) + 1

        # Overall risk
        if risk_counts["critical"] > 0:
            overall_risk = "critical"
        elif risk_counts["high"] > 0:
            overall_risk = "high"
        elif risk_counts["medium"] > 0:
            overall_risk = "medium"
        elif risk_counts["low"] > 0:
            overall_risk = "low"
        else:
            overall_risk = "info"

        # Risk score (0-10)
        risk_score = min(10.0, round(
            risk_counts["critical"] * 3.0 +
            risk_counts["high"] * 2.0 +
            risk_counts["medium"] * 1.0 +
            risk_counts["low"] * 0.3,
            1
        ))

        # Sort results: critical first
        risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        sorted_results = sorted(
            alive_results,
            key=lambda r: risk_order.get(r.risk_level.value if r.risk_level else "info", 5)
        )

        # Build recommendations
        recommendations = []
        if risk_counts["critical"] > 0:
            recommendations.append({
                "priority": "IMMEDIATE",
                "action": f"Address {risk_counts['critical']} critical findings within the next hour.",
                "details": "Critical findings represent active security risks with direct exploitation potential."
            })
        if risk_counts["high"] > 0:
            recommendations.append({
                "priority": "HIGH",
                "action": f"Resolve {risk_counts['high']} high-severity findings within 24 hours.",
                "details": "High-severity issues significantly increase attack surface."
            })
        if risk_counts["medium"] > 0:
            recommendations.append({
                "priority": "MEDIUM",
                "action": f"Schedule remediation for {risk_counts['medium']} medium-severity findings.",
                "details": "Medium findings should be resolved within the current sprint."
            })

        # Executive summary
        total_alive = len(alive_results)
        if scan.ai_summary and scan.ai_summary != "__processing__":
            summary_text = scan.ai_summary
        else:
            summary_text = (
                f"Reconnaissance scan of {scan.target} identified {scan.total_urls_found} URLs, "
                f"of which {total_alive} were confirmed accessible. "
                f"The scan revealed {risk_counts['critical']} critical, "
                f"{risk_counts['high']} high, and {risk_counts['medium']} medium severity findings. "
                f"Overall risk level: {overall_risk.upper()}."
            )

        return {
            "metadata": {
                "report_generated": datetime.now(timezone.utc).isoformat(),
                "scan_id": str(scan.id),
                "target": scan.target,
                "scan_depth": scan.depth.value,
                "scan_created": scan.created_at.isoformat(),
                "scan_completed": scan.completed_at.isoformat() if scan.completed_at else None,
                "dorks_used": scan.total_dorks,
            },
            "executive_summary": {
                "target": scan.target,
                "overall_risk": overall_risk,
                "risk_score": risk_score,
                "summary": summary_text,
                "urls_discovered": scan.total_urls_found,
                "urls_alive": total_alive,
                "total_findings": scan.total_findings,
                "risk_breakdown": risk_counts,
            },
            "findings": [
                {
                    "id": str(r.id),
                    "url": r.url,
                    "title": r.title,
                    "risk_level": r.risk_level.value if r.risk_level else "info",
                    "http_status": r.http_status,
                    "ai_explanation": r.ai_explanation,
                    "snippet": r.snippet,
                    "found_at": r.found_at.isoformat(),
                }
                for r in sorted_results
            ],
            "recommendations": recommendations,
            "dorks_used": [
                {"category": d.category, "query": d.query}
                for d in scan.dorks
            ],
        }

    def _render_html(self, data: Dict[str, Any]) -> str:
        """Render a full styled HTML report."""
        meta      = data["metadata"]
        summary   = data["executive_summary"]
        findings  = data["findings"]
        recs      = data["recommendations"]
        risk      = summary["overall_risk"]
        risk_color = RISK_COLORS.get(risk, "#6b7280")

        # Findings rows
        findings_html = ""
        for f in findings:
            level = f.get("risk_level", "info")
            color = RISK_COLORS.get(level, "#6b7280")
            badge = RISK_BADGES.get(level, level.upper())
            explanation = (f.get("ai_explanation") or "No AI analysis available.").replace("\n", "<br>")
            url = f.get("url", "")
            findings_html += f"""
            <div class="finding finding-{level}">
              <div class="finding-header">
                <span class="badge" style="background:{color}">{badge}</span>
                <a href="{url}" target="_blank" rel="noopener noreferrer" class="finding-url">{url}</a>
                <span class="http-status">HTTP {f.get('http_status', '?')}</span>
              </div>
              <div class="finding-body">
                <p class="explanation">{explanation}</p>
              </div>
            </div>"""

        # Recommendations
        recs_html = ""
        for rec in recs:
            recs_html += f"""
            <div class="rec">
              <span class="rec-priority">{rec['priority']}</span>
              <div>
                <strong>{rec['action']}</strong>
                <p>{rec['details']}</p>
              </div>
            </div>"""

        risk_counts = summary["risk_breakdown"]

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ReconMind Report — {meta['target']}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0c0c0e; color: #f0eff0; line-height: 1.6; }}
  .page {{ max-width: 1000px; margin: 0 auto; padding: 40px 24px; }}
  
  /* Header */
  .header {{ display: flex; justify-content: space-between; align-items: flex-start;
             border-bottom: 1px solid #2a2a35; padding-bottom: 24px; margin-bottom: 32px; }}
  .brand {{ font-size: 22px; font-weight: 700; color: #6366f1; letter-spacing: -0.5px; }}
  .brand span {{ color: #f0eff0; }}
  .report-meta {{ text-align: right; font-size: 13px; color: #9998a8; }}
  
  /* Risk badge */
  .overall-risk {{ display: inline-block; padding: 6px 16px; border-radius: 6px;
                   font-weight: 700; font-size: 14px; letter-spacing: 0.5px;
                   background: {risk_color}22; color: {risk_color}; border: 1px solid {risk_color}44; }}
  
  /* Summary card */
  .summary-card {{ background: #1e1e24; border: 1px solid #2a2a35; border-radius: 12px;
                   padding: 24px; margin-bottom: 24px; }}
  .summary-card h2 {{ font-size: 18px; margin-bottom: 16px; color: #f0eff0; }}
  .summary-text {{ color: #c8c7d8; font-size: 15px; margin-bottom: 20px; }}

  /* Risk grid */
  .risk-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-top: 20px; }}
  .risk-cell {{ background: #14141a; border-radius: 8px; padding: 12px;
                text-align: center; border: 1px solid #2a2a35; }}
  .risk-cell .count {{ font-size: 28px; font-weight: 700; }}
  .risk-cell .label {{ font-size: 11px; color: #9998a8; text-transform: uppercase;
                       letter-spacing: 0.5px; margin-top: 4px; }}
  
  /* Section */
  h3 {{ font-size: 16px; color: #9998a8; text-transform: uppercase;
        letter-spacing: 1px; margin: 32px 0 16px; }}
  
  /* Findings */
  .finding {{ background: #1e1e24; border: 1px solid #2a2a35;
              border-radius: 10px; padding: 16px; margin-bottom: 12px; }}
  .finding-critical {{ border-left: 3px solid #dc2626; }}
  .finding-high     {{ border-left: 3px solid #ea580c; }}
  .finding-medium   {{ border-left: 3px solid #ca8a04; }}
  .finding-low      {{ border-left: 3px solid #16a34a; }}
  .finding-header   {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  .badge {{ padding: 3px 10px; border-radius: 4px; font-size: 11px;
            font-weight: 700; color: white; white-space: nowrap; }}
  .finding-url {{ color: #6366f1; font-size: 13px; font-family: monospace;
                  word-break: break-all; flex: 1; text-decoration: none; }}
  .finding-url:hover {{ text-decoration: underline; }}
  .http-status {{ font-size: 12px; color: #9998a8; white-space: nowrap; }}
  .finding-body {{ margin-top: 12px; }}
  .explanation {{ font-size: 14px; color: #c8c7d8; }}
  
  /* Recommendations */
  .rec {{ display: flex; gap: 16px; background: #1e1e24; border: 1px solid #2a2a35;
          border-radius: 10px; padding: 16px; margin-bottom: 12px; }}
  .rec-priority {{ padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 700;
                   background: #6366f122; color: #818cf8; border: 1px solid #6366f144;
                   white-space: nowrap; height: fit-content; }}
  .rec p {{ font-size: 14px; color: #9998a8; margin-top: 4px; }}
  
  /* Footer */
  .footer {{ margin-top: 48px; padding-top: 20px; border-top: 1px solid #2a2a35;
             font-size: 12px; color: #9998a8; text-align: center; }}
</style>
</head>
<body>
<div class="page">
  
  <!-- Header -->
  <div class="header">
    <div>
      <div class="brand">Recon<span>Mind</span></div>
      <div style="margin-top: 8px;">
        <span class="overall-risk">{RISK_BADGES.get(risk, risk.upper())}</span>
      </div>
    </div>
    <div class="report-meta">
      <div><strong>Target:</strong> {meta['target']}</div>
      <div><strong>Scan ID:</strong> {meta['scan_id'][:8]}...</div>
      <div><strong>Generated:</strong> {meta['report_generated'][:10]}</div>
      <div><strong>Depth:</strong> {meta['scan_depth'].upper()}</div>
    </div>
  </div>

  <!-- Executive Summary -->
  <div class="summary-card">
    <h2>Executive Summary</h2>
    <p class="summary-text">{summary['summary']}</p>
    
    <div style="display:flex; gap:24px; font-size:14px; color:#9998a8;">
      <div><strong style="color:#f0eff0">{summary['urls_discovered']}</strong> URLs found</div>
      <div><strong style="color:#f0eff0">{summary['urls_alive']}</strong> alive</div>
      <div><strong style="color:#f0eff0">{summary['risk_score']}/10</strong> risk score</div>
    </div>

    <div class="risk-grid">
      <div class="risk-cell">
        <div class="count" style="color:#dc2626">{risk_counts['critical']}</div>
        <div class="label">Critical</div>
      </div>
      <div class="risk-cell">
        <div class="count" style="color:#ea580c">{risk_counts['high']}</div>
        <div class="label">High</div>
      </div>
      <div class="risk-cell">
        <div class="count" style="color:#ca8a04">{risk_counts['medium']}</div>
        <div class="label">Medium</div>
      </div>
      <div class="risk-cell">
        <div class="count" style="color:#16a34a">{risk_counts['low']}</div>
        <div class="label">Low</div>
      </div>
      <div class="risk-cell">
        <div class="count" style="color:#6b7280">{risk_counts['info']}</div>
        <div class="label">Info</div>
      </div>
    </div>
  </div>

  <!-- Recommendations -->
  {'<h3>Recommendations</h3>' + recs_html if recs else ''}

  <!-- Findings -->
  <h3>Findings ({len(findings)})</h3>
  {findings_html if findings else '<p style="color:#9998a8">No alive findings recorded.</p>'}

  <!-- Footer -->
  <div class="footer">
    Generated by ReconMind AI · {meta['report_generated'][:19]} UTC ·
    Target: {meta['target']} · Dorks used: {meta['dorks_used']}
  </div>

</div>
</body>
</html>"""
