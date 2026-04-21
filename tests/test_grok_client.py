"""Tests for the xAI Grok provider + factory routing.

Live xAI calls gate behind ``@pytest.mark.llm`` + ``XAI_API_KEY``. Structural
tests (import, factory routing, error paths) run unconditionally.
"""

from __future__ import annotations

import os

import pytest

from zeststream_voice.llm.client import (
    ANTHROPIC_API_KEY_HELP,
    MODEL_PREFIXES,
    AnthropicClient,
    LLMClient,
    LLMClientError,
    get_llm_client,
    make_client,
)
from zeststream_voice.llm.grok import (
    GROK_AVAILABLE_MODELS,
    GROK_DEFAULT_MODEL,
    GrokClient,
    XAI_API_KEY_HELP,
)


# ---------------------------------------------------------------------------
# Structural tests (no live calls)
# ---------------------------------------------------------------------------


def test_grok_client_class_implements_llm_interface() -> None:
    assert issubclass(GrokClient, LLMClient)
    assert hasattr(GrokClient, "_generate")
    assert hasattr(GrokClient, "available_models")
    assert callable(GrokClient.available_models)


def test_grok_available_models_lists_defaults() -> None:
    models = GrokClient.available_models()
    assert "grok-4" in models
    assert "grok-code" in models
    assert "grok-4-fast" in models
    # Default is grok-4.
    assert GROK_DEFAULT_MODEL == "grok-4"
    # Mutating the returned list doesn't leak into the module constant.
    models.append("noop")
    assert "noop" not in GROK_AVAILABLE_MODELS


def test_grok_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(LLMClientError) as excinfo:
        GrokClient()
    assert "XAI_API_KEY" in str(excinfo.value)
    assert XAI_API_KEY_HELP.splitlines()[0] in str(excinfo.value)


def test_grok_missing_openai_package_message_is_clear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `openai` isn't installed, the error must point at the right extra."""
    import builtins

    monkeypatch.setenv("XAI_API_KEY", "fake-key-for-test")
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openai":
            raise ImportError("simulated: openai not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(LLMClientError) as excinfo:
        GrokClient()
    msg = str(excinfo.value)
    assert "openai" in msg
    assert "zeststream-voice[grok]" in msg


# ---------------------------------------------------------------------------
# Factory routing
# ---------------------------------------------------------------------------


def test_model_prefixes_registered() -> None:
    assert "claude" in MODEL_PREFIXES
    assert "grok" in MODEL_PREFIXES
    providers = {p for p, _ in MODEL_PREFIXES.values()}
    assert providers == {"anthropic", "grok"}


def test_get_llm_client_routes_grok_by_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "fake-key-for-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ZV_LLM_MODEL", raising=False)
    client = get_llm_client(model="grok-4")
    assert isinstance(client, GrokClient)
    assert client.model == "grok-4"


def test_get_llm_client_routes_claude_by_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("ZV_LLM_MODEL", raising=False)
    client = get_llm_client(model="claude-haiku-4-5-20251001")
    assert isinstance(client, AnthropicClient)


def test_get_llm_client_unknown_prefix_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    with pytest.raises(LLMClientError) as excinfo:
        get_llm_client(model="gpt-4")
    msg = str(excinfo.value)
    assert "prefix" in msg.lower()
    # Must list the known prefixes so the caller knows what's valid.
    assert "claude" in msg
    assert "grok" in msg


def test_get_llm_client_prefers_anthropic_when_both_keys_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic")
    monkeypatch.setenv("XAI_API_KEY", "fake-xai")
    monkeypatch.delenv("ZV_LLM_MODEL", raising=False)
    client = get_llm_client(model=None)
    assert isinstance(client, AnthropicClient)


def test_get_llm_client_falls_back_to_grok_when_only_xai_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "fake-xai")
    monkeypatch.delenv("ZV_LLM_MODEL", raising=False)
    client = get_llm_client(model=None)
    assert isinstance(client, GrokClient)


def test_get_llm_client_zv_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZV_LLM_MODEL", "grok-4-fast")
    monkeypatch.setenv("XAI_API_KEY", "fake-xai")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = get_llm_client(model=None)
    assert isinstance(client, GrokClient)
    assert client.model == "grok-4-fast"


def test_get_llm_client_no_keys_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("ZV_LLM_MODEL", raising=False)
    with pytest.raises(LLMClientError) as excinfo:
        get_llm_client()
    # The Anthropic setup hint is the default nudge (most common path).
    assert "ANTHROPIC_API_KEY" in str(excinfo.value)
    assert ANTHROPIC_API_KEY_HELP.splitlines()[0] in str(excinfo.value)


def test_make_client_is_backwards_compatible_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing call sites using `make_client` must still work."""
    monkeypatch.setenv("XAI_API_KEY", "fake-xai")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = make_client(model="grok-4")
    assert isinstance(client, GrokClient)


# ---------------------------------------------------------------------------
# System-prompt coercion (Grok flattens Anthropic-style blocks)
# ---------------------------------------------------------------------------


def test_grok_flattens_anthropic_style_system_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "fake-xai")
    client = GrokClient()
    blocks = [
        {"type": "text", "text": "VOICE CONSTANTS: ...", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "SURFACE: x"},
    ]
    flat = client._coerce_system_to_text(blocks)
    assert "VOICE CONSTANTS" in flat
    assert "SURFACE: x" in flat
    # Cache control metadata is silently dropped (Grok has no equivalent).


def test_grok_passes_plain_string_system_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "fake-xai")
    client = GrokClient()
    assert client._coerce_system_to_text("plain system prompt") == "plain system prompt"


# ---------------------------------------------------------------------------
# Live Grok smoke test (gated)
# ---------------------------------------------------------------------------


@pytest.mark.llm
@pytest.mark.skipif(
    not os.environ.get("XAI_API_KEY"),
    reason="XAI_API_KEY not set — skipping live Grok smoke test",
)
def test_grok_client_live_smoke() -> None:
    client = GrokClient()
    resp = client.generate(
        system="Reply with exactly: OK",
        user="ping",
        max_tokens=16,
        temperature=0.0,
    )
    assert resp.text.strip()
    assert resp.model == client.model
