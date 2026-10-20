#!/usr/bin/env python3
"""Tests for tools/update_log.py — render output.

weglot.csv and its upload signal are gone (monorepo CEL-104): the log tracks
sitemap.xml and llms.txt only.

Run:
    pytest tools/test_update_log.py -v
"""

import sys
from pathlib import Path

# Make update_log importable regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))
import update_log
from update_log import render

ENTRIES = {k: "2026-04-16 17:00 GMT+3" for k in ("sitemap.xml", "llms.txt")}


# ---------------------------------------------------------------------------
# render output sanity checks
# ---------------------------------------------------------------------------

class TestRender:
    """Smoke tests for the render() function output format."""

    def test_output_starts_with_last_updated(self):
        assert render(ENTRIES).startswith("Last updated (GMT+3")

    def test_both_tracked_files_present(self):
        output = render(ENTRIES)
        for name in ("sitemap.xml", "llms.txt"):
            assert name in output

    def test_each_tracked_file_has_url_line(self):
        output = render(ENTRIES)
        assert "URL: https://cel.englishcollege.com/sitemap.xml" in output
        assert "URL: https://cel.englishcollege.com/llms.txt" in output

    def test_nothing_about_weglot_is_left(self):
        # CEL-071 retired the daily report ("Last Weglot check"); CEL-104 the weglot.csv upload signal
        assert update_log.TRACKED == ("sitemap.xml", "llms.txt")
        assert "weglot" not in render(ENTRIES).lower()
