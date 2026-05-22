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

## 4-part Summary structure (tracker-096, 2026-05-21)

The Summary section was redesigned so it reads like a genuine, designed part of the page rather than an SEO block. Courses, Housing, and the static landing pages now use a **4-part** structure; **blog posts keep the single-block** summary unchanged.

| Part | Static element id | Courses/Housing CMS field slug | Type | Rule |
|---|---|---|---|---|
| Tagline | `#summary-tagline` (H2) | `summary---tagline` | PlainText | 2–3 related words (editorial kicker) |
| Title | `#summary-title` (H3) | `summary---title` | PlainText | short title; primary keyword lands here |
| Paragraphs | `#summary-paragraphs` | `summary---paragraphs` | RichText | 1–2 lead paragraphs; may carry inline links |
| Content | `#summary-content` (rich) | **`summary`** (renamed "Summary - Content") | RichText | starts at H4, uses H5; carries the rest of the links |

- The model emits ONE Markdown document (`## Tagline` → `### Title` → Paragraphs → `#### …` Content); `tools/summary/structure.py` (`parse_four_part`) splits it into the four parts. `four_part_paragraph_html` renders the Paragraphs part and `four_part_content_html` renders the Content part to the HTML subset Webflow's RichText field needs (plain Markdown would render literal `####` / `[](url)`). Only the two plain parts (Tagline, Title) are written as stripped plain text.
- **CMS write** (tracker-098): `webflow_client.update_item_summary_body` patches ONLY the two RichText bodies — `summary---paragraphs` + `summary` (Content) — as HTML, **preserving the author-owned Tagline + Title** (the model still emits them, but write-back never overwrites them). `update_item_summary_parts` is retained for back-compat/tests but is no longer the write path. Note the slug asymmetry: CMS slugs use triple hyphens, static element ids use single hyphens.
- **Static write**: `webflow_designer.write_static_summary_parts` writes one `<slug>.summary.md` with 4 labeled sections for paste into the 4 elements.
- **QA**: `qa.qa_checks(..., structure="four_part")` validates the 4-part contract (Tagline 2–3 words, keyword in Title + Paragraph, no links in Tagline/Title, H4/H5-only Content, 6–8-link target + anti-stuffing ceiling). The `structure="single_block"` (blog) path adds a CRITICAL same-locale link check. Blog Markdown is rendered to HTML by `summary_markdown_to_html` before the CMS PATCH.
- **Internal-link domain rule (CRITICAL, both structures — 2026-05-22 /housing guardrail)**: `links_internal_domain` rejects any summary whose link targets are not root-relative paths or `englishcollege.com` URLs (subdomains OK). A foreign domain (e.g. a hallucinated `https://claude.ai/…`) is a hard FAIL → the summary is held back to `MANUAL_REVIEW`, never staged/deployed. The check runs unconditionally (no inventory/source needed), so the audit phase catches off-domain links in already-live summaries too. The prompt (`common.md` → Internal linking) also states the domain rule explicitly as the first bullet. Before this, the only domain-aware check (`link_in_inventory`) was a non-critical warning, so a hallucinated off-site link could pass QA — which is how a few external links reached the live `/housing` page.
- **Vancouver pages**: 4 new static pages (`/vancouver`, `/vancouver/cost-of-studying-english`, `/vancouver/how-long-to-learn-english`, `/vancouver/vs-toronto`) were added → **16 static pages** total.
- `SUMMARY_PROMPT_VERSION` bumped to `2026-05-21-t096`, which invalidates the idempotency hash + translation memory so existing items regenerate under the new structure.

### Processing modes + Gemini quota (operational, 2026-05-20)

- **Blog posts** keep the single-block summary (no 4-part structure) but ARE summarized. They carry their language as a `language` **Reference**, so the locale is resolved via `config.BLOG_LANGUAGE_ID_TO_LOCALE` → each post gets a summary in its own language (415 posts across 9 locales).
- **Batch (default)** — cheapest + async, the right mode for the full catalog. Requires Batch API quota: as of 2026-05-20 a full-catalog batch returned `429 RESOURCE_EXHAUSTED` ("check your plan and billing") on `batches.create`, i.e. **the Gemini project needs billing enabled to use the Batch API at scale** (esp. the 415 blog posts).
- **Sync (`--sync`)** — instant `generateContent`, validated live (a 2-course run wrote 2/2 staged, QA-passed, in ~1m). Sequential + RPM-limited, so it's for **testing + small runs**, NOT the full 415-post blog catalog.
- **Live-validated**: the 4-part CMS write path was confirmed end-to-end (sync 2-course run → 4 staged fields, QA passed) before any fan-out.

## Internal-link remediation — `link-blogs` mode (2026-05-22)

An audit found **138 of 241 blog summaries had ZERO internal links** (Flash under-followed
the 6–8-link instruction; the 4-part course/housing/landing pages were fine at ~7.5 links).
The fix is a dedicated **link-insertion** pass that ADDS links to the existing summary
WITHOUT regenerating the prose:

```bash
# Pilot (2 EN blogs, instant/sync):
python3 -m tools.summary link-blogs --no-dry-run --sync --locale en --limit 2 \
    --from-run data/seo-intel/run-098-full --confirm-cost
# Full zero-link remediation (all locales, Batch):
python3 -m tools.summary link-blogs --no-dry-run --confirm-cost \
    --from-run data/seo-intel/run-098-full
```

- **Source**: the `--from-run` manifest's existing summary Markdown. Only blog_post entries
  with `<= --max-existing-links` internal links (default **0** → just the zero-link blogs)
  are processed; the live blog collection supplies the `cms_item_id` for the staged write-back.
- **Model**: Gemini 2.5 Flash, `thinking_budget=0` — optimized for the narrow link-only task.
- **Prompt** (`prompts/link_insertion.md`): wrap EXISTING phrases in `[phrase](url)`; change
  no words; 6–8 same-locale `www.englishcollege.com` links; never in a heading.
- **Acceptance gate** (all must hold or the item is held back, never written): `qa.text_preserved`
  (de-linked output ≈ original, so the prose wasn't rewritten) **AND** the critical QA checks
  (`links_internal_domain`, `links_locale_matched`, `no_link_stuffing`) **AND** ≥1 link added.
  Demotions are logged to `link-blogs-review.json`.
- **Housing**: `config.HOUSING_LINK_CANDIDATE_CAP` (1 → **3**) lets the new `/housing` detail
  pages (now in llms.txt for every locale) be linked from topically-relevant posts.

## www + cross-locale link rules (2026-05-22)

- **www**: every full URL must be `https://www.englishcollege.com/…`. `cli._sanitize_summary`
  normalizes any bare `https://englishcollege.com` → `www.` before QA + write-back; the prompts
  state the rule.
- **Cross-locale (translation)**: a translated summary links ONLY to same-locale URLs. The
  translate phase swaps each source link to its `/{locale}/` equivalent via
  `LlmsIndex.find_equivalent`; when there is **no** equivalent the link is **removed** (kept as
  plain prose), never linked cross-language. Reinforced in `build_translation_user_message`.

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
- For static pages, writes Markdown to `docs/admin/weglot-imports/static-summaries/<slug>.summary.md` for **manual paste** into Webflow Designer (the `tools/summary` tool itself never auto-writes static pages — audit-086 H-1). **An agent can, however, deploy these directly via the Webflow Designer MCP — see the static-page note below (proven 2026-05-22).**
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
| `--sync` | `generate-english` only — use synchronous Gemini `generateContent` (instant, no Batch API ≤24h SLA) instead of the Batch API. Higher per-call cost; for **fast testing + small runs** (sync is sequential + RPM-limited, so it does NOT scale to the full catalog / 415 blog posts). The full catalog uses the default (Batch). |
| `--exclude-blog` | Skip the blog collection (static + courses + housing only). Blog keeps its single-block summary; this just lets the 4-part scope run without regenerating the 415 blog posts. |
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
- **sync**: `true` = instant synchronous `generateContent` (fast testing + small runs); `false` (default) = Batch API
- **exclude_blog**: `true` = run static + courses + housing without regenerating blog (tracker-096 "except Blog Posts")
- **collection_filter** / **locale_filter** / **limit**: optional

The workflow uploads dry-run artifacts as a build artifact (`summary-dryrun-<run-id>`). Live runs additionally commit changes to `docs/admin/weglot-imports/*.csv` + the static-summaries Markdown files.

## Pre-execution checklist (one-time setup)

Before flipping `dry_run=false`:

- [ ] Rotated `WEBFLOW_API_TOKEN` (was leaked in transcripts). `GEMINI_API_KEY` was freshly issued in tracker-091; restrict it to "Generative Language API" only.
- [ ] Added BOTH secrets (`WEBFLOW_API_TOKEN`, `GEMINI_API_KEY`) to CEL repo's GitHub Actions secrets.
- [ ] Reviewed dry-run output at least once on the `plan` subcommand.
- [ ] Verified the `Summary` rich-text field exists on the three target CMS collections (Blog, Courses, Housing). If missing, the script's first live run auto-creates it via `data_cms_tool.create_collection_rich_text_field`.
- [ ] **Ran a pilot live invocation with `--limit 1` FIRST.** The staged CMS endpoint (`/items/{id}`, switched from `/live` in tracker-088 F-3) has been validated against the sibling `tools/fidelo/cms_writer.py` pattern but has not been live-tested against the Webflow Data API v2 yet (no API key during the audit window). A `--limit 1` pilot confirms the endpoint accepts the PATCH payload, the staged write lands, and (after the user clicks Publish in Webflow Designer) the change propagates to the live site. Only after the pilot succeeds end-to-end should the full live run be triggered.

Static-page summaries do NOT auto-write — they land as Markdown files for manual paste into Webflow Designer. Plan to spend ~10–15 minutes pasting after each generate-english run that touches the 16 static pages. tracker-096: each static `.summary.md` now carries 4 labeled sections (Tagline / Title / Paragraph / Content) to paste into the four `#summary-*` elements.

**Agent-driven MCP deploy (proven 2026-05-22):** the manual paste is now optional — an agent can deploy the static-page summaries directly into the page's `Section / Summary` (and `Section / Summary / Alternative` on the Vancouver-cluster pages) component instances via the Webflow **Designer MCP**, with real inline links preserved. The parts are **richText component-instance props** (`Paragraphs`, `Content`/`Summary`). The ONLY working write path is: `element_builder` targeting the empty prop element — its `parent_element_id` accepts the `prop` field (which `whtml_builder` does not) — to seed one Paragraph, then `whtml_builder` to insert the real `<p>`/`<a>`/`<h4>` blocks as siblings after the seed, then `element_tool > remove_element` to delete the seed. Writes are **per-instance** (no cross-page leakage). What does NOT work on the primary locale: the Data API `data_localization_tool.update_static_content` (primary locale is read-only), `de_component_tool.set_component_instance_prop_values` (rejects plain text for richText), and `rich_text_inner_text` (escapes HTML → links die). This supersedes the earlier "rich-text component props can't be set via MCP" conclusion.

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
├── structure.py           # tracker-096: 4-part parse (Tagline/Title/Paragraph/Content) + Content Markdown→HTML
├── webflow_client.py      # CMS Data API reader/writer (dry-run safe; single-field + 4-part writes)
├── webflow_designer.py    # static-page summary → Markdown file (single-block or 4-section, manual paste)
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

**Verified pricing (2026-05-21, https://ai.google.dev/gemini-api/docs/pricing):**

| Model | Interactive (`--sync`) in/out per 1M | Batch in/out per 1M | Cached read per 1M |
|---|---|---|---|
| Gemini 3.1 Pro Preview (landing/courses/housing) | $2.00 / $12.00 | $1.00 / $6.00 | $0.20 |
| Gemini 2.5 Flash (blog) | $0.30 / $2.50 | $0.15 / $1.25 | $0.03 |

The workload is **input-token dominated**: ~6,500 tokens of stable system prefix + ~1,000 tokens of body/links per request, ~800 output. So input price + prefix re-use drive the bill.

### tracker-097 cost levers
- **Honest estimation.** `estimate_batch_cost_usd` prices by the path actually billed (`--sync` = interactive, default = Batch) and credits caching only when it engages. The earlier estimator priced sync at Batch rates and assumed a fictional cached prefix, so it undershot real spend ~2×.
- **Explicit context caching** of the shared system prefix (per content-type/locale/model group; Batch path). Drops the prefix from full input rate to the cache-read rate — **~60% input-cost reduction** on a typical run. Fallback-safe: a cache failure degrades to full price. Toggle with `config.ENABLE_EXPLICIT_CACHE`.
- **Model tiering.** The 415 blog posts (single-block, bulk) run on **Gemini 2.5 Flash** (~6.7× cheaper input, `thinking_budget=0`); the high-value designed pages (landing/courses/housing 4-part) stay on **Pro**. See `config.model_for_content_type`. The QA gate is the quality backstop.
- **Idempotency across runs.** `summary-state.json` is now committed by the workflow, so a re-run no longer re-bills unchanged items (the model is folded into the hash, so retiering regenerates correctly).

Rough full-catalog estimate after these levers: well under the cap; a single blog post ~$0.002–0.005; a `--limit 1` pilot ~$0.001.

### Spend guardrails
- **Hard cap**: `MAX_BATCH_COST_USD = 15` in `config.py` (was 100). A run aborts before submitting if the projection exceeds it.
- **Pilot-first confirm gate**: a LIVE run projected over `COST_CONFIRM_THRESHOLD_USD` ($1) refuses to submit unless `--confirm-cost` is passed (workflow input `confirm_cost`). You always see the projected cost (in `report.json` → `phases.generate_english.cost_gate`) before any spend.
- **Orphaned-batch recovery**: a submitted Gemini batch keeps billing even after its GitHub Actions run is cancelled. `submit_batch` persists the batch id to `data/seo-intel/summary-last-batch.json` (committed); `python3 -m tools.summary cancel-batch [--batch-id …]` stops it and `retrieve-batch` reclaims its results.

Migrated from Anthropic Claude Opus 4.7 → Gemini 3.1 Pro Preview in tracker-091 (Artificial Analysis Intelligence Index 57 = 57).

## Troubleshooting

### "GEMINI_API_KEY env var not set"
The script ran in `--no-dry-run` but the secret isn't configured. Add to CEL repo Secrets and re-run.

### "WEBFLOW_API_TOKEN env var not set"
Same as above for the Webflow token.

### "COST CAP EXCEEDED"
The estimate exceeded `MAX_BATCH_COST_USD` (15). Either reduce scope (`--limit`) or raise the cap in `config.py`. Don't raise without thinking — the cap is defensive (tracker-097 lowered it 100 → 15).

### "COST CONFIRM REQUIRED"
A LIVE run is projected over `COST_CONFIRM_THRESHOLD_USD` ($1) and no batch was submitted (pilot-first). Review the projected cost in `report.json` → `cost_gate`, then re-run with `--confirm-cost` (workflow input `confirm_cost: true`) to authorize the spend.

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
- Primary keyword placement (tracker-096): blog (single-block) → H2 + first 120 chars of P1 + ≥1 H3; courses/housing/landing (4-part) → Title (H3) + first 120 chars of the Paragraph.
- Body keyword density 0.3–2.0% (`qa.py` `_DENSITY_LOW`/`_DENSITY_HIGH`).
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
python3 -m pytest tools/summary/tests/ tools/translator/tests/ -q   # 209 passed
```

Current: **170 tests** across 13 files in `tools/summary/tests/` (audit, batch_runner, cli, csv_emitter, end_to_end, keyword_extractor, llms_parser, page_fetcher, prompt_builder, qa, structure, webflow_client_dryrun, webflow_designer) plus **39 tests** in `tools/translator/tests/` (engine, glossary, qa, tm, weglot) — **209 total**. The summary suite covers the Phase-1 QA quality-gate (`qa.py`), Phase-2 idempotency/retry hardening, and the tracker-096 4-part structure (`structure.py` parse + Markdown→HTML + audit reconstruction, and the 4-part QA path); the translator suite covers glossary, translation-memory, translation-QA, and the Weglot-CSV/Fidelo-merge.

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
