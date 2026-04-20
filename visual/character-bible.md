# Yuzu Character Bible

**Status:** CANONICAL (locked session 15, 2026-04-20)
**Canonical reference:** `yuzu_canonical.jpg` (this directory)
**Voice:** Operator Yuzu — senior, competent, slightly weathered, kind

---

## Identity

**Name:** Yuzu
**Archetype:** anthropomorphic yuzu citrus fruit — the ZestStream operator mascot
**Role across ecosystem:** Yuzu appears in every public-facing ZestStream-authored repo hero image, social preview card, and brand-associated illustration. Yuzu IS the brand signal.

---

## Form

- Head = a yuzu citrus fruit (spherical, slightly bumpy, yellow-green peel with subsurface scattering — glows softly from within)
- One (and only one) small green leaf sprouts from a short stem on top of the head
- Small humanoid body (cartoon proportions)
- Head is approximately 40% of the total figure height
- Body color matches peel (slightly desaturated yellow-green), visible on arms/hands when sleeves are rolled

---

## Face (the crucial lock)

**Canonical expression: "Operator Yuzu"**
- Medium-sized expressive emerald-green eyes with small white highlights (NOT ink-black, NOT wide anime with sparkle chaos)
- Warm competent smile — subtle, quietly confident
- Slight laugh lines / eye softening — senior-operator, not fresh apprentice
- Gentle eyebrows, often slightly raised asymmetrically (thoughtful, engaged)

**BANNED face variants (previous drift in generations):**
- ❌ Big chibi open smile with visible teeth
- ❌ Blushing pink cheeks (too kawaii)
- ❌ Wide anime sparkle-eyes with excessive highlights
- ❌ Stern or angry expression (Yuzu is kind)
- ❌ Eyes closed / "cute winking" (loses the competent read)

If a generation shows any of the banned variants, it is off-canon. Regenerate.

---

## Wardrobe (consistent across all scenes)

- **Shirt:** cream / off-white henley, rolled to elbows — always visible under apron
- **Apron:** canvas natural tone, full-body apron with small tool pockets. Mild working wear (not dirty, not crisp). Occasional small yuzu-icon embroidery on a pocket is permitted but not required
- **Accessory (signature):** wood-handled clipboard under one arm (neutral pose) OR held/in use (active pose) — always has visible receipt / score pages on it
- Barefoot or simple shoes — scene-dependent, low importance

---

## Palette (locked hex values)

| Role | Color | Hex |
|------|-------|-----|
| Primary (peel, body) | Yuzu yellow-green | `#CEE741` (and warmer variations) |
| Leaf/stem | Sage / deep green | `#6B8E23` |
| Clothing | Cream / canvas natural | `#F5F0E1` |
| Text/structural | Deep ink black | `#1A1B1F` |
| Scene warmth | Amber / golden hour | `#E8A94B` |
| Environment plants | Forest sage | `#5B7553` |

**NEVER:** corporate saas blue, pure magenta, cyberpunk cyan, neon purple gradient, Jeff's blue-robot colors (#4169E1-ish)

---

## Rendering style (locked)

- 3D Pixar / DreamWorks CG illustration
- Subsurface scattering on the yuzu peel — soft inner glow
- Soft global illumination, warm rim lighting
- Shallow depth of field — environment softly blurred, Yuzu sharp
- Never: flat vector, photographic, painterly, pixel art, cyberpunk neon, corporate gradient

---

## Scene pattern (ties mascot to Yuzu Method trademark)

Yuzu always does the thing the repo/tool does. The work IS the image.

**PEEL phase scenes** (discovery, research, audit, learn):
- Setting: greenhouse, kitchen workbench, forest edge
- Light: early morning / dawn
- Activity: peeling, inspecting with magnifier, reading a scroll, examining receipts
- Reference: `scenes/peel_phase_discovery.jpg`

**PRESS phase scenes** (build, construct, transform):
- Setting: workshop, lab, workbench with tool pegboard
- Light: midday, warm workshop
- Activity: operating a press/tool, assembling, stamping receipts
- Reference: `scenes/press_phase_workbench.jpg`

**POUR phase scenes** (deliver, ship, complete):
- Setting: finish table, barn doorway, counter
- Light: golden hour
- Activity: pouring bright yuzu-green liquid into a glass, stamping "SHIPPED", presenting a receipt
- Reference: `scenes/pour_phase_delivery.jpg`

**Explainer / banner scenes** (Yuzu Method overview, /consult page hero):
- Setting: workshop with all three phases visible
- Three Yuzus, each in one phase, left-to-right PEEL → PRESS → POUR
- Reference: `scenes/yuzu_method_explainer.jpg`

**Avatar / square crop** (GitHub profile, social avatar):
- Setting: gradient studio background, head-and-shoulders portrait
- Reference: `yuzu_avatar_square.jpg`

---

## Generation workflow (replicable)

**Step 1 — Use canonical as `--cref` anchor**
Any tool that supports character reference (Midjourney `--cref`, Leonardo Character Reference, Flux IP-Adapter, Grok Imagine edit-chain) should use `yuzu_canonical.jpg` as the locked reference.

**Step 2 — Standard prompt template**
```
[Operator Yuzu character — yuzu citrus fruit head with ONE green leaf,
emerald-green eyes with quiet competent smile, cream henley with rolled
sleeves under canvas apron, wood-handled clipboard]. Scene: [repo-specific
scene]. In the scene: [tool outputs as floating 3D objects or monitors].
3D Pixar-quality CG, subsurface scattering on the peel, [PEEL morning
dawn | PRESS midday workshop | POUR golden hour] lighting. Palette: yuzu
yellow-green #CEE741, cream, warm amber, sage green, deep ink black.
16:9 aspect ratio.

--ar 16:9 --stylize 200 --v 6 --style raw --cref [canonical_url] --cw 100
```
(The `--cref` / `--cw` flags are Midjourney-specific. Use equivalent character-reference inputs for other tools.)

**Step 3 — Output surfaces**
- `yuzu_[repo-slug]_hero.jpg` — 16:9 for repo README + GitHub social preview
- `yuzu_[repo-slug]_avatar.jpg` — 1:1 center-crop for GitHub repo avatar
- Save both to repo root

**Step 4 — Validation (3-pane consensus before shipping)**
Every new generation goes through STEP 0 regex-equivalent visual check:
- ✅ ONE leaf on head (not two or three)
- ✅ Emerald-green eyes (not black, not blue)
- ✅ Canvas apron + cream henley + rolled sleeves
- ✅ Operator expression (not chibi-cheerful)
- ✅ Palette compliance
- ✅ 3D Pixar rendering (not flat / photo / neon)
- ❌ Any drift = reject, regenerate

---

## What's saved in this directory

```
visual/
├── character-bible.md              ← this file (the spec)
├── yuzu_canonical.jpg              ← CANONICAL reference (use for --cref)
├── yuzu_avatar_square.jpg          ← GitHub avatar, social profile
└── scenes/
    ├── zeststream_brand_voice_hero.jpg  ← for zeststream-brand-voice repo
    ├── peel_phase_discovery.jpg         ← PEEL template
    ├── press_phase_workbench.jpg        ← PRESS template
    ├── pour_phase_delivery.jpg          ← POUR template
    └── yuzu_method_explainer.jpg        ← Yuzu Method banner
```

All 7 images generated via Grok Imagine, session 15, 2026-04-20.
Canonical selected from candidate set of 10 via 3-way consensus (operator vibe, pose, clipboard legibility, background cleanliness).
