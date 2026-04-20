#!/usr/bin/env bash
# install.sh — symlink the brand-voice skill into Claude Code's skill directory
# Idempotent: re-running it just re-confirms the symlink.

set -euo pipefail

REPO_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
SKILL_SOURCE="${REPO_ROOT}/skills/brand-voice"
SKILL_TARGET_DIR="${HOME}/.claude/skills"
SKILL_TARGET="${SKILL_TARGET_DIR}/brand-voice"

echo "zeststream-brand-voice installer"
echo "  repo:      ${REPO_ROOT}"
echo "  skill src: ${SKILL_SOURCE}"
echo "  skill dst: ${SKILL_TARGET}"
echo

if [[ ! -d "${SKILL_SOURCE}" ]]; then
  echo "ERROR: skill source not found at ${SKILL_SOURCE}"
  echo "Did you run this from outside the repo? Re-run as ./scripts/install.sh from the repo root."
  exit 1
fi

mkdir -p "${SKILL_TARGET_DIR}"

if [[ -L "${SKILL_TARGET}" ]]; then
  existing="$(readlink "${SKILL_TARGET}")"
  if [[ "${existing}" == "${SKILL_SOURCE}" ]]; then
    echo "OK — symlink already points at this repo. Nothing to do."
    exit 0
  fi
  echo "A different symlink exists at ${SKILL_TARGET} pointing at ${existing}"
  echo "Remove it yourself if you want to replace: rm '${SKILL_TARGET}'"
  exit 1
fi

if [[ -e "${SKILL_TARGET}" ]]; then
  echo "A real directory or file already exists at ${SKILL_TARGET}"
  echo "Remove it yourself if you want to replace: rm -r '${SKILL_TARGET}'"
  exit 1
fi

ln -s "${SKILL_SOURCE}" "${SKILL_TARGET}"
echo "Linked ${SKILL_TARGET} → ${SKILL_SOURCE}"
echo
echo "Next:"
echo "  1. Restart Claude Code (or open a new session)."
echo "  2. Try: 'write a LinkedIn post about X in the zeststream brand voice'"
echo "  3. Read journey/01-peel-discover.md to onboard a new brand."
