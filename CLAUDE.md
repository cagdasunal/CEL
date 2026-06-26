# CLAUDE.md — standing rules for this repo (CEL tools)

Python automation + SEO-asset deployment for **englishcollege.com** (Canadian English Language
College / "CEL"), git repo `cagdasunal/CEL`. A fleet of GitHub Actions crons drives Webflow CMS
content, Weglot translation exclusions, blog-image optimization, offers automation, and SEO
summaries/copywriting. The canonical design doc is [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) —
read it first for anything touching `tools/`.

## The five things that must never drift

1. **The runtime LLM is Gemini, NOT Claude.** Every model call at runtime goes to Google Gemini
   (`tools/core/gemini/config.py`: `MODEL_ID = "gemini-3.1-pro-preview"`, blog `gemini-2.5-flash`).
   Claude (you) is the *dev* assistant only — never wire Claude/Anthropic into the runtime, and never
   assume a model call here is Claude.

2. **No-spend by default — `dry_run` is the safe default and must stay that way.** The shared Webflow
   client defaults to dry-run: `tools/core/webflow/cms.py` `CmsClient.__init__(..., dry_run: bool = True)`.
   A real spend / real Webflow write happens ONLY when a caller explicitly passes `dry_run=False` (or
   removes it) and supplies keys. **Never remove a `dry_run=True` from existing call sites** to "make it
   work" — that turns a safe test into real spend. During any build/refactor: dry-run + mocks only, no
   live API/Webflow calls (ARCHITECTURE.md "Global execution protocol" §5).

3. **Claude never publishes.** Publishing to Webflow is explicit human opt-in: the `summary` CLI gates
   it behind `--publish` (`action="store_true", default=False`). Do not add an auto-publish path, do not
   default `--publish` on, and do not run a publish command on the owner's behalf without being told to.

4. **`tools.core.*` is a leaf — the dependency direction is a test, not a comment.** Any tool may import
   `tools.core.*`; `tools.core` must NEVER import a consumer tool (`summary`, `translator`, `copywriter`,
   `offers`, `weglot`, `blog_images`, `arabic_rtl`, `mailer`). Enforced by import-linter
   (`.importlinter` contract `core-is-a-leaf`; run `lint-imports`). If you add a new leaf under
   `tools/core/`, add it to `source_modules`; if you add a new consumer tool, add it to
   `forbidden_modules` (`test_50_contract_coverage.py` fails otherwise).

5. **The regression baseline is a floor, not a guess.** `tools/_stress/test_00_regression.py` pins
   `BASELINE_PASSED = 462` and `KNOWN_FAILURES = 0` (suite is fully green). Bump `BASELINE_PASSED`
   *deliberately* only when the suite legitimately grows; never lower it or raise `KNOWN_FAILURES` to get
   to green — that defeats the guard. If you cite the baseline, cite the live numbers from that file.

## Sibling repo

A sibling Webflow checkout lives at `~/Desktop/dev/webflow` (`cagdasunal/webflow`). Some assets/workflows
are kept in step between the two. There is **no formal mirror manifest in this repo** — do not assume a
file here is the source of truth for the sibling (or vice-versa). When in doubt about which side owns a
mirrored file, ask before editing; do not blindly copy in either direction.

## How to work here

- **Env:** a venv with `requirements.txt`. CI uses Python 3.12; local dev may use 3.13 (`.venv` or
  `.venv313`). `pyproject.toml` sets `pythonpath`, `testpaths`, and the `stress`/`eval` markers.
- **Tests:** `pytest tools/ -q` (full) · `pytest -m "not stress"` (legacy only) · `pytest -m stress`
  (deterministic mocked cross-tool harness — no spend, safe in CI). `lint-imports` enforces the leaf
  contract. The `eval` marker is real-spend and runs manually, never in CI.
- **`/preflight`** chains the read-only gates (legacy tests + `lint-imports` + stress + workflow lint).
  Run it before pushing. It never spends and never lowers the baseline.
- **Workflows:** lint them with `python scripts/lint_workflows.py --strict` (default threshold is high+;
  `--strict` fails on medium+).
- **Branch + revert:** one change per branch/commit with its own green gate; rollback = `git revert`
  (ARCHITECTURE.md "Global execution protocol").

## Pointers

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the canonical design (layout, the leaf rule, extraction
  pattern, testing, execution protocol). When this file disagrees with ARCHITECTURE.md on `tools/`
  internals, ARCHITECTURE.md wins and this file gets fixed.
- `.github/workflows/` — the cron fleet (summary, content-pipeline, weglot-sync, offers-*, blog-image,
  arabic-css, sitemap-llms, stress-test, lint-workflows).
