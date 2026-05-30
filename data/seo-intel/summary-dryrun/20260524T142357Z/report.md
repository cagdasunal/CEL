# Summary script — run report

- Started: `2026-05-24T14:23:57.089730+00:00`
- Subcommand: `translate`
- Dry-run: `False`
- Filters: `{"collection": "courses", "page": null, "locale": "de", "limit": 2}`

## Phase: translate

```json
{
  "target_locales": [
    "de"
  ],
  "per_locale": {
    "de": {
      "dry_run": false,
      "engine": "translator",
      "request_count": 2,
      "succeeded": 2,
      "failed": 0,
      "cost_estimate_usd": 0.05,
      "csv_path": "/Users/cagdas/Desktop/dev/englishcollege/docs/admin/weglot-imports/de.csv",
      "rows_appended": 14,
      "duplicates_skipped": 0,
      "existing_rows": 674,
      "words": 1318,
      "internal_links": 15
    }
  },
  "manifest_path": "data/seo-intel/summary-dryrun/20260521T224800Z/en-summaries.json",
  "translation_status_path": "/Users/cagdas/Desktop/dev/englishcollege/docs/admin/weglot-imports/translation-status.json",
  "warnings": [
    "locale de tr-de-gen-1-englishcollege.com/los-angeles-ca/language-courses: QA flags ['dnt_term_dropped:California']"
  ]
}
```
