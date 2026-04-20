# Is this actually accretive?

Every "brand voice tool" on the market claims to compound — "define your voice, sound like yourself forever." In practice most of them are one-shot PDF generators. You run them once, get a document, and the document drifts the minute a new page ships because nothing enforces it, nothing promotes good examples, and nothing captures failures.

This doc audits whether *this* repo is any different. The answer is mostly yes, with two named gaps. If either of those gaps gets fixed without the rest of the system atrophying, the claim holds. If this doc stops being true — if the loops stop closing — someone (probably future-me) should delete parts of the repo and rethink.

## The definition of accretive, for voice specifically

A brand voice system is **accretive** if every session leaves at least one of these more useful than it was:

1. The rule set (`voice.yaml`) — does it contain a rule it didn't before?
2. The exemplar corpus (`brands/<slug>/exemplars/`) — is there a new approved example?
3. The trauma log (`trauma.jsonl`) — was a failure pattern captured?
4. The ground-truth claim bank (`capabilities-ground-truth.yaml`) — was a new receipt added?
5. The audience trust stock (`S.RECOGNITION`) — is there feedback signal suggesting the brand feels more itself to its readers?

Items 1–4 are observable in git diff. Item 5 requires external feedback (which is the first named gap below).

## The loops, audited

### R1 — virtuous reinforcing loop (exemplar corpus)

> S.EXEMPLAR ↑ → LLM/writer output quality ↑ → S.LIVE quality ↑ → S.RECOGNITION ↑ → more exemplars harvested → S.EXEMPLAR ↑

**Status: working mechanically, closes on a 48-hour + 24-hour cadence.**

Implemented via the Pour step's nightly promotion cron: anything shipped with composite ≥98 that ages 48 hours without being re-flagged gets auto-promoted into `exemplars/`. New drafts retrieve the top-K=5 exemplars via Qdrant at write-time. If the LLM is doing its job, it matches the retrieval cluster, which nudges new copy toward the already-approved cluster.

**Gap:** the link from "S.LIVE quality" to "S.RECOGNITION" is assumed, not measured. See §Gap 1.

### R2 — vicious reinforcing loop (drift in corpus poisons future output)

> S.DRIFT ↑ → LLM retrieves drift as exemplar → new copy drifts more → S.DRIFT ↑

**Status: actively capped by the weekly quarantine cron.**

This is the loop most brand-voice systems ignore and the reason their corpuses decay. Our fix: every Monday at 04:00, every exemplar in the corpus gets re-scored. Anything that drops below 90 composite on re-audit moves to `exemplars/_quarantined/` and is deleted from the Qdrant collection. The bad example can't poison retrieval.

**Residual risk:** if nobody reads the quarantine log, patterns of demotion (which exemplars keep getting flagged?) are invisible. Mitigation: the Pour step docs require a human review of quarantine decisions weekly. The hard question is whether *this* discipline holds — if you skip quarantine reviews for 8 weeks, the corpus rots silently.

### B1 — primary balancing gate (voice-gate rejects drift before ship)

> voice-gate review → S.DRIFT capped before reaching S.LIVE

**Status: closes on every scoring call.**

This is the loop this entire repo is built around. Any draft that fails regex (Layer 1), rules (Layer 2), embedding (Layer 3), or LLM rubric (Layer 4) blocks before shipping. Four independent gates, any one rejects. Composite ≥95, no dim <9, no banned words, all claims grounded — or it doesn't ship.

**Strength depends on:** whether the human enforcing the gate actually refuses to override it. If "just this once" becomes a pattern, Meadows drift-to-low-performance kicks in and the floor erodes. The CLAUDE.md rule (which I enforce on myself) is "composite <95 does not ship — no exceptions." Write it in your own config with the same literal wording if you want it to hold.

### B2 — secondary balancing loop (trauma promotes to rule)

> S.TRAUMA capture → S.RULES promotion → future writing_rate produces less drift

**Status: implemented, triggers at recurrence ≥3.**

Every captured drift lands in `trauma.jsonl` with a `regen_hints` field. A weekly cron counts recurrence of each hint category. When a hint recurs 3 or more times, the system auto-drafts a PR proposing a new rule in `voice.yaml` (e.g. "add `X` to banned_words"). Human reviews the PR, accepts or rejects.

**This is Meadows leverage point #4 — self-organization.** The system literally rewrites its own rules from its own captured failures. If you want to see one in action: write 3 pieces of copy that all contain the same banned-phrase-candidate, let them flag, and the trauma-to-rule cron will propose it for formal inclusion.

**Gap:** if nobody writes traumas down (forgets to append on a drift catch), the loop doesn't close. Mitigation: the `/score-route` command appends automatically. Manual scoring has to be diligent.

### B3 — slow audit loop (weekly drift check)

> S.RECOGNITION goal vs S.LIVE quality gap → triggers cross-route audits

**Status: weekly cron runs, posts to attention surface.**

Every Monday at 09:00, the `voice-reach-check.sh` cron samples Wave-A routes (the dozen or so pages that represent the brand's live voice), runs `/score-route`, appends to `scorecard-log.jsonl`, and compares against the prior week. If composite drops ≥5 points on any route, it posts an alert.

**Gap:** this is the "alert that nobody reads" risk. Mitigation: pick a surface where the alert actually interrupts you (Slack DM, not a dashboard). If the alert lands in a silent place, the loop is dead.

## Meadows axiom check — are we working at the right leverage point?

The skill's primary intervention is at leverage **#6 (information flow)** — getting the voice rules to the writer at the *moment of writing*, not in a retro 30 days later. That's the right place to operate because it's where a writer (human or LLM) has actual authority.

Secondary interventions at:

- **#5 (rules)** — `voice.yaml` is codified, not narrative
- **#4 (self-organization)** — trauma-to-rule promotion
- **#3 (goals)** — scoring optimizes for trust-proxy (rubric + grounding), not vanity (pages shipped, SEO)
- **#2 (paradigm)** — treating voice as a Meadows *system* instead of a style-guide PDF is the paradigm shift this whole repo is an argument for

Not working at: **#12–#7** (parameters, buffer sizes, material-flow structure) — those don't apply to voice. And not at **#1** (transcending paradigms) — that would be a different repo arguing against the idea of brand voice entirely, which I'm not. Deliberate scope.

## Gap 1 — no direct SMB reader feedback

**The ask:** does the voice actually feel more like the brand to real audience members? This is S.RECOGNITION (the trust stock). We measure proxies — rubric composite, dim scores — but we don't measure the actual thing.

**What's missing:**

- An SMB "capability score" survey mechanism (Grok's A-Z framework items U/Y)
- An A/B test between voice-enforced vs. pre-system copy
- ROI tracking on the journey itself (did Peel sessions convert better after the brand voice shipped?)

**Why it's not in v0.1:** these are expensive to set up, slow to feedback on (months of data), and not required for the system to *function*. They're required for the system to *prove it's accretive on the trust axis specifically*.

**Fix path:** after 3–6 months of the system running, add a quarterly "voice retro" that pulls conversion rate, return-visit rate, and referral rate on Wave-A routes and compares to pre-system baseline. If S.RECOGNITION hasn't moved, the rubric is optimizing for the wrong proxy.

## Gap 2 — no automated per-route drift re-scoring yet

**The ask:** routes in `S.LIVE` should be re-scored periodically without a human initiating it. A content calendar that shipped 40 pages over a quarter has 40 potential drift surfaces; we sample a few (Wave-A) in the weekly cron.

**What's missing:** a cron that re-scores EVERY route on a 30-day rotating schedule, not just the hand-picked Wave-A.

**Why it's not in v0.1:** depends on a live Qdrant + API + `/score-route` being reliable enough to run unattended at scale. As of v0.1 the scorer reference implementation is a stub in `scripts/score.py` (not shipped in this repo — that's intentional, it's too brittle). Anthropics SDK + Claude Code slash commands work well enough for interactive scoring; unattended scoring at scale needs more plumbing.

**Fix path:** write `scripts/score.py` properly (API client + YAML loader + rubric + Qdrant adapter), ship as v0.2. Then the 30-day rotating re-score becomes a second cron line. Patches welcome.

## What IS already accretive (checklist)

- [x] Every `/score-route` call appends to `scorecard-log.jsonl` (black box persistence)
- [x] Every drift catch appends to `trauma.jsonl` (learning substrate)
- [x] Every composite ≥98 + 48hr-aged ship promotes to exemplars (R1)
- [x] Weekly quarantine cron removes degraded exemplars (R2 cap)
- [x] Weekly trauma-to-rule promoter proposes new rules (B2)
- [x] Weekly drift audit alerts on Wave-A degradation (B3)
- [x] Grounding pass (capabilities-ground-truth.yaml) blocks hallucinated claims structurally
- [x] Open questions (with agent recommendation) never become dead-ends
- [x] Confidence scoring per section and per claim; low-confidence auto-promotes to open-question after 30 days

## What is NOT yet accretive (named gaps)

- [ ] Direct SMB reader feedback loop (S.RECOGNITION measured via proxies, not directly)
- [ ] Per-route full-corpus re-scoring (only Wave-A is automatic)
- [ ] Cross-brand rule promotion (if zeststream and acme-saas both independently add the same trauma→rule, there's no mechanism to suggest it as a *brand-agnostic* default for `brands/_template/voice.yaml`)

## The honest verdict

This system **compounds** on the mechanical axes (rule set grows, exemplars promote, trauma captures close into rules) and **has known gaps** on the measurement axis (we don't yet measure audience trust directly). If you adopt it, expect the mechanical compounding to kick in within 2–3 months of use. Expect to add your own measurement layer on top if trust-signal is something you need to optimize for.

If this doc stops being true, file an issue titled `IS-IT-ACCRETIVE is out of date`. Or delete the parts that stopped compounding and rethink.

I build things that work, and I show you the receipt. This doc is the receipt for the accretive claim.
