# Changelog

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
