#!/usr/bin/env python3
"""
analyze_corpus.py — extract 9 stylometric signatures from a brand corpus.

Usage:
    python scripts/analyze_corpus.py <corpus-file.txt> > signature.yaml

Ported from houtini-ai/voice-analyser-mcp (TypeScript) to Python.
Output is YAML, matching the `corpus_signature` block in voice.yaml.

Dependencies: only stdlib. PyYAML optional (falls back to manual output).
"""
from __future__ import annotations

import re
import statistics
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml  # optional; emit YAML manually if missing
    HAS_YAML = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    HAS_YAML = False


def split_sentences(text: str) -> list[str]:
    # Basic splitter. For production, swap in nltk.sent_tokenize or spacy.
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip() and len(s.split()) >= 2]


def sentence_lengths(sentences: list[str]) -> list[int]:
    return [len(s.split()) for s in sentences]


def burstiness(lengths: list[int]) -> float:
    if not lengths or statistics.mean(lengths) == 0:
        return 0.0
    if len(lengths) < 2:
        return 0.0
    return statistics.stdev(lengths) / statistics.mean(lengths)


def sentence_starters(sentences: list[str], top_n: int = 10) -> list[dict]:
    starters = [s.split()[0].lower().strip(".,!?'\"()[]") for s in sentences if s.split()]
    total = len(starters) or 1
    c = Counter(starters).most_common(top_n)
    return [{"word": w, "share": round(n / total, 3)} for w, n in c]


def sentence_enders(text: str, top_n: int = 5) -> list[dict]:
    matches = re.findall(r"[.!?]+", text) or ["."]
    total = len(matches)
    c = Counter(matches).most_common(top_n)
    return [{"punct": p, "share": round(n / total, 3)} for p, n in c]


def complexity_distribution(sentences: list[str]) -> dict:
    simple, compound, complex_ = 0, 0, 0
    for s in sentences:
        has_comma = "," in s
        has_semi = ";" in s
        has_sub = bool(
            re.search(r"\b(which|that|who|when|where|while|if|because|although)\b", s, re.IGNORECASE)
        )
        has_conj = bool(re.search(r"\b(and|but|or)\b", s, re.IGNORECASE))
        if has_sub:
            complex_ += 1
        elif has_semi or (has_comma and has_conj):
            compound += 1
        else:
            simple += 1
    total = simple + compound + complex_ or 1
    return {
        "simple": round(simple / total, 3),
        "compound": round(compound / total, 3),
        "complex": round(complex_ / total, 3),
    }


def analyze_corpus(text: str, source: str = "") -> dict:
    from datetime import datetime, timezone

    sents = split_sentences(text)
    lens = sentence_lengths(sents)

    return {
        "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": source,
        "sentence_count": len(sents),
        "mean_sentence_length": round(statistics.mean(lens), 2) if lens else 0.0,
        "stdev_sentence_length": round(statistics.stdev(lens), 2) if len(lens) > 1 else 0.0,
        "burstiness": round(burstiness(lens), 3),
        "top_starters": sentence_starters(sents),
        "top_enders": sentence_enders(text),
        "complexity_distribution": complexity_distribution(sents),
    }


def emit_yaml_manually(data: dict) -> str:
    # Minimal YAML emitter for when PyYAML isn't installed.
    out = ["corpus_signature:"]
    for k, v in data.items():
        if isinstance(v, list):
            out.append(f"  {k}:")
            for item in v:
                if isinstance(item, dict):
                    out.append(f"    - " + ", ".join(f"{ik}: {iv!r}" for ik, iv in item.items()).replace("'", '"'))
                else:
                    out.append(f"    - {item}")
        elif isinstance(v, dict):
            out.append(f"  {k}:")
            for ik, iv in v.items():
                out.append(f"    {ik}: {iv}")
        else:
            out.append(f"  {k}: {v}")
    return "\n".join(out) + "\n"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python analyze_corpus.py <corpus-file.txt>", file=sys.stderr)
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8", errors="replace")
    signature = analyze_corpus(text, source=str(path))

    if HAS_YAML and yaml is not None:
        print(yaml.safe_dump({"corpus_signature": signature}, sort_keys=False, default_flow_style=False))
    else:
        print(emit_yaml_manually(signature))

    # Also emit interpretation hints to stderr
    print("\n--- interpretation hints ---", file=sys.stderr)
    b = signature["burstiness"]
    if b < 0.30:
        print(f"  burstiness={b} — LOW. Current copy already reads mechanical. Target higher.", file=sys.stderr)
    elif b > 0.65:
        print(f"  burstiness={b} — HIGH. Copy varies wildly; check for inconsistency.", file=sys.stderr)
    else:
        print(f"  burstiness={b} — in human range (0.35–0.65). Good.", file=sys.stderr)

    msl = signature["mean_sentence_length"]
    if msl > 25:
        print(f"  mean_sentence_length={msl} — LONG. Academic/corporate register. Consider shortening.", file=sys.stderr)
    elif msl < 8:
        print(f"  mean_sentence_length={msl} — SHORT. Punchy social-media register. OK for some brands.", file=sys.stderr)

    top_starter_share = signature["top_starters"][0]["share"] if signature["top_starters"] else 0
    if top_starter_share > 0.15:
        print(
            f"  top starter '{signature['top_starters'][0]['word']}' = {top_starter_share*100:.1f}% of sentences. "
            f"Consider variation.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
