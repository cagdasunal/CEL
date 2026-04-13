# englishcollege

Public repository hosting auto-generated SEO files for [englishcollege.com](https://www.englishcollege.com).

## Files

| File | Description | Updated |
|------|-------------|---------|
| `sitemap.xml` | Filtered multilingual sitemap (EN + 8 languages, ~696 URLs) | Every 6 hours + on new posts |
| `llms.txt` | LLM-friendly context extracted from sitemap | Every 6 hours |

## Public URLs

- **Sitemap**: `https://sitemap.englishcollege.com/sitemap.xml`
- **LLMs.txt**: `https://sitemap.englishcollege.com/llms.txt`

## Automation

### Sitemap & LLMs.txt (`update-sitemap-llms.yml`)
Runs every 6 hours. Generates `sitemap.xml` from 9 sitemaps (EN + 8 regional), filters ghost translations and category pages, then generates `llms.txt` from the filtered sitemap.

### Weglot Exclusion Sync (`weglot-sync.yml`)
Runs every 15 minutes. Detects new published blog posts in Webflow CMS, pushes translation exclusion rules to Weglot API, and regenerates the sitemap. See `tools/weglot/README.md` for details.

## Manual Trigger

Go to **Actions** tab > select workflow > **Run workflow**.
