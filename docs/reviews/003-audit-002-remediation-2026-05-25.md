# Audit-002 Remediation — 2026-05-25

> Remediates every finding in `docs/reviews/002-session-audit-2026-05-25.md` (1 high, 4 medium,
> 8 low) + a small gap (G4). Web-verified the two non-obvious fixes (import-linter contract
> type; Korean no-NLP matching). `002` left immutable as the audit record.

## Status

| 002 finding | Resolution | Where |
|---|---|---|
| **H1** contract omits consumers | `forbidden_modules` now lists all 8 consumers (added weglot/arabic_rtl/mailer/copywriter); **`weglot` is a no-`__init__.py` namespace pkg** — enforcement PROVEN by a scratch mutation-test (core→weglot ⇒ lint BROKEN). Added `test_50_contract_coverage.py` self-guard. | `.importlinter`, `tools/_stress/test_50_contract_coverage.py` |
| **M1** flag double-count | Threshold now counts DISTINCT tells (a term in both the universal list and a locale banlist is one tell). | `tools/copywriter/qa.py` |
| **M2** KO substring false-positive | Single-token Hangul banlist terms use a Hangul-boundary lookaround `(?<![가-힣])t(?![가-힣])` (lightweight; full correctness needs a morphological analyzer — deferred). No-op for ja/ar. | `tools/copywriter/qa.py` |
| **M3** inert `glossary`/`sync` params | Removed from `improve_copy` (brand terms preserved via `must_keep_facts` per common.md; generation is always sync for interactive copy). README updated. | `tools/copywriter/engine.py`, `README.md` |
| **M4** vacuous translate-spy | `test_40` now asserts the live (stubbed) path calls `generate_sync` ONCE with the `ko` locale layer in the system prompt and returns same-locale copy — proving locale-native generation, not a tautology. | `tools/_stress/test_40_locale_native.py` |
| **L1** stale baseline 444 | → 456 (real non-stress count 462; small cushion). | `test_00_regression.py` |
| **L2** duplicate CI runs | `push` scoped to `branches: [main]` (PRs trigger via `pull_request` only). | `.github/workflows/stress-test.yml` |
| **L3** silent `--deselect` no-op | CI step now fails loudly if either deselected node ID was renamed/removed (`--collect-only` guard). | `.github/workflows/stress-test.yml` |
| **L4** unbounded must-keep-fact substring | ASCII facts use an alnum-boundary `(?<![a-z0-9])f(?![a-z0-9])` (refinement over the plan's `\b`, which breaks for symbol-flanked facts like `$1,200`); non-ASCII keep substring. | `tools/copywriter/qa.py` |
| **L5** UA drift | shared fetchers `page_fetcher`/`llms_parser` → `cel-tools/1.0` (cms.py stays `cel-webflow-client/1.0`). NOT gate-verifiable (no live fetch in tests); safe for self-fetch GETs. | `tools/core/web/page_fetcher.py`, `tools/core/seo/llms_parser.py` |
| **L6** stale SKILL caveat | "Requires the modular-core branch on main" removed (it is on main). | `M/.claude/skills/copywriter/SKILL.md` |
| **L7** lint resolution + redundant CI lint | `run_stress.sh` resolves lint via `command -v` (never a bare CWD name); redundant standalone CI lint step dropped (run_stress.sh lints). | `run_stress.sh`, `stress-test.yml` |
| **L8** shim rebind fragility + banlist silent-disable | Invariant comment on the `batch_runner` shim (the only one with mutable module state); `test_qa.py` now asserts en+ko banlists parse ≥1 term (catches a renamed heading). | `tools/summary/batch_runner.py`, `test_qa.py` |
| **G4** (gap) `_is_allowlisted_url` non-str | `isinstance(url, str)` guard + test. | `tools/copywriter/cli.py`, `test_cli.py` |

## Verification

```
Full suite:   tests=486 passed=484 failed=2 errors=0   (only the 2 known test_update_log)
Non-stress:   passed=462  (>= BASELINE_PASSED 456)
lint-imports: 1 kept, 0 broken   (expanded forbidden list)
run_stress.sh: exit 0
H1 mutation-test: core→weglot import ⇒ "tools.core is not allowed to import tools.weglot" ⇒ reverted
```

Targeted proofs (all pass): M1 `"We leverage a robust platform."` → 2 distinct tells, ok=True;
M2 `사또한테` does NOT flag `또한`, standalone tells still fail; L4 `cat`/`category`; M4 ko
locale-layer-in-prompt assertion.

## Out of scope (deferred in the first remediation PR #45)

- G1: prompt (`common.md`) vs `qa.py` `_UNIVERSAL_FLAG_TERMS` banlist drift.
- The 2 pre-existing `test_update_log.py` host-assert failures.
- Wiring a real glossary feature (the inverse of M3) — removal was the decision.

## Follow-up — out-of-scope items completed (2026-05-25)

- **G1 — DONE.** `common.md` banned-word list synced to `qa.py`: added `consequently`, `notably`,
  `embark` (QA flagged them; the prompt didn't warn). Prompt now warns about everything QA
  enforces, so the model isn't blind-sided into a QA-fail retry. Prompt-only; no fixture churn.
- **`test_update_log` — DONE (suite now fully green).** The 2 stale assertions
  (`sitemap.englishcollege.com`) were corrected to the canonical `cel.englishcollege.com` —
  what `update_log.render()` actually emits (the code was right per the canonical-sitemap rule;
  the tests were stale). Cascade: `KNOWN_FAILURES 2→0`, `BASELINE_PASSED 456→462`, and the CI
  `--deselect` machinery + its existence-guard removed (no longer needed). Full suite: **486
  passed / 0 failed**.
- **M2 (Korean) — intentionally deferred, not a bug.** A full fix needs a morphological analyzer
  (KoNLPy/mecab) — a heavy dependency deferred by an earlier locked decision. The Hangul-boundary
  heuristic + the ≥3-distinct-tell threshold is the accepted lightweight state.
- **L5 (UA) — unverifiable by design.** The live fetch isn't exercised in tests (no-network); the
  `cel-tools/1.0` change is safe for a self-fetch GET but can't be gate-proven without a live call.
- Glossary feature: still intentionally NOT wired (removal stands — brand terms via `must_keep_facts`).
