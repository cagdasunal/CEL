# Weglot Exclusion Sync

Automated system that detects new blog posts on englishcollege.com and generates a CSV for Weglot translation exclusion import.

## Problem

When a blog post is published in a specific language (e.g., Italian), Weglot auto-creates translated versions for all 8 target languages. Posts that are already in their original language should NOT be translated. Without exclusion rules, this creates duplicate/ghost pages — terrible for SEO.

## How It Works

1. **GitHub Actions** runs every 15 minutes (`.github/workflows/weglot-sync.yml`)
2. **Fetches all published blog posts** from Webflow CMS API
3. **Reads current Weglot exclusions** via `GET /projects/settings` (public key)
4. **Computes the delta** — posts that are published but not yet excluded
5. **Generates `weglot.csv`** for manual import into the Weglot dashboard
6. **Regenerates `sitemap.xml`** with language-aware filtering (independent of CSV import)
7. **Commits and pushes** — CSV is downloadable at `https://sitemap.englishcollege.com/weglot.csv`

## Workflow

1. New blog post published on Webflow
2. Within 15 min, GitHub Actions detects it
3. CSV appears at `https://sitemap.englishcollege.com/weglot.csv`
4. Download and import into Weglot dashboard (Translation Exclusions → Import)
5. Next sync run auto-confirms the import (updates state from `csv` → `weglot_existing`)
6. CSV clears — no duplicates

## Weglot API Limitation

The Weglot `POST /projects/settings` API silently strips the `excluded_languages` field. Per-language exclusions can ONLY be set via the dashboard (manual or CSV import). The API is used read-only for checking current exclusions.

**Status (2026-04-14):** Reported to Weglot support (Fanny). Weglot devs reproduced the bug on a test project, identified the root cause, and filed an internal issue to fix in a future release. No ETA yet. Once shipped, `sync_exclusions.py` can switch from CSV export to direct `POST /projects/settings` with minimal changes (the per-language computation in `compute_excluded_languages()` is already correct, only the output step needs to change).

### What we know about the bug (shared with Weglot support, Apr 14)

1. **Blast radius:** POST does not just drop `excluded_languages` on the new entry. It wipes the field on **every entry in the array**, including the 290+ existing ones that already had correct per-language values. A single API call destroyed our per-language setup and had to be restored from a CSV export.
2. **Not a permissions issue:** both the public `wg_` key and the private API key produce identical behaviour, so the bug is not in the auth/ACL layer.
3. **Other fields are fine:** `type`, `value`, `language_button_displayed`, and `exclusion_behavior` all round-trip through POST correctly. Only `excluded_languages` gets dropped.
4. **CSV import works:** the same entries with the same language codes persist correctly when imported via the dashboard, so the storage layer is fine. The bug is isolated to the API write path.
5. **Our guess:** a DTO/struct on the write path that does not declare `excluded_languages`, so the deserializer drops it silently and the re-serialized array loses the field on every entry.

### Destructive-write warning

Until the bug is fixed, **do not attempt `POST /projects/settings` with an `excluded_paths` array** even as a test. A single call will wipe `excluded_languages` on every existing entry. If you must experiment, do it against a fresh test project with nothing valuable in it.

## Key Behaviors

- **Only processes published posts** — scheduled posts (`lastPublished=null`) are skipped
- **Handles draft edits** — `isDraft=True` + `lastPublished` set = still live
- **No duplicates** — checks Weglot's live list on every run
- **Auto-confirms imports** — after you import the CSV, next run detects the entries in Weglot and clears them from CSV
- **Sitemap independent** — sitemap filtering works immediately, doesn't wait for CSV import

## Files

| File | Purpose |
|---|---|
| `tools/weglot/sync_exclusions.py` | Core sync script |
| `tools/weglot/test_sync_exclusions.py` | Tests |
| `data/weglot-exclusions.json` | Tracked state |
| `data/weglot.csv` | CSV for Weglot import |
| `data/weglot-sitemap-exclusions.json` | Sitemap filter data |
| `weglot.csv` | Root copy for `sitemap.englishcollege.com/weglot.csv` |

## GitHub Actions Secrets

| Secret | Purpose |
|---|---|
| `WEBFLOW_API_TOKEN` | Read-only CMS access |
| `WEGLOT_API_KEY` | Read Weglot exclusions (public key) |
