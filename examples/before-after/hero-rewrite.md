# Before/after: hero rewrite

An actual rewrite from pre-system to post-system on the zeststream.ai homepage hero. Shows what the scorer catches and what the fix looks like.

---

## BEFORE (pre-system, composite 62)

```
Transform Your Business with AI-Powered Workflow Automation

We help enterprises unlock their potential through our cutting-edge AI platform
that seamlessly integrates with your existing systems. Our team of experts
leverages best-in-class technology to deliver mission-critical solutions that
move the needle on your KPIs.

[Request a Demo]
```

**Scorer verdict: BLOCK (composite 62, banned_words populated)**

Dim breakdown:

| Dim | Score | Why |
|-----|-------|-----|
| testable | 4 | No verifiable claims; "unlock their potential" is unfalsifiable |
| brand_voice | 3 | Wrong posture (third-person "we help enterprises" — ZS is solo) |
| canon_present | 0 | Canon line missing |
| person_named | 0 | No named operator — "we", "our team", "experts" |
| receipt_shown | 0 | Zero numbers, zero repos, zero benchmarks |
| invite_not_pitch | 2 | "Request a Demo" is a sales gate, not an invite |
| yuzu_phase_mapped | 0 | No Peel / Press / Pour visible |
| plain_language | 3 | "Leverage," "unlock," "mission-critical" — multiple hedges and abstractions |
| specificity | 1 | Swap test fails — change "zeststream" to any competitor name; sentence still works |

Banned words found: `transform`, `enterprises`, `unlock`, `cutting-edge`, `platform`, `seamlessly`, `leverages`, `best-in-class`, `mission-critical`, `move the needle`. Ten hits. Block.

Trademark errors: none (there was nothing specific enough to render wrong).

Claims ungrounded: none to extract (there are no factual claims; that's *also* a problem — see `receipt_shown: 0`).

---

## AFTER (post-system, composite 97)

```
I build things that work, and I show you the receipt.

I'm Joshua Nowak. I wire AI into businesses that already work —
96 production n8n workflows, an 8-GPU inference stack rebuilt from
bare metal, a 910× cache-hit improvement on a 2-line regex.

Book a 20-minute Peel session. $0. Specific. No pitch at the end.

[Book with Joshua →]
```

**Scorer verdict: SHIP (composite 97)**

Dim breakdown:

| Dim | Score | Why |
|-----|-------|-----|
| testable | 10 | Every claim has a source in `capabilities-ground-truth.yaml` |
| brand_voice | 10 | First-person singular; matches posture in `voice.yaml` |
| canon_present | 10 | Canon line present, verbatim |
| person_named | 10 | "I'm Joshua Nowak" |
| receipt_shown | 10 | Three receipts inline (96 workflows, 8-GPU stack, 910× cache) |
| invite_not_pitch | 10 | "Book a 20-min Peel session, $0, no pitch at the end" |
| yuzu_phase_mapped | 9 | Peel named; Press/Pour implied via the method name; could be more explicit |
| plain_language | 10 | Short sentences, concrete nouns, zero hedging |
| specificity | 10 | Swap test passes — sentence breaks if you remove "Joshua" or the specific numbers |

Banned words: none.

Claims grounded:
- `"96 production n8n workflows"` → `n8n_workflow_count_2026_04_19` (High confidence, api_pull, 2026-04-19)
- `"8-GPU inference stack rebuilt from bare metal"` → `gpu_stack_config` + CubCloud rebuild narrative (High confidence)
- `"910× cache-hit improvement on a 2-line regex"` → `cache_improvement_multiplier` (High confidence, benchmark calculated 2026-03-25)

Trademark errors: none.

---

## What changed (the diff that matters)

1. **Canon line added.** The entire hero now anchors on "I build things that work, and I show you the receipt." Every other sentence serves that anchor.
2. **Pronoun flipped** from third-person to first-person singular. Matches `voice.yaml.posture.voice: "first-person singular"`.
3. **Abstractions replaced with receipts.** "Cutting-edge AI platform" became "96 production n8n workflows, an 8-GPU inference stack, a 910× cache-hit improvement." Three concrete numbers.
4. **CTA flipped** from "Request a Demo" (sales gate) to "Book a Peel session, $0, no pitch" (low-friction invite).
5. **Banned words removed** — all ten hits gone.
6. **Length dropped** from 56 words to 45 words. Denser information, fewer words.

## What this cost to produce

About 15 minutes of rewriting + 5 minutes of grounding every claim against `capabilities-ground-truth.yaml`. The 20-minute investment compounds: the new hero is a canonical exemplar now (see `brands/zeststream/exemplars/hero/consult-hero-v1.md`), which informs future rewrites. The old hero would still be live today without the scorer.

## Meta-point

The scorer didn't "come up with" the better copy. A human (me) wrote it. The scorer's job was to catch the old copy and refuse the new copy until the new copy matched the rules. That's the whole model: **AI generates, rules gate, human writes inside the gates.** The rules are the information flow (Meadows #6); the human is the paradigm (#2).
