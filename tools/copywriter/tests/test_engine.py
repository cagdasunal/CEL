"""Engine + brief + webflow_writer + CLI — dry-run paths (no API, no live write)."""
import json
from pathlib import Path

import pytest

from tools.copywriter import CopyRequest, CopyResult, improve_copy
from tools.copywriter.brief import load_brief


def test_dry_run_improve_ko_returns_before_and_never_translates(monkeypatch):
    # The translator MUST NOT be called by improve_copy (locale-native).
    import tools.translator.engine as te
    calls = {"n": 0}
    monkeypatch.setattr(te, "translate_batch", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or [])
    req = CopyRequest(brief="warmer tone", locale="ko", existing_copy="원래 한국어 카피입니다.")
    r = improve_copy(req, dry_run=True)
    assert isinstance(r, CopyResult)
    assert r.locale == "ko" and r.before == "원래 한국어 카피입니다."
    assert "dry_run" in r.qa_flags
    assert calls["n"] == 0  # never translated


def test_dry_run_improve_en(monkeypatch):
    req = CopyRequest(brief="tighten the intro", locale="en", existing_copy="Some current copy.")
    r = improve_copy(req, dry_run=True)
    assert r.locale == "en" and r.before == "Some current copy." and r.ok


def test_load_brief_roundtrip(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps({"brief": "improve hero", "locale": "ko",
                             "existing_copy": "x", "must_keep_facts": ["B2"]}), encoding="utf-8")
    req = load_brief(p)
    assert req.brief == "improve hero" and req.locale == "ko" and req.must_keep_facts == ("B2",)


def test_load_brief_requires_brief(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"locale": "ko"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_brief(p)


def test_webflow_writer_dry_run_backs_up_and_does_not_write(tmp_path):
    from tools.copywriter import webflow_writer
    res = CopyResult(text="## Heading\n\nClean human copy.", locale="en", ok=True, before="old copy value")
    out = webflow_writer.write_cms_field("cid", "iid", "summary", res, dry_run=True, run_dir=tmp_path)
    assert out["write"].dry_run is True and out["write"].success is True
    backup = json.loads((tmp_path / "backup.json").read_text(encoding="utf-8"))
    assert backup["prior_value"] == "old copy value" and backup["field_slug"] == "summary"
    assert (tmp_path / "audit.json").exists()


def test_webflow_writer_static_doc(tmp_path):
    from tools.copywriter import webflow_writer
    res = CopyResult(text="improved after", locale="en", ok=True, before="original before")
    out = webflow_writer.write_static_doc("https://www.englishcollege.com/courses", res, out_dir=tmp_path)
    doc = Path(out["doc"]).read_text(encoding="utf-8")
    assert "BEFORE" in doc and "AFTER" in doc and "original before" in doc and "improved after" in doc


def test_cli_improve_dry_run_writes_preview(tmp_path):
    from tools.copywriter.cli import main
    brief = tmp_path / "b.json"
    brief.write_text(json.dumps({"brief": "improve", "locale": "en", "existing_copy": "Current copy."}), encoding="utf-8")
    out = tmp_path / "run"
    rc = main(["improve", "--brief", str(brief), "--out-dir", str(out)])
    assert rc == 0
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert result["locale"] == "en" and result["before"] == "Current copy."
    assert (out / "preview.md").exists()
