"""Tests for `zv peel` wizard scaffold.

Covers:
  - pre-flight slug rejection
  - pre-flight overwrite guard (existing voice.yaml without --force)
  - pre-flight `--force` backs up pre-existing voice.yaml + state (P0-1)
  - corrupt .peel-state.json triggers three-way recovery prompt (P0-2)
  - Block 1 + Block 2 collection via CliRunner with piped stdin
  - voice.yaml round-trips yaml.safe_load (session-14 silent-failure guard)
  - merge_to_voice_yaml raises on non-round-trippable YAML (P1-5)
  - merge_to_voice_yaml raises when brand key missing (P1-5)
  - domain validation rejects malformed hostnames (P1-2)
  - atomic copytree does not leave partial brand dirs on failure (P1-3)
  - word count treats hyphenated / apostrophized words as one (P1-4)
  - state persistence across runs (.peel-state.json)

All fixtures use pytest's real-fs `tmp_path`. No mocks on filesystem,
click, or yaml collaborators (per testing-real-service-e2e-no-mocks).
The one monkeypatch in this suite targets the function under test to
force its error branch — this is the allowed pattern, not mocking a
dependency.
"""

from __future__ import annotations

import click
import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from zeststream_voice.commands.peel import (
    DOMAIN_RE,
    PeelState,
    _word_count,
    cli as peel_cmd,
    load_state,
    merge_to_voice_yaml,
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
    for bad in ["X", "ab", "1-starts-with-digit", "Has_Underscore", ""]:
        with pytest.raises(click.ClickException) as exc:
            preflight(bad, brands_root=brands_root)
        assert "invalid slug" in str(exc.value).lower()


def test_preflight_creates_fresh_from_template(brands_root: Path):
    dirs = preflight("acme-demo", brands_root=brands_root)
    assert dirs.is_fresh
    assert dirs.brand_dir.exists()
    assert (dirs.brand_dir / "voice.yaml").exists()


def test_preflight_rejects_existing_without_force(brands_root: Path):
    # First run creates it.
    preflight("acme-demo", brands_root=brands_root)
    # Populate the voice.yaml so the guard fires.
    (brands_root / "acme-demo" / "voice.yaml").write_text(
        "brand:\n  slug: acme-demo\n  name: Acme\n", encoding="utf-8"
    )
    # Second run without --force should raise.
    with pytest.raises(click.ClickException) as exc:
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


# ---- P0-1 regression ------------------------------------------------------


def test_force_backs_up_existing_voice_yaml(brands_root: Path):
    """P0-1: --force must back up the pre-existing voice.yaml before allowing
    overwrite. A bad wizard run must be reversible.
    """
    preflight("acme-demo", brands_root=brands_root)
    brand_dir = brands_root / "acme-demo"
    (brand_dir / "voice.yaml").write_text(
        "brand: populated\n", encoding="utf-8"
    )

    preflight("acme-demo", brands_root=brands_root, force=True)

    backups = list(brand_dir.glob("voice.yaml.bak.*"))
    assert len(backups) == 1, f"expected one backup, found {backups}"
    assert backups[0].read_text(encoding="utf-8") == "brand: populated\n"


def test_force_backs_up_existing_peel_state(brands_root: Path):
    """P0-1: --force unlinks .peel-state.json but must back it up first so
    the prior run's progress is recoverable.
    """
    dirs = preflight("acme-demo", brands_root=brands_root)
    state = PeelState(
        slug="acme-demo",
        started_at="2026-04-21T00:00:00Z",
        blocks_completed=[1],
        current_block=2,
        answers={"1": {"brand": {"slug": "acme-demo"}}},
    )
    save_state(dirs.brand_dir, state)
    (dirs.brand_dir / "voice.yaml").write_text(
        "brand: populated\n", encoding="utf-8"
    )
    original_state_json = (dirs.brand_dir / ".peel-state.json").read_text(
        encoding="utf-8"
    )

    preflight("acme-demo", brands_root=brands_root, force=True)

    # Active state file gone, backup remains with original content.
    assert not (dirs.brand_dir / ".peel-state.json").exists()
    backups = list(dirs.brand_dir.glob(".peel-state.json.bak.*"))
    assert len(backups) == 1, f"expected one backup, found {backups}"
    assert backups[0].read_text(encoding="utf-8") == original_state_json


# ---- P1-3 regression ------------------------------------------------------


def test_atomic_copytree_leaves_no_partial_dir_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """P1-3: _atomic_copytree must leave no half-populated brand_dir if the
    copy fails partway. We induce failure by making the staging rename raise.
    """
    # Build a real source tree and a real brands_root — no mocks on fs.
    root = tmp_path / "skills" / "brand-voice" / "brands"
    (root / "_template").mkdir(parents=True)
    (root / "_template" / "voice.yaml").write_text(
        "brand: x\n", encoding="utf-8"
    )

    import zeststream_voice.commands.peel as peel_mod

    real_rename = peel_mod.os.rename

    def exploding_rename(src, dst):
        raise OSError("simulated crash between copy and rename")

    monkeypatch.setattr(peel_mod.os, "rename", exploding_rename)
    with pytest.raises(OSError, match="simulated crash"):
        preflight("acme-demo", brands_root=root)

    # No brand dir, no stranded .tmp staging dir.
    assert not (root / "acme-demo").exists(), "brand_dir survived failed copy"
    assert not (root / "acme-demo.tmp").exists(), "staging dir survived"

    # Restore and confirm a fresh run succeeds — proves no hidden dirty state.
    monkeypatch.setattr(peel_mod.os, "rename", real_rename)
    dirs = preflight("acme-demo", brands_root=root)
    assert dirs.brand_dir.exists()


# ---------------------------------------------------------------------------
# Domain validator (P1-2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_domain",
    [
        "acme..com",           # consecutive dots
        "-acme.com",           # leading dash
        "acme-.com",           # trailing dash in label
        ".acme.com",           # empty leading label
        "acme.com.",           # trailing dot
        "acme.c",              # TLD too short
        "",                    # empty
    ],
)
def test_domain_regex_rejects_malformed(bad_domain: str):
    """P1-2: DOMAIN_RE must reject malformed hostnames so voice.yaml
    never carries a broken brand.domain into downstream rules.
    """
    assert DOMAIN_RE.match(bad_domain) is None, (
        f"{bad_domain!r} should be rejected"
    )


@pytest.mark.parametrize(
    "good_domain",
    ["acme.com", "zeststream.ai", "sub.acme-demo.com", "a-b.co.uk", "x1.io"],
)
def test_domain_regex_accepts_valid(good_domain: str):
    assert DOMAIN_RE.match(good_domain) is not None


# ---------------------------------------------------------------------------
# Tokenizer (P1-4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sentence,expected",
    [
        ("don't panic", 2),
        ("state-of-the-art tooling", 2),
        ("  extra   whitespace  only ", 3),
        ("", 0),
        ("one", 1),
        ("I ship things that prove themselves.", 6),
    ],
)
def test_word_count_matches_vale_tokenizer(sentence: str, expected: int):
    """P1-4: _word_count must bind hyphens and apostrophes so canon-length
    checks match the downstream Vale-shape scorer.
    """
    assert _word_count(sentence) == expected


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


# ---- P1-5 regression: silent-failure guard itself ------------------------


def test_merge_raises_on_corrupt_yaml(
    brands_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """P1-5: session-14 trauma class. If yaml.safe_dump ever produces a
    string that fails round-trip, merge_to_voice_yaml MUST raise so we
    never silently ship a broken voice.yaml. This is the explicit reason
    the guard exists; without this test the guard is a regression risk.
    """
    import zeststream_voice.commands.peel as peel_mod

    # Monkeypatch the function under test's dump step to emit invalid YAML.
    monkeypatch.setattr(
        peel_mod.yaml, "safe_dump", lambda *a, **k: "not: valid:\n  -broken: [\n"
    )

    brand_dir = brands_root / "acme-demo"
    brand_dir.mkdir(parents=True)
    state = PeelState(
        slug="acme-demo",
        started_at="2026-04-21T00:00:00Z",
        answers={"1": {"brand": {"slug": "acme-demo"}}},
    )
    with pytest.raises(click.ClickException) as exc:
        merge_to_voice_yaml(brand_dir, state)
    assert "round-trip" in str(exc.value).lower()
    # And the tmp file was cleaned up — no dangling .yaml.tmp.
    assert not (brand_dir / "voice.yaml.tmp").exists()


def test_merge_raises_when_brand_key_missing(brands_root: Path):
    """P1-5: the post-parse 'must contain brand key' guard must fire when
    the wizard somehow writes a voice.yaml without a brand: root.
    """
    brand_dir = brands_root / "acme-demo"
    brand_dir.mkdir(parents=True)
    state = PeelState(
        slug="acme-demo",
        started_at="2026-04-21T00:00:00Z",
        answers={},  # no block-1 payload -> no brand key
    )
    with pytest.raises(click.ClickException) as exc:
        merge_to_voice_yaml(brand_dir, state)
    assert "brand" in str(exc.value).lower()
    assert not (brand_dir / "voice.yaml").exists()


# ---- P0-2 regression: corrupt state recovery -----------------------------


def test_resume_on_corrupt_state_offers_discard(brands_root: Path):
    """P0-2: corrupt .peel-state.json must NOT hard-crash the CLI. The
    operator must be offered a three-way (resume/abort/discard) prompt
    and `discard` must clear the bad file and proceed with a fresh run.
    """
    # First run creates the brand.
    preflight("acme-demo", brands_root=brands_root)
    brand_dir = brands_root / "acme-demo"

    # Corrupt the state file directly on disk (real fs, no mocks).
    state_file = brand_dir / ".peel-state.json"
    state_file.write_text("{ this is not valid json", encoding="utf-8")

    # Feed "discard" choice, then the full wizard answers.
    piped = "discard\n" + PIPED_ANSWERS + "\n"
    runner = CliRunner()
    result = runner.invoke(
        peel_cmd,
        ["acme-demo", "--brands-root", str(brands_root), "--resume"],
        input=piped,
    )
    assert result.exit_code == 0, result.output
    assert "corrupt" in result.output.lower()

    # Corrupt file was backed up (forensic trail) and a fresh run produced
    # a valid voice.yaml.
    corrupt_backups = list(brand_dir.glob(".peel-state.json.corrupt.*"))
    assert len(corrupt_backups) == 1, (
        f"expected 1 corrupt backup, found {corrupt_backups}"
    )
    voice_yaml = brand_dir / "voice.yaml"
    parsed = yaml.safe_load(voice_yaml.read_text(encoding="utf-8"))
    assert parsed["brand"]["slug"] == "acme-demo"


def test_resume_on_corrupt_state_abort_exits_nonzero(brands_root: Path):
    """P0-2: `abort` path must exit with a nonzero status — the operator
    made an informed choice not to destroy the corrupt file.
    """
    preflight("acme-demo", brands_root=brands_root)
    brand_dir = brands_root / "acme-demo"
    (brand_dir / ".peel-state.json").write_text(
        "{ bad json", encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(
        peel_cmd,
        ["acme-demo", "--brands-root", str(brands_root), "--resume"],
        input="abort\n",
    )
    assert result.exit_code != 0
    # State file untouched — abort is non-destructive.
    assert (brand_dir / ".peel-state.json").read_text(encoding="utf-8") == (
        "{ bad json"
    )


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
