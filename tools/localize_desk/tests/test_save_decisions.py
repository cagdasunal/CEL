"""Tests for applying reviewer decisions to the repo.

The payload is website copy typed by a human and forwarded by a Worker, so most of
these are about refusing things rather than accepting them. The governing rule: a
partial save that reports success is worse than a failed one.
"""
from __future__ import annotations

import base64
import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from localize_desk.save_decisions import (  # noqa: E402
    Invalid,
    apply,
    clean_decision,
    decode,
    merge,
)


def pack(doc: dict) -> str:
    raw = json.dumps(doc, ensure_ascii=False).encode()
    return base64.b64encode(gzip.compress(raw)).decode()


def payload(locale: str = "de", decisions: dict | None = None) -> str:
    return pack({"schema": "cel-localization-desk/1", "locale": locale,
                 "decisions": decisions if decisions is not None else {}})


class TestDecode:
    def test_round_trips(self):
        assert decode(pack({"a": 1})) == {"a": 1}

    @pytest.mark.parametrize("bad,expect", [
        ("not base64 !!", "base64"),
        (base64.b64encode(b"not gzip").decode(), "gzip"),
        (base64.b64encode(gzip.compress(b"not json")).decode(), "JSON"),
        (base64.b64encode(gzip.compress(b'"a string"')).decode(), "object"),
    ])
    def test_every_failure_is_named(self, bad, expect):
        with pytest.raises(Invalid, match=expect):
            decode(bad)


class TestCleanDecision:
    def test_keeps_only_known_fields(self):
        got = clean_decision("u", {"tray": "csv", "text": "x", "at": "2026-09-23",
                                   "evil": "rm -rf /", "__proto__": "nope"})
        assert set(got) == {"tray", "text", "at"}

    def test_null_means_clear(self):
        assert clean_decision("u", None) is None

    @pytest.mark.parametrize("bad", [
        {"tray": "somewhere-else"},
        {"tray": "csv", "text": 123},
        {"tray": "csv", "rejected": "not a list"},
        {"tray": "csv", "rejected": [1, 2]},
        {"tray": "csv", "at": "x" * 41},
        "a string",
        {},
    ])
    def test_rejects_malformed(self, bad):
        with pytest.raises(Invalid):
            clean_decision("u", bad)

    def test_text_has_a_ceiling(self):
        with pytest.raises(Invalid, match="over the"):
            clean_decision("u", {"text": "x" * 8001})

    def test_rejected_history_is_bounded(self):
        got = clean_decision("u", {"tray": "draft", "rejected": [str(i) for i in range(20)]})
        assert got["rejected"] == ["15", "16", "17", "18", "19"]


class TestMerge:
    def test_adds_updates_and_clears(self):
        existing = {"keep": {"tray": "csv"}, "drop": {"tray": "draft"},
                    "same": {"tray": "csv"}}
        merged, counts = merge(existing, {
            "new": {"tray": "draft"},
            "drop": None,
            "same": {"tray": "csv"},
            "keep": {"tray": "draft"},
        })
        assert merged == {"keep": {"tray": "draft"}, "same": {"tray": "csv"},
                          "new": {"tray": "draft"}}
        assert counts == {"set": 2, "cleared": 1, "unchanged": 1}

    def test_does_not_mutate_the_existing_dict(self):
        existing = {"a": {"tray": "csv"}}
        merge(existing, {"b": {"tray": "draft"}})
        assert existing == {"a": {"tray": "csv"}}

    def test_a_single_bad_entry_fails_the_whole_apply(self):
        """No partial writes. A save that half-worked and said 'ok' is the worst case."""
        with pytest.raises(Invalid):
            merge({}, {"good": {"tray": "csv"}, "bad": {"tray": "nowhere"}})


class TestApply:
    def test_writes_and_merges_across_calls(self, tmp_path):
        r1 = apply("de", payload("de", {"u1": {"tray": "csv", "text": "eins"}}), tmp_path)
        assert r1["total"] == 1 and r1["set"] == 1

        r2 = apply("de", payload("de", {"u2": {"tray": "draft"}}), tmp_path)
        assert r2["total"] == 2, "a second save must merge, not replace"

        doc = json.loads((tmp_path / "de" / "decisions.json").read_text())
        assert set(doc["decisions"]) == {"u1", "u2"}
        assert doc["decisions"]["u1"]["text"] == "eins"

    def test_each_locale_has_its_own_file(self, tmp_path):
        apply("de", payload("de", {"u1": {"tray": "csv"}}), tmp_path)
        apply("fr", payload("fr", {"u1": {"tray": "draft"}}), tmp_path)
        assert json.loads((tmp_path / "de" / "decisions.json").read_text())["decisions"]["u1"]["tray"] == "csv"
        assert json.loads((tmp_path / "fr" / "decisions.json").read_text())["decisions"]["u1"]["tray"] == "draft"

    def test_refuses_an_unknown_locale(self, tmp_path):
        with pytest.raises(Invalid, match="unknown locale"):
            apply("xx", payload("xx"), tmp_path)

    def test_refuses_when_the_payload_disagrees_with_the_dispatch(self, tmp_path):
        """Two sources say what is being written; a disagreement is never benign."""
        with pytest.raises(Invalid, match="dispatch said"):
            apply("de", payload("fr", {"u1": {"tray": "csv"}}), tmp_path)

    def test_refuses_an_unexpected_schema(self, tmp_path):
        with pytest.raises(Invalid, match="schema"):
            apply("de", pack({"schema": "something/9", "locale": "de", "decisions": {}}), tmp_path)

    def test_refuses_an_oversized_batch(self, tmp_path):
        big = {f"u{i}": {"tray": "csv"} for i in range(5001)}
        with pytest.raises(Invalid, match="over the"):
            apply("de", payload("de", big), tmp_path)

    def test_a_corrupt_existing_file_does_not_lose_the_incoming_save(self, tmp_path):
        (tmp_path / "de").mkdir()
        (tmp_path / "de" / "decisions.json").write_text("{ this is not json")
        r = apply("de", payload("de", {"u1": {"tray": "csv"}}), tmp_path)
        assert r["total"] == 1

    def test_output_is_stable_across_identical_saves(self, tmp_path):
        """Sorted keys, so a re-save produces no git diff and no noise commit."""
        apply("de", payload("de", {"b": {"tray": "csv"}, "a": {"tray": "draft"}}), tmp_path)
        first = (tmp_path / "de" / "decisions.json").read_text()
        apply("de", payload("de", {"a": {"tray": "draft"}, "b": {"tray": "csv"}}), tmp_path)
        assert (tmp_path / "de" / "decisions.json").read_text() == first


class TestInjectionShapedInput:
    """The payload is human-typed copy. None of it is ever executed, and these are
    the shapes that would matter if that ever stopped being true."""

    @pytest.mark.parametrize("nasty", [
        "$(rm -rf /)",
        "`whoami`",
        "'; DROP TABLE units; --",
        "../../etc/passwd",
        "<script>alert(1)</script>",
        "a\nb\rc\x00d",
    ])
    def test_stored_verbatim_as_data(self, tmp_path, nasty):
        apply("de", payload("de", {"u1": {"tray": "csv", "text": nasty}}), tmp_path)
        doc = json.loads((tmp_path / "de" / "decisions.json").read_text())
        assert doc["decisions"]["u1"]["text"] == nasty

    def test_a_unit_id_must_be_a_non_empty_string(self, tmp_path):
        with pytest.raises(Invalid):
            merge({}, {"": {"tray": "csv"}})
