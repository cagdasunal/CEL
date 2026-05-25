"""copywriter CLI — `python3 -m tools.copywriter <improve|plan> --brief <path>`.

improve : load a brief -> resolve the current copy (brief.existing_copy, or fetch a
          static page) -> improve_copy (dry-run by default; --no-dry-run calls Gemini) ->
          write a before/after preview + result.json; with --write + a target, perform the
          staged CMS PATCH (backup + audit) or emit a static-page doc.
plan    : dry-run report — QA the current copy, show the target; no API call.

EN-source -> multi-locale translation is a SEPARATE step on the approved English via the
existing `tools.translator` (not wired into this CLI yet). `improve --locale <X>` is
locale-native and never translates.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
import urllib.parse
from pathlib import Path

from tools.copywriter import config, webflow_writer
from tools.copywriter.brief import CopyRequest, CopyResult, load_brief
from tools.copywriter.engine import improve_copy


def _is_allowlisted_url(url: str) -> bool:
    """Only fetch over https from englishcollege.com (defensive — the target URL is
    operator-supplied via the brief; restrict the fetch surface to the known domain)."""
    if not isinstance(url, str):
        return False
    p = urllib.parse.urlparse(url)
    host = (p.hostname or "").lower()
    return p.scheme == "https" and (host == "englishcollege.com" or host.endswith(".englishcollege.com"))


def _resolve_before(req: CopyRequest) -> CopyRequest:
    """Fill existing_copy: brief value wins; else fetch a static-page target's body text."""
    if req.existing_copy:
        return req
    tgt = req.target or {}
    if tgt.get("kind") == "static_page" and tgt.get("url"):
        url = tgt["url"]
        if not _is_allowlisted_url(url):
            print(f"[copywriter] refusing to fetch non-allowlisted URL "
                  f"(https + *.englishcollege.com only): {url}", file=sys.stderr)
            return req
        from tools.core.web.page_fetcher import fetch_page
        try:
            return dataclasses.replace(req, existing_copy=fetch_page(url).body_text_excerpt)
        except Exception as e:  # noqa: BLE001 — fetch failure is non-fatal; proceed with empty
            print(f"[copywriter] could not fetch {url}: {e}", file=sys.stderr)
    return req


def _write_run(result: CopyResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps({"locale": result.locale, "ok": result.ok, "qa_flags": result.qa_flags,
                    "before": result.before, "text": result.text}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    (out_dir / "preview.md").write_text(
        f"# Copywriter preview ({result.locale}) — QA ok={result.ok}\n\n"
        f"flags: {result.qa_flags}\n\n## BEFORE\n\n{result.before}\n\n## AFTER\n\n{result.text}\n",
        encoding="utf-8")


def _out_dir(args) -> Path:
    return Path(args.out_dir) if args.out_dir else Path(config.RUN_DIR) / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _cmd_improve(args) -> int:
    req = load_brief(args.brief)
    if args.locale:
        req = dataclasses.replace(req, locale=args.locale)
    req = _resolve_before(req)
    dry_run = not args.no_dry_run
    result = improve_copy(req, dry_run=dry_run)
    out_dir = _out_dir(args)
    _write_run(result, out_dir)
    print(f"[copywriter] locale={result.locale} qa_ok={result.ok} flags={result.qa_flags}", file=sys.stderr)
    print(f"[copywriter] preview: {out_dir / 'preview.md'}", file=sys.stderr)
    if args.write:
        tgt = req.target or {}
        if tgt.get("kind") == "cms_item" and tgt.get("cms_item_id") and tgt.get("field_slug"):
            cid = config.COLLECTIONS.get(tgt.get("collection", ""), tgt.get("collection"))
            res = webflow_writer.write_cms_field(
                cid, tgt["cms_item_id"], tgt["field_slug"], result, dry_run=dry_run, run_dir=out_dir)
            print(f"[copywriter] CMS write: success={res['write'].success} dry_run={res['write'].dry_run} backup={res['backup']}", file=sys.stderr)
        elif tgt.get("kind") == "static_page" and tgt.get("url"):
            res = webflow_writer.write_static_doc(tgt["url"], result, out_dir=out_dir)
            print(f"[copywriter] static doc: {res.get('doc')}", file=sys.stderr)
    return 0 if (result.ok or dry_run) else 1


def _cmd_plan(args) -> int:
    from tools.copywriter import qa
    req = load_brief(args.brief)
    if args.locale:
        req = dataclasses.replace(req, locale=args.locale)
    req = _resolve_before(req)
    report = qa.copywriter_qa(req.existing_copy, req.locale, must_keep_facts=req.must_keep_facts)
    print(f"[copywriter] plan: locale={req.locale} target={req.target} current-copy QA: {report.summary()}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="tools.copywriter", description="Multilingual brief-driven copy improvement (Gemini 3.1 Pro).")
    sub = p.add_subparsers(dest="subcommand", required=True)
    pi = sub.add_parser("improve", help="Improve copy from a brief (dry-run by default).")
    pi.add_argument("--brief", required=True)
    pi.add_argument("--locale")
    pi.add_argument("--no-dry-run", action="store_true", help="Call Gemini for real (default: dry-run).")
    pi.add_argument("--write", action="store_true", help="Also write to Webflow / emit a static doc (needs a target).")
    pi.add_argument("--out-dir")
    pi.set_defaults(func=_cmd_improve)
    pp = sub.add_parser("plan", help="Dry-run report — QA the current copy; no API call.")
    pp.add_argument("--brief", required=True)
    pp.add_argument("--locale")
    pp.set_defaults(func=_cmd_plan)
    args = p.parse_args(argv)
    return args.func(args)
