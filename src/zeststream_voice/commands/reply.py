"""``zv reply <email-file>`` — draft a response to an inbound message.

Per doc 10 §3. The highest-retention write-quadrant command: takes an inbound
email/message, classifies it against the brand's qa-matrix, and either
wraps a canonical answer in email register OR drafts via playbooks +
exemplars/email when no canonical match exists.

**Human always approves before send.** This command never auto-sends; it
prints a "DRAFT — review before sending" banner.

Flow
----

1. Read inbound from file.
2. Load qa-matrix.yaml for the brand (may be absent → always playbook path).
3. ``match_qa`` on the inbound. If confidence ≥ threshold, route canonical.
4. Build voice context for surface=email.
5. Regen-loop through the LLM until voice-gate passes.
6. Render draft + provenance (canonical-answer used, banned words to watch).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

from zeststream_voice._brands import discover_brand
from zeststream_voice.sdk import BrandVoiceEnforcer


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


_EMAIL_SYSTEM_TAIL = (
    "EMAIL RULES:\n"
    "- Register: warm, first-person, named operator.\n"
    "- No arithmetic (\"N hours at $X\"). Pricing line is: free 20-min Peel + $500 Peel Report.\n"
    "- No promises beyond what's in ground_truth.\n"
    "- Signoff: \"— Joshua\" (never \"Josh\").\n"
)


def _build_canonical_user_prompt(inbound: str, match, extra_context: Optional[str]) -> str:
    """User prompt when qa-matrix matched a canonical answer."""
    banned_note = ""
    if match.banned_in_this_answer:
        banned = ", ".join(sorted(set(match.banned_in_this_answer)))
        banned_note = f"\n\nThe canonical answer explicitly forbids these tokens: {banned}. Do not introduce any of them when expanding."
    ctx = f"\n\nAdditional context from the sender's thread:\n{extra_context.strip()}" if extra_context else ""
    return (
        f"Wrap this canonical answer in an email reply. Keep the substance verbatim; "
        f"add a warm salutation, a brief acknowledgement of what the sender asked, "
        f"the canonical answer itself, and a simple CTA (book a Peel or reply-for-more).\n\n"
        f"INBOUND:\n---\n{inbound.strip()}\n---\n\n"
        f"CANONICAL ANSWER (id={match.qa_id}, tier={match.tier}, confidence={match.confidence:.2f}):\n"
        f"---\n{match.canonical_answer}\n---"
        f"{banned_note}"
        f"{ctx}\n\n"
        f"Output only the email body. No subject line unless the inbound demands one. No preamble, no meta."
    )


def _build_playbook_user_prompt(inbound: str, extra_context: Optional[str]) -> str:
    """User prompt when no canonical match — we lean on playbooks + exemplars/email."""
    ctx = f"\n\nAdditional context from the sender's thread:\n{extra_context.strip()}" if extra_context else ""
    return (
        f"Draft an email reply to this inbound message. No canonical answer matched "
        f"the brand's qa-matrix, so lean on the voice constants and email exemplars.\n\n"
        f"INBOUND:\n---\n{inbound.strip()}\n---"
        f"{ctx}\n\n"
        f"Rules: do not invent numbers or commitments. If you don't know the answer, say "
        f"\"I'll follow up with specifics\" instead of guessing. Close with a next step the "
        f"sender can act on without another email from you.\n\n"
        f"Output only the email body. No subject line, no preamble, no meta."
    )


def _append_email_rules(context_system: list[dict]) -> list[dict]:
    """Splice the EMAIL RULES tail onto the dynamic (non-cached) block."""
    system = list(context_system)
    system.append({"type": "text", "text": _EMAIL_SYSTEM_TAIL})
    return system


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command(
    "reply",
    help=(
        "Draft an email reply, routing canonical-answer hits through the qa-matrix "
        "and falling back to playbook+exemplars on a miss. Always DRAFT — never sends."
    ),
)
@click.argument(
    "email_file",
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
)
@click.option("--brand", default="zeststream", show_default=True)
@click.option(
    "--brand-path",
    default=None,
    help="Explicit brand directory (overrides --brand).",
)
@click.option(
    "--model",
    default=None,
    help="Override the LLM model (else env ZV_LLM_MODEL or package default).",
)
@click.option(
    "--context",
    "extra_context",
    default=None,
    help="Extra thread context the LLM should condition on.",
)
@click.option(
    "--max-attempts",
    type=int,
    default=3,
    show_default=True,
)
@click.option(
    "--target-score",
    type=float,
    default=95.0,
    show_default=True,
)
@click.option(
    "--qa-threshold",
    type=float,
    default=0.7,
    show_default=True,
    help="Minimum confidence to accept a qa-matrix match (else playbook path).",
)
@click.option("--json", "as_json", is_flag=True)
def cli(
    email_file: Path,
    brand: str,
    brand_path: Optional[str],
    model: Optional[str],
    extra_context: Optional[str],
    max_attempts: int,
    target_score: float,
    qa_threshold: float,
    as_json: bool,
) -> None:
    # Lazy LLM import so missing extras don't break --help.
    try:
        from zeststream_voice.llm import (
            build_voice_context,
            generate_with_voice_gate,
            get_llm_client,
        )
        from zeststream_voice.llm.qa_matcher import load_qa_matrix, match_qa
    except ImportError as exc:  # pragma: no cover
        raise click.ClickException(
            f"LLM subsystem unavailable: {exc}. Install: pip install 'zeststream-voice[rubric]'"
        ) from exc

    inbound = email_file.read_text(encoding="utf-8").strip()
    if not inbound:
        raise click.ClickException(f"{email_file} is empty — nothing to reply to.")

    try:
        paths = discover_brand(
            slug=brand,
            explicit_brand_path=Path(brand_path) if brand_path else None,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    # --- Classify inbound against the qa-matrix (may be absent).
    qa_matrix = load_qa_matrix(paths.brand_dir)
    qa_match = (
        match_qa(inbound, qa_matrix, threshold=qa_threshold)
        if qa_matrix
        else None
    )

    # --- Build voice context + LLM client.
    context = build_voice_context(
        brand_path=paths.brand_dir,
        surface="email",
        brand_slug=brand,
    )
    context.system = _append_email_rules(context.system)

    try:
        client = get_llm_client(model=model)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if qa_match is not None:
        user_prompt = _build_canonical_user_prompt(inbound, qa_match, extra_context)
        route = "canonical"
    else:
        user_prompt = _build_playbook_user_prompt(inbound, extra_context)
        route = "playbook"

    enforcer = BrandVoiceEnforcer(brand=brand, brand_path=str(paths.brand_dir))

    gen = generate_with_voice_gate(
        client=client,
        context=context,
        user_prompt=user_prompt,
        scorer=enforcer,
        max_attempts=max_attempts,
        target_composite=target_score,
    )

    # --- Render.
    if as_json:
        payload = {
            "route": route,
            "qa_match": qa_match.to_dict() if qa_match else None,
            "qa_threshold": qa_threshold,
            "brand": brand,
            "draft": gen.text,
            "generation": gen.to_dict(),
            "reminder": "DRAFT — review before sending. Never auto-send.",
        }
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo("")
        click.echo(f"=== DRAFT — review before sending ({route} route) ===")
        if qa_match is not None:
            click.echo(
                f"canonical answer: {qa_match.qa_id} "
                f"(tier={qa_match.tier}, confidence={qa_match.confidence:.2f})"
            )
            if qa_match.banned_in_this_answer:
                click.echo(
                    f"banned-in-this-answer: "
                    f"{', '.join(sorted(set(qa_match.banned_in_this_answer)))}"
                )
        else:
            click.echo("canonical answer: (none — playbook path)")
        click.echo(f"model: {gen.model}")
        click.echo(
            f"score: {gen.composite:.2f}  attempts: {gen.attempts_used}  "
            f"cost≈{gen.cost_estimate_cents:.2f}¢"
        )
        click.echo("=" * 60)
        click.echo(gen.text.rstrip() if gen.text else "(empty — LLM returned no content)")
        click.echo("=" * 60)
        if gen.banned_hits:
            click.echo("")
            click.echo("banned-word hits (must be resolved before sending):")
            for word, span in gen.banned_hits:
                click.echo(f"  - {word!r} @ {span}")
        click.echo("")
        click.echo("Reminder: human approves before send. Never auto-send.")

    sys.exit(0 if gen.passed else 2)
