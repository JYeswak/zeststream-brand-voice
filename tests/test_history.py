"""Tests for zv history/tag/revert/diff.

No git mutation is performed — these tests work on an isolated tmp brand
fixture. The real seed tags under ``skills/brand-voice/brands/zeststream/
.voice-history/`` are also smoke-tested for parseability.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from zeststream_voice.commands.history import (
    VoiceTag,
    _list_tags,
    diff_cli,
    history_cli,
    revert_cli,
    tag_cli,
)


# ---------------------------------------------------------------------------
# Seed-tag smoke (real repo)
# ---------------------------------------------------------------------------


def test_seed_tags_exist_and_parse(zeststream_brand: Path) -> None:
    tags = _list_tags(zeststream_brand)
    names = {t.tag for t in tags}
    assert "v1.0-initial-peel" in names
    assert "v1.1-pricing-doctrine" in names
    assert "v2.0-canon-buy-time-back" in names

    for t in tags:
        assert t.git_sha, f"tag {t.tag} missing git_sha"
        assert t.date, f"tag {t.tag} missing date"
        assert t.summary, f"tag {t.tag} missing summary"


def test_history_cli_lists_real_seed_tags(zeststream_brand: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(history_cli, ["--brand-path", str(zeststream_brand)])
    assert result.exit_code == 0
    assert "v1.0-initial-peel" in result.output
    assert "v2.0-canon-buy-time-back" in result.output


def test_history_cli_json(zeststream_brand: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        history_cli,
        ["--brand-path", str(zeststream_brand), "--json"],
    )
    assert result.exit_code == 0
    import json as _json
    payload = _json.loads(result.output)
    assert "tags" in payload
    assert len(payload["tags"]) >= 3


# ---------------------------------------------------------------------------
# Isolated sandbox tests (tag/revert/diff)
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_brand(tmp_path: Path, zeststream_brand: Path) -> Path:
    """Copy voice.yaml into a throwaway directory so tag writes don't leak."""
    dst = tmp_path / "brand"
    dst.mkdir()
    # Only need voice.yaml for the history commands to work.
    shutil.copy2(zeststream_brand / "voice.yaml", dst / "voice.yaml")
    # Initialize an isolated git repo so tag/diff helpers have a SHA to talk to.
    subprocess.run(["git", "init", "-q"], cwd=dst, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=dst, check=True
    )
    subprocess.run(["git", "config", "user.name", "test"], cwd=dst, check=True)
    subprocess.run(["git", "add", "voice.yaml"], cwd=dst, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=dst, check=True
    )
    return dst


def test_tag_cli_writes_yaml(isolated_brand: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        tag_cli,
        [
            "test-tag",
            "--brand-path",
            str(isolated_brand),
            "--summary",
            "unit-test snapshot",
        ],
    )
    assert result.exit_code == 0, result.output
    tag_path = isolated_brand / ".voice-history" / "test-tag.tag"
    assert tag_path.exists()
    data = yaml.safe_load(tag_path.read_text())
    assert data["tag"] == "test-tag"
    assert data["git_sha"]
    assert "unit-test snapshot" in data["summary"]


def test_tag_cli_rejects_duplicate(isolated_brand: Path) -> None:
    runner = CliRunner()
    args = [
        "dup",
        "--brand-path",
        str(isolated_brand),
        "--summary",
        "first",
    ]
    assert runner.invoke(tag_cli, args).exit_code == 0
    second = runner.invoke(tag_cli, args)
    assert second.exit_code != 0
    assert "already exists" in second.output.lower()


def test_diff_cli_identical_when_no_change(isolated_brand: Path) -> None:
    runner = CliRunner()
    runner.invoke(
        tag_cli,
        [
            "snap-a",
            "--brand-path",
            str(isolated_brand),
            "--summary",
            "snap a",
        ],
    )
    result = runner.invoke(
        diff_cli,
        ["snap-a", "--brand-path", str(isolated_brand)],
    )
    assert result.exit_code == 0
    assert "identical" in result.output.lower()


def test_diff_cli_reports_changes(isolated_brand: Path) -> None:
    runner = CliRunner()
    # Snap the starting point.
    runner.invoke(
        tag_cli,
        [
            "snap-before",
            "--brand-path",
            str(isolated_brand),
            "--summary",
            "before",
        ],
    )
    # Mutate voice.yaml without tagging — current should now differ.
    voice = isolated_brand / "voice.yaml"
    voice.write_text(voice.read_text(encoding="utf-8") + "\n# sentinel comment\n")
    result = runner.invoke(
        diff_cli,
        ["snap-before", "--brand-path", str(isolated_brand)],
    )
    assert result.exit_code == 0
    assert "sentinel comment" in result.output


def test_revert_cli_dry_run_does_not_mutate(isolated_brand: Path) -> None:
    runner = CliRunner()
    runner.invoke(
        tag_cli,
        [
            "snap-pre",
            "--brand-path",
            str(isolated_brand),
            "--summary",
            "pre-mutation",
        ],
    )
    voice = isolated_brand / "voice.yaml"
    original = voice.read_text(encoding="utf-8")
    voice.write_text(original + "\n# drifted\n")

    dry = runner.invoke(
        revert_cli,
        ["snap-pre", "--brand-path", str(isolated_brand)],
    )
    assert dry.exit_code == 0
    assert "DRY RUN" in dry.output
    # File should still be the mutated version.
    assert voice.read_text(encoding="utf-8").endswith("# drifted\n")


def test_revert_cli_confirm_restores_and_writes_snapshot(isolated_brand: Path) -> None:
    runner = CliRunner()
    runner.invoke(
        tag_cli,
        [
            "snap-good",
            "--brand-path",
            str(isolated_brand),
            "--summary",
            "good",
        ],
    )
    voice = isolated_brand / "voice.yaml"
    original = voice.read_text(encoding="utf-8")
    voice.write_text(original + "\n# drift\n")

    result = runner.invoke(
        revert_cli,
        [
            "snap-good",
            "--brand-path",
            str(isolated_brand),
            "--confirm",
            "--new-tag",
            "snap-good-reverted",
        ],
    )
    assert result.exit_code == 0, result.output
    assert voice.read_text(encoding="utf-8") == original
    assert (
        isolated_brand / ".voice-history" / "snap-good-reverted.tag"
    ).exists()


# ---------------------------------------------------------------------------
# VoiceTag dataclass
# ---------------------------------------------------------------------------


def test_voicetag_to_dict_roundtrip(isolated_brand: Path) -> None:
    runner = CliRunner()
    runner.invoke(
        tag_cli,
        [
            "roundtrip",
            "--brand-path",
            str(isolated_brand),
            "--summary",
            "dataclass check",
        ],
    )
    tag_file = isolated_brand / ".voice-history" / "roundtrip.tag"
    tag = VoiceTag.load(tag_file)
    d = tag.to_dict()
    assert d["tag"] == "roundtrip"
    assert d["git_sha"]
    assert "dataclass check" in d["summary"]
