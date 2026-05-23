# `tools/translator/` — reusable LLM translation component

A small, dependency-light translator built on Google **Gemini** (Batch API) + Python
stdlib. It wraps a raw Gemini call with the three layers production translation
needs — a **translation memory** (don't re-translate unchanged source), a
**glossary** (do-not-translate brand/entity terms; forbidden/preferred), and
**translation QA** (placeholder / number / URL preservation, passthrough,
length-ratio) — and emits **Weglot import CSVs** that consolidate cleanly with the
**Fidelo** translations already in those files.

Renamed from `tools/translation_engine/` in tracker-094. Canonical home: `cagdasunal/CEL`.

## Why it exists / when to use it

Use the translator from any CEL tool that needs to turn English strings into the 8
locale CSVs Weglot imports (published on the dashboard). Today it powers the summary
tool's `translate` and `translate-meta` phases; it's designed so other tools (CMS
fields, UI strings, new content types) can adopt it without copying translation,
glossary, memory, or CSV-format logic.

It depends on the summary tool only for the shared Gemini client:
`tools.translator.engine` imports `tools.summary.batch_runner`. Everything else
is Python stdlib, and the Weglot CSV writer (`tools.translator.weglot`) has no
summary dependency at all. To reuse the translator from a non-CEL project,
vendor `tools.summary.batch_runner` (+ its `config`) alongside it, or lift the
shared Gemini client into a neutral location.

## Public API

```python
from tools.translator import translate_batch, TranslationUnit, Translation
from tools.translator.glossary import load_glossary
from tools.translator.tm import TranslationMemory
from tools.translator.weglot import pairs_from_translations, emit_consolidated_csv

glossary = load_glossary()                                  # bundled CEL brand/entity terms
tm = TranslationMemory(Path("data/seo-intel/translation-memory.json"))

units = [TranslationUnit(id="title::home", text="Learn English at CEL", content_type="meta_title")]
results = translate_batch(units, "de", glossary, tm=tm)     # → list[Translation], input order

# Turn results into Weglot CSV rows + merge into the per-locale file (preserving Fidelo rows):
pairs = pairs_from_translations(results, type_="meta_title")
emit_consolidated_csv(target_locale="de",
                      existing_csv_path=Path("docs/admin/weglot-imports/de.csv"),
                      summary_pairs=pairs,
                      out_path=Path("docs/admin/weglot-imports/de.csv"))
```

`translate_batch(units, target_locale, glossary, *, tone=None, tm=None, dry_run=False, request_builder=None, api_key_env="GEMINI_API_KEY")`:

1. **TM lookup** — units whose `(normalized source, locale, glossary_version, tone)`
   hash is cached are returned with `from_tm=True` and **no API call**.
2. **Glossary slice** — for each miss, the terms present in the text are injected into
   the prompt prefix (matched terms only, not the whole termbase).
3. **Gemini batch** — one request per miss via `batch_runner` (so it inherits the
   truncation guard, `max_tokens`, and transient-error backoff). Pass a
   `request_builder(unit, locale, glossary_slice) -> (system_blocks, user_message)`
   to override the default generic translator prompt (the summary caller does this
   to reproduce its exact summary-translation prompt + llms.txt link swaps; since
   2026-05-23 it uses `llms_parser.find_equivalent_or_fallback` — if no exact
   slug-equivalent exists for a source URL in the target locale, it falls back to
   the nearest same-locale ancestor in the index, then the locale root, rather than
   removing the link entirely; this preserves link equity on pages where locales
   use different slug conventions).
4. **Glossary post-edit** — a **forbidden** term in the output is BLOCKING (sets
   `ok=False`); a dropped **do-not-translate** term is flagged (advisory — DNT is
   enforced via the prompt slice, not by rewriting); **preferred** is SOFT (warn
   only — over-rigid enforcement lowers quality).
5. **Translation QA** — see below. Sets `Translation.ok=False` on a blocking failure.
6. **TM write** — only `ok` translations are cached (live mode).

`dry_run=True` returns passthrough stubs (`qa_flags=["dry_run"]`) and never calls
Gemini — for wiring tests and offline runs.

### `Translation` fields
`id, source, target, target_locale, from_tm: bool, qa_flags: list[str], ok: bool`.
`ok=False` means a BLOCKING QA check failed (placeholder/number/URL/HTML) or the
target was empty — the caller should not ship it. `qa_flags` carries non-blocking
warnings too (e.g. `untranslated_passthrough`, `length_ratio:3.1`).

## Modules

| Module | Responsibility |
|---|---|
| `engine.py` | `translate_batch` — the pipeline above. |
| `units.py` | `TranslationUnit` (input), `Translation` (output) — frozen dataclasses. |
| `glossary.py` | `load_glossary`, per-unit term `match`, `prompt_slice`, two-tier `enforce`. |
| `glossary.json` | Seeded CEL brand/entity do-not-translate terms (CEL, CEFR, IELTS, TOEFL, DLI, PGWPP, ACCET, CEA, city names, visa codes…). Bump `version` to invalidate the TM. |
| `tm.py` | `TranslationMemory` — JSON store keyed by `sha256(normalize(source)) + locale + glossary_version + tone`. Exact-match; FIFO-capped at 20 000 entries. |
| `qa.py` | `check_translation(source, target, locale) -> (ok, flags)`. Blocking: placeholder/variable set, number, URL preservation. Warning: untranslated passthrough, per-locale length-ratio band. |
| `weglot.py` | The reusable Weglot-CSV adapter (see below). |

## Weglot CSV output (`tools.translator.weglot`)

Owns the Weglot import-CSV format — byte-identical to the Fidelo exporter
`tools/weglot/csv_export.py` (monorepo):

```
id;language_from;language_to;word_from;word_to;type     (semicolon, minimal-quote, LF)
```

- `WeglotPair(word_from, word_to, type_="Text")` — one row.
- `pairs_from_translations(translations, type_) -> list[WeglotPair]` — 1:1 map, skips empties.
- `emit_consolidated_csv(target_locale, existing_csv_path, summary_pairs, out_path)` —
  **reads the existing per-locale CSV** (which already holds Fidelo rows), **dedups on
  `(word_from, language_to)`**, appends the new rows, and atomic-writes. A translator
  run therefore **never clobbers Fidelo translations** — Fidelo and translator rows
  coexist in one file. Idempotent: same inputs → byte-identical output.
- `EmissionReport.warnings` — populated when the written CSV approaches Weglot's
  **5 MB file-size import limit**. Per the Weglot Help Center ([432](https://support.weglot.com/article/432-what-can-we-export-import),
  [206](https://support.weglot.com/article/206-can-i-export-my-translations)), a
  **general translation CSV import** (what this emitter produces) has **no documented
  row maximum** — only the 5 MB size cap and a UTF-8 requirement. The separate
  **500-element cap applies to Dynamic Content / URL-slug / Exclusion-rule imports, not
  this CSV** (live locale files are already 538–593 rows and import fine). Largest live
  file ≈ 222 KB, so the warning is dormant headroom that fires only if the consolidated
  CSV genuinely grows toward 5 MB. Callers should surface `report.warnings` to their run
  report (the summary CLI does); the authoritative post-import completeness check is the
  sentinel verifier (`docs/admin/weglot-imports/import-status.json`).

The summary tool's `tools/summary/csv_emitter.py` re-exports these (keeping
`SummaryPair` as a back-compat alias) and adds its summary-specific paragraph
splitters.

## Glossary

`glossary.json` is `{"version": "...", "terms": [{term, do_not_translate, forbidden,
preferred: {locale: str}, case_sensitive}]}`. Edit it to add brand/entity terms and
**bump `version`** — the version is part of the TM key, so a glossary change forces
re-translation of affected strings rather than serving stale cache hits.

## Tests

```bash
python3 -m pytest tools/translator/tests/ -q
```
`test_engine.py` (pipeline, TM hit, glossary+QA, ordering), `test_glossary.py`,
`test_tm.py` (key/version invalidation, FIFO cap), `test_qa.py`, and `test_weglot.py`
(Fidelo-row coexistence + dedup). Gemini is mocked at the `batch_runner` boundary —
no live API calls in tests.

## References
- Built in tracker-092 Phase 3; renamed + given `weglot.py` in tracker-094 (`cagdasunal/webflow/docs/reviews/`).
- Gemini Batch API: https://ai.google.dev/gemini-api/docs/batch-api
- Fidelo→Weglot CSV exporter (format authority): `cagdasunal/webflow/tools/weglot/csv_export.py`.
