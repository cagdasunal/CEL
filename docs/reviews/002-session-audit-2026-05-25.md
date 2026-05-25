# Session Audit — modular `tools/core` refactor + copywriter + stress harness

> Scope: a deep, READ-ONLY audit of everything produced this session — Plans 0/B2/A/B/C/D
> (the `tools/core` extraction + shims), the `copywriter` tool, the `_stress` harness + the
> new CI, the docs, the monorepo `/copywriter` skill, and the PR-#44 review-fixes.
> Baseline commit: `80a248d` (main). Method: 4 parallel `general-purpose` audit agents
> (stress/CI · shims/config/leaf · copywriter · docs/skill) + executor re-verification of
> every high-impact finding against the live code. **Zero code changed — report only.**

## Summary

| Severity | Count | Findings |
|---|---|---|
| Critical | 0 | — |
| High | 1 | H1 |
| Medium | 4 | M1–M4 |
| Low | 8 | L1–L8 |
| Info / verified-solid | 10 | see §“What's solid” |
| **Total actionable** | **13** | |

Net: the work is functionally sound and merged-green (gate below). No data-loss, security, or
broken-build issues. The actionable items are an architecture-contract hole I introduced (H1),
QA-correctness over/under-matching (M1, M2, L4), two misleading/dead API surfaces (M3, M4),
and doc/CI hygiene (L1–L8).

## Verification evidence (baseline gate, `main` `80a248d`, `.venv313`)

```
Full suite:      tests=481 passed=479 failed=2 errors=0 skipped=0   (exit 1)
  failures = the 2 pre-existing, OUT-OF-SCOPE tools/test_update_log.py host asserts only.
Non-stress only: collected=460 passed=458 failed=2 errors=0 skipped=0   (-m "not stress")
lint-imports:    Contracts: 1 kept, 0 broken
run_stress.sh:   exit 0
```

---

## HIGH

### H1 · `.importlinter:20-24` · The leaf-contract's `forbidden_modules` is incomplete — it does not forbid `tools.core` from importing `tools.copywriter` (added THIS session), nor `weglot`/`arabic_rtl`/`mailer`/`dashboard_users`.
**Evidence:** `forbidden_modules` lists only `tools.summary`, `tools.translator`, `tools.offers`, `tools.blog_images`. So `tools.core → tools.copywriter` (or `→ tools.weglot`, etc.) would PASS the contract — the central invariant of the whole refactor ("core is a leaf; never imports a consumer") is unenforced for those consumers. This is a regression I introduced: Plan C added the `copywriter` consumer but did not add it to the contract; and Plan 0's own spec named `weglot|arabic_rtl|mailer` which never made it into the file. Currently no such import exists (lint is green because the violation simply isn't present), so it's a **latent** hole, not an active break.
**Recommendation:** add `tools.copywriter`, `tools.weglot`, `tools.arabic_rtl`, `tools.mailer`, `tools.dashboard_users` to `forbidden_modules` (or invert to an `independence`/`layers` contract that enumerates every consumer so new tools are covered by default). Re-run `lint-imports` (still expect 1 kept / 0 broken).

---

## MEDIUM

### M1 · `tools/copywriter/qa.py:42-50` ↔ `:120-127` · Anti-AI flags double-count terms present in BOTH `_UNIVERSAL_FLAG_TERMS` and a locale banlist, so the documented "≥3 tells ⇒ fail" gate actually fails at **2 distinct tells**.
**Evidence (executor-run):** `copywriter_qa("We leverage a robust platform.", "en")` → `ok=False`, `flags=['ai_term:leverage','ai_term:robust','banlist[en]:leverage','banlist[en]:robust']` — 2 real tells, 4 flags, trips `_FLAG_FAIL_THRESHOLD=3`. Many EN terms overlap (`leverage, robust, delve, utilize, harness, vibrant, moreover, furthermore, …`). The QA is *over-strict*: it can reject acceptable copy. (Fail-safe direction — over-flagging triggers the one retry + human review — so impact is bounded.)
**Recommendation:** dedupe by underlying term before thresholding (e.g. skip the universal term when a locale banlist already covers it, or collapse `ai_term:X`+`banlist[..]:X` to one flag).

### M2 · `tools/copywriter/qa.py:120-127` · Per-locale banlist uses bare substring match for non-ASCII terms, so short Korean particles false-match INSIDE unrelated words.
**Evidence (executor-run):** `copywriter_qa("사또한테 그 말을 전했어요.", "ko")` flags `banlist[ko]:또한` because `또한` is a substring of `사또한테`. Korean is agglutinative (no word spaces), so 2-3 char banlist terms (`또한`, `매우`, `당사는`, `저희는`) collide with legitimate stems. A single collision is harmless (1 < 3), but **three** accidental collisions fail genuinely clean Korean — directly undercutting the "Korean-first" goal.
**Recommendation:** describe-only — there's no clean pure-substring fix for agglutinative scripts; options: raise the minimum length for non-ASCII banlist substring hits, add a boundary/space heuristic, or weight single short non-ASCII hits below the fail threshold. No test currently guards clean-Korean-with-collision.

### M3 · `tools/copywriter/engine.py:37,39` · `improve_copy` accepts `glossary=None` and `sync=True` but the body uses NEITHER — both are dead/misleading params (Script-Creation-Gate Rule 5).
**Evidence:** line 64 unconditionally calls `gemini.generate_sync(...)` regardless of `sync`; `glossary` is never referenced. `tools/copywriter/README.md:54` documents `sync=True` as if it selects batch-vs-sync, and a caller passing `glossary=<terms>` would reasonably expect it to constrain output — it does nothing.
**Recommendation:** either wire `sync` (route to the batch path when `False`) and pass `glossary` into the prompt/QA, or drop both from the signature + `__init__` exports + README. Lowest-risk: remove them until a caller needs them.

### M4 · `tools/_stress/test_40_locale_native.py:38-62` · The "improve_copy never translates" spy is **vacuous** — it can't fail.
**Evidence:** `improve_copy` imports no translator symbol on any path (executor grep of `tools/copywriter/*.py`: only docstrings + the dormant `translate_to` brief field; the live path calls `core.gemini.client.generate_sync`). So `assert _translate_spy["n"] == 0` is true by construction and would still pass if both patched symbols were deleted. The locale-native guarantee is REAL, but this test gives false confidence rather than proving it.
**Recommendation:** assert the *positive* — that the live (stubbed) path calls `generate_sync` once with `req.locale`'s system prompt and returns same-locale text — and keep the spy only as a defense-in-depth guard.

---

## LOW

### L1 · `tools/_stress/test_00_regression.py:24` · `BASELINE_PASSED = 444` is stale/loose: the non-stress suite now passes **458** (14 slack), so the guard only catches a *large* (>14) test loss.
**Evidence (executor-run):** `pytest -m "not stress"` → collected=460, passed=458. (Note: audit agent A reported "446/444, zero slack" — that was a **miscount**; the live number is 458.) Not brittle, just no longer tightly tracking.
**Recommendation:** bump `BASELINE_PASSED` to ~456 (small cushion under 458) so a handful of dropped tests trips it; or document the intended cushion.

### L2 · `.github/workflows/stress-test.yml:9-23` · Duplicate CI runs — both `on: push` and `on: pull_request` are scoped to identical `tools/**` paths, and the `concurrency.group` keys on `${{ github.ref }}` (different for push vs PR), so it does not dedupe. PR #44 fired 2 identical `stress` jobs.
**Recommendation:** scope `push` to `branches: [main]` (keep `pull_request` for branches), halving CI minutes.

### L3 · `.github/workflows/stress-test.yml:66-67` · The 2 `--deselect`'d known-failing `test_update_log` node IDs silently no-op if renamed/fixed (pytest exits 0 on a non-matching `--deselect`).
**Recommendation:** add an existence guard (e.g., `--collect-only` grep, or convert the underlying failures to `xfail(strict=False)`) so a rename surfaces instead of silently re-including or phantom-deselecting.

### L4 · `tools/copywriter/qa.py:130-133` · `must_keep_facts` uses unbounded lowercased substring match — a short fact is "preserved" when it only appears inside an unrelated word.
**Evidence:** the mechanism is `_norm(fact) not in ntext`; a fact `"cat"` would be satisfied by `"category"`. Low impact for typical facts (`"DLI #O19…"`), real for short tokens/acronyms.
**Recommendation:** word-boundary check for ASCII facts (mirror the flag logic); leave non-ASCII as substring.

### L5 · `tools/core/web/page_fetcher.py:18`, `tools/core/seo/llms_parser.py:220` · User-Agent inconsistency: these still send `cel-summary-script/1.0` after the PR-#44 fix changed `cms.py` to `cel-webflow-client/1.0`.
**Recommendation:** unify (a shared `core` UA constant) — but verify no public server keys on the old UA first; deliberately left this pass per the #4 finding's scope.

### L6 · `M/.claude/skills/copywriter/SKILL.md:20-21` · Stale caveat "Requires the modular-core branch … to be on the CEL `main`" — it IS on main (PR #42 merged). Misleadingly implies the tool may not be runnable.
**Recommendation:** delete the sentence (or restate "Lives on CEL `main`").

### L7 · `tools/_stress/run_stress.sh:21-22` · `lint-imports` resolution (`$(dirname "$PY")/lint-imports`, fallback PATH) is correct today but would silently run a repo-root `./lint-imports` if such a file ever existed, and lint runs 3× across the CI (workflow step + run_stress.sh).
**Recommendation:** resolve via `command -v lint-imports`; drop the redundant standalone CI lint step since `run_stress.sh` already lints.

### L8 · `tools/summary/{batch_runner,page_fetcher,structure,llms_parser}.py` shims · Identity-by-snapshot (`globals().update(vars(_src) …)`) is correct today but fragile: it copies references once at import, so it would silently go STALE if any core module-global is ever *reassigned* at runtime (`_PENDING_BATCHES` is safe only because it's mutated in place, never rebound).
**Recommendation:** add a comment forbidding runtime rebinding of core module globals, or delegate via `__getattr__` instead of a snapshot (survives rebinding). Also: `qa.py:80-81` banlist parser silently disables a locale's entire banlist if its `## AI-tell banlist` heading is ever renamed/translated (returns `()` with no warning) — same "silent staleness" class.

---

## What's solid (adversarially checked, found correct)

- **#5 config deletion is SAFE.** All 28 distinct `config.*` reads across `cli/audit/prompt_builder/url_map/match_verify/webflow_designer/qa/keyword_extractor` resolve; the 12 deleted knobs are all re-imported, the rest stay local. The `DRYRUN_DIR`/`LAST_BATCH_FILE` monkeypatch trap is cleared — `cli.py` reads them off `tools.summary.config` and the client off `tools.core.gemini.config`; conftest/test_cost_optimization dual-patch both, and the cancel-batch tests patch exactly the module `cli.py` resolves from.
- **No token leak.** `core/webflow/http.py` error strings interpolate only method+url+truncated-body+reason; the `headers` dict (Bearer token) is never logged or interpolated; `resolve_token` raises only the env-var name.
- **Shim completeness verified** — every public + tested-private name (incl. `_PENDING_BATCHES`, `_parse_inline_response`, the retained `time`/`urllib` globals in the webflow adapter) is re-exported with identity preserved.
- **No-spend is genuine** — autouse `_no_spend` deletes both keys (inherited by the test_00 subprocess), and every live entry hard-raises on an empty key before the lazy SDK import.
- **`_is_allowlisted_url` is sound** — all spoofs rejected: `…@evil.com` (host=`evil.com`), `EVIL.com` (lowercased), `englishcollege.com.evil.com`, `evil-englishcollege.com`. Only a trailing-dot FQDN is over-rejected (fail-closed, safe).
- **ARCHITECTURE composition example runs**; core API tables + copywriter CLI/flags/brief-fields/QA-contract all match code; the phantom `paginate`/`NetworkError`/`create/bulk` claims are confirmed GONE (PR #44).
- **L2 eval scaffold absence is documented as deferred** (`tools/_stress/README.md`), not silently dropped.
- **`/copywriter` vs `/multilingual-copy` triggers are disjoint** (improve/rewrite/tighten vs translate/write-in-lang) — no mis-routing; Turkish correctly stays with `/multilingual-copy` (not a CEL locale).
- **JUnit parsing + signature pins in test_10 are accurate**; test_00 handles the crash-before-XML case.

## Review-hotspot coverage (from the plan)

1. Shim identity mechanism → **L8** (fragile-by-design; correct today). 2. #5 config blast radius → **SAFE** (§solid). 3. test_00 subprocess+XML → correct; baseline staleness → **L1**. 4. `_is_allowlisted_url` urlparse edges → sound (§solid); trailing-dot → noted. 5. test_40 translate-spy → **M4** (vacuous). 6. http.py token leak → **none** (§solid). 7. `.importlinter` grimp/deferred-imports → **H1** (incomplete list); the contract is honest for what it lists (no core→consumer import exists), but grimp's deferred-import visibility means it should be enforced in a gate — the new `stress-test.yml` now does run `lint-imports`, closing the historical "nothing enforces it" gap.

## Agent-error note (transparency)

Audit agent A reported the regression baseline as "446 collected / 444 passing, zero slack." Executor re-measurement on `main` gives **460 / 458** for `-m "not stress"`. L1 reflects the corrected number (stale/loose, not zero-slack). All other agent findings were re-verified against live code before inclusion.

---

**Zero code changed — report only.** To act on these, run `/fix docs/reviews/002-session-audit-2026-05-25.md`. Suggested fix order: H1 (contract hole) → M1/M2 (QA correctness) → M3/M4 (dead param + weak test) → L1–L8 (hygiene). All are independent and low-risk.
