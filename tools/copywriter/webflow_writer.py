"""Write improved copy back to Webflow — with a prior-value backup + audit, dry-run safe.

CMS path: backup the prior field value -> render Markdown to RichText HTML -> render-guard
(refuse a literal '](' that means the MD->HTML conversion failed) -> staged patch_fields
via the shared core.webflow.CmsClient -> audit log. Static-page path: emit a reviewed
before/after Markdown doc for assisted Designer-MCP deploy / manual paste (the Data API
can't write a static page's primary-locale content). Live writes need explicit approval;
dry_run is the default and performs NO live read or write.
"""
from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path
from typing import Optional

from tools.copywriter import config
from tools.copywriter.brief import CopyResult
from tools.core.content.structure import summary_markdown_to_html
from tools.core.webflow.cms import CmsClient, WriteResult


def _run_dir(run_dir: Optional[str | Path]) -> Path:
    d = Path(run_dir) if run_dir else Path(config.RUN_DIR) / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_cms_field(
    collection_id: str,
    item_id: str,
    field_slug: str,
    result: CopyResult,
    *,
    dry_run: bool = True,
    token_env: str = "WEBFLOW_API_TOKEN",
    run_dir: Optional[str | Path] = None,
) -> dict:
    """Backup `result.before` (the prior field value) -> render -> staged PATCH -> audit.
    Returns {backup, write: WriteResult, run_dir}. dry_run does no live write."""
    rd = _run_dir(run_dir)
    (rd / "backup.json").write_text(
        json.dumps(
            {"collection_id": collection_id, "item_id": item_id, "field_slug": field_slug,
             "prior_value": result.before, "locale": result.locale},
            ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    html = summary_markdown_to_html(result.text)
    if "](" in html:  # render guard: a literal Markdown link survived => conversion bug
        return {"backup": str(rd / "backup.json"),
                "write": WriteResult(dry_run=dry_run, success=False, method="PATCH", url="",
                                     error="render guard: literal '](' in rendered HTML"),
                "run_dir": str(rd)}
    client = CmsClient(dry_run=dry_run, token_env=token_env)
    write = client.patch_fields(collection_id, item_id, {field_slug: html})
    (rd / "audit.json").write_text(
        json.dumps(
            {"collection_id": collection_id, "item_id": item_id, "field_slug": field_slug,
             "dry_run": dry_run, "write_success": write.success, "qa_ok": result.ok,
             "qa_flags": result.qa_flags, "prompt_version": config.COPYWRITER_PROMPT_VERSION},
            ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"backup": str(rd / "backup.json"), "write": write, "run_dir": str(rd)}


def write_static_doc(url: str, result: CopyResult, *, out_dir: Optional[str | Path] = None) -> dict:
    """Emit a reviewed before/after Markdown doc for a static page (assisted deploy/paste)."""
    slug = urllib.parse.urlparse(url).path.strip("/").replace("/", "-") or "home"
    if ".." in slug or "\x00" in slug:
        return {"doc": None, "error": f"unsafe slug from URL: {slug!r}"}
    d = Path(out_dir) if out_dir else Path(config.STATIC_DOC_DIR)
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{slug}.copy.md"
    doc = (
        f"<!-- copywriter: {url} | locale={result.locale} | qa_ok={result.ok} | "
        f"flags={result.qa_flags} -->\n\n## BEFORE\n\n{result.before}\n\n## AFTER\n\n{result.text}\n"
    )
    out.write_text(doc, encoding="utf-8")
    return {"doc": str(out), "ok": result.ok}
