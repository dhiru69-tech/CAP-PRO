"""
ReconMind — scanner/discovery/discovery.py
Discovery Engine: executes dork queries and extracts URLs.
Uses ddgs library (renamed from duckduckgo-search)
"""

import asyncio
import os
from typing import List
from urllib.parse import urlparse, urlencode

import httpx

from scanner.utils.logger import get_logger
from scanner.utils.models import DiscoveryResult

logger = get_logger("discovery")

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
REQUEST_TIMEOUT = int(os.getenv("DISCOVERY_TIMEOUT", "15"))
DELAY_BETWEEN_QUERIES = float(os.getenv("DISCOVERY_DELAY", "2.0"))
MAX_RESULTS_PER_QUERY = int(os.getenv("DISCOVERY_MAX_RESULTS", "10"))


class DiscoveryEngine:

    async def run(
        self,
        scan_id: str,
        dorks: List[dict],
        target: str,
    ) -> List[DiscoveryResult]:
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
                    raw = await self._search_ddgs(query)

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

            if i < total:
                await asyncio.sleep(DELAY_BETWEEN_QUERIES)

        logger.info(f"[{scan_id}] Discovery complete: {len(all_results)} unique URLs found")
        return all_results

    # ─────────────────────────────────────────
    # SerpAPI (preferred)
    # ─────────────────────────────────────────
    async def _search_serpapi(self, query: str) -> List[dict]:
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
    # DDGS search (new library name)
    # ─────────────────────────────────────────
    async def _search_ddgs(self, query: str) -> List[dict]:
        """Use ddgs library — reliable, no API key needed."""
        try:
            # Try new ddgs library first
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS

            results = []
            loop = asyncio.get_event_loop()

            def _search():
                with DDGS() as ddgs:
                    return list(ddgs.text(
                        query,
                        max_results=MAX_RESULTS_PER_QUERY,
                        safesearch="off",
                    ))

            items = await loop.run_in_executor(None, _search)

            for item in items:
                url = item.get("href", "") or item.get("url", "")
                results.append({
                    "url": url,
                    "title": item.get("title", ""),
                    "snippet": item.get("body", "") or item.get("snippet", ""),
                })

            logger.debug(f"DDGS returned {len(results)} raw results for: {query[:50]}")
            return results

        except Exception as e:
            logger.warning(f"DDGS search error: {e}")
            return []

    # ─────────────────────────────────────────
    # URL filtering
    # ─────────────────────────────────────────
    def _is_valid_url(self, url: str, target: str) -> bool:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            host = parsed.netloc.lower()
            return host == target or host.endswith(f".{target}")
        except Exception:
            return False