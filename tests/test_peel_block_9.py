"""Tests for `zv peel` block 9 — EXEMPLARS SEED (Wave G2b).

Covers:
  - 3 exemplars with mixed scores write files under voice_examples_by_context/
  - <95 exemplar lands in aspiring/<surface>-near-miss-NN.md (not the surface
    folder), preserving near-miss archaeology for diff training
  - trauma.jsonl always exists after block 9 closes (empty file is legal —
    session-14 downstream-reader FileNotFound guard)
  - 95+ exemplar containing a banned word triggers the spec line-509 refusal
    (ClickException surfaces as non-zero exit code)

Fixtures use real tmp_path filesystem. State is prepopulated with blocks
1+2+5 so the scanner has a banned list to hit. Block 5 is a sibling worker's;
we stub its answers here.
"""

from __future__ import annotations

import json
import yaml
from pathlib import Path

import pytest
from click.testing import CliRunner

from zeststream_voice.commands.peel import (
    PeelState,
    cli as peel_cmd,
    save_state,
)


@pytest.fixture
def prepared_brand(tmp_path: Path) -> tuple[Path, Path]:
    """Brand skeleton + state with blocks 1..7 completed and block 5 seeded.

    Seeding block 5 with ['leverage', 'platform', 'streamline'] lets the
    inline scanner fire; block 8 is also marked complete with a stub payload
    so cli() jumps straight to block 9.
    """
    root = tmp_path / "skills" / "brand-voice" / "brands"
    template = root / "_template"
    template.mkdir(parents=True)
    (template / "voice.yaml").write_text(
        "brand:\n  slug: TEMPLATE\n  name: TEMPLATE\n",
        encoding="utf-8",
    )

    slug = "acme-b9"
    brand_dir = root / slug
    brand_dir.mkdir(parents=True)
    (brand_dir / "voice.yaml").write_text(
        "brand:\n  slug: TEMPLATE\n  name: TEMPLATE\n",
        encoding="utf-8",
    )

    state = PeelState(
        version=1,
        slug=slug,
        started_at="2026-04-21T00:00:00Z",
        blocks_completed=[1, 2, 3, 4, 5, 6, 7, 8],
        current_block=9,
        answers={
            "1": {
                "brand": {
                    "slug": slug,
                    "name": "Acme B9",
                    "operator": "Alex Example",
                    "operator_variants_banned": [],
                    "domain": "acme-b9.test",
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
            "8": {
                "situation_playbooks": {
                    "playbooks": [],
                    "mandatory_on_chat_surfaces": True,
                }
            },
        },
    )
    save_state(brand_dir, state)
    return root, brand_dir


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------


def _mixed_exemplars_inputs() -> list[str]:
    """2× 95+ + 1× <90 (triggers aspiring/) + Q9.5 n (no trauma)."""
    out = [
        # Exemplar 1 — 95+, body
        "This is exemplar one. Receipts: client names, dates, SHA refs.",
        "body",
        "95+",
        # Exemplar 2 — <90, hero (goes to aspiring/)
        "Weaker draft: generic verbs, no receipts, no specific clients.",
        "hero",
        "<90",
        "Missing receipts — generic framing.",  # Q9.4 weakness
        # Exemplar 3 — 95+, email
        "Third exemplar: specific CLI tool names and benchmark numbers.",
        "email",
        "95+",
        "n",  # Q9.5 no trauma
    ]
    return out


def _banned_word_exemplar_inputs() -> list[str]:
    """Exemplar 1 marked 95+ but contains 'leverage' → spec line 509 refusal."""
    return [
        # 40+ chars with a banned word; marked 95+ to trigger the refusal.
        "We can leverage the platform to ship faster with clear receipts.",
        "body",
        "95+",
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_block9_mixed_scores_write_files_and_aspiring(
    prepared_brand: tuple[Path, Path],
):
    root, brand_dir = prepared_brand
    runner = CliRunner()

    piped = "\n".join(_mixed_exemplars_inputs()) + "\n"
    result = runner.invoke(
        peel_cmd,
        ["acme-b9", "--brands-root", str(root), "--resume"],
        input=piped,
    )
    assert result.exit_code == 0, result.output

    examples = brand_dir / "voice_examples_by_context"
    assert examples.exists()

    # Two 95+ exemplars land in their surface folders.
    assert (examples / "body" / "exemplar-01.md").exists()
    assert (examples / "email" / "exemplar-01.md").exists()
    # <90 hero lands in aspiring/ as near-miss.
    assert (examples / "aspiring" / "hero-near-miss-01.md").exists()

    # Frontmatter is valid YAML and carries score + surface + source.
    body01 = (examples / "body" / "exemplar-01.md").read_text(encoding="utf-8")
    assert body01.startswith("---\n")
    _, front, _ = body01.split("---\n", 2)
    meta = yaml.safe_load(front)
    assert meta["surface"] == "body"
    assert meta["score"] == 96
    assert meta["source"] == "peel-block-9"
    assert meta["weakness"] is None

    near = (examples / "aspiring" / "hero-near-miss-01.md").read_text(encoding="utf-8")
    near_meta = yaml.safe_load(near.split("---\n")[1])
    assert near_meta["score"] == 88
    assert near_meta["weakness"] == "Missing receipts — generic framing."


def test_block9_trauma_jsonl_exists_even_when_empty(
    prepared_brand: tuple[Path, Path],
):
    """Session-14 guard: trauma.jsonl must always exist, even with 0 entries."""
    root, brand_dir = prepared_brand
    runner = CliRunner()

    piped = "\n".join(_mixed_exemplars_inputs()) + "\n"
    result = runner.invoke(
        peel_cmd,
        ["acme-b9", "--brands-root", str(root), "--resume"],
        input=piped,
    )
    assert result.exit_code == 0, result.output

    trauma = brand_dir / "trauma.jsonl"
    assert trauma.exists(), "trauma.jsonl must exist even with 0 entries"
    contents = trauma.read_text(encoding="utf-8")
    # Empty file is legal JSONL.
    lines = [ln for ln in contents.splitlines() if ln.strip()]
    assert lines == []
    # And every non-empty line that COULD be there must parse — verify parser
    # contract (no malformed concatenation).
    for ln in lines:
        json.loads(ln)


def test_block9_refuses_banned_word_in_95_plus_exemplar(
    prepared_brand: tuple[Path, Path],
):
    """Spec line 509: 95+ exemplar firing bans from own list aborts the block."""
    root, brand_dir = prepared_brand
    runner = CliRunner()

    piped = "\n".join(_banned_word_exemplar_inputs()) + "\n"
    result = runner.invoke(
        peel_cmd,
        ["acme-b9", "--brands-root", str(root), "--resume"],
        input=piped,
    )
    # ClickException → exit code 1 (click default for usage errors is 2;
    # our raise uses ClickException which exits 1).
    assert result.exit_code != 0
    assert "ban" in result.output.lower()
    assert "cannot proceed" in result.output.lower()
