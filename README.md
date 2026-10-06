# englishcollege

Public repository hosting auto-generated SEO files and automation for [englishcollege.com](https://www.englishcollege.com).

## Files

| File | Description | Updated |
|------|-------------|---------|
| `docs/sitemap.xml` | Filtered multilingual sitemap (EN + 8 languages, ~696 URLs) | Every 6 hours + on new posts |
| `docs/llms.txt` | LLM-friendly context extracted from sitemap | Every 6 hours |

## Public URLs

- **Sitemap**: `https://cel.englishcollege.com/sitemap.xml`
- **LLMs.txt**: `https://cel.englishcollege.com/llms.txt`

(`sitemap.englishcollege.com` no longer exists — its DNS was removed on 2026-04-22.)

## Automation

### Content Pipeline (`content-pipeline.yml`)
Scheduled every 15 minutes (GitHub often delays scheduled runs — gaps of a few hours are normal). Step 1 runs `tools/weglot/api_sync.py`: every newly published blog post gets its Weglot translation exclusions created **through the Weglot API** — no manual import. It then regenerates the sitemap and `llms.txt` when something changed, checks the Weglot CSV import status, and regenerates the dashboard pages under `cel.englishcollege.com/admin/`. See `tools/weglot/README.md`.

### Sitemap & LLMs.txt (`update-sitemap-llms.yml`)
Runs every 6 hours. Generates `sitemap.xml` from 9 sitemaps (EN + 8 regional), filters ghost translations and category pages, then generates `llms.txt` from the filtered sitemap.

### Weglot Daily Report (`weglot-daily-report.yml`)
Runs daily (06:07 UTC). Opens **one** GitHub issue only when exclusions are waiting for a manual Weglot import (rows in `data/weglot.csv` that Weglot does not already have) and closes it when none are left. Normally silent. It also writes the daily `.weglot-last-check` stamp the dashboard reads. Logic: `tools/weglot/pending_report.py`.

### Weglot Exclusion Sync (`weglot-sync.yml`) — disabled
The legacy CSV path, disabled on 2026-04-22 and replaced by the API sync above. Manual run only.

## Manual Trigger

Go to **Actions** tab > select workflow > **Run workflow**.
