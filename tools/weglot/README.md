# Weglot Exclusion Sync

Automated system that detects new blog posts on englishcollege.com and manages Weglot translation exclusions.

## Problem

When a blog post is published in a specific language (e.g., Italian), Weglot auto-creates translated versions for all 8 target languages. Posts that are already in their original language should NOT be translated. Without exclusion rules, this creates duplicate/ghost pages in the sitemap — terrible for SEO.

## How It Works

1. **GitHub Actions** runs every 15 minutes (`.github/workflows/weglot-sync.yml`)
2. **Fetches all published blog posts** from Webflow CMS API (collection `667453c576e8d35c454ccaae`)
3. **Reads current Weglot exclusions** via `GET /projects/settings?api_key=...`
4. **Computes the delta** — posts that are published but not yet excluded
5. **Generates outputs**:
   - `data/weglot-import.csv` — CSV for manual Weglot dashboard import
   - `data/weglot-exclusions.json` — local state tracking
   - `data/weglot-sitemap-exclusions.json` — consumed by the sitemap generator
6. **Regenerates** `sitemap.xml` and `llms.txt` (independent of CSV import)
7. **Commits and pushes** changes to the repo

## Exclusion Logic

```
ALL_TRANSLATED = {ar, de, es, fr, it, ja, ko, pt}   # 8 languages (not English base)

If post language == "en":
    exclude_from = ALL_TRANSLATED                     # all 8
Else:
    exclude_from = ALL_TRANSLATED - {post_language}   # 7 (keep the post's own language)
```

English is Weglot's base language and can never be excluded.

## Key Behaviors

- **Only processes published posts** — scheduled posts (`lastPublished=null`) are skipped
- **No duplicates** — checks Weglot's live exclusion list on every run
- **Sitemap is fixed immediately** — doesn't wait for CSV import into Weglot
- **Attempts Weglot API write** — if Weglot grants write access later, it works automatically

## Files

| File | Purpose |
|---|---|
| `tools/weglot/sync_exclusions.py` | Core sync script |
| `tools/weglot/test_sync_exclusions.py` | Tests (28 tests) |
| `data/weglot-exclusions.json` | Tracked exclusion state |
| `data/weglot-import.csv` | CSV for Weglot dashboard import |
| `data/weglot-sitemap-exclusions.json` | Sitemap filter data |
| `.github/workflows/weglot-sync.yml` | GitHub Actions workflow |

## Usage

```bash
# Dry run — show what would change
WEBFLOW_API_TOKEN=... WEGLOT_API_KEY=... python3 tools/weglot/sync_exclusions.py --dry-run

# Full sync
WEBFLOW_API_TOKEN=... WEGLOT_API_KEY=... python3 tools/weglot/sync_exclusions.py

# Check status
python3 tools/weglot/sync_exclusions.py --status
```

## GitHub Actions Secrets

| Secret | Purpose |
|---|---|
| `WEBFLOW_API_TOKEN` | Read-only CMS access to fetch blog posts |
| `WEGLOT_API_KEY` | Read Weglot settings (write if granted later) |

## Weglot API Status

- `GET /projects/settings` — works (reads all exclusions)
- `POST /projects/settings` — returns 401 "insufficient rights" with `wg_` key
- Weglot has been contacted about write API access (April 2026)
