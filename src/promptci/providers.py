"""Model providers. Anything that speaks the OpenAI /v1/chat/completions dialect works:
Ollama, LM Studio, vLLM, llama.cpp server — plus cloud APIs if you point base_url at them.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx

from .errors import ProviderError
from .schema import Defaults


class BaseProvider:
    name = "base"

    def complete(
        self, *, model: str, system: str | None, user: str, temperature: float, timeout: float
    ) -> str:
        raise NotImplementedError


class MockProvider(BaseProvider):
    """Deterministic offline provider. If the prompt contains a line starting with
    MOCK_RESPONSE:, that line's remainder is returned verbatim — so demo workflows
    and tests run with no model server and no network."""

    name = "mock"

    def complete(
        self, *, model: str, system: str | None, user: str, temperature: float, timeout: float
    ) -> str:
        for line in user.splitlines():
            if line.strip().startswith("MOCK_RESPONSE:"):
                return line.split(":", 1)[1].strip()
        return f"[mock:{hashlib.sha1((model + user).encode()).hexdigest()[:8]}]"


class OpenAICompatProvider(BaseProvider):
    name = "openai-compat"

    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def complete(
        self, *, model: str, system: str | None, user: str, temperature: float, timeout: float
    ) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": False,
                },
                headers=headers,
                timeout=timeout,
            )
        except httpx.HTTPError as e:
            raise ProviderError(
                f"could not reach model server at {self.base_url} "
                f"({e.__class__.__name__}) — is it running? e.g. `ollama serve`"
            ) from e
        if resp.status_code >= 400:
            raise ProviderError(
                f"model server at {self.base_url} returned HTTP {resp.status_code}: "
                f"{resp.text[:300]}"
            )
        try:
            content: str | None = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise ProviderError(
                f"unexpected response shape from {self.base_url}: {resp.text[:300]}"
            ) from e
        if content is None:
            raise ProviderError(f"model returned no content: {resp.text[:300]}")
        return content


def make_provider(defaults: Defaults) -> BaseProvider:
    base = defaults.base_url
    if base.startswith("mock"):
        return MockProvider()
    api_key = os.environ.get(defaults.api_key_env or "", "") or os.environ.get("OPENAI_API_KEY", "")
    return OpenAICompatProvider(base, api_key=api_key or None)


def list_models(base_url: str, api_key: str | None = None, timeout: float = 5.0) -> list[str]:
    """Ask an OpenAI-compatible server which models it serves. Raises ProviderError."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=timeout)
    except httpx.HTTPError as e:
        raise ProviderError(
            f"could not reach model server at {base_url} ({e.__class__.__name__}) "
            "— is it running? e.g. `ollama serve`"
        ) from e
    if resp.status_code >= 400:
        raise ProviderError(f"model server returned HTTP {resp.status_code} for /models")
    try:
        data: list[dict[str, Any]] = resp.json().get("data", [])
    except ValueError as e:
        raise ProviderError(f"unexpected /models response from {base_url}") from e
    return [m.get("id", "") for m in data]
