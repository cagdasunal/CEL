# `tools/summary/` — SEO Summary Generation + Weglot CSV Emission

Production pipeline for generating SEO summary content on englishcollege.com pages and emitting consolidated Weglot-ready translation CSVs.

## Status

**As of 2026-05-19 (tracker-087 closure)**: production-ready for workflow_dispatch. Previously "deployment-ready but execution deferred" framing was inaccurate — the audit-086 commit shipped two false-closure claims (H-1 missing `write_static_summary` function; C-4 stub `_execute_translate`). Both are now genuinely closed and exercised by the end-to-end stress test in `tests/test_end_to_end.py`. Live workflow_dispatch still requires the user to rotate API keys (see below) and trigger manually.

## Known limitations (resolved 2026-05-19 morning, tracker-087)

The following audit-086 closures were proven incomplete by `/review` 2026-05-17 and re-closed in tracker-087 (`docs/reviews/087-summary-script-followup-2026-05-19.md` in the monorepo):

- **H-1 (was false-closed)**: `write_static_summary` is now a real function in `webflow_designer.py`. The CEL `f094fad` commit had `cli.py:459` importing a symbol that didn't exist — first live static-page write would have `ImportError`. The Designer-API endpoints (`find_summary_element`, `write_summary_element`) remain DEPRECATED.
- **C-4 (was false-closed)**: `_execute_translate` actually runs the pipeline now. The CEL `f094fad` version was a skeleton that imported `LinkSwap`, `batch_runner`, `csv_emitter`, `llms_parser` but used none of them.
- **H-5 (was partial)**: persistent failures after the retry loop now land in `manual-review.json`. Tracker-086 had ticked H-5 as "MANUAL_REVIEW state written" — no such state was written before 2026-05-19.
- **M-1 (line-count partial)**: `prompts/common.md` is now 185 lines (was 139 in CEL `f094fad`) with 2026 SEO research corrections — keyword density narrowed to 1–2%, FAQPage schema 3.2× citation rate, EEAT re-weighted Trust > Experience > Expertise > Authoritativeness, 134–167 word answer-block target, anti-AI burstiness section.

## Known limitations (resolved 2026-05-19 afternoon, tracker-088)

The tracker-087 executor's final-summary observations surfaced 4 production-blocking bugs that would have broken the first live `workflow_dispatch`. tracker-088 (`docs/reviews/088-summary-production-readiness-2026-05-19.md` in the monorepo) closes them:

- **F-1 (was production bug)**: `config.WEGLOT_IMPORTS_DIR` pointed at `data/weglot-imports/`, but the dashboard + downloads + Weglot status page all serve from `docs/admin/weglot-imports/`. Live CSV writes would have been orphaned. Config now points at the served path.
- **F-2 (was production bug)**: `.github/workflows/summary.yml` had `timeout-minutes: 60` but `batch_runner.wait_for_batch` defaults to 24h timeout. Live runs > 60 min would have been killed mid-poll. Now `360` (6h, GHA free-tier hard cap). For batches > 6h, the user splits the workflow: `generate-english` first, then `translate --from-run <prior run dir>` separately once the batch completes in background.
- **F-3 (was production bug)**: `webflow_client.update_item_summary` wrote to `/items/{id}/live` which requires items already published — first-time writes on drafts returned 409. Switched to staged `/items/{id}`. The user publishes the Webflow site via Designer to push changes live, per `rules/workflow.md §7.1` ("Claude never publishes"). Pattern matches `tools/fidelo/cms_writer.py` + `cms_writer_courses.py` (monorepo) which already write to this CEL site.
- **F-4 (was production bug)**: CEL `tools/dashboard.py` + `docs/assets/css/dashboard.css` were uncommitted despite the monorepo equivalent shipping in audit-086 `340bc39`. Closes a `rules/dashboard-deploy.md` two-repo-lockstep violation. The 15-min `content-pipeline.yml` cron now renders IMAGES + WEGLOT-dropdown nav (was stale BLOG + FIDELO-Translations).

## Repository

This script lives in `cagdasunal/CEL` at `tools/summary/` and runs via `.github/workflows/summary.yml` (workflow_dispatch). It is **NOT** mirrored in the monorepo (`cagdasunal/webflow`) — the source of truth is here. Operator audits, design reviews, and rule changes happen in the monorepo (canonical skill files at `.claude/skills/page-summary/`); the script is the production deployment.

The Weglot CSV outputs land at `docs/admin/weglot-imports/<lang>.csv` and are served via GitHub Pages.

## ⚠️ Security: API key handling

The `WEBFLOW_API_TOKEN` value that was pasted in earlier planning conversations is in chat transcripts — **rotate before any live execution**. The new `GEMINI_API_KEY` (tracker-091 migration from Anthropic) is freshly issued by the user.

1. Webflow Dashboard → Site Settings → API Access → revoke any leaked token + generate a new one.
2. Google AI Studio (`englishcollege-seo` project) → create the API key restricted to "Generative Language API".
3. CEL repo → Settings → Secrets and variables → Actions:
   - `WEBFLOW_API_TOKEN` → paste new value.
   - `GEMINI_API_KEY` → paste the key (this secret name changed in tracker-091; the old `ANTHROPIC_API_KEY` is no longer used).

## Default mode = `--dry-run`

`--dry-run` (the default):
- Fetches live HTML for static landing pages (no API charge — public pages)
- Builds prompts + writes a JSONL batch payload to disk
- Does NOT call the Gemini API
- Does NOT write to Webflow CMS or commit CSV changes

`--no-dry-run`:
- Submits Gemini Batch API requests
- Polls for completion (≤24h SLA, 48h hard expiry)
- Writes Summary content to Webflow CMS items (Blog, Courses, Housing collections)
- For static pages, writes Markdown to `docs/admin/weglot-imports/static-summaries/<slug>.summary.md` for **manual paste** into Webflow Designer (auto-write to Designer was dropped per audit-086 H-1 — endpoints were unverified)
- Translate phase appends rows to `docs/admin/weglot-imports/<lang>.csv` per locale

## CLI

```bash
python3 -m tools.summary <subcommand> [--dry-run | --no-dry-run] [filters]
```

Subcommands:

| Subcommand | What it does |
|---|---|
| `plan` | Show what would be processed; produce report.json + report.md. Cheapest sanity check. |
| `generate-english` | Fetch source content, derive keywords, generate EN summaries for static pages + courses + housing. Blog posts get native-language summaries. |
| `audit` | Score existing summaries; surface REGENERATE candidates with reasons. |
| `translate` | Translate EN summaries into the 8 locales via the **`translator`** package (glossary + translation-memory + translation-QA); append rows to the per-language Weglot CSVs, consolidated with the existing Fidelo rows. |
| `translate-meta` | Translate static-page `<title>` + `<meta name="description">` into the 8 locales via the `translator`; emit Weglot CSV rows typed `meta_title` / `meta_description` (mobile-safe char limits flagged for Latin locales). |
| `all` | Run generate-english → audit → translate in sequence. |

Filters:

| Flag | Effect |
|---|---|
| `--collection blog\|courses\|housing_new` | Process only one collection. |
| `--page <URL>` | Process only one static page. |
| `--locale <code>` | Filter CSV emission to one locale. |
| `--limit <n>` | Cap items processed (use during pilot batches). |
| `--force` | `generate-english` only — regenerate every item even if its source content is unchanged since the last successful run (bypasses the summary-state idempotency skip). |
| `--out-dir <path>` | Override the run artifact location. |

## Running it

### Locally (dry-run)

```bash
cd /path/to/englishcollege
python3 -m tools.summary plan
```

Output: `data/seo-intel/summary-dryrun/<timestamp>/{report.json,report.md}`. No API calls, no writes.

### Via GitHub Actions (production)

CEL repo → Actions tab → "Summary script (Webflow CMS + landing pages → Weglot CSVs)" → "Run workflow" → choose:

- **mode**: `plan`, `generate-english`, `audit`, `translate`, or `all`
- **dry_run**: `true` (default) or `false` (real run)
- **collection_filter** / **locale_filter** / **limit**: optional

The workflow uploads dry-run artifacts as a build artifact (`summary-dryrun-<run-id>`). Live runs additionally commit changes to `docs/admin/weglot-imports/*.csv` + the static-summaries Markdown files.

## Pre-execution checklist (one-time setup)

Before flipping `dry_run=false`:

- [ ] Rotated `WEBFLOW_API_TOKEN` (was leaked in transcripts). `GEMINI_API_KEY` was freshly issued in tracker-091; restrict it to "Generative Language API" only.
- [ ] Added BOTH secrets (`WEBFLOW_API_TOKEN`, `GEMINI_API_KEY`) to CEL repo's GitHub Actions secrets.
- [ ] Reviewed dry-run output at least once on the `plan` subcommand.
- [ ] Verified the `Summary` rich-text field exists on the three target CMS collections (Blog, Courses, Housing). If missing, the script's first live run auto-creates it via `data_cms_tool.create_collection_rich_text_field`.
- [ ] **Ran a pilot live invocation with `--limit 1` FIRST.** The staged CMS endpoint (`/items/{id}`, switched from `/live` in tracker-088 F-3) has been validated against the sibling `tools/fidelo/cms_writer.py` pattern but has not been live-tested against the Webflow Data API v2 yet (no API key during the audit window). A `--limit 1` pilot confirms the endpoint accepts the PATCH payload, the staged write lands, and (after the user clicks Publish in Webflow Designer) the change propagates to the live site. Only after the pilot succeeds end-to-end should the full live run be triggered.

Static-page summaries do NOT auto-write — they land as Markdown files for manual paste into Webflow Designer. Plan to spend ~10–15 minutes pasting after each generate-english run that touches the 12 static pages.

### Pilot live-run procedure

```bash
# 1. Trigger workflow_dispatch with mode=generate-english, dry_run=false, limit=1
# 2. Wait for the workflow to complete (typical: 5–15 minutes for 1 item)
# 3. Open the affected CMS item in Webflow Designer (Blog or Courses or Housing — whichever the pilot hit)
# 4. Confirm the Summary field now contains the generated Markdown
# 5. Click "Publish" in Webflow Designer to push the staged change live
# 6. Verify the published page renders the summary correctly
# Only after step 6 succeeds, re-trigger workflow_dispatch without --limit for the full run.
```

## Architecture

```
tools/summary/
├── __init__.py
├── __main__.py            # python3 -m tools.summary <subcommand>
├── cli.py                 # argparse + orchestration (_execute_* functions)
├── config.py              # locale codes, collection IDs, model, exclusions, cost cap
├── page_fetcher.py        # stdlib HTML fetch + parse (title, H1, headings, summary element, body)
├── keyword_extractor.py   # /page-summary Phase 2.5 derivation
├── llms_parser.py         # llms.txt → structured graph
├── prompt_builder.py      # composes system + user messages (Gemini caches implicitly on Batch tier)
├── qa.py                  # locked rule checks (em-dash, lists, keyword placement, density)
├── audit.py               # score existing summaries → REGENERATE / KEEP / MANUAL_REVIEW
├── webflow_client.py      # CMS Data API reader/writer (dry-run safe; pagination via metadata)
├── webflow_designer.py    # static-page summary → Markdown file (manual paste)
├── batch_runner.py        # Gemini Batch API submission + retrieval + cost estimator (tracker-091); shared by the translator
├── csv_emitter.py         # summary paragraph splitters; re-exports Weglot-CSV emission from tools/translator/weglot.py (tracker-094)
├── requirements.txt       # documents google-genai SDK (installed via CEL root requirements.txt)
├── prompts/
│   ├── common.md          # locked critical rules (~200 lines; 2026-refreshed)
│   ├── blog_post.md       # blog post adaptation
│   ├── course.md          # course adaptation
│   ├── housing.md         # housing adaptation
│   ├── landing.md         # static landing page adaptation
│   └── locales/
│       ├── README.md      # canonical dimension checklist + coverage matrix
│       └── {en,de,fr,es,it,pt,ko,ja,ar}.md
└── tests/                 # pytest suite (see Tests section for the current count + files)
```

### Sibling package: `tools/translator/`

Translation is handled by the reusable **`tools/translator/`** package (renamed from
`tools/translation_engine/` in tracker-094), not by the summary tool directly. The
`translate` and `translate-meta` phases call `translator.translate_batch(...)`, which
adds a glossary (do-not-translate brand/entity terms), a translation-memory (skips
unchanged source), and translation-QA (number/URL/placeholder preservation) on top of
the shared `batch_runner` Gemini client. The Weglot-CSV emission also lives there
(`tools/translator/weglot.py`) — `csv_emitter.py` re-exports it. Other CEL tools can
reuse the translator independently; see `tools/translator/README.md` for the full API.

## Cost expectation

Rough estimate against the live CEL catalog (491 generate-english + 1,352 translate ≈ 1,843 Gemini API calls):

- Gemini 3.1 Pro Preview + Batch API (already 50% off standard) + implicit caching: **~$15 USD full sweep**
- Skip-translate (491 generate-english only): **~$5 USD**
- Per new blog post (ongoing): **~$0.01–0.02 USD**
- Single-request pilot (`--limit 1`): **~$0.002 USD**

Pricing as of 2026-05-19; verify at https://ai.google.dev/gemini-api/docs/pricing.

Migrated from Anthropic Claude Opus 4.7 → Gemini 3.1 Pro Preview in tracker-091 for ~7× cost reduction at equivalent benchmarks (Artificial Analysis Intelligence Index 57 = 57).

Defensive cost cap: `MAX_BATCH_COST_USD = 100` in `config.py`. The orchestrator estimates cost before each batch submission and aborts if it would exceed the cap. With Gemini's lower per-request cost, this cap is now ~7× margin — safer.

## Troubleshooting

### "GEMINI_API_KEY env var not set"
The script ran in `--no-dry-run` but the secret isn't configured. Add to CEL repo Secrets and re-run.

### "WEBFLOW_API_TOKEN env var not set"
Same as above for the Webflow token.

### "Cost cap exceeded"
The batch estimate exceeded `MAX_BATCH_COST_USD` (100). Either reduce scope (`--limit` flag) or raise the cap in `config.py`. Don't raise without thinking — the cap is defensive.

### "Batch submission timed out"
`wait_for_batch` polls for ≤24 hours then raises `TimeoutError`. If this fires, check the Google AI Studio / Gemini batch console for batch status; it may still be processing (48h hard expiry). Re-run the workflow to re-poll.

### Partial batch failures
Each generation can fail individually (model refusal, token overrun, etc.). The orchestrator retries failed items once with a tightened prompt. After retry, persistent failures are logged in the run report and marked MANUAL_REVIEW. They do not block the rest of the run.

### Webflow API auth failure (401)
The `WEBFLOW_API_TOKEN` is expired or revoked. Rotate, update the GitHub Secret, re-run.

### "Webflow API 404 — collection not found"
The collection IDs in `config.py:COLLECTIONS` are stale. Re-verify against the Webflow Dashboard.

### "Summary field doesn't exist on collection"
The script's `ensure_summary_field` auto-creates the field on the first live run. If it fails (permissions / schema lock), add manually via Webflow Designer → CMS → Collection Settings → Add Field → "Summary" (rich text).

### "Static page summary written but not visible on the live page"
The script does NOT auto-write to static pages (audit-086 H-1). After a live run, navigate to `cel.englishcollege.com/admin/weglot-imports/static-summaries/`, download the relevant `.summary.md` file, and paste the Markdown into the Rich Text element on the page in Webflow Designer. Publish.

### "CSV import status shows pending"
The script appends rows to `docs/admin/weglot-imports/<lang>.csv` but Weglot doesn't auto-ingest. After a live run, the user must:
1. Go to Weglot Dashboard → Translations → Import/Export
2. For each language, click "Import" and upload the corresponding `<lang>.csv`
3. Confirm the rows imported

The dashboard's "Translations" tab shows the per-language import status badge.

### Local test suite fails after a change
`python3 -m pytest tools/summary/tests/ -q` should pass clean. If a test fails after a config change, check whether the assertion is stale (e.g., the cache_control shape changed when `ttl: "1h"` was added — `test_prompt_builder.py` was updated).

## Failure modes + recovery

| Failure | Symptom | Recovery |
|---|---|---|
| Gemini rate limit | Batch submission returns 429 | SDK auto-retries with backoff. If persistent, reduce `--limit` and re-run. |
| Gemini batch infrastructure issue | Random per-request failures within a successful batch | Tracker-091 retry-once + MANUAL_REVIEW path handles this. Google has flagged this as a known incident in the Batch API docs. |
| Webflow CMS write conflict (412) | update_item_summary returns 412 | Item was modified between read and write. Re-run; the orchestrator will re-fetch. |
| `--no-dry-run` with no SDK installed | `ImportError: google.genai` | Install via `pip install -r requirements.txt` (CEL root). |
| Static page has no `id="summary"` element | The static-page summary is generated but invisible on the page | Add the element manually in Webflow Designer (one-time per page). |
| Workflow timeout | GitHub Actions kills the job at 60 minutes | Run with `--limit N` to keep batches small. The 24-hour batch SLA is the bottleneck for large runs. |

## Adding a new locale

1. Create `prompts/locales/<code>.md` (use any existing file as template).
2. Add `<code>` to `config.LOCALES` and the locale's value to `TARGET_TRANSLATION_LOCALES` if translation is intended.
3. Add a column to `prompts/locales/README.md` coverage matrix.
4. Re-run dry-run to confirm wiring.

## Adding a new content type

1. Create `prompts/<type>.md`.
2. Add the mapping in `prompt_builder._content_type_filename()`.
3. Update `cli._plan_generate_english` to include the new content type.

## Hard rules the script enforces

These ship as system-prompt content in `prompts/common.md`. The QA layer (`qa.py`) checks them on output:

- No em dashes (—, –).
- No bullet/numbered lists (paragraphs only).
- Primary keyword in H2 + first 120 chars of P1 + ≥1 H3.
- Body keyword density 0.5–2.5%.
- Internal link density 2–5 per 1000 words.
- First-occurrence-only link rule.
- Never link to URLs containing `/vc/`, `/sd/`, `/sm/`.
- Server-rendered Markdown output; no JavaScript-injected schema, hreflang, or canonicals.
- Numerals over spelled-out numbers.
- First mention of CEFR/IELTS/TOEFL iBT/PGWPP/DLI uses full name + abbreviation.

## What this script does NOT do

- Does NOT publish the Webflow site (user publishes manually per `rules/workflow.md` §7.1).
- Does NOT auto-write to static landing pages (manual paste; see above).
- Does NOT modify Weglot Dashboard config — only emits CSVs the user imports.
- Does NOT touch Fidelo sync logic — appends to Fidelo's CSV output.
- Does NOT add a scheduled cron; `workflow_dispatch` only.

## Tests

```bash
cd /path/to/englishcollege
python3 -m pytest tools/summary/tests/ tools/translator/tests/ -q   # 168 passed
```

Current: **135 tests** across 12 files in `tools/summary/tests/` (audit, batch_runner, cli, csv_emitter, end_to_end, keyword_extractor, llms_parser, page_fetcher, prompt_builder, qa, webflow_client_dryrun, webflow_designer) plus **33 tests** in `tools/translator/tests/` (engine, glossary, qa, tm, weglot) — **168 total**. The summary suite covers the Phase-1 QA quality-gate (`qa.py`) and Phase-2 idempotency/retry hardening; the translator suite covers glossary, translation-memory, translation-QA, and the Weglot-CSV/Fidelo-merge.

## References

- Canonical rule set: `cagdasunal/webflow/.claude/skills/page-summary/SKILL.md` (in the monorepo).
- 2026 SEO research backing the rules: `cagdasunal/webflow/.claude/skills/page-summary/best-practices.md`.
- llms.txt source: https://cel.englishcollege.com/llms.txt (765 URLs, 9 locales).
- Webflow Data API v2: https://developers.webflow.com/v2.0.0/data/reference
- Gemini Batch API: https://ai.google.dev/gemini-api/docs/batch-api
- Gemini pricing: https://ai.google.dev/gemini-api/docs/pricing
- google-genai SDK (Python): https://github.com/googleapis/python-genai
- Audit tracker: `cagdasunal/webflow/docs/reviews/086-summary-script-audit-2026-05-16.md`
- Migration tracker: `cagdasunal/webflow/docs/reviews/091-summary-gemini-migration-2026-05-19.md`
