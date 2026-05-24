"""Integration tests for translate_batch (Gemini mocked at the batch_runner boundary)."""
from tools.translator import translate_batch, TranslationUnit
from tools.translator.glossary import Glossary, GlossaryTerm
from tools.translator.tm import TranslationMemory

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


def test_sync_routes_to_generate_sync_not_batch(monkeypatch):
    """sync=True → instant generate_sync (pilot runs); submit_batch must NOT fire."""
    from tools.summary import batch_runner

    def boom_submit(*a, **kw):
        raise AssertionError("submit_batch must not be called when sync=True")

    captured: dict = {}

    def fake_sync(requests, **kw):
        captured["requests"] = requests
        return [
            batch_runner.BatchResult(custom_id=r.custom_id, succeeded=True,
                                     content="Willkommen bei CEL")
            for r in requests
        ]

    monkeypatch.setattr(batch_runner, "submit_batch", boom_submit)
    monkeypatch.setattr(batch_runner, "generate_sync", fake_sync)
    units = [TranslationUnit(id="u1", text="Welcome to CEL")]
    out = translate_batch(units, "de", _GLOSSARY, sync=True)
    assert len(out) == 1 and out[0].ok
    assert out[0].target == "Willkommen bei CEL"
    assert len(captured["requests"]) == 1


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


def test_forbidden_term_blocks_and_not_cached(monkeypatch, tmp_path):
    # tracker-095 M2: a forbidden glossary term in the output sets ok=False
    # (must never ship) and is not written to the TM.
    glossary = Glossary(terms=[GlossaryTerm(term="cheap", forbidden=True)], version="v1")
    tm = TranslationMemory(tmp_path / "tm.json")
    units = [TranslationUnit(id="u1", text="Affordable courses")]
    _mock_gemini(monkeypatch, {"u1": "cheap Kurse"})  # contains the forbidden word
    out = translate_batch(units, "de", glossary, tm=tm)
    assert out[0].ok is False
    assert any(f.startswith("forbidden_term_present") for f in out[0].qa_flags)
    assert tm.get("Affordable courses", "de", "v1") is None


def test_qa_check_urls_false_allows_link_swap(monkeypatch):
    # tracker-095 H2: the link-swap caller disables url preservation, so a
    # swapped target URL does not block.
    units = [TranslationUnit(id="u1", text="See https://www.englishcollege.com/x")]
    _mock_gemini(monkeypatch, {"u1": "Siehe https://www.englishcollege.com/de/x"})
    out = translate_batch(units, "de", _GLOSSARY, qa_check_urls=False)
    assert out[0].ok
    assert not any(f.startswith("url_drift") for f in out[0].qa_flags)
