"""xAI Grok provider for the zv write quadrant.

Uses the ``openai`` SDK pointed at ``https://api.x.ai/v1`` — the xAI API is
OpenAI-chat-completions-compatible, and reusing the openai client drops a
dependency vs. pulling in xai-sdk.

Caching
-------
Grok has **no equivalent to Anthropic prompt-caching cache_control**. The
``cache_anchors`` that ``build_voice_context`` emits are informational for
this client — the cached block is concatenated into the system message and
sent every call. For heavy-voice-context workloads where the system prompt
stays stable across many calls, ``AnthropicClient`` is cheaper. Grok wins
when the context is small, the generation is one-shot, or the reasoning
depth on tech-register content matters more than per-call cost.

Models
------
- ``grok-4`` — default for this client, xAI flagship reasoning model.
- ``grok-code`` — code-specialised.
- ``grok-4-fast`` — lower-latency variant.

Failure modes
-------------
- ``XAI_API_KEY`` missing → ``LLMClientError`` with a clear setup hint.
- ``openai`` package missing → ``LLMClientError`` pointing at the ``grok`` extra.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from zeststream_voice.llm.client import (
    LLMClient,
    LLMClientError,
    LLMResponse,
)


GROK_DEFAULT_MODEL = "grok-4"
GROK_AVAILABLE_MODELS = [
    "grok-4",
    "grok-code",
    "grok-4-fast",
]
GROK_BASE_URL = "https://api.x.ai/v1"

XAI_API_KEY_HELP = (
    "XAI_API_KEY is not set. Either:\n"
    "  export XAI_API_KEY=xai-...\n"
    "  or load via infisical: eval \"$(infisical-load --export zeststream)\"\n"
    "Then re-run. See Section 14 of ~/.claude/CLAUDE.md for Infisical details."
)


class GrokClient(LLMClient):
    """xAI Grok client via the OpenAI-compatible chat completions endpoint.

    Parameters
    ----------
    model:
        Model name. Defaults to ``grok-4``. Env ``ZV_LLM_MODEL`` overrides
        when it starts with ``grok``; otherwise callers should pass the model
        explicitly via the factory.
    api_key:
        Explicit key. If None, reads ``XAI_API_KEY`` from env.
    """

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None) -> None:
        env_model = os.environ.get("ZV_LLM_MODEL", "").strip()
        if model:
            self.model = model.strip()
        elif env_model.startswith("grok"):
            self.model = env_model
        else:
            self.model = GROK_DEFAULT_MODEL

        self._api_key = api_key or os.environ.get("XAI_API_KEY")
        if not self._api_key:
            raise LLMClientError(XAI_API_KEY_HELP)
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise LLMClientError(
                "The `openai` package is not installed. "
                "Install with: pip install 'zeststream-voice[grok]'"
            ) from exc
        self._client = self._build_client()

    def _build_client(self):
        from openai import OpenAI

        return OpenAI(api_key=self._api_key, base_url=GROK_BASE_URL)

    @staticmethod
    def available_models() -> list[str]:
        return list(GROK_AVAILABLE_MODELS)

    def _coerce_system_to_text(self, system: str | list[dict[str, Any]]) -> str:
        """Flatten Anthropic-style typed blocks into a single string.

        Anthropic callers may pass ``[{"type": "text", "text": "...", "cache_control": ...}, ...]``.
        Grok/openai only wants a plain string system message. Cache anchors
        are silently dropped (see module docstring).
        """
        if isinstance(system, str):
            return system
        parts: list[str] = []
        for block in system:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text"):
                parts.append(str(block["text"]))
        return "\n\n".join(parts)

    def _generate(
        self,
        system: str | list[dict[str, Any]],
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        system_text = self._coerce_system_to_text(system)
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": user},
                ],
            )
        except Exception as exc:
            raise LLMClientError(f"xAI API call failed: {exc}") from exc

        text = ""
        choices = getattr(resp, "choices", None) or []
        if choices:
            msg = getattr(choices[0], "message", None)
            content = getattr(msg, "content", None) if msg is not None else None
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                # OpenAI may return parts list for multimodal — flatten text parts.
                for part in content:
                    t = getattr(part, "text", None)
                    if t is None and isinstance(part, dict):
                        t = part.get("text")
                    if t:
                        text += t

        usage = getattr(resp, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        stop_reason = None
        if choices:
            stop_reason = getattr(choices[0], "finish_reason", None)

        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_tokens=0,  # Grok has no cache surface.
            cache_read_tokens=0,
            stop_reason=stop_reason,
            raw=resp,
        )
