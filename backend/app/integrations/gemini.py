"""Google Gemini REST client (Generative Language API v1beta).

  GET  https://generativelanguage.googleapis.com/v1beta/models
  POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
  auth header: x-goog-api-key

Model ids change over time, so none is hardcoded: GEMINI_MODEL is used when set, otherwise
the first "flash" model that the key can call with generateContent is chosen from models.list.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiClient:
    def __init__(self, api_key: str, model: str = "", timeout_s: float = 60.0):
        self.api_key = api_key
        self.model = model.removeprefix("models/")
        self.timeout_s = timeout_s

    async def resolve_model(self) -> str:
        if self.model:
            return self.model
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{BASE}/models", headers={"x-goog-api-key": self.api_key}, params={"pageSize": 200})
        r.raise_for_status()
        models = r.json().get("models", [])
        usable = [m["name"].removeprefix("models/") for m in models
                  if "generateContent" in m.get("supportedGenerationMethods", [])]
        flash = [m for m in usable if "flash" in m and "preview" not in m and "exp" not in m] or usable
        if not flash:
            raise RuntimeError("No Gemini model supporting generateContent is available to this key.")
        self.model = sorted(flash)[-1]
        return self.model

    async def generate_json(self, system: str, user: str) -> tuple[str, Optional[dict[str, Any]], str, int]:
        model = await self.resolve_model()
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout_s) as c:
            r = await c.post(f"{BASE}/models/{model}:generateContent", json=body,
                             headers={"x-goog-api-key": self.api_key})
        duration = int((time.perf_counter() - t0) * 1000)
        r.raise_for_status()
        data = r.json()
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
        return text, data.get("usageMetadata"), model, duration
