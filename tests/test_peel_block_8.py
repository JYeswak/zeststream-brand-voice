"""Tests for `zv peel` block 8 — SITUATION PLAYBOOKS (Wave G2b).

Covers:
  - 5 playbooks land in voice.yaml under situation_playbooks.playbooks
  - inline_score dict is populated per playbook with integer counts
  - Q8.6 banned-word scanner actually runs: off_brand containing a banned word
    reports exactly 1 on_brand_bans=0 / off_brand_bans=1
  - mandatory_on_chat_surfaces is True

Fixtures use real tmp_path filesystem (testing-real-service-e2e-no-mocks).
State is prepopulated with blocks 1+2 completed plus a block-5 banned_words
list so the inline scanner has something to hit. Block 5 itself is owned by
a different worker — we stub its answer payload here so block 8 can read it.
"""

from __future__ import annotations

import yaml
from pathlib import Path

import pytest
from click.testing import CliRunner

from zeststream_voice.commands.peel import (
    PeelState,
    cli as peel_cmd,
    save_state,
)


# ---------------------------------------------------------------------------
# Fixture — brand skeleton with blocks 1+2+5 prepopulated
# ---------------------------------------------------------------------------


@pytest.fixture
def prepared_brand(tmp_path: Path) -> tuple[Path, Path]:
    """Create brands/_template/ layout and prepopulate state with blocks 1+2+5.

    Returns (brands_root, brand_dir).
    """
    root = tmp_path / "skills" / "brand-voice" / "brands"
    template = root / "_template"
    template.mkdir(parents=True)
    (template / "voice.yaml").write_text(
        "brand:\n  slug: TEMPLATE\n  name: TEMPLATE\n",
        encoding="utf-8",
    )

    slug = "acme-b8"
    brand_dir = root / slug
    # Copy from template so preflight sees an existing populated dir.
    brand_dir.mkdir(parents=True)
    (brand_dir / "voice.yaml").write_text(
        "brand:\n  slug: TEMPLATE\n  name: TEMPLATE\n",
        encoding="utf-8",
    )

    # Prepopulate state: blocks 1 and 2 complete + block 5 seeded with
    # a banned list that includes 'leverage' so we can assert scanner fires.
    state = PeelState(
        version=1,
        slug=slug,
        started_at="2026-04-21T00:00:00Z",
        blocks_completed=[1, 2, 3, 4, 5, 6, 7],
        current_block=8,
        answers={
            "1": {
                "brand": {
                    "slug": slug,
                    "name": "Acme B8",
                    "operator": "Alex Example",
                    "operator_variants_banned": [],
                    "domain": "acme-b8.test",
                    "source_of_truth": f"brands/{slug}/SOURCE_OF_TRUTH.md",
                    "ground_truth": f"brands/{slug}/data/capabilities-ground-truth.yaml",
                },
                "posture": {
                    "voice": "first-person singular",
                    "pronouns_allowed": ["I"],
                    "pronouns_banned": ["we"],
                    "permitted_exceptions": [],
                    "attribution_rule": "",
                },
            },
            "2": {"canon": {"primary": "I ship with receipts.", "variants_approved": [], "rule": "", "allow_split": False}},
            "5": {"banned_words": ["leverage", "platform", "streamline"], "banned_phrases": []},
        },
    )
    save_state(brand_dir, state)
    return root, brand_dir


# ---------------------------------------------------------------------------
# Input helpers — drive cli() which skips completed blocks, so we only
# need to supply answers for blocks 8 and 9.
# ---------------------------------------------------------------------------


def _block_8_inputs_clean() -> list[str]:
    """5 playbooks, none with banned words in either side."""
    out: list[str] = []
    for i in range(5):
        out += [
            f"Situation {i}",
            f"trig {i}a, trig {i}b",
            f"I only ship with receipts ({i}).",
            f"Lazy copy number {i}.",
            f"Receipts beat vibes ({i}).",
            "y" if i < 4 else "n",
        ]
    return out


def _block_8_inputs_with_ban() -> list[str]:
    """5 playbooks where playbook #1 off_brand contains the banned word 'leverage'."""
    out: list[str] = []
    for i in range(5):
        if i == 0:
            on = "I ship with receipts."
            off = "We can leverage synergies here."
        else:
            on = f"I only ship with receipts ({i})."
            off = f"Lazy copy number {i}."
        out += [
            f"Situation {i}",
            f"trig {i}",
            on,
            off,
            f"Receipts beat vibes ({i}).",
            "y" if i < 4 else "n",
        ]
    return out


# Minimal block-9 inputs (3 clean 95+ exemplars, no trauma) so cli() completes.
_BLOCK_9_TAIL = []
for i in range(3):
    _BLOCK_9_TAIL += [
        f"This is exemplar number {i}. Specific receipts with names and dates here.",
        "body",
        "95+",
    ]
_BLOCK_9_TAIL.append("n")  # Q9.5 no trauma


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_block8_five_playbooks_land_in_voice_yaml(prepared_brand: tuple[Path, Path]):
    root, brand_dir = prepared_brand
    runner = CliRunner()

    piped = "\n".join(_block_8_inputs_clean() + _BLOCK_9_TAIL) + "\n"
    result = runner.invoke(
        peel_cmd,
        ["acme-b8", "--brands-root", str(root), "--resume"],
        input=piped,
    )
    assert result.exit_code == 0, result.output

    voice = yaml.safe_load((brand_dir / "voice.yaml").read_text(encoding="utf-8"))
    assert "situation_playbooks" in voice
    sp = voice["situation_playbooks"]
    assert sp["mandatory_on_chat_surfaces"] is True
    assert len(sp["playbooks"]) == 5
    for p in sp["playbooks"]:
        assert isinstance(p["inline_score"]["on_brand_bans"], int)
        assert isinstance(p["inline_score"]["off_brand_bans"], int)
        assert set(p.keys()) >= {"id", "triggers", "on_brand", "off_brand", "rule", "inline_score"}


def test_block8_inline_scanner_fires_on_off_brand_banned_word(
    prepared_brand: tuple[Path, Path],
):
    """Q8.6 banned-word scan: off_brand containing 'leverage' yields 1 hit."""
    root, brand_dir = prepared_brand
    runner = CliRunner()

    piped = "\n".join(_block_8_inputs_with_ban() + _BLOCK_9_TAIL) + "\n"
    result = runner.invoke(
        peel_cmd,
        ["acme-b8", "--brands-root", str(root), "--resume"],
        input=piped,
    )
    assert result.exit_code == 0, result.output

    voice = yaml.safe_load((brand_dir / "voice.yaml").read_text(encoding="utf-8"))
    first = voice["situation_playbooks"]["playbooks"][0]
    assert first["inline_score"]["on_brand_bans"] == 0
    assert first["inline_score"]["off_brand_bans"] == 1, (
        f"expected 1 ban for 'leverage', got {first['inline_score']['off_brand_bans']}"
    )

    # Other playbooks clean on both sides.
    for p in voice["situation_playbooks"]["playbooks"][1:]:
        assert p["inline_score"]["on_brand_bans"] == 0
        assert p["inline_score"]["off_brand_bans"] == 0
