"""Tests for `zv peel` Block 4 — RECEIPTS.

Covers:
  - 5 receipts are collected (minimum), persisted to the sidecar
  - capabilities-ground-truth.yaml round-trips yaml.safe_load
  - ``receipts:`` key contains all 5 receipts keyed by Q4.2 label
  - ``private_pricing`` placeholder keys exist (populated later by Block 7)
  - bad Q4.2 key format is re-prompted
  - fuzzy-evidence warning fires but does NOT block acceptance
  - Q4.6 'never' and ISO date both accepted
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from zeststream_voice.commands.peel import cli as peel_cmd


@pytest.fixture
def brands_root(tmp_path: Path) -> Path:
    """Minimal brands/_template/ layout used by preflight fallback logic."""
    root = tmp_path / "skills" / "brand-voice" / "brands"
    template = root / "_template"
    template.mkdir(parents=True)
    (template / "voice.yaml").write_text(
        "brand:\n  slug: TEMPLATE\n  name: TEMPLATE\n", encoding="utf-8"
    )
    return root


_PRELUDE = [
    "Acme Demo",
    "Alex Example",
    "",
    "acme-demo.com",
    "solo",
    "n",
    "",
    "I ship things that prove themselves.",
    "",
    "",
    "n",
    "n",  # Q3.0 — no named methodology (block 3 exits early)
]

_BLOCK_6_SUFFIX = [
    "Acme Demo is a solo consultancy. I ship code.",
    "We ship repeatable automations and CLI tools.",
    "We refuse retainers before a Peel session.",
    "Upsells, mock tests, vibe estimates",
    "Receipts, benchmark logs, named clients",
    "I started in 2012. I rebuilt in 2024. Now this is the third act.",
]


def _five_receipts() -> list[str]:
    inputs: list[str] = []
    categories = ["capability", "number", "client", "tool", "benchmark"]
    for i, cat in enumerate(categories):
        inputs += [
            cat,
            f"receipt_{i}",
            f"We ship claim number {i}.",
            f"https://example.com/evidence/{i}",
            "public",
            "never" if i % 2 == 0 else "2027-01-01",
        ]
    inputs.append("n")
    return inputs


def _run_wizard(brands_root: Path, block_4_inputs: list[str]) -> tuple[int, str, Path]:
    runner = CliRunner()
    piped = "\n".join(_PRELUDE + block_4_inputs + _BLOCK_6_SUFFIX) + "\n"
    result = runner.invoke(
        peel_cmd,
        ["acme-demo", "--brands-root", str(brands_root)],
        input=piped,
        catch_exceptions=False,
    )
    brand_dir = brands_root / "acme-demo"
    return result.exit_code, result.output, brand_dir


def test_block_4_writes_ground_truth_yaml(brands_root: Path):
    code, output, brand_dir = _run_wizard(brands_root, _five_receipts())
    assert code == 0, output

    gt_path = brand_dir / "data" / "capabilities-ground-truth.yaml"
    assert gt_path.exists(), "capabilities-ground-truth.yaml not written"

    parsed = yaml.safe_load(gt_path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    assert parsed["version"] == 1
    assert "last_updated" in parsed
    assert "receipts" in parsed
    assert len(parsed["receipts"]) == 5
    for i in range(5):
        key = f"receipt_{i}"
        assert key in parsed["receipts"]
        r = parsed["receipts"][key]
        assert r["claim"] == f"We ship claim number {i}."
        assert r["evidence"].startswith("https://example.com/evidence/")
        assert r["visibility"] == "public"

    assert parsed["private_pricing"] == {
        "in_pocket_floor": None,
        "retainer_ceiling": None,
    }


def test_block_4_rereplays_bad_key_format(brands_root: Path):
    """Q4.2 must reject keys that do not match ^[a-z][a-z0-9_]*$."""
    inputs: list[str] = []
    inputs += [
        "capability",
        "Bad-Key!",
        "receipt_0",
        "We ship thing 0.",
        "https://example.com/ev/0",
        "public",
        "never",
    ]
    for i in range(1, 5):
        inputs += [
            "number",
            f"receipt_{i}",
            f"We ship thing {i}.",
            f"https://example.com/ev/{i}",
            "public",
            "never",
        ]
    inputs.append("n")

    code, output, brand_dir = _run_wizard(brands_root, inputs)
    assert code == 0, output
    assert "invalid key" in output.lower()

    parsed = yaml.safe_load(
        (brand_dir / "data" / "capabilities-ground-truth.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert len(parsed["receipts"]) == 5
    assert "receipt_0" in parsed["receipts"]
    assert "Bad-Key!" not in parsed["receipts"]


def test_block_4_warns_on_fuzzy_evidence(brands_root: Path):
    """Q4.4 'roughly' should warn but not block."""
    inputs = _five_receipts()
    inputs[3] = "roughly 10 deploys a week"
    code, output, brand_dir = _run_wizard(brands_root, inputs)
    assert code == 0, output
    assert "fuzzy" in output.lower() or "warn" in output.lower()
    parsed = yaml.safe_load(
        (brand_dir / "data" / "capabilities-ground-truth.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert parsed["receipts"]["receipt_0"]["evidence"] == "roughly 10 deploys a week"
