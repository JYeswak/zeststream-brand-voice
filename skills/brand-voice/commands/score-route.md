---
description: Score a zeststream.ai route (or given text) against the 15-dim rubric
argument-hint: "<route path or pasted text>"
---

Score the content at $ARGUMENTS against the zeststream brand voice rubric.

**If $ARGUMENTS is a route path** (e.g. `/consult`, `/about`):
1. Fetch the served copy via WebFetch (respecting prod URL from `voice.yaml.brand.domain`).
2. Extract visible hero / body / cta / meta spans.

**If $ARGUMENTS is pasted text**:
1. Ask for surface, audience, phase if not provided inline.

**Scoring steps:**

1. **Layer 1 — Regex**: grep for `voice.yaml.banned_words` and `banned_phrases`. Count hits.
2. **Layer 2 — Rules**: check each of the 10 rules in `ALGORITHM.md §Layer-2`. Score 0/1 each.
3. **Layer 3 — Embedding (skipped if scorer not running)**: note `layer_scores.embedding: unknown` and reweight.
4. **Layer 4 — LLM Rubric**: mentally score each of 15 dimensions 0–10 per the rubric in `voice.yaml.rubric.dimensions`.
5. **Grounding pass**: extract claims, match against `capabilities-ground-truth.yaml`.
6. **Composite**: regex × 0.15 + rules × 0.20 + (embedding × 0.25 — skip) + llm × 0.40 (re-weighted to 0.15 + 0.27 + 0.53 if embedding skipped).
7. **Verdict**: ship / regen / block per `voice.yaml.rubric.thresholds`.

**Output format:**

```
ROUTE: /consult (or "pasted text")
SURFACE × AUDIENCE × PHASE: hero × customer × peel
COMPOSITE: 94 (regen)

DIMS (0–10):
  testable: 10    secure: 10       fun: 9
  valuable: 10    easy: 9          brand_voice: 9
  canon_present: 10    person_named: 10   receipt_shown: 9
  invite_not_pitch: 10   yuzu_phase_mapped: 10   plain_language: 8 ← LOW
  specificity: 9       rhythm: 9   friction_calibrated: 10

BANNED WORDS: []
CLAIMS UNGROUNDED: ["95% of clients"]  ← BLOCK
TRADEMARK ERRORS: []

REGEN HINTS:
- plain_language (8): "utilize" → "use" at line 3. See banned_phrases.
- claims_ungrounded: "95% of clients" has no ground-truth match. Rewrite or add entry.

VERDICT: block (claims_ungrounded non-empty)
```

**Also log** the scoring result to `.planning/scorecard-log.jsonl` (append-only JSONL row per `ALGORITHM.md §Logging contract`).
