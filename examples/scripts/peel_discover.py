#!/usr/bin/env python3
"""
peel_discover.py — Peel-phase discovery stub.

Scrapes a public URL, extracts headlines + body text, prints phrases
grouped by length. You review, pick winners, paste into voice.yaml.

Usage:
    python examples/scripts/peel_discover.py https://example.com
    python examples/scripts/peel_discover.py https://example.com --out phrases.json

Requires:
    pip install requests beautifulsoup4

What this does NOT do (v0.4):
    - Clustering by semantic similarity (v0.5 with sentence-transformers)
    - Auto-proposing banned words (v0.5)
    - Multi-page crawl (v0.6)

For now it prints raw phrases. You copy/paste the good ones.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing deps. Install: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)


def fetch_and_extract(url: str) -> dict:
    """Fetch URL, return dict of {headlines, subheads, body_sentences}."""
    resp = requests.get(url, timeout=15, headers={"User-Agent": "zeststream-voice/0.4 peel-discover"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Strip noise
    for tag in soup(["script", "style", "nav", "footer", "aside"]):
        tag.decompose()

    headlines = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2"])][:30]
    subheads = [h.get_text(strip=True) for h in soup.find_all("h3")][:30]

    # Body sentences — rough split on periods
    body_text = soup.get_text(separator=" ", strip=True)
    sentences = [s.strip() for s in body_text.replace("!", ".").replace("?", ".").split(".")]
    body_sentences = [s for s in sentences if 5 < len(s.split()) < 30][:100]

    return {
        "url": url,
        "headlines": [h for h in headlines if h],
        "subheads": [h for h in subheads if h],
        "body_sentences": body_sentences[:50],
    }


def group_by_length(phrases: list[str]) -> dict:
    buckets = defaultdict(list)
    for p in phrases:
        n = len(p.split())
        if n <= 5:
            buckets["short (1-5 words)"].append(p)
        elif n <= 12:
            buckets["medium (6-12 words)"].append(p)
        else:
            buckets["long (13+ words)"].append(p)
    return dict(buckets)


def main() -> int:
    parser = argparse.ArgumentParser(description="Peel-phase discovery: scrape a site, dump phrases.")
    parser.add_argument("url", help="URL to scrape")
    parser.add_argument("--out", help="Optional JSON output path")
    args = parser.parse_args()

    print(f"Fetching {args.url}...", file=sys.stderr)
    data = fetch_and_extract(args.url)
    print(f"  {len(data['headlines'])} headlines, {len(data['subheads'])} subheads, {len(data['body_sentences'])} body sentences", file=sys.stderr)

    print("\n=== Headlines ===")
    for h in data["headlines"]:
        print(f"  {h}")

    print("\n=== Subheads ===")
    for s in data["subheads"]:
        print(f"  {s}")

    print("\n=== Body sentences (by length bucket) ===")
    for bucket, phrases in group_by_length(data["body_sentences"]).items():
        print(f"\n  {bucket}:")
        for p in phrases[:15]:
            print(f"    - {p}")

    if args.out:
        Path(args.out).write_text(json.dumps(data, indent=2))
        print(f"\nWrote JSON to {args.out}", file=sys.stderr)

    print(
        "\nNext: review phrases, pick 3-5 canon candidates, add 5-10 banned words, "
        "paste into brands/<slug>/voice.yaml. See journey/02-press-define.md.",
        file=sys.stderr
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
