"""Integration tests for translate_batch (Gemini mocked at the batch_runner boundary)."""
from tools.translation_engine import translate_batch, TranslationUnit
from tools.translation_engine.glossary import Glossary, GlossaryTerm
from tools.translation_engine.tm import TranslationMemory

_GLOSSARY = Glossary(terms=[GlossaryTerm(term="CEL", do_not_translate=True, case_sensitive=True)], version="v1")


def _mock_gemini(monkeypatch, mapping: dict[str, str], succeeded: bool = True):
    """Patch batch_runner so each request's custom_id returns mapping[custom_id]."""
    from tools.summary import batch_runner

    captured = {}

    def fake_submit(requests, **kw):
        captured["requests"] = requests
        return batch_runner.BatchHandle(batch_id="b", request_count=len(requests), submitted_at="t", dry_run=False)

    def fake_wait(handle, **kw):
        return [
            batch_runner.BatchResult(
                custom_id=r.custom_id,
                succeeded=succeeded,
                content=mapping.get(r.custom_id, ""),
                error="" if succeeded else "mock failure",
            )
            for r in captured["requests"]
        ]

    monkeypatch.setattr(batch_runner, "submit_batch", fake_submit)
    monkeypatch.setattr(batch_runner, "wait_for_batch", fake_wait)
    return captured


def test_dry_run_returns_passthrough_stubs_no_api(monkeypatch):
    from tools.summary import batch_runner

    def boom(*a, **kw):
        raise AssertionError("submit_batch must not be called in dry-run")

    monkeypatch.setattr(batch_runner, "submit_batch", boom)
    units = [TranslationUnit(id="u1", text="Welcome to CEL")]
    out = translate_batch(units, "de", _GLOSSARY, dry_run=True)
    assert len(out) == 1
    assert out[0].id == "u1"
    assert out[0].qa_flags == ["dry_run"]
    assert out[0].ok


def test_tm_hit_skips_api(monkeypatch, tmp_path):
    tm = TranslationMemory(tmp_path / "tm.json")
    tm.put("Welcome", "de", "v1", "Willkommen")
    captured = _mock_gemini(monkeypatch, {})  # would error if a request were built+sent
    units = [TranslationUnit(id="u1", text="Welcome")]
    out = translate_batch(units, "de", _GLOSSARY, tm=tm)
    assert out[0].from_tm is True
    assert out[0].target == "Willkommen"
    assert "requests" not in captured  # no submit happened


def test_live_translation_runs_glossary_and_qa(monkeypatch, tmp_path):
    tm = TranslationMemory(tmp_path / "tm.json")
    units = [TranslationUnit(id="u1", text="Study at CEL for 12 weeks")]
    # Good translation: keeps "CEL" + "12".
    _mock_gemini(monkeypatch, {"u1": "Studiere bei CEL für 12 Wochen"})
    out = translate_batch(units, "de", _GLOSSARY, tm=tm)
    assert out[0].ok
    assert out[0].target == "Studiere bei CEL für 12 Wochen"
    assert out[0].from_tm is False
    # Successful translation is written to TM.
    assert tm.get("Study at CEL for 12 weeks", "de", "v1") == "Studiere bei CEL für 12 Wochen"


def test_live_translation_qa_blocks_number_drift(monkeypatch, tmp_path):
    tm = TranslationMemory(tmp_path / "tm.json")
    units = [TranslationUnit(id="u1", text="Reach B2 in 12 weeks")]
    # Bad: drops the number 12 → QA blocks → ok False → NOT written to TM.
    _mock_gemini(monkeypatch, {"u1": "Erreiche B2 in wenigen Wochen"})
    out = translate_batch(units, "de", _GLOSSARY, tm=tm)
    assert out[0].ok is False
    assert any(f.startswith("number_drift") for f in out[0].qa_flags)
    assert tm.get("Reach B2 in 12 weeks", "de", "v1") is None  # not cached when not ok


def test_failed_batch_result_marks_not_ok(monkeypatch):
    units = [TranslationUnit(id="u1", text="Hello")]
    _mock_gemini(monkeypatch, {"u1": ""}, succeeded=False)
    out = translate_batch(units, "de", _GLOSSARY)
    assert out[0].ok is False
    assert any(f.startswith("batch_failed") for f in out[0].qa_flags)


def test_output_order_matches_input(monkeypatch):
    units = [TranslationUnit(id=f"u{i}", text=f"text {i}") for i in range(5)]
    _mock_gemini(monkeypatch, {f"u{i}": f"trans {i}" for i in range(5)})
    out = translate_batch(units, "de", _GLOSSARY)
    assert [t.id for t in out] == [f"u{i}" for i in range(5)]
