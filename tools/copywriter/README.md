# `tools/copywriter` — multilingual, brief-driven copy improvement

Improves landing-page and blog copy on **Gemini 3.1 Pro**, across all 9 CEL locales
(en/de/fr/es/it/pt/ko/ja/ar). **Locale-native**: a Korean page is improved *in Korean* —
it never goes through the translator. The output must read as **genuinely human** — no em
dashes, no AI words/phrases/templates — enforced in BOTH the prompt and a QA gate. Writes
to Webflow are **brief-driven, never automatic**, preview + backup + approval first.

Built entirely on the shared leaf layer: `tools.core.gemini` (generate), `tools.core.web`
(fetch a page's current copy), `tools.core.content` (Markdown ⇄ RichText), `tools.core.seo`
(internal-link inventory), `tools.core.webflow` (staged write); optional EN→multi-locale
propagation reuses `tools.translator`.

## Library API

```python
from tools.copywriter import CopyRequest, improve_copy, improve_copy_batch

res = improve_copy(
    CopyRequest(brief="warmer hero, keep the DLI number", locale="ko",
                existing_copy=current_copy, must_keep_facts=("DLI #O19283785432",)),
    dry_run=True,            # default-safe: no API call, runs QA on the input
)
# res.text / res.before / res.ok / res.qa_flags
```

`improve_copy(req, *, dry_run=False, api_key_env="GEMINI_API_KEY", link_candidates=())`.
`dry_run=True` returns a passthrough (no spend) so wiring + the QA gate can be exercised
offline. (Brand/do-not-translate terms are preserved via `req.must_keep_facts`, not a
glossary; generation is always synchronous — the copywriter is interactive, low-volume.) The live path generates → runs QA → **one** auto-retry with
a tightened prompt on a QA fail → returns the result (a failing draft is surfaced, never
silently written).

## CLI

```bash
python3 -m tools.copywriter plan    --brief brief.json [--locale ko]   # QA current copy; no API
python3 -m tools.copywriter improve --brief brief.json [--locale ko]   # dry-run by default
python3 -m tools.copywriter improve --brief brief.json --no-dry-run    # calls Gemini
python3 -m tools.copywriter improve --brief brief.json --no-dry-run --write   # + staged Webflow write
```

A brief is a JSON object; only `brief` is required (see `brief.py::load_brief`). A `target`
selects what to fetch/write: `{"kind":"cms_item","collection":"blog","cms_item_id":"…","field_slug":"…"}`
or `{"kind":"static_page","url":"https://www.englishcollege.com/…"}`. Every run writes a
`preview.md` + `result.json`; `--write` adds a `backup.json` + `audit.json`.

## The human-voice / anti-AI QA (`qa.py`)

The first **enforced** banlist gate (summary's `qa.py` was structural-only; the banlists
were prompt-only). Pure stdlib, runs for every locale:

- **Universal hard fails** — em dash, emoji, AI-template openers ("In today's…", "It's not
  just X, it's Y", "Not only … but also").
- **Universal flags** — English hype/transition/hedge crutches (delve, leverage, robust,
  seamless, elevate, unlock, furthermore, "it's worth noting", …).
- **Per-locale banlist** — parsed live from `tools/summary/prompts/locales/<locale>.md`
  `## AI-tell banlist` (e.g. Korean translationese: 다양한, 살펴보겠습니다, 또한, 매우 …).
- **Fact preservation** — every `must_keep_fact` must survive (a miss is a hard fail).

Rule: any hard fail ⇒ fail; **≥ 3 flags** ⇒ fail. `COPYWRITER_PROMPT_VERSION` pins the
prompt/QA contract for eval regression.

## Multilingual flow

- `improve --locale <X>` rewrites natively in any locale and **never** translates.
- EN-source → other locales is a **separate, opt-in** step on the approved English via
  `tools.translator.translate_batch` (same-locale link preservation via the `url_map` /
  `find_equivalent_or_fallback` helpers). Not wired into this CLI yet — by design.

## Safety

Dry-run is the default everywhere. CMS writes are staged (`core.webflow.CmsClient`),
backed up, audited, and gated behind explicit approval. Static primary-locale pages can't
be written by the Data API, so the writer emits a reviewed before/after doc under
`docs/admin/copywriter/<slug>.copy.md` for assisted Designer-MCP deploy / manual paste.
