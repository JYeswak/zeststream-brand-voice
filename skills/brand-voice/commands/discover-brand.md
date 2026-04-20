---
description: Run the onboarding-discovery flow for a new brand (client onboarding)
argument-hint: "<brand-slug> <primary URL>"
---

Run the DISCOVER flow from `references/DISCOVER.md` for a new brand at $ARGUMENTS.

**Orient the user first:**

"Here's how brand discovery works for this engagement:

1. **Scrape** — I'll pull all pages from the URL you named and tag every sentence against voice attributes.
2. **Cluster** — embed sections, find repeated phrases, identify pronoun posture and register spread.
3. **Interview** — 60–90 min with the founder/operator (recorded, transcribed).
4. **Mine artifacts** — emails, decks, recordings to find actual vs aspirational voice.
5. **Draft** — fill `voice.yaml`, `WE_ARE.md`, `TONE_MATRIX.md`, seed `capabilities-ground-truth.yaml`.
6. **Calibrate** — dry-run scorer on 5 existing pages, set thresholds.
7. **Seed exemplars** — 20+ before/after pairs.

Total: 4–8 hours of focused work. Nothing is written to the brand config until you review.

Ready?"

Wait for confirmation.

**Then execute the 9-step flow in DISCOVER.md.**

Output destination:

```
~/.claude/skills/zeststream-brand-voice/brands/<slug>/
├── voice.yaml
├── WE_ARE.md
├── TONE_MATRIX.md
├── LANGUAGE_BANK.md
├── JOURNEY_MAP.md
├── OPEN_QUESTIONS.md
├── calibration.md           # threshold decisions + baseline scores
├── exemplars/
│   ├── hero/
│   ├── body/
│   ├── cta/
│   ├── email/
│   ├── post/
│   └── meta/
├── _raw/                    # scraped site + interview transcripts (not tracked)
└── _interview/
    ├── recording.mp3
    └── transcript.md
```

Also add brand-tagged entries to `~/.claude/skills/zeststream-brand-voice/data/capabilities-ground-truth.yaml` with `brand: <slug>` prefix.

**Stop conditions:**
- Can predict what the founder would reject before showing them → done
- Can write a hero that scores ≥95 on first pass → done
- Can point to the exact rule that rejects a specific failed draft → done

Otherwise: more time in interview or artifact mining. Not in drafting.

Report when complete with: total sources analyzed, top 3 voice attributes discovered, number of open questions raised, overall confidence rating.
