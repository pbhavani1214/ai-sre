"""Minimal LLM provider abstraction using only the standard library (no SDKs).

Environment variables:
    LLM_PROVIDER   anthropic (default) | openai
    LLM_API_KEY    falls back to ANTHROPIC_API_KEY / OPENAI_API_KEY
    LLM_MODEL      optional model override
    LLM_BASE_URL   optional (e.g. an OpenAI-compatible endpoint)
    LLM_TIMEOUT    seconds, default 120
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod


class LLMError(RuntimeError):
    pass


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Return the model's text response."""


def _post_json(url: str, headers: dict[str, str], payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers={"content-type": "application/json", **headers}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise LLMError(f"HTTP {e.code} from {url}: {e.read().decode('utf-8', 'replace')[:500]}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"Could not reach {url}: {e.reason}") from e


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-5", base_url: str = "https://api.anthropic.com",
                 timeout: float = 120, max_tokens: int = 4096):
        self.api_key, self.model, self.base_url = api_key, model, base_url.rstrip("/")
        self.timeout, self.max_tokens = timeout, max_tokens

    def complete(self, system: str, user: str) -> str:
        data = _post_json(
            f"{self.base_url}/v1/messages",
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            {"model": self.model, "max_tokens": self.max_tokens, "system": system,
             "messages": [{"role": "user", "content": user}]},
            self.timeout,
        )
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", base_url: str = "https://api.openai.com/v1",
                 timeout: float = 120):
        self.api_key, self.model, self.base_url, self.timeout = api_key, model, base_url.rstrip("/"), timeout

    def complete(self, system: str, user: str) -> str:
        data = _post_json(
            f"{self.base_url}/chat/completions",
            {"authorization": f"Bearer {self.api_key}"},
            {"model": self.model, "response_format": {"type": "json_object"},
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            self.timeout,
        )
        return data["choices"][0]["message"]["content"]


def get_provider() -> LLMProvider:
    name = os.getenv("LLM_PROVIDER", "anthropic").lower()
    timeout = float(os.getenv("LLM_TIMEOUT", "120"))
    model, base_url = os.getenv("LLM_MODEL"), os.getenv("LLM_BASE_URL")

    if name == "anthropic":
        key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        cls, kwargs = AnthropicProvider, {}
    elif name == "openai":
        key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        cls, kwargs = OpenAIProvider, {}
    else:
        raise LLMError(f"Unknown LLM_PROVIDER '{name}' (expected 'anthropic' or 'openai')")
    if not key:
        raise LLMError(f"No API key set for provider '{name}'. Set LLM_API_KEY.")
    if model:
        kwargs["model"] = model
    if base_url:
        kwargs["base_url"] = base_url
    return cls(api_key=key, timeout=timeout, **kwargs)
