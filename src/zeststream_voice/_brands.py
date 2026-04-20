"""Brand discovery and loading.

A "brand" is a slug with a directory laid out as:

    skills/brand-voice/brands/<slug>/voice.yaml
    skills/brand-voice/data/capabilities-ground-truth.yaml

We auto-discover by walking up from CWD looking for
``skills/brand-voice/brands/<slug>/voice.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class BrandPaths:
    """Resolved file locations for a brand."""

    slug: str
    brand_dir: Path
    voice_yaml: Path
    ground_truth_yaml: Optional[Path]


def _walk_up(start: Path) -> list[Path]:
    paths = [start.resolve()]
    paths.extend(start.resolve().parents)
    return paths


def discover_brand(
    slug: str = "zeststream",
    search_from: Optional[Path] = None,
    explicit_brand_path: Optional[Path] = None,
) -> BrandPaths:
    """Resolve a brand slug (or explicit dir) to its config paths.

    Resolution order:
      1. ``explicit_brand_path`` — a directory containing ``voice.yaml``
      2. ``search_from`` (default: cwd) walked upward; first hit on
         ``skills/brand-voice/brands/<slug>/voice.yaml`` wins.

    Raises:
        FileNotFoundError: no voice.yaml could be located.
    """
    if explicit_brand_path is not None:
        brand_dir = Path(explicit_brand_path).resolve()
        voice = brand_dir / "voice.yaml"
        if not voice.exists():
            raise FileNotFoundError(
                f"no voice.yaml at {voice} — check --brand-path argument"
            )
        gt = _resolve_ground_truth(brand_dir, voice)
        return BrandPaths(
            slug=slug, brand_dir=brand_dir, voice_yaml=voice, ground_truth_yaml=gt
        )

    start = (search_from or Path.cwd()).resolve()
    for parent in _walk_up(start):
        candidate = parent / "skills" / "brand-voice" / "brands" / slug / "voice.yaml"
        if candidate.exists():
            brand_dir = candidate.parent
            gt = _resolve_ground_truth(brand_dir, candidate)
            return BrandPaths(
                slug=slug,
                brand_dir=brand_dir,
                voice_yaml=candidate,
                ground_truth_yaml=gt,
            )

    raise FileNotFoundError(
        f"could not find skills/brand-voice/brands/{slug}/voice.yaml "
        f"walking up from {start}"
    )


def _resolve_ground_truth(brand_dir: Path, voice_yaml: Path) -> Optional[Path]:
    """Find capabilities-ground-truth.yaml.

    Checks, in order:
      1. The ``ground_truth`` key in voice.yaml (absolute path)
      2. ``<brand-root>/data/capabilities-ground-truth.yaml``
      3. ``<brand-root>/../../data/capabilities-ground-truth.yaml`` (repo-relative)
    """
    try:
        with voice_yaml.open("r", encoding="utf-8") as f:
            voice = yaml.safe_load(f) or {}
    except Exception:
        voice = {}

    declared = (voice.get("brand") or {}).get("ground_truth")
    if declared:
        p = Path(declared).expanduser()
        if p.exists():
            return p

    # skills/brand-voice/brands/<slug>/voice.yaml → skills/brand-voice/data/...
    brand_voice_root = brand_dir.parent.parent
    candidate = brand_voice_root / "data" / "capabilities-ground-truth.yaml"
    if candidate.exists():
        return candidate

    return None


def load_voice_yaml(paths: BrandPaths) -> dict:
    with paths.voice_yaml.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_ground_truth(paths: BrandPaths) -> dict:
    if paths.ground_truth_yaml is None:
        return {"entries": []}
    with paths.ground_truth_yaml.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"entries": []}
