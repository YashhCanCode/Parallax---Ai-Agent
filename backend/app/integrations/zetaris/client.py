"""Zetaris HTTP client (UI proxy routes).

Every route, header and body field here is taken from Zetaris's official helpers in
github.com/zetaris/getting-started (scripts/zetaris_api.py, query_zetaris.py, check_zetaris.py):

  POST {ZETARIS_BASE_URL}/api/auth/login                       {"username", "password"} -> token
  GET  {ZETARIS_BASE_URL}/api/proxy/lightning-database/databases
  POST {ZETARIS_BASE_URL}/api/proxy/sql-editor/sqls/run-query  {"sql", "limit", "engineId"?}

Headers on proxied calls: Authorization: Bearer <token>, X-Org-ID: <numeric org id>,
X-Request-ID: <uuid4>. The run-query response carries a `data` array (object rows or array
rows) and optional `headers` naming the columns (see examples/pudl-chart/render.py).

Nothing in this module fabricates a result: on any failure it raises ZetarisError.
"""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings


class ZetarisError(RuntimeError):
    pass


class ZetarisNotConfigured(ZetarisError):
    pass


@dataclass
class ZetarisQueryResult:
    rows: list[dict[str, Any]]
    columns: list[str]
    request_id: str
    duration_ms: int
    sql: str
    raw_keys: list[str]


_JWT_RE = re.compile(r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")


def parse_query_response(payload: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Turn a run-query response into (rows-as-dicts, column-names).

    Accepts the documented shape {"data": [...], "headers": [...]}, where rows are either
    objects or arrays aligned with headers. Column names are lower-cased, as in the official
    renderer. Raises ZetarisError for any other shape rather than guessing.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ZetarisError("Unexpected run-query response: expected an object with a 'data' array.")
    headers = payload.get("headers") or []
    names: list[str] = []
    if isinstance(headers, list):
        for h in headers:
            name = h.get("name") if isinstance(h, dict) else h
            names.append(name.lower() if isinstance(name, str) else "")
    rows: list[dict[str, Any]] = []
    for row in payload["data"]:
        if isinstance(row, dict):
            rows.append({str(k).lower(): v for k, v in row.items()})
        elif isinstance(row, list):
            if len(row) != len(names) or "" in names or len(set(names)) != len(names):
                raise ZetarisError("Array rows need unique named headers matching the row length.")
            rows.append(dict(zip(names, row)))
        else:
            raise ZetarisError("Expected object rows or array rows with matching headers.")
    if not names and rows:
        names = list(rows[0].keys())
    return rows, names


class ZetarisClient:
    def __init__(self, settings: Settings, timeout_s: float = 30.0, max_attempts: int = 2):
        self.s = settings
        self.timeout_s = timeout_s
        self.max_attempts = max_attempts
        self._token: str | None = settings.zetaris_api_key or None

    # -- configuration ---------------------------------------------------------------
    def configuration_problems(self) -> list[str]:
        problems = []
        if not re.fullmatch(r"https?://[^/]+", self.s.zetaris_base_url):
            problems.append("ZETARIS_BASE_URL must be an http(s) origin with no path, e.g. http://localhost:3000")
        if not re.fullmatch(r"[0-9]+", self.s.zetaris_org_id or ""):
            problems.append("ZETARIS_ORG_ID must be your numeric organisation ID")
        if not self.s.zetaris_api_key and not (self.s.zetaris_username and self.s.zetaris_password):
            problems.append("Set ZETARIS_API_KEY, or both ZETARIS_USERNAME and ZETARIS_PASSWORD")
        return problems

    def ensure_configured(self) -> None:
        problems = self.configuration_problems()
        if problems:
            raise ZetarisNotConfigured("; ".join(problems))

    # -- auth --------------------------------------------------------------------------
    async def _login(self, client: httpx.AsyncClient) -> str:
        resp = await client.post(
            f"{self.s.zetaris_base_url}/api/auth/login",
            json={"username": self.s.zetaris_username, "password": self.s.zetaris_password},
            headers={"Content-Type": "application/json", "X-Request-ID": str(uuid.uuid4())},
        )
        if resp.status_code != 200:
            raise ZetarisError(f"Zetaris login failed: HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise ZetarisError("Zetaris login returned a non-JSON body.") from exc
        token = None
        if isinstance(body, dict):
            token = body.get("idToken") or body.get("token") or body.get("accessToken")
        if not token:
            match = _JWT_RE.search(resp.text)
            token = match.group(0) if match else None
        if not isinstance(token, str) or not token:
            raise ZetarisError("Zetaris login did not return an access token.")
        return token

    async def _request(self, method: str, path: str, body: Any = None) -> tuple[Any, str, int]:
        self.ensure_configured()
        started = time.perf_counter()
        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            for attempt in range(1, self.max_attempts + 1):
                request_id = str(uuid.uuid4())
                try:
                    if not self._token:
                        self._token = await self._login(client)
                    headers = {
                        "Authorization": f"Bearer {self._token}",
                        "X-Org-ID": self.s.zetaris_org_id,
                        "X-Request-ID": request_id,
                    }
                    resp = await client.request(method, f"{self.s.zetaris_base_url}{path}", json=body, headers=headers)
                except httpx.HTTPError as exc:
                    last_exc = ZetarisError(f"Cannot reach {self.s.zetaris_base_url}: {exc}")
                    if attempt < self.max_attempts:
                        await asyncio.sleep(0.5 * attempt)
                        continue
                    raise last_exc from exc
                if resp.status_code == 401 and not self.s.zetaris_api_key and attempt < self.max_attempts:
                    self._token = None  # token may have expired; log in again once
                    continue
                if resp.status_code >= 500 and attempt < self.max_attempts:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                if resp.status_code >= 400:
                    if "text/html" in resp.headers.get("content-type", ""):
                        detail = "The server returned an HTML page; check that ZETARIS_BASE_URL is the UI origin."
                    else:
                        detail = resp.text[:500]
                    raise ZetarisError(f"{method} {path} failed: HTTP {resp.status_code} {detail}")
                duration_ms = int((time.perf_counter() - started) * 1000)
                if resp.status_code == 204:
                    return None, request_id, duration_ms
                try:
                    return resp.json(), request_id, duration_ms
                except ValueError as exc:
                    raise ZetarisError(f"{method} {path} returned a non-JSON body") from exc
        raise last_exc or ZetarisError("Zetaris request failed")

    # -- public API --------------------------------------------------------------------
    async def list_databases(self) -> tuple[list[Any], str, int]:
        payload, request_id, duration_ms = await self._request("GET", "/api/proxy/lightning-database/databases")
        if not isinstance(payload, list):
            raise ZetarisError("Unexpected database-list response.")
        return payload, request_id, duration_ms

    async def run_query(self, sql: str, limit: int | None = None) -> ZetarisQueryResult:
        if not sql.strip():
            raise ZetarisError("SQL must not be empty.")
        body: dict[str, Any] = {"sql": sql, "limit": limit or self.s.zetaris_query_limit}
        if self.s.zetaris_engine_id:
            body["engineId"] = self.s.zetaris_engine_id
        payload, request_id, duration_ms = await self._request(
            "POST", "/api/proxy/sql-editor/sqls/run-query", body
        )
        rows, columns = parse_query_response(payload)
        return ZetarisQueryResult(
            rows=rows,
            columns=columns,
            request_id=request_id,
            duration_ms=duration_ms,
            sql=sql,
            raw_keys=sorted(payload.keys()) if isinstance(payload, dict) else [],
        )
