"""Tests for Block 3 — METHOD (optional).

Covers:
  - Q3.0 = n skip path: `method:` key OMITTED from voice.yaml (not null).
  - Q3.0 = y with 3 phases: method.phases captured; phase_not_gate=True.
  - Q3.8 Yuzu IP guard: 'Yuzu' triggers re-prompt, second try accepted.
  - Q3.3 range validation: rejects <2 and >5.
  - phase slug collision: two "Discovery" phases get disambiguated keys.
  - merge_to_voice_yaml omits `method` key entirely when block 3 skipped.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from zeststream_voice.commands.peel import (
    PeelState,
    _slugify_phase,
    cli as peel_cmd,
    merge_to_voice_yaml,
)


@pytest.fixture
def brands_root(tmp_path: Path) -> Path:
    root = tmp_path / "skills" / "brand-voice" / "brands"
    (root / "_template").mkdir(parents=True)
    (root / "_template" / "voice.yaml").write_text(
        "brand:\n  slug: TEMPLATE\n  name: TEMPLATE\n", encoding="utf-8"
    )
    return root


# Blocks 1+2 piped answers (reuses the same shape as test_peel.py).
_BLOCKS_1_2 = [
    "Acme Demo",
    "Alex Example",
    "Al, Alex E",
    "acme-demo.com",
    "solo",
    "n",
    "",
    "I ship things that prove themselves.",
    "I'm Alex. I ship.",
    "",
    "n",
]


# Block 4 RECEIPTS — minimum 5 entries, each 6 prompts + final "n" to stop.
_BLOCK_4: list[str] = []
for i in range(5):
    _BLOCK_4 += [
        "capability",
        f"receipt_{i}",
        f"We ship thing {i}.",
        f"https://example.com/evidence/{i}",
        "public",
        "never",
    ]
_BLOCK_4.append("n")  # Q4.7 after 5th receipt


# Block 6 WE_ARE — Q6.1..Q6.6.
_BLOCK_6 = [
    "Acme Demo is a one-person consultancy. We build automations.",  # Q6.1
    "We ship repeatable CLI tools and deliver deploy scripts.",       # Q6.2
    "We refuse to sell retainers before a Peel session.",             # Q6.3
    "Retainer upsells, mock tests, vibe-only deliverables",           # Q6.4
    "GitHub receipts, benchmark logs, client permission slips",       # Q6.5
    "I started shipping code in 2012. I burned out in 2020. "
    "I rebuilt my stack in 2024. Now this.",                          # Q6.6
]


def _run_with_block3(brands_root: Path, block3_inputs: list[str]):
    """Pipe blocks 1+2 → block 3 → block 4 → block 6 to drive the CLI
    all the way through. Block 4+6 are owned by another worker; we just
    feed them valid answers so the run completes and voice.yaml is written.
    """
    piped = "\n".join(_BLOCKS_1_2 + block3_inputs + _BLOCK_4 + _BLOCK_6) + "\n"
    runner = CliRunner()
    return runner.invoke(
        peel_cmd,
        [
            "acme-demo",
            "--brands-root", str(brands_root),
            "--only-blocks", "1,2,3,4,6",
        ],
        input=piped,
    )


def test_block3_skip_omits_method_key(brands_root: Path):
    """Q3.0 = n → `method:` must NOT appear in voice.yaml (not as null either)."""
    result = _run_with_block3(brands_root, ["n"])  # Q3.0 = n
    assert result.exit_code == 0, result.output
    voice = yaml.safe_load(
        (brands_root / "acme-demo" / "voice.yaml").read_text(encoding="utf-8")
    )
    assert "method" not in voice, (
        f"method key leaked into voice.yaml when operator declined: {voice.get('method')}"
    )
    assert "will be omitted" in result.output.lower()


def test_block3_three_phases_captured(brands_root: Path):
    """Q3.0 = y with 3 phases writes method.phases with 3 entries + flags."""
    block3 = [
        "y",                          # Q3.0
        "Discover Design Deliver™",   # Q3.1
        "Discover. Design. Deliver.", # Q3.2
        "3",                          # Q3.3
        # phase 1
        "Discover", "Week 1", "Discovery",
        "The questions we didn't know we had got asked.",
        # phase 2
        "Design", "Weeks 2-4", "Build",
        "The design held up to scrutiny.",
        # phase 3
        "Deliver", "Weeks 5-6", "Launch",
        "It shipped and it kept shipping.",
        "",                           # Q3.8 blank
    ]
    result = _run_with_block3(brands_root, block3)
    assert result.exit_code == 0, result.output
    voice = yaml.safe_load(
        (brands_root / "acme-demo" / "voice.yaml").read_text(encoding="utf-8")
    )
    assert "method" in voice
    method = voice["method"]
    assert method["name_registered"] == "Discover Design Deliver™"
    assert method["name_full"] == "Discover. Design. Deliver."
    assert method["phase_not_gate"] is True
    assert len(method["phases"]) == 3
    assert "discover" in method["phases"]
    assert "design" in method["phases"]
    assert "deliver" in method["phases"]
    assert method["phases"]["discover"]["duration"] == "Week 1"
    assert method["phases"]["discover"]["role"] == "Discovery"
    assert method["phases"]["deliver"]["milestone_quote"] == (
        "It shipped and it kept shipping."
    )
    # Q3.8 was blank → conflicts_or_extends key should not be present.
    assert "conflicts_or_extends" not in method


def test_block3_rejects_yuzu_reference(brands_root: Path):
    """Q3.8 containing 'Yuzu' triggers a re-prompt; second try accepted."""
    block3 = [
        "y",
        "Acme Method",
        "Acme Acme Acme.",
        "2",
        "Plan", "Week 1", "Discovery", "We know what to build.",
        "Build", "Weeks 2-4", "Build", "We built what we planned.",
        "Extends the Yuzu Method",   # rejected
        "Extends our prior framework",  # accepted
    ]
    result = _run_with_block3(brands_root, block3)
    assert result.exit_code == 0, result.output
    assert "rejected" in result.output.lower()
    assert "yuzu" in result.output.lower()  # rejection message mentions why
    voice = yaml.safe_load(
        (brands_root / "acme-demo" / "voice.yaml").read_text(encoding="utf-8")
    )
    assert voice["method"]["conflicts_or_extends"] == "Extends our prior framework"
    # Yuzu token must not leak into stored value.
    assert "yuzu" not in voice["method"]["conflicts_or_extends"].lower()


def test_block3_rejects_out_of_range_phase_count(brands_root: Path):
    """Q3.3 must reject 1 and 6, accept retry in [2,5]."""
    block3 = [
        "y",
        "Acme Method",
        "A. B.",
        "1",   # too few
        "6",   # too many
        "abc", # non-int
        "2",   # valid
        "Plan", "Week 1", "Discovery", "Done.",
        "Do",  "Week 2", "Build",     "Shipped.",
        "",
    ]
    result = _run_with_block3(brands_root, block3)
    assert result.exit_code == 0, result.output
    assert "between 2 and 5" in result.output or "integer 2-5" in result.output
    voice = yaml.safe_load(
        (brands_root / "acme-demo" / "voice.yaml").read_text(encoding="utf-8")
    )
    assert len(voice["method"]["phases"]) == 2


def test_block3_phase_slug_collision_disambiguates(brands_root: Path):
    """Two phases named 'Discovery' get distinct slugs."""
    block3 = [
        "y",
        "Acme Method",
        "A. B.",
        "2",
        "Discovery", "Week 1", "Discovery", "Round 1 done.",
        "Discovery", "Week 2", "Discovery", "Round 2 done.",
        "",
    ]
    result = _run_with_block3(brands_root, block3)
    assert result.exit_code == 0, result.output
    voice = yaml.safe_load(
        (brands_root / "acme-demo" / "voice.yaml").read_text(encoding="utf-8")
    )
    keys = list(voice["method"]["phases"].keys())
    assert len(keys) == 2
    assert "discovery" in keys
    # Second "Discovery" should get a numeric suffix.
    assert any(k.startswith("discovery_") for k in keys)


def test_merge_omits_method_when_block3_not_in_answers(brands_root: Path):
    """Unit test on merge: empty/absent block 3 answers → no `method:` key."""
    brand_dir = brands_root / "acme-demo"
    brand_dir.mkdir(parents=True)
    state = PeelState(
        slug="acme-demo",
        started_at="2026-04-21T00:00:00Z",
        answers={
            "1": {
                "brand": {"slug": "acme-demo", "name": "Acme"},
                "posture": {"voice": "first-person singular"},
            },
            # no "3" entry — simulates skipped block
        },
    )
    voice_yaml = merge_to_voice_yaml(brand_dir, state)
    parsed = yaml.safe_load(voice_yaml.read_text(encoding="utf-8"))
    assert "method" not in parsed


def test_merge_emits_method_when_block3_present(brands_root: Path):
    """Unit test on merge: block 3 payload → method key populated."""
    brand_dir = brands_root / "acme-demo"
    brand_dir.mkdir(parents=True)
    state = PeelState(
        slug="acme-demo",
        started_at="2026-04-21T00:00:00Z",
        answers={
            "1": {
                "brand": {"slug": "acme-demo", "name": "Acme"},
                "posture": {"voice": "first-person singular"},
            },
            "3": {
                "method": {
                    "name_full": "Plan. Do. Ship.",
                    "name_registered": "Plan Do Ship™",
                    "phases": {
                        "plan": {"duration": "Week 1", "role": "Discovery",
                                 "milestone_quote": "Known."},
                    },
                    "phase_not_gate": True,
                }
            },
        },
    )
    voice_yaml = merge_to_voice_yaml(brand_dir, state)
    parsed = yaml.safe_load(voice_yaml.read_text(encoding="utf-8"))
    assert parsed["method"]["phase_not_gate"] is True
    assert "plan" in parsed["method"]["phases"]


def test_slugify_phase_handles_punctuation_and_case():
    """Unit test on helper — covers common operator-input shapes."""
    assert _slugify_phase("Discovery") == "discovery"
    assert _slugify_phase("Weeks 2-4") == "weeks_2_4"
    assert _slugify_phase("Plan & Do") == "plan_do"
    assert _slugify_phase("   ") == "phase"  # empty-after-strip fallback
    assert _slugify_phase("!!!") == "phase"
