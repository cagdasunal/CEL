# `tools/core` — shared services (the leaf layer)

Canonical, single-copy infrastructure that every CEL tool imports. **`tools.core` is a
leaf**: any tool may import it; it must never import a consumer tool back. The rule is
enforced mechanically by `import-linter` (`.importlinter` → `lint-imports`), so a stray
back-import fails CI, not a code review. See [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md).

## Packages

| Package | Module(s) | Public surface |
|---|---|---|
| `core.gemini` | `client`, `config` | Gemini 3.1 Pro Batch + sync client: `BatchRequest`, `submit_batch`, `generate_sync`, `wait_for_batch`, `dry_run_submit`, `cancel_batch`, `estimate_batch_cost_usd`, `plan_caches`; knobs in `config` (`MODEL_ID`, cache/token/cost constants, `DRYRUN_DIR`, `LAST_BATCH_FILE`). |
| `core.webflow` | `http`, `cms` | Webflow Data API: `http` = `resolve_token` + `request` (429/5xx + timeout backoff) + `paginate` + `WebflowApiError`/`NetworkError`; `cms.CmsClient` = generic staged `patch_fields`, `list_items`, `ensure_field`, dry-run default; `WriteResult`/`CmsItem`/`CollectionField`. |
| `core.web` | `page_fetcher` | `fetch_page(url) -> PageContent` (stdlib live-page fetch + extract). |
| `core.content` | `structure` | Markdown ⇄ Webflow RichText HTML (`summary_markdown_to_html`, `summary_html_to_markdown`, `parse_four_part`, …). |
| `core.seo` | `llms_parser` | `llms.txt` → `LlmsIndex` internal-link graph (`parse_llms_txt`, `find_equivalent`, `LlmsIndex.find_equivalent_or_fallback`). |

## Usage

```python
from tools.core.gemini import client as gemini
from tools.core.webflow.cms import CmsClient

handle = gemini.dry_run_submit([gemini.BatchRequest(
    custom_id="c1", system_blocks=[{"text": "…"}], user_message="…")])
CmsClient(dry_run=True).patch_fields(collection_id, item_id, {"slug": "<p>html</p>"})
```

## Back-compat shims

These modules were extracted from `tools/summary/` via strangler-fig. The old paths
(`tools.summary.batch_runner`, `.page_fetcher`, `.structure`, `.llms_parser`,
`.webflow_client`, and the moved `config` names) remain as **identity-preserving
re-export shims** — existing importers and `monkeypatch.setattr(<oldmod>, …)` keep
working. The stress harness pins this identity (`tools/_stress/test_10_imports.py`).

## Dry-run + no-spend

`core.gemini.dry_run_submit` writes the batch payload to disk and never calls the API;
`core.webflow.CmsClient(dry_run=True)` (the default) stages the PATCH and never sends it.
The stress harness deletes the API keys as a backstop so an accidental real call raises.
