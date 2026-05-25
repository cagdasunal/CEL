# `tools/_stress` — L1 deterministic stress harness

Proves the modular refactor didn't break anything **and** that the modular composition
works — with **no secrets and no spend**. Every test carries the `stress` marker (so
`pytest -m "not stress"` runs the legacy suite alone), and the autouse `_no_spend` fixture
deletes `GEMINI_API_KEY` / `WEBFLOW_API_TOKEN` so a stray real Gemini/Webflow call raises
instead of billing. All paths are dry-run or mocked.

## Run it

```bash
# repo root, with a venv that has requirements.txt installed:
STRESS_PY=.venv313/bin/python bash tools/_stress/run_stress.sh
```

`run_stress.sh` unsets the keys, enforces the import-linter contract, then runs the suite.
CI runs the same thing keyless on Python 3.12 (`.github/workflows/stress-test.yml` — the
repo's first test-running workflow).

## The tests

| File | What it locks down |
|---|---|
| `test_00_regression.py` | Subprocesses the legacy + copywriter suite and reads a **JUnit XML** report: `passed >= 444` (no test loss) and `failures <= 2` (no NEW failure beyond the 2 known, out-of-scope `test_update_log` host asserts). XML, not stdout — pytest 9.x omits the trailing "N passed" line to a pipe. |
| `test_10_imports.py` | Each `tools.core.*` module imports standalone; the back-compat shims preserve **object identity** (`summary.batch_runner.submit_batch is core.gemini.client.submit_batch`, shared `_PENDING_BATCHES`, `WriteResult`, `MODEL_ID`/`LAST_BATCH_FILE`, …); public signatures are pinned. |
| `test_20_dryrun.py` | Each tool's dry-run entry is exercised with zero live calls (copywriter passthrough, translator passthrough, staged-not-sent CMS PATCH, on-disk batch artifact, backup+audit), and every consumer still imports under the namespace layout. |
| `test_30_compose.py` | The orchestrator proof: `core.gemini.dry_run_submit` → `copywriter.improve_copy` → `translator.translate_batch` → `core.webflow.CmsClient.patch_fields`, asserting the data hand-off at every seam. |
| `test_40_locale_native.py` | `improve_copy` is locale-native (ko AND en, dry-run AND live-stubbed) — a spy asserts the translator is **never** called; the anti-AI QA blocks em-dash / AI-template / hype-threshold drafts in EN and translationese in KO, and passes clean human copy in both. |

## When a guard trips

- **`passed < 444`** — a refactor dropped tests. Find what stopped collecting/running; don't
  just lower the baseline. Bump `BASELINE_PASSED` only on legitimate growth.
- **`failures > 2`** — a NEW real failure. Fix it (the 2 known ones are out of scope).
- **shim identity fails** — an extraction forked instead of re-exporting; the old path must
  `from tools.core.<pkg>.<mod> import *` + re-export to preserve identity.
- **`lint-imports` broken** — something made `tools.core` import a consumer tool. Invert the
  dependency (the consumer imports core, never the reverse).

## L2 (real-model quality evals) — deferred

The `eval` marker is reserved for a real-model golden-set + LLM-as-judge harness
(`tools/copywriter/evals/`). It incurs cost, needs golden data, and never runs in CI — it
will land when the model + golden set exist (Script-Creation-Gate: build it when a caller
needs it, not speculatively).
