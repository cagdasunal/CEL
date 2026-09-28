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
    freeze would silently not exist."""
    doc = json.loads(config.FREEZE_FILE.read_text(encoding="utf-8"))
    assert doc["schema_version"] == 1
    assert doc["frozen_pages"] and all(p.startswith("/") for p in doc["frozen_pages"])


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
