# Visual assets — Operator Yuzu mascot system

**Status: CANONICAL, locked 2026-04-20.** This directory holds the full visual identity for the zeststream-brand-voice repo and the ZestStream mascot character "Operator Yuzu." All assets below are production-approved; regenerate only by round-tripping through `character-bible.md` with the canonical character as the `--cref` anchor. Do not hand-edit, recolor, or substitute variants — the character bible names the banned forms.

| Asset | Path | Use |
|---|---|---|
| Canonical character | `yuzu_canonical.jpg` | `--cref` anchor for all future generations |
| GitHub avatar | `yuzu_avatar_square.jpg` | 1:1 repo avatar, social profile |
| Repo hero | `scenes/zeststream_brand_voice_hero.jpg` | README hero, GitHub social preview |
| PEEL template | `scenes/peel_phase_discovery.jpg` | Discovery / research / audit repos |
| PRESS template | `scenes/press_phase_workbench.jpg` | Build / tooling / transform repos |
| POUR template | `scenes/pour_phase_delivery.jpg` | Launch / delivery / ship repos |
| Explainer banner | `scenes/yuzu_method_explainer.jpg` | Yuzu Method explainer, /consult, about pages |

## Character specification

See [character-bible.md](character-bible.md) for the full 166-line spec: likeness rules, palette hex values, wardrobe constants, banned variants, scene patterns, and the generation workflow.

## Where this plugs in

- Repo-level framing: see the "Visual identity" section in [../README.md](../README.md).
- Voice scoring and grading of copy that references these assets: see [../skills/](../skills/) — the `brand-voice` skill loads brand configs and enforces the rendering rules for "The Yuzu Method ®" and "Peel. Press. Pour.™" on every outbound asset.
