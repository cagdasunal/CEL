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
