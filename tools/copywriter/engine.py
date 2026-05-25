"""improve_copy — the copywriter engine.

Pipeline: build the Gemini request (Pro, thinking on => the low advisory budget the
shared client sets, default temperature) from the brief + current copy => generate via
the shared core.gemini client => anti-AI QA => one auto-retry with a tightened prompt on
a QA fail => CopyResult. `dry_run` returns a passthrough (no API call, no spend) so the
wiring + QA gate can be exercised offline. NEVER translates — that is a separate step.
"""
from __future__ import annotations

from typing import Iterable, Optional

from tools.copywriter import config, qa
from tools.copywriter.brief import CopyRequest, CopyResult
from tools.copywriter.prompt_builder import build_system_prompt, build_user_message

_RETRY_NUDGE = (
    "\n\n## REVISION REQUIRED\nThe previous draft tripped the anti-AI / banned-phrase "
    "gate ({flags}). Rewrite it: remove every banned word, phrase, template, and em "
    "dash; vary sentence length; keep it natural and human. Return only the improved copy."
)


def _strip_fences(text: str) -> str:
    """Drop a leading ```lang fence + trailing ``` if the model wrapped its output."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def improve_copy(
    req: CopyRequest,
    *,
    glossary=None,
    dry_run: bool = False,
    sync: bool = True,
    api_key_env: str = "GEMINI_API_KEY",
    link_candidates: Iterable[str] = (),
) -> CopyResult:
    """Improve `req`'s copy in `req.locale` (locale-native; never translates)."""
    before = req.existing_copy or ""
    system_blocks = build_system_prompt(req.locale)
    user_message = build_user_message(req, before, link_candidates)

    if dry_run:
        # No API call. Run QA on the CURRENT copy so the gate + wiring are exercised;
        # flags here describe the INPUT, not a generation.
        report = qa.copywriter_qa(before, req.locale, must_keep_facts=req.must_keep_facts)
        return CopyResult(
            text=before, locale=req.locale, ok=True, before=before,
            qa_flags=["dry_run", *report.flags, *report.hard_fails],
        )

    from tools.core.gemini import client as gemini  # deferred: lazy SDK import

    def _generate(extra: str = "") -> tuple[str, int, int]:
        reqs = [gemini.BatchRequest(
            custom_id="copy-1", system_blocks=system_blocks,
            user_message=user_message + extra, enable_thinking=True, model=config.MODEL_ID,
        )]
        r = gemini.generate_sync(reqs, api_key_env=api_key_env)[0]
        if r.succeeded:
            return _strip_fences(r.content), int(r.input_tokens or 0), int(r.output_tokens or 0)
        return "", 0, 0

    text, in_tok, out_tok = _generate()
    report = qa.copywriter_qa(text, req.locale, must_keep_facts=req.must_keep_facts)
    if not report.ok and text:
        text2, in2, out2 = _generate(_RETRY_NUDGE.format(flags=report.summary()))
        if text2:
            report2 = qa.copywriter_qa(text2, req.locale, must_keep_facts=req.must_keep_facts)
            text, in_tok, out_tok, report = text2, in2, out2, report2

    return CopyResult(
        text=text, locale=req.locale, ok=report.ok, before=before,
        qa_flags=[*report.flags, *report.hard_fails], input_tokens=in_tok, output_tokens=out_tok,
    )


def improve_copy_batch(reqs: list[CopyRequest], **kw) -> list[CopyResult]:
    """Improve a list of requests (sequential). Same kwargs as improve_copy."""
    return [improve_copy(r, **kw) for r in reqs]
