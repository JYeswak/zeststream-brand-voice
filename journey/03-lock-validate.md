# Step 3 — Lock: validate

> Every rubric agrees with taste in theory. The rubric you actually built may not. Lock is where you find out before it matters.

## What you're doing in this step

Calibrating. You've written `voice.yaml`; now you run it on real copy, compare verdicts to your own judgment, and adjust thresholds until they match. You also hand-curate the first 20+ exemplars and catch the first trauma entries.

**Output:** a calibrated rubric + 20+ seeded exemplars + an initial trauma.jsonl + a `calibration.md` decision log.

## Prerequisites

- Full Press output (see [02-press-define.md](02-press-define.md) §stop-conditions)
- 5 existing pages from the scraped site (pick a mix: 1 hero, 2 body, 1 CTA, 1 about-style)
- Access to the scorer (or willingness to run the 4 layers mentally against each page)

## The work

### 1. Dry-run the rubric on 5 pages (45 min)

For each of the 5 pages, run the 4 layers:

**Layer 1 — Regex.** Grep for banned words. Check canon presence. Check trademark rendering.
**Layer 2 — Rules.** Check three moves present on conversion surfaces, first-person posture, attribution to sources, receipt present, phase naming correct.
**Layer 3 — Embedding.** If Qdrant isn't set up yet, skip — layer score becomes `unknown`, reweight remaining.
**Layer 4 — LLM rubric.** 15 dims × 0–10. If no scorer API yet, do this by hand: read the page, score each dim, justify.

For each page, write to `brands/<slug>/calibration.md`:

```markdown
## Page: /<route>  (surface=X, audience=Y, phase=Z)

layer_regex: NN (N banned words, canon present?, trademark errors?)
layer_rules: NN (M rules passed / 10)
layer_embedding: skipped (no Qdrant yet) | NN
layer_llm: NN (per-dim scores)
composite: NN
verdict: ship | regen | block
my_gut_verdict: ship | regen | block
agrees_with_gut: yes | no
notes: [where scorer disagreed with you]
```

### 2. Reconcile disagreements (45 min)

For every page where the scorer and your gut disagreed, figure out which one was wrong. Two options:

**Option A — scorer was right, your gut was miscalibrated.** The page you thought was fine actually violates a rule. Good — your gut now updates.

**Option B — your gut was right, scorer was miscalibrated.** More common. One of:
- Banned word too aggressive (false positive). Move to `banned_phrases` with more context, or loosen.
- Dim threshold too strict. Consider lowering `any_dim_below` from 9 to 8, OR clarify the dim definition.
- LLM rubric prompt misaligned. Rewrite the rubric description for that dim.

Log every reconciliation in `calibration.md`. Example:

```markdown
### Calibration #3 — 2026-05-02
Dim `plain_language` was flagging paragraphs as low that I read as fine.
Root cause: dim description said "no jargon," but this brand's audience IS
technical. Jargon paired with analogy is OK. Updated dim description in
voice.yaml to "jargon allowed if paired with analogy in same paragraph."
Rescored all 5 pages; agreement now 5/5.
```

### 3. Hand-curate 20+ exemplars (90 min)

From the scraped site + (if this is a new brand) first-draft-you-write copy, build the exemplar seed. One file per exemplar under `brands/<slug>/exemplars/<surface>/<slug>.md`.

YAML frontmatter:

```yaml
---
id: <slug>
surface: hero | body | cta | email | post | meta
audience: operator | candidate | customer | general
phase: peel | press | pour | na
source_url: <url or "hand-authored">
source_sha: <git commit SHA if from production>
composite: <0..100>
scored_at: <ISO ts>
promoted_at: <ISO ts>
dims: { ... 15-dim scores ... }
notes: |
  Why this exemplar is canonical. What it demonstrates.
  Reference for [which future surface types].
---
```

Body is the actual copy text.

**Quality bar:** every exemplar must score ≥95 composite with no dim <9. If a candidate doesn't hit that, **don't lower the bar** — fix the candidate or drop it.

**Distribution:** roughly 4 hero, 6 body, 3 cta, 3 email, 2 post, 2 meta. Adjust to match the brand's dominant surfaces.

### 4. Catch the first trauma entries (30 min)

As you work through steps 1–3, you'll find off-voice copy on the live site that you'd catch with the system. For each one, append to `brands/<slug>/trauma.jsonl`:

```json
{"ts": "2026-05-02T15:30:00Z", "text": "offending span here", "surface": "body", "composite": 68, "banned_words": ["platform"], "dims": {...}, "regen_hints": ["replace 'platform' with specific service names"], "recurrence_count": 1}
```

**This is the seed for R2-vicious-loop prevention and B2-learning-loop activation.** When the same trauma pattern recurs 3 times, the Pour step's trauma-to-rule promoter will auto-propose a new `voice.yaml` rule.

### 5. If the scorer is live, index exemplars into Qdrant (30 min)

Skip if you don't have Qdrant running yet. If you do:

```bash
# pseudo-command; adapt to your embedding script
for f in brands/<slug>/exemplars/**/*.md; do
  embed "$f" | qdrant-upsert \
    --collection brand_voice_exemplars_<slug> \
    --payload "surface=$(yq .surface $f),audience=$(yq .audience $f)"
done
```

Now Layer 3 works: new copy gets cosine-matched against these exemplars at write-time.

### 6. Decide the grandfather policy (15 min)

Existing live copy will score below 95 on first pass. It was written pre-system. Decide:

- **Grandfather** — existing copy stays live but is tagged "pre-system." New writes enforce. Existing pages re-scored on a 90-day cadence; anything <90 escalates.
- **Rewrite** — everything below 95 gets rewritten before new copy can ship. More painful, more consistent.

Log the decision in `calibration.md` with rationale. For new client brands, **grandfather is usually right**. For your own brand where the whole point is that the site represents the system, **rewrite is usually right**.

## Stop conditions

Done with Lock when:

1. On 5 representative pages, scorer verdict matches your gut verdict ≥4/5 times.
2. You have 20+ exemplars scoring ≥95 each, distributed across surfaces.
3. `trauma.jsonl` has at least 5 captured drift entries (it will grow naturally; don't fake them).
4. `calibration.md` documents every threshold/dim adjustment you made and why.
5. You can hand the `brands/<slug>/` directory to someone else and they'd reach the same verdicts.

## Anti-patterns

1. **Claiming "calibration done" when you only ran 2 pages.** Minimum 5, and they need to be diverse (hero / body / cta / about / long-form). Low-diversity calibration calibrates poorly.
2. **Lowering thresholds to match broken live copy.** The point of the system is that the live copy is wrong. Don't move the bar; fix the copy.
3. **Skipping exemplar curation because "the scorer can generate them."** No. First 20 exemplars must be hand-curated so the embedding RAG has a clean seed. Auto-promotion starts in Pour, not Lock.
4. **Writing exemplars ad-hoc without YAML frontmatter.** The frontmatter is what makes them queryable. Skip it and you have a notes file, not an exemplar corpus.
5. **Not logging reconciliations.** Six months from now when you wonder why `plain_language` means something specific, `calibration.md` is the answer. Don't skip.

## What's next

[Step 4 — Pour: activate](04-pour-activate.md) expects:

- `brands/<slug>/voice.yaml` — calibrated
- 20+ exemplars in `brands/<slug>/exemplars/`
- `trauma.jsonl` with initial drift captures
- `calibration.md` with decisions documented
- Grandfather-vs-rewrite policy chosen
