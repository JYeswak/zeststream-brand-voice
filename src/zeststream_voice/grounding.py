"""Claim extraction + ground-truth matching.

Pulls number-ish tokens out of prose, then looks them up against
capabilities-ground-truth.yaml. A claim "matches" if its literal value or
surrounding context substring-matches a ground-truth entry's value or
canonical_phrasing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


# Matches numbers (with optional commas/decimals) and optionally a trailing unit
# token. Kept deliberately permissive — we'd rather extract a claim and fail to
# match it than silently skip it.
NUMBER_PATTERN = re.compile(
    r"""
    \b
    (
        \d{1,3}(?:,\d{3})+(?:\.\d+)?          # 23,188 or 10,000.5
        | \d+(?:\.\d+)?                        # 96 or 6.37
    )
    (
        \s*%                                    # 6.37%
        | \s*(?:years?|hrs?|hours?|workflows?|clients?|customers?|chunks?|
               weeks?|days?|months?|tok/s|GPUs?|containers?|scripts?|dashboards?|
               counties|county|\+|×|x)          # units
    )?
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

CONTEXT_WINDOW = 80


@dataclass
class Claim:
    """A numeric/quantified token extracted from prose."""

    value: str
    span: list[int]
    context: str


@dataclass
class GroundingResult:
    """Result of matching extracted claims against the ground-truth bank."""

    matched: list[tuple[str, str]] = field(default_factory=list)
    """List of (claim_value, ground_truth_id) tuples."""

    unmatched: list[Claim] = field(default_factory=list)
    """Claims that had no ground-truth hit."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": [{"value": v, "id": i} for v, i in self.matched],
            "unmatched": [
                {"value": c.value, "span": c.span, "context": c.context}
                for c in self.unmatched
            ],
        }


def extract_claims(text: str) -> list[Claim]:
    """Pull every number-ish token that might be a marketing claim."""
    claims: list[Claim] = []
    for m in NUMBER_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        raw = m.group(0).strip()
        context = text[
            max(0, start - CONTEXT_WINDOW) : min(len(text), end + CONTEXT_WINDOW)
        ]
        claims.append(Claim(value=raw, span=[start, end], context=context))
    return claims


def match_against_groundtruth(
    claim: Claim, ground_truth: dict
) -> Optional[str]:
    """Return a ground-truth id if the claim matches, None otherwise.

    Matching strategy (ordered):
      1. Exact value match (numeric) against ``entry.value``
      2. ``canonical_phrasing`` substring present in claim context
      3. Claim value substring present in ``canonical_phrasing``
    """
    entries = ground_truth.get("entries", []) or []

    # Pull the numeric portion of the claim for comparison
    numeric = _strip_to_number(claim.value)

    ctx_lower = claim.context.lower()

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id")
        if not entry_id:
            continue
        # Skip PROHIBITED entries — they're explicit bans, not matches
        if str(entry.get("category", "")).upper() == "PROHIBITED":
            continue

        # 1) numeric equality
        ev = entry.get("value")
        if ev is not None and numeric is not None:
            try:
                if float(ev) == float(numeric):
                    return entry_id
            except (TypeError, ValueError):
                pass

        # 2) canonical_phrasing substring in claim context
        canonical = str(entry.get("canonical_phrasing") or "").strip()
        if canonical and canonical.lower() in ctx_lower:
            return entry_id

        # 3) claim value substring in canonical_phrasing
        if canonical and claim.value.lower().strip() in canonical.lower():
            # Guard: avoid "1" matching "12 years" etc. Require length >= 3 or
            # a unit adjacent.
            if len(claim.value.strip()) >= 3 or any(
                ch.isalpha() for ch in claim.value
            ):
                return entry_id

        # 4) explicit claim text substring match
        claim_text = str(entry.get("claim") or "")
        if claim_text and claim.value.lower().strip() in claim_text.lower():
            if len(claim.value.strip()) >= 3:
                return entry_id

    return None


def ground_text(text: str, ground_truth: dict) -> GroundingResult:
    """Extract every claim in ``text`` and classify as matched/unmatched."""
    result = GroundingResult()
    for claim in extract_claims(text):
        gt_id = match_against_groundtruth(claim, ground_truth)
        if gt_id:
            result.matched.append((claim.value, gt_id))
        else:
            result.unmatched.append(claim)
    return result


_NUMBER_ONLY = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def _strip_to_number(raw: str) -> Optional[float]:
    """Pull the first numeric substring out of raw and return it as float."""
    m = _NUMBER_ONLY.search(raw or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None
