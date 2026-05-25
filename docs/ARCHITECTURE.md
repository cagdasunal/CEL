# CEL Tools — Architecture

> Living document. Seeded in **Plan 0** of the modular refactor; filled in as
> `tools/core/` services land (gemini → webflow → web/content/seo) and the
> `copywriter` tool is built.

## Layout

```
tools/
├── core/          # SHARED SERVICES (leaf — import these; never imports a consumer back)
│   ├── gemini/    # Gemini 3.1 Pro client (Plan A): BatchRequest, submit_batch, generate_sync, wait_for_batch, cost/cache
│   ├── webflow/   # Webflow Data API (Plan B): http (auth/retry/pagination) + cms (generic field PATCH, create/bulk, dry-run)
│   ├── web/       # page_fetcher (Plan B2): live-page fetch -> PageContent
│   ├── content/   # structure (Plan B2): Markdown <-> Webflow RichText HTML
│   └── seo/       # llms_parser (Plan B2): llms.txt -> LlmsIndex internal-link graph
├── summary/       # SEO summary generation (consumes core)
├── translator/    # reusable LLM translation (consumes core.gemini)
├── copywriter/    # multilingual, brief-driven copy improvement (Plan C; consumes core + translator)
├── offers/        # Webflow offers automation
├── weglot/        # Weglot exclusion sync + status
├── blog_images/   # blog image optimization
└── arabic_rtl/    # Arabic RTL work (an early consumer of core.web/content/seo)
```

## The one rule: dependency direction

`tools.core.*` is a **leaf**. Any tool may import from `tools.core`; `tools.core`
must **never** import a consumer tool (`summary`, `translator`, `copywriter`,
`offers`, `weglot`, `blog_images`, `arabic_rtl`, …). Enforced mechanically by
`import-linter` (`.importlinter`, run `lint-imports`) — architecture as a test,
not a comment. A future orchestrator composes `core.gemini` + `copywriter` +
`translator` + `core.webflow` by importing each; nothing is rebuilt.

## Composition example (the modular end state)

A future orchestrator composes the shared surfaces by **importing each** — nothing is
rebuilt. Every call below is dry-run safe (no spend); drop `dry_run=True` and supply the
keys to go live. This exact hand-off is proven by `tools/_stress/test_30_compose.py`.

```python
from tools.copywriter import CopyRequest, improve_copy
from tools.translator import TranslationUnit, translate_batch
from tools.translator.glossary import load_glossary
from tools.core.content.structure import summary_markdown_to_html
from tools.core.webflow.cms import CmsClient

# 1. Improve the Korean hero IN Korean (locale-native — never translated).
res = improve_copy(
    CopyRequest(brief="warmer hero", locale="ko", existing_copy=current_copy),
    dry_run=True,
)

# 2. (optional) Propagate EN-source copy to other locales via the translator.
de = translate_batch(
    [TranslationUnit(id="hero", text=res.text)], "de", load_glossary(), dry_run=True
)

# 3. Stage the rewrite back to Webflow through the shared client (dry-run default).
html = summary_markdown_to_html(res.text)
CmsClient(dry_run=True).patch_fields(collection_id, item_id, {"hero": html})
```

## Adding a consumer tool

1. `mkdir tools/<tool>` (no `tools/__init__.py` — `tools/` is a namespace package).
2. Import shared infra from `tools.core.*` (and `tools.translator` for multilingual).
   **Never** make `tools.core` import your tool back.
3. If you add a NEW leaf under `tools/core/`, list its package in the `source_modules`
   of the forbidden contract in `.importlinter`, then run `lint-imports`.
4. Put tests in `tools/<tool>/tests/`; the repo-root `pyproject.toml` `pythonpath = ["."]`
   makes `import tools.<tool>` resolve (add a `tests/conftest.py` sys.path shim only if
   you run the file outside the configured root).
5. If the tool participates in the orchestrator, add a dry-run check to
   `tools/_stress/test_20_dryrun.py` and a hand-off assertion to `test_30_compose.py`.

## Extraction pattern (strangler-fig + shims)

Shared modules are extracted from `tools/summary/` by MOVING the body into
`tools/core/...` and leaving an identity-preserving **re-export shim** at the old
path (`from tools.core.<pkg>.<mod> import <every public + tested-private name>`),
so existing importers and `monkeypatch.setattr(<oldmod>, ...)` keep working
unchanged. Consumer imports are mostly deferred (inside functions), so a running
process is unaffected by a file move; the next call resolves the shim.

## Testing

- Env: a venv with `requirements.txt` installed (CI uses Python 3.12; local dev
  may use 3.13). `pyproject.toml [tool.pytest.ini_options]` sets `pythonpath`,
  `testpaths`, and the `stress`/`eval` markers.
- `pytest tools/ -q` — full suite. `pytest -m "not stress"` — legacy only.
  `pytest -m stress` — the deterministic mocked cross-tool harness (Plan D).
- `lint-imports` — enforce the dependency-direction contract.

## Global execution protocol (for the modular refactor)

Each plan ships as one branch + commit with its own green gate + revert:

1. **Branch** `refactor/<plan-id>`; one plan per commit/PR.
2. **Pre-flight** (module moves — Plans A, B, B2): confirm no summary batch
   in-flight (`data/seo-intel/summary-last-batch.json` `submitted_at` not < 24h);
   for **A and B**, confirm the translator is idle. **B2 is translator-independent.**
3. **Gate** after every change: `pytest tools/ -q` (no NEW failures vs baseline)
   + an import smoke (`python -c "import tools.summary.cli, tools.translator, ..."`)
   + `lint-imports`.
4. **Merge** only on green; **rollback** = `git revert` the plan commit.
5. **No live API/Webflow calls, no spend** during a build — dry-run + mocks only.
