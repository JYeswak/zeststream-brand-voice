# CORPUS_SIGNATURES — stylometric fingerprinting for voice drift detection

> Ported from houtini/voice-analyser-mcp (MIT licensed). Adapted for the brand-voice Meadows stack. v0.2.

This doc covers the `rhythm` + `corpus_signature` blocks in `voice.yaml` and the `rhythm_variance` rubric dim. Together they add one capability the original skill didn't have: **detecting AI-slop rhythm** — copy that passes every other gate (right canon, right banned words, right claims) but reads mechanical because its sentence lengths cluster around a single value.

Humans vary. LLMs default to monotone. This layer measures that.

---

## The 9 signatures we extract

For each brand's approved corpus (scraped site + hand-curated exemplars), we compute:

| # | Signature | What it measures | Where in voice.yaml |
|---|-----------|-----------------|--------------------|
| 1 | **Sentence length mean** | Avg words per sentence | `rhythm.sentence_length.mean_target` |
| 2 | **Sentence length stdev** | Absolute variation | `rhythm.sentence_length.stdev_target` |
| 3 | **Burstiness** | `stdev / mean` — relative variation | `rhythm.burstiness.target` |
| 4 | **Paragraph length** | Sentences per paragraph | `rhythm.paragraph_length.*` |
| 5 | **Top sentence starters** | Which words open sentences | `corpus_signature.top_starters` |
| 6 | **Top sentence enders** | `.` vs `!` vs `?` distribution | `corpus_signature.top_enders` |
| 7 | **Complexity distribution** | Simple / compound / complex ratio | `corpus_signature.complexity_distribution` |
| 8 | **Zero-tolerance patterns** | LLM-slop phrases with swap-alternatives | `corpus_signature.zero_tolerance_patterns` |
| 9 | **Starter variation** | Top 3 starters' share of all sentences | `rhythm.starter_variation.top_3_starters_max_share` |

Signatures 1–3 are the core rhythm fingerprint. Signatures 4–7 are secondary structural features. Signatures 8–9 catch specific LLM patterns.

---

## The algorithm (reference implementation)

```python
# scripts/analyze_corpus.py (reference; ~60 lines)
import re
import statistics
from pathlib import Path
import yaml

def split_sentences(text: str) -> list[str]:
    # Basic splitter — handles . ! ? but not all edge cases.
    # For production, swap in nltk.sent_tokenize or spacy.
    return [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]

def sentence_lengths(sentences: list[str]) -> list[int]:
    return [len(s.split()) for s in sentences]

def burstiness(lengths: list[int]) -> float:
    # Coefficient of variation: stdev / mean.
    # Human range typically 0.35–0.65. LLM default 0.15–0.25.
    if not lengths or statistics.mean(lengths) == 0:
        return 0.0
    return statistics.stdev(lengths) / statistics.mean(lengths)

def sentence_starters(sentences: list[str], top_n: int = 10) -> list[dict]:
    starters = [s.split()[0].lower().strip(".,!?'\"") for s in sentences if s.split()]
    total = len(starters)
    from collections import Counter
    c = Counter(starters).most_common(top_n)
    return [{"word": w, "share": round(n/total, 3)} for w, n in c]

def complexity_distribution(sentences: list[str]) -> dict:
    simple, compound, complex_ = 0, 0, 0
    for s in sentences:
        has_comma = "," in s
        has_semi = ";" in s
        has_sub = bool(re.search(r"\b(which|that|who|when|where|while|if|because|although)\b", s, re.I))
        has_conj = bool(re.search(r"\b(and|but|or)\b", s, re.I))
        if has_sub:
            complex_ += 1
        elif has_semi or (has_comma and has_conj):
            compound += 1
        else:
            simple += 1
    total = simple + compound + complex_ or 1
    return {
        "simple": round(simple/total, 3),
        "compound": round(compound/total, 3),
        "complex": round(complex_/total, 3),
    }

def analyze_corpus(text: str) -> dict:
    sents = split_sentences(text)
    lens = sentence_lengths(sents)
    return {
        "sentence_count": len(sents),
        "mean_sentence_length": round(statistics.mean(lens), 2) if lens else 0,
        "stdev_sentence_length": round(statistics.stdev(lens), 2) if len(lens) > 1 else 0,
        "burstiness": round(burstiness(lens), 3),
        "top_starters": sentence_starters(sents),
        "complexity_distribution": complexity_distribution(sents),
    }

if __name__ == "__main__":
    import sys
    corpus_text = Path(sys.argv[1]).read_text()
    sig = analyze_corpus(corpus_text)
    print(yaml.safe_dump(sig, sort_keys=False))
```

This is a reference implementation. The actual implementation should use `nltk.sent_tokenize` or `spacy` for robust sentence splitting (handles abbreviations, quoted speech, lists). The simple regex splitter above is deliberately minimal to show the idea.

---

## Integration with the 4-layer scorer

### Layer 1 (Regex) — adds rhythm checks

After regex pre-checks (banned words, canon, trademarks), compute the scored text's rhythm:

```python
text_sig = analyze_corpus(input_text)
brand_sig = voice_yaml["rhythm"]

# rhythm_variance dim (0..10)
dim_score = 10
if text_sig["burstiness"] < brand_sig["burstiness"]["min"]:
    dim_score -= 4  # mechanical / AI-slop signature
if text_sig["burstiness"] > brand_sig["burstiness"]["max"]:
    dim_score -= 3  # incoherent
if abs(text_sig["mean_sentence_length"] - brand_sig["sentence_length"]["mean_target"]) > brand_sig["sentence_length"]["mean_tolerance"]:
    dim_score -= 2  # off-target length
```

A draft that hits <7 on `rhythm_variance` drops composite by ~1 point (15-dim average). A <5 triggers the `any_dim_below_9` block.

### Layer 4 (LLM rubric) — uses signature as retrieval context

When the LLM rubric scores `brand_voice` and `friction_calibrated`, it receives the brand signature as context:

> "This brand's approved corpus has mean sentence length 15 words (stdev 7, burstiness 0.47). The text below has mean 18 (stdev 3, burstiness 0.17). Flag rhythm drift in your assessment."

This gives the LLM measurable drift signal, not just vibe judgment.

---

## Running corpus analysis (Peel phase)

The Peel step calls corpus analysis once per brand, populates `voice.yaml.corpus_signature`, and sets `voice.yaml.rhythm` targets. Operationally:

1. Scrape approved site copy → `brands/<slug>/_raw/corpus.txt`
2. Run `python scripts/analyze_corpus.py brands/<slug>/_raw/corpus.txt > brands/<slug>/_raw/signature.yaml`
3. Review signature manually — does the mean sentence length feel right for this brand? Does burstiness fall in 0.35–0.65?
4. Copy signature values into `voice.yaml.corpus_signature`
5. Set `voice.yaml.rhythm.*.target` from signature (usually = signature) and `voice.yaml.rhythm.*.tolerance` from judgment (typical: ±5 words for mean, ±0.1 for burstiness)

After the first corpus run, tolerances can tighten as the brand corpus stabilizes.

---

## Zero-tolerance patterns (the LLM-slop list)

Beyond the brand-specific banned words, LLMs have characteristic slop phrases that show up across brands. The `corpus_signature.zero_tolerance_patterns` list captures these with **swap alternatives**, not just prohibitions:

```yaml
zero_tolerance_patterns:
  - {pattern: "delve into", alternative: "look at", reason: "GPT-4 signature; rarely appears in human writing"}
  - {pattern: "leverage", alternative: "use", reason: "consultant-slop; banned globally"}
  - {pattern: "in today's fast-paced world", alternative: "[delete]", reason: "opener-slop; filler"}
  - {pattern: "it's important to note that", alternative: "[delete]", reason: "LLM throat-clearing"}
  - {pattern: "navigate the complexities of", alternative: "work through", reason: "consultant-slop"}
  - {pattern: "cutting-edge", alternative: "[name the specific technology]", reason: "empty intensifier"}
  - {pattern: "robust", alternative: "[describe what it does]", reason: "empty adjective"}
  - {pattern: "seamless", alternative: "[delete or name the friction removed]", reason: "marketing-slop"}
  - {pattern: "ensure", alternative: "[use active verb of what's ensured]", reason: "passive-corporate"}
  - {pattern: "realm of", alternative: "[delete — say the thing directly]", reason: "GPT filler"}
```

This list is universal starting material; each brand adds brand-specific patterns discovered during Lock (step 3 of the journey).

---

## Why this closes the R2 vicious loop from a different angle

The `METHODOLOGY.md` already documents R2 (drift in corpus poisons future output). The standard fix was **semantic quarantine** — weekly re-audit of exemplars, remove anything below 90 composite.

Corpus signatures add a **statistical quarantine**:

- If a new exemplar shifts the brand signature (e.g. burstiness drops from 0.47 to 0.32 after the exemplar lands), flag it
- The shift is measurable before the LLM has had time to drift future output toward the new mean
- Course correction is a `git revert` on that exemplar, not a multi-week recovery after drift compounds

Statistical quarantine fires faster than semantic quarantine. Use both.

---

## What this doesn't do

- **It doesn't replace the LLM rubric.** Rhythm is one signal among many. A text with perfect rhythm but wrong canon still blocks.
- **It doesn't work on ≤3 sentences.** Burstiness is meaningless on a CTA button or single-sentence meta tag. For those surfaces, `rhythm_variance` dim returns "N/A" and the scorer reweights.
- **It doesn't detect meaning-level drift.** A brand that shifted from SMB-operator to enterprise-buyer will show up in `brand_voice` dim (wrong posture) and `specificity` (swap test fails), not in rhythm.
- **It doesn't catch rhythm that's within-band but subtly wrong.** A cultural register shift (formal → casual) may preserve burstiness. That's Layer 4's job.

Rhythm is a **high-precision, mid-recall** signal: when it fires, it's usually right. When it doesn't fire, other layers still matter.

---

## Acknowledgment

This module is a direct adaptation of https://github.com/houtini-ai/voice-analyser-mcp — specifically their `analyzers/sentence.ts`, `analyzers/function-words.ts`, and `utils/zscore.ts`. Their MCP server runs the full 16-analyser sweep; this skill runs the 9 most useful in ~60 lines of Python with the same YAML schema shape. If you want the full 16, install their MCP alongside this skill — they're complementary, not competitive.
