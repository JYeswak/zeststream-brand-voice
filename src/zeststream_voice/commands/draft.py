"""`zv draft` — generate a new piece of copy for a brand surface.

Authoritative spec:
  /Users/josh/Developer/zesttube/.planning/brand-voice-cli/10-write-quadrant-vision.md §1

v0.6 MVP wires three surfaces end-to-end:
  x, linkedin, page

Five more surfaces are accepted by the CLI but raise a clear "not yet
implemented in v0.6" message when asked to draft:
  facebook, instagram, email, meta, blog

Flow (wired surfaces)::

  preflight(brand, surface)
    → build_voice_context(brand_path, surface)
    → build_user_prompt(surface, topic, voice_context)
    → generate_with_voice_gate(client, context, user_prompt, scorer,
                                max_attempts, target_composite)
    → render HUMAN or JSON output
    → exit 0 if passed, exit 1 if max_attempts exhausted without passing

The JUDGE quadrant stays deterministic: scoring is delegated to
``BrandVoiceEnforcer``. Only the *write* step calls the LLM.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

from zeststream_voice._brands import discover_brand
from zeststream_voice.commands._surface_templates import (
    ALL_SURFACES,
    STUB_SURFACES,
    build_user_prompt,
)
from zeststream_voice.llm import (
    GenerationResult,
    LLMClientError,
    build_voice_context,
    generate_with_voice_gate,
    make_client,
)
from zeststream_voice.sdk import BrandVoiceEnforcer


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def _preflight(
    brand: str,
    surface: str,
    brand_path: Optional[str],
) -> Path:
    """Validate surface, resolve brand dir. Returns the brand_dir path.

    Raises ``click.ClickException`` on any failure so the CLI layer emits
    a clean error. No LLM calls, no network — pure config validation.
    """
    if surface not in ALL_SURFACES:
        raise click.ClickException(
            f"unknown surface {surface!r}. "
            f"valid: {', '.join(ALL_SURFACES)}"
        )

    try:
        paths = discover_brand(
            slug=brand,
            explicit_brand_path=Path(brand_path) if brand_path else None,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if not paths.voice_yaml.exists():
        raise click.ClickException(
            f"brand {brand!r} has no voice.yaml at {paths.voice_yaml} — "
            "run `zv peel` first to build the voice"
        )

    return paths.brand_dir


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_human(
    result: GenerationResult,
    *,
    surface: str,
    brand: str,
    target_score: float,
) -> None:
    status = "PASS" if result.passed else "FAIL"
    click.echo("")
    click.echo(f"DRAFT ({status} — score {result.composite:.1f}/100, "
               f"target {target_score:.0f})")
    click.echo("=" * 60)
    click.echo(result.text)
    click.echo("=" * 60)
    click.echo("")
    click.echo(f"surface: {surface}")
    click.echo(f"brand:   {brand}")
    click.echo(f"model:   {result.model}")
    click.echo(f"attempts used: {result.attempts_used}")
    if result.per_dim_scores:
        click.echo("")
        click.echo("per-layer scores:")
        for name, score in result.per_dim_scores.items():
            if isinstance(score, (int, float)):
                tag = " ✓" if score >= 90 else " (weak)"
                click.echo(f"  {name}: {score:.2f}{tag}")
            else:
                click.echo(f"  {name}: {score}")
    if result.banned_hits:
        click.echo("")
        click.echo("banned-word hits (must be resolved before shipping):")
        for word, span in result.banned_hits:
            click.echo(f"  - {word!r} @ {span}")
    if result.which_exemplars_primed:
        click.echo("")
        click.echo("exemplars primed:")
        for rel in result.which_exemplars_primed:
            click.echo(f"  - {rel}")
    click.echo("")
    click.echo(f"cost estimate: {result.cost_estimate_cents:.4f}¢ "
               f"across {result.attempts_used} attempt(s)")


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


@click.command(
    "draft",
    help=(
        "Generate brand-voice copy for a surface (x/linkedin/page wired "
        "in v0.6). See 10-write-quadrant-vision.md §1."
    ),
)
@click.argument("surface", type=click.Choice(ALL_SURFACES, case_sensitive=False))
@click.argument("topic")
@click.option("--brand", default="zeststream", show_default=True,
              help="Brand slug (must already be peeled).")
@click.option("--brand-path", default=None,
              help="Explicit path to the brand folder (overrides --brand).")
@click.option("--model", default=None,
              help="LLM model ID (defaults to ZV_LLM_MODEL env or Haiku 4.5).")
@click.option("--max-attempts", type=int, default=3, show_default=True,
              help="Cap on regen-loop attempts before returning best effort.")
@click.option("--target-score", type=float, default=95.0, show_default=True,
              help="Composite score required for PASS.")
@click.option("--json", "as_json", is_flag=True,
              help="Emit the GenerationResult as JSON for CI/automation.")
def cli(
    surface: str,
    topic: str,
    brand: str,
    brand_path: Optional[str],
    model: Optional[str],
    max_attempts: int,
    target_score: float,
    as_json: bool,
) -> None:
    surface = surface.lower()
    brand_dir = _preflight(brand, surface, brand_path)

    # Early stub gate: keep the CLI UX consistent — the stub explanation
    # comes from ``build_user_prompt`` so we get a single source of truth.
    if surface in STUB_SURFACES:
        try:
            build_user_prompt(surface, topic)
        except NotImplementedError as exc:
            raise click.ClickException(str(exc)) from exc

    try:
        user_prompt = build_user_prompt(surface, topic)
    except (NotImplementedError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    context = build_voice_context(
        brand_path=brand_dir,
        surface=surface,
        brand_slug=brand,
    )

    try:
        client = make_client(model=model)
    except LLMClientError as exc:
        raise click.ClickException(str(exc)) from exc

    scorer = BrandVoiceEnforcer(brand=brand, brand_path=str(brand_dir))

    result = generate_with_voice_gate(
        client,
        context,
        user_prompt=user_prompt,
        scorer=scorer,
        max_attempts=max_attempts,
        target_composite=target_score,
    )

    if as_json:
        payload = result.to_dict()
        payload["surface"] = surface
        payload["brand"] = brand
        payload["target_composite"] = target_score
        click.echo(json.dumps(payload, indent=2))
    else:
        _render_human(
            result,
            surface=surface,
            brand=brand,
            target_score=target_score,
        )

    sys.exit(0 if result.passed else 1)
