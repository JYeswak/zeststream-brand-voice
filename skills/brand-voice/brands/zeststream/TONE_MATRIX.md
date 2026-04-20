# TONE_MATRIX — surface × audience × phase → register

Closes the tone-by-context gap (§F in the source extraction). Per Meadows: "locate responsibility in the system" — the register a writer uses should be derivable from context, not a vibe call.

When the scorer flags `friction_calibrated` <9, the root cause is almost always in this matrix. Read this file before rewriting.

---

## The three axes

| Axis | Values | Source |
|------|--------|--------|
| **Surface** | hero \| body \| cta \| email \| post \| meta \| other | `voice.yaml.surfaces` |
| **Audience** | operator \| candidate \| customer \| general | `voice.yaml.audiences` |
| **Phase** | peel \| press \| pour \| na | Yuzu Method phase of the conversation |

Every outbound copy block has exactly one coordinate. If it has two (because the page mixes audiences or phases), split the block.

---

## Register descriptors (the language of tone)

These are the tone levers. Apply them combinatorially per the matrix below.

- **direct** — declarative, few clauses, no hedging
- **inviting** — ends with a low-friction ask, warm
- **specific** — names tools, numbers, past builds
- **technical-accessible** — jargon paired with analogy in same paragraph
- **warm-operator** — first-person, like talking to a colleague
- **credibility-forward** — leads with receipts and resilience story
- **discovery-curious** — asks about the reader's system; acknowledges unknowns
- **build-confident** — past-tense, shipped, receipts
- **kaizen-calm** — operational, in-progress, post-ship
- **declarative-meta** — meta-description register: facts, no decoration
- **narrative-hook** — social post register; tension → insight → receipt

---

## The matrix (surface × audience × phase → register)

### Audience: operator (builder/technical SMB owner)

| Surface | Phase=peel | Phase=press | Phase=pour | Phase=na |
|---------|-----------|-------------|-----------|----------|
| hero | direct + specific + discovery-curious | direct + build-confident | direct + kaizen-calm | direct + specific |
| body | technical-accessible + discovery-curious | technical-accessible + build-confident | technical-accessible + kaizen-calm | technical-accessible |
| cta | inviting + specific (Peel session) | inviting + specific (mid-build milestone) | inviting + specific (next quarter review) | inviting + specific |
| email | warm-operator + discovery-curious | warm-operator + build-confident | warm-operator + kaizen-calm | warm-operator |
| post | narrative-hook + technical-accessible | narrative-hook + build-confident | narrative-hook + kaizen-calm | narrative-hook |
| meta | declarative-meta + specific | declarative-meta + specific | declarative-meta + specific | declarative-meta |

### Audience: candidate (hiring, collaboration, speaking)

| Surface | Phase=na dominant |
|---------|-------------------|
| hero | direct + credibility-forward |
| body | credibility-forward + technical-accessible + warm-operator (mention Montana, resilience story) |
| cta | inviting + direct (DM, email) |
| email | warm-operator + credibility-forward |
| post | narrative-hook + credibility-forward |
| meta | declarative-meta + credibility-forward |

### Audience: customer (non-technical buyer, operator-adjacent)

| Surface | Phase=peel | Phase=press | Phase=pour | Phase=na |
|---------|-----------|-------------|-----------|----------|
| hero | direct + inviting | direct + build-confident | direct + kaizen-calm | direct + inviting |
| body | warm-operator + discovery-curious + technical-accessible | warm-operator + build-confident | warm-operator + kaizen-calm | warm-operator |
| cta | inviting (20-min Peel session, $0) | inviting (milestone review) | inviting (retainer conversation) | inviting |
| email | warm-operator + inviting | warm-operator + build-confident | warm-operator + kaizen-calm | warm-operator |
| post | narrative-hook + warm-operator | narrative-hook + build-confident | narrative-hook + kaizen-calm | narrative-hook |
| meta | declarative-meta + inviting | declarative-meta + specific | declarative-meta + specific | declarative-meta + inviting |

### Audience: general (default, when no clear audience signal)

Default to **operator × phase=na** — build-confident, specific, technical-accessible. If a draft feels too technical for the page it's on, check whether the actual audience is *customer* and re-register.

---

## Worked examples

### Example A: `/consult` hero, audience=customer, phase=peel

Coordinate: hero × customer × peel → `direct + inviting`

**Right:**
> "I'm Joshua. Book a 20-minute Peel session and we'll map the system you're running. Free, specific, no pitch at the end. I build things that work, and I show you the receipt."

Why: declarative, first-person, concrete ("20-minute", "map the system"), inviting ("book"), no hedge, canon at end, audience-appropriate (customer, not operator).

**Wrong:**
> "We enable organizations to discover automation opportunities through our proprietary consultation framework."

Why: "we," "enable," "organizations," "proprietary framework" — banned words; wrong pronoun; abstract; no receipt. Coordinate mismatch on all axes.

---

### Example B: `/work/cubcloud` body, audience=operator, phase=pour

Coordinate: body × operator × pour → `technical-accessible + kaizen-calm`

**Right:**
> "CubCloud's inference stack runs 105 tok/s generation on MiniMax M2.5 FP8 at TP=4, measured on 2026-03-24. I still touch the stack on a project basis — a new model rotation here, a cache optimization there. The 2-line regex that fixed the `cch=` cache hit rate (0.007% → 6.37%, 910× improvement) runs in every proxy request today."

Why: technical but accessible (jargon paired with concrete numbers), past-tense on shipped work, present-continuous on kaizen, every number cited, operator-appropriate depth.

---

### Example C: LinkedIn post, audience=operator, phase=na

Coordinate: post × operator × na → `narrative-hook + technical-accessible`

**Right:**
> "The radix cache was running at 0.007% hit rate. Every 50K-token prompt was a fresh compute path.
>
> I found it in a billing header — `cch=XXXXX` at position 0, changing per request. A 2-line regex normalized it.
>
> Cache hit jumped to 6.37%. That's 910× improvement on a 2-line diff. Sometimes the wiring problem is a regex."

Why: tension (broken state) → insight (cause) → receipt (numbers + diff size) → philosophical close. Narrative hook intact, technical-accessible, no jargon unpaired.

---

### Example D: meta description for `/`, audience=general, phase=na

Coordinate: meta × general × na → `declarative-meta + specific`, max 20 words, 160 chars.

**Right (158 chars):**
> "Joshua Nowak wires AI systems into your stack. 96 production n8n workflows, 8-GPU rebuild for CubCloud. $5k Peel session, $15k+ builds."

Why: specific (96, 8, $5k, $15k), declarative, no verbs beyond essential, under char limit.

---

## Rules of thumb (when the matrix isn't enough)

1. **If the coordinate produces awkward copy, the coordinate is wrong.** Re-check axes before rewriting.
2. **When phase is unclear, default to `na`.** Don't fake a phase to claim the descriptor — it'll show.
3. **Never mix customer and operator registers in one block.** Split or pick one.
4. **Phase=pour register (kaizen-calm) is hard to do well.** Post-ship tone drifts toward either bragging or complacency. Keep it operational: "runs today, monitored, occasionally patched."
5. **If the matrix says "inviting" and you wrote a pitch, rewrite.** Inviting = low-friction ask. Pitch = high-friction close.

---

## Extending the matrix

When a new surface is added (say, `whitepaper` or `webinar_script`), add a row with its own register combos. Don't overload an existing row.

When a new audience segment appears (say, `investor`), add a column. Don't force investor copy into `customer`.

Every matrix extension requires at least one worked example. No abstract register additions.

---

## Feedback loop

When the scorer flags `friction_calibrated` <9, the rejection message must name:
1. The coordinate detected (`hero × customer × peel`)
2. The register combo the matrix says to use (`direct + inviting`)
3. An exemplar from the matched coordinate
4. The register drift observed (`sentence 3 reads as technical-accessible; this is the customer row, not operator`)

This is how the matrix improves: trauma entries accumulate in coordinates where the register guidance was ambiguous. Those rows get refined.
