"""Public SDK surface."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from zeststream_voice._brands import (
    BrandPaths,
    discover_brand,
    load_ground_truth,
    load_voice_yaml,
)
from zeststream_voice.grounding import Claim, GroundingResult, ground_text
from zeststream_voice.scorer import (
    LayerResult,
    score_layer1_banned,
    score_layer2_rules,
    score_layer3_embedding,
    score_layer4_rubric,
)


# Re-export so callers can `from zeststream_voice import Claim` etc.
__all__ = [
    "BrandVoiceEnforcer",
    "Claim",
    "GroundingResult",
    "LayerResult",
    "ScoreResult",
]


@dataclass
class ScoreResult:
    """Composite result from ``BrandVoiceEnforcer.score()``."""

    composite: float
    passed: bool
    layers: dict[str, LayerResult] = field(default_factory=dict)
    banned_hits: list[tuple[str, list[int]]] = field(default_factory=list)
    grounded: Optional[GroundingResult] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "composite": self.composite,
            "passed": self.passed,
            "layers": {
                k: {
                    "name": v.name,
                    "score": v.score,
                    "vetoed": v.vetoed,
                    "reason": v.reason,
                    "details": v.details,
                }
                for k, v in self.layers.items()
            },
            "banned_hits": [
                {"word": w, "span": s} for w, s in self.banned_hits
            ],
            "grounded": self.grounded.to_dict() if self.grounded else None,
        }


class BrandVoiceEnforcer:
    """Main SDK entry point.

    >>> e = BrandVoiceEnforcer(brand="zeststream")
    >>> result = e.score("some draft text")
    >>> result.composite
    100.0
    """

    def __init__(
        self,
        brand: str = "zeststream",
        brand_path: Optional[str | Path] = None,
        search_from: Optional[Path] = None,
        warn_stream=sys.stderr,
    ) -> None:
        self._paths: BrandPaths = discover_brand(
            slug=brand,
            search_from=search_from,
            explicit_brand_path=Path(brand_path) if brand_path else None,
        )
        self._voice: dict = load_voice_yaml(self._paths)
        self._ground_truth: dict = load_ground_truth(self._paths)
        self._warn_stream = warn_stream

    # ------------------------------------------------------------------ info
    @property
    def paths(self) -> BrandPaths:
        return self._paths

    @property
    def voice_yaml(self) -> dict:
        return self._voice

    @property
    def ground_truth_yaml(self) -> dict:
        return self._ground_truth

    # --------------------------------------------------------------- scoring
    def score(self, text: str, *, include_grounding: bool = True) -> ScoreResult:
        """Score ``text`` through layer 1 (real) + optional grounding.

        Layers 2-4 are not invoked; see score_with_rubric etc. for explicit
        NotImplementedError surfaces.
        """
        layer1 = score_layer1_banned(text, self._voice)
        layers: dict[str, LayerResult] = {layer1.name: layer1}

        # Emit a single, clear warning so operators aren't surprised by the
        # layer-1-only composite.
        self._warn(
            "v0.4 ships layer 1 + grounding only. Layers 2-4 on roadmap — "
            "composite reflects layer 1 only."
        )

        composite = layer1.score
        passed = not layer1.vetoed and composite >= self._composite_threshold()

        banned_hits: list[tuple[str, list[int]]] = []
        for hit in layer1.details.get("hits", []):
            word = hit.get("word", "")
            span = hit.get("span", [0, 0])
            banned_hits.append((word, span))

        grounded = None
        if include_grounding:
            grounded = ground_text(text, self._ground_truth)

        return ScoreResult(
            composite=composite,
            passed=passed,
            layers=layers,
            banned_hits=banned_hits,
            grounded=grounded,
        )

    def ground(self, text: str) -> GroundingResult:
        """Extract + classify numeric claims against ground-truth."""
        return ground_text(text, self._ground_truth)

    # --------------------------------------------------- future-layer stubs
    def score_with_rules(self, text: str) -> LayerResult:
        return score_layer2_rules(text, self._voice)

    def score_with_embeddings(
        self, text: str, exemplars_dir: str | None = None
    ) -> LayerResult:
        return score_layer3_embedding(text, self._voice, exemplars_dir)

    def score_with_rubric(
        self, text: str, api_key: str | None = None
    ) -> LayerResult:
        return score_layer4_rubric(text, self._voice, api_key)

    # -------------------------------------------------------------- helpers
    def _composite_threshold(self) -> float:
        rubric = self._voice.get("rubric") or {}
        thresholds = rubric.get("thresholds") or {}
        # Canonical threshold for "ship" is composite_ge_95; express as 95.0.
        # We treat composite_below_85 as hard fail; between = regen.
        # For `passed`, we require composite >= 95 AND no veto.
        if "composite_ge_95" in thresholds:
            return 95.0
        return 85.0

    def _warn(self, msg: str) -> None:
        if self._warn_stream is None:
            return
        try:
            self._warn_stream.write(f"[zeststream-voice] {msg}\n")
            self._warn_stream.flush()
        except Exception:
            pass
