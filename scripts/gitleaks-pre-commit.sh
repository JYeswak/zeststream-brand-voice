#!/usr/bin/env bash
# Canonical @zeststream/security-hygiene pre-commit hook — v0.0.1
#
# L48-GATED. This hook gates EVERY future commit; do NOT install
# without explicit owner sign-off. Ships as a template only; consumer
# (or operator) copies to .git/hooks/pre-commit and chmod +x.
#
# Behavior:
#   1. Run gitleaks against the staging diff.
#   2. Block commit if any leaks are detected against the repo's
#      .gitleaks.toml (which SHOULD use the canonical TWO-LAYER
#      pattern shipped at templates/gitleaks.toml).
#   3. Exit 0 if no leaks; non-zero otherwise.
#
# Installation (L48-gated; document why before installing):
#   cp node_modules/@zeststream/security-hygiene/templates/pre-commit-hook .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# Bypass (emergency only; document rationale + file fuckup row):
#   git commit --no-verify

set -euo pipefail

# Resolve repo root.
repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "pre-commit-hook: not a git repo; exiting 0" >&2
    exit 0
}
cd "$repo_root"

# Require gitleaks installed.
if ! command -v gitleaks >/dev/null 2>&1; then
    cat >&2 <<'EOF'
pre-commit-hook: gitleaks binary not found in PATH.

Install:
  brew install gitleaks
  # or: go install github.com/zricethezav/gitleaks/v8@latest

Bypass (NOT recommended): git commit --no-verify
EOF
    exit 1
fi

# Scan the staging diff (uncommitted index). Avoids scanning full
# history on every commit (gitleaks `protect` mode).
if gitleaks protect --staged --no-banner --redact 2>&1; then
    exit 0
fi

cat >&2 <<'EOF'

pre-commit-hook: BLOCKED — gitleaks found leaks in the staging diff.

Resolution:
  1. Remove the secret from the staged changes.
  2. If false-positive, add an allowlist entry to .gitleaks.toml:
     - path-allowlist for documented example/test/research/doc paths
     - regex-allowlist for documented internal-prefix family
     - stopwords for canonical placeholder literals
  3. Re-stage and re-commit.

Emergency bypass (document in fuckup-row before using):
  git commit --no-verify
EOF
exit 1
