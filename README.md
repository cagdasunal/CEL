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
Scheduled every 15 minutes (GitHub often delays scheduled runs — gaps of a few hours are normal). Step 1 runs `tools/weglot/api_sync.py`: every newly published blog post gets its Weglot translation exclusions created **through the Weglot API** — no manual import. It then regenerates the sitemap and `llms.txt` when something changed, and regenerates the dashboard pages under `cel.englishcollege.com/admin/`. See `tools/weglot/README.md`.

### Sitemap & LLMs.txt (`update-sitemap-llms.yml`)
Runs every 6 hours. Generates `sitemap.xml` from 9 sitemaps (EN + 8 regional), filters ghost translations and category pages, then generates `llms.txt` from the filtered sitemap.

## Manual Trigger

Go to **Actions** tab > select workflow > **Run workflow**.
