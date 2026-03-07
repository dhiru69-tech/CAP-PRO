"""
ReconMind — scanner/discovery/discovery.py

Discovery Engine: executes dork queries and extracts URLs.

Current implementation uses:
  - SerpAPI (Google Search API) if SERPAPI_KEY is configured
  - DuckDuckGo HTML scraping as fallback (no API key needed)

Phase 6: AI model augments discovery with intelligent query refinement.

IMPORTANT: This module only COLLECTS URLs from search results.
It does NOT visit or interact with the discovered URLs.
URL validation (alive check, status code) happens in validator.py.
"""

import asyncio
import os
import re
from typing import List
from urllib.parse import urlparse, urlencode, quote_plus

import httpx

from scanner.utils.logger import get_logger
from scanner.utils.models import DiscoveryResult

logger = get_logger("discovery")

# ─────────────────────────────────────────
# Config
# ─────────────────────────────────────────
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
REQUEST_TIMEOUT = int(os.getenv("DISCOVERY_TIMEOUT", "15"))
DELAY_BETWEEN_QUERIES = float(os.getenv("DISCOVERY_DELAY", "2.0"))
MAX_RESULTS_PER_QUERY = int(os.getenv("DISCOVERY_MAX_RESULTS", "10"))

# Browser-like headers to avoid blocks
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class DiscoveryEngine:
    """
    Executes dork queries and returns a list of discovered URLs.

    Strategy:
      1. If SERPAPI_KEY is set → use SerpAPI (reliable, rate-limited by plan)
      2. Fallback → DuckDuckGo HTML scraping

    Usage:
        engine = DiscoveryEngine()
        results = await engine.run(scan_id, dorks, target)
    """

    async def run(
        self,
        scan_id: str,
        dorks: List[dict],
        target: str,
    ) -> List[DiscoveryResult]:
        """
        Execute all dork queries and collect results.
        Returns deduplicated list of DiscoveryResult objects.
        """
        all_results: List[DiscoveryResult] = []
        seen_urls: set = set()
        total = len(dorks)

        logger.info(f"[{scan_id}] Starting discovery: {total} dorks for '{target}'")

        for i, dork in enumerate(dorks, 1):
            query = dork["query"]
            category = dork["category"]
            dork_id = dork.get("dork_id")

            logger.debug(f"[{scan_id}] [{i}/{total}] Running: {query}")

            try:
                if SERPAPI_KEY:
                    raw = await self._search_serpapi(query)
                else:
                    raw = await self._search_duckduckgo(query)

                # Deduplicate and filter
                for item in raw:
                    url = item.get("url", "").strip()
                    if not url or url in seen_urls:
                        continue
                    if not self._is_valid_url(url, target):
                        continue

                    seen_urls.add(url)
                    all_results.append(DiscoveryResult(
                        url=url,
                        title=item.get("title"),
                        snippet=item.get("snippet"),
                        source_query=query,
                        category=category,
                        dork_id=dork_id,
                    ))

                logger.debug(
                    f"[{scan_id}] [{i}/{total}] Got {len(raw)} results "
                    f"({len(all_results)} total unique so far)"
                )

            except Exception as e:
                logger.warning(f"[{scan_id}] Query failed: {query[:60]} | {e}")

            # Respectful delay between queries
            if i < total:
                await asyncio.sleep(DELAY_BETWEEN_QUERIES)

        logger.info(
            f"[{scan_id}] Discovery complete: {len(all_results)} unique URLs found"
        )
        return all_results

    # ─────────────────────────────────────────
    # SerpAPI (preferred — structured results)
    # ─────────────────────────────────────────
    async def _search_serpapi(self, query: str) -> List[dict]:
        """
        Use SerpAPI to execute a Google search.
        Returns list of {"url", "title", "snippet"}.
        Sign up at: https://serpapi.com (free tier available)
        """
        params = {
            "q": query,
            "api_key": SERPAPI_KEY,
            "engine": "google",
            "num": MAX_RESULTS_PER_QUERY,
            "hl": "en",
            "gl": "us",
        }
        url = f"https://serpapi.com/search?{urlencode(params)}"

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("organic_results", []):
            results.append({
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
            })
        return results

    # ─────────────────────────────────────────
    # DuckDuckGo fallback (no API key needed)
    # ─────────────────────────────────────────
    async def _search_duckduckgo(self, query: str) -> List[dict]:
        """
        Scrape DuckDuckGo HTML results as a fallback.
        Less reliable than SerpAPI but requires no API key.
        """
        encoded = quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"

        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            headers=HEADERS,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text

        return self._parse_ddg_html(html)

    def _parse_ddg_html(self, html: str) -> List[dict]:
        """
        Extract URLs, titles, and snippets from DuckDuckGo HTML.
        Uses regex — fragile but zero-dependency.
        """
        results = []

        # Extract result blocks
        result_blocks = re.findall(
            r'<div class="result.*?</div>\s*</div>',
            html,
            re.DOTALL,
        )

        for block in result_blocks[:MAX_RESULTS_PER_QUERY]:
            # Extract URL
            url_match = re.search(r'<a[^>]+href="(https?://[^"]+)"', block)
            url = url_match.group(1) if url_match else ""

            # Clean DDG redirect URLs
            if "duckduckgo.com" in url:
                inner = re.search(r'uddg=(https?://[^&"]+)', url)
                if inner:
                    from urllib.parse import unquote
                    url = unquote(inner.group(1))

            # Extract title
            title_match = re.search(r'<a[^>]+class="result__a"[^>]*>(.*?)</a>', block, re.DOTALL)
            title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else ""

            # Extract snippet
            snippet_match = re.search(
                r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL
            )
            snippet = re.sub(r"<[^>]+>", "", snippet_match.group(1)).strip() if snippet_match else ""

            if url and url.startswith("http"):
                results.append({"url": url, "title": title, "snippet": snippet})

        return results

    # ─────────────────────────────────────────
    # URL filtering
    # ─────────────────────────────────────────
    def _is_valid_url(self, url: str, target: str) -> bool:
        """
        Basic check: URL must be valid and relate to the target domain.
        Filters out unrelated domains.
        """
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            host = parsed.netloc.lower()
            # Accept URLs from target domain or its subdomains
            return host == target or host.endswith(f".{target}")
        except Exception:
            return False
