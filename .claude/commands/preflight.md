---
description: Run the full read-only gate set (legacy tests + import-linter + stress + workflow lint) before pushing. No spend, never lowers the baseline.
allowed-tools: Bash(python3:*), Bash(.venv*/bin/python:*), Bash(pytest:*), Bash(bash tools/_stress/run_stress.sh:*), Bash(lint-imports:*), Bash(scripts/lint_workflows.py:*)
---

Run the repo's gates in order and report a clear PASS/FAIL for each. These are all read-only and
**never spend** (the stress harness unsets the Gemini/Webflow keys). Do NOT "fix" a failure by lowering
`BASELINE_PASSED` or raising `KNOWN_FAILURES` in `tools/_stress/test_00_regression.py` — those are the
guard; echo the live baseline on failure instead.

Pick the interpreter once (prefer an active venv): use `.venv/bin/python` or `.venv313/bin/python` if it
exists, else `python3`. Export it as `PY` and pass `STRESS_PY=$PY` to the stress harness.

1. **Legacy suite** (no spend):
   `$PY -m pytest tools/ -m "not stress" -p no:cacheprovider -q`
2. **Stress harness** (import-linter leaf contract + stress suite, keys unset inside the script):
   `STRESS_PY=$PY bash tools/_stress/run_stress.sh`
3. **Workflow lint** (strict — fail on medium+):
   `$PY scripts/lint_workflows.py --strict`

After running all three, print a summary table:

```
gate                  result
legacy suite          PASS / FAIL (passed=NN, baseline=462)
stress + leaf         PASS / FAIL
workflow lint --strict PASS / FAIL
```

If anything fails, show the relevant tail of output and STOP — do not push. If a test count dipped below
`BASELINE_PASSED = 462`, say so explicitly and treat it as a regression to investigate, never as a number
to edit down.
