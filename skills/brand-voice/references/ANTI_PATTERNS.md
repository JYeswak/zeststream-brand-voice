# ANTI_PATTERNS — the 12 failure modes this skill exists to prevent

Read before shipping copy. If a draft matches one of these, stop and fix.

---

## 1. Hardcoded banned-words lists without a semantic backstop

**Symptom:** writer routes around the regex ("empower" → "give power to", "enterprise" → "enterprise-grade").

**Why it fails:** Meadows' "rule beating" (TiS p. 137). The system optimizes for letter-of-law not spirit-of-law.

**Fix in this skill:** Layer 3 (embedding) catches semantic drift even when Layer 1 (regex) passes. Four independent gates; any one rejects.

---

## 2. Single-gate validation

**Symptom:** "The LLM rated it 8/10, ship it." Or: "It passed the banned-words grep, ship it."

**Why it fails:** single-gate = single point of failure. LLMs confidently mis-rate. Regex misses semantics.

**Fix:** 4-layer stack (regex → rules → embedding → LLM rubric). Composite + per-dim floor. Verdict only ships if all layers agree.

---

## 3. Grounding as aspiration

**Symptom:** "We should cite our claims." Nothing enforces it. Writers forget mid-draft. Numbers drift into hyperbole.

**Why it fails:** Meadows "policy resistance" (TiS p. 112). Guidelines in a PDF nobody reads.

**Fix:** `GROUNDING.md` makes claim-extraction a **gate**. Ungrounded claim → hard block. Mechanical, not voluntary.

---

## 4. Confidence scores without escalation path

**Symptom:** "Model returned 72% confidence. Ship anyway because we don't have a reviewer."

**Why it fails:** confidence scores used without a gate are just theater.

**Fix:** composite <95 → regen; <85 → block. Any dim <9 → block. No "we'll just lower the threshold."

---

## 5. RAG over a poisoned exemplar corpus

**Symptom:** An off-voice page shipped (say, composite 88). Gets promoted to `exemplars/` because of a promotion bug. Now LLM retrieves it and drifts future copy toward the bad pattern.

**Why it fails:** R2 vicious reinforcing loop. Unchecked, drift compounds exponentially.

**Fix:** 
- Promotion threshold ≥98 + 48hr aging (not fresh)
- Weekly quarantine cron re-scores exemplars; <90 → move to `_quarantined/`
- Never skip the quarantine pass to save time

---

## 6. Mental-model drift without structural fix

**Symptom:** "This page feels off." Writer edits the sentence. Ships. Three weeks later, same problem on another page.

**Why it fails:** staying at the Events layer of the iceberg. Pattern underneath isn't caught.

**Fix:** every reject triggers a `trauma.jsonl` entry. Recurrence ≥3 → auto-propose a new `voice.yaml` rule (Meadows leverage #4, self-organization). The system writes its own rules from its own scars.

---

## 7. Pre-empting reviewer taste with AI judgment

**Symptom:** "The LLM said it was on-brand, so we're done. Don't need Josh to look."

**Why it fails:** CubCloud Axiom 5 — "Taste is human & non-negotiable." AI proposes; Josh disposes. The rubric is a proxy, not a replacement.

**Fix:** the scorer never auto-ships to prod on conversion routes. It ships to a staging gate. Josh's approval or rejection is the final input. The rubric shortens the list of things Josh has to review, not replace him.

---

## 8. Treating claim-grounding as "nice to have"

**Symptom:** copy says "95% Deployment Rate" with no source. Writer meant it as illustrative.

**Why it fails:** The 2026-04-19 pivot. On-voice hallucinated claims shipped for 5 weeks before detection. Meadows diagnosis: information flow #6 was absent for the claims stock.

**Fix:** `GROUNDING.md`. Mechanical claim extraction + ground-truth match. "Nice to have" is an aspiration layer. This is now a hard gate.

---

## 9. Assuming "we fixed it once" means it's fixed forever

**Symptom:** a banned word made it through in March. Added to the list. Now a new surface (e.g., email drip) uses the same word. Regex doesn't run there.

**Why it fails:** different surface, same rule, no coverage. Meadows "bounded rationality" (TiS p. 106).

**Fix:** `voice-reach-check.sh` probes ALL Wave-A routes on every tick. Coverage is continuous, not one-shot. Adding a new surface (email, post, meta) requires updating the route list; the probe refuses to skip.

---

## 10. Building one-shot prompts instead of the skill

**Symptom:** Writer copies `voice.yaml` content into a single prompt, writes one page, closes session. Next session, starts from scratch.

**Why it fails:** Meadows "addiction" (TiS p. 129) — the human stopped internalizing the system because "I'll just re-prompt next time." Prompts rot. Context degrades. Consistency drops.

**Fix:** this file structure. `voice.yaml` is read every invocation. Exemplars are promoted (not re-invented). Trauma accumulates. The skill IS the memory — no one-shot can match it.

---

## 11. Shipping copy without a scorecard entry

**Symptom:** Writer ships a page. No scorecard-log.jsonl row. No trace that the gate was run.

**Why it fails:** the log is the voice system's black box. Without it: no R1/R2 loop visibility, no trend detection, no audit trail.

**Fix:** every ship appends. Pre-deploy hook verifies the scorecard entry exists for the file+SHA about to deploy. If missing → block.

---

## 12. Decorative complexity (the Meadows one)

**Symptom:** guidelines file is 500 lines, nobody reads it. Rubric has 37 dimensions, nobody can reason about them. Tool chain is 6 CLIs, nobody remembers which.

**Why it fails:** complexity that doesn't reduce to behavior change is friction. Meadows: "The goal of a system is what it does, not what it's called."

**Fix:** 
- SKILL.md is a table of contents, not an encyclopedia
- voice.yaml is exactly the constants, nothing editorial
- 15 dims (not 37) — each with a one-sentence rationale
- One scorecard log, one trauma log, one exemplars dir per brand

If the skill grows more surface than this, something is wrong. Prune.

---

## Counter-pattern: what the skill does right

For each failure above, the answering mechanism:

| Anti-pattern | Countermeasure |
|--------------|----------------|
| Hardcoded bans only | Layer 3 semantic backstop |
| Single-gate | 4 independent layers |
| Grounding-as-aspiration | `GROUNDING.md` mechanical gate |
| No escalation | Hard composite + dim floors |
| Poisoned exemplars | 48hr aging + weekly quarantine |
| Events-layer-only fixes | Trauma → rule promotion at 3× |
| Pre-empting reviewer | Stage to Josh, never auto-ship conversion routes |
| Skipped grounding | Hard block on `claims_ungrounded` |
| One-shot coverage | Wave-A probe on all routes every tick |
| One-shot prompts | Persistent skill + exemplars + traumas |
| Untraced ships | Pre-deploy hook requires scorecard row |
| Decorative complexity | One log, one trauma, one exemplars per brand |

---

## The one-line test

Ask yourself: *if this sentence ships and a skeptical reader dissects it, does anything I can't defend remain?*

- Numbers I can't source → fail.
- Claims about myself I haven't earned → fail.
- Corporate register that could swap to any competitor → fail.
- A CTA that's a sales pitch → fail.
- A trademark rendered wrong → fail.

If all those answer clean, and the composite is ≥95, and no dim is <9: ship it.
