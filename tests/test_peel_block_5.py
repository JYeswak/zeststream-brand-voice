"""Tests for Block 5 — BANS.

Covers:
  - slop auto-extraction from the Q5.1 paste intersects DEFAULT_SLOP
  - Q5.5 empty → no attribution_rules key in payload
  - Q5.5 populated → attribution_rules entries carry trigger_regex and id
  - banned_words ≥ accepted slop + Q5.3 custom
  - banned_phrases = Q5.4 phrases ∪ Q5.7 never-appear
  - _extract_slop_candidates uses tokenizer (not substring) for single-word slop
  - _extract_slop_candidates catches hyphenated slop via substring
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from zeststream_voice.commands.peel import (
    DEFAULT_SLOP,
    _extract_slop_candidates,
    cli as peel_cmd,
)


@pytest.fixture
def brands_root(tmp_path: Path) -> Path:
    root = tmp_path / "skills" / "brand-voice" / "brands"
    (root / "_template").mkdir(parents=True)
    (root / "_template" / "voice.yaml").write_text(
        "brand:\n  slug: TEMPLATE\n  name: TEMPLATE\n", encoding="utf-8"
    )
    return root


# ---------------------------------------------------------------------------
# Helper coverage
# ---------------------------------------------------------------------------


def test_extract_slop_single_word_uses_tokenizer():
    """'leveraging' should NOT match 'leverage' — tokenizer-based counts."""
    paste = "We leverage platforms to transform enterprise."
    got = _extract_slop_candidates(paste)
    assert "leverage" in got
    assert "platform" not in got, "plural 'platforms' != 'platform'"
    # "platforms" is the plural form — not in DEFAULT_SLOP's singular entry.
    paste_plural = "We leverage platforms."
    assert "platform" not in _extract_slop_candidates(paste_plural)


def test_extract_slop_counts_multiple_occurrences():
    paste = "leverage leverage transform transform transform."
    got = _extract_slop_candidates(paste)
    assert got["leverage"] == 2
    assert "transformation" not in got, "'transform' != 'transformation'"
    assert got.get("transform") is None, "'transform' is not in DEFAULT_SLOP"


def test_extract_slop_hyphenated_substring():
    """cutting-edge is hyphenated — matches via substring on lowered paste."""
    paste = "Our cutting-edge solution is best-in-class."
    got = _extract_slop_candidates(paste)
    assert got.get("cutting-edge") == 1
    assert got.get("best-in-class") == 1
    assert got.get("solution") == 1


def test_extract_slop_case_insensitive():
    paste = "LEVERAGE Platform ENTERPRISE."
    got = _extract_slop_candidates(paste)
    assert "leverage" in got
    assert "platform" in got
    assert "enterprise" in got


# ---------------------------------------------------------------------------
# Full CLI flow
# ---------------------------------------------------------------------------


_BLOCKS_1_2 = [
    "Acme Demo", "Alex Example", "Al, Alex E", "acme-demo.com",
    "solo", "n", "",
    "I ship things that prove themselves.",
    "I'm Alex. I ship.",
    "", "n",
]

_BLOCK_3_SKIP = ["n"]  # Q3.0 = n

_BLOCK_4: list[str] = []
for i in range(5):
    _BLOCK_4 += [
        "capability", f"receipt_{i}",
        f"We ship thing {i}.",
        f"https://example.com/evidence/{i}",
        "public", "never",
    ]
_BLOCK_4.append("n")

_BLOCK_6 = [
    "Acme Demo is a one-person consultancy. We build automations.",
    "We ship repeatable CLI tools and deliver deploy scripts.",
    "We refuse to sell retainers before a Peel session.",
    "Retainer upsells, mock tests, vibe-only deliverables",
    "GitHub receipts, benchmark logs, client permission slips",
    "I started shipping code in 2012. I burned out in 2020. "
    "I rebuilt my stack in 2024. Now this.",
]


def _piped_block_5(block5_lines: list[str]) -> str:
    """Build piped stdin: blocks 1+2, block 3 skip, block 4 mins, BLOCK 5,
    block 6 answers. Block 5 paste uses blank-line-terminated multiline."""
    return "\n".join(_BLOCKS_1_2 + _BLOCK_3_SKIP + _BLOCK_4 + block5_lines + _BLOCK_6) + "\n"


def _run_cli(brands_root: Path, block5_lines: list[str]):
    runner = CliRunner()
    return runner.invoke(
        peel_cmd,
        ["acme-demo", "--brands-root", str(brands_root)],
        input=_piped_block_5(block5_lines),
    )


def test_block5_slop_extraction_autoban_all(brands_root: Path):
    """Q5.1 paste with known slop + Q5.2 'all' → banned_words includes those."""
    # Paste mentions leverage, platform (singular), transform as distinct tokens.
    block5 = [
        "We leverage platforms to transform enterprise workflows.",  # Q5.1 L1
        "Our innovative solution is best-in-class.",                  # Q5.1 L2
        "We streamline your paradigm.",                               # Q5.1 L3
        "",           # blank line ends Q5.1
        "all",        # Q5.2 accept all candidates
        "",           # Q5.3 no custom words
        "",           # Q5.4 no custom phrases
        "",           # Q5.5 no attributions
        "",           # Q5.7 no never-appear
    ]
    result = _run_cli(brands_root, block5)
    assert result.exit_code == 0, result.output
    voice = yaml.safe_load(
        (brands_root / "acme-demo" / "voice.yaml").read_text(encoding="utf-8")
    )
    # These singular words appear in the paste and in DEFAULT_SLOP.
    assert "leverage" in voice["banned_words"]
    assert "enterprise" in voice["banned_words"]
    assert "innovative" in voice["banned_words"]
    assert "solution" in voice["banned_words"]
    assert "streamline" in voice["banned_words"]
    assert "paradigm" in voice["banned_words"]
    # Hyphenated slop present too.
    assert "best-in-class" in voice["banned_words"]
    # No attribution_rules key when Q5.5 is empty.
    assert "attribution_rules" not in voice or voice.get("attribution_rules") == []


def test_block5_empty_attribution_omits_key(brands_root: Path):
    """Q5.5 blank → payload has no attribution_rules key at all."""
    from zeststream_voice.commands.peel import PeelState
    # Not going through CLI — just inspect the state after a minimal run.
    block5 = [
        "Generic marketing copy one.",
        "Generic marketing copy two.",
        "Generic marketing copy three.",
        "",
        "none",  # Q5.2 none
        "",      # Q5.3
        "",      # Q5.4
        "",      # Q5.5 no attributions
        "",      # Q5.7
    ]
    result = _run_cli(brands_root, block5)
    assert result.exit_code == 0, result.output

    # The answers["5"] payload should not have attribution_rules key.
    import json
    state = json.loads(
        (brands_root / "acme-demo" / ".peel-state.json").read_text(
            encoding="utf-8"
        )
    )
    b5 = state["answers"]["5"]
    assert "attribution_rules" not in b5
    assert b5["banned_words"] == []


def test_block5_attribution_rules_populated(brands_root: Path):
    """Q5.5 with 'tool — author' → attribution_rules entry with regex."""
    block5 = [
        "Nauseating copy line one.",
        "Nauseating copy line two.",
        "Nauseating copy line three.",
        "",
        "none",               # Q5.2 none
        "",                   # Q5.3 no custom
        "",                   # Q5.4 no phrases
        "claude — anthropic, grok — xai",  # Q5.5 two attributions
        "",                   # Q5.6 for claude — accept default regex
        "",                   # Q5.6 for grok   — accept default regex
        "",                   # Q5.7
    ]
    result = _run_cli(brands_root, block5)
    assert result.exit_code == 0, result.output

    voice = yaml.safe_load(
        (brands_root / "acme-demo" / "voice.yaml").read_text(encoding="utf-8")
    )
    rules = voice["attribution_rules"]
    assert len(rules) == 2
    ids = {r["id"] for r in rules}
    assert "claude" in ids and "grok" in ids
    # Each rule must carry a valid compiled regex in trigger_regex.
    for rule in rules:
        assert "trigger_regex" in rule and rule["trigger_regex"]
        re.compile(rule["trigger_regex"])  # must not raise
        assert rule["action"] == "auto_reject"


def test_block5_banned_words_includes_custom(brands_root: Path):
    """Q5.3 custom single-word bans land in banned_words alongside slop."""
    block5 = [
        "We leverage the platform.",
        "Our enterprise solution.",
        "Innovative paradigm.",
        "",
        "all",          # Q5.2
        "frobnicate, widgetize",  # Q5.3 custom
        "",             # Q5.4
        "",             # Q5.5
        "",             # Q5.7
    ]
    result = _run_cli(brands_root, block5)
    assert result.exit_code == 0, result.output
    voice = yaml.safe_load(
        (brands_root / "acme-demo" / "voice.yaml").read_text(encoding="utf-8")
    )
    assert "frobnicate" in voice["banned_words"]
    assert "widgetize" in voice["banned_words"]
    # Slop still present.
    assert "leverage" in voice["banned_words"]


def test_block5_never_appear_lands_in_banned_phrases(brands_root: Path):
    """Q5.7 trademarked/NDA phrases merge into banned_phrases."""
    block5 = [
        "Competitor Inc ships a thing.",
        "Another line about nothing.",
        "Third line to satisfy min.",
        "",
        "none",
        "",
        "not just X but Y, in today's world",   # Q5.4
        "",
        "SecretClientCorp, DeprecatedProductName",  # Q5.7
    ]
    result = _run_cli(brands_root, block5)
    assert result.exit_code == 0, result.output
    voice = yaml.safe_load(
        (brands_root / "acme-demo" / "voice.yaml").read_text(encoding="utf-8")
    )
    assert "not just X but Y" in voice["banned_phrases"]
    assert "in today's world" in voice["banned_phrases"]
    assert "SecretClientCorp" in voice["banned_phrases"]
    assert "DeprecatedProductName" in voice["banned_phrases"]
