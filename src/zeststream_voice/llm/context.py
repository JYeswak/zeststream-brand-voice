"""Build an LLM system prompt from a brand's voice.yaml + exemplars.

Returns a structure optimised for Anthropic prompt caching: the large,
stable voice content goes into a cached block; the small, dynamic surface
slug + topic goes uncached. Callers pass the ``system`` field directly to
``LLMClient.generate()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from zeststream_voice._brands import BrandPaths, discover_brand, load_voice_yaml


VALID_SURFACES = {"x", "linkedin", "facebook", "instagram", "email", "page", "post", "meta", "blog", "hero", "body", "cta"}


@dataclass
class VoiceContext:
    """Packaged LLM context for a single brand + surface.

    ``system`` is a list of typed blocks ready for the Anthropic Messages
    API; the first (large) block carries ``cache_control`` so repeated calls
    within a session hit the prompt cache.
    """

    system: list[dict[str, Any]]
    surface: Optional[str]
    situation_key: Optional[str]
    exemplars_loaded: list[str] = field(default_factory=list)
    brand_slug: str = "zeststream"

    @property
    def cache_anchors(self) -> int:
        """How many blocks request caching. Useful for telemetry/tests."""
        return sum(1 for b in self.system if b.get("cache_control"))

    @property
    def cached_chunks(self) -> list[dict[str, Any]]:
        """The blocks that request caching (for inspection/tests)."""
        return [b for b in self.system if b.get("cache_control")]


def build_voice_context(
    brand_path: Optional[Path | str] = None,
    surface: Optional[str] = None,
    situation_key: Optional[str] = None,
    brand_slug: str = "zeststream",
    max_exemplars: int = 5,
) -> VoiceContext:
    """Assemble a cache-friendly system prompt from a brand folder.

    Parameters
    ----------
    brand_path:
        Absolute path to the brand folder (containing ``voice.yaml``). If
        ``None``, falls back to walk-up discovery via ``discover_brand``.
    surface:
        One of x/linkedin/facebook/instagram/email/page/post/meta/blog plus
        the legacy hero/body/cta buckets used by existing exemplars/.
    situation_key:
        Optional key into ``situation_playbooks`` (when that section lands
        in voice.yaml). Currently tolerated if absent.
    brand_slug:
        Brand identifier. Ignored if ``brand_path`` is passed.
    max_exemplars:
        Cap on how many exemplars to splice in.
    """
    paths: BrandPaths = discover_brand(
        slug=brand_slug,
        explicit_brand_path=Path(brand_path) if brand_path else None,
    )
    voice = load_voice_yaml(paths)

    cached_text = _render_voice_block(voice, paths=paths, surface=surface, max_exemplars=max_exemplars)
    exemplars_loaded = _list_exemplars(paths.brand_dir, surface=surface, max_n=max_exemplars)

    # Build dynamic (uncached) tail: surface + situation playbook (if present).
    dynamic_parts: list[str] = []
    if surface:
        dynamic_parts.append(f"ACTIVE SURFACE: {surface}")
    playbook = _situation_playbook(voice, surface=surface, key=situation_key)
    if playbook:
        dynamic_parts.append(f"SITUATION PLAYBOOK:\n{playbook}")

    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": cached_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if dynamic_parts:
        system_blocks.append({"type": "text", "text": "\n\n".join(dynamic_parts)})

    return VoiceContext(
        system=system_blocks,
        surface=surface,
        situation_key=situation_key,
        exemplars_loaded=exemplars_loaded,
        brand_slug=paths.slug,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_VOICE_KEYS = (
    "brand",
    "posture",
    "method",
    "canon",
    "banned_words",
    "banned_phrases",
    "three_moves",
    "attribution_rules",
    "trademarks",
    "rubric",
)


def _render_voice_block(
    voice: dict,
    paths: BrandPaths,
    surface: Optional[str],
    max_exemplars: int,
) -> str:
    """Render the large, stable, cacheable system prompt."""
    header = (
        "You write in a specific brand voice. The constants below are "
        "enforced by a downstream scorer — do not invent new rules, do not "
        "paraphrase the canon, do not use any banned word or phrase.\n"
    )
    sections: list[str] = [header.strip()]

    identity = voice.get("brand") or {}
    posture = voice.get("posture") or {}
    canon = voice.get("canon") or {}

    # Tight identity header — these four lines drive most of the voice.
    ident_lines = []
    if identity.get("name"):
        ident_lines.append(f"Brand: {identity['name']}")
    if identity.get("operator"):
        ident_lines.append(f"Operator: {identity['operator']}")
    banned_operators = identity.get("operator_variants_banned") or []
    if banned_operators:
        ident_lines.append(f"Never call the operator: {', '.join(banned_operators)}")
    if posture.get("voice"):
        ident_lines.append(f"Voice: {posture['voice']}")
    if ident_lines:
        sections.append("IDENTITY:\n" + "\n".join(ident_lines))

    if canon.get("primary"):
        canon_lines = [f'Primary (verbatim when used): "{canon["primary"]}"']
        for v in canon.get("variants_approved") or []:
            canon_lines.append(f'Variant OK: "{v}"')
        if canon.get("rule"):
            canon_lines.append(f"Rule: {canon['rule']}")
        sections.append("CANON:\n" + "\n".join(canon_lines))

    # Method, banned words, three moves, attribution — dump verbatim YAML so
    # the model sees the same structure the scorer enforces.
    passthrough = {k: voice[k] for k in _VOICE_KEYS if k in voice and k not in {"brand", "posture", "canon"}}
    if passthrough:
        sections.append("VOICE CONSTANTS (yaml):\n" + yaml.safe_dump(passthrough, sort_keys=False).rstrip())

    # Exemplars — few-shot priming from matching surface folder.
    exemplars_text = _load_exemplar_text(paths.brand_dir, surface=surface, max_n=max_exemplars)
    if exemplars_text:
        sections.append("EXEMPLARS (on-voice reference pieces — match their posture, do not copy):\n" + exemplars_text)

    sections.append(
        "OUTPUT RULES:\n"
        "- Write in the operator's first-person voice unless the brief says otherwise.\n"
        "- Every factual claim must already be grounded (numbers, names, timelines) — if you do not know, omit it, do not invent.\n"
        "- Do not hedge. Do not use banned words or phrases.\n"
        "- Composite target: 95+. No dimension below 9."
    )
    return "\n\n".join(sections)


def _list_exemplars(brand_dir: Path, surface: Optional[str], max_n: int) -> list[str]:
    """Return relative paths of exemplars we'd load, capped at ``max_n``."""
    found: list[Path] = []
    exemplars_root = brand_dir / "exemplars"
    if not exemplars_root.is_dir():
        return []

    surface_dirs: list[Path] = []
    if surface:
        sd = exemplars_root / surface
        if sd.is_dir():
            surface_dirs.append(sd)
        # Fallback: for social surfaces we often share "body" exemplars.
        if not surface_dirs:
            fallback = exemplars_root / "body"
            if fallback.is_dir():
                surface_dirs.append(fallback)
    else:
        # No surface: walk everything.
        surface_dirs = [p for p in exemplars_root.iterdir() if p.is_dir()]

    for sd in surface_dirs:
        for p in sorted(sd.glob("*.md")):
            found.append(p)
            if len(found) >= max_n:
                break
        if len(found) >= max_n:
            break

    return [str(p.relative_to(brand_dir)) for p in found[:max_n]]


def _load_exemplar_text(brand_dir: Path, surface: Optional[str], max_n: int) -> str:
    rels = _list_exemplars(brand_dir, surface, max_n)
    if not rels:
        return ""
    chunks: list[str] = []
    for rel in rels:
        p = brand_dir / rel
        try:
            body = p.read_text(encoding="utf-8")
        except Exception:
            continue
        chunks.append(f"--- {rel} ---\n{body.strip()}")
    return "\n\n".join(chunks)


def _situation_playbook(voice: dict, surface: Optional[str], key: Optional[str]) -> str:
    """Render a situation playbook entry if voice.yaml defines one.

    Schema tolerance: callers may ship either ``situation_playbooks`` (the
    spec-shape in 10-write-quadrant-vision.md) or nothing at all. Both are
    fine — this helper just returns "" when nothing matches.
    """
    playbooks = voice.get("situation_playbooks") or {}
    if not isinstance(playbooks, dict) or not playbooks:
        return ""

    entry: Any = None
    if key and key in playbooks:
        entry = playbooks[key]
    elif surface and surface in playbooks:
        entry = playbooks[surface]

    if entry is None:
        return ""
    if isinstance(entry, str):
        return entry
    # dict-shaped playbook → dump compact yaml so ordering is preserved
    return yaml.safe_dump(entry, sort_keys=False).rstrip()
