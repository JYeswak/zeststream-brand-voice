"""Tests for `zv peel` wizard scaffold.

Covers:
  - pre-flight slug rejection
  - pre-flight overwrite guard (existing voice.yaml without --force)
  - Block 1 + Block 2 collection via CliRunner with piped stdin
  - voice.yaml round-trips yaml.safe_load (session-14 silent-failure guard)
  - state persistence across runs (.peel-state.json)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from zeststream_voice.commands.peel import (
    PeelState,
    cli as peel_cmd,
    load_state,
    preflight,
    save_state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def brands_root(tmp_path: Path) -> Path:
    """Minimal brands/_template/ layout used by preflight fallback logic."""
    root = tmp_path / "skills" / "brand-voice" / "brands"
    template = root / "_template"
    template.mkdir(parents=True)
    # Seed a minimal template voice.yaml — peel will overwrite on final merge.
    (template / "voice.yaml").write_text(
        "brand:\n  slug: TEMPLATE\n  name: TEMPLATE\n",
        encoding="utf-8",
    )
    return root


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------


def test_preflight_rejects_bad_slug(brands_root: Path):
    import click as _click

    for bad in ["X", "ab", "1-starts-with-digit", "Has_Underscore", ""]:
        with pytest.raises(_click.ClickException) as exc:
            preflight(bad, brands_root=brands_root)
        assert "invalid slug" in str(exc.value).lower()


def test_preflight_creates_fresh_from_template(brands_root: Path):
    dirs = preflight("acme-demo", brands_root=brands_root)
    assert dirs.is_fresh
    assert dirs.brand_dir.exists()
    assert (dirs.brand_dir / "voice.yaml").exists()


def test_preflight_rejects_existing_without_force(brands_root: Path):
    import click as _click

    # First run creates it.
    preflight("acme-demo", brands_root=brands_root)
    # Populate the voice.yaml so the guard fires.
    (brands_root / "acme-demo" / "voice.yaml").write_text(
        "brand:\n  slug: acme-demo\n  name: Acme\n", encoding="utf-8"
    )
    # Second run without --force should raise.
    with pytest.raises(_click.ClickException) as exc:
        preflight("acme-demo", brands_root=brands_root)
    msg = str(exc.value).lower()
    assert "already exists" in msg or "--force" in msg


def test_preflight_allows_force_overwrite(brands_root: Path):
    preflight("acme-demo", brands_root=brands_root)
    (brands_root / "acme-demo" / "voice.yaml").write_text(
        "brand: populated\n", encoding="utf-8"
    )
    # With --force, no exception.
    dirs = preflight("acme-demo", brands_root=brands_root, force=True)
    assert dirs.brand_dir.exists()


# ---------------------------------------------------------------------------
# Block 1 + Block 2 via CliRunner
# ---------------------------------------------------------------------------


# Answers chosen to flex every branch of blocks 1+2.
# Order: Q1.1, Q1.2, Q1.3, Q1.4, Q1.5, Q1.7-yn, (no exception details), Q1.8 default,
#        Q2.1, Q2.2, Q2.3 default, Q2.4-yn
PIPED_ANSWERS = "\n".join(
    [
        "Acme Demo",                       # Q1.1 brand name
        "Alex Example",                    # Q1.2 operator name
        "Al, Alex E",                      # Q1.3 banned variants
        "acme-demo.com",                   # Q1.4 domain
        "solo",                            # Q1.5
        "n",                               # Q1.7 no exceptions
        "",                                # Q1.8 default source-of-truth
        "I ship things that prove themselves.",  # Q2.1 canon (6 words)
        "I'm Alex. I ship.",               # Q2.2 variants
        "",                                # Q2.3 default (top-level-routes)
        "n",                               # Q2.4 no split
    ]
)


def test_block1_and_block2_collect_required(brands_root: Path):
    runner = CliRunner()
    result = runner.invoke(
        peel_cmd,
        ["acme-demo", "--brands-root", str(brands_root)],
        input=PIPED_ANSWERS + "\n",
    )
    assert result.exit_code == 0, result.output
    # Stub messages present for blocks 3-9
    for n in (3, 4, 5, 6, 7, 8, 9):
        assert f"[BLOCK {n}" in result.output, f"block {n} stub missing"
    # Checkpoint confirmations
    assert "IDENTITY locked" in result.output
    assert "CANON:" in result.output


def test_yaml_output_is_safe_loadable(brands_root: Path):
    runner = CliRunner()
    result = runner.invoke(
        peel_cmd,
        ["acme-demo", "--brands-root", str(brands_root)],
        input=PIPED_ANSWERS + "\n",
    )
    assert result.exit_code == 0, result.output
    voice_yaml = brands_root / "acme-demo" / "voice.yaml"
    assert voice_yaml.exists()

    # Silent-failure guard: must round-trip.
    parsed = yaml.safe_load(voice_yaml.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    assert parsed["brand"]["slug"] == "acme-demo"
    assert parsed["brand"]["name"] == "Acme Demo"
    assert parsed["brand"]["operator"] == "Alex Example"
    assert parsed["brand"]["operator_variants_banned"] == ["Al", "Alex E"]
    assert parsed["brand"]["domain"] == "acme-demo.com"
    assert parsed["canon"]["primary"] == "I ship things that prove themselves."
    assert parsed["posture"]["voice"] == "first-person singular"
    assert "we" in parsed["posture"]["pronouns_banned"]


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


def test_state_persistence_across_runs(tmp_path: Path):
    brand_dir = tmp_path / "acme-demo"
    brand_dir.mkdir()
    state = PeelState(
        slug="acme-demo",
        started_at="2026-04-21T00:00:00Z",
        blocks_completed=[1, 2],
        current_block=3,
        answers={"1": {"brand": {"slug": "acme-demo"}}},
    )
    save_state(brand_dir, state)

    state_file = brand_dir / ".peel-state.json"
    assert state_file.exists()
    # Atomic write shouldn't leave tmp
    assert not (brand_dir / ".peel-state.json.tmp").exists()

    loaded = load_state(brand_dir)
    assert loaded is not None
    assert loaded.slug == "acme-demo"
    assert loaded.blocks_completed == [1, 2]
    assert loaded.current_block == 3
    assert loaded.answers["1"]["brand"]["slug"] == "acme-demo"


def test_state_file_is_valid_json(tmp_path: Path):
    brand_dir = tmp_path / "acme-demo"
    brand_dir.mkdir()
    state = PeelState(slug="acme-demo", started_at="2026-04-21T00:00:00Z")
    save_state(brand_dir, state)
    raw = (brand_dir / ".peel-state.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["slug"] == "acme-demo"
    assert data["version"] == 1
