from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from autoresearch.config import Settings


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    provider: str
    raw: dict[str, Any]


class LLMService:
    """Optional OpenAI-compatible boundary. Secrets remain inside Settings."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def available(self) -> bool:
        return self.settings.llm_configured

    def complete(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> LLMResult | None:
        if not self.available:
            return None
        assert self.settings.llm_base_url
        assert self.settings.llm_model
        assert self.settings.llm_api_key

        endpoint = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
            response = client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            raw = response.json()
        text = raw["choices"][0]["message"]["content"]
        return LLMResult(
            text=text,
            model=self.settings.llm_model,
            provider=self.settings.llm_provider,
            raw={"id": raw.get("id"), "usage": raw.get("usage", {})},
        )

    def complete_json(self, *, system: str, user: str) -> dict[str, Any] | None:
        result = self.complete(system=system, user=user, json_mode=True)
        if result is None:
            return None
        return json.loads(result.text)
