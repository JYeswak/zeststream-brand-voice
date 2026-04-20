"""zeststream-voice: brand voice scoring + claim grounding.

v0.4 ships layer 1 (banned-words regex) and grounding (YAML lookup) as real
implementations. Layers 2-4 (rules, embeddings, LLM rubric) raise
NotImplementedError with roadmap pointers.
"""

from zeststream_voice.sdk import (
    BrandVoiceEnforcer,
    Claim,
    GroundingResult,
    LayerResult,
    ScoreResult,
)

__version__ = "0.4.0"

__all__ = [
    "BrandVoiceEnforcer",
    "Claim",
    "GroundingResult",
    "LayerResult",
    "ScoreResult",
    "__version__",
]
