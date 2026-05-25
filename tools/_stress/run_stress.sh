#!/usr/bin/env bash
# L1 deterministic stress harness — no secrets, no spend.
#
# 1. Unsets the Gemini/Webflow keys (belt-and-suspenders to the conftest backstop) so a
#    stray real call CANNOT fire.
# 2. Enforces the import-linter dependency-direction contract (tools.core is a leaf).
# 3. Runs the stress suite (regression baseline + shim identity + dry-run each + the
#    gemini->copywriter->translator->webflow compose proof + locale-native anti-AI QA).
#
# Interpreter override:  STRESS_PY=.venv313/bin/python bash tools/_stress/run_stress.sh
set -euo pipefail

cd "$(dirname "$0")/../.."   # -> repo root (where .importlinter + pyproject.toml live)

PY="${STRESS_PY:-python3}"

unset GEMINI_API_KEY WEBFLOW_API_TOKEN 2>/dev/null || true

# import-linter ships only the `lint-imports` console script (no `python -m` entry).
# Prefer the one beside the chosen interpreter; else resolve an absolute path from PATH
# (never a bare name — that could pick up a stray ./lint-imports in the CWD).
if [ -x "$(dirname "$PY")/lint-imports" ]; then
  LINT="$(dirname "$PY")/lint-imports"
else
  LINT="$(command -v lint-imports)" || { echo "lint-imports not found on PATH"; exit 1; }
fi

echo "== import-linter (tools.core leaf contract) =="
PYTHONPATH=. "$LINT"

echo "== stress suite (marker: stress) =="
"$PY" -m pytest tools/_stress -m stress -p no:cacheprovider -q
