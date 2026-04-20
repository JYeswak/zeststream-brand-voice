#!/usr/bin/env bash
# bootstrap-client.sh — create a new brand skeleton from template
# Usage: ./scripts/bootstrap-client.sh <brand-slug> [site-url]
#
# Creates: skills/brand-voice/brands/<slug>/ with voice.yaml + capabilities-ground-truth.yaml + exemplars/
# Idempotent: safe to re-run; errors out if brand already exists (remove manually to redo).

set -euo pipefail

SLUG="${1:-}"
SITE_URL="${2:-}"

if [[ -z "$SLUG" ]]; then
  echo "Usage: $0 <brand-slug> [site-url]"
  echo "  brand-slug: lowercase, dash-separated (e.g. acme-saas, clutterfreespaces)"
  echo "  site-url:   optional — seeds source_of_truth URL"
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE_DIR="$REPO_ROOT/skills/brand-voice/brands/_template"
TARGET_DIR="$REPO_ROOT/skills/brand-voice/brands/$SLUG"

if [[ -d "$TARGET_DIR" ]]; then
  echo "ERROR: brand already exists at $TARGET_DIR"
  echo "Remove it first: rm -rf $TARGET_DIR"
  exit 2
fi

if [[ ! -d "$TEMPLATE_DIR" ]]; then
  echo "ERROR: template missing at $TEMPLATE_DIR"
  echo "Falling back to acme-saas as template..."
  TEMPLATE_DIR="$REPO_ROOT/skills/brand-voice/brands/acme-saas"
  if [[ ! -d "$TEMPLATE_DIR" ]]; then
    echo "ERROR: no fallback template available either. Aborting."
    exit 3
  fi
fi

cp -R "$TEMPLATE_DIR" "$TARGET_DIR"

# Seed voice.yaml with the slug + site
if [[ -f "$TARGET_DIR/voice.yaml" ]]; then
  # BSD sed on macOS needs -i ''
  sed -i.bak -E "s|^(  slug:).*|\1 $SLUG|" "$TARGET_DIR/voice.yaml"
  sed -i.bak -E "s|^(  name:).*|\1 ${SLUG^}|" "$TARGET_DIR/voice.yaml"
  if [[ -n "$SITE_URL" ]]; then
    sed -i.bak -E "s|^(  domain:).*|\1 \"$SITE_URL\"|" "$TARGET_DIR/voice.yaml"
  fi
  rm -f "$TARGET_DIR/voice.yaml.bak"
fi

echo ""
echo "New brand created at: $TARGET_DIR"
echo ""
echo "Next steps (Peel phase):"
echo "  1. Edit $TARGET_DIR/voice.yaml — canon line, banned words, pronoun rules"
echo "  2. Edit $TARGET_DIR/capabilities-ground-truth.yaml — every number/claim you can prove"
echo "  3. Add 3-5 exemplars to $TARGET_DIR/exemplars/ (draft + score pairs)"
echo "  4. Run: python -m zeststream_voice score 'test copy' --brand $SLUG"
echo ""
echo "See journey/01-peel-discover.md for the discovery playbook."
