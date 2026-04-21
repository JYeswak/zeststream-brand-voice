# Changelog

## v0.6.0 — 2026-04-21 — Write quadrant + dual-provider LLM

First production-grade write-quadrant surface: the tool now generates
on-brand copy, not just scores it. Scoring stays deterministic; only
the draft/rewrite steps call an LLM.

### Added

- **`zv draft <surface> <topic>`** — generate a new piece of copy for a
  brand surface. Three surfaces wired end-to-end: `x` (<=280 chars,
  receipt required), `linkedin` (150-200 words, 1 insight, soft invite),
  `page` (30-50-word hero, canon verbatim). Five surfaces
  (`facebook`, `instagram`, `email`, `meta`, `blog`) accepted by the CLI
  but raise a clear "not yet implemented in v0.6" error — wired in
  v0.6.1+.
- **`zv rewrite <file>`** — transform off-brand copy into brand voice
  with BEFORE/AFTER composite-score delta and unified diff output. The
  "put ANY business wording into their brand voice" command.
- **LLM foundation** under `src/zeststream_voice/llm/`:
  - `AnthropicClient` — Claude Messages API with prompt caching on the
    voice.yaml system block (cuts per-call cost ~10× on repeat calls).
  - `GrokClient` — xAI `grok-4` provider for tech-register content.
  - `get_llm_client(model=...)` factory routes by model prefix
    (`claude*` → Anthropic, `grok*` → xAI). `ZV_LLM_PROVIDER` /
    `ZV_LLM_MODEL` env overrides.
  - `build_voice_context(brand_path, surface)` — assembles the
    cached system prompt from voice.yaml + exemplars + situation
    playbooks.
  - `generate_with_voice_gate(...)` — draft → score → revise regen loop
    capped at `--max-attempts` (default 3). Scorer feedback (banned
    hits, weak layers) is injected into the rewrite prompt on each
    failed pass.
- **Optional install extras**: `pip install 'zeststream-voice[rubric]'`
  for Anthropic, `pip install 'zeststream-voice[grok]'` for xAI. Both
  are optional so the judge quadrant stays installable with zero LLM
  dependencies.

### Changed

- `zv draft` + `zv rewrite` both route through `get_llm_client(model)`
  so the `--model` flag picks a provider transparently.
- System prompt structure: voice.yaml sections serialised verbatim so
  the model sees the same constants the scorer enforces (no paraphrase
  drift between draft-time and score-time).

### Not yet (deferred to v0.6.1)

- **`zv reply <email-file>`** — inbound-email response drafter consulting
  qa-matrix + boundaries + trauma.jsonl + exemplars.
- **`zv history` / `zv tag` / `zv revert` / `zv diff`** — voice
  versioning with semantic tags over `voice.yaml` git SHAs.

### Spec

Full vision: `.planning/brand-voice-cli/10-write-quadrant-vision.md` (in
zesttube repo, not committed here). Ships as the basis for daily-use
retention; peel is the setup, write is the flywheel.

---

## v0.5.0 — 2026-04-21 — Peel wizard + Vale-shape rules + canon migration

First end-to-end onboarding path. A new brand goes from zero to working
voice.yaml via a conversational wizard, and rules ship as individual
files a client can grep, edit, and test.

### Added

- **`zv peel <slug>`** — conversational 9-block wizard that emits a
  working `voice.yaml`. Blocks 1 (IDENTITY) and 2 (CANON) are fully
  wired and produce valid output; blocks 3-9 stubbed with a "not yet
  implemented, skipping" notice for v0.5.1. Features:
  - 7-item pre-flight (slug format, brand dir, template fallback,
    state-file handshake, writable check, YAML round-trip sanity,
    operator-name deferral).
  - `.peel-state.json` persistence with atomic tmp+rename writes so a
    mid-flight crash resumes cleanly.
  - `--resume` / `--force` / `--skip-block` flags with per-block
    precondition gating.
  - Corrupt-state recovery prompt (resume / abort / discard) with a
    `.peel-state.json.corrupt.<epoch>` backup before discard.
  - `voice.yaml` round-trip validated through `yaml.safe_load` after
    every merge (session-14 silent-failure guard).
  - Vale-compatible word tokenizer (`_word_count`) so canon length
    warnings match downstream scorer behaviour.
- **22 Vale-shape rule files** under `brands/<slug>/rules/` — rules
  split from monolithic voice.yaml blocks into addressable YAML files
  with acceptance tests (fail/pass fixtures). Each rule is
  individually testable and editable by non-Python clients.
- **`scripts/test_rules.py`** — rule acceptance test harness. Walks
  every `rules/*.yaml`, runs its fail/pass fixtures through the layer-2
  rule engine, reports pass/fail per rule. 22/22 green at ship.

### Changed

- **Canon migration**: `canon.primary` was "I build things that work,
  and I show you the receipt." — now **"I help SMB owners buy their
  time back."** The buy-time-back line positions for the SMB-operator
  audience; the receipt discipline is preserved in the `receipt_shown`
  rubric dimension, `three_moves.show_receipt`, and the
  `claims_ungrounded` grounding layer (all unchanged).
- New variants approved for `/about` and opener use:
  - "I help SMB owners buy their Tuesdays back."
  - "I am Joshua. I build things that work."
  - "Most consultants hand you a slide deck and leave. I hand you a
    working system."
- Old canon demoted to `operating_principle` — still load-bearing, no
  longer the headline. See
  `.planning/brand-voice-cli/08-canon-migration.md` (in zesttube repo)
  for the rationale.

### Fixed

- 2 P0 + 6 P1 findings from the Wave B peel code review, each with a
  regression test in `tests/test_peel.py`:
  - P0-1 — voice.yaml and `.peel-state.json` are backed up before
    `--force` overwrite / discard, so a bad wizard run is reversible.
  - P0-2 — corrupt `.peel-state.json` offers a three-way recovery
    (resume / abort / discard) instead of crashing.
  - P1-1 — rejected prompts re-offer the last entered value as default
    so users can edit, not retype.
  - P1-2 — domain validation rejects leading/trailing dashes, empty
    labels, <2-char TLDs.
  - P1-3 — `_atomic_copytree` stages to `.tmp` + renames so a crashed
    pre-flight never leaves a half-built brand dir.
  - P1-4 — canon word-count tokenizer binds hyphenated and
    apostrophised words (Vale-compatible), preventing false-positive
    length warnings.
  - P1-5 — `merge_to_voice_yaml` raises on non-round-trippable YAML or
    missing `brand:` key, making silent corruption impossible.
  - P1-6 — state file is written via tmp+rename, matching the P0-1
    backup semantics.

---

## v0.2 — 2026-04-19 (unreleased)

Three patterns ported from brand-voice-tool research (alignmenter + houtini).

### Added

- **`situation_playbooks`** block in `voice.yaml` — per-scenario response rules for customer_service / competitor_mention / product_promo / community_engagement / crisis_response. Ported from alignmenter's Wendy's example. Used by Layer 2 to catch scenario/register mismatches (e.g. sales-pitch register on a crisis response).
- **`voice_examples_by_context`** block — pre-paired on-brand/off-brand examples scoped to moment (greeting / problem_acknowledgment / call_to_action / product_mention / competitor_reference). Used as few-shot priors in Layer 4 LLM rubric prompts.
- **`boundaries`** block — per-category positive/negative pairs (tone / humor / scope / pricing). "X, not Y" pairs that Layer 2 enforces as soft rules.
- **`rhythm` + `corpus_signature`** blocks — stylometric fingerprint (sentence-length mean + stdev + burstiness, top starters, complexity distribution, zero-tolerance-pattern list). Ported from houtini/voice-analyser-mcp. Extracted once from approved corpus during Peel; used by Layer 1 to detect AI-slop rhythm at scoring time.
- **`rhythm_variance` rubric dim** — 16th dim. Sentence-length coefficient of variation must fall within per-brand target band. Catches the AI-slop failure mode: copy that passes every other gate but reads mechanical because sentence lengths cluster.
- **`references/CORPUS_SIGNATURES.md`** — ~200-line reference for the 9 signatures, the ~60-line Python reference implementation, integration with the 4-layer scorer, and attribution.
- **`journey/01-peel-discover.md §4.5`** — new "Corpus analysis" step in Peel. Scrape → run `scripts/analyze_corpus.py` → populate `voice.yaml.corpus_signature` → set `rhythm.*.target`.
- **`acme-saas` brand fully populated** with all v0.2 blocks as a clean reference.
- **`zeststream` brand fully populated** with all v0.2 blocks grounded in actual capabilities.

### Changed

- `rubric.version`: 1 → 2 (v0.2 schema)
- `rubric.kind`: `composite_15_dim` → `composite_16_dim`
- `_template/voice.yaml` now includes all v0.2 blocks as fill-in stubs
- `rhythm` dim in the existing rubric (qualitative) remains; `rhythm_variance` (quantitative) is additive, not a replacement

### Attribution

- `situation_playbooks` / `voice_examples_by_context` / `boundaries` structure — adapted from [justinGrosvenor/alignmenter](https://github.com/justinGrosvenor/alignmenter) (Wendy's Twitter persona). MIT-compatible.
- `rhythm` / `corpus_signature` / 9-signature extraction — adapted from [houtini-ai/voice-analyser-mcp](https://github.com/houtini-ai/voice-analyser-mcp). MIT-compatible.
- Research context for which patterns to port (and which to skip) — see `docs/IS-IT-ACCRETIVE.md` §Gap 1 closure and the repo commit history.

### Not ported (deliberate)

Seven tools surveyed; three ported above. Skipped:

- **Voicebox (Nick Parker)** — physical product + workshop guide. Not automatable. Deferred as client-delivery tool (not repo content).
- **Typetone.ai** — SaaS with post-publish audit. Requires infra not available to target SMB users.
- **Word.studio, Portent, DXPR** — shallow or dead. Post-Tier-1 discovery UX deferred to a possible `discover-quiz` companion skill.

See `docs/IS-IT-ACCRETIVE.md` §"What IS already accretive" for verification that the v0.2 adds close the R2 drift loop with a faster statistical trigger (not just semantic quarantine).

---

## v0.1 — 2026-04-19

Initial public release. Core skill + 4-layer scorer + grounding pass + Meadows methodology + Peel→Press→Lock→Pour journey + IS-IT-ACCRETIVE audit + two worked brands (zeststream live, acme-saas fictional).
