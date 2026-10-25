"""Direct client for the public SEC EDGAR XBRL companyconcept API.

Used in `sec_direct` mode and as the cross-check against Zetaris. The SEC requires a
declared User-Agent ("app_name contact@email") and at most 10 requests/second.
Responses are cached on disk; a cached response is reported as `cached`, not `live`.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.financial_data.normalize import concept_api_url

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

_MIN_INTERVAL = 0.12  # seconds between requests (< 10 req/s)
_lock = asyncio.Lock()
_last_request = 0.0


class SecError(RuntimeError):
    pass


class SecClient:
    def __init__(self, user_agent: str, cache_dir: Path, cache_ttl_s: int = 6 * 3600, timeout_s: float = 15.0):
        if not user_agent or "@" not in user_agent:
            raise SecError(
                "SEC_USER_AGENT must be set to 'app_name contact@email' (SEC blocks undeclared clients)."
            )
        self.user_agent = user_agent
        self.cache_dir = cache_dir / "sec"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_s = cache_ttl_s
        self.timeout_s = timeout_s

    def _cache_path(self, cik: str, tag: str) -> Path:
        return self.cache_dir / f"{cik}_{tag}.json"

    async def company_concept(self, cik: str, tag: str) -> dict[str, Any]:
        """Return {"status": "live"|"cached"|"missing", "payload": ..., "url", "duration_ms", "retrieved_at"}."""
        return await self._get(concept_api_url(cik, tag), self._cache_path(cik, tag))

    async def company_facts(self, cik: str) -> dict[str, Any]:
        """The SEC companyfacts document (all concepts for one company), same return shape."""
        return await self._get(FACTS_URL.format(cik=cik), self.cache_dir / f"{cik}__companyfacts.json")

    async def submissions(self, cik: str) -> dict[str, Any]:
        """SEC submissions record (name, SIC industry, exchanges, fiscal year end, filer category)."""
        return await self._get(SUBMISSIONS_URL.format(cik=cik), self.cache_dir / f"{cik}__submissions.json")

    async def concept_rows(self, cik: str, tag: str) -> dict[str, Any]:
        """USD facts for one concept. If companyconcept answers 200 but with no USD rows while companyfacts has
        them (an SEC-side inconsistency seen for some filers, e.g. Coca-Cola in Oct 2026), the companyfacts rows
        are used and the result says so via "fallback": "companyfacts"."""
        r = await self.company_concept(cik, tag)
        if r["status"] == "missing":
            return {**r, "rows": [], "fallback": None}
        usd = (r["payload"].get("units") or {}).get("USD")
        rows = usd if isinstance(usd, list) else []
        if rows:
            return {**r, "rows": rows, "fallback": None}
        f = await self.company_facts(cik)
        if f["status"] != "missing":
            alt = (((f["payload"].get("facts") or {}).get("us-gaap") or {}).get(tag) or {}).get("units", {}).get("USD")
            if isinstance(alt, list) and alt:
                return {**f, "rows": alt, "fallback": "companyfacts", "concept_url": r["url"]}
        return {**r, "rows": [], "fallback": None}

    async def _get(self, url: str, path: Path) -> dict[str, Any]:
        if path.exists() and time.time() - path.stat().st_mtime < self.cache_ttl_s:
            cached = json.loads(path.read_text())
            cached["status"] = "cached" if cached.get("status") != "missing" else "missing"
            cached["duration_ms"] = 0
            return cached

        global _last_request
        attempt = 0
        started = time.perf_counter()
        while True:
            attempt += 1
            async with _lock:
                wait = _MIN_INTERVAL - (time.monotonic() - _last_request)
                if wait > 0:
                    await asyncio.sleep(wait)
                _last_request = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    resp = await client.get(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
            except httpx.HTTPError as exc:
                if attempt < 3:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                raise SecError(f"SEC request failed for {url}: {exc}") from exc
            if resp.status_code == 429 and attempt < 3:
                await asyncio.sleep(2.0 * attempt)
                continue
            break

        retrieved_at = datetime.now(timezone.utc).isoformat()
        duration_ms = int((time.perf_counter() - started) * 1000)
        if resp.status_code == 404:
            record = {"status": "missing", "payload": None, "url": url, "retrieved_at": retrieved_at}
            path.write_text(json.dumps(record))
            return {**record, "duration_ms": duration_ms}
        if resp.status_code != 200:
            raise SecError(f"SEC returned HTTP {resp.status_code} for {url}")
        record = {"status": "live", "payload": resp.json(), "url": url, "retrieved_at": retrieved_at}
        path.write_text(json.dumps(record))
        return {**record, "duration_ms": duration_ms}
