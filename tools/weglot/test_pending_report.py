"""Tests for tools/weglot/pending_report.py — the daily Weglot-import report must keep ONE issue.

Regression: 172 open duplicate "Weglot: 2 exclusion(s) pending import (<date>)" issues, 0 closed
(2026-04-14 .. 2026-10-06), because the report created a new issue per day and nothing ever
confirmed rows that had already been imported.
"""
from __future__ import annotations

import json

import pytest

from tools.weglot import pending_report as pr

HEADER = "id;type;value;languages;language_button_displayed;exclusion_behavior\n"
ROW_A = ";Is exactly;/post/aaa;ar,de;1;Redirect\n"
ROW_B = ";Is exactly;/post/bbb;ar,fr;1;Redirect\n"


class FakeGh:
    """Stands in for the gh CLI: answers `issue list` from `issues`, records everything else."""

    def __init__(self, issues=None):
        self.issues = issues or []
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        return json.dumps(self.issues) if args[:2] == ["issue", "list"] else ""

    def writes(self):
        return [c[1] for c in self.calls if c[0] == "issue" and c[1] != "list"]


def _issue(number, title=pr.TITLE, body=""):
    return {"number": number, "title": title, "body": body}


def _csv(tmp_path, text):
    p = tmp_path / "weglot.csv"
    p.write_text(text, encoding="utf-8")
    return p


# ---- pending_rows -----------------------------------------------------------------------------

def test_missing_file_is_nothing_pending(tmp_path):
    assert pr.pending_rows(tmp_path / "nope.csv") == []


def test_header_only_file_is_nothing_pending(tmp_path):
    assert pr.pending_rows(_csv(tmp_path, HEADER)) == []


def test_rows_are_read_with_their_languages(tmp_path):
    assert pr.pending_rows(_csv(tmp_path, HEADER + ROW_A + ROW_B)) == [("/post/aaa", "ar,de"), ("/post/bbb", "ar,fr")]


# ---- reconcile --------------------------------------------------------------------------------

ROWS = [("/post/aaa", "ar,de"), ("/post/bbb", "ar,fr")]


def test_pending_rows_create_the_issue_once():
    gh = FakeGh()
    assert pr.reconcile(ROWS, "o/r", gh) == "created"
    create = next(c for c in gh.calls if c[1] == "create")
    assert pr.TITLE in create and "/post/aaa" in create[-1] and "/post/bbb" in create[-1]
    assert gh.writes() == ["create"]


def test_the_next_day_does_not_create_a_second_issue():
    """The regression: same pending rows, issue already open -> no new issue, no edit."""
    body = pr.build_body(ROWS, "o/r")
    gh = FakeGh([_issue(7, body=body)])
    assert pr.reconcile(ROWS, "o/r", gh) == "unchanged"
    assert gh.writes() == []


def test_a_stored_body_with_crlf_is_still_unchanged():
    gh = FakeGh([_issue(7, body=pr.build_body(ROWS, "o/r").replace("\n", "\r\n"))])
    assert pr.reconcile(ROWS, "o/r", gh) == "unchanged"


def test_changed_rows_edit_the_same_issue():
    gh = FakeGh([_issue(7, body=pr.build_body(ROWS[:1], "o/r"))])
    assert pr.reconcile(ROWS, "o/r", gh) == "updated"
    assert gh.writes() == ["edit"] and next(c for c in gh.calls if c[1] == "edit")[2] == "7"


def test_nothing_pending_closes_the_issue():
    gh = FakeGh([_issue(7)])
    assert pr.reconcile([], "o/r", gh) == "closed"
    assert gh.writes() == ["close"] and next(c for c in gh.calls if c[1] == "close")[2] == "7"


def test_nothing_pending_and_no_issue_does_nothing():
    gh = FakeGh()
    assert pr.reconcile([], "o/r", gh) == "none"
    assert gh.writes() == []


def test_legacy_dated_issues_are_never_touched():
    legacy = [_issue(n, title=f"Weglot: 2 exclusion(s) pending import (2026-09-{n:02d})") for n in range(1, 6)]
    gh = FakeGh(legacy)
    assert pr.reconcile([], "o/r", gh) == "none"
    assert gh.writes() == []
    assert pr.reconcile(ROWS, "o/r", gh) == "created"


# ---- main (CSV + Weglot + gh together) --------------------------------------------------------

@pytest.fixture
def run_main(tmp_path, monkeypatch):
    def _run(csv_text, weglot_paths, issues=None, key="k"):
        monkeypatch.setattr(pr, "CSV_PATH", _csv(tmp_path, csv_text))
        monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
        monkeypatch.setenv("WEGLOT_PUBLIC_KEY", key)
        monkeypatch.setattr(pr, "weglot_exclusion_paths", lambda k: weglot_paths)
        gh = FakeGh(issues)
        monkeypatch.setattr(pr, "_gh", gh)
        assert pr.main() == 0
        return gh
    return _run


def test_rows_already_in_weglot_are_not_reported(run_main):
    """The real incident: both CSV rows were imported by hand long ago -> no issue, open one closes."""
    gh = run_main(HEADER + ROW_A + ROW_B, {"/post/aaa", "/post/bbb", "/post/other"})
    assert gh.writes() == []
    gh = run_main(HEADER + ROW_A + ROW_B, {"/post/aaa", "/post/bbb"}, issues=[_issue(7)])
    assert gh.writes() == ["close"]


def test_only_the_rows_missing_from_weglot_are_reported(run_main):
    gh = run_main(HEADER + ROW_A + ROW_B, {"/post/aaa"})
    body = next(c for c in gh.calls if c[1] == "create")[-1]
    assert "/post/bbb" in body and "/post/aaa" not in body and "**1 blog post(s)**" in body


def test_when_weglot_cannot_be_read_every_row_is_reported(run_main):
    gh = run_main(HEADER + ROW_A + ROW_B, None)
    body = next(c for c in gh.calls if c[1] == "create")[-1]
    assert "/post/aaa" in body and "/post/bbb" in body


def test_without_a_key_every_row_is_reported(run_main):
    gh = run_main(HEADER + ROW_A, {"/post/aaa"}, key="")
    assert gh.writes() == ["create"]


def test_repo_is_required(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert pr.main() == 2


# ---- weglot_exclusion_paths -------------------------------------------------------------------

def test_weglot_paths_keep_only_exact_matches(monkeypatch):
    payload = {"excluded_paths": [
        {"type": "IS_EXACTLY", "value": "/post/aaa"},
        {"type": "START_WITH", "value": "/category/"},
        {"type": "IS_EXACTLY", "value": ""},
    ]}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, *a): return json.dumps(payload).encode()

    monkeypatch.setattr(pr.urllib.request, "urlopen", lambda req, timeout=0: Resp())
    assert pr.weglot_exclusion_paths("k") == {"/post/aaa"}


def test_weglot_paths_none_on_network_error(monkeypatch):
    def boom(req, timeout=0):
        raise OSError("down")
    monkeypatch.setattr(pr.urllib.request, "urlopen", boom)
    assert pr.weglot_exclusion_paths("k") is None
