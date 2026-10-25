"""Client for the FinSight H-MEM sidecar (services/hmem-sidecar), which runs the Meterless
H-MEM reference engine. Failures never break an investigation: they are reported as receipts.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.models.schemas import QueryReceipt


class HmemUnavailable(RuntimeError):
    pass


class HmemClient:
    def __init__(self, base_url: str, timeout_s: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.receipts: list[QueryReceipt] = []

    async def _call(self, method: str, path: str, body: Any = None) -> Any:
        started = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                r = await c.request(method, self.base_url + path, json=body)
            ok = r.status_code < 400
            self.receipts.append(QueryReceipt(channel="hmem", target=f"{method} {path}", started_at=started,
                                              duration_ms=int((time.perf_counter() - t0) * 1000), ok=ok,
                                              error=None if ok else f"HTTP {r.status_code}"))
            if not ok:
                raise HmemUnavailable(f"H-MEM sidecar returned HTTP {r.status_code} for {path}: {r.text[:200]}")
            return r.json()
        except httpx.HTTPError as exc:
            self.receipts.append(QueryReceipt(channel="hmem", target=f"{method} {path}", started_at=started,
                                              duration_ms=int((time.perf_counter() - t0) * 1000), ok=False,
                                              error=str(exc)))
            raise HmemUnavailable(f"H-MEM sidecar unreachable at {self.base_url}: {exc}") from exc

    async def health(self) -> dict[str, Any]:
        return await self._call("GET", "/health")

    async def recall(self, ticker: str, query: str, top_n: int = 8) -> dict[str, Any]:
        return await self._call("POST", "/recall", {"ticker": ticker, "query": query, "topN": top_n})

    async def write_facts(self, ticker: str, facts: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._call("POST", "/facts", {"ticker": ticker, "facts": facts})

    async def write_note(self, ticker: str, content: str, source: str, refs: list[str], tags: list[str]) -> dict[str, Any]:
        return await self._call("POST", "/notes", {"ticker": ticker, "content": content, "source": source,
                                                    "refs": refs, "tags": tags})

    async def audit(self, memory_id: str) -> dict[str, Any]:
        return await self._call("GET", f"/memories/{memory_id}/audit")
