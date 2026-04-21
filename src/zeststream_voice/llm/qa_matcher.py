"""Canonical-answer matcher for inbound questions.

Given an inbound text (an email, a message, a question) and a loaded
qa-matrix.yaml, returns the best-matching canonical answer if confidence
is high enough — otherwise ``None``, and the caller falls back to the
playbook path.

Design
------
No LLM, no embedding model. The match runs at import-time, deterministic,
sub-millisecond. Precision > recall here: a wrong canonical answer is
worse than an honest playbook draft, so the threshold is high.

Algorithm (weighted):
- Exact phrase / substring match of any ``question_variants`` entry → 1.0
- Question-word stem overlap (Jaccard on normalised tokens)
- Topic keyword bonus for known tier-specific terms

Threshold default is 0.7 (tunable). Below that, we return ``None``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml


# Very small English stopword set — enough to avoid weighting "the/a/is"
# when comparing a user's question to known variants.
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "doing", "have", "has", "had",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "her", "its", "our", "their",
    "this", "that", "these", "those",
    "to", "of", "in", "on", "at", "for", "with", "about", "as",
    "and", "or", "but", "if", "so", "not", "no", "yes",
    "what", "how", "why", "when", "where", "who", "which",
    "can", "could", "should", "would", "will", "shall", "may", "might",
    "just", "really", "some", "any", "all", "from", "by",
})

_TOKEN = re.compile(r"[A-Za-z0-9$]+")


def _tokenise(text: str) -> set[str]:
    """Lowercase alphanumeric tokens, stopwords removed."""
    tokens = {m.group(0).lower() for m in _TOKEN.finditer(text or "")}
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


@dataclass
class QAMatch:
    """A resolved canonical-answer match."""

    qa_id: str
    tier: str
    confidence: float
    canonical_answer: str
    register: str = "lay_audience"
    banned_in_this_answer: list[str] = None  # type: ignore[assignment]
    matched_variant: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "qa_id": self.qa_id,
            "tier": self.tier,
            "confidence": round(self.confidence, 3),
            "canonical_answer": self.canonical_answer,
            "register": self.register,
            "banned_in_this_answer": list(self.banned_in_this_answer or []),
            "matched_variant": self.matched_variant,
            "note": self.note,
        }


def load_qa_matrix(brand_dir: Path) -> Optional[dict]:
    """Load qa-matrix.yaml from a brand directory. Returns None if absent.

    The matcher treats a missing matrix as "no canonical answers yet" and
    always falls through to the playbook path.
    """
    path = Path(brand_dir) / "qa-matrix.yaml"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def match_qa(
    inbound_text: str,
    qa_matrix: dict,
    *,
    threshold: float = 0.7,
) -> Optional[QAMatch]:
    """Find the best-matching canonical answer.

    Returns ``None`` if no entry clears ``threshold`` — the caller should
    then fall back to the generic playbook draft path.
    """
    if not inbound_text or not qa_matrix:
        return None

    entries = qa_matrix.get("qa") or []
    if not entries:
        return None

    inbound_norm = (inbound_text or "").lower()
    inbound_tokens = _tokenise(inbound_text)

    best: Optional[QAMatch] = None
    best_score = 0.0

    for entry in entries:
        variants = entry.get("question_variants") or []
        if not variants:
            continue

        # Substring / exact match tier — very strong signal.
        exact_score = 0.0
        matched_variant: Optional[str] = None
        for v in variants:
            vnorm = (v or "").strip().lower().rstrip("?.!")
            if not vnorm:
                continue
            if vnorm and vnorm in inbound_norm:
                exact_score = 1.0
                matched_variant = v
                break

        # Token-overlap tier — fallback signal.
        best_variant_overlap = 0.0
        for v in variants:
            vtokens = _tokenise(v or "")
            overlap = _jaccard(inbound_tokens, vtokens)
            if overlap > best_variant_overlap:
                best_variant_overlap = overlap
                if matched_variant is None:
                    matched_variant = v

        score = max(exact_score, best_variant_overlap)
        if score > best_score:
            canonical = entry.get("canonical_answer") or ""
            best = QAMatch(
                qa_id=entry.get("id", "unknown"),
                tier=entry.get("tier", "T?"),
                confidence=score,
                canonical_answer=canonical.strip(),
                register=entry.get("register", "lay_audience"),
                banned_in_this_answer=list(entry.get("banned_in_this_answer") or []),
                matched_variant=matched_variant,
                note=entry.get("note"),
            )
            best_score = score

    if best is None or best_score < threshold:
        return None
    return best
