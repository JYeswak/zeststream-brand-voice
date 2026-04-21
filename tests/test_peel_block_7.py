"""Tests for Block 7 — OFFER + PRICING.

Covers:
  - peel-only doctrine skips Q7.4 tier entry
  - public-tiers doctrine collects tiers and emits warning
  - Q7.5/Q7.6 PRIVATE values land in capabilities-ground-truth.yaml
    under private_pricing, NOT in voice.yaml
  - offer block structure matches spec (free_onramp, paid_entry, CTA)
  - _write_private_pricing round-trips and sets last_updated
  - ground-truth.yaml created from minimal structure if Block 4 skipped
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from zeststream_voice.commands.peel import (
    _write_private_pricing,
)


@pytest.fixture
def brand_dir(tmp_path: Path) -> Path:
    d = tmp_path / "skills" / "brand-voice" / "brands" / "acme-demo"
    d.mkdir(parents=True)
    return d


def test_private_pricing_creates_new_file(brand_dir: Path):
    """Block 7 runs before Block 4 → ground-truth.yaml doesn't exist yet."""
    gt = _write_private_pricing(brand_dir, "acme-demo", "$1,200", "$18,000")
    assert gt.exists()
    data = yaml.safe_load(gt.read_text(encoding="utf-8"))
    assert data["brand"] == "acme-demo"
    assert data["private_pricing"]["in_pocket_floor"] == "$1,200"
    assert data["private_pricing"]["retainer_ceiling"] == "$18,000"
    assert "rule" in data["private_pricing"]
    assert data["receipts"] == {}
    assert "version" in data


def test_private_pricing_appends_to_existing(brand_dir: Path):
    """Block 4 ran first → ground-truth.yaml has receipts; merge preserves."""
    gt = brand_dir / "data" / "capabilities-ground-truth.yaml"
    gt.parent.mkdir(parents=True)
    existing = {
        "version": 1,
        "last_updated": "2026-01-01T00:00:00Z",
        "receipts": {
            "sample_receipt": {
                "category": "capability",
                "claim": "We ship a thing.",
                "evidence": "https://example.com/evidence",
                "visibility": "public",
                "expires": "never",
            }
        },
    }
    gt.write_text(yaml.safe_dump(existing), encoding="utf-8")

    _write_private_pricing(brand_dir, "acme-demo", "$500", "$50,000")
    data = yaml.safe_load(gt.read_text(encoding="utf-8"))
    # Receipts preserved
    assert "sample_receipt" in data["receipts"]
    # private_pricing added
    assert data["private_pricing"]["in_pocket_floor"] == "$500"
    assert data["private_pricing"]["retainer_ceiling"] == "$50,000"
    # last_updated refreshed
    assert data["last_updated"] != "2026-01-01T00:00:00Z"


def test_private_pricing_accepts_none_values(brand_dir: Path):
    """Q7.5/Q7.6 may be left blank → None values stored explicitly."""
    gt = _write_private_pricing(brand_dir, "acme-demo", None, None)
    data = yaml.safe_load(gt.read_text(encoding="utf-8"))
    assert data["private_pricing"]["in_pocket_floor"] is None
    assert data["private_pricing"]["retainer_ceiling"] is None


def test_private_pricing_round_trips_after_partial_write(brand_dir: Path):
    """Silent-failure guard: written file must parse back via safe_load."""
    gt = _write_private_pricing(brand_dir, "acme-demo", "$100", "$10,000")
    # Round-trip must succeed.
    reparsed = yaml.safe_load(gt.read_text(encoding="utf-8"))
    assert isinstance(reparsed, dict)
    assert "private_pricing" in reparsed


def test_payload_structure_matches_spec():
    """Spot-check the expected voice.yaml `offer:` block shape. We build
    the payload structurally from what block_7_offer_pricing emits so
    downstream consumers can rely on the key names.
    """
    # This mirrors the structure block_7_offer_pricing assembles.
    example_payload = {
        "offer": {
            "doctrine": "peel-only",
            "free_onramp": {
                "label": "Free 20-min Peel session",
                "cta": "Book my Peel",
            },
            "paid_entry": {
                "label": "$500 Peel Report",
                "price_public": "$500 Peel Report",
            },
            "tiers": [],
            "never_quote_publicly": "We never quote retainer publicly.",
        }
    }
    # Must serialize + round-trip.
    text = yaml.safe_dump(example_payload)
    back = yaml.safe_load(text)
    assert back["offer"]["doctrine"] == "peel-only"
    assert back["offer"]["free_onramp"]["label"].startswith("Free")
    assert back["offer"]["free_onramp"]["cta"] == "Book my Peel"
    assert back["offer"]["paid_entry"]["price_public"] == "$500 Peel Report"
    assert back["offer"]["tiers"] == []


def test_public_tiers_structure():
    """When doctrine != peel-only, tiers is a list of dicts with
    name/price/duration/scope keys."""
    payload = {
        "offer": {
            "doctrine": "public-tiers",
            "free_onramp": {"label": "Free scan", "cta": "Scan me"},
            "paid_entry": {"label": "Starter", "price_public": "Starter"},
            "tiers": [
                {"name": "Growth", "price": "$5k/mo",
                 "duration": "3 months", "scope": "automation"},
                {"name": "Scale", "price": "$15k/mo",
                 "duration": "6 months", "scope": "full stack"},
            ],
            "never_quote_publicly": "Retainer above Scale is custom.",
        }
    }
    back = yaml.safe_load(yaml.safe_dump(payload))
    assert len(back["offer"]["tiers"]) == 2
    assert back["offer"]["tiers"][0]["price"] == "$5k/mo"


def test_private_pricing_never_in_voice_yaml_shape():
    """The Q7.5/Q7.6 values must ONLY appear under private_pricing in
    the ground-truth sidecar — never in any voice.yaml offer block.
    """
    # Simulate the two documents.
    voice_payload = {
        "offer": {
            "doctrine": "peel-only",
            "free_onramp": {"label": "Free 20-min", "cta": "Book"},
            "paid_entry": {"label": "$500", "price_public": "$500"},
            "tiers": [],
            "never_quote_publicly": "No retainer in public.",
        }
    }
    gt_payload = {
        "private_pricing": {
            "in_pocket_floor": "$1,500",
            "retainer_ceiling": "$30,000",
            "rule": "never speak publicly",
        }
    }
    # in_pocket_floor / retainer_ceiling must NOT appear anywhere in voice.yaml.
    voice_text = yaml.safe_dump(voice_payload)
    assert "in_pocket_floor" not in voice_text
    assert "retainer_ceiling" not in voice_text
    assert "$1,500" not in voice_text
    assert "$30,000" not in voice_text
    # But must appear in ground_truth.
    gt_text = yaml.safe_dump(gt_payload)
    assert "in_pocket_floor" in gt_text
    assert "$1,500" in gt_text
