"""Meterless Runtime provider (OpenAI-compatible), implementing the published contract for
Meterless Runtime 0.90.0 (github.com/meterless/meterless, docs/agent-ready/add-meterless-provider.md):

- default base URL http://127.0.0.1:8088/v1; any pasted URL is normalised to <host>/v1
- Authorization: Bearer <token> on every call; token from <stateDir>/proxy-token; "rt-local" rejected
- meterless-app: <stable app id> on every request, meterless-scope: user on chat
- model ids are routing modes (meterless/auto, fast, deep, cheap, local, fusion, ...), read from /v1/models
- GET /v1/models decides status: 401/403 = unauthorized, 200 with meterless ids = online, else offline
- auto detect ports 8088, 8090, 8787, 11434 on 127.0.0.1, localhost and [::1]
- 180 s timeout for chat (cold model loads can take minutes)
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

APP_ID = "parallax-ai"
CHAT_TIMEOUT_S = 180.0
PROBE_TIMEOUT_S = 2.5
DETECT_PORTS = (8088, 8090, 8787, 11434)
DETECT_HOSTS = ("127.0.0.1", "localhost", "[::1]")


def normalize_base_url(raw: str) -> str:
    url = raw.strip()
    if not url:
        return "http://127.0.0.1:8088/v1"
    if not re.match(r"^https?://", url, re.I):
        url = "http://" + url
    url = url.rstrip("/")
    for suffix in ("/v1/chat/completions", "/v1/models", "/healthz", "/v1"):
        if url.lower().endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url.rstrip("/") + "/v1"


# Where the Nightshift desktop apps keep their runtime token (the Mac app names it "runtime-token"; the published
# contract calls it <stateDir>/proxy-token). Used only when no token or token file is configured.
NIGHTSHIFT_STATE_GLOB = "Library/Application Support/ai.meterless.nightshift*"
TOKEN_NAMES = ("runtime-token", "proxy-token")


def discover_token_file(home: Optional[Path] = None) -> Optional[Path]:
    for state_dir in sorted((home or Path.home()).glob(NIGHTSHIFT_STATE_GLOB)):
        for name in TOKEN_NAMES:
            if (state_dir / name).is_file():
                return state_dir / name
    return None


def resolve_token(token: str, token_file: str) -> str:
    if not token and not token_file:
        found = discover_token_file()
        token_file = str(found) if found else ""
    if not token and token_file:
        p = Path(token_file).expanduser()
        if p.exists():
            token = p.read_text().strip()
    if token == "rt-local":
        return ""  # placeholder is rejected by the runtime; treat as missing
    return token


@dataclass
class RuntimeStatus:
    state: str  # online | unauthorized | offline
    base_url: str
    models: list[str]
    detail: str = ""


class MeterlessRuntime:
    def __init__(self, base_url: str, token: str, model: str = "meterless/auto"):
        self.base_url = normalize_base_url(base_url)
        self.token = token
        self.model = model

    def _headers(self, chat: bool = False) -> dict[str, str]:
        h = {"meterless-app": APP_ID}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if chat:
            h["meterless-scope"] = "user"
        return h

    async def status(self, base_url: Optional[str] = None) -> RuntimeStatus:
        url = normalize_base_url(base_url or self.base_url)
        try:
            async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_S) as c:
                r = await c.get(url + "/models", headers=self._headers())
        except httpx.HTTPError as exc:
            return RuntimeStatus("offline", url, [], f"unreachable: {exc.__class__.__name__}")
        if r.status_code in (401, 403):
            return RuntimeStatus("unauthorized", url, [], "token missing or rejected; paste the token from <stateDir>/proxy-token")
        if r.status_code == 200:
            try:
                ids = [m.get("id", "") for m in r.json().get("data", [])]
            except (ValueError, AttributeError):
                ids = []
            ids = [i for i in ids if isinstance(i, str)]
            if any(i.startswith("meterless/") for i in ids):
                return RuntimeStatus("online", url, ids)
            return RuntimeStatus("offline", url, ids, "endpoint answered but lists no meterless/* models")
        return RuntimeStatus("offline", url, [], f"HTTP {r.status_code}")

    async def auto_detect(self) -> RuntimeStatus:
        first = await self.status()
        if first.state in ("online", "unauthorized"):
            return first
        for host in DETECT_HOSTS:
            for port in DETECT_PORTS:
                st = await self.status(f"http://{host}:{port}/v1")
                if st.state in ("online", "unauthorized"):
                    self.base_url = st.base_url
                    return st
        return first

    async def chat(self, system: str, user: str) -> tuple[str, Optional[dict[str, Any]], str, int]:
        """Return (text, usage-as-returned, model-id-as-returned, duration_ms).

        Nemotron models (routed by Nightshift to NVIDIA) get chat_template_kwargs.enable_thinking=false: Parallax
        wants short structured output, and Nemotron's reasoning otherwise makes each call ~20x slower. If a model
        rejects the switch (HTTP 400), the call is retried once without it."""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
        }
        if self.model.lower().startswith("nvidia/nemotron"):
            body["chat_template_kwargs"] = {"enable_thinking": False}
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT_S) as c:
            r = await c.post(self.base_url + "/chat/completions", json=body, headers=self._headers(chat=True))
            if r.status_code == 400 and "chat_template_kwargs" in body:
                body.pop("chat_template_kwargs")
                r = await c.post(self.base_url + "/chat/completions", json=body, headers=self._headers(chat=True))
        duration = int((time.perf_counter() - t0) * 1000)
        if r.status_code in (401, 403):
            raise RuntimeError("Meterless Runtime rejected the token (unauthorized).")
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            raise RuntimeError("Meterless Runtime returned a non-string message content.")
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()  # any reasoning text is never shown
        return text, data.get("usage"), data.get("model", self.model), duration
