"""Tests for tools.summary.webflow_designer.

Specifically the new `write_static_summary` top-level function that closes
audit-086 H-1 (tracker-087 F-1) by writing static-page summaries to Markdown
files on disk for manual paste into Webflow Designer.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.summary.webflow_designer import write_static_summary


def test_write_static_summary_dry_run_returns_result_but_no_file(tmp_path: Path) -> None:
    out_dir = tmp_path / "static-summaries"
    result = write_static_summary(
        page_url="https://www.englishcollege.com/learn-english-usa",
        summary_markdown="## How long does it take?\n\nTwelve weeks.\n",
        out_dir=out_dir,
        dry_run=True,
    )
    assert result.dry_run is True
    assert result.success is True
    assert result.method == "WRITE_FILE"
    # No file should be created in dry-run.
    expected_path = out_dir / "learn-english-usa.summary.md"
    assert not expected_path.exists()
    # But the payload should describe where it WOULD have written.
    assert result.payload["path"] == str(expected_path)


def test_write_static_summary_live_writes_file(tmp_path: Path) -> None:
    out_dir = tmp_path / "static-summaries"
    content = "## How long?\n\nIt depends.\n"
    result = write_static_summary(
        page_url="https://www.englishcollege.com/learn-english-usa",
        summary_markdown=content,
        out_dir=out_dir,
        dry_run=False,
    )
    assert result.dry_run is False
    assert result.success is True
    expected_path = out_dir / "learn-english-usa.summary.md"
    assert expected_path.exists()
    assert expected_path.read_text(encoding="utf-8") == content


def test_write_static_summary_home_url(tmp_path: Path) -> None:
    """A bare root URL should derive slug 'home'."""
    out_dir = tmp_path / "static-summaries"
    result = write_static_summary(
        page_url="https://www.englishcollege.com/",
        summary_markdown="## Welcome\n\nHello.\n",
        out_dir=out_dir,
        dry_run=False,
    )
    assert result.success is True
    assert (out_dir / "home.summary.md").exists()


def test_write_static_summary_nested_path_uses_dashes(tmp_path: Path) -> None:
    out_dir = tmp_path / "static-summaries"
    result = write_static_summary(
        page_url="https://www.englishcollege.com/pathway/semester-abroad",
        summary_markdown="## Semester abroad\n\nGo abroad.\n",
        out_dir=out_dir,
        dry_run=False,
    )
    assert result.success is True
    assert (out_dir / "pathway-semester-abroad.summary.md").exists()


def test_write_static_summary_rejects_traversal_slug(tmp_path: Path) -> None:
    """If the URL path contains '..', the function refuses to write."""
    out_dir = tmp_path / "static-summaries"
    result = write_static_summary(
        page_url="https://www.englishcollege.com/../../etc/passwd",
        summary_markdown="## bad\n\nbad.\n",
        out_dir=out_dir,
        dry_run=False,
    )
    assert result.success is False
    assert "unsafe slug" in (result.error or "")
    # And nothing was written.
    assert not any(out_dir.rglob("*.md")) if out_dir.exists() else True
