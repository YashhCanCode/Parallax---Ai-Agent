"""NVIDIA hosted API (build.nvidia.com) for Nemotron models. OpenAI-compatible.

Verified 2026-10-24:
  GET  https://integrate.api.nvidia.com/v1/models            (public list; includes nvidia/nemotron-* ids)
  POST https://integrate.api.nvidia.com/v1/chat/completions  (Authorization: Bearer <key>; 401 without, 403 if invalid)
Nemotron 3 models document a reasoning switch, chat_template_kwargs.enable_thinking. FinSight turns it off
(short structured output, no arithmetic delegated to the model). If the hosted service rejects that field,
the call is retried once without it. Any <think>...</think> block is removed before validation.
"""
from __future__ import annotations

import re
import time
from typing import Any, Optional

import httpx

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


class NvidiaError(RuntimeError):
    pass


class NvidiaClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE_URL, timeout_s: float = 90.0):
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

    async def check(self) -> tuple[str, str]:
        """('online'|'unauthorized'|'offline'|'model_missing', detail). Uses the public model list plus a 1-token call."""
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(self.base_url + "/models", headers=self._headers())
                if r.status_code != 200:
                    return "offline", f"models list HTTP {r.status_code}"
                ids = {m.get("id") for m in r.json().get("data", [])}
                if self.model not in ids:
                    return "model_missing", f"{self.model} is not in the NVIDIA model list"
                p = await c.post(self.base_url + "/chat/completions", headers=self._headers(),
                                 json={"model": self.model, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 1})
        except httpx.HTTPError as exc:
            return "offline", exc.__class__.__name__
        if p.status_code in (401, 403):
            return "unauthorized", "NVIDIA_API_KEY was rejected"
        if p.status_code >= 400:
            return "offline", f"chat HTTP {p.status_code}: {p.text[:120]}"
        return "online", self.model

    async def chat(self, system: str, user: str, json_schema: Optional[dict[str, Any]] = None,
                   schema_name: str = "finsight_output") -> tuple[str, Optional[dict[str, Any]], str, int]:
        """Return (text, usage-as-returned, model-id-as-returned, duration_ms).

        With json_schema, the request asks the service to constrain output to that schema
        (OpenAI-style response_format json_schema; verified on the hosted Nemotron 3.5 Lightning, 2026-10-24).
        FinSight still validates the result itself; the constraint only prevents malformed JSON.
        """
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
            "max_tokens": 1200,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if json_schema is not None:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": schema_name, "schema": json_schema, "strict": True}}
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout_s) as c:
            r = await c.post(self.base_url + "/chat/completions", headers=self._headers(), json=body)
            for field in ("chat_template_kwargs", "response_format"):  # drop an option the model rejects, once each
                if r.status_code in (400, 422) and field in r.text and field in body:
                    body.pop(field)
                    r = await c.post(self.base_url + "/chat/completions", headers=self._headers(), json=body)
        duration = int((time.perf_counter() - t0) * 1000)
        if r.status_code in (401, 403):
            raise NvidiaError("NVIDIA API rejected the key (unauthorized).")
        if r.status_code == 429:
            raise NvidiaError("NVIDIA API rate limit reached (HTTP 429).")
        if r.status_code >= 400:
            raise NvidiaError(f"NVIDIA API HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        msg = data["choices"][0]["message"]
        text = msg.get("content") or ""
        if not isinstance(text, str):
            raise NvidiaError("NVIDIA API returned non-string content.")
        return _THINK.sub("", text).strip(), data.get("usage"), data.get("model", self.model), duration
