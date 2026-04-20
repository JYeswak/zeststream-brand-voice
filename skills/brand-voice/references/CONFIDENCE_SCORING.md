# CONFIDENCE_SCORING — assigning H/M/L per section

Pattern ported from anthropics/knowledge-work-plugins `guideline-generation/references/confidence-scoring.md`. Adapted for this skill's 4-layer scorer and grounding pass.

Every major section of `voice.yaml` and every entry in `capabilities-ground-truth.yaml` carries an implicit confidence level. This doc tells you how to assign it and what to do when it's low.

---

## The three levels

| Level | Criteria | Action |
|-------|----------|--------|
| **High** | 3+ corroborating sources (docs / benchmarks / client-confirmed) OR direct measurement with reproducible method | Use verbatim. Safe to promote to exemplars. |
| **Medium** | 1–2 sources OR inferred from strong pattern (e.g. repeated phrasing across 2 artifacts) | Use but flag with `confidence: medium` in the entry. Re-verify before using in high-stakes surfaces (proposals, case studies). |
| **Low** | Single source, inferred-only, or conflicting data | Do NOT ship in user-visible copy without Joshua review. File as an `OPEN_QUESTIONS.md` entry. |

---

## Confidence per `voice.yaml` section

Every block in `voice.yaml` implicitly carries confidence. Explicit annotations live in trailing comments. Examples:

- `canon.primary` — **High** (Joshua wrote it, used in production since session 10)
- `banned_words` (consolidated list) — **High** (derived from 3 source docs + session-10 extraction)
- `banned_words` (new additions from trauma) — **Medium** until 48hr + 3 applications
- `posture.voice: "first-person singular"` — **High** (explicit in `capabilities-brief.md`)
- `method.phases.press.duration` — **Medium** (one authoritative source says Weeks 2–8, another says 2–6 — resolved via Q-003-style reconciliation)
- `trademarks.yuzu_method.first_use_per_asset` — **High** (authoritative in `~/Developer/zeststream-v2-fresh/.agents/THE-YUZU-METHOD.md`)

---

## Confidence per `capabilities-ground-truth.yaml` entry

Each entry's `source.type` implies a confidence:

| source.type | Default confidence |
|-------------|---------------------|
| `benchmark` | High (if reproducible command documented) |
| `api_pull` | High (stale_after_days honored) |
| `repo_link` | High (if commit SHA pinned) |
| `timestamped_log` | High (if log location verifiable) |
| `client_authorized` | High |
| `vendor_public_pricing` | Medium (vendor pricing changes; re-verify per stale_after_days) |
| `commitment` | Medium (Joshua's stated capability; receipt may still need landing) |

**Rule:** Medium-confidence entries should have `stale_after_days` set lower than High-confidence entries. Stale warnings escalate to blocks if aged >90 days without refresh.

---

## How to use during scoring

### Layer 2 (Rules) integration

When the scorer encounters a factual claim, it checks `capabilities-ground-truth.yaml`:

1. If match found with `confidence: high` → grounded, ship-eligible
2. If match found with `confidence: medium` → grounded, but add `claims_medium_confidence[]` to `ScoreResult` and annotate in the rejection if any other dim fails
3. If match found with `confidence: low` → block with message "Claim X matched a low-confidence entry. Please have Joshua re-verify before ship."
4. If no match → block (same as before)

### Layer 4 (LLM Rubric) integration

The rubric prompt now includes:

> "For each claim made in the copy, assess whether the grounding is High/Medium/Low confidence. If Medium or Low, annotate in the output. If the content depends on Medium-confidence claims and the surface is high-stakes (proposal, case study, /consult), recommend additional verification."

---

## Updating confidence

When new evidence arrives:

- Adding a second corroborating source → bump Medium → High
- A benchmark re-runs and confirms → bump to High and reset `stale_after_days`
- A claim fails in production (e.g. a quoted client disputes it) → bump down to Low + trauma entry
- A vendor updates pricing → touch the entry's `timestamp`, bump confidence if unchanged from previous verification

Never silently elevate confidence. All bumps should have a commit message explaining the new evidence.

---

## The open-question connection

Low-confidence entries and `OPEN_QUESTIONS.md` entries are two views of the same problem:

- **Low confidence** = we have *some* evidence but it's insufficient
- **Open question** = we have *conflicting or missing* evidence and need a decision

When a Low-confidence entry sits for >30 days without evidence escalation, auto-promote it to an `OPEN_QUESTIONS.md` entry (Q-xxx) so Joshua sees it as a pending decision, not a quiet risk.

---

## Meadows connection

Confidence scoring is an information-flow (#6) intervention for the *meta-system*: it tells writers "the system is uncertain here, slow down." Without it, Medium and Low claims ship at the same speed as High, and drift compounds. With it, uncertainty surfaces at write-time.

The rule-of-thumb: **if a claim feels obvious, it's probably High. If it requires a hedge in your head ("I think we've said this before"), it's Medium. If you'd want to double-check, it's Low — and you should double-check.**
