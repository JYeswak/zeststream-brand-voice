# Step 2 — Press: define

> *Press in the Yuzu method: controlled pressure. Too little = waste. Too much = contamination. You're applying craftsmanship, not force.*

## What you're doing in this step

Writing the rules. You take the Peel outputs (raw corpus, cringe list, interview, claims list) and turn them into four machine-checkable files and one source-of-truth data file. After Press, anyone (human or LLM) can read the config and predict the verdict on a new piece of copy.

**Output:** `voice.yaml` + `WE_ARE.md` + `TONE_MATRIX.md` + `LANGUAGE_BANK.md` + brand-tagged entries in `data/capabilities-ground-truth.yaml`.

## Prerequisites

- All Peel outputs complete (see [01-peel-discover.md](01-peel-discover.md) §stop-conditions)
- `brands/<slug>/` directory exists, copied from `_template/`

## The work

### 1. Draft `voice.yaml` (90 min)

Open `brands/<slug>/voice.yaml` (copied from template). Fill the sections in this order:

**1a. Canon.** The one sentence from the founder interview that summarizes what the brand does. Usually needs 2–3 revisions to land. Also capture 1–2 approved variants (e.g. a shorter version for the `/about` opener).

**1b. Posture.** Is this brand first-person singular ("I"), first-person plural ("we"), second-person ("you"), third-person ("they") or mixed? Refer to the Peel pronoun analysis — go with the **actual** posture, not the aspirational one.

**1c. Three moves (optional but highly recommended).** What are the 3 mandatory elements on every conversion surface? Default: name a person, show a receipt, invite don't pitch. Adapt per brand.

**1d. Banned words.** Start with the universal consultant-tells list (enterprise, transformation, platform, handoff, artifact, leverage, etc. — see `brands/zeststream/voice.yaml` for a full set). Add the brand-specific cringe list from the Peel interview. Add any over-used words the brand itself is guilty of (from Peel cluster analysis).

**1e. Trademark rules.** First-use rendering for the brand name, any method/product trademarks. Example: `The Yuzu Method ®` on first use per asset. Rules are terse and enforceable.

**1f. Surfaces.** Sentence-max-words per surface type (hero/body/cta/email/post/meta). Paragraph-max-sentences. Register per surface. Use the zeststream `voice.yaml` as a reference calibration.

**1g. Rubric.** The 15-dim composite with thresholds (composite ≥95 ship, 85-94 regen, <85 block, any dim <9 block). Start with the default weights (0.15/0.20/0.25/0.40 for regex/rules/embed/llm). Adjust in Step 3 (Lock) after real data.

**1h. Invariants — never / always.** One-line rules the scorer enforces unconditionally. E.g. *never* use "Pour" as a verb (if you're using Yuzu method), *always* cite every number.

Do a final pass: does reading the file alone let someone predict a verdict? If no, add rules until yes.

### 2. Write `WE_ARE.md` (45 min)

The explicit posture table. 12+ rows "We Are" with evidence; 12+ rows "We Are Not" with reasons. Every row should be defensible against a specific Peel observation.

Template structure:

```markdown
## WE ARE
| # | We are… | Evidence / receipt |
|---|---------|-------------------|
| 1 | A solo operator | 14 years at X, left end of 2025, no team |
| 2 | A builder, not a slide-decker | 96 production workflows at domain.com |
...

## WE ARE NOT
| # | We are not… | Why |
|---|-------------|-----|
| 1 | A consulting firm | One person. "Firm" implies a team that doesn't exist. |
...
```

Close with **edge cases**: what about partners? What about client teams? What about using third-person in case studies? This is where most drift sneaks in — name the edges explicitly.

### 3. Write `TONE_MATRIX.md` (45 min)

Surface × audience × phase → register grid. Registers are descriptive adjectives (direct, inviting, specific, warm-operator, discovery-curious, build-confident, kaizen-calm, etc.).

Minimum 3 worked examples showing a specific coordinate (e.g. `hero × customer × peel → direct + inviting`), a "right" sample, a "wrong" sample, and why each.

This file is the answer to "what tone should I use?" — when the scorer flags `friction_calibrated` low, this file is where the fix lives.

### 4. Write `LANGUAGE_BANK.md` (45 min)

The mental-model-shifting phrase library from the Peel "Mental Model Shift Goals." 5 tiers:

- **Tier 1** — hero/homepage (highest leverage, use sparingly)
- **Tier 2** — body copy (systems-leverage language)
- **Tier 3** — CTAs and invites (low-friction)
- **Tier 4** — personal story / credibility
- **Tier 5** — anti-patterns to replace (find/replace table)

Each phrase: phrase text, mental-model shift attached, use context. This file is what writers (and LLMs) pull from when drafting — it's the seed corpus before exemplars exist.

### 5. Seed `capabilities-ground-truth.yaml` (60 min)

For each of the 10+ candidate claims from Peel:

- If source status = **Yes** → write an entry with `id`, `claim`, `canonical_phrasing`, `category`, `source.{type, location, timestamp}`. Pick `confidence` per `references/CONFIDENCE_SCORING.md`.
- If source status = **No** → **either** track down a real source right now, **or** add to an `OPEN_QUESTIONS.md` entry as Q-xxx so the founder decides later.
- If source status = **Unsure** → write the entry with `confidence: medium` and `stale_after_days: 30` to force re-verification soon.

The zeststream `capabilities-ground-truth.yaml` has 40+ entries to reference. Typical first-brand seed is 15–30.

**Critical:** also add the **PROHIBITED** entries — claims that must NEVER appear (e.g. "95% of clients" when no such metric exists, or competitor service offerings the brand doesn't actually do). These are the guardrails, not just suggestions.

### 6. Cross-check against Peel

Open the Voice Health Report. For each Mental Model Shift Goal:

- Does the canon address it?
- Does the banned-words list prevent its inverse?
- Does `LANGUAGE_BANK.md` contain phrases that achieve the shift?

If any goal isn't covered, add rules until it is. The point of Press is that every Peel finding has a mechanical countermeasure.

## Stop conditions

Done with Press when:

1. Reading `voice.yaml` alone predicts the rubric verdict on any sample copy.
2. Every Peel Mental Model Shift Goal has at least one rule + one banned word/phrase + one LANGUAGE_BANK phrase supporting it.
3. Every candidate claim from Peel is in the ground-truth YAML, in `OPEN_QUESTIONS.md`, or explicitly PROHIBITED.
4. `WE_ARE.md` has 12+ rows per column, each with evidence.
5. `TONE_MATRIX.md` has at least 3 worked examples you can walk through without looking.

## Anti-patterns

1. **Copying zeststream `voice.yaml` wholesale.** The algorithm is brand-agnostic; the config is not. Re-derive from this brand's Peel outputs.
2. **Banned-words list that's only the universal consultant-tells list.** Each brand has unique over-uses. Add them.
3. **Rubric with no brand-specific dimensions.** If this brand has a method (like Yuzu), a dim like `yuzu_phase_mapped` belongs in the rubric. If not, cut it.
4. **Skipping PROHIBITED claims.** The ones that *must not appear* are as important as the ones that may.
5. **Too many rules.** If `voice.yaml` has 50 banned phrases, nobody remembers them. Prune to the 20 that actually matter. Add back via trauma-to-rule promotion in Pour.

## What's next

[Step 3 — Lock: validate](03-lock-validate.md) expects:

- `brands/<slug>/voice.yaml` (fully filled)
- `brands/<slug>/WE_ARE.md`
- `brands/<slug>/TONE_MATRIX.md`
- `brands/<slug>/LANGUAGE_BANK.md`
- `data/capabilities-ground-truth.yaml` (with brand entries)
- 5 existing pages you'll dry-run the scorer on (from the scraped site)
