"""Tests for tools.summary.run_ledger — the append-only run history + status.

Covers the public surface: record_run (append, never-raise), read_ledger
(roundtrip, corrupt-line tolerance), _compact_entry (TM-hit/Gemini split +
generate-english stats), format_status, and the `status` CLI subcommand.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.summary import run_ledger


def _translate_report() -> dict:
    return {
        "started_at": "2026-05-26T09:00:00+00:00",
        "finished_at": "2026-05-26T09:05:00+00:00",
        "subcommand": "translate",
        "dry_run": False,
        "phases": {
            "translate": {
                "target_locales": ["de", "fr"],
                "per_locale": {
                    "de": {"tm_hits": 28, "gemini_calls": 4, "succeeded": 32,
                           "failed": 0, "request_count": 32, "rows_appended": 700},
                    "fr": {"tm_hits": 30, "gemini_calls": 2, "succeeded": 32,
                           "failed": 0, "request_count": 32, "rows_appended": 710},
                },
            }
        },
    }


def test_record_and_read_roundtrip(tmp_path: Path):
    ledger = tmp_path / "run-ledger.jsonl"
    run_ledger.record_run(_translate_report(), tmp_path / "out-A", path=ledger)
    run_ledger.record_run(_translate_report(), tmp_path / "out-B", path=ledger)

    entries = run_ledger.read_ledger(ledger)
    assert len(entries) == 2
    assert entries[0]["out_dir"] == "out-A"
    assert entries[1]["out_dir"] == "out-B"
    assert entries[0]["subcommand"] == "translate"
    assert entries[0]["dry_run"] is False


def test_compact_entry_captures_tm_and_gemini_split(tmp_path: Path):
    ledger = tmp_path / "run-ledger.jsonl"
    run_ledger.record_run(_translate_report(), tmp_path / "out", path=ledger)
    e = run_ledger.read_ledger(ledger)[0]
    tr = e["translate"]
    assert tr["locales"] == ["de", "fr"]
    assert tr["per_locale"]["de"]["tm_hits"] == 28
    assert tr["per_locale"]["de"]["gemini_calls"] == 4
    assert tr["per_locale"]["fr"]["gemini_calls"] == 2


def test_compact_entry_captures_generate_english(tmp_path: Path):
    ledger = tmp_path / "run-ledger.jsonl"
    report = {
        "started_at": "2026-05-26T08:00:00+00:00",
        "finished_at": "2026-05-26T08:10:00+00:00",
        "subcommand": "generate-english",
        "dry_run": False,
        "phases": {
            "generate_english": {
                "target_count": 17, "sources_resolved": 17,
                "requests_built": 5, "idempotency_skipped": 12, "submitted": True,
            }
        },
    }
    run_ledger.record_run(report, tmp_path / "out", path=ledger)
    ge = run_ledger.read_ledger(ledger)[0]["generate_english"]
    assert ge["requests_built"] == 5
    assert ge["idempotency_skipped"] == 12
    assert ge["submitted"] is True


def test_record_run_never_raises_on_garbage(tmp_path: Path):
    ledger = tmp_path / "run-ledger.jsonl"
    # Non-dict report, missing phases, weird out_dir — must not raise.
    run_ledger.record_run({}, tmp_path / "out", path=ledger)
    run_ledger.record_run({"phases": {"translate": "not-a-dict"}}, tmp_path / "out", path=ledger)
    entries = run_ledger.read_ledger(ledger)
    assert len(entries) == 2  # both recorded, just sparse


def test_read_ledger_tolerates_corrupt_lines(tmp_path: Path):
    ledger = tmp_path / "run-ledger.jsonl"
    ledger.write_text(
        '{"subcommand": "translate", "dry_run": true}\n'
        "this is not json\n"
        "\n"
        '{"subcommand": "audit", "dry_run": false}\n',
        encoding="utf-8",
    )
    entries = run_ledger.read_ledger(ledger)
    assert len(entries) == 2
    assert entries[0]["subcommand"] == "translate"
    assert entries[1]["subcommand"] == "audit"


def test_read_ledger_absent_file_returns_empty(tmp_path: Path):
    assert run_ledger.read_ledger(tmp_path / "nope.jsonl") == []


def test_format_status_renders_sections(tmp_path: Path):
    ledger = tmp_path / "run-ledger.jsonl"
    run_ledger.record_run(_translate_report(), tmp_path / "out", path=ledger)
    summary_state = tmp_path / "summary-state.json"
    summary_state.write_text(json.dumps({
        "page-a": {"source_hash": "x", "generated_at": "2026-05-21T13:08:25+00:00"},
        "page-b": {"source_hash": "y", "generated_at": "2026-05-25T20:32:34+00:00"},
    }), encoding="utf-8")
    ts = tmp_path / "translation-status.json"
    ts.write_text(json.dumps({
        "generated_at": "2026-05-24T20:09:41+00:00", "source_run": "run-098-full",
        "per_locale": {"de": {"translated": 10, "failed": 0, "words": 7854}},
    }), encoding="utf-8")

    out = run_ledger.format_status(
        ledger_path=ledger, summary_state_path=summary_state,
        translation_status_path=ts,
    )
    assert "SUMMARY / TRANSLATION STATUS" in out
    assert "2026-05-25 20:32:34" in out   # latest generation surfaces
    assert "run-098-full" in out          # translation source_run surfaces
    assert "translate" in out             # recent-run line


def test_status_subcommand_via_cli(capsys):
    """The `status` CLI subcommand prints and exits 0 without creating an out_dir."""
    from tools.summary import cli
    rc = cli.main(["status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "SUMMARY / TRANSLATION STATUS" in out
