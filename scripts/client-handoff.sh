#!/usr/bin/env bash
# client-handoff.sh — bundle a brand's kit for handoff
# Usage: ./scripts/client-handoff.sh <brand-slug> [output-dir]
#
# Creates a tar.gz with: the brand's voice.yaml + ground-truth + exemplars
# + visual/ + journey/ docs. Drop-shippable to the client.

set -euo pipefail

SLUG="${1:-}"
OUT_DIR="${2:-./handoffs}"

if [[ -z "$SLUG" ]]; then
  echo "Usage: $0 <brand-slug> [output-dir]"
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BRAND_DIR="$REPO_ROOT/skills/brand-voice/brands/$SLUG"

if [[ ! -d "$BRAND_DIR" ]]; then
  echo "ERROR: brand not found: $BRAND_DIR"
  echo "Available brands:"
  ls "$REPO_ROOT/skills/brand-voice/brands/" | sed 's/^/  - /'
  exit 2
fi

mkdir -p "$OUT_DIR"

STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUT="$OUT_DIR/$SLUG-brand-kit-$STAMP.tar.gz"

tar -czf "$OUT" \
  -C "$REPO_ROOT" \
  "skills/brand-voice/brands/$SLUG" \
  "skills/brand-voice/data/capabilities-ground-truth.yaml" \
  "skills/brand-voice/SKILL.md" \
  "journey" \
  "visual" \
  "README.md"

echo "Handoff bundle: $OUT ($(du -h "$OUT" | awk '{print $1}'))"
echo ""
echo "Contents:"
tar -tzf "$OUT" | head -20
echo "  ..."
echo "  (total: $(tar -tzf "$OUT" | wc -l | tr -d ' ') files)"
