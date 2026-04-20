# Step 4 — Pour: activate

> *Pour in the Yuzu method: kaizen. The refined product is dispensed; now the system monitors itself, improves itself, and asks for your attention only when it needs it.*

## What you're doing in this step

Wiring enforcement so the system runs without you thinking about it. You take a calibrated rubric (Lock output) and plug it into every place copy gets written, reviewed, or shipped. Then you step back, and the system tells you when it's drifting.

**Output:** slash commands wired, pre-commit hook running banned-words grep, optional CI scoring, weekly drift audit cron, trauma-to-rule promotion active.

## Prerequisites

- Full Lock output (see [03-lock-validate.md](03-lock-validate.md) §stop-conditions)
- Claude Code installed (for slash commands) — optional if running markdown-only
- A repo where marketing/web copy lives (for pre-commit and CI)

## The work

### 1. Wire the slash commands (15 min)

Three commands ship with this repo:

- `/enforce-voice <content>` — load skill, apply voice, output with "Voice decisions" note
- `/score-route <path or text>` — score against 15-dim rubric, output composite + dim breakdown + regen hints
- `/discover-brand <slug> <url>` — run DISCOVER.md flow for a new brand

If you ran `./scripts/install.sh`, they're already available. Test with:

```bash
# in any project, ask Claude:
# "/enforce-voice write me a 3-sentence LinkedIn post about a recent ship"
# or
# "/score-route https://<your-domain>/about"
```

If it doesn't trigger, confirm the symlink:

```bash
ls -la ~/.claude/skills/brand-voice
# should point at /path/to/zeststream-brand-voice/skills/brand-voice
```

### 2. Pre-commit hook (30 min)

For every repo containing marketing/web copy, install a pre-commit hook that greps for banned words and blocks commits that hit them.

Example script (`.ops/voice-lint.sh`):

```bash
#!/usr/bin/env bash
# voice-lint.sh — block commits containing banned words
# Reads banned_words from voice.yaml
set -euo pipefail

BRAND_SLUG="${BRAND_SLUG:-zeststream}"
VOICE_YAML="$HOME/.claude/skills/brand-voice/brands/${BRAND_SLUG}/voice.yaml"

# extract banned words (simple; a real impl would use yq)
BANNED=$(awk '/^banned_words:/,/^banned_phrases:/' "$VOICE_YAML" \
         | grep -E '^\s+-\s+' | sed -E 's/^\s+-\s+//; s/"//g')

STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM \
               | grep -E '\.(md|mdx|html|tsx|jsx)$' || true)
[ -z "$STAGED_FILES" ] && exit 0

EXIT_CODE=0
for f in $STAGED_FILES; do
  for word in $BANNED; do
    if git diff --cached "$f" | grep -qiE "^\+.*\b${word}\b"; then
      echo "BANNED WORD in $f: $word" >&2
      EXIT_CODE=1
    fi
  done
done

exit $EXIT_CODE
```

Wire into git:

```bash
ln -s ../../.ops/voice-lint.sh .git/hooks/pre-commit
chmod +x .ops/voice-lint.sh
```

This catches the Layer-1-regex failures at commit-time, before they ever reach CI or prod.

### 3. CI scoring (45 min, optional but recommended)

On every PR that touches copy files, run the full scorer and post the composite score as a PR comment.

GitHub Actions skeleton (`.github/workflows/voice-score.yml`):

```yaml
name: Voice score
on:
  pull_request:
    paths:
      - '**.md'
      - 'src/content/**'
      - 'public/**.html'

jobs:
  score:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install brand-voice
        run: |
          git clone https://github.com/JYeswak/zeststream-brand-voice.git .voice-tmp
          ./.voice-tmp/scripts/install.sh
      - name: Score changed files
        run: |
          for f in $(git diff origin/main --name-only | grep -E '\.(md|html)$'); do
            claude run "/score-route $f" >> voice-report.md
          done
      - name: Post PR comment
        uses: marocchino/sticky-pull-request-comment@v2
        with:
          path: voice-report.md
```

This is a stub; adapt to your CI and Claude Code runner availability. The intent is: every copy PR gets a scorecard comment, merge blocks on composite <85.

### 4. Weekly drift audit (15 min to set up)

A cron that re-scores Wave-A routes (the handful of routes that represent your live voice) every Monday and posts the result to wherever you'll see it (Slack, Mattermost, email, a dashboard).

Example cron line (macOS launchd or cron):

```bash
# Every Monday 09:00 local
0 9 * * 1 cd /path/to/repo && /path/to/voice-reach-check.sh >> logs/drift.log 2>&1
```

The `voice-reach-check.sh` script samples each Wave-A route, runs `/score-route`, appends to `scorecard-log.jsonl`, and compares against last week. If composite drops ≥5 points on any route, it posts an alert.

If that's too much setup for week one, do this manually every Monday for 4 weeks. You'll learn what to watch for, then automate.

### 5. Activate trauma-to-rule promotion (30 min)

A second cron that reads `trauma.jsonl` weekly and checks for recurrence ≥3 on the same `regen_hint` category. When it finds one, it auto-drafts a PR adding a new rule to `voice.yaml`:

Example logic (pseudocode):

```python
from collections import Counter

traumas = [json.loads(l) for l in open('brands/<slug>/trauma.jsonl')]
hint_counts = Counter(t['regen_hints'][0] for t in traumas if t['regen_hints'])

for hint, count in hint_counts.items():
    if count >= 3:
        propose_rule(hint, count)  # creates a PR
```

Joshua (or whoever owns the brand) reviews the proposed rule, decides accept/reject. If accepted, `voice.yaml` updates and the rule takes effect immediately. If rejected, the hint is marked as a known false positive so it doesn't propose again.

This is the **B2 learning loop** activated: the system writes its own rules from its own scars. Meadows leverage #4, self-organization.

### 6. Exemplar promotion cron (10 min)

Every night at 03:00, scan `scorecard-log.jsonl` for ships in the last 24 hours with composite ≥98. Those that have aged 48hr without being found off-voice on re-audit get promoted to `brands/<slug>/exemplars/<surface>/<auto-slug>.md` and indexed into Qdrant.

This is the **R1 virtuous loop**: high-scoring copy ages into exemplars that inform future drafts. The corpus gets better every week without anyone curating it manually.

### 7. Exemplar quarantine cron (10 min)

Every Monday 04:00, re-score every file in `brands/<slug>/exemplars/`. Any that scores <90 on re-audit gets moved to `_quarantined/<slug>-<ts>.md` and removed from the Qdrant collection.

This is the **R2 vicious loop prevention**: even an exemplar can drift off-voice if the brand evolves. Quarantine keeps the corpus clean.

### 8. Documentation (15 min)

Close the loop by writing `brands/<slug>/ops.md` — a one-pager listing:

- Where `voice.yaml` lives
- How to invoke the scorer manually
- What cron jobs are running and where their output goes
- Escalation: who decides proposed rules, who reviews quarantine decisions
- Drift thresholds that trigger human attention

Without this doc, the system becomes a black box when you're not the one tending it.

## Stop conditions

Done with Pour when:

1. Pre-commit hook blocks a test commit containing a banned word.
2. `/score-route /your-homepage` produces a composite + dim breakdown in <10 seconds.
3. Weekly drift cron has run once and posted to your attention surface (Slack/email/dashboard).
4. At least one trauma-to-rule proposal has fired (or you've force-triggered one with test data).
5. `brands/<slug>/ops.md` exists and someone else could operate the system from it alone.

## Anti-patterns

1. **Wiring enforcement but not escalation.** Pre-commit that blocks is useful; pre-commit that blocks without telling the writer *why* (which banned word, which line, what to replace with) is hostile. Always include the fix hint in the rejection message.
2. **Weekly drift cron that nobody reads.** Pick a surface where the alert will actually be noticed (Slack DM, not a dashboard nobody visits). If it's not seen, it didn't happen.
3. **Trauma-to-rule with no human review.** The cron should *propose* a rule, not auto-merge it. Human taste (Axiom 5) stays non-negotiable.
4. **Exemplar promotion without aging.** Fresh ships that score 98 aren't stable yet. 48-hour aging catches the ones that looked right on Monday and obviously-wrong on Thursday.
5. **Skipping quarantine.** R2 vicious loop will poison the exemplar corpus within 90 days without weekly re-scoring. Don't skip.
6. **Treating Pour as "done."** Pour is kaizen — continuous improvement. The cron runs, you occasionally review, the rubric updates. The brand compounds. If you find yourself saying "the system is done," something has calcified and you should look for what stopped improving.

## What's next

There is no next step. Pour is where the system runs. You come back when:

- Trauma-to-rule proposes something and you review it
- A client engagement starts and you run journey steps 1–4 for their brand
- Quarterly retro: review the rubric itself, weights, dim definitions. Update where you've learned.

The repo now works for you. That's the whole point of the 4-step journey.

*I build things that work, and I show you the receipt.* This repo is one of those receipts.
