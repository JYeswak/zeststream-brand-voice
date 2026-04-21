"""Tests for ``zv draft`` (write-quadrant MVP).

Follows the real-service-e2e-no-mocks discipline from the peel test
suite: real filesystem, real click, real YAML. The LLM itself is gated
behind ``@pytest.mark.llm`` so CI can run the non-LLM portion without
an API key.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from zeststream_voice.cli import cli as root_cli
from zeststream_voice.commands._surface_templates import (
    ALL_SURFACES,
    STUB_SURFACES,
    WIRED_SURFACES,
    build_user_prompt,
)
from zeststream_voice.commands.draft import _preflight


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def brand_dir(tmp_path: Path) -> Path:
    """Minimal brand folder with a parseable voice.yaml."""
    bdir = tmp_path / "skills" / "brand-voice" / "brands" / "acme-test"
    bdir.mkdir(parents=True)
    (bdir / "voice.yaml").write_text(
        "brand:\n"
        "  slug: acme-test\n"
        "  name: Acme\n"
        "  operator: Alex Example\n"
        "  operator_variants_banned: []\n"
        "  domain: acme.test\n"
        "posture:\n"
        "  voice: first-person singular\n"
        "  pronouns_allowed: [I, me, my, you, your]\n"
        "  pronouns_banned: []\n"
        "canon:\n"
        "  primary: 'I ship working systems.'\n"
        "  variants_approved: []\n"
        "  rule: 'Appears verbatim per top-level-routes.'\n",
        encoding="utf-8",
    )
    return bdir


# ---------------------------------------------------------------------------
# Surface template tests (pure, no network)
# ---------------------------------------------------------------------------


def test_wired_surfaces_are_the_expected_three():
    assert set(WIRED_SURFACES) == {"x", "linkedin", "page"}


def test_stub_surfaces_list_is_exhaustive():
    assert set(STUB_SURFACES) == {"facebook", "instagram", "email", "meta", "blog"}


def test_all_surfaces_union():
    assert set(ALL_SURFACES) == set(WIRED_SURFACES) | set(STUB_SURFACES)


@pytest.mark.parametrize("surface", WIRED_SURFACES)
def test_build_user_prompt_wired_returns_nonempty(surface: str):
    prompt = build_user_prompt(surface, "the 910x cache hit fix")
    assert "the 910x cache hit fix" in prompt
    assert len(prompt) > 100  # has structural rules body


def test_x_template_mentions_receipt_requirement():
    prompt = build_user_prompt("x", "shipping a thing")
    assert "receipt" in prompt.lower()
    assert "280" in prompt  # char cap surfaced


def test_linkedin_template_specifies_word_range():
    prompt = build_user_prompt("linkedin", "shipping a thing")
    assert "150-200 word" in prompt or "150-200 words" in prompt


def test_page_template_requires_canon_verbatim():
    prompt = build_user_prompt("page", "landing page for pricing")
    assert "canon" in prompt.lower()
    assert "verbatim" in prompt.lower()


@pytest.mark.parametrize("surface", STUB_SURFACES)
def test_stub_surfaces_raise_not_implemented(surface: str):
    with pytest.raises(NotImplementedError) as exc:
        build_user_prompt(surface, "any topic")
    # Message must name the surface and point at v0.6 scope.
    assert surface in str(exc.value)
    assert "v0.6" in str(exc.value)


def test_unknown_surface_raises_value_error():
    with pytest.raises(ValueError):
        build_user_prompt("tiktok", "any topic")


# ---------------------------------------------------------------------------
# Preflight tests (no LLM)
# ---------------------------------------------------------------------------


def test_preflight_rejects_unknown_surface(brand_dir: Path):
    import click

    with pytest.raises(click.ClickException) as exc:
        _preflight("acme-test", "tiktok", brand_path=str(brand_dir))
    assert "unknown surface" in str(exc.value).lower()


def test_preflight_rejects_missing_voice_yaml(tmp_path: Path):
    import click

    empty_brand = tmp_path / "skills" / "brand-voice" / "brands" / "empty-brand"
    empty_brand.mkdir(parents=True)

    with pytest.raises(click.ClickException) as exc:
        _preflight("empty-brand", "x", brand_path=str(empty_brand))
    assert "voice.yaml" in str(exc.value)


def test_preflight_accepts_populated_brand(brand_dir: Path):
    result = _preflight("acme-test", "x", brand_path=str(brand_dir))
    assert result == brand_dir


# ---------------------------------------------------------------------------
# CLI shape tests (no LLM)
# ---------------------------------------------------------------------------


def test_draft_help_renders():
    runner = CliRunner()
    result = runner.invoke(root_cli, ["draft", "--help"])
    assert result.exit_code == 0
    assert "surface" in result.output.lower()
    assert "topic" in result.output.lower()


def test_draft_rejects_unknown_surface_via_choice():
    runner = CliRunner()
    result = runner.invoke(root_cli, ["draft", "tiktok", "hello world"])
    # click.Choice should reject before we enter our own code.
    assert result.exit_code != 0
    assert "tiktok" in result.output.lower() or "invalid" in result.output.lower()


def test_draft_stub_surface_errors_cleanly(brand_dir: Path):
    runner = CliRunner()
    result = runner.invoke(
        root_cli,
        [
            "draft",
            "facebook",
            "any topic",
            "--brand",
            "acme-test",
            "--brand-path",
            str(brand_dir),
        ],
    )
    # We expect a clean ClickException, not a Python traceback.
    assert result.exit_code != 0
    assert "facebook" in result.output.lower()
    assert "not yet" in result.output.lower() or "v0.6" in result.output


def test_draft_missing_brand_errors_cleanly(tmp_path: Path):
    runner = CliRunner()
    bogus_brand_path = tmp_path / "nonexistent-brand"
    result = runner.invoke(
        root_cli,
        [
            "draft",
            "x",
            "hello",
            "--brand",
            "does-not-exist",
            "--brand-path",
            str(bogus_brand_path),
        ],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# LLM-backed tests (gated on ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------


requires_llm = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping live LLM call",
)


@pytest.mark.llm
@requires_llm
def test_draft_x_live_call_returns_something(brand_dir: Path, tmp_path: Path):
    """Smoke-test the live Claude path. Lowered bar: score>=80.

    The goal is to prove the command connects end-to-end, not to grade
    the output. A real composite-95 check would require a seeded brand
    with rubric+exemplars, which is out of MVP scope.
    """
    # Copy the zeststream brand into a fresh location so we do not mutate
    # the packaged brand during a live call.
    repo_root = Path(__file__).resolve().parents[1]
    src_brand = repo_root / "skills" / "brand-voice" / "brands" / "zeststream"
    if not src_brand.exists():
        pytest.skip("zeststream brand not present in repo")

    live_brand = tmp_path / "skills" / "brand-voice" / "brands" / "zeststream"
    live_brand.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_brand, live_brand)

    runner = CliRunner()
    result = runner.invoke(
        root_cli,
        [
            "draft",
            "x",
            "hello world, smoke test",
            "--brand",
            "zeststream",
            "--brand-path",
            str(live_brand),
            "--max-attempts",
            "1",
            "--target-score",
            "80",
            "--json",
        ],
    )

    # We accept exit 0 (passed) or exit 1 (max-attempts exhausted) — both
    # are valid live-call outcomes. We are smoke-testing wiring, not
    # gating on score.
    assert result.exit_code in (0, 1), result.output
    payload = json.loads(result.output)
    assert "text" in payload
    assert payload["text"]
    assert payload["surface"] == "x"
    assert payload["brand"] == "zeststream"
