# The 4-step journey

Peel → Press → Lock → Pour. This is the repeatable process for taking any brand from "we have some marketing copy and vibes" to "every sentence scored, every claim grounded, every drift captured, every rule promoted from captured drift."

Run it on your own brand first (dogfood). Then run it on clients.

## The four steps

| Step | Question answered | Time | Output |
|---|---|---|---|
| [01 — Peel: discover](01-peel-discover.md) | What does this brand actually sound like, in practice, right now? | 4–8 hrs | Raw corpus + founder interview + cringe list + Voice Health Report |
| [02 — Press: define](02-press-define.md) | What are the rules, what are the claims, what's the posture? | 3–4 hrs | `voice.yaml` + `WE_ARE.md` + `TONE_MATRIX.md` + seeded `capabilities-ground-truth.yaml` |
| [03 — Lock: validate](03-lock-validate.md) | Does the rubric actually agree with taste on real copy? | 3–4 hrs | Calibrated thresholds + 20+ exemplars + first trauma entries |
| [04 — Pour: activate](04-pour-activate.md) | Is enforcement running without anyone remembering to think about it? | 2–3 hrs | Slash commands wired, pre-commit hooks, CI scoring, weekly audits |

Total: **12–18 hours for a brand you care about.** Not a weekend project. But the bet is 12 hours front-loaded saves 40+ hours of reactive per-piece voice rewriting over the next year.

## Meadows framing (why these four steps, in this order)

Each step matches a Meadows leverage point:

| Step | Leverage point | Intervention |
|---|---|---|
| Peel | **Get the beat of the system before you disturb it** (Dancing with Systems, principle 1) | Don't impose; listen. Observe what exists. |
| Press | **Rules of the system** (leverage #5) | Codify the machine-checkable constants. |
| Lock | **Information flow** (leverage #6) | Put the rules in the writer's context at write-time. |
| Pour | **Self-organization** (leverage #4) | The system writes its own rules from captured failures (trauma → rule at recurrence ≥3). |

Skip any step and the loop doesn't close. Specifically:

- Skip Peel → you impose an aspirational voice instead of the brand's actual voice. Drift is immediate.
- Skip Press → rules live in heads, not config. New writers (human or LLM) can't enforce what nobody wrote down.
- Skip Lock → rubric scores look impressive but don't match taste. Composite-95 drafts still feel off.
- Skip Pour → system requires human attention to survive. It dies the first week nobody tends it.

## How the steps read

Each journey doc follows the same structure:

1. **What you're doing in this step** (30-second summary)
2. **Prerequisites** (what must be true before starting)
3. **The work, step-by-step** (numbered, with commands and exact outputs)
4. **Stop conditions** (how you know the step is done — not time-based)
5. **Anti-patterns** (common ways to get this wrong)
6. **What's next** (what the next step expects from this one)

You can skim them in order first (maybe 20 minutes total), then come back and execute.

## Pick your path

**New brand (client or your own):** start at [01 — Peel](01-peel-discover.md).

**Existing brand with some docs:** read [01 — Peel](01-peel-discover.md), skip to [02 — Press](02-press-define.md), come back to fill Peel gaps.

**Already have a voice.yaml (e.g. from the anthropics plugin):** skip to [03 — Lock](03-lock-validate.md) to calibrate thresholds. If your YAML has no ground-truth claim bank, detour to [02 — Press](02-press-define.md) §4.

**Want to understand the theory first:** read [`../skills/brand-voice/references/METHODOLOGY.md`](../skills/brand-voice/references/METHODOLOGY.md) before starting. The rest of the system is implementation detail for that file.
