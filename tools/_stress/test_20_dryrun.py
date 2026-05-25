"""(c) Dry-run each tool — exercise every public entry with NO live call, NO spend.

The autouse `_no_spend` fixture (conftest) has already deleted the API keys, so any
accidental real Gemini/Webflow call would raise on token resolution. Each test here
drives a tool's dry-run path and asserts the no-call contract held (a stub result, a
staged-not-sent payload, an on-disk artifact) — never the network.
"""
import json

import pytest

pytestmark = pytest.mark.stress

_CLEAN = "Study English in Vancouver. Classes stay small. Your teacher learns your name by week one."


def test_copywriter_improve_copy_dry_run_is_passthrough():
    from tools.copywriter import CopyRequest, improve_copy
    r = improve_copy(CopyRequest(brief="warmer", locale="en", existing_copy=_CLEAN), dry_run=True)
    assert r.text == _CLEAN              # dry-run never mutates: out == in
    assert r.before == _CLEAN
    assert "dry_run" in r.qa_flags       # the gate ran on the input
    assert r.ok is True


def test_translator_translate_batch_dry_run_is_passthrough():
    from tools.translator import TranslationUnit, translate_batch
    from tools.translator.glossary import load_glossary
    out = translate_batch(
        [TranslationUnit(id="u1", text=_CLEAN)], "de", load_glossary(), dry_run=True
    )
    assert len(out) == 1
    assert out[0].target == _CLEAN       # passthrough stub, no API
    assert out[0].qa_flags == ["dry_run"]
    assert out[0].ok is True


def test_core_webflow_patch_is_staged_not_sent():
    from tools.core.webflow.cms import CmsClient, WriteResult
    wr = CmsClient(dry_run=True).patch_fields("col-1", "item-1", {"summary": "<p>hi</p>"})
    assert isinstance(wr, WriteResult)
    assert wr.dry_run is True and wr.success is True and wr.method == "PATCH"
    assert wr.payload["fieldData"]["summary"] == "<p>hi</p>"   # staged
    assert wr.response.get("_dry_run") is True                  # never sent


def test_core_gemini_dry_run_submit_writes_artifact(tmp_path):
    from tools.core.gemini import client as gemini
    reqs = [gemini.BatchRequest(custom_id="c1", system_blocks=[{"text": "sys"}], user_message="hi")]
    handle = gemini.dry_run_submit(reqs, artifact_dir=tmp_path)
    assert handle.dry_run is True and handle.request_count == 1
    assert handle.artifact_path.exists()
    line = json.loads(handle.artifact_path.read_text(encoding="utf-8").splitlines()[0])
    assert line["custom_id"] == "c1"     # the request was serialized, not sent


def test_copywriter_webflow_writer_dry_run_backs_up_and_audits(tmp_path):
    from tools.copywriter.brief import CopyResult
    from tools.copywriter.webflow_writer import write_cms_field
    res = CopyResult(text=_CLEAN, locale="en", ok=True, before="Old copy.")
    out = write_cms_field("col-1", "item-1", "summary", res, dry_run=True, run_dir=tmp_path)
    assert out["write"].dry_run is True and out["write"].success is True
    backup = json.loads((tmp_path / "backup.json").read_text(encoding="utf-8"))
    assert backup["prior_value"] == "Old copy."      # the old value is captured before any write
    audit = json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))
    assert audit["dry_run"] is True and audit["qa_ok"] is True


def test_consumer_tools_still_import_under_namespace_layout():
    # The strangler-fig shims + namespace package must keep every consumer importable.
    import importlib
    for m in ("tools.summary.cli", "tools.translator", "tools.offers.auto_extend",
              "tools.copywriter"):
        importlib.import_module(m)
