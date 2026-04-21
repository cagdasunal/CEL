#!/usr/bin/env python3
"""Tests for tools/update_log.py — count_pending_weglot_entries() and render output.

Run:
    pytest tools/test_update_log.py -v
"""

import sys
from pathlib import Path

import pytest

# Make update_log importable regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))
import update_log
from update_log import count_pending_weglot_entries, render

# The real Weglot CSV header produced by sync_exclusions.py
WEGLOT_HEADER = "id;type;value;languages;language_button_displayed;exclusion_behavior"

# A realistic data row (matches the actual format from the live CSV)
DATA_ROW = ";Is exactly;/post/some-slug;ar,de,es,fr,it,ja,ko,pt;1;Redirect"


# ---------------------------------------------------------------------------
# count_pending_weglot_entries
# ---------------------------------------------------------------------------

class TestCountPendingWeglotEntries:
    """Unit tests for count_pending_weglot_entries().

    All tests chdir to tmp_path so weglot.csv reads from an isolated directory.
    """

    def test_missing_file_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert count_pending_weglot_entries() == 0

    def test_empty_file_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "weglot.csv").write_text("", encoding="utf-8")
        assert count_pending_weglot_entries() == 0

    def test_whitespace_only_file_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "weglot.csv").write_text("   \n\n  \n", encoding="utf-8")
        assert count_pending_weglot_entries() == 0

    def test_header_only_returns_zero(self, tmp_path, monkeypatch):
        """Header-only file means nothing to import."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "weglot.csv").write_text(WEGLOT_HEADER + "\n", encoding="utf-8")
        assert count_pending_weglot_entries() == 0

    def test_header_plus_one_data_row_returns_one(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "weglot.csv").write_text(
            WEGLOT_HEADER + "\n" + DATA_ROW + "\n", encoding="utf-8"
        )
        assert count_pending_weglot_entries() == 1

    def test_regression_four_data_rows_returns_four(self, tmp_path, monkeypatch):
        """Regression: before the 2026-04-16 fix, the header was counted as a data row
        and this returned 5 instead of 4."""
        monkeypatch.chdir(tmp_path)
        rows = [
            WEGLOT_HEADER,
            ";Is exactly;/post/apprendre-anglais-san-diego-experience-gabriel;ar,de,es,it,ja,ko,pt;1;Redirect",
            ";Is exactly;/post/englisch-lernen-san-diego-gabriel-erfahrung;ar,es,fr,it,ja,ko,pt;1;Redirect",
            ";Is exactly;/post/san-diego-vs-hawaii-englisch-lernen;ar,es,fr,it,ja,ko,pt;1;Redirect",
            ";Is exactly;/post/sejours-linguistique-vancouver-famille-colocation;ar,de,es,it,ja,ko,pt;1;Redirect",
        ]
        (tmp_path / "weglot.csv").write_text("\n".join(rows), encoding="utf-8")
        assert count_pending_weglot_entries() == 4

    def test_header_with_many_data_rows(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        data_rows = [f";Is exactly;/post/slug-{i};ar,de;1;Redirect" for i in range(10)]
        csv_text = "\n".join([WEGLOT_HEADER] + data_rows)
        (tmp_path / "weglot.csv").write_text(csv_text, encoding="utf-8")
        assert count_pending_weglot_entries() == 10

    def test_whitespace_lines_between_rows_ignored(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        csv_text = WEGLOT_HEADER + "\n\n" + DATA_ROW + "\n\n" + DATA_ROW + "\n"
        (tmp_path / "weglot.csv").write_text(csv_text, encoding="utf-8")
        assert count_pending_weglot_entries() == 2

    def test_no_recognized_header_counts_all_lines(self, tmp_path, monkeypatch):
        """CSV with an unrecognized first row: every line is treated as a data row."""
        monkeypatch.chdir(tmp_path)
        csv_text = "\n".join([
            "custom_column;other_column",
            "val1;val2",
            "val3;val4",
        ])
        (tmp_path / "weglot.csv").write_text(csv_text, encoding="utf-8")
        assert count_pending_weglot_entries() == 3

    def test_id_only_first_field_not_mistaken_for_header(self, tmp_path, monkeypatch):
        """'id;something_else' (not 'id;type;') should NOT be treated as a header —
        tighter than the original 'id;' check to avoid false-positives."""
        monkeypatch.chdir(tmp_path)
        csv_text = "\n".join([
            "id;other_column;third",   # starts with "id;" but not "id;type;" — not a Weglot header
            "val1;val2;val3",
        ])
        (tmp_path / "weglot.csv").write_text(csv_text, encoding="utf-8")
        # Both lines are data rows — NOT a header detection
        assert count_pending_weglot_entries() == 2


# ---------------------------------------------------------------------------
# render output sanity checks
# ---------------------------------------------------------------------------

class TestRender:
    """Smoke tests for the render() function output format."""

    def test_pending_shows_upload_required(self):
        entries = {
            "sitemap.xml": "2026-04-16 17:00 GMT+3",
            "llms.txt": "2026-04-16 17:00 GMT+3",
            "weglot.csv": "2026-04-16 17:00 GMT+3  [4 pending entries — UPLOAD NEEDED]",
        }
        output = render(entries, pending=4, weglot_last_check="2026-04-16 09:07 GMT+3")
        assert "Upload to Weglot: REQUIRED" in output
        assert "sitemap.englishcollege.com/weglot.csv" in output

    def test_cleared_shows_not_required(self):
        entries = {
            "sitemap.xml": "2026-04-16 17:00 GMT+3",
            "llms.txt": "2026-04-16 17:00 GMT+3",
            "weglot.csv": "2026-04-16 17:00 GMT+3  [cleared — no upload needed]",
        }
        output = render(entries, pending=0, weglot_last_check="2026-04-16 09:07 GMT+3")
        assert "Upload to Weglot: NOT REQUIRED" in output
        # When cleared, no download/dashboard block should appear
        assert "Download:" not in output
        assert "Dashboard:" not in output

    def test_output_starts_with_last_updated(self):
        entries = {k: "2026-04-16 17:00 GMT+3" for k in ("sitemap.xml", "llms.txt", "weglot.csv")}
        output = render(entries, pending=0, weglot_last_check="2026-04-16 09:07 GMT+3")
        assert output.startswith("Last updated (GMT+3")

    def test_all_three_tracked_files_present(self):
        entries = {k: "2026-04-16 17:00 GMT+3" for k in ("sitemap.xml", "llms.txt", "weglot.csv")}
        output = render(entries, pending=0, weglot_last_check="2026-04-16 09:07 GMT+3")
        for name in ("sitemap.xml", "llms.txt", "weglot.csv"):
            assert name in output

    def test_each_tracked_file_has_url_line(self):
        entries = {k: "2026-04-16 17:00 GMT+3" for k in ("sitemap.xml", "llms.txt", "weglot.csv")}
        output = render(entries, pending=0, weglot_last_check="2026-04-16 09:07 GMT+3")
        assert "URL: https://sitemap.englishcollege.com/sitemap.xml" in output
        assert "URL: https://sitemap.englishcollege.com/llms.txt" in output
        assert "URL: https://sitemap.englishcollege.com/weglot.csv" in output

    def test_last_weglot_check_line_present(self):
        entries = {k: "2026-04-16 17:00 GMT+3" for k in ("sitemap.xml", "llms.txt", "weglot.csv")}
        output = render(entries, pending=0, weglot_last_check="2026-04-16 09:07 GMT+3")
        assert "Last Weglot check: 2026-04-16 09:07 GMT+3" in output

    def test_last_weglot_check_never_when_missing(self):
        entries = {k: "2026-04-16 17:00 GMT+3" for k in ("sitemap.xml", "llms.txt", "weglot.csv")}
        output = render(entries, pending=0, weglot_last_check="never")
        assert "Last Weglot check: never" in output


# ---------------------------------------------------------------------------
# read_weglot_last_check
# ---------------------------------------------------------------------------

class TestReadWeglotLastCheck:
    """Unit tests for read_weglot_last_check()."""

    def test_missing_file_returns_never(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert update_log.read_weglot_last_check() == "never"

    def test_empty_file_returns_never(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".weglot-last-check").write_text("", encoding="utf-8")
        assert update_log.read_weglot_last_check() == "never"

    def test_malformed_file_returns_never(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".weglot-last-check").write_text("not-a-timestamp", encoding="utf-8")
        assert update_log.read_weglot_last_check() == "never"

    def test_valid_utc_z_timestamp_converts_to_gmt3(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".weglot-last-check").write_text(
            "2026-04-21T06:07:00Z", encoding="utf-8"
        )
        # 06:07 UTC → 09:07 GMT+3
        assert update_log.read_weglot_last_check() == "2026-04-21 09:07 GMT+3"

    def test_valid_offset_timestamp_converts_to_gmt3(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".weglot-last-check").write_text(
            "2026-04-21T06:07:00+00:00", encoding="utf-8"
        )
        assert update_log.read_weglot_last_check() == "2026-04-21 09:07 GMT+3"

    def test_whitespace_around_timestamp_trimmed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".weglot-last-check").write_text(
            "  2026-04-21T06:07:00Z\n", encoding="utf-8"
        )
        assert update_log.read_weglot_last_check() == "2026-04-21 09:07 GMT+3"
