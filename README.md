# zeststream-brand-voice

A brand-voice enforcement system for AI-generated marketing copy, built as a Claude Code plugin. It treats brand voice as a Donella-Meadows system — stocks, flows, feedback loops, leverage points — rather than a static style guide, and combines a 4-layer hybrid scorer (regex + rules + embeddings + LLM rubric) with a mandatory claim-grounding pass against a source-of-truth YAML so factually-hallucinated-but-on-voice copy can't ship. You point it at any brand's `voice.yaml` + `capabilities-ground-truth.yaml` and you get a repeatable rewrite → score → ground → log → promote loop that gets smarter every session: off-voice copy becomes trauma entries, trauma patterns that recur 3+ times auto-propose new rules, high-scoring copy ages into exemplars that then inform future drafts via retrieval. The project ships with a full working example (zeststream.ai, my own consulting site), a redacted fictional example (a generic B2B SaaS called Acme), a 4-step "Peel → Press → Lock → Pour" journey you can run on any brand yourself, and enough methodology documentation that the thing is useful even if you never run the scorer — the markdown is the product.

*TLDR, if you run Claude Code and want to kick the tires:*

```bash
git clone https://github.com/JYeswak/zeststream-brand-voice.git
cd zeststream-brand-voice
./scripts/install.sh              # symlinks skills/brand-voice → ~/.claude/skills/brand-voice
# open any repo, ask Claude: "write me a LinkedIn post about X for brand Y"
# the skill will load, pull voice.yaml + claims bank, score the draft, and block on banned words
```

*TLDR, if you want the concepts without the tooling:*

Read `skills/brand-voice/references/METHODOLOGY.md` (the Meadows frame), `skills/brand-voice/references/ALGORITHM.md` (the 4-layer scorer), `skills/brand-voice/references/GROUNDING.md` (the hallucination fix), and `journey/` (the 4-step Peel→Press→Lock→Pour flow). Those five files capture the whole system; everything else is implementation detail.

---

## Why this exists

I'm Joshua Nowak. I build AI systems for operators — mostly wiring agent stacks, n8n pipelines, and RAG into existing businesses. In April 2026 I spent five sessions running a per-page voice rubric against my own marketing site, scoring each route A- on tone and cadence while shipping claims like "95% Deployment Rate" and "10,000+ Hours Removed" — numbers that had no source, because there is no client roster that generated them. The voice-gate was checking *how* things sounded. It wasn't checking *whether they were true.*

Two Meadows-flavored diagnoses fell out of that failure:

1. **Information flow (leverage point #6) for voice was intact, but absent for claims.** Writers (human and LLM) had no mechanism to check their own numbers against a canonical source. The ground-truth YAML + extraction regex + mandatory-match gate closes that hole structurally, not via writer vigilance.
2. **Voice enforcement that relies on a single LLM rubric call is the wrong shape.** An LLM that passes the same prompt that generated the copy will often mark its own output on-brand — the model doesn't know what it doesn't know. Four independent layers (regex, rules, embedding, rubric) where any single layer can reject kills that failure mode.

The rest of the README is the resulting system. The implementation is a Claude Code skill because that's the harness I use; the concepts apply to any LLM workflow.

---

## What's in this repo

| Path | What lives there |
|---|---|
| `skills/brand-voice/SKILL.md` | Entry point. The 5-step loop (Load → Write → Gate → Ground → Log), hard rules, 4 tests, 3 moves. |
| `skills/brand-voice/references/METHODOLOGY.md` | Meadows iceberg, 12 leverage points mapped to voice, 7 stocks + 6 flows + 5 loops. |
| `skills/brand-voice/references/ALGORITHM.md` | The 4-layer scorer — regex (0.15) + rules (0.20) + embedding (0.25) + LLM rubric (0.40). Weights, thresholds, verdict resolution. |
| `skills/brand-voice/references/GROUNDING.md` | Claim extraction + ground-truth match. The cite-or-omit gate. |
| `skills/brand-voice/references/ANTI_PATTERNS.md` | 12 failure modes this skill exists to prevent. |
| `skills/brand-voice/references/CONFIDENCE_SCORING.md` | H/M/L per section, stale-after-days policy, low-confidence → open-question promotion. |
| `skills/brand-voice/references/DISCOVER.md` | 9-step onboarding flow for a new brand (4–8 hours of work, serious). |
| `skills/brand-voice/references/CORPUS_SIGNATURES.md` | Stylometric fingerprinting — 9 signatures including burstiness (AI-slop detection). v0.2. |
| `skills/brand-voice/brands/zeststream/` | My own brand, real config, redacted specifics. |
| `skills/brand-voice/brands/acme-saas/` | A fictional B2B SaaS for readers who want a clean reference without my positioning. |
| `skills/brand-voice/brands/_template/` | Copy-to-start skeleton for a new brand. |
| `skills/brand-voice/data/capabilities-ground-truth.yaml` | The claim bank. Every approved factual claim with evidence. |
| `skills/brand-voice/commands/` | `/enforce-voice`, `/score-route`, `/discover-brand` slash commands. |
| `journey/` | The 4-step Peel → Press → Lock → Pour walkthrough you can run on your own brand. |
| `examples/before-after/` | Redacted before/after pairs showing what the scorer catches. |
| `docs/IS-IT-ACCRETIVE.md` | Audit of whether the system actually compounds (spoiler: mostly yes, with named gaps). |

---

## The 4-layer scorer, in one diagram

```
Input: text + brand_slug + surface + audience + phase
                   │
                   ▼
   ┌───────────── Layer 1: REGEX ──────────────┐   weight 0.15
   │ banned words │ canon presence │ trademarks │   <10ms
   │ vague quantifiers │ sentence length caps   │   any banned word → block
   └────────────────────┬───────────────────────┘
                        ▼
   ┌───────────── Layer 2: RULES ──────────────┐   weight 0.20
   │ three moves present │ first-person         │   booleans, no LLM
   │ Jeff/Meadows attributed │ receipt present  │   −8 per rule failed
   │ Yuzu-phase mapped │ no phase/gate confusion│
   └────────────────────┬───────────────────────┘
                        ▼
   ┌─────────── Layer 3: EMBEDDING ────────────┐   weight 0.25
   │ cosine to top-K=5 approved exemplars      │   Qdrant local
   │ cosine to top-K=3 trauma entries          │   p95 < 400ms
   │ drift detection vs surface-cluster        │
   └────────────────────┬───────────────────────┘
                        ▼
   ┌─────────── Layer 4: LLM RUBRIC ───────────┐   weight 0.40
   │ Sonnet 4.6 primary │ Grok 4.1-fast bulk   │   T=0, JSON out
   │ 15 dims × 0..10    │ 8-criterion sub-check│   3-retry fail-loud
   └────────────────────┬───────────────────────┘
                        ▼
   ┌────────── GROUNDING (mandatory) ──────────┐   every factual claim
   │ extract numbers/benchmarks/capabilities   │   regex-matched
   │ match against capabilities-ground-truth   │   unmatched → block
   └────────────────────┬───────────────────────┘
                        ▼
               composite = Σ(weight × layer)
                        │
        composite ≥ 95 AND min(dim) ≥ 9 AND no banned AND grounded
                        │
                        ▼
                       SHIP
```

Any layer can reject. The composite is a convenience; the gates are where the work happens.

---

## The Meadows frame, in one table

| Level | Stocks | Flows | Loops |
|---|---|---|---|
| **What accumulates** | S.EXEMPLAR (approved copy corpus)<br>S.TRAUMA (known failure modes)<br>S.LIVE (deployed surfaces)<br>S.RECOGNITION (audience trust, slow)<br>S.RULES (codified machine-checkable)<br>S.DRIFT (off-voice shipped but not caught)<br>S.CAPABILITIES (ground-truth claim bank) | writing_rate → S.LIVE<br>review_rate → S.EXEMPLAR or S.TRAUMA<br>trauma_capture_rate → S.TRAUMA<br>rule_promotion_rate → S.RULES (at recurrence ≥3)<br>drift_decay_rate → reduces S.DRIFT | R1 virtuous: exemplars → quality → trust → more exemplars<br>R2 vicious: drift in corpus → drift in new copy (must cap)<br>B1 primary gate: voice-gate caps drift before ship<br>B2 learning: trauma → new rule<br>B3 slow: recognition vs quality gap → audit |

The **R2 vicious loop** is the one most brand-voice systems ignore. If off-voice pages get sampled as exemplars, the LLM learns them, future output drifts more, and the corpus poisons itself within weeks. Weekly re-audit + quarantine under 90 composite breaks that loop. See `skills/brand-voice/references/METHODOLOGY.md §3`.

---

## What you need to run the scorer end-to-end

You can use most of this repo as markdown-only (read the methodology, apply it mentally, manually grade your copy). That gets you 70% of the value.

The full scorer needs:

| Dependency | What for | Optional? |
|---|---|---|
| Claude Code | Slash commands + skill loading | Yes — docs are usable standalone |
| Anthropic API key (Sonnet 4.6) | Layer 4 LLM rubric | Yes — xAI Grok 4.1-fast works as drop-in |
| Qdrant (local, `:6433`) | Layer 3 embeddings | Yes — skip layer, reweight 0.20/0.27/0.53 |
| Ollama + `nomic-embed-text` | 768-dim local embedder | Only if running Qdrant |
| Python 3.11+ | `scripts/score.py` reference implementation (stub) | Only if scripting outside Claude Code |

Zero of these are required to read `journey/01-peel-discover.md` and start running the system by hand. I'd encourage you to do exactly that for your first brand — the automation is an optimization on top of the method, not a replacement for it.

---

## The journey (Peel → Press → Lock → Pour)

Four steps. Run them on your own brand or a client's. Each step has its own file in `journey/`:

1. **Peel — Discover.** Scrape the current site, cluster phrasings, founder interview, mine artifacts. Outputs: raw corpus + founder transcript + cringe list. Time: 4–8 hours.
2. **Press — Define.** Fill `voice.yaml`, draft `WE_ARE.md`, build `TONE_MATRIX.md`, seed `capabilities-ground-truth.yaml`. Outputs: the enforceable config. Time: 3–4 hours.
3. **Lock — Validate.** Dry-run the scorer on 5 existing pages. Calibrate thresholds. Hand-curate 20+ exemplars. Outputs: working rubric + exemplar seed. Time: 3–4 hours.
4. **Pour — Activate.** Slash-command integration, pre-commit hooks, CI scoring, weekly drift audits. Outputs: the thing runs without you remembering to think about it. Time: 2–3 hours.

Total: 12–18 hours for a brand you care about. Not a weekend project. The bet is that 12 hours of front-loading prevents the 40+ hours of per-piece voice rewriting most brands do reactively.

---

## Two working examples

**`skills/brand-voice/brands/zeststream/`** — my own consulting site. Canon line is "I build things that work, and I show you the receipt." First-person singular. 96 production n8n workflows as the big receipt. This is the brand I dogfooded the system on; the redacted public version has the rubric and banned words intact but strips my open internal questions.

**`skills/brand-voice/brands/acme-saas/`** — fictional B2B SaaS, third-person plural, completely different posture. Exists so you can read a clean reference without decoding my positioning. If you're forking this for a client, start here, not with zeststream.

Both brands share the same algorithm, the same 15-dim rubric, the same grounding pass. Only the config differs. That's the point of the brand-agnostic / per-brand-config split.

---

## Is this actually accretive? (the audit)

This matters because most "brand voice tools" are a one-shot PDF generator — you run them once, get a document, and that document drifts the minute a new page ships. A real system has to compound: each session should leave the brand voice *stronger*, not just *used*.

I audited this against that question and wrote up the answer at `docs/IS-IT-ACCRETIVE.md`. Short version: R1 virtuous loop compounds (exemplars → quality → more exemplars), R2 vicious loop is capped (quarantine cron), B2 learning loop compounds (trauma → rule), B3 slow audit loop runs weekly. The two places where accretion *doesn't yet work* — feedback from real SMB readers (item U/Y in Grok's A-Z framework) and automated per-route drift re-scoring — are named in the doc with specific next-step fixes.

If that doc ever stops being true, the system has become static and someone (probably future-me) should delete parts of the repo and re-think.

---

## Install

### As a Claude Code plugin

```bash
git clone https://github.com/JYeswak/zeststream-brand-voice.git
cd zeststream-brand-voice
./scripts/install.sh
# Claude Code will auto-discover skills/brand-voice on next session start
```

### As markdown reference only

```bash
git clone https://github.com/JYeswak/zeststream-brand-voice.git
# open skills/brand-voice/references/ in your editor of choice
# open journey/ and walk the four steps
```

### As a starting point for your own brand

```bash
cp -r skills/brand-voice/brands/_template skills/brand-voice/brands/<your-slug>
# fill in voice.yaml, WE_ARE.md, TONE_MATRIX.md
# run journey/01-peel-discover.md to build your claim bank
```

---

## Slash commands (requires Claude Code)

| Command | What it does |
|---|---|
| `/enforce-voice <content>` | Load brand, apply voice constants + tone matrix + grounding, output with "Voice decisions" note. |
| `/score-route <path or text>` | Score against 15-dim rubric, output composite + dim breakdown + regen hints. |
| `/discover-brand <slug> <url>` | Run the 9-step DISCOVER flow for a new brand (4–8 hours of work). |

See `skills/brand-voice/commands/` for the prompt definitions.

---

## What this isn't

- A SaaS product. It's a markdown + YAML system you run yourself.
- An LLM fine-tuning harness. The enforcement is prompt-level + mechanical, not weight-level.
- A replacement for human taste. The scorer is a proxy for trust, not a judge of it. Every composite-≥95 draft should still pass through a human who owns the brand.
- A general-purpose style checker. It's opinionated about brand voice specifically — a different use case (academic writing, legal drafts, fiction) would want a different rubric.
- Finished. Several Grok-A-Z items (SMB capability surveys, A/B infra, ROI tracking) are named as gaps in `docs/IS-IT-ACCRETIVE.md`. Patches welcome.

---

## Related projects / prior art

- **anthropics/knowledge-work-plugins** (`partner-built/brand-voice/`) — the partner-built plugin from Tribe AI. Different shape: single LLM gate, RAG-over-brand-artifacts, enterprise source connectors (Notion / Drive / Slack / Gong). Good patterns; I ported three of them (strictness settings, confidence scoring, open-questions). Not ported: their single-gate enforcement (too fragile) and their lack of claim-grounding (the 2026-04-19 hallucination pivot is the reason for this repo's existence).
- **justinGrosvenor/alignmenter** — persona packs in YAML with per-scenario playbooks and on-brand/off-brand example pairs. Their Wendy's Twitter persona is a masterclass in voice-as-config. I ported three blocks verbatim (`situation_playbooks`, `voice_examples_by_context`, `boundaries`) in v0.2. Their post-generation authenticity scorer is orthogonal to this repo's pre-generation enforcement; complementary, not competitive.
- **houtini-ai/voice-analyser-mcp** — 16-analyser linguistic fingerprinting (sentence length, burstiness, function-word z-scores, etc.) that extracts a brand voice from corpus rather than from a questionnaire. I ported the 9 most useful analyses into `references/CORPUS_SIGNATURES.md` and added `rhythm_variance` as the 16th dim in v0.2. Their full MCP is worth installing alongside if you want the remaining 7 analysers.
- **jgerton/brand-toolkit** — 4-test anti-slop pattern (swap / specificity / differentiation / business-type). I use those tests as the human layer above the mechanical scorer.
- **Donella Meadows, *Thinking in Systems* (2008) and "Dancing with Systems" (2001)** — the frame. If you only read one thing before forking, read "Dancing with Systems" (it's ~15 pages and online free).
- **Jeff Emanuel** — I use NTM / Agent Mail / beads / CASS in my own workflow. Not in this repo, but mentioned throughout. Cite him if you adopt his tools.

---

## Visual identity

Meet **Operator Yuzu** — the ZestStream mascot and the character who anchors every visual asset across this brand-voice system. Yuzu is an anthropomorphic yuzu citrus fruit rendered as a senior-operator presence: quiet competent smile, slightly weathered, kind eyes, canvas apron over a cream henley with rolled sleeves, wood-handled clipboard always in hand. The work IS the image — Yuzu always does what the repo or tool does. When a repo runs discovery, Yuzu is peeling; when a repo transforms raw material, Yuzu is at the workbench; when a repo ships, Yuzu is pouring. The character stays constant so the scene can vary.

![Operator Yuzu](visual/yuzu_canonical.jpg)
*Canonical character anchor — use as `--cref` input for every future generation to lock likeness across scenes.*

| Asset | Path | Use |
|---|---|---|
| Canonical character | `visual/yuzu_canonical.jpg` | `--cref` anchor for all future generations |
| GitHub avatar | `visual/yuzu_avatar_square.jpg` | 1:1 repo avatar, social profile |
| Repo hero | `visual/scenes/zeststream_brand_voice_hero.jpg` | README hero, GitHub social preview |
| PEEL template | `visual/scenes/peel_phase_discovery.jpg` | Discovery / research / audit repos |
| PRESS template | `visual/scenes/press_phase_workbench.jpg` | Build / tooling / transform repos |
| POUR template | `visual/scenes/pour_phase_delivery.jpg` | Launch / delivery / ship repos |
| Explainer banner | `visual/scenes/yuzu_method_explainer.jpg` | Yuzu Method explainer, /consult, about pages |

See [visual/character-bible.md](visual/character-bible.md) for the full character specification — banned variants, palette hex values, scene patterns, and generation workflow.

**Yuzu Method® rendering note.** First use per asset must render "The Yuzu Method ®" with the registered symbol. The motto renders as "Peel. Press. Pour.™" — periods between words, trademark symbol after the third word. These are non-negotiable; the voice-gate auto-rejects assets that drop the marks.

---

## License

MIT. Fork it, modify it, sell services around it, don't relicense it as AGPL and ship it back to me.

---

## Who built this

Joshua Nowak. Solo operator, Montana. 14 years at ZIRKEL before the 2024 acquisition, led tech ops at ElektraFi through end of 2025, now running ZestStream full-time. I wire AI into businesses that already work — 96 production n8n workflows at `n8n.zeststream.ai`, a rebuilt 8-GPU inference stack for CubCloud, a cache-hit optimization that went from 0.007% to 6.37% on a 2-line regex (910× improvement, measured). If you're stuck between "AI headlines everywhere" and "my systems don't talk to each other," book a 20-minute Peel session at zeststream.ai/consult. $0, specific, no pitch.

Canon: *I build things that work, and I show you the receipt.* This repo is one of those receipts.
