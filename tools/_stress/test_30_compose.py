"""(d) The modular-composition proof — a future orchestrator wires the four shared
surfaces together by IMPORTING each, nothing rebuilt (the user's headline requirement).

One end-to-end dry-run pipeline, asserting the data hand-off at every seam:

    core.gemini.dry_run_submit        # the shared client plans a batch (no send)
        │  copy text
        ▼
    copywriter.improve_copy(dry_run)  # locale-native improve → CopyResult.text
        │  result.text
        ▼
    translator.translate_batch(dry)   # EN-source propagation → Translation.target
        │  rendered HTML
        ▼
    core.webflow.CmsClient(dry).patch_fields   # staged PATCH payload (no send)

Zero live calls, zero spend — every stage is dry-run and the keys are unset.
"""
import pytest

pytestmark = pytest.mark.stress

_SOURCE = "Study English in Vancouver. Classes stay small. Your teacher learns your name fast."


def test_gemini_copywriter_translator_webflow_handoff(tmp_path):
    from tools.core.gemini import client as gemini
    from tools.copywriter import CopyRequest, improve_copy
    from tools.translator import TranslationUnit, translate_batch
    from tools.translator.glossary import load_glossary
    from tools.core.content.structure import summary_markdown_to_html
    from tools.core.webflow.cms import CmsClient

    # 1. Shared Gemini client composes a batch request (planned, never sent).
    handle = gemini.dry_run_submit(
        [gemini.BatchRequest(custom_id="seed", system_blocks=[{"text": "x"}], user_message=_SOURCE)],
        artifact_dir=tmp_path,
    )
    assert handle.dry_run is True and handle.request_count == 1

    # 2. Copywriter improves the copy in-locale (dry-run => passthrough we can assert on).
    result = improve_copy(CopyRequest(brief="tighten", locale="en", existing_copy=_SOURCE), dry_run=True)
    assert result.text == _SOURCE        # hand-off: the copy text flows out of the copywriter

    # 3. Translator takes the improved copy as a neutral unit and propagates it (dry-run).
    trs = translate_batch(
        [TranslationUnit(id="u1", text=result.text)], "de", load_glossary(), dry_run=True
    )
    assert trs[0].source == result.text  # hand-off: copywriter output IS the translator input
    assert trs[0].target == result.text  # dry-run passthrough

    # 4. Shared Webflow client stages the rendered copy as a PATCH (no live write).
    html = summary_markdown_to_html(result.text)
    wr = CmsClient(dry_run=True).patch_fields("collection-1", "item-1", {"summary": html})
    assert wr.dry_run is True and wr.success is True
    assert _SOURCE.split(".")[0] in wr.payload["fieldData"]["summary"]  # the copy reached the write seam


def test_orchestrator_imports_only_no_rebuild():
    """Modularity contract: the four surfaces are importable as independent libraries —
    an orchestrator composes them with imports alone (requirement #8)."""
    from tools.core.gemini.client import submit_batch, generate_sync, dry_run_submit  # noqa: F401
    from tools.core.webflow.cms import CmsClient  # noqa: F401
    from tools.copywriter import improve_copy, improve_copy_batch  # noqa: F401
    from tools.translator import translate_batch  # noqa: F401
    # None of these pulled a consumer tool into core (enforced separately by lint-imports).
