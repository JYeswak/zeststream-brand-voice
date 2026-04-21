"""Tests for zv reply + qa_matcher.

LLM-driven paths stay gated behind @pytest.mark.llm + ANTHROPIC/XAI keys.
Structural tests cover the deterministic matcher + click command wiring.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from zeststream_voice.commands.reply import cli as reply_cli
from zeststream_voice.llm.qa_matcher import (
    QAMatch,
    load_qa_matrix,
    match_qa,
)


# ---------------------------------------------------------------------------
# qa_matcher
# ---------------------------------------------------------------------------


def test_load_qa_matrix_real(zeststream_brand: Path) -> None:
    matrix = load_qa_matrix(zeststream_brand)
    assert matrix is not None
    assert matrix.get("brand") == "zeststream"
    qas = matrix.get("qa", [])
    assert len(qas) >= 20  # 21 canonical answers seeded


def test_load_qa_matrix_absent_returns_none(tmp_path: Path) -> None:
    assert load_qa_matrix(tmp_path) is None


def test_match_qa_exact_variant_hits_pricing(zeststream_brand: Path) -> None:
    matrix = load_qa_matrix(zeststream_brand)
    hit = match_qa("What are your prices?", matrix)
    assert hit is not None
    assert isinstance(hit, QAMatch)
    assert hit.qa_id.startswith("t1_")
    assert hit.confidence >= 0.9
    # Pricing canonical must forbid hourly/per-hour style language.
    banned = set(hit.banned_in_this_answer or [])
    assert any(b.lower() in {"hourly", "per hour", "/hr"} for b in banned)


def test_match_qa_paraphrase_below_threshold_returns_none(zeststream_brand: Path) -> None:
    matrix = load_qa_matrix(zeststream_brand)
    # Nonsense sentence — no entry should clear 0.7.
    assert match_qa("Unrelated noise about quantum llamas", matrix) is None


def test_match_qa_empty_inputs() -> None:
    assert match_qa("", {"qa": []}) is None
    assert match_qa("hello", {}) is None


def test_match_qa_threshold_configurable(zeststream_brand: Path) -> None:
    matrix = load_qa_matrix(zeststream_brand)
    # "What do you do" matches verbatim → always passes.
    hit_strict = match_qa("What do you do?", matrix, threshold=0.95)
    assert hit_strict is not None

    # A paraphrase that shares only stopwords/generic nouns should not hit
    # the default threshold, but can be surfaced with a very low one.
    loose_query = "asking about something unrelated to your business today"
    none_at_default = match_qa(loose_query, matrix)
    assert none_at_default is None
    exposed = match_qa(loose_query, matrix, threshold=0.01)
    # Weaker thresholds either surface a low-confidence match or still return
    # None — both are acceptable; we just want the threshold to actually gate.
    if exposed is not None:
        assert exposed.confidence < 0.95


# ---------------------------------------------------------------------------
# CLI: reply --help and empty-file guard
# ---------------------------------------------------------------------------


def test_reply_help_renders() -> None:
    runner = CliRunner()
    result = runner.invoke(reply_cli, ["--help"])
    assert result.exit_code == 0
    assert "reply" in result.output.lower()
    assert "--model" in result.output
    assert "--qa-threshold" in result.output


def test_reply_empty_file_fails_cleanly(tmp_path: Path, zeststream_brand: Path) -> None:
    runner = CliRunner()
    empty = tmp_path / "empty.eml"
    empty.write_text("")
    result = runner.invoke(
        reply_cli,
        [str(empty), "--brand-path", str(zeststream_brand)],
    )
    assert result.exit_code != 0
    assert "empty" in result.output.lower()


# ---------------------------------------------------------------------------
# Live smoke (gated on API key)
# ---------------------------------------------------------------------------


@pytest.mark.llm
@pytest.mark.skipif(
    not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("XAI_API_KEY")),
    reason="Neither ANTHROPIC_API_KEY nor XAI_API_KEY set — skipping live reply smoke",
)
def test_reply_canonical_route_smoke(tmp_path: Path, zeststream_brand: Path) -> None:
    runner = CliRunner()
    email = tmp_path / "inbound.eml"
    email.write_text(
        "Hey Joshua — quick one: what are your prices? Trying to budget for "
        "a small automation project. Thanks."
    )
    result = runner.invoke(
        reply_cli,
        [
            str(email),
            "--brand-path",
            str(zeststream_brand),
            "--json",
            "--max-attempts",
            "1",
        ],
    )
    # Non-zero exit is OK if the voice gate failed; we just want a parseable result.
    assert result.output.strip()
    import json as _json
    payload = _json.loads(result.output)
    assert payload.get("route") in {"canonical", "playbook"}
    assert "draft" in payload
    assert "DRAFT" in payload.get("reminder", "")
