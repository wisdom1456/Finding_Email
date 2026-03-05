#!/bin/bash
# Verify api/constraints.txt is up-to-date with api/requirements.txt.
# Run: bash scripts/check_constraints.sh
# Exits 0 if in sync, 1 if regeneration needed.
set -e

if ! command -v pip-compile &>/dev/null; then
  echo "pip-tools not installed. Install with: pip install pip-tools"
  exit 1
fi

TMPFILE=$(mktemp)
trap 'rm -f "$TMPFILE"' EXIT

pip-compile --output-file="$TMPFILE" --strip-extras --no-header --allow-unsafe --quiet api/requirements.txt 2>/dev/null

if diff -q api/constraints.txt "$TMPFILE" >/dev/null 2>&1; then
  echo "✅ api/constraints.txt is up-to-date"
  exit 0
else
  echo "❌ api/constraints.txt is stale. Regenerate with:"
  echo "   pip-compile --output-file=api/constraints.txt --strip-extras --no-header --allow-unsafe api/requirements.txt"
  diff --unified=0 api/constraints.txt "$TMPFILE" | head -30
  exit 1
fi
