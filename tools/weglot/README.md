# Weglot Exclusion Sync

Automated system that detects new blog posts on englishcollege.com and pushes translation exclusions directly to Weglot via API.

## Problem

When a blog post is published in a specific language (e.g., Italian), Weglot auto-creates translated versions for all 8 target languages. Posts that are already in their original language should NOT be translated. Without exclusion rules, this creates duplicate/ghost pages in the sitemap — terrible for SEO.

## How It Works

1. **GitHub Actions** runs every 15 minutes (`.github/workflows/weglot-sync.yml`)
2. **Fetches all published blog posts** from Webflow CMS API (collection `667453c576e8d35c454ccaae`)
3. **Reads current Weglot exclusions** via `GET /projects/settings`
4. **Computes the delta** — posts that are published but not yet excluded
5. **Pushes new exclusions** directly to Weglot via `POST /projects/settings` (private key)
6. **Regenerates** `sitemap.xml` with language-aware filtering
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

- **Fully automated** — pushes exclusions directly to Weglot API (private key)
- **Only processes published posts** — scheduled posts (`lastPublished=null`) are skipped
- **Handles draft edits** — `isDraft=True` + `lastPublished` set = published with unsaved edits (still live)
- **No duplicates** — checks Weglot's live exclusion list on every run via GET before POST
- **Safe writes** — GET current state → append new → POST full array (never overwrites other settings)
- **Sitemap filtering** — removes ghost translated URLs from regional sitemaps independently

## Files

| File | Purpose |
|---|---|
| `tools/weglot/sync_exclusions.py` | Core sync script |
| `tools/weglot/test_sync_exclusions.py` | Tests (29 tests) |
| `data/weglot-exclusions.json` | Tracked exclusion state |
| `data/weglot-sitemap-exclusions.json` | Sitemap filter data |
| `.github/workflows/weglot-sync.yml` | GitHub Actions workflow (every 15 min) |

## Usage

```bash
# Dry run — show what would change
WEBFLOW_API_TOKEN=... WEGLOT_API_KEY=... WEGLOT_PRIVATE_KEY=... python3 tools/weglot/sync_exclusions.py --dry-run

# Full sync
WEBFLOW_API_TOKEN=... WEGLOT_API_KEY=... WEGLOT_PRIVATE_KEY=... python3 tools/weglot/sync_exclusions.py

# Check status
python3 tools/weglot/sync_exclusions.py --status
```

## GitHub Actions Secrets

| Secret | Purpose |
|---|---|
| `WEBFLOW_API_TOKEN` | Read-only CMS access to fetch blog posts |
| `WEGLOT_API_KEY` | Public key — read Weglot settings |
| `WEGLOT_PRIVATE_KEY` | Private key — write exclusions to Weglot |

## Weglot API

- `GET /projects/settings` — reads all exclusions (public key)
- `POST /projects/settings` — writes exclusions (private key, safe GET→append→POST pattern)
- Private key provided by Weglot support (April 2026)
