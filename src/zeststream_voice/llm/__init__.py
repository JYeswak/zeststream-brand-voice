"""LLM foundation for zv write-quadrant (draft / rewrite / reply).

The judge quadrant (score/enforce/ground) is deterministic. The write quadrant
wraps an LLM provider behind a thin abstraction so the engine can stay
provider-agnostic.
"""

from zeststream_voice.llm.client import (
    ANTHROPIC_API_KEY_HELP,
    AnthropicClient,
    LLMClient,
    LLMClientError,
    LLMResponse,
    default_model,
    make_client,
)
from zeststream_voice.llm.context import VoiceContext, build_voice_context
from zeststream_voice.llm.regen_loop import GenerationResult, generate_with_voice_gate

__all__ = [
    "ANTHROPIC_API_KEY_HELP",
    "AnthropicClient",
    "GenerationResult",
    "LLMClient",
    "LLMClientError",
    "LLMResponse",
    "VoiceContext",
    "build_voice_context",
    "default_model",
    "generate_with_voice_gate",
    "make_client",
]
