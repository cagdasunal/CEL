#!/usr/bin/env bash
# No-spend guard — fails if a staged diff REMOVES a `dry_run=True` default/argument.
#
# Why: the whole repo is "safe by default" because callers pass dry_run=True (and the shared
# CmsClient defaults to it). Silently dropping a `dry_run=True` turns a safe test or staged write
# into REAL Webflow spend. This guard catches that in the diff, for the human and for Claude.
#
# Scope: it only flags REMOVED lines (leading `-`) that contain `dry_run=True` or `dry_run = True`,
# excluding this script itself. Adding/keeping dry_run is always fine. A deliberate go-live (removing
# dry_run on purpose) can be allowed with: ALLOW_REMOVE_DRY_RUN=1 git commit ...
#
# Install as a pre-commit hook:
#   ln -sf ../../scripts/hooks/check-no-spend.sh .git/hooks/pre-commit
# or call it from /preflight / CI.
set -euo pipefail

if [ "${ALLOW_REMOVE_DRY_RUN:-0}" = "1" ]; then
  echo "no-spend guard: bypassed via ALLOW_REMOVE_DRY_RUN=1 (deliberate go-live)."
  exit 0
fi

# Staged diff only; if not in a commit context, diff the working tree against HEAD.
if git rev-parse --verify -q HEAD >/dev/null 2>&1; then
  DIFF="$(git diff --cached -U0 -- '*.py' 2>/dev/null || true)"
else
  DIFF="$(git diff --cached -U0 -- '*.py' 2>/dev/null || true)"
fi

# Removed lines start with a single '-' (not '---'); look for a dry_run=True default being deleted.
OFFENDERS="$(printf '%s\n' "$DIFF" \
  | grep -E '^-[^-]' \
  | grep -E 'dry_run[[:space:]]*=[[:space:]]*True' \
  | grep -v 'scripts/hooks/check-no-spend.sh' || true)"

if [ -n "$OFFENDERS" ]; then
  echo "ERROR: this commit REMOVES a 'dry_run=True' default — that can turn a safe call into real spend." >&2
  echo "Removed lines:" >&2
  printf '%s\n' "$OFFENDERS" >&2
  echo >&2
  echo "If this go-live is intentional, re-run with:  ALLOW_REMOVE_DRY_RUN=1 git commit ..." >&2
  exit 1
fi

echo "no-spend guard: OK (no dry_run=True default removed)."
exit 0
