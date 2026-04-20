# zeststream-voice

Brand voice scoring + claim grounding for AI-generated marketing copy.

This is the Python package layer for the public
[zeststream-brand-voice](https://github.com/JYeswak/zeststream-brand-voice)
repo. See the repo root README for the full methodology (Yuzu Method, the Josh
canon, the 15-dim composite rubric, the 2026-04-19 pivot).

## Install

```bash
pip install zeststream-voice
# or from a local checkout:
pip install -e .
```

## CLI quickstart

```bash
zeststream-voice info                                   # show brand paths + layer status
zeststream-voice score "I build things that work."      # layer 1 + grounding
zeststream-voice score --file draft.md --json
zeststream-voice enforce --path content/ --fail-under 95
zeststream-voice ground "I run 96 production workflows."
```

Also runnable as `python -m zeststream_voice ...`.

## SDK quickstart

```python
from zeststream_voice import BrandVoiceEnforcer

e = BrandVoiceEnforcer(brand="zeststream")

# Layer 1 + grounding (real)
result = e.score("some draft text")
print(result.composite, result.passed)

# Grounding only
ground = e.ground("I run 96 production workflows.")
for value, gt_id in ground.matched:
    print(value, "->", gt_id)
```

## Layer status

| Layer | Version | Status |
|------|---------|--------|
| layer1 banned-words regex | v0.4 | REAL |
| layer2 rules (three_moves) | v0.5 | STUB (NotImplementedError) |
| layer3 embedding similarity | v0.6 | STUB (`[embeddings]` extra) |
| layer4 LLM rubric (15-dim) | v0.6 | STUB (`[rubric]` extra) |
| grounding (YAML lookup) | v0.4 | REAL |

Layers 2-4 intentionally raise `NotImplementedError` with a roadmap pointer
so callers cannot silently rely on a fake composite. v0.4's composite reflects
layer 1 only.

## Brand resolution

The enforcer auto-discovers `skills/brand-voice/brands/<slug>/voice.yaml` by
walking up from CWD. Pass `brand_path=` (SDK) or `--brand-path` (CLI) to point
at an arbitrary directory.

## License

MIT. See repository root LICENSE.
