"""``zv rewrite <file>`` — the killer demo.

Takes off-brand copy, identifies specific failures via the deterministic
voice-gate, then rewrites the copy through an LLM + regen-loop until it
clears the gate (or we hit ``--max-attempts``). Outputs BEFORE/AFTER with
score deltas and an optional unified diff.

Spec: /Users/josh/Developer/zesttube/.planning/brand-voice-cli/10-write-quadrant-vision.md §2.

Surface auto-detection
----------------------
If the caller doesn't pass ``--surface``, we pick from text length:

    len < 280    → x
    len < 500    → post      (generic short-form)
    len < 1500   → email
    otherwise    → page

Clients can always override with ``--surface``.

Output modes
------------
- Default (human): "BEFORE  N.NN -> AFTER  N.NN" header, a "failures fixed"
  block, and (with ``--show-diff``) a unified diff.
- ``--json``: full envelope including the GenerationResult dict, the
  BEFORE/AFTER score dicts, attempt telemetry, and the rendered diff.

The command intentionally does NOT write back to the source file — callers
redirect stdout or pipe. "Always approve before send" per the vision doc.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

from zeststream_voice.commands._diff_render import render_diff
from zeststream_voice.sdk import BrandVoiceEnforcer, ScoreResult


# ---------------------------------------------------------------------------
# Constants / small helpers
# ---------------------------------------------------------------------------


VALID_SURFACES = (
    "auto",
    "x",
    "linkedin",
    "facebook",
    "instagram",
    "email",
    "page",
    "post",
    "meta",
    "blog",
)


def _detect_surface(text: str) -> str:
    """Heuristic surface picker based on text length."""
    n = len(text)
    if n < 280:
        return "x"
    if n < 500:
        return "post"
    if n < 1500:
        return "email"
    return "page"


def _failure_summary(result: ScoreResult) -> list[str]:
    """Flatten a ScoreResult into a list of human-readable failure strings.

    Empty list means "nothing to fix" — which is the signal that the input
    already passes the gate and no rewrite is necessary.
    """
    failures: list[str] = []

    # Banned-word hits are the most common and most concrete failures.
    for word, span in result.banned_hits:
        failures.append(f"banned word/phrase: {word!r} at offset {span}")

    # Layer-level vetoes / reasons.
    for name, layer in result.layers.items():
        reason = getattr(layer, "reason", "") or ""
        score = getattr(layer, "score", None)
        vetoed = getattr(layer, "vetoed", False)
        if vetoed:
            failures.append(f"{name}: VETOED — {reason}")
        elif isinstance(score, (int, float)) and score < 90:
            failures.append(f"{name}: low score {score:.1f} — {reason or '(no reason given)'}")

    # Grounding issues (unmatched numeric claims).
    grounded = result.grounded
    if grounded is not None:
        for claim in grounded.unmatched:
            val = getattr(claim, "value", "?")
            ctx = (getattr(claim, "context", "") or "").strip().replace("\n", " ")
            failures.append(f"ungrounded claim: {val!r} (context: …{ctx[:60]}…)")

    return failures


def _initial_user_prompt(
    original: str,
    surface: str,
    failures: list[str],
    target_composite: float,
) -> str:
    """Build the first-attempt user prompt for the regen loop.

    The regen loop takes care of subsequent attempts; this only needs to
    tell the model (a) what to rewrite, (b) why it failed, (c) the target.
    """
    fail_block = (
        "\n".join(f"- {f}" for f in failures) if failures else "- (none detected)"
    )
    return (
        f"Rewrite the following {surface}-surface copy so it clears the voice "
        f"gate (composite ≥{target_composite:.0f}). Preserve meaning and any "
        "grounded numeric claims; rewrite tone, structure, and banned words.\n\n"
        "ORIGINAL:\n"
        "---\n"
        f"{original.strip()}\n"
        "---\n\n"
        f"Specific failures identified by the scorer:\n{fail_block}\n\n"
        "Output only the rewritten copy — no preamble, no meta-commentary, "
        "no markdown fences."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command(
    "rewrite",
    help="Rewrite a file's copy to clear the brand voice gate (BEFORE/AFTER).",
)
@click.argument(
    "file",
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
)
@click.option(
    "--surface",
    type=click.Choice(list(VALID_SURFACES), case_sensitive=False),
    default="auto",
    show_default=True,
    help="Target surface. 'auto' picks by text length.",
)
@click.option("--brand", default="zeststream", show_default=True)
@click.option(
    "--brand-path",
    default=None,
    help="Explicit brand directory containing voice.yaml (overrides --brand).",
)
@click.option(
    "--accept-threshold",
    type=float,
    default=95.0,
    show_default=True,
    help="Composite score the rewrite must clear.",
)
@click.option(
    "--max-attempts",
    type=int,
    default=3,
    show_default=True,
    help="Regen-loop cap. 1 disables regeneration.",
)
@click.option(
    "--model",
    default=None,
    help="Override the LLM model (else env ZV_LLM_MODEL or package default).",
)
@click.option(
    "--show-diff",
    is_flag=True,
    help="Print a unified diff between BEFORE and AFTER.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit a JSON envelope.")
def cli(
    file: Path,
    surface: str,
    brand: str,
    brand_path: Optional[str],
    accept_threshold: float,
    max_attempts: int,
    model: Optional[str],
    show_diff: bool,
    as_json: bool,
) -> None:
    # Lazy LLM imports so missing extras don't break `--help`.
    try:
        from zeststream_voice.llm import (
            build_voice_context,
            generate_with_voice_gate,
            make_client,
        )
    except ImportError as e:  # pragma: no cover
        raise click.ClickException(
            f"LLM subsystem unavailable: {e}. Install the extras: "
            "pip install 'zeststream-voice[rubric]'"
        ) from e

    original = file.read_text(encoding="utf-8")
    if not original.strip():
        raise click.ClickException(f"{file} is empty — nothing to rewrite.")

    resolved_surface = (
        _detect_surface(original) if surface == "auto" else surface.lower()
    )

    # --- BEFORE: score the original deterministically.
    try:
        enforcer = BrandVoiceEnforcer(brand=brand, brand_path=brand_path)
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e

    before_result = enforcer.score(original, include_grounding=True)
    before_composite = before_result.composite
    failures = _failure_summary(before_result)

    # Fast-path: already on brand and above threshold. Return AFTER=BEFORE.
    if before_result.passed and before_composite >= accept_threshold:
        _emit(
            original=original,
            rewritten=original,
            before=before_result,
            after=before_result,
            surface=resolved_surface,
            attempts=1,
            cost_cents=0.0,
            model_used="(none — already on-brand)",
            no_rewrite_needed=True,
            show_diff=show_diff,
            as_json=as_json,
            threshold=accept_threshold,
            failures=failures,
        )
        sys.exit(0)

    # --- Build voice context + LLM client, then run the regen loop.
    try:
        client = make_client(model=model)
    except Exception as e:
        raise click.ClickException(str(e)) from e

    context = build_voice_context(
        brand_path=Path(brand_path) if brand_path else enforcer.paths.brand_dir,
        surface=resolved_surface,
        brand_slug=brand,
    )

    user_prompt = _initial_user_prompt(
        original=original,
        surface=resolved_surface,
        failures=failures,
        target_composite=accept_threshold,
    )

    gen = generate_with_voice_gate(
        client=client,
        context=context,
        user_prompt=user_prompt,
        scorer=enforcer,
        max_attempts=max_attempts,
        target_composite=accept_threshold,
    )

    rewritten = gen.text or ""
    after_result = enforcer.score(rewritten, include_grounding=True) if rewritten else before_result

    _emit(
        original=original,
        rewritten=rewritten,
        before=before_result,
        after=after_result,
        surface=resolved_surface,
        attempts=gen.attempts_used,
        cost_cents=gen.cost_estimate_cents,
        model_used=gen.model,
        no_rewrite_needed=False,
        show_diff=show_diff,
        as_json=as_json,
        threshold=accept_threshold,
        failures=failures,
        gen_result=gen,
    )

    # Exit 0 if we cleared the threshold; 2 otherwise (CI-friendly).
    sys.exit(0 if after_result.composite >= accept_threshold and after_result.passed else 2)


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def _emit(
    *,
    original: str,
    rewritten: str,
    before: ScoreResult,
    after: ScoreResult,
    surface: str,
    attempts: int,
    cost_cents: float,
    model_used: str,
    no_rewrite_needed: bool,
    show_diff: bool,
    as_json: bool,
    threshold: float,
    failures: list[str],
    gen_result=None,
) -> None:
    """Render the BEFORE/AFTER output in the requested mode."""
    diff_text = render_diff(original, rewritten) if (rewritten and rewritten != original) else ""

    if as_json:
        payload = {
            "surface": surface,
            "threshold": threshold,
            "no_rewrite_needed": no_rewrite_needed,
            "attempts_used": attempts,
            "cost_estimate_cents": round(cost_cents, 4),
            "model": model_used,
            "before": {
                "composite": before.composite,
                "passed": before.passed,
                "failures": failures,
                "score": before.to_dict(),
            },
            "after": {
                "composite": after.composite,
                "passed": after.passed,
                "score": after.to_dict(),
            },
            "diff": diff_text,
            "original": original,
            "rewritten": rewritten,
        }
        if gen_result is not None:
            payload["generation"] = gen_result.to_dict()
        click.echo(json.dumps(payload, indent=2))
        return

    # Human mode.
    click.echo(f"surface: {surface}")
    click.echo(f"model:   {model_used}")
    click.echo(
        f"BEFORE:  {before.composite:6.2f}  "
        f"{'PASS' if before.passed else 'FAIL'}  "
        f"({len(failures)} failure{'s' if len(failures) != 1 else ''})"
    )
    click.echo(
        f"AFTER:   {after.composite:6.2f}  "
        f"{'PASS' if after.passed else 'FAIL'}  "
        f"(attempts={attempts}, cost≈{cost_cents:.2f}¢)"
    )
    delta = after.composite - before.composite
    if delta > 0:
        click.echo(f"delta:   +{delta:.2f}")
    elif delta < 0:
        click.echo(f"delta:   {delta:.2f}")

    if no_rewrite_needed:
        click.echo("")
        click.echo("Input already clears the voice gate — no rewrite performed.")
        return

    if failures:
        click.echo("")
        click.echo("Failures targeted:")
        for f in failures:
            click.echo(f"  - {f}")

    click.echo("")
    click.echo("--- AFTER ---")
    click.echo(rewritten.rstrip() if rewritten else "(empty — LLM returned no content)")

    if show_diff and diff_text:
        click.echo("")
        click.echo("--- DIFF ---")
        click.echo(diff_text.rstrip())
