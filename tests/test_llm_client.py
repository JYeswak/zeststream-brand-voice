"""Tests for the LLM foundation layer.

Live Anthropic calls are gated behind ``@pytest.mark.llm`` and skipped when
``ANTHROPIC_API_KEY`` is unset, so CI without a key still passes. Import
and structural checks run unconditionally.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from zeststream_voice.llm.client import (
    ANTHROPIC_API_KEY_HELP,
    AVAILABLE_MODELS,
    AnthropicClient,
    DEFAULT_MODEL,
    LLMClient,
    LLMClientError,
    default_model,
    make_client,
)
from zeststream_voice.llm.context import VoiceContext, build_voice_context
from zeststream_voice.llm.regen_loop import (
    GenerationResult,
    generate_with_voice_gate,
)


# ---------------------------------------------------------------------------
# Structural tests (run without a live API key)
# ---------------------------------------------------------------------------


def test_default_model_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZV_LLM_MODEL", raising=False)
    assert default_model() == DEFAULT_MODEL

    monkeypatch.setenv("ZV_LLM_MODEL", "claude-sonnet-4-6")
    assert default_model() == "claude-sonnet-4-6"


def test_available_models_list() -> None:
    models = LLMClient.available_models()
    assert DEFAULT_MODEL in models
    assert "claude-sonnet-4-6" in models
    assert "claude-opus-4-7" in models
    # Caller-safe: mutation doesn't leak into the module constant.
    models.append("noop")
    assert "noop" not in AVAILABLE_MODELS


def test_missing_api_key_raises_with_helpful_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMClientError) as excinfo:
        AnthropicClient()
    assert "ANTHROPIC_API_KEY" in str(excinfo.value)
    assert ANTHROPIC_API_KEY_HELP.splitlines()[0] in str(excinfo.value)


def test_make_client_rejects_unknown_model_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Post–Grok factory rework: routing is by model prefix, not ZV_LLM_PROVIDER."""
    monkeypatch.delenv("ZV_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    with pytest.raises(LLMClientError):
        make_client(model="gpt-4")


def test_build_voice_context_loads_voice_and_exemplars(zeststream_brand: Path) -> None:
    ctx = build_voice_context(brand_path=zeststream_brand, surface="hero")
    assert isinstance(ctx, VoiceContext)
    assert ctx.brand_slug == "zeststream"
    assert ctx.surface == "hero"

    # System prompt is a list of typed blocks
    assert isinstance(ctx.system, list)
    assert all(isinstance(b, dict) and "type" in b for b in ctx.system)

    # At least one block requests caching (the big stable one)
    assert ctx.cache_anchors >= 1

    # The cached block actually carries voice content
    cached_text = "\n".join(b["text"] for b in ctx.cached_chunks)
    assert "CANON" in cached_text
    assert "zeststream" in cached_text.lower() or "ZestStream" in cached_text

    # Hero exemplars exist and at least one is referenced
    assert any("exemplars/hero" in p for p in ctx.exemplars_loaded)


def test_build_voice_context_tolerates_missing_situation(zeststream_brand: Path) -> None:
    ctx = build_voice_context(brand_path=zeststream_brand, surface="linkedin", situation_key="nonexistent")
    # linkedin has no exemplar folder yet — should fall back cleanly without raising
    assert isinstance(ctx, VoiceContext)
    assert ctx.cache_anchors >= 1


def test_build_voice_context_without_surface(zeststream_brand: Path) -> None:
    ctx = build_voice_context(brand_path=zeststream_brand)
    assert ctx.surface is None
    assert ctx.cache_anchors >= 1


# ---------------------------------------------------------------------------
# Regen-loop unit test with a fake client (no API call)
# ---------------------------------------------------------------------------


class _StubScoreResult:
    def __init__(self, composite: float, passed: bool) -> None:
        self.composite = composite
        self.passed = passed
        self.layers = {"layer1_banned": type("L", (), {"score": composite})()}
        self.banned_hits: list[tuple[str, list[int]]] = []


class _StubScorer:
    def __init__(self, scores: list[float]) -> None:
        self._scores = list(scores)

    def score(self, text: str):  # noqa: ARG002
        value = self._scores.pop(0) if self._scores else 100.0
        return _StubScoreResult(composite=value, passed=value >= 95)


class _StubClient(LLMClient):
    model = "stub-model"

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)
        self.calls = 0

    def _generate(self, system, user, max_tokens, temperature):  # noqa: ARG002
        from zeststream_voice.llm.client import LLMResponse

        self.calls += 1
        text = self._texts.pop(0) if self._texts else "ok"
        return LLMResponse(text=text, model=self.model, input_tokens=100, output_tokens=50)


def test_regen_loop_returns_on_first_pass(zeststream_brand: Path) -> None:
    ctx = build_voice_context(brand_path=zeststream_brand, surface="hero")
    client = _StubClient(texts=["great draft"])
    scorer = _StubScorer(scores=[97.0])

    result = generate_with_voice_gate(client, ctx, "write something", scorer, max_attempts=3)

    assert isinstance(result, GenerationResult)
    assert result.passed is True
    assert result.attempts_used == 1
    assert client.calls == 1
    assert result.composite == 97.0


def test_regen_loop_retries_then_passes(zeststream_brand: Path) -> None:
    ctx = build_voice_context(brand_path=zeststream_brand, surface="hero")
    client = _StubClient(texts=["bad", "better", "good"])
    scorer = _StubScorer(scores=[70.0, 88.0, 96.0])

    result = generate_with_voice_gate(client, ctx, "write something", scorer, max_attempts=3)

    assert result.passed is True
    assert result.attempts_used == 3
    assert result.composite == 96.0
    assert len(result.attempts) == 3


def test_regen_loop_gives_up_after_max(zeststream_brand: Path) -> None:
    ctx = build_voice_context(brand_path=zeststream_brand, surface="hero")
    client = _StubClient(texts=["bad", "bad", "bad"])
    scorer = _StubScorer(scores=[50.0, 55.0, 60.0])

    result = generate_with_voice_gate(client, ctx, "write something", scorer, max_attempts=3)

    assert result.passed is False
    assert result.attempts_used == 3
    assert result.composite == 60.0


# ---------------------------------------------------------------------------
# Live Anthropic smoke test (gated on API key presence)
# ---------------------------------------------------------------------------


@pytest.mark.llm
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping live LLM smoke test",
)
def test_anthropic_client_live_smoke(zeststream_brand: Path) -> None:
    client = AnthropicClient()
    ctx = build_voice_context(brand_path=zeststream_brand, surface="hero")

    # Sanity: cache_control is set on the large block
    assert ctx.system[0].get("cache_control", {}).get("type") == "ephemeral"

    resp = client.generate(
        system=ctx.system,
        user="Reply with exactly: OK",
        max_tokens=16,
        temperature=0.0,
    )
    assert resp.text.strip()
    assert resp.model == client.model
