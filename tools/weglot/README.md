# Weglot Exclusion Sync

Automated system that detects new blog posts on englishcollege.com and creates their Weglot translation exclusions through the Weglot API.

## Problem

When a blog post is published in a specific language (e.g., Italian), Weglot auto-creates translated versions for all 8 target languages. Posts that are already in their original language should NOT be translated. Without exclusion rules, this creates duplicate/ghost pages — terrible for SEO.

## How It Works

Runs as **Step 1 of the Content Pipeline** (`.github/workflows/content-pipeline.yml`, scheduled every 15 minutes) via `tools/weglot/api_sync.py`:

1. **Fetches all published blog posts** from the Webflow CMS API (archived and never-published posts are skipped)
2. **Reads Weglot's current `excluded_paths`** with `GET /projects/settings` (public key)
3. **Computes the delta** — posts that are published but not yet excluded, with the languages to exclude (every target language except the post's own)
4. **POSTs the full merged list** (existing entries verbatim + the new ones, uppercase enums `IS_EXACTLY` / `REDIRECT`) with the private key
5. **Verifies with a second GET** and exits 2 if any existing entry lost its `excluded_languages`
6. **Writes state** to `data/weglot-exclusions.json` (new entries carry `source: api`) and `data/weglot-sitemap-exclusions.json`, and signals the pipeline to regenerate `sitemap.xml` / `llms.txt` when something changed

No manual import is needed. Use `python3 tools/weglot/api_sync.py --dry-run` to preview and `--status` to print the state.

## History: the per-language bug (fixed)

On 2026-04-14 `POST /projects/settings` silently stripped `excluded_languages` from **every** entry in the array (not only the new one), which is why per-language exclusions were imported by CSV until April. Weglot fixed it; it was verified on 2026-04-21 (317 baseline entries preserved, 0 stripped) and still holds — the exclusions created through the API since then carry the correct per-language lists (checked 2026-10-06). Keep the step-5 verification in `api_sync.py`: it is the guard against a regression, and always POST the full merged list, never a partial one.

## The retired CSV path

Until 2026-04-22 the exclusions were written to `weglot.csv` for a manual dashboard import by `tools/weglot/sync_exclusions.py` (`.github/workflows/weglot-sync.yml`, every 15 minutes), which also confirmed an import and cleared the CSV. That workflow is **disabled** (manual run only); `sync_exclusions.py` stays as the rollback path. `data/weglot.csv` therefore exists only if that path is re-enabled.

To re-enable it: uncomment the `schedule:` block in `weglot-sync.yml` and comment out the one in `content-pipeline.yml`.

**Lesson (2026-10-06):** the sync was disabled with two rows still in the CSV. Both were imported by hand, but with the sync off nothing could mark them done, and the daily report filed a new issue every day — 172 open, none closed. `weglot-daily-report.yml` now runs `tools/weglot/pending_report.py`, which ignores rows Weglot already excludes and keeps one self-closing issue.

## Key Behaviors

- **Only processes published posts** — archived posts and scheduled posts (`lastPublished=null`) are skipped
- **Handles draft edits** — `isDraft=True` + `lastPublished` set = still live
- **No duplicates** — compares with Weglot's live list on every run
- **Never loses per-language settings** — the full list is re-read and checked after every POST
- **Sitemap independent** — sitemap filtering uses `data/weglot-sitemap-exclusions.json`

## Files

| File | Purpose |
|---|---|
| `tools/weglot/api_sync.py` | The sync (Content Pipeline Step 1) |
| `tools/weglot/test_api_sync.py` | Tests for it |
| `tools/weglot/pending_report.py` | Daily report: one issue for rows still waiting for a manual import |
| `tools/weglot/test_pending_report.py` | Tests for it |
| `tools/weglot/sync_exclusions.py` | Legacy CSV sync (disabled, rollback path) |
| `data/weglot-exclusions.json` | Tracked state |
| `data/weglot-sitemap-exclusions.json` | Sitemap filter data |
| `data/weglot.csv` | Legacy CSV — only exists if the CSV path is re-enabled |

## GitHub Actions Secrets

| Secret | Purpose |
|---|---|
| `WEBFLOW_API_TOKEN` | Read-only CMS access |
| `WEGLOT_API_KEY` | Weglot public key — read exclusions (passed as `WEGLOT_PUBLIC_KEY`) |
| `WEGLOT_PRIVATE_KEY` | Weglot private key — write exclusions |
