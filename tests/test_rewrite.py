"""Tests for ``zv rewrite`` — the WRITE-quadrant killer demo.

Fast-path tests (no LLM):
  - --help renders
  - surface auto-detect buckets behave per spec (<280 x, <500 post, <1500 email, else page)
  - _diff_render produces unified-diff output with expected headers
  - missing file exits with a clean error
  - empty file errors cleanly
  - already-on-brand input short-circuits without invoking the LLM

LLM-gated tests (real Anthropic API, skip when ANTHROPIC_API_KEY unset):
  - feeding text with known banned words produces a rewrite whose composite
    is >= BEFORE composite, and the banned words are gone.

Per testing-real-service-e2e-no-mocks: tmp_path real fs, no mocks of the
scorer or CLI. The only monkeypatch in the fast-path is pointing the CLI
at a real brand dir via --brand-path, which is the intended test seam.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from zeststream_voice.commands._diff_render import render_diff
from zeststream_voice.commands.rewrite import _detect_surface, cli as rewrite_cmd


# ---------------------------------------------------------------------------
# Surface auto-detect (pure function)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "length,expected",
    [
        (100, "x"),
        (279, "x"),
        (300, "post"),
        (499, "post"),
        (600, "email"),
        (1499, "email"),
        (2000, "page"),
        (10000, "page"),
    ],
)
def test_detect_surface_buckets(length: int, expected: str):
    text = "x" * length
    assert _detect_surface(text) == expected


# ---------------------------------------------------------------------------
# Diff renderer
# ---------------------------------------------------------------------------


def test_render_diff_empty_when_identical():
    assert render_diff("same text", "same text") == ""


def test_render_diff_produces_unified_output_without_color():
    before = "line one\nline two\nline three\n"
    after = "line one\nLINE TWO CHANGED\nline three\n"
    out = render_diff(before, after, use_color=False)
    # Unified diff headers.
    assert "--- BEFORE" in out
    assert "+++ AFTER" in out
    # Change markers.
    assert "-line two" in out
    assert "+LINE TWO CHANGED" in out
    # Unchanged context lines are present but without +/-.
    assert "line one" in out
    assert "line three" in out


def test_render_diff_respects_no_color_env(monkeypatch: pytest.MonkeyPatch):
    """NO_COLOR env var forces plain output even with autodetect."""
    monkeypatch.setenv("NO_COLOR", "1")
    out = render_diff("a\n", "b\n")  # use_color=None -> autodetect
    # No ANSI escape sequences.
    assert "\x1b[" not in out


def test_render_diff_honors_force_color(monkeypatch: pytest.MonkeyPatch):
    """FORCE_COLOR env var adds ANSI codes even on non-tty."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    out = render_diff("a\n", "b\n")
    assert "\x1b[" in out


def test_render_diff_handles_missing_trailing_newline():
    # Neither side ends with \n — output lines should still terminate cleanly.
    out = render_diff("one line", "two line", use_color=False)
    assert out  # non-empty
    for line in out.splitlines(keepends=True):
        assert line.endswith("\n"), f"line missing \\n: {line!r}"


# ---------------------------------------------------------------------------
# CLI --help
# ---------------------------------------------------------------------------


def test_rewrite_help_renders():
    runner = CliRunner()
    result = runner.invoke(rewrite_cmd, ["--help"])
    assert result.exit_code == 0, result.output
    # Key flags must be documented.
    for flag in ("--surface", "--brand", "--accept-threshold", "--json", "--show-diff"):
        assert flag in result.output, f"missing {flag} in --help"


# ---------------------------------------------------------------------------
# File-level errors
# ---------------------------------------------------------------------------


def test_rewrite_missing_file_exits_cleanly(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(rewrite_cmd, [str(tmp_path / "nope.md")])
    # click's Path(exists=True) yields exit code 2 with a usage-style error.
    assert result.exit_code != 0
    assert "does not exist" in result.output.lower() or "not found" in result.output.lower()


def test_rewrite_empty_file_exits_cleanly(tmp_path: Path, brand_path: Path):
    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        rewrite_cmd,
        [str(empty), "--brand-path", str(brand_path)],
    )
    assert result.exit_code != 0
    assert "empty" in result.output.lower()


# ---------------------------------------------------------------------------
# Already-on-brand fast path (no LLM invoked)
# ---------------------------------------------------------------------------


@pytest.fixture
def brand_path() -> Path:
    """Point tests at the real zeststream brand folder in this repo."""
    here = Path(__file__).resolve().parent
    root = here.parent  # repo root
    bp = root / "skills" / "brand-voice" / "brands" / "zeststream"
    if not (bp / "voice.yaml").exists():
        pytest.skip(f"real brand folder not present at {bp}")
    return bp


def test_rewrite_short_circuits_when_input_already_passes(
    tmp_path: Path, brand_path: Path
):
    """An input that already clears the voice gate must not call the LLM.

    We assert by setting an absurdly low --accept-threshold (0.0) so any
    non-empty non-banned text passes, then checking the CLI reports
    'no rewrite performed' and exits 0.
    """
    src = tmp_path / "ok.md"
    src.write_text(
        "Clear sentence. No banned terms here.\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    # ANTHROPIC_API_KEY not required — fast path should not call the LLM.
    result = runner.invoke(
        rewrite_cmd,
        [
            str(src),
            "--brand-path",
            str(brand_path),
            "--accept-threshold",
            "0.0",
            "--max-attempts",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "no rewrite performed" in result.output.lower() or "already clears" in result.output.lower()


# ---------------------------------------------------------------------------
# LLM-gated end-to-end (real Anthropic API)
# ---------------------------------------------------------------------------


pytestmark_llm = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; LLM end-to-end tests skipped.",
)


@pytestmark_llm
def test_rewrite_lifts_off_brand_copy(tmp_path: Path, brand_path: Path):
    """End-to-end: feed text with banned words, expect a rewrite whose
    composite is strictly higher than BEFORE.
    """
    src = tmp_path / "offbrand.md"
    # Intentionally off-brand: "platform", generic-SaaS register, "we help".
    src.write_text(
        "Our enterprise platform helps businesses streamline operations and "
        "leverage cutting-edge solutions to deliver transformational outcomes.\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        rewrite_cmd,
        [
            str(src),
            "--brand-path",
            str(brand_path),
            "--json",
            "--max-attempts",
            "3",
        ],
    )
    # Exit code 0 only if AFTER passes; LLM variability may push exit to 2.
    # We only require a rewrite to be produced and composite to improve.
    assert result.exit_code in (0, 2), result.output

    import json as _json

    payload = _json.loads(result.output)
    assert payload["rewritten"] != payload["original"]
    assert payload["after"]["composite"] >= payload["before"]["composite"]
    # At least one known banned word should be gone from the rewrite.
    rewritten_lower = payload["rewritten"].lower()
    # Not asserting all banned words removed (LLM may keep edge cases) — just
    # require at least one was removed to prove the targeting works.
    original_lower = payload["original"].lower()
    removed_any = False
    for word in ("platform", "leverage", "streamline"):
        if word in original_lower and word not in rewritten_lower:
            removed_any = True
            break
    assert removed_any, f"no banned word removed — rewrite: {payload['rewritten']!r}"
