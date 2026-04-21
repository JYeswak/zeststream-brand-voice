"""Draft → score → revise regeneration loop.

Wraps an ``LLMClient`` + a ``BrandVoiceEnforcer`` in a single call:

    result = generate_with_voice_gate(
        client, context, user_prompt="draft an x post about the 910× cache fix",
        scorer=BrandVoiceEnforcer(brand="zeststream"),
    )

The loop is deliberately simple: generate, score, and on failure re-prompt
with the specific scorer feedback baked in. Max attempts capped so a
pathological voice/prompt pair cannot burn unbounded tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zeststream_voice.llm.client import LLMClient, LLMResponse
from zeststream_voice.llm.context import VoiceContext


@dataclass
class GenerationResult:
    """Outcome of a ``generate_with_voice_gate`` run."""

    text: str
    composite: float
    passed: bool
    attempts_used: int
    per_dim_scores: dict[str, Any] = field(default_factory=dict)
    which_exemplars_primed: list[str] = field(default_factory=list)
    cost_estimate_cents: float = 0.0
    model: str = ""
    banned_hits: list[tuple[str, list[int]]] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "composite": self.composite,
            "passed": self.passed,
            "attempts_used": self.attempts_used,
            "per_dim_scores": self.per_dim_scores,
            "which_exemplars_primed": list(self.which_exemplars_primed),
            "cost_estimate_cents": round(self.cost_estimate_cents, 4),
            "model": self.model,
            "banned_hits": [{"word": w, "span": s} for w, s in self.banned_hits],
            "attempts": self.attempts,
        }


def generate_with_voice_gate(
    client: LLMClient,
    context: VoiceContext,
    user_prompt: str,
    scorer,
    *,
    max_attempts: int = 3,
    target_composite: float = 95.0,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> GenerationResult:
    """Generate copy and iterate until it passes the voice gate.

    ``scorer`` is any object exposing ``.score(text) -> ScoreResult`` — in
    practice, a ``BrandVoiceEnforcer``. We deliberately avoid importing it
    here so the regen loop stays free of scorer-specific dependencies.
    """
    current_prompt = user_prompt
    total_cost = 0.0
    attempts: list[dict[str, Any]] = []
    last_text = ""
    last_composite = 0.0
    last_passed = False
    last_per_dim: dict[str, Any] = {}
    last_banned: list[tuple[str, list[int]]] = []

    for attempt in range(1, max_attempts + 1):
        resp: LLMResponse = client.generate(
            system=context.system,
            user=current_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        total_cost += resp.cost_estimate_cents
        text = resp.text.strip()

        result = scorer.score(text)
        composite = float(getattr(result, "composite", 0.0) or 0.0)
        passed = bool(getattr(result, "passed", False)) and composite >= target_composite
        per_dim = _per_dim_from_scorer(result)
        banned = list(getattr(result, "banned_hits", []) or [])

        attempts.append(
            {
                "attempt": attempt,
                "composite": composite,
                "passed": passed,
                "banned_hits": [w for w, _ in banned],
                "output_tokens": resp.output_tokens,
                "cost_cents": round(resp.cost_estimate_cents, 4),
            }
        )
        last_text = text
        last_composite = composite
        last_passed = passed
        last_per_dim = per_dim
        last_banned = banned

        if passed:
            break

        current_prompt = _rebuild_prompt(
            original=user_prompt,
            last_text=text,
            composite=composite,
            banned_hits=[w for w, _ in banned],
            per_dim=per_dim,
            target_composite=target_composite,
        )

    return GenerationResult(
        text=last_text,
        composite=last_composite,
        passed=last_passed,
        attempts_used=len(attempts),
        per_dim_scores=last_per_dim,
        which_exemplars_primed=list(context.exemplars_loaded),
        cost_estimate_cents=total_cost,
        model=getattr(client, "model", ""),
        banned_hits=last_banned,
        attempts=attempts,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _per_dim_from_scorer(result: Any) -> dict[str, Any]:
    """Extract per-layer / per-dim scores from a ScoreResult.

    Tolerant of both the v0.4 shape (layers dict) and any future per-dim dict.
    """
    per_dim: dict[str, Any] = {}
    layers = getattr(result, "layers", None) or {}
    for name, layer in layers.items():
        score = getattr(layer, "score", None)
        if score is None and isinstance(layer, dict):
            score = layer.get("score")
        per_dim[name] = score
    # Future-proof: if scorer exposes a flat per-dim map, merge it.
    dims = getattr(result, "per_dim", None)
    if isinstance(dims, dict):
        per_dim.update(dims)
    return per_dim


def _rebuild_prompt(
    original: str,
    last_text: str,
    composite: float,
    banned_hits: list[str],
    per_dim: dict[str, Any],
    target_composite: float,
) -> str:
    """Rebuild the user prompt with scorer feedback for the next attempt."""
    feedback_bits: list[str] = []
    feedback_bits.append(
        f"Previous draft scored {composite:.1f} (target ≥{target_composite:.0f}). Rewrite it so it passes."
    )
    if banned_hits:
        feedback_bits.append(f"Banned words/phrases hit: {', '.join(sorted(set(banned_hits)))}. Remove every one.")
    weak_layers = [name for name, s in per_dim.items() if isinstance(s, (int, float)) and s < 90]
    if weak_layers:
        feedback_bits.append(f"Weak layers: {', '.join(weak_layers)}. Tighten these.")
    feedback_bits.append("Keep on-voice per the system prompt. Do not invent numeric claims.")

    return (
        f"Original brief:\n{original.strip()}\n\n"
        f"Your previous attempt:\n---\n{last_text.strip()}\n---\n\n"
        f"Scorer feedback:\n- " + "\n- ".join(feedback_bits) + "\n\n"
        "Produce a new draft that clears the voice gate."
    )
