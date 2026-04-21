# ZestStream Brand-Voice Rules (Vale-shape)

This directory contains the ZestStream brand-voice ruleset split into one
YAML file per rule, following the [Vale](https://vale.sh/docs/topics/styles)
style convention: each rule file declares its `extends:` type, its message,
level, and either a list of tokens or a conditional trigger.

Rules are additive to `voice.yaml` — the monolithic file still exists
during the v0.5 transition. The loader reads both, and the rule files here
take precedence when both disagree.

## Rule file format

```yaml
extends: existence | substitution | occurrence | conditional | metric
message: "<human-readable message on violation>"
level: error | warning | suggestion
scope: raw | markdown
action:
  name: auto_reject | flag_for_review | warn
tokens:                           # for existence / substitution rules
  - '<regex>'
# or
conditions:                       # for conditional rules
  - name: <id>
    match: '<regex>'
    require_near: '<regex>'       # optional proximity check
    window_chars: 80
# or
required_occurrences:             # for occurrence rules
  - name: <id>
    pattern: '<regex>'
    min: 1
# or
swap:                             # for substitution rules
  '<pattern>': '<replacement>'
# or
metric: sentence_max_words        # for metric rules
per_surface_limits:
  hero: 18

applies_to_surfaces: [hero, body, post, ...]   # optional — empty means all

provenance:
  source_voice_yaml_keys: [<dotted.path.in.voice.yaml>, ...]
  rule_of_five_origin: "<trauma / session reference>"

acceptance_test:
  should_fail_on: "<string that MUST trigger the rule>"
  should_pass_on: "<string that MUST NOT trigger the rule>"
```

## Vale rule-type reference

- **existence** — fires when any of `tokens` appears in the text
- **substitution** — like existence, plus a suggested replacement (`swap:`)
- **occurrence** — requires each `required_occurrences[].pattern` to match
  at least `min` times (used for "must-have" checks like the Three Moves)
- **conditional** — fires on `match` only when `require_near` is / isn't
  present within `window_chars` (used for "X and Y within N chars")
- **metric** — computes a metric (e.g. `sentence_max_words`) and fires when
  the metric exceeds `per_surface_limits[surface]`

## Composition

Rules compose linearly. Each rule is a pure function of `(text, surface) →
list[violation]`. The runtime concatenates violations from all rule files
and applies the most severe `action` (auto_reject > flag_for_review > warn).

## Adding a new rule

1. Create `rules/<name>.yaml`. Copy the shape from an existing rule of the
   same `extends:` type.
2. Write the `acceptance_test.should_fail_on` and `should_pass_on`
   sentences BEFORE writing the tokens — drives correct regex design.
3. Run `python scripts/test_rules.py` to confirm the acceptance test passes.
4. Add the rule's `source_voice_yaml_keys` in the `provenance:` block so
   future audits can trace the rule back to voice.yaml.
5. If this rule is promoted from a trauma (Rule of Five: same failure
   pattern 3+ times), write the session reference in `rule_of_five_origin:`.

## Testing

`scripts/test_rules.py` loads every `rules/*.yaml`, runs each rule's
`acceptance_test.should_fail_on` and `should_pass_on` against the rule's
patterns, and asserts:

- `should_fail_on` produces ≥1 violation
- `should_pass_on` produces 0 violations

Exit code is 0 when all rules pass their acceptance tests, non-zero if
any fail. Run in CI:

```bash
python3 scripts/test_rules.py
```

## Scope

Each rule's `applies_to_surfaces` field restricts where it fires. An
empty list or missing field means the rule applies everywhere. Surfaces
are defined in `voice.yaml:surfaces` and include: `hero`, `body`, `cta`,
`email`, `post`, `meta`, `voice_channel`.

## Version / provenance

Every rule file carries a `provenance` block naming the `voice.yaml` keys
it was extracted from. This keeps the migration auditable — you can always
ask "which rules came from which part of voice.yaml?" by grepping:

```bash
grep -l 'source_voice_yaml_keys' rules/*.yaml | \
  xargs grep -l 'attribution_rules'
```
