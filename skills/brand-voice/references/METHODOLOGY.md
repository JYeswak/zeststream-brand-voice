# METHODOLOGY — Meadows-style voice system

> *"A system is a set of things—people, cells, molecules, or whatever—interconnected in such a way that they produce their own pattern of behavior over time."* — Donella Meadows, Thinking in Systems, p. 2

This document is the **why** behind every mechanical rule in `voice.yaml` and `ALGORITHM.md`. Read it once per session. It informs every judgment call the rubric can't make for you.

---

## 1. The iceberg — four layers of voice audit

When auditing a website, a page, or a single sentence, push past the surface. Meadows' iceberg (events → patterns → structures → mental models) applies directly:

| Layer | What you see | Audit questions | SMB-site example |
|-------|--------------|-----------------|------------------|
| **Events** (tip) | Individual sentences | What was said? | Homepage H1 uses "Transform your operations" |
| **Patterns** (waterline) | Repetition over time / across pages | What keeps happening? | Every CTA on the site starts with "Discover" |
| **Structures** (below) | Templates, CMS defaults, incentives, tooling | What produces these patterns? | Webflow template ships with stock copy; marketer rewarded for page count; no banned-words gate |
| **Mental models** (deep) | Beliefs held by writer / LLM | What do they *think* good copy is? | "We need to sound enterprise-grade to be taken seriously" (exact inversion of ZestStream voice) |

**Audit heuristic:** if every fix stays at the Events layer ("change this sentence"), drift returns within 30 days. The durable fix is always one or two layers deeper than the complaint. Rewrite the sentence — *and* patch the template, *and* name the mental model.

This skill operates primarily at the **Structures** layer (voice.yaml is a structure, the rubric is a structure, exemplars are a structure) but feeds back into **Mental models** through the exemplar corpus.

---

## 2. The 12 leverage points — mapped to voice interventions

Meadows (TiS ch. 6, pp. 145–165) ranks system-intervention leverage from weakest (#12) to strongest (#1). The top 6 — where this skill operates:

- **#7 Gain of positive loops.** The vicious R2 loop: if an off-voice phrase ships, the LLM/writer imitates it → more off-voice. **Intervention:** quarantine off-voice pages from `exemplars/` (RAG source pool). See `ALGORITHM.md §exemplar-promotion`.

- **#6 Information flow — highest *actionable* leverage.** Writers don't have authority over #1–#5. They have authority over #6. Move voice information *to the point of decision*: prompt injection at write-time, pre-commit grep, LSP diagnostic, PR comment score. **This skill IS the #6 intervention.** Latency between off-voice event and signal = <1 second.

- **#5 Rules of the system.** Codified `voice.yaml` — banned words, canon enforcement, trademark rendering — machine-checkable, not prose. The difference between a Notion page nobody reads and a pre-commit hook that blocks a merge.

- **#4 Power to self-organize.** S.TRAUMA → S.RULES promotion. When the same failure mode recurs ≥3 times, the skill auto-files a PR adding a new machine-checkable rule. The system writes its own rules from captured failures.

- **#3 Goals of the system.** Replace "publish more pages" with "grow S.RECOGNITION (reader trust)." Every gate scores against trust-delta, not volume. The skill's success metric is *quality of shipped voice*, never *count of shipped voice*.

- **#2 Paradigm.** Treat voice as a **living system** with stocks, flows, loops — not a static PDF. This skill's existence is the paradigm. Every other intervention is implementation detail.

Rule-of-thumb: if an intervention doesn't reduce the latency between cause (off-voice produced) and signal (writer notices), it's probably working at #10–#12 and won't hold.

---

## 3. Stocks, flows, loops — the voice system model

### Stocks (accumulators — things that persist)

- **S.EXEMPLAR** — approved copy corpus. Lives in `brands/<slug>/exemplars/`. Promoted when composite ≥98 + 48hr aging. Quarantined if later found drifting.
- **S.TRAUMA** — known failure modes. Lives in `brands/<slug>/trauma.jsonl`. Append-only. Each entry: `{ts, text, surface, composite, banned_words, dims, regen_hints, fix_applied, recurrence_count}`.
- **S.LIVE** — deployed surfaces. Measured as `n_pages × avg_voice_score`. Read from `.planning/scorecard-log.jsonl`.
- **S.RECOGNITION** — audience trust. Slow stock (months). Proxies: return visits, consult-form conversion, referral rate.
- **S.RULES** — codified machine-checkable rules. Count = number of regex + boolean checks in `voice.yaml`. Grows via #4 self-organization.
- **S.DRIFT** — off-voice phrases currently live but not yet caught. Grows when ungated copy ships. Decays when audit catches and fixes.
- **S.CAPABILITIES** — ground-truth claims the voice is allowed to make. Lives in `data/capabilities-ground-truth.yaml`. **Added after the 2026-04-19 pivot — prevents on-voice hallucinated claims.**

### Flows (rates of change)

- `writing_rate` → adds to S.LIVE (and to S.DRIFT if ungated)
- `review_rate` → moves draft to S.EXEMPLAR (pass) or S.TRAUMA (fail)
- `deployment_rate` → S.LIVE
- `trust_accumulation_rate` → S.RECOGNITION (slow, months)
- `trauma_capture_rate` → S.TRAUMA
- `rule_promotion_rate` → S.RULES (from S.TRAUMA when recurrence ≥3)
- `drift_decay_rate` → reduces S.DRIFT as audits fix live pages

### Loops

**R1 — Virtuous reinforcing.** S.EXEMPLAR ↑ → LLM/writer output quality ↑ → S.LIVE quality ↑ → S.RECOGNITION ↑ → more exemplars harvested → S.EXEMPLAR ↑. **This is what the skill is built to run.**

**R2 — Vicious reinforcing (must cap).** S.DRIFT ↑ → LLM retrieves drift as exemplar → new copy drifts more → S.DRIFT ↑. **Cap intervention:** quarantine off-voice pages from the RAG exemplar pool. No exception.

**B1 — Primary balancing gate.** voice-gate review → S.DRIFT capped before reaching S.LIVE. **This is the dominant loop** this skill protects. Rule 2 in CLAUDE.md (never skip voice-gate) enforces B1 strength.

**B2 — Secondary balancing (learning).** S.TRAUMA capture → S.RULES promotion → future writing_rate produces less drift. The skill gets smarter session-over-session.

**B3 — Slow balancing (audit).** S.RECOGNITION goal vs S.LIVE quality gap → triggers cross-route audits. Weekly cron scan, Mattermost post.

---

## 4. Dancing with Systems — 5 principles that shape this skill

From Donella Meadows' *Dancing with Systems* (2001 essay, posthumous in *TiS* appendix):

1. **"Get the beat of the system before you disturb it."** → `references/DISCOVER.md` runs before any new copy is written for a new brand. Scrape the live site, cluster phrasings, interview the founder. Don't impose ZestStream voice onto Blackfoot.

2. **"Expose your mental models to the light of day."** → `voice.yaml` forces implicit taste into explicit, reviewable rules. No tacit "I know it when I see it." Any writer (human or LLM) can read the rules and predict the verdict.

3. **"Stay humble. Stay a learner."** → `trauma.jsonl` is append-only. Every escaped drift becomes a test case. The skill gets smarter session-over-session. This matches CubCloud axiom 7 (recursive self-improvement).

4. **"Honor and protect information."** → Voice violations must be **visible** (logs, diffs, scores). The 2026-04-19 trauma — on-voice hallucinated claims — was a corrupted-information failure: voice was honored, *truth* wasn't. `S.CAPABILITIES` + `GROUNDING.md` close that gap.

5. **"Locate responsibility in the system."** → The writer (human or LLM) owns voice *at write-time*, not the reviewer at merge-time. Pushing checks upstream (prompt injection, LSP, pre-commit) aligns responsibility with causation.

---

## 5. Common failure modes (Meadows traps applied to voice)

Each of these has a counter-intervention in the skill. If you find a new one, add it here and file a S.RULES promotion.

| Meadows trap | TiS ref | Voice manifestation | Counter in this skill |
|--------------|---------|--------------------|-----------------------|
| Seeking the wrong goal | p. 138 | Optimizing for pages-shipped, SEO keyword density, reach | Goal = S.RECOGNITION, measured via rubric composite not volume |
| Policy resistance | p. 112 | Writers revert to old phrasing because the guidelines doc isn't in their loop | #6 information flow — rules surface in the editor / prompt, not in Notion |
| Drift to low performance | p. 121 | Each "just this once" exception lowers the standard; next exception calibrates to new floor | Hard gate, no ship-below-95 |
| Tragedy of the commons | p. 116 | Shared exemplar corpus degraded by any writer shipping off-voice | Quarantine off-voice from `exemplars/` |
| Rule beating | p. 137 | Writing that passes banned-word grep but violates cadence/posture | Multi-signal gates (lexical + structural + semantic + LLM) — any layer rejects |
| Addiction / shifted burden | p. 129 | Writers stop internalizing voice because "the gate will catch it" | Gate feedback teaches — shows *why* with exemplars, builds capacity rather than replacing it |
| Bounded rationality | p. 106 | Writer can't see full brand at write-time | Prompt injection of relevant exemplars + voice constants + ground-truth claims |
| Seeking the wrong information | p. 172 | Dashboard shows vanity metric (page views) not trust delta | Dashboard shows composite score × route, S.DRIFT delta, trauma-capture rate |

---

## 6. The 2026-04-19 pivot — why S.CAPABILITIES exists

The original voice system had 5 stocks and 3 loops. It was A-grade on voice but let through hallucinated claims like "95% Deployment Rate" and "10,000+ Hours Removed" — claims that were on-register but factually false.

The trauma: **voice ≠ truth. A voice-gate that scores only cadence, lexicon, and posture will happily pass a lie if the lie sounds like the brand.**

The Meadows diagnosis: **information flow #6 was intact for voice, absent for claims.** The system had no mechanism to check *whether what the sentence says is true*.

The durable fix (now in the skill):

1. **New stock: S.CAPABILITIES** — `data/capabilities-ground-truth.yaml`. Every approved factual claim, one entry.
2. **New gate: grounding** — `references/GROUNDING.md`. Claim extraction + match-or-reject.
3. **New rule: cite-or-omit** — banned phrases for unnamed stats ("about X% of clients", "roughly Y hours saved"). No vague claims permitted.

Any future voice skill build should preserve this lesson in its paradigm (leverage #2): **voice and truth are separate stocks. Protect both.**

---

## 7. Operational discipline — how this skill stays a system, not a PDF

- **Every ship appends a scorecard entry.** `.planning/scorecard-log.jsonl` is the voice black box. If it stops growing, the system is dead.
- **Every trauma appends.** Drift escapes must be logged. An off-voice ship without a trauma entry means the loop didn't close.
- **Promote after 48hr + ≥98.** Fresh exemplars are suspicious. Aging stabilizes them.
- **Quarantine on audit re-score.** If a previously-promoted exemplar scores <90 on re-audit, remove it from the pool. Don't let drift compound.
- **Retro the rubric quarterly.** Same rubric for 12 months = possibly stale. Re-weight the pass components (regex / rules / embed / LLM) when their correlations drift.
- **Read this file at session start.** If METHODOLOGY falls out of context, the skill becomes a checklist — the failure mode this skill exists to prevent.

---

## 8. Self-check — you are using this skill correctly when…

- You read `voice.yaml` before writing, not after
- You know which brand you're writing for (explicit, not implicit)
- You cite or omit — never hedge
- You log the composite score of every ship
- You can name, for any rejection, the specific dim that failed and the exemplar that shows the fix
- You feed the trauma file when you catch a late drift
- You treat the rubric as a **proxy** for trust, not a replacement for taste (Axiom 5, human taste non-negotiable)

If you can't tick these, slow down and re-read this file.

---

*Sources: Donella Meadows,* Thinking in Systems *(Chelsea Green, 2008);* Dancing with Systems *(The Academy for Systems Change, 2001).*
