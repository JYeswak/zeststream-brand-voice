# JOURNEY_MAP — voice per stage

Closes Grok framework item **J** (Journey Mapping). Maps the 5 customer-journey stages to surface × register. Derived from our `TONE_MATRIX.md` but organized by what the reader is *doing*, not what the page *is*.

---

## The five stages

```
AWARENESS → CONSIDERATION → DECISION → ONBOARDING → ADVOCACY
  "gap"       "leverage"       "Peel"      "handoff"     "flywheel"
```

Each stage has a dominant **Meadows iceberg level** the reader is processing. Voice meets them where their mental model currently sits.

---

## Stage 1 — Awareness

**Reader state:** Noticed something is off. "My operators are drowning. AI headlines everywhere. I don't know where to start."

**Iceberg level reader is on:** Events (specific frustrations)

**Mental-model shift goal:** From "I'm behind" → "my systems are fixable and one build compounds"

**Surface × register:**

| Surface | Register | Must include |
|---------|----------|--------------|
| LinkedIn/social post | narrative-hook + technical-accessible (Tier 2 language) | One receipt number, one mental-model phrase |
| /methods/* essay | technical-accessible + build-confident | First-person experience, measured benchmark, Meadows or Jeff citation |
| cold email | warm-operator + discovery-curious | One specific stat from the recipient's visible stack, low-friction ask |
| meta description | declarative-meta + specific | Canon line fragment + one receipt |

**What the reader needs to feel:** "Someone sees my gap, is technically credible, and isn't selling me."

**What to avoid:** Pitching. Claiming to solve their problem without naming it. AI hype.

**Exemplar phrase:** *"Your data lives in five places. Your CRM is seven years old. No $20/month SaaS will ever land and work."*

---

## Stage 2 — Consideration

**Reader state:** On the site. Reading. Comparing. "Is this the right person? Can I trust the claims?"

**Iceberg level:** Patterns → Structures

**Mental-model shift goal:** From "is Joshua legit?" → "Joshua has shipped the receipts and names his limits"

**Surface × register:**

| Surface | Register | Must include |
|---------|----------|--------------|
| / hero | direct + inviting + specific (Tier 1 language) | Canon line, three moves |
| / body | technical-accessible + build-confident | 96 workflows, CubCloud 910× story, frontier-pricing line |
| /about | credibility-forward + warm-operator (Tier 4) | Montana, 14 years, ElektraFi end-2025, exit, partnership frame |
| /work/cubcloud | build-confident + technical-accessible | 8-GPU bare-metal rebuild, specific benchmarks, current vendor-architect status |
| /methods/* | technical-accessible + narrative-hook | Problem → investigation → specific fix → measured result |
| case studies (future) | build-confident + specific | Named client (if authorized), named metric, named receipt |

**What the reader needs to feel:** "This person has actually done this. And they told me where they don't fit."

**What to avoid:** Testimonials without metrics. "Trust me" framing. Hidden limits. Phase/gate conflation.

**Exemplar phrase:** *"None of this is a roadmap. It's running today."*

---

## Stage 3 — Decision

**Reader state:** Ready to act or ready to walk. "Is a Peel session worth 20 minutes?"

**Iceberg level:** Structures → Mental Models (shifting)

**Mental-model shift goal:** From "this is a sales trap" → "Peel is $0 diagnostic with a written map at the end"

**Surface × register:**

| Surface | Register | Must include |
|---------|----------|--------------|
| /consult hero | direct + inviting (Tier 3 language) | Canon line, 20-minute Peel, $0, no pitch at end |
| /consult body | warm-operator + discovery-curious | Three doors with numbers, capacity discipline, what Peel produces |
| /consult CTA | inviting + specific | Calendar link or "book now" — never "contact sales" |
| pricing section | direct + specific | All three doors with $ and week ranges |
| confirmation email | warm-operator + inviting | What to prep, what to expect, signoff `— Joshua` |

**What the reader needs to feel:** "Low-risk. Known bounds. Joshua respects my time."

**What to avoid:** Upsell in the Peel offer. Hidden fees. "Contact us for pricing."

**Exemplar phrase:** *"Book a 20-minute Peel session. Free, specific, no pitch at the end."*

---

## Stage 4 — Onboarding

**Reader state:** Paid. "I want to see the wiring I bought."

**Iceberg level:** Structures (their own stack revealed)

**Mental-model shift goal:** From "consulting is a black box" → "every milestone ships with its receipt"

**Surface × register:**

| Surface | Register | Must include |
|---------|----------|--------------|
| kickoff email | warm-operator + build-confident | Peel schedule, deliverable list, comms cadence |
| Peel Report delivery | build-confident + specific | 5 deliverables (report, map, quick-win matrix, scorecard, proposal) |
| mid-build update | build-confident + technical-accessible | Milestone-by-milestone receipt (JSON, diagram, benchmark) |
| handoff doc | build-confident + kaizen-calm | What shipped, how to run it, how to monitor, what to touch me for |
| retainer proposal | warm-operator + specific | Scope, cadence, price, out-of-scope |

**What the reader needs to feel:** "I can see what's being built. I'll own it."

**What to avoid:** Consulting-speak ("deliverable," "stakeholder," "touchpoint"). Opaque status updates. Scope creep without explicit $.

**Exemplar phrase:** *"Every milestone ships with its receipt — the workflow JSON, the pipeline diagram, the benchmark numbers, the runbook, the monitoring."*

---

## Stage 5 — Advocacy

**Reader state:** Shipped. Running. "I'd recommend Joshua. Here's what he built."

**Iceberg level:** Mental Models (permanently shifted)

**Mental-model shift goal:** From "I got a system" → "I got a system that compounds and I tell other operators about it"

**Surface × register:**

| Surface | Register | Must include |
|---------|----------|--------------|
| post-ship check-in | warm-operator + kaizen-calm | What's running, what's about to need a refresh, anything they want me to look at |
| case study (with permission) | build-confident + specific | Named metric, named workflow, named after-state |
| referral ask | warm-operator + direct | "If you know someone stuck in the same gap, send them the Peel link." |
| retainer renewal | warm-operator + specific | What I did this period, what I'm watching next, price |

**What the reader needs to feel:** "This ships, this compounds, and I'm in kaizen mode."

**What to avoid:** Generic "how's it going" check-ins. Case studies that sound like Joshua wrote them. Pressure to refer.

**Exemplar phrase:** *"Operations run themselves. We know exactly how to improve the rest."*

---

## Cross-stage rules

### Phase consistency

If the reader is in `peel` phase (Meadows discovery), avoid `kaizen-calm` register — they're not at pour yet. If reader is in `pour` phase (retainer), avoid `discovery-curious` — they already bought.

### Iceberg depth per stage

Don't try to shift mental models before the reader has absorbed the preceding layer. Awareness copy that jumps to "paradigm shift" language alienates. Decision copy that lingers on pattern-naming loses urgency.

### Register fade

The voice's *personality* is constant (first-person, receipt-first, inviting, technical-accessible). The *tone* shifts along formality/energy/depth per `TONE_MATRIX.md`. Never change voice. Always adapt tone.

---

## How to use this file

When writing any outbound piece:

1. **Identify the stage.** Which of the 5 does this reader sit in?
2. **Identify the iceberg level.** Events / Patterns / Structures / Mental Models?
3. **Pick the register** from the table for that surface × stage.
4. **Pull the exemplar phrase** for that stage as a starting-point anchor.
5. **Run the scorer** — `friction_calibrated` dim is the one most sensitive to stage mismatch.

If a piece mixes two stages (e.g. blog post that hooks Awareness but pitches Decision in the same paragraph), **split the piece**. Never mix.
