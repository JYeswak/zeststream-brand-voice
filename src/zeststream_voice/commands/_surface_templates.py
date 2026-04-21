"""User-prompt templates per surface for ``zv draft``.

The system prompt (voice.yaml + exemplars) is built by
``zeststream_voice.llm.context.build_voice_context``. This module
contributes only the *user* message — the topic-specific brief that
tells the model what to write and what structural constraints apply to
this surface.

Surfaces wired in v0.6 MVP:
  - x         (single post, <=280 chars)
  - linkedin  (150-200 word post)
  - page      (landing-page hero, 30-50 words)

Surfaces stubbed (v0.6 raises NotImplementedError):
  facebook, instagram, email, meta, blog
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zeststream_voice.llm.context import VoiceContext


WIRED_SURFACES: tuple[str, ...] = ("x", "linkedin", "page")
STUB_SURFACES: tuple[str, ...] = ("facebook", "instagram", "email", "meta", "blog")
ALL_SURFACES: tuple[str, ...] = WIRED_SURFACES + STUB_SURFACES


def _canon_hint(voice_context: "VoiceContext | None") -> str:
    """Return a one-line canon reminder if voice_context exposes it.

    Kept defensive: VoiceContext is structured for LLM consumption; we do
    not reach back into its blocks to parse YAML. The reminder is a
    generic "use the canon verbatim when it fits" nudge, which the system
    prompt then enforces with actual text.
    """
    return (
        "If your surface permits, include the brand canon line verbatim "
        "from the system prompt."
    )


def build_user_prompt(
    surface: str,
    topic: str,
    voice_context: "VoiceContext | None" = None,
) -> str:
    """Return the user message for ``client.generate()``.

    Parameters
    ----------
    surface:
        One of ``ALL_SURFACES``. Wired surfaces return a real brief;
        stub surfaces raise ``NotImplementedError`` with a clear v0.6
        scope message.
    topic:
        The raw topic/brief the caller typed on the CLI.
    voice_context:
        Optional — currently unused for wiring but reserved so templates
        can pull surface-specific hints (e.g. sentence caps) once the
        Block 8 situation_playbooks lands in voice.yaml.
    """
    surface = surface.lower().strip()
    topic = (topic or "").strip()

    if surface in STUB_SURFACES:
        raise NotImplementedError(
            f"surface {surface!r} is not yet wired in v0.6. "
            f"Wired surfaces: {', '.join(WIRED_SURFACES)}. "
            "Stubs land in Wave E/F per "
            ".planning/brand-voice-cli/10-write-quadrant-vision.md."
        )

    if surface == "x":
        return (
            f"Write a single X post (<=280 chars) on topic: {topic}\n\n"
            "Structural rules:\n"
            "- Exactly one post, no thread.\n"
            "- Must include at least 1 receipt (a specific number, repo, "
            "SHA, count, or named artifact).\n"
            "- Surface register: operator, direct, no hype.\n"
            "- No hashtags unless the topic explicitly calls for one.\n"
            "- Open with tension or a specific moment, not a framing "
            "statement.\n"
            f"- {_canon_hint(voice_context)}"
        )

    if surface == "linkedin":
        return (
            f"Write a 150-200 word LinkedIn post on topic: {topic}\n\n"
            "Structural rules:\n"
            "- Open with a specific receipt (number, client moment, "
            "timestamp — not a generic statement).\n"
            "- Develop exactly 1 insight. Do not list 3 takeaways.\n"
            "- Close with a soft invite (zeststream.ai/consult if and "
            "only if relevant to the insight).\n"
            "- First-person operator voice. No 'we' unless the system "
            "prompt says collective voice is permitted.\n"
            "- 150-200 words. Count them.\n"
            f"- {_canon_hint(voice_context)}"
        )

    if surface == "page":
        return (
            f"Write a landing-page hero section (30-50 words) for "
            f"topic: {topic}\n\n"
            "Structural rules:\n"
            "- Include the brand canon line verbatim somewhere in the "
            "hero. Do not paraphrase.\n"
            "- Include at least 1 receipt (number, timeline, named "
            "artifact).\n"
            "- Invite, not pitch. Soft CTA in the last sentence.\n"
            "- 30-50 words total. Count them.\n"
            "- Operator first-person voice unless system prompt says "
            "otherwise."
        )

    raise ValueError(
        f"unknown surface {surface!r}. "
        f"Valid: {', '.join(ALL_SURFACES)}"
    )
