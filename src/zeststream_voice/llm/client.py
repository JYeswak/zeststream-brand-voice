"""LLM client abstraction for the zv write quadrant.

One abstract ``LLMClient`` + one concrete ``AnthropicClient`` using the
Messages API with **prompt caching** on the system block. The voice context
(voice.yaml + exemplars) is stable across calls in a session, so caching it
cuts per-call cost dramatically.

Model selection
---------------
- Env ``ZV_LLM_MODEL`` overrides the default.
- Default: ``claude-haiku-4-5-20251001`` (cheap, fast, sufficient for voice work).
- Recommended overrides: ``claude-sonnet-4-6`` (harder rewrites), ``claude-opus-4-7`` (complex reply/negotiation).

Caching
-------
The client accepts a system prompt as either a plain string (no caching) or a
list of typed blocks (``{"type": "text", "text": ..., "cache_control": ...}``).
Callers building prompts from ``context.build_voice_context()`` get the cached
form for free.

Failure modes
-------------
- ``ANTHROPIC_API_KEY`` missing → ``LLMClientError`` with a clear setup hint.
- ``anthropic`` package missing → ``LLMClientError`` pointing at the extras.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional


DEFAULT_MODEL = "claude-haiku-4-5-20251001"
AVAILABLE_MODELS = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-7",
]

ANTHROPIC_API_KEY_HELP = (
    "ANTHROPIC_API_KEY is not set. Either:\n"
    "  export ANTHROPIC_API_KEY=sk-ant-...\n"
    "  or load via infisical: eval \"$(infisical-load --export zeststream)\"\n"
    "Then re-run. See Section 14 of ~/.claude/CLAUDE.md for Infisical details."
)


class LLMClientError(RuntimeError):
    """Raised when the LLM backend is unusable (missing key, missing pkg, API error)."""


def default_model() -> str:
    """Resolve the active model name via env override."""
    return os.environ.get("ZV_LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


@dataclass
class LLMResponse:
    """Uniform response envelope across providers."""

    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    stop_reason: Optional[str] = None
    raw: Any = None

    @property
    def cost_estimate_cents(self) -> float:
        """Rough cost in cents using Haiku-4.5 published rates.

        For precision, clients should consult ground-truth pricing table.
        This is a ballpark so the CLI can surface "this cost you ~0.2¢".
        """
        # Haiku-4.5: $0.25/M in, $1.25/M out, cache-read $0.03/M (10% of input)
        in_cost = (self.input_tokens + self.cache_creation_tokens) * 0.25 / 1_000_000
        cached_cost = self.cache_read_tokens * 0.03 / 1_000_000
        out_cost = self.output_tokens * 1.25 / 1_000_000
        return (in_cost + cached_cost + out_cost) * 100


class LLMClient:
    """Abstract LLM client.

    Subclasses must implement ``_generate``. Callers use ``generate``.
    """

    model: str = DEFAULT_MODEL

    def generate(
        self,
        system: str | list[dict[str, Any]],
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        return self._generate(system=system, user=user, max_tokens=max_tokens, temperature=temperature)

    def _generate(
        self,
        system: str | list[dict[str, Any]],
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        raise NotImplementedError

    @staticmethod
    def available_models() -> list[str]:
        return list(AVAILABLE_MODELS)


class AnthropicClient(LLMClient):
    """Anthropic Messages API client with prompt caching on system prompt.

    Parameters
    ----------
    model:
        Model name. Defaults to ``default_model()`` (env ``ZV_LLM_MODEL``).
    api_key:
        Explicit key. If None, reads ``ANTHROPIC_API_KEY`` from env.
    """

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.model = (model or default_model()).strip()
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise LLMClientError(ANTHROPIC_API_KEY_HELP)
        try:
            import anthropic  # noqa: F401
        except ImportError as exc:
            raise LLMClientError(
                "The `anthropic` package is not installed. "
                "Install with: pip install 'zeststream-voice[rubric]'"
            ) from exc
        self._client = self._build_client()

    def _build_client(self):
        import anthropic

        return anthropic.Anthropic(api_key=self._api_key)

    def _coerce_system(self, system: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalise system prompt to a block list.

        A plain string becomes a single uncached text block. A list is
        returned unchanged (callers are expected to attach ``cache_control``
        where appropriate).
        """
        if isinstance(system, str):
            return [{"type": "text", "text": system}]
        return list(system)

    def _generate(
        self,
        system: str | list[dict[str, Any]],
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        # The Anthropic SDK accepts a list of typed blocks for `system` (the
        # prompt-caching shape), but its type stubs are narrower than runtime
        # reality. Cast through Any to silence the static-type check.
        system_param: Any = self._coerce_system(system)
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_param,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            raise LLMClientError(f"Anthropic API call failed: {exc}") from exc

        text = ""
        for block in getattr(resp, "content", []) or []:
            # blocks may be TextBlock objects or dicts depending on SDK version
            block_type = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
            if block_type == "text":
                text += getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else "") or ""

        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) if usage else 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) if usage else 0,
            stop_reason=getattr(resp, "stop_reason", None),
            raw=resp,
        )


def make_client(model: Optional[str] = None, api_key: Optional[str] = None) -> LLMClient:
    """Factory: return the configured default client.

    Currently returns ``AnthropicClient``. When other providers land, this
    function reads a ``ZV_LLM_PROVIDER`` env var to pick between them.
    """
    provider = os.environ.get("ZV_LLM_PROVIDER", "anthropic").strip().lower()
    if provider == "anthropic":
        return AnthropicClient(model=model, api_key=api_key)
    raise LLMClientError(
        f"Unknown ZV_LLM_PROVIDER={provider!r}. Supported: anthropic."
    )
