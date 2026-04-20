# Step 1 — Peel: discover

> *"Get the beat of the system before you disturb it."* — Donella Meadows, *Dancing with Systems*

## What you're doing in this step

Listening. You're building a snapshot of the brand's **current voice** (aspirational + actual) before you write a single rule. You are NOT defining anything yet. You are reading, scraping, interviewing, and categorizing.

**Output:** a raw corpus + founder interview transcript + cringe list + a Voice Health Report that names the gap between what the brand wants to sound like and what it currently sounds like.

## Prerequisites

- Brand URL (primary site)
- 60–90 minutes scheduled with the founder/operator (recorded, with permission)
- Access to at least one of: past emails, sales decks, meeting recordings, blog posts, social posts
- A clean `brands/<slug>/` directory created from `brands/_template/` (but don't fill it yet)

## The work

### 1. Scrape the site (60 min)

Pull every page the brand owns. Markdown-ize. Strip navigation and footers. Keep:

- H1, H2, H3 (structure)
- Body prose
- CTAs (what are they asking for?)
- Meta descriptions
- Any testimonials (language customers use)

Store raw output at `brands/<slug>/_raw/site-<YYYYMMDD>/`. Not tracked in git; too noisy.

Quick command if the site is a static Next.js or Hugo site:

```bash
# simple recursive fetch, adapt to taste
wget --recursive --level=2 --convert-links --no-parent \
  --exclude-directories=/assets \
  -P brands/<slug>/_raw/site-$(date +%Y%m%d) \
  https://<brand-domain>/
```

For JS-heavy sites, use a headless browser (Playwright) or similar. The tool doesn't matter; the completeness does.

### 2. Cluster phrasings (45 min)

Read through the scraped pages. Answer these questions, write answers to `brands/<slug>/_raw/clusters.md`:

- **Top 10 most-repeated phrases** (exact strings, count occurrences)
- **Pronoun posture** — is it "we," "I," "you," or none? Mixed? Where does it drift?
- **Sentence-length distribution** — mostly short, mostly long, or mixed? By surface (hero vs body)?
- **Trademark / brand-term rendering consistency** — is the company name always rendered the same way? Any method or product trademarks rendered inconsistently?
- **Register spread** — how much does tone vary across pages? Is the About page a different brand than the Pricing page?

If the site uses an embedder you can query (Qdrant, pgvector, etc.), cluster sections by cosine similarity and look at the top 10 clusters. If not, read by hand. Either way, 45 minutes is enough.

### 3. Interview the founder (60–90 min)

Record this. Transcribe it afterward. Don't skip.

Not a survey. An interview. Ask these, in roughly this order:

- **Origin.** How did you start? What was the first problem you solved for a real customer?
- **Identity.** If a customer described you in one sentence, what would they say? What would you *want* them to say? (The gap between these two answers is often where the brand lives.)
- **Voice reference.** What two other companies do you admire the communication of? Why?
- **Anti-voice.** Show them 3 copy samples you think are *bad* on their own site. Why bad?
- **Claim bank.** Walk through 10 specific factual claims the brand makes. For each, what's the receipt? (Benchmark? Repo? Client doc? Or nothing — they hope it's true?)
- **Audience.** Who specifically reads the site? Operator? Customer? Candidate? Investor? Rank by real % of audience, not wished %.
- **Phase.** Where is most of your customer's journey stuck? Discovery, build, or post-ship adoption?
- **Banned words.** Are there words that make you cringe when competitors use them? (These become your first-draft banned-words list.)
- **Canon.** What's the one sentence that summarizes what you do? Rough draft — it'll refine.
- **Limits.** What do you NOT do? What misconceptions do you want to kill?

Index the transcript somewhere searchable (a vector store is fine, plain markdown grep is also fine). Store at `brands/<slug>/_interview/transcript.md`.

### 4. Mine artifacts (45 min)

For each of the following that exists — 3+ emails, 1+ sales deck, any blog posts, any meeting recordings:

- What pronouns?
- What phrases recur?
- Sentence-length distribution?
- Claim-to-hedge ratio? (Every time a number appears, is there a source? Or is it "roughly" / "about" / "most"?)

This is where the **actual** voice lives, not the aspirational voice in the site copy. When artifacts and site diverge (they will), **weight artifacts 70/30 over site** — the unconscious voice is truer than the polished voice.

Store findings at `brands/<slug>/_raw/artifacts-analysis.md`.

### 4.5. Run corpus analysis to extract stylometric signature (30 min, v0.2)

The site scrape from step 1 is your corpus. Run the 9-signature extraction to populate `voice.yaml.corpus_signature` and set rhythm targets.

```bash
# concatenate scraped pages into a single corpus file
cat brands/<slug>/_raw/site-*/\*.md > brands/<slug>/_raw/corpus.txt

# run the reference implementation
python scripts/analyze_corpus.py brands/<slug>/_raw/corpus.txt \
  > brands/<slug>/_raw/signature.yaml

# review the output — does mean sentence length feel right?
# is burstiness in the human range 0.35–0.65?
# are top starters varied enough (top 3 ≤ 30% of all)?
cat brands/<slug>/_raw/signature.yaml
```

What to look for:

- **Burstiness < 0.30** — existing copy is already AI-slop monotone. Flag this in the Voice Health Report (the brand's *current* voice has already drifted toward LLM default). Target rhythm should be higher than current.
- **Mean sentence length > 25** — academic/corporate register. If SMB audience, this is a structural problem.
- **Top starter > 15% of sentences** — the brand opens sentences with the same word too often. Add to `banned_phrases` or flag for rewrite.
- **Complex clauses dominant** — reads as bureaucratic. Target simple:compound:complex ≈ 0.5:0.3:0.2 for accessible copy.

Copy the signature values into `voice.yaml.corpus_signature` in step 2 (Press). Set `voice.yaml.rhythm.*.target` from signature, with a judgment call on tolerances (typical: ±5 words mean, ±0.1 burstiness).

**Why this matters:** without a measurable rhythm fingerprint, you can't detect the AI-slop failure mode at scoring time — the one where copy passes every other gate but reads mechanical because sentence lengths cluster at 15±2 words. See `references/CORPUS_SIGNATURES.md` for the algorithm + integration with the 4-layer scorer.

**If you're not running the scorer yet:** skip to step 5. Come back to corpus analysis during Press (step 2) when you populate `voice.yaml`.

### 5. Write the Voice Health Report (30 min)

One markdown file at `brands/<slug>/voice-health-report-<YYYYMMDD>.md`. Structure:

```markdown
# [Brand] — Voice Health Report, <date>

## Events layer (what we see on the surface)
- [3–5 specific on-page observations, e.g. "Homepage hero uses 'enterprise-grade' 4 times"]

## Patterns layer (what keeps happening)
- [3–5 repeated patterns across pages, e.g. "Every CTA starts with 'Discover'"]

## Structures layer (what produces these patterns)
- [2–3 structural causes, e.g. "Webflow template defaults, no banned-words list, marketer rewarded for page count"]

## Mental models layer (what the brand/team believes)
- [2–3 beliefs decoded from the above, e.g. "Believes enterprise posture = credibility, when audience is actually SMB operators"]

## The gap
- **Aspirational voice:** [1–2 sentences from the founder interview]
- **Actual voice:** [1–2 sentences from the artifact mining]
- **Size of gap:** [small / medium / large / brand-identity-crisis]

## Mental Model Shift Goals
- From "[current belief]" → "[target belief]"
- From "[current belief]" → "[target belief]"
- From "[current belief]" → "[target belief]"
```

This is the iceberg model applied to voice. Events → patterns → structures → mental models. Every brand has all four layers; most brand-voice projects only fix events.

## Stop conditions

You are done with Peel when:

1. You can predict what the founder will reject in a draft, **before showing them**.
2. You can name 3–5 specific phrases the brand over-uses and 3–5 it under-uses.
3. You can name the iceberg-level gap (events / patterns / structures / mental models).
4. You have at least 10 candidate factual claims written down, each with a source-status (Yes / No / Unsure).

If you can't answer any of those: more time in interview or artifact mining. Not in drafting. **Do not advance to Press until these hold.**

## Anti-patterns (common ways to get Peel wrong)

1. **Skipping the founder interview** because "we can see the voice from the site." No. The site is aspirational voice. The interview reveals the delta with actual voice.
2. **Weighting aspirational over actual.** Every brand describes itself as it wants to be, not as it is. The artifacts (emails, call recordings) are the ground truth.
3. **Spending 8 hours on scraping and 5 minutes on the interview.** Invert that. The interview is the highest-leverage hour of Peel.
4. **Writing rules during Peel.** You're observing. If you start drafting `voice.yaml`, you've jumped to Press and will get the rules wrong because you don't yet know what you're codifying.
5. **Skipping the cringe list.** The competitor phrases that make the founder wince are a free-first-draft banned-words list. Capture them.

## What's next

[Step 2 — Press: define](02-press-define.md) expects:

- `brands/<slug>/_raw/clusters.md`
- `brands/<slug>/_raw/artifacts-analysis.md`
- `brands/<slug>/_interview/transcript.md`
- `brands/<slug>/voice-health-report-<YYYYMMDD>.md`
- A list of 10+ candidate factual claims with source-status

If any of those are missing, finish Peel before starting Press. You'll regret skipping otherwise.
