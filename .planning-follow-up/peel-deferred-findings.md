# peel.py deferred findings (from 06-wave-b-skill-pass-peel.md)

Source review: `/Users/josh/Developer/zesttube/.planning/brand-voice-cli/06-wave-b-skill-pass-peel.md`
Worker K fix commit landed P0-1, P0-2, P1-1, P1-2, P1-3, P1-4, P1-5, P1-6,
plus the cheap P2s that were <5-line changes. Remaining items deferred here
for v0.6 / follow-up polish — none block first client dry-run or public ship.

## P2 — remaining (polish, ship-safe)

### P2-5. Test `test_block1_and_block2_collect_required` asserts on `result.output` text
- **Location:** `tests/test_peel.py` in the CliRunner smoke test.
- **Why deferred:** Refactor to assert on parsed voice.yaml instead of stdout
  strings. Touches test organization. Not a correctness bug — just brittleness.
- **When to revisit:** next time someone changes checkpoint wording.

### P2-6. `PeelState.to_json` uses `indent=2` (3× file-size inflation)
- **Location:** `src/zeststream_voice/commands/peel.py` — `PeelState.to_json`.
- **Why deferred:** Debuggability of `.peel-state.json` outweighs the byte
  cost for a wizard that runs once per brand. Documented in the original
  skill-pass as "lower priority — keep for debuggability."
- **Action if revisited:** Add a `--compact-state` CLI flag rather than
  flipping the default.

## P3 — all 4 (nits)

### P3-1. Module docstring pointer
- **Fixed in this commit:** docstring now points at `05-unified-spec.md`
  with a note that doc 03 is archaeology. (Cheap enough to land inline.)

### P3-2. Unicode `≤` in prompt text (cp1252 Windows cmd garble)
- **Fixed in this commit:** replaced with `<=` everywhere in prompt copy.
  Modern-terminal assumption still holds for Mac / Linux; `<=` is safer.

### P3-3. `block_stub` prints 14 blank lines across stubs 3-9
- **Location:** `src/zeststream_voice/commands/peel.py` — `block_stub`.
- **Why deferred:** Cosmetic. First-time operators see the agenda header
  first, which sets expectations that blocks 3–9 are stubs; the blank-line
  noise is annoying but doesn't mislead.
- **Action if revisited:** collapse to one summary line:
  `Blocks 3–9 not yet implemented (v0.5 scaffold).`

### P3-4. `tests/test_peel.py` imported `click as _click` twice (locally)
- **Fixed in this commit:** `click` is now a module-level import. The two
  local `import click as _click` statements are gone.

## Not deferred — landed in this commit

- **P0-1** voice.yaml + .peel-state.json backups before destructive overwrite.
- **P0-2** corrupt .peel-state.json prompts three-way recovery (resume/abort/discard).
- **P1-1** re-prompt loops pass the rejected value as `default=` so the user can edit.
- **P1-2** `DOMAIN_RE` tightened — rejects empty labels, leading/trailing dashes, missing TLD.
- **P1-3** `_atomic_copytree` helper: stage-to-`.tmp`, rename on success, rmtree-cleanup on failure.
- **P1-4** `_word_count` uses a Vale-compatible `\b\w+(?:['-]\w+)*\b` tokenizer; documented.
- **P1-5** two new pytest regressions: `test_merge_raises_on_corrupt_yaml`, `test_merge_raises_when_brand_key_missing`.
- **P1-6** `test_force_backs_up_existing_voice_yaml` + `test_force_backs_up_existing_peel_state` verify the P0-1 invariant.
- **Cheap P2s:** P2-1 (`Optional[X]` → `X | None`), P2-2 (`dict[str, dict]` on `PeelState.answers`), P2-3 (docstrings on `_ask*` helpers), P2-4 (dead `name=` param removed from `block_stub`), P2-7 (`_clean(text)` named helper).
