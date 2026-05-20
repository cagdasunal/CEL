"""translate_batch — the engine entry point (tracker-092 Phase 3).

Pipeline: TM lookup (skip hits) → build one Gemini request per miss (reusing
`tools.summary.batch_runner`, so all the M-11/M-12/Phase-2.3 hardening — truncation
guard, max_tokens, backoff — comes for free) → glossary post-edit → translation
QA → TM write → return Translations in input order.

The Gemini prompt is built by a `request_builder(unit, locale, glossary_slice)`
callback. The default builder is a generic translator prompt; the summary caller
passes its own builder to reproduce the existing summary-translation prompt
(behaviour + CSV parity). The engine never emits CSV — callers do.
"""
from __future__ import annotations

from typing import Callable, Optional

from tools.translation_engine.glossary import Glossary, GlossaryTerm
from tools.translation_engine.qa import check_translation
from tools.translation_engine.tm import TranslationMemory
from tools.translation_engine.units import Translation, TranslationUnit

_LOCALE_NAMES = {
    "de": "German", "fr": "French", "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "ko": "Korean", "ja": "Japanese", "ar": "Arabic",
    "en": "English",
}

# (system_blocks, user_message)
RequestBuilder = Callable[[TranslationUnit, str, str], tuple[list[dict], str]]


def _default_request_builder(
    unit: TranslationUnit, locale: str, glossary_slice: str
) -> tuple[list[dict], str]:
    """Generic professional-translation prompt used by the meta-tags caller."""
    lang = _LOCALE_NAMES.get(locale, locale)
    system = (
        f"You are a professional translator. Translate the user's text into {lang} "
        f"({locale}). Preserve every number, price, URL, and placeholder exactly. "
        f"Match the source register and length. Return ONLY the translated text — "
        f"no preamble, no quotes, no notes."
    )
    if glossary_slice:
        system = f"{system}\n\n{glossary_slice}"
    system_blocks = [{"type": "text", "text": system}]
    user_message = unit.text if not unit.context else f"{unit.context}\n\n{unit.text}"
    return system_blocks, user_message


def translate_batch(
    units: list[TranslationUnit],
    target_locale: str,
    glossary: Glossary,
    *,
    tone: Optional[str] = None,
    tm: Optional[TranslationMemory] = None,
    dry_run: bool = False,
    request_builder: Optional[RequestBuilder] = None,
    api_key_env: str = "GEMINI_API_KEY",
) -> list[Translation]:
    """Translate `units` into `target_locale`. Returns Translations in input order.

    - `tm`: optional translation memory. Hits are returned without an API call;
      successful new translations are written back (live mode only).
    - `dry_run`: no Gemini call — returns passthrough stubs (qa_flags=["dry_run"])
      so callers can exercise their wiring without the network.
    - `request_builder`: override the Gemini prompt (summary caller uses this for
      parity); defaults to a generic translator prompt.
    """
    from tools.summary import batch_runner

    builder = request_builder or _default_request_builder
    tone = tone or ""
    by_id: dict[str, Translation] = {}

    # 1. TM lookup (live only — dry-run never reads/writes the memory).
    misses: list[TranslationUnit] = []
    for u in units:
        if tm is not None and not dry_run:
            cached = tm.get(u.text, target_locale, glossary.version, tone)
            if cached is not None:
                by_id[u.id] = Translation(
                    id=u.id, source=u.text, target=cached,
                    target_locale=target_locale, from_tm=True, ok=True,
                )
                continue
        misses.append(u)

    # 2. Build one Gemini request per miss.
    requests = []
    for u in misses:
        gslice = glossary.prompt_slice(glossary.match(u.text), target_locale)
        system_blocks, user_message = builder(u, target_locale, gslice)
        requests.append(batch_runner.BatchRequest(
            custom_id=u.id,
            system_blocks=system_blocks,
            user_message=user_message,
            enable_thinking=False,  # translation is low-reasoning
        ))

    if not requests:
        return [by_id[u.id] for u in units]

    # 3. Dry-run: passthrough stubs, no API call, no QA/glossary/TM.
    if dry_run:
        for u in misses:
            by_id[u.id] = Translation(
                id=u.id, source=u.text, target=u.text,
                target_locale=target_locale, from_tm=False,
                qa_flags=["dry_run"], ok=True,
            )
        return [by_id[u.id] for u in units]

    # 4. Submit + poll (reuses batch_runner's hardened client).
    handle = batch_runner.submit_batch(requests, api_key_env=api_key_env)
    batch_results = batch_runner.wait_for_batch(handle, api_key_env=api_key_env)
    got = {r.custom_id: r for r in batch_results}

    # 5. Glossary post-edit + QA + TM write.
    for u in misses:
        br = got.get(u.id)
        if br is None:
            by_id[u.id] = Translation(
                id=u.id, source=u.text, target="", target_locale=target_locale,
                ok=False, qa_flags=["no_result"],
            )
            continue
        if not br.succeeded:
            by_id[u.id] = Translation(
                id=u.id, source=u.text, target=br.content or "", target_locale=target_locale,
                ok=False, qa_flags=[f"batch_failed:{(br.error or '')[:80]}"],
            )
            continue
        target, gflags = glossary.enforce(u.text, br.content, target_locale)
        qa_ok, qa_flags = check_translation(u.text, target, target_locale)
        ok = qa_ok and bool(target.strip())
        by_id[u.id] = Translation(
            id=u.id, source=u.text, target=target, target_locale=target_locale,
            from_tm=False, qa_flags=gflags + qa_flags, ok=ok,
        )
        if ok and tm is not None:
            tm.put(u.text, target_locale, glossary.version, target, tone)

    if tm is not None:
        tm.save()

    return [by_id[u.id] for u in units]
