"""Tests for `zv peel` Block 6 — WE_ARE / WE_ARE_NOT.

Covers:
  - WE_ARE.md and WE_ARE_NOT.md both written to brands/<slug>/
  - brand.name from Block 1 appears in both headers
  - Q6.2 containing a banned verb (help/enable/etc) is auto-rejected and
    the operator is re-prompted
  - Q6.4 and Q6.5 enforce exactly 3 items
  - WE_ARE.md structure has 'What we do', 'How we prove it', 'Origin'
  - WE_ARE_NOT.md structure has 'What we refuse to do'
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from zeststream_voice.commands.peel import cli as peel_cmd


@pytest.fixture
def brands_root(tmp_path: Path) -> Path:
    root = tmp_path / "skills" / "brand-voice" / "brands"
    template = root / "_template"
    template.mkdir(parents=True)
    (template / "voice.yaml").write_text(
        "brand:\n  slug: TEMPLATE\n  name: TEMPLATE\n", encoding="utf-8"
    )
    return root


# Block 1+2 prelude.
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
    "n",  # Q3.0 — skip Block 3 methodology
]

# Five receipts so Block 4 completes.
def _block_4_inputs() -> list[str]:
    inputs: list[str] = []
    for i in range(5):
        inputs += [
            "capability",
            f"receipt_{i}",
            f"Claim {i}.",
            f"https://example.com/{i}",
            "public",
            "never",
        ]
    inputs.append("n")
    return inputs


def _run(brands_root: Path, block_6_inputs: list[str]) -> tuple[int, str, Path]:
    runner = CliRunner()
    piped = "\n".join(_PRELUDE + _block_4_inputs() + block_6_inputs) + "\n"
    result = runner.invoke(
        peel_cmd,
        [
            "acme-demo",
            "--brands-root", str(brands_root),
            "--only-blocks", "1,2,3,4,6",
        ],
        input=piped,
        catch_exceptions=False,
    )
    return result.exit_code, result.output, brands_root / "acme-demo"


_GOOD_BLOCK_6 = [
    "Acme Demo is a solo consultancy. I ship code.",
    "We ship repeatable automations and CLI tools.",
    "We refuse retainers before a Peel session.",
    "Upsells, mock tests, vibe estimates",
    "Receipts, benchmark logs, named clients",
    "I started in 2012. I rebuilt in 2024. Now this is the third act.",
]


def test_block_6_writes_we_are_docs(brands_root: Path):
    code, output, brand_dir = _run(brands_root, _GOOD_BLOCK_6)
    assert code == 0, output

    we_are = brand_dir / "WE_ARE.md"
    we_are_not = brand_dir / "WE_ARE_NOT.md"
    assert we_are.exists(), "WE_ARE.md not written"
    assert we_are_not.exists(), "WE_ARE_NOT.md not written"

    we_are_body = we_are.read_text(encoding="utf-8")
    we_are_not_body = we_are_not.read_text(encoding="utf-8")

    # Brand name from Block 1 flows through.
    assert "Acme Demo" in we_are_body
    assert "Acme Demo" in we_are_not_body

    # Structural headers from template.
    assert "## What we do" in we_are_body
    assert "## How we prove it" in we_are_body
    assert "## Origin" in we_are_body
    assert "## What we refuse to do" in we_are_not_body

    # Q6.5 items rendered as bullets.
    assert "- Receipts" in we_are_body
    # Q6.4 items rendered as bullets.
    assert "- Upsells" in we_are_not_body


def test_block_6_rejects_banned_verb_in_q6_2(brands_root: Path):
    """Q6.2 must auto-reject 'help'/'enable'/'empower' etc and re-prompt."""
    inputs = [
        "Acme Demo is a solo consultancy. I ship code.",
        # First Q6.2 — contains 'help' → auto-reject.
        "We help clients ship automations faster.",
        # Second Q6.2 — clean.
        "We ship repeatable automations and CLI tools.",
        "We refuse retainers before a Peel session.",
        "Upsells, mock tests, vibe estimates",
        "Receipts, benchmark logs, named clients",
        "I started in 2012. I rebuilt in 2024. Now this is the third act.",
    ]
    code, output, brand_dir = _run(brands_root, inputs)
    assert code == 0, output
    # The rejection notice fires.
    assert "auto-reject" in output.lower() or "banned verb" in output.lower()

    # The accepted Q6.2 lands in the file; the rejected one does not.
    we_are = (brand_dir / "WE_ARE.md").read_text(encoding="utf-8")
    assert "help clients ship" not in we_are.lower()
    assert "ship repeatable automations" in we_are.lower()


def test_block_6_enforces_exactly_three_items(brands_root: Path):
    """Q6.4 must reject 2-item list, accept 3-item list on second try."""
    inputs = [
        "Acme Demo is a solo consultancy. I ship code.",
        "We ship repeatable automations and CLI tools.",
        "We refuse retainers before a Peel session.",
        # First Q6.4 — only 2 items → rejected.
        "Upsells, mock tests",
        # Second Q6.4 — 3 items → accepted.
        "Upsells, mock tests, vibe estimates",
        "Receipts, benchmark logs, named clients",
        "I started in 2012. I rebuilt in 2024. Now this is the third act.",
    ]
    code, output, brand_dir = _run(brands_root, inputs)
    assert code == 0, output
    assert "need exactly 3" in output.lower()

    we_are_not = (brand_dir / "WE_ARE_NOT.md").read_text(encoding="utf-8")
    assert "- vibe estimates" in we_are_not
