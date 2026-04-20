"""Brand loader tests — voice.yaml discovery + ground-truth resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from zeststream_voice._brands import discover_brand, load_ground_truth, load_voice_yaml


def test_discover_by_explicit_path(zeststream_brand: Path):
    paths = discover_brand(
        slug="zeststream", explicit_brand_path=zeststream_brand
    )
    assert paths.voice_yaml.exists()
    assert paths.voice_yaml.name == "voice.yaml"
    assert paths.ground_truth_yaml is not None
    assert paths.ground_truth_yaml.exists()


def test_load_voice_yaml(zeststream_brand: Path):
    paths = discover_brand(
        slug="zeststream", explicit_brand_path=zeststream_brand
    )
    voice = load_voice_yaml(paths)
    assert voice["brand"]["slug"] == "zeststream"
    assert "banned_words" in voice


def test_load_ground_truth(zeststream_brand: Path):
    paths = discover_brand(
        slug="zeststream", explicit_brand_path=zeststream_brand
    )
    gt = load_ground_truth(paths)
    assert "entries" in gt
    assert any(
        e.get("id") == "n8n_workflow_count_2026_04_19" for e in gt["entries"]
    )


def test_missing_brand_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        discover_brand(slug="nonexistent", search_from=tmp_path)


def test_search_from_walks_up(zeststream_brand: Path):
    # Search from a deep subdirectory inside the repo — should still find it.
    repo_root = zeststream_brand.parent.parent.parent.parent
    start = repo_root / "tests"
    assert start.exists()
    paths = discover_brand(slug="zeststream", search_from=start)
    assert paths.voice_yaml.exists()
