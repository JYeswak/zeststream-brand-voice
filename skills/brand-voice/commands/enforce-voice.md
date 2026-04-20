---
description: Apply ZestStream brand voice to a content request or rewrite
argument-hint: "<content to write or rewrite>"
---

Load the zeststream-brand-voice skill. Apply voice constants + tone matrix + grounding pass to the content request provided in $ARGUMENTS.

**Load sequence (stop as soon as found):**

1. **Session context** — if guidelines were loaded or generated earlier in this conversation, use them directly.
2. **Skill files** — read:
   - `~/.claude/skills/zeststream-brand-voice/SKILL.md`
   - `~/.claude/skills/zeststream-brand-voice/brands/zeststream/voice.yaml`
   - `~/.claude/skills/zeststream-brand-voice/brands/zeststream/WE_ARE.md`
   - `~/.claude/skills/zeststream-brand-voice/brands/zeststream/TONE_MATRIX.md` (register)
   - `~/.claude/skills/zeststream-brand-voice/brands/zeststream/LANGUAGE_BANK.md` (phrase library)
   - `~/.claude/skills/zeststream-brand-voice/brands/zeststream/JOURNEY_MAP.md` (stage register)
   - `~/.claude/skills/zeststream-brand-voice/data/capabilities-ground-truth.yaml` (claim bank)
3. **Settings** — if `brands/zeststream/settings.local.md` exists, apply strictness + enforcement knobs.

**Enforcement workflow:**

1. **Analyze the content request**: surface (hero / body / cta / email / post / meta), audience (operator / candidate / customer / general), phase (peel / press / pour / na), journey stage (awareness / consideration / decision / onboarding / advocacy).
2. **Pull register** from TONE_MATRIX.md for that coordinate.
3. **Pull starter phrases** from LANGUAGE_BANK.md matching the tier for this surface.
4. **Draft**. Keep sentence caps from `voice.yaml.surfaces.<surface>`.
5. **Apply the 5-step loop** (LOAD → WRITE → GATE → GROUND → LOG) from SKILL.md.
6. **Self-score** mentally against the 15-dim rubric. Any dim <9 or composite <95 → regen.
7. **Grounding pass**: every factual claim must match `capabilities-ground-truth.yaml` or be rewritten to omit.
8. **Banned-word grep**: reject if any `voice.yaml.banned_words` match.
9. **Trademark check**: The Yuzu Method ® on first use, Peel. Press. Pour.™ exact.
10. **Output the content + a brief "Voice decisions" note** listing: coordinate used, register applied, exemplars drawn from, any Medium-confidence claims flagged.

**If the request conflicts with guidelines:**
- Explain the conflict
- Recommend (follow strict / adapt / override)
- Default: adapt with explanation

**If a claim has no ground-truth match:**
- STOP. Quote the offending span.
- Offer: "Add entry to `capabilities-ground-truth.yaml` with evidence, OR I'll rewrite to omit."
- Never silently regenerate a hallucinated claim.

Log the ship to `.planning/scorecard-log.jsonl` (when in zesttube repo).
