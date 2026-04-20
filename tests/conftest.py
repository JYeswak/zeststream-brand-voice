"""Shared pytest fixtures for zeststream-voice."""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
ZESTSTREAM_BRAND_DIR = (
    REPO_ROOT / "skills" / "brand-voice" / "brands" / "zeststream"
)


@pytest.fixture(scope="session")
def zeststream_brand() -> Path:
    """Absolute path to the zeststream brand directory (containing voice.yaml)."""
    assert ZESTSTREAM_BRAND_DIR.exists(), (
        f"fixture path missing: {ZESTSTREAM_BRAND_DIR}"
    )
    return ZESTSTREAM_BRAND_DIR
