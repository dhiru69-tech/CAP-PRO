"""
ReconMind — scanner/validator/validator.py

URL Validator: for each discovered URL, checks if it is alive,
records HTTP status code, grabs page title, and applies
heuristic risk scoring.

What it does per URL:
  - HEAD request → status code, content-type, redirect
  - GET (if HEAD returns 200) → extract <title> from HTML
  - Heuristic risk classification based on URL pattern + status

What it does NOT do:
  - Does NOT log in to any page
  - Does NOT exploit any vulnerability
  - Does NOT download files
  - Only reads publicly accessible HTTP responses

Phase 6: AI model replaces heuristic risk classification with
learned pattern recognition.
"""

import asyncio
import re
import time
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from scanner.utils.logger import get_logger
from scanner.utils.models import DiscoveryResult, ValidatedURL, RiskLevel

logger = get_logger("validator")

# ─────────────────────────────────────────
# Config
# ─────────────────────────────────────────
VALIDATE_TIMEOUT   = 10        # seconds per request
MAX_CONCURRENT     = 10        # parallel validation requests
MAX_RESPONSE_SIZE  = 50_000    # bytes to read for title extraction

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ReconMind/1.0; "
        "+https://github.com/reconmind)"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}


class URLValidator:
    """
    Validates discovered URLs concurrently.
    Checks liveness, extracts metadata, and scores risk.

    Usage:
        validator = URLValidator()
        validated = await validator.validate_all(discovery_results)
    """

    async def validate_all(
        self,
        results: List[DiscoveryResult],
        max_concurrent: int = MAX_CONCURRENT,
    ) -> List[ValidatedURL]:
        """
        Validate a list of DiscoveryResult objects concurrently.
        Returns a list of ValidatedURL objects.
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        tasks = [
            self._validate_one(r, semaphore)
            for r in results
        ]
        validated = await asyncio.gather(*tasks, return_exceptions=False)
        alive = sum(1 for v in validated if v.is_alive)
        logger.info(
            f"Validation done: {alive}/{len(validated)} alive"
        )
        return validated

    async def _validate_one(
        self,
        result: DiscoveryResult,
        semaphore: asyncio.Semaphore,
    ) -> ValidatedURL:
        """Check a single URL. Returns ValidatedURL."""
        async with semaphore:
            return await self._check_url(result)

    async def _check_url(self, result: DiscoveryResult) -> ValidatedURL:
        """
        HTTP check a single URL.
        1. HEAD → get status + headers (fast)
        2. GET small body → extract title (only if alive)
        """
        url = result.url
        start = time.monotonic()

        base = ValidatedURL(
            url=url,
            is_alive=False,
            title=result.title,
            snippet=result.snippet,
            category=result.category,
            dork_id=result.dork_id,
        )

        try:
            async with httpx.AsyncClient(
                timeout=VALIDATE_TIMEOUT,
                headers=HEADERS,
                follow_redirects=True,
                verify=False,        # Many targets have self-signed certs
            ) as client:

                # ── HEAD request ─────────────────────────
                try:
                    head_resp = await client.head(url)
                    status = head_resp.status_code
                    content_type = head_resp.headers.get("content-type", "")
                    final_url = str(head_resp.url)
                except Exception:
                    # HEAD not supported — fall through to GET
                    head_resp = None
                    status = None
                    content_type = ""
                    final_url = url

                # ── GET for title (HTML pages only) ──────
                title = result.title
                if status in (200, 201, 301, 302, 403) and "html" in content_type:
                    try:
                        get_resp = await client.get(url)
                        html_chunk = get_resp.text[:MAX_RESPONSE_SIZE]
                        title = self._extract_title(html_chunk) or title
                        status = get_resp.status_code
                        final_url = str(get_resp.url)
                    except Exception:
                        pass

            elapsed_ms = int((time.monotonic() - start) * 1000)
            is_alive = status is not None and status < 500

            base.is_alive = is_alive
            base.http_status = status
            base.content_type = content_type
            base.title = title
            base.response_time_ms = elapsed_ms
            base.redirect_url = final_url if final_url != url else None

            # Heuristic risk classification
            base.risk_level = self._classify_risk(url, status, content_type, result.category)

            logger.debug(f"  {'✓' if is_alive else '✗'} [{status}] {url[:70]}")

        except httpx.TimeoutException:
            base.error = "timeout"
            logger.debug(f"  ✗ [timeout] {url[:70]}")

        except Exception as e:
            base.error = str(e)[:100]
            logger.debug(f"  ✗ [error] {url[:70]} | {e}")

        return base

    # ─────────────────────────────────────────
    # Title extraction
    # ─────────────────────────────────────────
    def _extract_title(self, html: str) -> Optional[str]:
        """Extract <title> from HTML content."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            title = re.sub(r"<[^>]+>", "", match.group(1))
            return title.strip()[:200]
        return None

    # ─────────────────────────────────────────
    # Heuristic risk classification
    # Phase 6: AI model replaces this
    # ─────────────────────────────────────────
    def _classify_risk(
        self,
        url: str,
        status: Optional[int],
        content_type: str,
        category: Optional[str],
    ) -> Optional[RiskLevel]:
        """
        Assigns a preliminary risk level based on:
        - Dork category
        - URL patterns
        - HTTP status code

        This is a rule-based heuristic. The AI model in Phase 6
        will provide much more accurate classification.
        """
        if not status or status >= 400:
            return RiskLevel.INFO

        url_lower = url.lower()

        # Critical patterns
        critical_patterns = [
            r"\.(sql|dump|bak)(\?|$)",
            r"db_password|secret_key|private_key",
            r"aws_access_key|stripe_secret",
            r"\.env(\?|$)",
            r"database_dump|db_dump",
        ]
        for pattern in critical_patterns:
            if re.search(pattern, url_lower):
                return RiskLevel.CRITICAL

        # High risk by category
        if category in ("credential_leaks", "database_dumps"):
            return RiskLevel.HIGH

        if category in ("admin_panels",):
            return RiskLevel.HIGH if status == 200 else RiskLevel.MEDIUM

        # High patterns
        high_patterns = [
            r"/(admin|administrator|login|panel|dashboard)",
            r"\.(log|cfg|ini|xml)(\?|$)",
            r"phpmyadmin|wp-admin",
        ]
        for pattern in high_patterns:
            if re.search(pattern, url_lower):
                return RiskLevel.HIGH

        # Medium
        if category in ("config_files", "log_files", "api_keys"):
            return RiskLevel.MEDIUM

        if category in ("backup_files",):
            return RiskLevel.MEDIUM if status == 200 else RiskLevel.LOW

        # Low — file exposure that returned non-200
        if category == "file_exposure":
            return RiskLevel.LOW

        return RiskLevel.INFO
