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


# ── Round 3 (the re-check of WO-32's fixes) ────────────────────────────────────────

def test_a_frozen_path_no_static_page_has_is_reported(tmp_path, freeze):
    freeze(["/vancouver/cost-of-studying-english", "/vancouver/no-such-page"])
    plan = _english_plan(tmp_path / "o")
    assert plan["freeze_unmatched"] == ["/vancouver/no-such-page"]


