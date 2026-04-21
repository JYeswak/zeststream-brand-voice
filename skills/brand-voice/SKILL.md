---
name: zeststream-brand-voice
description: Use when writing, reviewing, or grading any user-visible copy for zeststream.ai (or a client brand registered in brands/). This skill is the Meadows #6 information-flow intervention for brand voice — it brings voice constants, banned-words, approved-claims bank, and the 15-dim rubric to the point of writing. TRIGGER when writing any outbound copy (website pages, emails, LinkedIn posts, proposals, CTAs, meta descriptions) for a registered brand, when grading existing routes against the voice rubric, when auditing a new client site, or when asked to "write in brand voice". SKIP for internal code comments, commit messages, bead descriptions, or private notes — those are not brand voice surfaces.
---

# ZestStream Brand Voice — Enforcement Skill

> *"I help SMB owners buy their time back."* — Canon line. This skill exists so every sentence on zeststream.ai carries that weight without drifting.

## What this skill is

A Meadows-style voice **system** — not a style guide PDF. Stocks, flows, feedback loops, leverage points. Written once, scored every tick, promoted when proven, demoted when it drifts.

It enforces three things at the moment of writing:

1. **Voice constants** — canon line, banned words, three moves, first-person operator posture. Machine-checkable. Auto-reject if violated.
2. **Claims grounding** — every factual claim must map to a ground-truth entry in `data/capabilities-ground-truth.yaml`. This is the 2026-04-19 pivot's durable fix: stop on-voice hallucinated claims.
3. **15-dim rubric scoring** — hybrid (regex 0.15 + rules 0.20 + embedding 0.25 + LLM rubric 0.40). Ship threshold ≥95 composite, no dim <9.

## Which brand am I writing for?

Check `brands/` for the brand slug the user or repo references.

- **zeststream.ai / ZestStream / Joshua Nowak / The Gap** → `brands/zeststream/`
- **Client brands** → register under `brands/<slug>/` using `brands/_template/` as the starting shape.

If no brand config exists yet, run the **discover** flow in `references/DISCOVER.md` before writing any new copy. Meadows principle 1: *"Get the beat of the system before you disturb it."*

## The 5-step loop (every time you write or grade)

```
1. LOAD      — brands/<slug>/voice.yaml + capabilities-ground-truth.yaml + exemplars/
2. WRITE     — draft with voice constants pre-loaded into context (prompt injection)
3. GATE      — 4-layer validation (banned / rules / embed / LLM). See ALGORITHM.md.
4. GROUND    — every factual claim maps to a ground-truth entry, or reject
5. LOG       — append to .planning/scorecard-log.jsonl; promote to exemplars if ≥98
```

Each layer is independent. A claim that passes regex but fails grounding is still rejected. Single-gate validation is an anti-pattern — see `references/ANTI_PATTERNS.md`.

## Core files (read these when the skill fires)

| File | Purpose | When to read |
|------|---------|--------------|
| `references/METHODOLOGY.md` | Meadows stocks/flows/loops + iceberg + 12 leverage points applied to voice | Once per session. Informs every decision. |
| `references/ALGORITHM.md` | 4-pass scorer (regex → rules → embedding → LLM rubric) spec + weights + thresholds | When scoring or regenerating copy. |
| `references/DISCOVER.md` | Scrape + cluster + voice-inference workflow for a new client brand | Only when bootstrapping a new brand. |
| `references/ANTI_PATTERNS.md` | The 12 failure modes this skill exists to prevent | Before shipping any copy. |
| `references/GROUNDING.md` | Claim-extraction and ground-truth matching. The 2026-04-19 pivot's permanent fix. | Any time copy makes a factual claim. |
| `brands/<slug>/voice.yaml` | Machine-checkable constants: canon, banned words, three moves, rubric weights, thresholds | Always. This is the enforceable core. |
| `brands/<slug>/WE_ARE.md` | We Are / We Are Not table. Explicit posture. | When writing about identity, positioning, or competitive framing. |
| `brands/<slug>/TONE_MATRIX.md` | Surface × audience × phase → register mapping | When choosing tone for a specific page. |
| `data/capabilities-ground-truth.yaml` | Every approved claim, one entry per line. RAG source for grounding. | Every time copy makes a factual claim. |

## Hard rules (auto-reject, no negotiation)

1. **Canon missing on a conversion page** → reject. Every top-level route on zeststream.ai carries the canon line verbatim at least once.
2. **Banned word in output** → reject. See `brands/<slug>/voice.yaml` banned_words list. Grep pre-commit.
3. **Ungrounded factual claim** → reject. If a number, duration, or capability appears, it must match an entry in `capabilities-ground-truth.yaml`. No "roughly" no "approximately". Cite or omit.
4. **Third-person corporate voice** (`"we"`, `"our team"`, `"ZestStream delivers"`) → reject on zeststream brand. First-person singular always.
5. **Trademark rendering wrong** → reject. First use per asset: `The Yuzu Method ®`. Motto: `Peel. Press. Pour.™`. Exactly.
6. **Testimonial without named client, metric, or repo** → reject. "Receipts over testimonials" is the floor.
7. **Enemy framing or doomer framing about AI** → reject. Partnership frame only.
8. **Jeff-Emanuel's work attributed to Joshua** (NTM, Agent Mail, beads, CASS) → reject. Cite Jeff where used.

## The four tests (steal from jgerton, applied per draft)

Before shipping any sentence, it must pass:

- **Swap test** — can a competitor's name swap in without the sentence breaking? If yes, it's too generic. Rewrite.
- **Specificity test** — does it name actual tools, numbers, benchmarks, or a real client? If no, rewrite.
- **Differentiation test** — does the claim tie to something only Joshua/this-brand does? If no, cut it.
- **Business-type test** — does the register match the audience (operator, candidate, customer, general)? If no, re-register from `TONE_MATRIX.md`.

## Three moves (mandatory on every conversion surface)

1. **Name a specific person** — Joshua (this brand) or the named operator in client brands. Never a faceless "we."
2. **Show a receipt** — a number, a repo link, a benchmark, a workflow count, a SHA, a timestamped log line.
3. **Invite, don't pitch** — end with a low-friction invitation (Peel session, map call, DM link). Never "Contact sales."

If a section can't carry all three, shrink the section until it can.

## Scoring & ship threshold

- **Composite ≥95** — ship.
- **Composite 85–94** — regen with named fix hints.
- **Composite <85 OR any banned word** — block. Do not ship.
- **No dim <9** — even a 96 composite blocks if any single dim falls below 9.

Full rubric + weights in `references/ALGORITHM.md`. Verdict log at `.planning/scorecard-log.jsonl`.

## Grounding — the claim-citation protocol

Every factual claim in output copy is extracted by the grounding step and matched against `data/capabilities-ground-truth.yaml`. Claims that can't be matched are rejected with the specific offending span quoted back.

This is the Meadows #6 intervention for the specific failure that drove the 2026-04-19 pivot: voice was on-register but claims were hallucinated ("95% Deployment Rate," "10,000+ Hours Removed"). The grounding pass closes that gap structurally, not via writer vigilance.

See `references/GROUNDING.md` for the claim-extraction regex, the ground-truth YAML schema, and the cite-or-omit rule.

## Anti-patterns (why this skill exists)

See `references/ANTI_PATTERNS.md`. Top 3 to internalize:

1. **Hardcoded banned-words lists without embedding backstop** — writers route around them ("empower" → "give power to"). Fix: lexical + semantic dual-gate.
2. **Single-gate validation** — checklists are theater. Fix: 4 independent layers, any one rejects.
3. **Grounding-as-aspiration** — "we should cite claims" without a mechanical check. Fix: claim-extraction is a gate, not a suggestion.

## Extending to a new brand

```
~/.claude/skills/zeststream-brand-voice/
└── brands/
    ├── _template/         # copy this to start
    ├── zeststream/        # live
    ├── blackfoot/         # future
    ├── alps/              # future
    └── terratitle/        # future
```

For a new brand:
1. Copy `brands/_template/` → `brands/<slug>/`
2. Run the **discover flow** in `references/DISCOVER.md` (scrape site, cluster phrasings, infer existing cadence, interview founder)
3. Fill `voice.yaml` + `WE_ARE.md` + `TONE_MATRIX.md`
4. Build `exemplars/` by hand (20–50 annotated before/after pairs, per surface type)
5. Populate the brand-specific `capabilities-ground-truth.yaml` entries
6. Dry-run score 5 existing pages, calibrate thresholds
7. Ship

The skill stays brand-agnostic. The config per brand is the only thing that changes.

## Meadows one-liner

Voice is a **stock** (S.LIVE quality × n_pages), fed by **flows** (writing_rate, review_rate), balanced by **loops** (voice-gate B1, trauma-capture B2, audit B3), eroded by **drift** (S.DRIFT), and protected by this skill at the highest-leverage point available to a writer: **#6 information flow at the moment of decision**.

Everything else in this skill is an implementation detail of that one sentence.
