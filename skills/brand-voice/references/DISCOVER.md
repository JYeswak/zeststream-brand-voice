# DISCOVER — onboarding a new brand

> *"Get the beat of the system before you disturb it."* — Donella Meadows

Run this flow once per new brand (Blackfoot, ALPS, TerraTitle, future clients). Never write new copy for a brand whose voice hasn't been discovered. Imposing ZestStream voice onto another brand is the failure mode this file exists to prevent.

**Estimated time:** 4–8 hours for a real client brand. Not a 20-minute task.

---

## Prerequisites

- Client URL (primary site)
- Access to at least one of: client's Notion, Google Drive, Slack, meeting recordings
- An hour with the founder/operator (interview, not survey)
- Recent customer-facing artifacts: 3+ emails, 1+ sales deck, any blog posts

---

## The 9-step flow

### 1. Scrape the site (1 hour)

```bash
# pseudo-command — adapt to tooling
./scripts/scrape-brand-site.sh <url> --output brands/<slug>/_raw/
```

Pull every page into `brands/<slug>/_raw/`. Markdown-ize. Strip nav/footer. Keep:
- H1, H2, H3 (structure)
- Body prose (content)
- CTAs (what are they asking for?)
- Meta descriptions (how does the brand summarize itself for search?)
- Any testimonials (language customers use)

### 2. Cluster phrasings (45 min)

Embed each page section into Qdrant under `brand_voice_raw_<slug>`. Cluster by cosine. Output:
- Top 10 most-repeated phrases
- Register spread (how much variation exists across pages?)
- Pronoun posture ("we" dominant? "I"? "you"? none?)
- Sentence-length distribution
- Trademark / brand-term rendering consistency

### 3. Founder interview (60–90 min, recorded)

Not a survey. An interview. Ask:

- **Origin:** How did you start? What problem did you first solve for a real customer?
- **Identity:** If a customer described you in one sentence, what would they say? What would you *want* them to say?
- **Voice reference:** What two other companies do you admire the communication of? Why?
- **Anti-voice:** Show them 3 copy samples you think are *bad* on their site. Why bad?
- **Claim bank:** Walk through 10 specific claims you make. For each, what's the receipt?
- **Audience:** Who specifically reads your site? Operator? Customer? Candidate? Investor? Rank in % of your real audience.
- **Phase:** Where is most of your customer's journey stuck? Discovery (peel)? Build (press)? Adoption (pour)?
- **Banned words:** Are there any words that make you cringe when competitors use them?
- **Canon:** What's the one sentence that summarizes what you do? (First draft — will refine.)
- **Three moves:** Name a specific person. Show a receipt. Invite. Do they already do this? Where?
- **Limits:** What do you NOT do? What misconceptions about you do you want to kill?

**Record.** Transcribe. Index into Qdrant under `brand_voice_interviews_<slug>`.

### 4. Mine artifacts (45 min)

For each of: emails, decks, recordings, posts:
- What pronouns?
- What phrases recur?
- What's the sentence-length distribution?
- What's the claim-to-hedge ratio?

This is where the **actual** voice lives, not the aspirational voice in the site copy. Weight actual over aspirational 70/30 when conflicts arise.

### 5. Draft `voice.yaml` (90 min)

Copy `brands/_template/voice.yaml` → `brands/<slug>/voice.yaml`. Fill:

- `canon.primary` — the one sentence
- `canon.variants_approved` — 1–2 shorter variants
- `posture.voice` — first-person singular / first-person plural / second-person / third-person
- `posture.pronouns_allowed` / `pronouns_banned`
- `three_moves` — adapt to brand (some brands won't do `name_person`; pick three that work)
- `banned_words` — cross-reference from §2 cluster (their own over-used words) + §3 cringe-list + the universal consultant-tells list (enterprise, transformation, etc.)
- `trademarks` — what trademarks / brand-terms must render consistently?
- `rubric.dimensions` — can start from the 15-dim default; prune or adjust weights per brand need
- `surfaces` / `audiences` — from §3 founder ranking
- `word_caps_per_route` — 800 default; adjust per site depth

### 6. Draft `WE_ARE.md` (45 min)

12 We Are rows, 12 We Are Not rows. Each with evidence. If a row lacks evidence → either cut it or flag for §9 (gaps to fill with real receipts).

### 7. Draft `TONE_MATRIX.md` (45 min)

Fill the surface × audience × phase grid. At least 3 worked examples.

### 8. Draft `capabilities-ground-truth.yaml` (60 min)

Seed with all 10+ claims the founder walked through in §3. Each entry: `id`, `claim`, `canonical_phrasing`, `source{type, location, timestamp}`. If the founder can't produce a source → don't add it. Note in §9 gaps instead.

### 9. Calibrate thresholds (30 min)

Dry-run the scorer on 5 existing pages. Typical first-run results:

- Composite 60–75 for old copy (normal — it was written pre-system)
- Banned words present (normal — every brand has accumulated drift)
- Claims ungrounded (normal — grounding is the new layer)

Decide: do we **rewrite** old copy to the system, or do we **grandfather** old copy and enforce the system only on new writes going forward? For new client brands, grandfather first, rewrite during Press phase of their engagement.

Record decision in `brands/<slug>/calibration.md`.

### 10. Build exemplar seed (90 min)

20+ annotated before/after pairs. Source: §2 clusters (best existing) + §4 artifacts (best real voice). Rewrite each to hit composite ≥95 if needed. File under `brands/<slug>/exemplars/<surface>/<slug>.md` with YAML frontmatter per `voice.yaml.exemplars.schema`.

---

## Output

Delivered at end of DISCOVER:

```
brands/<slug>/
├── voice.yaml
├── WE_ARE.md
├── TONE_MATRIX.md
├── calibration.md          # threshold decisions + baseline scores
├── exemplars/
│   ├── hero/*.md
│   ├── body/*.md
│   └── cta/*.md
├── _raw/                   # scraped site + interview transcripts (not tracked)
└── _interview/
    ├── recording.mp3
    └── transcript.md

data/capabilities-ground-truth.yaml  # updated with brand entries (tagged brand:<slug>)
```

---

## What NOT to do

1. **Don't rush DISCOVER.** A half-discovered brand produces drift-prone scoring. The 4–8 hours is the compounding investment.
2. **Don't skip the founder interview.** A site scrape alone gets you aspirational voice, not actual voice. The two always diverge; the actual voice is what the brand really is.
3. **Don't import ZestStream voice constants wholesale.** Each brand gets its own canon, banned words, three moves. The skill's algorithm is brand-agnostic; the config is per-brand.
4. **Don't claim a receipt the founder can't produce.** If `capabilities-ground-truth.yaml` has no entry, copy can't make the claim. This is the 2026-04-19 pivot's discipline applied outward.
5. **Don't auto-promote to exemplars in week 1.** Hand-curate the seed. After 30 days of live scoring, promotion-cron takes over.

---

## Signal that DISCOVER is complete

Ask yourself:
- Can I predict what a founder would reject in a draft, before showing it to them?
- Can I write a hero section that scores ≥95 on first pass?
- Can I point to the exact rule that rejects a specific failed draft?

If yes to all three → DISCOVER done. Start writing.
If no to any → more time in §3 (interview) or §4 (artifacts). Not in §5 (drafting).

---

## Meadows footnote

The reason DISCOVER takes 4–8 hours and not 30 minutes is that brand voice is a **paradigm** (Meadows leverage #2). Paradigms sit underneath everything else. Getting them wrong early means every downstream intervention is working against the grain.

Investment in DISCOVER is the only place this skill asks you to slow down. Everywhere else, the system is designed to be fast. Here: measure twice, cut once. Or, in Meadows' phrasing: *"Get the beat of the system before you disturb it."*
