"""Static landing-page summary writer.

Writes a static-page summary to a Markdown file under
`docs/admin/weglot-imports/static-summaries/<slug>.summary.md` for the user to
paste into the Rich Text element below the hero in Webflow Designer.

This is the SUPPORTED path (tracker-087 F-1 / audit-086 H-1). The earlier
`WebflowDesignerClient` (a Designer-Engine API reader/writer for the page
element tree) was removed in tracker-092 Phase 2: its endpoints were never
verified, it was marked DEPRECATED, and it had zero callers anywhere in the
repo. The Markdown-file path below is the only static-page write mechanism.
"""
from __future__ import annotations

import os
import tempfile
import urllib.parse
from pathlib import Path

from tools.summary.webflow_client import WriteResult


def write_static_summary(
    page_url: str,
    summary_markdown: str,
    out_dir: Path,
    dry_run: bool = True,
) -> WriteResult:
    """Write a static-page summary to a Markdown file for manual paste into Webflow Designer.

    The user pastes the Markdown into the Rich Text element below the hero on the
    page. This avoids the unverified Designer-API endpoint risk (audit-086 H-1).

    Returns a WriteResult mirroring the CMS-write shape so the orchestrator can
    treat both paths uniformly.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    parsed = urllib.parse.urlparse(page_url)
    slug = parsed.path.strip("/").replace("/", "-") or "home"
    # Path-traversal safety: reject any slug containing ".." or null bytes
    # after the strip/replace. Defense-in-depth — urlparse already strips host.
    if ".." in slug or "\x00" in slug:
        return WriteResult(
            dry_run=dry_run,
            success=False,
            method="WRITE_FILE",
            url=page_url,
            payload={"slug": slug},
            error=f"unsafe slug derived from URL: {slug!r}",
        )
    out_path = out_dir / f"{slug}.summary.md"
    if dry_run:
        return WriteResult(
            dry_run=True,
            success=True,
            method="WRITE_FILE",
            url=page_url,
            payload={"path": str(out_path), "bytes": len(summary_markdown)},
            response={"_dry_run": True, "would_write": str(out_path)},
        )
    # Atomic write via temp + rename.
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(out_dir), prefix=".tmp-", suffix=".md")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(summary_markdown)
        os.replace(tmp_path, out_path)
        return WriteResult(
            dry_run=False,
            success=True,
            method="WRITE_FILE",
            url=page_url,
            payload={"path": str(out_path), "bytes": len(summary_markdown)},
            response={"written": str(out_path)},
        )
    except OSError as e:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return WriteResult(
            dry_run=False,
            success=False,
            method="WRITE_FILE",
            url=page_url,
            payload={"path": str(out_path)},
            error=str(e),
        )
