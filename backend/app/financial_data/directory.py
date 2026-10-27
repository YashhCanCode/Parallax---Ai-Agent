"""Directory of SEC-listed companies, from the SEC's official file
https://www.sec.gov/files/company_tickers_exchange.json  ({"fields": ["cik","name","ticker","exchange"], "data": [...]})

Cached on disk for 24 hours. If the SEC can't be reached, the last cached copy is used; if there is
none, only Parallax's built-in companies are available, and lookups say so. Set
FINSIGHT_COMPANY_DIRECTORY to a local file of the same shape to run fully offline (used by tests).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from app.config import get_settings

SEC_DIRECTORY_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_TTL_S = 24 * 3600
log = logging.getLogger("finsight.directory")


@dataclass(frozen=True)
class DirectoryEntry:
    ticker: str
    name: str
    cik: str  # 10-digit, zero padded
    exchange: str


class CompanyDirectory:
    def __init__(self) -> None:
        self._by_ticker: dict[str, DirectoryEntry] = {}
        self._loaded_at = 0.0
        self.source = "not loaded"
        self.error: Optional[str] = None
        self._lock = threading.Lock()

    # -- loading -------------------------------------------------------------------------
    def _parse(self, payload: dict) -> dict[str, DirectoryEntry]:
        fields = payload.get("fields")
        rows = payload.get("data")
        if fields != ["cik", "name", "ticker", "exchange"] or not isinstance(rows, list):
            raise ValueError("Unexpected SEC directory format.")
        out: dict[str, DirectoryEntry] = {}
        for cik, name, ticker, exchange in rows:
            if not ticker or not cik:
                continue
            t = str(ticker).upper().strip()
            out.setdefault(t, DirectoryEntry(t, str(name).strip(), f"{int(cik):010d}", exchange or ""))
        return out

    def _load(self) -> None:
        override = os.environ.get("FINSIGHT_COMPANY_DIRECTORY", "").strip()
        if override:
            self._by_ticker = self._parse(json.loads(Path(override).read_text()))
            self.source, self._loaded_at = f"file {override}", time.time()
            return
        s = get_settings()
        cache = s.cache_dir / "sec" / "company_tickers_exchange.json"
        fresh = cache.exists() and time.time() - cache.stat().st_mtime < _TTL_S
        if not fresh and s.sec_user_agent and "@" in s.sec_user_agent:
            try:
                r = httpx.get(SEC_DIRECTORY_URL, headers={"User-Agent": s.sec_user_agent}, timeout=20)
                r.raise_for_status()
                self._by_ticker = self._parse(r.json())
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(r.text)
                self.source, self.error, self._loaded_at = "SEC (live)", None, time.time()
                return
            except (httpx.HTTPError, ValueError) as exc:
                self.error = f"Could not refresh the SEC company list: {exc}"
                log.warning(self.error)
        if cache.exists():
            self._by_ticker = self._parse(json.loads(cache.read_text()))
            self.source = "SEC (cached)" + ("" if fresh else ", refresh failed")
            self._loaded_at = time.time()
            return
        if not (s.sec_user_agent and "@" in s.sec_user_agent):
            self.error = "Set SEC_USER_AGENT to load the SEC company list; only built-in companies are available."
        self._loaded_at = time.time()  # retry after the TTL rather than on every lookup

    def ensure_loaded(self) -> None:
        with self._lock:
            if not self._by_ticker and self._loaded_at and time.time() - self._loaded_at < 300:
                return  # recent failed attempt; don't hammer the SEC
            if not self._by_ticker or time.time() - self._loaded_at > _TTL_S:
                self._load()

    # -- queries -------------------------------------------------------------------------
    def get(self, ticker: str) -> Optional[DirectoryEntry]:
        self.ensure_loaded()
        return self._by_ticker.get(ticker.upper().strip())

    def __len__(self) -> int:
        return len(self._by_ticker)

    def search(self, query: str, limit: int = 15) -> list[DirectoryEntry]:
        self.ensure_loaded()
        q = query.strip().upper()
        if not q:
            return []
        word = re.compile(rf"\b{re.escape(q)}")
        scored: list[tuple[int, str, DirectoryEntry]] = []
        for e in self._by_ticker.values():
            name = e.name.upper()
            if e.ticker == q:
                rank = 0
            elif e.ticker.startswith(q):
                rank = 1
            elif name.startswith(q):
                rank = 2
            elif word.search(name):
                rank = 3
            elif len(q) >= 3 and q in name:  # mid-word matches only once the query is specific enough
                rank = 4
            else:
                continue
            # Prefer major exchanges over OTC within the same rank.
            scored.append((rank * 10 + (0 if e.exchange in ("Nasdaq", "NYSE") else 1), e.ticker, e))
        scored.sort(key=lambda x: (x[0], len(x[1]), x[1]))
        return [e for _, _, e in scored[:limit]]


DIRECTORY = CompanyDirectory()
