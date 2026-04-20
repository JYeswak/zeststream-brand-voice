"""Scoring layers.

v0.4 ships layer 1 (banned-words + operator-variant regex) as a REAL, veto-style
check. Layers 2-4 raise NotImplementedError with roadmap pointers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LayerResult:
    """Result from a single scoring layer."""

    name: str
    score: float
    vetoed: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


def _word_boundary_pattern(term: str) -> re.Pattern[str]:
    """Build a case-insensitive word-boundary pattern for ``term``.

    Uses non-word-boundary matching at the edges so hyphenated/quoted phrases
    like "cutting-edge" still match.
    """
    escaped = re.escape(term)
    # For multi-word or hyphenated phrases, \b around the whole thing is fine
    # because re.escape preserves internal spaces/hyphens.
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def score_layer1_banned(text: str, voice_yaml: dict) -> LayerResult:
    """Layer 1 — banned-words + operator-variant regex. VETO on any hit."""
    banned = list(voice_yaml.get("banned_words", []) or [])
    banned_phrases = list(voice_yaml.get("banned_phrases", []) or [])

    hits: list[dict[str, Any]] = []

    for word in banned + banned_phrases:
        if not isinstance(word, str) or not word.strip():
            continue
        pat = _word_boundary_pattern(word)
        for m in pat.finditer(text):
            start, end = m.start(), m.end()
            hits.append(
                {
                    "word": word,
                    "span": [start, end],
                    "context": text[max(0, start - 20) : end + 20],
                }
            )

    # Operator-variant check — case-SENSITIVE (we don't want to ban "josh" inside
    # "Josh" in lowercase contexts like code identifiers; the trauma fix is
    # specifically about canonical-casing like "Josh" in prose).
    variants_banned: list[str] = []
    brand = voice_yaml.get("brand") or {}
    for v in brand.get("operator_variants_banned", []) or []:
        if isinstance(v, str) and v.strip():
            variants_banned.append(v)

    # Also honor trademarks.brand_names.never_joshua (session 15 schema)
    tm = voice_yaml.get("trademarks") or {}
    tm_names = tm.get("brand_names") or {}
    for v in tm_names.get("never_joshua", []) or []:
        if isinstance(v, str) and v.strip() and v not in variants_banned:
            variants_banned.append(v)

    canonical = (tm_names.get("joshua") or brand.get("operator") or "Joshua Nowak")

    for variant in variants_banned:
        pat = re.compile(rf"(?<!\w){re.escape(variant)}(?!\w)")  # case-SENSITIVE
        for m in pat.finditer(text):
            start, end = m.start(), m.end()
            hits.append(
                {
                    "word": variant,
                    "span": [start, end],
                    "canonical": canonical,
                    "reason": "operator_variant_banned",
                    "context": text[max(0, start - 20) : end + 20],
                }
            )

    score = 100.0 if not hits else 0.0
    reason = (
        "clean"
        if not hits
        else f"{len(hits)} banned word(s) or operator variant(s) found"
    )
    return LayerResult(
        name="layer1_banned_words",
        score=score,
        vetoed=bool(hits),
        reason=reason,
        details={"hits": hits},
    )


def score_layer2_rules(text: str, voice_yaml: dict) -> LayerResult:
    raise NotImplementedError(
        "Layer 2 (three_moves rules engine) lands in v0.5. "
        "See https://github.com/JYeswak/zeststream-brand-voice/blob/main/ROADMAP.md"
    )


def score_layer3_embedding(
    text: str, voice_yaml: dict, exemplars_dir: str | None = None
) -> LayerResult:
    raise NotImplementedError(
        "Layer 3 (cosine similarity to exemplars) requires sentence-transformers + "
        "Qdrant. Install: pip install 'zeststream-voice[embeddings]' + run local "
        "Qdrant. Lands in v0.6 — see ROADMAP.md"
    )


def score_layer4_rubric(
    text: str, voice_yaml: dict, api_key: str | None = None
) -> LayerResult:
    raise NotImplementedError(
        "Layer 4 (15-dim LLM rubric) requires anthropic API access. "
        "Install: pip install 'zeststream-voice[rubric]' + set ANTHROPIC_API_KEY. "
        "Lands in v0.6 — see ROADMAP.md"
    )
