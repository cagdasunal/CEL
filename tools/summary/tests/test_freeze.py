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
