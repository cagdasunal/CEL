"""The English freeze is enforced (monorepo runbook WO-30, plan §3.1, R60).

`data/localize/freeze.json` names the pages whose English must not change while a
localization round is open: regenerating it mid-round changes the text every approval was
made against. It was a file nothing read. `generate-english` now leaves a frozen page out,
and refuses one named with --page; the TRANSLATED summary blocks still regenerate.
"""
import json
from pathlib import Path

import pytest

from tools.summary import cli, config

FROZEN = "https://www.englishcollege.com/vancouver/cost-of-studying-english"


@pytest.fixture(autouse=True)
def _offline_landing_fetch(monkeypatch):
    import types
    from tools.summary import page_fetcher
    monkeypatch.setattr(page_fetcher, "fetch_page",
                        lambda *a, **k: types.SimpleNamespace(existing_summary_parts={}),
                        raising=False)


@pytest.fixture
def freeze(tmp_path, monkeypatch):
    def write(pages, until=None):
        f = tmp_path / "freeze.json"
        f.write_text(json.dumps({"schema_version": 1, "frozen_pages": pages,
                                 "frozen_since": "2026-09-23", "frozen_until": until}))
        monkeypatch.setattr(config, "FREEZE_FILE", f)
    return write


def _english_plan(out: Path, *extra: str) -> dict:
    assert cli.main(["plan", "--out-dir", str(out), *extra]) == 0
    return json.loads((out / "report.json").read_text())["phases"]["generate_english"]


def _static(plan: dict) -> list[str]:
    return [t["url"] for t in plan["targets"] if t["kind"] == "static_page"]


def test_a_frozen_page_is_not_a_generate_english_target(tmp_path, freeze):
    freeze(["/vancouver/cost-of-studying-english"])
    plan = _english_plan(tmp_path / "o")
    assert FROZEN not in _static(plan)
    assert plan["frozen"] == [FROZEN]
    assert "https://www.englishcollege.com/vancouver/vs-toronto" in _static(plan)


def test_the_freeze_is_per_page_not_per_prefix(tmp_path, freeze):
    freeze(["/vancouver"])
    urls = _static(_english_plan(tmp_path / "o"))
    assert "https://www.englishcollege.com/vancouver" not in urls
    assert "https://www.englishcollege.com/vancouver/vs-toronto" in urls


@pytest.mark.parametrize("subcommand", ["generate-english", "all"])
def test_naming_a_frozen_page_is_refused_before_anything_runs(tmp_path, freeze, subcommand):
    freeze(["/vancouver/cost-of-studying-english"])
    out = tmp_path / "o"
    rc = cli.main([subcommand, "--dry-run", "--page", FROZEN, "--out-dir", str(out)])
    assert rc == 2
    assert not (out / "report.json").exists()


def test_a_freeze_whose_end_date_has_passed_is_over(tmp_path, freeze):
    freeze(["/vancouver/cost-of-studying-english"], until="2026-01-01")
    assert FROZEN in _static(_english_plan(tmp_path / "o"))


def test_the_translated_blocks_of_a_frozen_page_still_regenerate(tmp_path, freeze):
    """Only the ENGLISH step is frozen (runbook WO-30): translate still takes the page."""
    freeze(["/vancouver/cost-of-studying-english"])
    out = tmp_path / "o"
    out.mkdir()
    (out / "en-summaries.json").write_text(json.dumps({"gen-0-cost": {
        "url": FROZEN, "markdown": "## Cost\n\nTuition from C$330 per week.\n",
        "content_type": "landing", "locale": "en"}}), encoding="utf-8")
    assert cli.main(["translate", "--dry-run", "--locale", "de", "--out-dir", str(out)]) == 0
    de = json.loads((out / "report.json").read_text())["phases"]["translate"]["per_locale"]["de"]
    assert de.get("request_count") == 1


def test_the_vendored_freeze_file_is_there_and_readable():
    """The monorepo's file, vendored and held identical by its parity check. Missing, the
    freeze would silently not exist. Read through the pipeline's own check, so a file the
    pipeline would refuse cannot be committed (round 3: `frozen_until: ""` passed here)."""
    doc = json.loads(config.FREEZE_FILE.read_text(encoding="utf-8"))
    assert doc["schema_version"] == 1 and doc["frozen_pages"]
    cli._frozen_paths()                          # raises FreezeInvalid on a bad shape


# ── Review round 2 (monorepo runbook WO-32, lens L3) ──────────────────────────────

@pytest.fixture
def raw_freeze(tmp_path, monkeypatch):
    def write(text: str):
        f = tmp_path / "freeze.json"
        f.write_text(text)
        monkeypatch.setattr(config, "FREEZE_FILE", f)
    return write


def test_a_malformed_freeze_holds_every_static_page_back_and_says_why(tmp_path, raw_freeze):
    """Reading an unreadable freeze as "nothing frozen" would unprotect the round."""
    raw_freeze("{not json")
    plan = _english_plan(tmp_path / "o")
    assert _static(plan) == []
    assert "not JSON" in plan["freeze_error"]
    assert any(t["kind"] == "cms_collection" for t in plan["targets"])


def test_the_blog_autopilot_never_reads_the_freeze(tmp_path, raw_freeze):
    """--collection blog has nothing to do with frozen pages; a bad file crashed it."""
    raw_freeze("{not json")
    plan = _english_plan(tmp_path / "o", "--collection", "blog")
    assert "freeze_error" not in plan and plan["frozen"] == []


def test_naming_a_page_under_a_malformed_freeze_is_refused(tmp_path, raw_freeze):
    raw_freeze("[]")
    rc = cli.main(["generate-english", "--dry-run", "--page",
                   "https://www.englishcollege.com/vancouver/vs-toronto", "--out-dir", str(tmp_path / "o")])
    assert rc == 2


@pytest.mark.parametrize("doc", [
    {"schema_version": 2, "frozen_pages": ["/vancouver"], "frozen_until": None},
    {"schema_version": 1, "frozen_pages": "/vancouver", "frozen_until": None},
    {"schema_version": 1, "frozen_pages": ["vancouver"], "frozen_until": None},
    {"schema_version": 1, "frozen_pages": ["/vancouver"], "frozen_until": "2026/10/01"},
    {"schema_version": 1, "frozen_pages": ["/vancouver"], "frozen_until": 20261001},
    {"schema_version": 1, "frozen_pages": ["/vancouver"], "frozen_until": ""},
    {"schema_version": 1, "frozen_pages": ["/Vancouver"], "frozen_until": None},
    {"schema_version": 1, "frozen_pages": ["//vancouver"], "frozen_until": None},
    {"schema_version": 1, "frozen_pages": ["https://www.englishcollege.com/vancouver"], "frozen_until": None},
])
def test_a_freeze_of_the_wrong_shape_is_invalid_not_empty(raw_freeze, doc):
    raw_freeze(json.dumps(doc))
    with pytest.raises(cli.FreezeInvalid):
        cli._frozen_paths()


def test_page_plans_that_page_and_no_collection(tmp_path, freeze):
    freeze([])
    url = "https://www.englishcollege.com/vancouver/vs-toronto"
    plan = _english_plan(tmp_path / "o", "--page", url)
    assert [t.get("url") for t in plan["targets"]] == [url]


def test_a_dry_run_reports_what_the_freeze_held_back(tmp_path, freeze):
    """The plan said it; the run itself said nothing."""
    freeze(["/vancouver/cost-of-studying-english"])
    out = tmp_path / "o"
    assert cli.main(["generate-english", "--dry-run", "--out-dir", str(out)]) == 0
    ge = json.loads((out / "report.json").read_text())["phases"]["generate_english"]
    assert ge["frozen"] == [FROZEN]


def test_translate_page_translates_only_that_page(tmp_path, freeze):
    freeze(["/vancouver/cost-of-studying-english"])
    out = tmp_path / "o"
    out.mkdir()
    (out / "en-summaries.json").write_text(json.dumps({
        "gen-0-cost": {"url": FROZEN, "markdown": "## Cost\n\nTuition from C$330 per week.\n",
                       "content_type": "landing", "locale": "en"},
        "gen-1-vs": {"url": "https://www.englishcollege.com/vancouver/vs-toronto",
                     "markdown": "## Toronto\n\nTwo cities compared.\n",
                     "content_type": "landing", "locale": "en"}}), encoding="utf-8")
    assert cli.main(["translate", "--dry-run", "--locale", "de", "--page", FROZEN,
                     "--out-dir", str(out)]) == 0
    de = json.loads((out / "report.json").read_text())["phases"]["translate"]["per_locale"]["de"]
    assert de.get("request_count") == 1


def test_a_frozen_page_no_manifest_holds_is_translated_from_its_live_english(tmp_path, freeze, monkeypatch):
    """generate-english may not run for a frozen page, so no manifest ever holds it."""
    import types
    from tools.summary import page_fetcher
    freeze(["/vancouver/cost-of-studying-english"])
    monkeypatch.setattr(page_fetcher, "fetch_page", lambda *a, **k: types.SimpleNamespace(
        existing_summary_parts={"summary-tagline": "Cost",
                                "summary-paragraph": "Tuition from C$330 per week."}))
    out = tmp_path / "o"
    assert cli.main(["translate", "--dry-run", "--locale", "de", "--page", FROZEN,
                     "--out-dir", str(out)]) == 0
    de = json.loads((out / "report.json").read_text())["phases"]["translate"]["per_locale"]["de"]
    assert de.get("request_count") == 1


# ── Round 3 (the re-check of WO-32's fixes) ────────────────────────────────────────

def test_a_frozen_path_no_static_page_has_is_reported(tmp_path, freeze):
    freeze(["/vancouver/cost-of-studying-english", "/vancouver/no-such-page"])
    plan = _english_plan(tmp_path / "o")
    assert plan["freeze_unmatched"] == ["/vancouver/no-such-page"]


@pytest.mark.parametrize("named", [FROZEN + "/", FROZEN.replace("www.", "")])
def test_the_live_english_is_found_by_path(tmp_path, freeze, monkeypatch, named):
    """A trailing slash or the bare host used to say "run generate-english first"."""
    import types
    from tools.summary import page_fetcher
    freeze(["/vancouver/cost-of-studying-english"])
    monkeypatch.setattr(page_fetcher, "fetch_page", lambda *a, **k: types.SimpleNamespace(
        existing_summary_parts={"summary-tagline": "Cost", "summary-paragraph": "Tuition."}))
    out = tmp_path / "o"
    assert cli.main(["translate", "--dry-run", "--locale", "de", "--page", named, "--out-dir", str(out)]) == 0
    de = json.loads((out / "report.json").read_text())["phases"]["translate"]["per_locale"]["de"]
    assert de.get("request_count") == 1


def test_a_page_run_leaves_the_dashboards_coverage_alone(tmp_path, monkeypatch):
    """A live `translate --page` replaced translation-status.json with that one page."""
    import types
    from tools.summary import batch_runner, llms_parser, page_fetcher
    prior = tmp_path / "prior"
    prior.mkdir()
    (prior / "en-summaries.json").write_text(json.dumps({"gen-0-cost": {
        "url": FROZEN, "markdown": "## Cost\n\nTuition from C$330 per week.\n",
        "content_type": "landing", "locale": "en"}}), encoding="utf-8")
    weglot = tmp_path / "weglot"
    weglot.mkdir()
    status = weglot / "translation-status.json"
    status.write_text('{"per_item": {"gen-7-other": ["fr"]}}', encoding="utf-8")
    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", weglot)
    monkeypatch.setattr(config, "TRANSLATION_MEMORY_FILE", tmp_path / "tm.json")
    monkeypatch.setattr(config, "BLOCK_TM_FILE", tmp_path / "block-tm.json", raising=False)
    monkeypatch.setattr(llms_parser, "fetch_and_parse", lambda *a, **k: llms_parser.LlmsIndex(entries=[]))
    monkeypatch.setattr(page_fetcher, "fetch_page",
                        lambda *a, **k: types.SimpleNamespace(existing_summary_parts={}))
    captured = {}

    def fake_submit(requests, **kw):
        captured["requests"] = requests
        return batch_runner.BatchHandle(batch_id="b", request_count=len(requests), submitted_at="t", dry_run=False)

    monkeypatch.setattr(batch_runner, "submit_batch", fake_submit)
    monkeypatch.setattr(batch_runner, "wait_for_batch", lambda h, **kw: [
        batch_runner.BatchResult(custom_id=r.custom_id, succeeded=True, content="## Kosten\n\nAb C$330 pro Woche.")
        for r in captured["requests"]])
    out = tmp_path / "out"
    assert cli.main(["translate", "--no-dry-run", "--locale", "de", "--page", FROZEN,
                     "--from-run", str(prior), "--out-dir", str(out)]) == 0
    assert json.loads(status.read_text()) == {"per_item": {"gen-7-other": ["fr"]}}
    warns = json.loads((out / "report.json").read_text())["phases"]["translate"]["warnings"]
    assert any("not written" in w for w in warns)

