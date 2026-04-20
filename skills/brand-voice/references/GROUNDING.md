# GROUNDING — the 2026-04-19 pivot's permanent fix

> Voice and truth are separate stocks. A voice-gate that scores cadence, lexicon, and posture will happily pass a lie if the lie sounds like the brand.

This document defines the claim-extraction and ground-truth matching pass. It closes the gap exposed by 5 consecutive Wave-B sweeps that graded on-voice copy A- while the copy claimed "95% Deployment Rate" and "10,000+ Hours Removed" — numbers with no receipt.

---

## Why grounding is a separate layer

Layers 1–3 of the scorer check *how* something is said. Grounding checks *whether what is said is true*. Different failure mode, different fix.

Per Meadows, **information flow (#6) for voice** was intact before this. **Information flow for claims** was absent — writers had no mechanism to check their own numbers against a canonical source. The grounding pass adds that mechanism.

---

## The protocol

### 1. Extraction

Every scorer run extracts candidate factual claims from the text using `voice.yaml.claims.extraction.patterns`:

- Numbers with technical units: `\b\d[\d,]*\s*(?:tok/s|workflows?|chunks?|years?|hours?|weeks?|months?|days?|GPUs?|containers?|scripts?)\b`
- Money: `\$[\d,]+(?:k|K)?(?:/mo|/month|/hr|/yr)?`
- Percentages: `\b\d+(?:\.\d+)?%`
- Multipliers: `\b\d+(?:\.\d+)?×|\b\d+x improvement`
- Capability verbs: `\b(?:built|rebuilt|tuned|deployed|shipped|wired)\b` + their object

Each extracted span becomes a **claim candidate**.

### 2. Matching

Each claim candidate is matched against `data/capabilities-ground-truth.yaml`. Matching is a two-phase:

- **Phase A — Exact/near-exact lexical match.** Claim substring appears verbatim or with ≤3 edit-distance in a ground-truth entry's `claim` or `canonical_phrasing` field.
- **Phase B — Semantic match (fallback).** If no lexical hit, embed claim + each entry; accept if cosine ≥0.92 to any entry.

No match = ungrounded. The claim lands in `ScoreResult.claims_ungrounded` and the run blocks.

### 3. Citation

When a claim matches, the ground-truth entry's `source` field is logged with the ship. Example log row:

```json
"claims_grounded": [
  {"claim": "105 tok/s generation", "source": "capabilities-brief.md:59 (benchmark 2026-03-24)"},
  {"claim": "96 production n8n workflows", "source": "n8n.zeststream.ai API pull 2026-04-19"}
]
```

### 4. Cite-or-omit

If a writer (human or LLM) has a claim with no ground-truth match, they have two options:

- **Cite** — add the claim to `data/capabilities-ground-truth.yaml` with a real source (benchmark run, repo link, log file, client doc). Re-score.
- **Omit** — rewrite the copy without the claim. Use a hedge-free capability-phrasing: `"I can wire this in"` rather than `"I offer X service"` when there's no receipt yet.

**No third option.** "Roughly," "approximately," "most clients" — all banned per `voice.yaml.banned_phrases.vague_quantifier_auto_reject`.

---

## Ground-truth YAML schema

```yaml
# data/capabilities-ground-truth.yaml
- id: benchmark_sglang_2026_03_24
  claim: "105 tok/s generation on MiniMax M2.5 FP8 TP=4 H200"
  canonical_phrasing: "105 tok/s generation"
  category: infrastructure
  unit: tok/s
  value: 105
  source:
    type: benchmark
    location: "gpu-optimization repo, benchmark run 2026-03-24"
    verified_by: "direct measurement via cc-router"
    timestamp: "2026-03-24"
  context: "measured on my H200 stack, full 50K prefill at 670ms"
  risks:
    - "Do not generalize to other models or hardware"
    - "Must update if benchmark re-runs show drift"

- id: n8n_workflow_count_2026_04_19
  claim: "96 production n8n workflows running at n8n.zeststream.ai"
  canonical_phrasing: "96 production n8n workflows"
  category: infrastructure
  unit: workflows
  value: 96
  source:
    type: api_pull
    location: "n8n.zeststream.ai /api/v1/workflows?limit=250"
    verified_by: "pulled 2026-04-19"
    timestamp: "2026-04-19"
  context: "live count at pull time; fluctuates ±5 on any given day"
  stale_after_days: 30  # re-verify if older
```

Every entry must have: `id`, `claim`, `canonical_phrasing`, `source{type, location, timestamp}`.

---

## Severity levels

Not every ungrounded claim is a ship-blocker.

| Severity | Example | Action |
|----------|---------|--------|
| **P0 — factual** | "95% Deployment Rate" with no client cited | Block. No exceptions. |
| **P0 — numeric** | "910× improvement" without cache-breakthrough receipt | Block. No exceptions. |
| **P1 — capability** | "I offer video pipelines" when no receipt exists | Block. Rewrite to "I can wire this in." |
| **P2 — analogy** | "like Peel. Press. Pour." (method name, not a numeric claim) | No action — not a factual claim. |
| **P3 — aspiration** | "On path to SOC2" (stated as in-progress) | Allow if phrasing is in-progress; reject if past-tense. |

The scorer P0 and P1 gates are hard. P2 and P3 are passed through.

---

## Stale-source policy

Entries with `stale_after_days` that have aged past the threshold emit a **warning** but don't block scoring. A weekly cron lists stale entries; Joshua refreshes or retires them.

Why not auto-block on staleness? Because SMB reality: benchmarks from 2 months ago are still truthful more often than not. Human judgment on refresh cadence > mechanical expiry.

---

## What to do when a scorer call returns `claims_ungrounded`

1. **Quote the span back.** `ScoreResult.claims_ungrounded` is a list of exact offending spans. Show each one.
2. **Offer both paths.** "Add to `data/capabilities-ground-truth.yaml` with evidence, OR omit the claim and rewrite."
3. **Never silently regenerate.** Regenerating without Joshua (or the writer) making a truth call is how on-voice hallucination re-enters. The human owns the truth decision.

---

## The trauma log entry when a claim slips through

```jsonl
{"ts": "2026-04-19T14:22:00Z", "surface": "/services/ai-content", "text": "95% Deployment Rate", "composite": 91, "banned_words": [], "claims_ungrounded": ["95% Deployment Rate"], "recurrence_count": 1, "regen_hints": ["Remove the percentage — no client-verified source exists. Rephrase to 'the ones I've shipped went live' if the honest version is acceptable."], "fix_applied": "copy rewritten, re-scored composite 96"}
```

Recurrence-count tracks how many times a similar hallucination pattern has escaped. At 3+, the regex-extraction pattern is tightened (e.g., `\b\d+%\s*(?:deployment rate|success rate|retention)` added to claims extraction as a *stricter* required-source-type check).

---

## Integration with the wider voice system

- **Rubric dim `testable`** — explicitly scores grounding. A claim with no source = dim testable ≤5, blocks via `any_dim<9`.
- **Rubric dim `receipt_shown`** — scores *presence* of a receipt. Distinct from grounding (which checks *truth*). Both must pass.
- **Scorecard log** — logs `claims_grounded[]` and `claims_ungrounded[]` separately. Drift detection: watch for `len(claims_ungrounded) > 0` trend per route over time.
- **Wave-A probe** — the cron-sampled routes. Ungrounded claims in production = immediate P0 trauma entry + route on the fix list.

---

## The Meadows framing

This entire grounding pass is a **new information flow (#6)** added after the pivot. The skill had Meadows #6 for voice (cadence/lexicon/posture); it did not have #6 for truth. Adding it was the single highest-leverage intervention available after 2026-04-19.

The 2-minute mental model:

- **Before pivot:** voice was checked, claims were trusted. Result: on-voice hallucinated claims shipped to production.
- **After pivot:** voice is checked AND claims are matched against ground-truth. Result: structurally impossible to ship "95% Deployment Rate" without a source.

The fix compounds: every new approved claim lands in `capabilities-ground-truth.yaml`, permanent. Every attempted hallucination that hits the grounding gate adds a trauma entry. Each round makes the next round harder to fail.

That's the voice system dancing with itself.
