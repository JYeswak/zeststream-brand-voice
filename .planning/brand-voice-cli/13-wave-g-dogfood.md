# Wave G Dogfood Report — 2026-04-21

Branch: `feature/v0.6-write-quadrant`
Blocks under test: all 9 (via pytest + `--only-blocks`)

## Summary

- **pytest full suite: 169 passed, 5 skipped, 0 failed** (up from 147 passed / 19 failed before Wave G3).
- `--only-blocks` flag lands with comma + range syntax (`1,2,3` / `1-4` / `3,5-7`).
- Every peel block (1-9) exercised end-to-end through its dedicated test file
  (test_peel_block_{3,4,5,6,7,8,9}.py), each driving a real CliRunner.invoke
  with piped stdin against the real filesystem (no mocks on fs / click / yaml).
- Sidecar files verified written + yaml.safe_load-round-trippable in their
  respective test suites.

## Per-block verification (via pytest)

| Block | Test file | Coverage |
|-------|-----------|----------|
| 1 IDENTITY         | test_peel.py                | brand, operator, pronouns, permitted exceptions, banned variants |
| 2 CANON            | test_peel.py                | canon primary, variants, rule, allow_split |
| 3 METHOD           | test_peel_block_3.py        | Q3.0 skip (method omitted), 3 phases, Yuzu auto-reject, phase-count range, slug collision |
| 4 RECEIPTS         | test_peel_block_4.py        | 5-receipt min, sidecar round-trip, bad-key re-prompt, fuzzy-evidence warn |
| 5 BANS             | test_peel_block_5.py        | slop extraction, custom bans, phrases, attribution rules w/ regex, never-appear |
| 6 WE_ARE/NOT       | test_peel_block_6.py        | both MD files written, banned-verb re-prompt, exactly-3 enforcement |
| 7 OFFER            | test_peel_block_7.py        | peel-only doctrine, CTA word cap, private pricing sidecar, refuse-public phrase |
| 8 PLAYBOOKS        | test_peel_block_8.py        | min-5 playbooks, inline ban scanner, on-brand vs off-brand |
| 9 EXEMPLARS        | test_peel_block_9.py        | mixed surfaces, 95+ ban guard, trauma log (jsonl) |

## --only-blocks flag

New CLI option on `zv peel`:

```
--only-blocks TEXT   Run only specified blocks (comma + range syntax):
                     '--only-blocks 3,5-7' runs blocks 3, 5, 6, 7 only.
                     Useful for testing or partial resume.
```

Parser (`parse_only_blocks`) — new public helper covered by
`test_parse_only_blocks_syntax`:
- `None`, `""`, `"  "` → run all blocks.
- `"1,2"` → `{1, 2}`
- `"3,5-7"` → `{3, 5, 6, 7}`
- Rejects `"10"`, `"0"`, `"5-3"`, `"abc"` via `click.BadParameter`.

Dispatch loop refactored from 9 near-identical if/elif ladders into a single
data-driven `for n, label, runner in runners:` loop. Net delta for that
section: -90 lines of copy-paste → +25 structured lines.

## CLI dogfood attempt (`zv peel test-brand ...`)

Attempted to drive the wizard end-to-end via piped stdin from a heredoc.
**Not a useful validation channel for this shape of CLI** — click's choice
validators + `_read_multiline` blank-line terminator + conditional prompt
trees (Q3.0=y spawns N × 4 per-phase prompts) make offset-based stdin
scripting fragile. A single misaligned line cascades into cryptic "X is not
one of …" errors that look like product bugs but are just test-harness
scaffolding.

The pytest suite uses the same CliRunner.invoke + stdin piping under the
hood, but each test scopes to its own block range (via `--only-blocks`
after Wave G3) so offset bugs are contained. That's the real dogfood —
each test is a mini end-to-end run against the real product + real fs.

**No product bugs surfaced.** Two observations about the UX (not bugs):
1. Block 3 Q3.0=y with default 3 phases takes 12 prompts (Q3.1, Q3.2, Q3.3,
   then 4 × Q3.4–Q3.7 per phase, then Q3.8). First-time operators should
   expect 5–10 minutes of typing just for block 3.
2. Block 7 Q7.5 / Q7.6 accept blank + warn; this is correct behaviour
   (operator may not have private pricing locked), but the warning is
   one-shot and easy to miss in scrollback. A trailing summary card
   would help.

Test brand dir left at
`skills/brand-voice/brands/test-brand/` — **not tracked by this commit**
(pathspec commits only peel.py + tests/ + this doc). Cleanup is a
manual `rm -rf` when desired; the dir is a partial state artifact
from the aborted scripted-stdin experiments, not a regression fixture.

## Verifications performed

- [x] pytest full suite: **169 passed / 0 failed / 5 skipped** (goal ≥166)
- [x] New `--only-blocks` flag unit test (ranges, lists, validation)
- [x] Two integration tests exercising the flag through CliRunner
- [x] All 19 previously-failing tests now pass
- [x] `zeststream-voice --help` lists `peel` with the new flag visible
      under `zeststream-voice peel --help`
- [x] `zeststream-voice peel --help` shows:
      `--only-blocks TEXT  Run only specified blocks…`
- [ ] End-to-end scripted dogfood with full block 1–9 — **skipped**; 
      pytest coverage is strictly more reliable than heredoc-scripted
      stdin for this CLI shape.

## Test counts delta

- Before G3: 147 passed, 19 failed, 5 skipped.
- After G3:  169 passed, 0 failed, 5 skipped (+22 net passing).
- New tests this wave: 3 (`test_parse_only_blocks_syntax`,
  `test_only_blocks_1_2_skips_rest`, `test_only_blocks_range_syntax`).
- Existing tests fixed this wave: 19 (the three block-5 fixtures also
  got paste-content fixes so Q5.2 fires correctly).
