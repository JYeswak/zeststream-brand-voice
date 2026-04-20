# ALGORITHM — the 4-pass hybrid scorer

> Multi-layer defense: any single layer rejects. Single-gate validation is an anti-pattern (see ANTI_PATTERNS.md §3).

## Inputs

```
score_copy(
  text: str,
  brand_slug: str,            # e.g. "zeststream"
  surface: str,               # one of: hero|body|cta|email|post|meta|other
  audience: str = "general",  # one of: operator|candidate|customer|general
  phase: str = "na",          # one of: peel|press|pour|na
  route: str = None,          # e.g. "/consult" (optional, for logging)
) -> ScoreResult
```

## Outputs

```yaml
ScoreResult:
  composite: int  # 0..100
  verdict: ship | regen | block
  dims:
    testable: int  # 0..10
    secure: int
    fun: int
    valuable: int
    easy: int
    brand_voice: int
    canon_present: int
    person_named: int
    receipt_shown: int
    invite_not_pitch: int
    yuzu_phase_mapped: int
    plain_language: int
    specificity: int
    rhythm: int
    friction_calibrated: int
  banned_words: [str]         # matches found
  claims_ungrounded: [str]    # claims that didn't resolve to ground-truth
  trademark_errors: [str]     # e.g. "missing ® after 'The Yuzu Method'"
  regen_hints: [str]          # actionable fixes for each failed dim
  layer_scores:
    regex: int
    rules: int
    embedding: int
    llm_rubric: int
  cached: bool
  latency_ms: int
```

---

## Layer 1 — REGEX (weight 0.15)

Fast, deterministic, no LLM. Runs first, fails fast.

**Checks:**
1. **Banned words** — grep from `voice.yaml.banned_words` + `banned_phrases`. Case-insensitive, word-boundary anchored. Any match → layer score 0, block verdict, `banned_words` populated.
2. **Canon line present** — regex match `voice.yaml.canon.primary` on top-level routes (see route rules in `brand-config.yaml`).
3. **Trademark rendering** — 
   - `The Yuzu Method ®` on first use per asset
   - `Peel. Press. Pour.™` exact
   - `Peel|Press|Pour` as standalone phase names OK after first full motto use
   - First use of `Josh Nowak` full (subsequent "Josh" OK)
4. **Forbidden pronouns** — for ZestStream brand: `we|our|our team|ZestStream delivers`. Match → block.
5. **Sentence-length cap** — per `voice.yaml.surfaces.<surface>.sentence_max_words`. Violating sentences flagged, dim `rhythm` drops 2 per violation.
6. **Vague quantifiers** — `roughly|approximately|about \d+%|many clients|some users`. Match → block (cite-or-omit rule).
7. **Em-dash dramatic pause** — `\s—\s` in body copy (not in lists). Drops dim `rhythm` by 2.
8. **Three-part rhythmic lists** — `\b\w+, \w+,? and \w+\b` (approx). Drops dim `rhythm` by 2.

**Layer score:** `100 - (2 × violations)`, clamped [0, 100]. Any banned_word → 0.

**Performance budget:** <10ms for 2KB text.

---

## Layer 2 — RULES (weight 0.20)

Boolean checks against `voice.yaml` constants + `WE_ARE.md` posture. Still no LLM.

**Checks:**
1. **Three moves present on conversion surfaces** — for hero/cta surfaces, all three (name_person, show_receipt, invite_not_pitch) must be detectable.
2. **First-person operator** — regex confirms `\bI\b` present; no forbidden pronouns.
3. **Jeff/Meadows attribution** — if text mentions NTM, Agent Mail, beads, CASS, bv, bd, br → must cite Jeff Emanuel. If mentions leverage points, iceberg, stocks-and-flows, systems thinking → must cite Meadows.
4. **Phase naming** — if surface ∈ {hero, cta, body} AND route is a conversion route → at least one of `Peel|Press|Pour` must appear, mapped to its correct role (no "Pour the workflow" verb use).
5. **Receipt present** — regex matches number+unit, repo link, SHA, or explicit capability verb (built|rebuilt|tuned|deployed|shipped|wired) — per `voice.yaml.claims.extraction.patterns`.
6. **Word cap per route** — total word count ≤ `voice.yaml.word_caps_per_route[route]`.
7. **Japanese-philosophy mapping** — if Peel/Press/Pour mentioned with 3 Mus/Monozukuri/Kaizen, mapping must be Peel=3 Mus, Press=Monozukuri, Pour=Kaizen. Swap = hard reject.
8. **Phase/Gate conflation** — PEEL/PRESS/POUR never treated as TESTABLE/SECURE/FUN/VALUABLE/EASY. If text lists phase names as "gates" or vice versa → reject.
9. **Orphan quantitative claim** — BlackPond Pillar 6. Every number must attach to a source, a client, or a benchmark timestamp.
10. **Apocalyptic framing** — `\b(AI (will replace|is replacing|will destroy)|doom|apocalyp\w+|the end of|nobody will)\b` → reject.

**Layer score:** weighted pass/fail on each rule; 100 if all pass, −8 per fail (max 10 rules × 8 = 80 penalty floor at 20).

---

## Layer 3 — EMBEDDING (weight 0.25)

Semantic similarity to approved exemplars + distance from known trauma.

**Setup:**
- Qdrant on `:6433`, volume `qdrant_ks_data`
- Collection: `brand_voice_exemplars_<brand_slug>` (cosine, 768-dim, nomic-embed-text via Ollama local)
- Payload: `{id, surface, audience, phase, composite, promoted_at, source_url}`

**Checks:**
1. **Nearest exemplar** — cosine similarity to top-K=5 exemplars matching the target surface. `score = 100 × mean(top-k cosine)`, clamped.
2. **Nearest trauma** — cosine to top-K=3 entries in `trauma.jsonl`. If similarity ≥0.85 → dim `brand_voice` drops by 3 and trauma hit logged.
3. **Drift detection** — embedding distance to prior exemplars of same surface. If copy's embedding is >0.3 cosine distance from cluster centroid → flag `drift`, layer score −20.

**Fallback:** if Qdrant unreachable, layer returns `unknown` and scorer drops this layer, reweights remaining [0.15, 0.20, 0.40] → [0.20, 0.27, 0.53]. Logged.

**Performance budget:** p50 <150ms, p95 <400ms.

---

## Layer 4 — LLM RUBRIC (weight 0.40)

The judgment layer. Sonnet 4.6 primary (voice-sensitive tasks); Grok 4.1-fast-reasoning fallback (40× cheaper, used for bulk/probe).

**Model config:**
- Primary: `claude-sonnet-4-6` (T=0, max_tokens=2000)
- Bulk/probe: `grok-4-1-fast-reasoning` (T=0, max_tokens=2000)
- 3-attempt retry on JSON parse fail → return `composite=degraded, verdict=block` (fail-loud per Meadows #6)

**Caching:** LRU keyed on `sha256(text)+surface+audience+phase`. 1000 entries, 24h TTL.

**Prompt contract:** see `references/PROMPTS.md` (bundled). Prompt injects:
1. The full `voice.yaml` constants
2. The `WE_ARE.md` content
3. Top-5 relevant exemplars retrieved from Qdrant
4. The 8-criterion Yuzu-aware sub-rubric (inherited from brand-voice-rubric-v2.md)
5. The text to score
6. JSON-output instruction with schema

**Sub-rubric inside `brand_voice` dim (8 criteria, ALL must pass):**
1. Mission-aligned (names the gap correctly)
2. Partnership-framed (no enemy framing)
3. Attributed (Jeff/Meadows/OSS properly credited)
4. Operator-language (jargon paired with analogy)
5. Honest-tier (no frontier novelty claim, no beginner claim)
6. Demo-proof (no trust-me assertion)
7. Soft CTA (no email gate / course pitch)
8. Yuzu-Method-mapped (phases named, gates not conflated, TM rendered)

**Dim scoring:** LLM returns 0–10 per dim. No partial dims — the prompt forces explicit integer.

---

## Compositing

```python
composite = round(
    0.15 * layer_regex_score +
    0.20 * layer_rules_score +
    0.25 * layer_embedding_score +
    0.40 * layer_llm_rubric_score
)
```

**Verdict resolution (in order, short-circuit):**
1. If `banned_words` non-empty → `verdict = block`
2. If any `trademark_errors` → `verdict = block`
3. If `claims_ungrounded` non-empty → `verdict = block`
4. If `min(dims.values()) < 9` → `verdict = block`
5. If `composite < 85` → `verdict = block`
6. If `composite < 95` → `verdict = regen`
7. Else → `verdict = ship`

**Regen-hint generation:**
- For every dim <9, emit one actionable hint quoting an exemplar that shows the fix
- For every banned word, show the `voice.yaml.banned_words` line + suggested replacement
- For trademark errors, quote the correct rendering
- For ungrounded claims, quote the offending span and link to `data/capabilities-ground-truth.yaml`

---

## Logging contract

Every scoring call appends one row to `.planning/scorecard-log.jsonl`:

```json
{
  "ts": "2026-04-19T20:15:03Z",
  "brand": "zeststream",
  "route": "/consult",
  "surface": "hero",
  "audience": "customer",
  "phase": "peel",
  "composite": 96,
  "verdict": "ship",
  "dims": {"testable": 10, "secure": 10, "fun": 9, "valuable": 10, "easy": 9, "brand_voice": 9, "canon_present": 10, "person_named": 10, "receipt_shown": 10, "invite_not_pitch": 10, "yuzu_phase_mapped": 10, "plain_language": 9, "specificity": 10, "rhythm": 9, "friction_calibrated": 10},
  "banned_words": [],
  "claims_ungrounded": [],
  "trademark_errors": [],
  "source": "voice_probe",
  "tick": "sweep-202604192015",
  "layer_scores": {"regex": 100, "rules": 96, "embedding": 92, "llm_rubric": 94},
  "cached": false,
  "latency_ms": 347
}
```

The log is the voice system's black box. If it stops growing, the loop is dead.

---

## Exemplar promotion (closes R1 loop)

**Nightly cron `03:00 UTC`:**
```
for each ship in last 24h where composite >= 98 AND promoted_at is null:
  if age_hours >= 48:  # aging window — fresh exemplars are suspicious
    write brands/<slug>/exemplars/<surface>/<slug>.md
    embed and upsert to Qdrant collection
    mark promoted
```

## Exemplar quarantine (protects against R2 drift loop)

**Weekly cron Monday `04:00 UTC`:**
```
for each exemplar in brands/<slug>/exemplars/:
  re_score = score_copy(exemplar.text, brand, surface, audience, phase)
  if re_score.composite < 90:
    remove from Qdrant collection
    move file to exemplars/_quarantined/<slug>-<ts>.md
    write trauma.jsonl entry
```

## Trauma → rule promotion (closes B2 loop, leverage #4)

When `trauma.jsonl` shows the same `regen_hint` category recurring 3+ times:
1. Auto-generate a new `voice.yaml` rule candidate
2. Write `.planning/voice-rule-proposals/<slug>.md` for Josh's review
3. On approval, merge into `voice.yaml` and tag commit `voice-rule-promotion`
4. Run fresh audit on all exemplars to verify new rule doesn't regress the corpus

---

## Performance budgets (end-to-end)

| Percentile | Budget |
|------------|--------|
| p50 | <400ms |
| p95 | <1200ms |
| p99 | <2500ms |

If p95 >1500ms → degrade LLM model to Haiku, keep running. Log the degradation.

---

## Failure modes this algorithm prevents

(See ANTI_PATTERNS.md for depth.)

- **Rule beating** — copy passes regex but fails semantic. Layer 3+4 catches.
- **On-voice hallucination** — claim sounds right but is false. Layer 2 (claim extraction) + `GROUNDING.md` catches.
- **Drift-by-exception** — "just this once" creeping floor. Hard `composite<95 → block`.
- **Tragedy of commons** — off-voice in exemplars. Quarantine cron cleans.
- **Silent model failures** — JSON parse failures masked. 3-retry then fail-loud composite=degraded.

---

## Invocation shapes

**From a writer's LLM prompt (inline, before generation):**
```
SYSTEM: You are writing for {brand}. Read voice.yaml constants below.
Every sentence must pass 4 gates (regex, rules, embedding, LLM rubric).
Verdict threshold: composite >=95, no dim <9, no banned words, all claims grounded.
<voice.yaml content injected>
<top-5 retrieved exemplars>
<capabilities-ground-truth.yaml relevant entries>
USER: {task}
```

**From a pre-commit hook (mechanical):**
```
./scripts/voice-score.sh <file> --surface body --brand zeststream
# exit 0 = ship, exit 1 = regen, exit 2 = block
```

**From a probe cron (sampling live routes):**
```
./scripts/voice-reach-check.sh
# samples Wave-A routes, appends to scorecard-log.jsonl, writes STOP on ≥3/10 ticks drift
```
