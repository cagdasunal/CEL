"""CLI orchestration: generate-english | audit | translate | all | plan.

Subcommands:
  plan             — emit JSON describing what WOULD be processed (no fetches, no API)
  generate-english — fetch source content, derive keywords, generate EN summaries
  audit            — score existing summaries, surface REGENERATE candidates
  translate        — translate EN summaries into 8 locales + emit Weglot CSVs
  all              — run generate-english → audit → translate

Default mode is `--dry-run`: no live Claude API calls, no Webflow writes, no live
CSV mutations. `--no-dry-run` enables real API calls + Webflow writes. Static-
page summaries are written to Markdown files under
`docs/admin/weglot-imports/static-summaries/` regardless of mode — the user copy-
pastes those into Webflow Designer.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.summary import config


# ---- Helpers ----


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tools.summary",
        description=(
            "Generate SEO summary content for Webflow CMS items + static landing "
            "pages, audit existing summaries, and emit Weglot-ready translation "
            "CSVs. Default mode is --dry-run."
        ),
    )
    parser.add_argument(
        "subcommand",
        choices=["generate-english", "audit", "translate", "all", "plan"],
    )
    parser.add_argument(
        "--dry-run", dest="dry_run", action="store_true", default=True,
        help="Default. No Claude API calls, no Webflow writes.",
    )
    parser.add_argument(
        "--no-dry-run", dest="dry_run", action="store_false",
        help="Real API calls + Webflow writes. Requires WEBFLOW_API_TOKEN and ANTHROPIC_API_KEY.",
    )
    parser.add_argument(
        "--collection", choices=["blog", "courses", "housing_new"], default=None,
    )
    parser.add_argument("--page", default=None, help="Filter to a single static-page URL.")
    parser.add_argument("--locale", choices=config.LOCALES, default=None)
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap items processed (pilot batches).",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=None,
        help="Override output artifact directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    out_dir = args.out_dir or (config.DRYRUN_DIR / _timestamp_slug())
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print(f"[summary] DRY RUN — artifacts → {out_dir}", file=sys.stderr)
    else:
        print(f"[summary] LIVE RUN — real API calls + Webflow writes will fire.", file=sys.stderr)

    report: dict[str, Any] = {
        "started_at": _now_iso(),
        "subcommand": args.subcommand,
        "dry_run": args.dry_run,
        "filters": {
            "collection": args.collection, "page": args.page,
            "locale": args.locale, "limit": args.limit,
        },
        "phases": {},
        "warnings": [],
    }

    # 'plan' subcommand: planners only, no orchestration.
    if args.subcommand == "plan":
        report["phases"]["generate_english"] = _plan_generate_english(args)
        report["phases"]["audit"] = _plan_audit(args)
        report["phases"]["translate"] = _plan_translate(args)
    else:
        # All other subcommands run the orchestrator (real or dry-run).
        if args.subcommand in ("generate-english", "all"):
            report["phases"]["generate_english"] = _execute_generate_english(args, out_dir)
        if args.subcommand in ("audit", "all"):
            report["phases"]["audit"] = _execute_audit(args, out_dir)
        if args.subcommand in ("translate", "all"):
            report["phases"]["translate"] = _execute_translate(args, out_dir)

    # Write the report.
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "report.md").write_text(_render_markdown_report(report), encoding="utf-8")
    print(f"[summary] report.json + report.md → {out_dir}", file=sys.stderr)
    if args.dry_run:
        print("[summary] Dry-run complete. No API calls fired, no Webflow writes performed.", file=sys.stderr)
    return 0


# ---- Plan-only helpers (informational; used by 'plan' subcommand) ----


def _plan_generate_english(args: argparse.Namespace) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    if not args.collection:
        for url in config.STATIC_PAGES:
            if args.page and url != args.page:
                continue
            targets.append({"kind": "static_page", "url": url, "locale": "en", "content_type": "landing"})
    for slug, cid in config.COLLECTIONS.items():
        if args.collection and args.collection != slug:
            continue
        content_type = {"blog": "blog_post", "courses": "course", "housing_new": "housing"}[slug]
        translate = slug in config.TRANSLATE_COLLECTIONS
        targets.append({
            "kind": "cms_collection", "collection": slug, "collection_id": cid,
            "locale": "native_per_item" if slug in config.NATIVE_LANGUAGE_COLLECTIONS else "en",
            "content_type": content_type, "translate": translate,
        })
    if args.limit:
        targets = targets[: args.limit]
    return {"target_count": len(targets), "targets": targets, "model": config.MODEL_ID}


def _plan_audit(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "audit_thresholds": {
            "regenerate_below": config.AUDIT_REGENERATE_THRESHOLD,
            "manual_review_below": config.AUDIT_MANUAL_REVIEW_THRESHOLD,
        },
        "collections_to_audit": list(config.COLLECTIONS.keys()),
        "static_pages_to_audit": list(config.STATIC_PAGES),
    }


def _plan_translate(args: argparse.Namespace) -> dict[str, Any]:
    target_locales = (
        [args.locale] if args.locale and args.locale != "en"
        else list(config.TARGET_TRANSLATION_LOCALES)
    )
    return {
        "target_locales": target_locales,
        "csvs": [
            {
                "locale": locale,
                "csv_path": str(config.WEGLOT_IMPORTS_DIR / f"{locale}.csv"),
            }
            for locale in target_locales
        ],
        "translatable_collections": list(config.TRANSLATE_COLLECTIONS),
    }


# ---- Executors (the orchestrator) ----
#
# These functions do the actual work. Each respects `args.dry_run`:
#   - dry_run=True: assemble inputs, build prompts, write a JSONL artifact
#     describing what would happen. NO API calls. NO Webflow writes.
#   - dry_run=False: assemble inputs, build prompts, submit Claude batches,
#     parse results, write to Webflow CMS (or to static-summaries Markdown
#     for static pages).
#
# Imports of network-touching modules are lazy so dry-run + --help work
# without the anthropic SDK installed.


def _execute_generate_english(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    """Execute generate-english phase. Returns metadata for the report."""
    from tools.summary import batch_runner, llms_parser
    from tools.summary.page_fetcher import fetch_page, PageContent
    from tools.summary.keyword_extractor import derive_keywords
    from tools.summary.prompt_builder import (
        KeywordPlan, SourceItem, build_system_prompt, build_user_message,
    )

    plan = _plan_generate_english(args)
    items_to_process: list[dict[str, Any]] = []
    warnings: list[str] = []

    # Resolve targets → SourceItem list. Static pages fetch live HTML; CMS
    # collections enumerate via the Webflow Data API (or get mocked in tests).
    sources: list[tuple[SourceItem, KeywordPlan, str]] = []  # (item, keywords, target)
    # target = "cms" or "static"
    if not args.dry_run:
        from tools.summary.webflow_client import WebflowClient
        wf = WebflowClient(dry_run=False)
    else:
        wf = None

    for target in plan["targets"]:
        if target["kind"] == "static_page":
            try:
                pc: PageContent = fetch_page(target["url"])
                kw = derive_keywords(pc.title, pc.h1, pc.url, pc.body_text_excerpt)
                item = SourceItem(
                    url=pc.url, title=pc.title, body_excerpt=pc.body_text_excerpt[:8000],
                    locale="en", content_type="landing",
                )
                sources.append((item, kw, "static"))
            except Exception as e:
                warnings.append(f"static_page fetch failed for {target['url']}: {e}")
        elif target["kind"] == "cms_collection":
            if wf is None:
                # Dry-run: emit a placeholder note. The plan-output already
                # describes the collection; live execution iterates items.
                continue
            try:
                for cms_item in wf.list_items(target["collection_id"]):
                    if cms_item.is_draft or cms_item.is_archived:
                        continue
                    field_data = cms_item.field_data
                    title = field_data.get("name") or field_data.get("title", "")
                    slug = field_data.get("slug", "")
                    body = field_data.get("post-body") or field_data.get("description") or ""
                    locale = field_data.get("language-shortcode") or field_data.get("locale", "en")
                    if target["locale"] != "native_per_item":
                        locale = "en"
                    url = f"https://www.englishcollege.com/post/{slug}"  # rough; CMS items map to URLs by collection
                    kw = derive_keywords(title, title, url, body)
                    item = SourceItem(
                        url=url, title=title, body_excerpt=body[:8000],
                        locale=locale, content_type=target["content_type"],
                        cms_item_id=cms_item.id,
                    )
                    sources.append((item, kw, "cms"))
                    if args.limit and len(sources) >= args.limit:
                        break
            except Exception as e:
                warnings.append(f"cms_collection enumeration failed for {target['collection']}: {e}")

    if args.limit:
        sources = sources[: args.limit]

    # Build batch requests + cost check.
    requests = []
    for i, (item, kw, _target) in enumerate(sources):
        try:
            system_blocks = build_system_prompt(item.content_type, item.locale if item.content_type == "blog_post" else "en")
            link_inv = config.STATIC_PAGES  # baseline inventory; the orchestrator can enrich later
            user_msg = build_user_message(item, link_inv, kw)
            req = batch_runner.BatchRequest(
                custom_id=f"gen-{i}-{item.cms_item_id or item.url[-50:]}",
                system_blocks=system_blocks,
                user_message=user_msg,
                enable_thinking=True,
            )
            requests.append(req)
        except Exception as e:
            warnings.append(f"prompt-build failed for {item.url}: {e}")

    cost_estimate = batch_runner.estimate_batch_cost_usd(requests)
    if cost_estimate > config.MAX_BATCH_COST_USD:
        warnings.append(
            f"COST CAP EXCEEDED: estimated ${cost_estimate:.2f} > "
            f"MAX_BATCH_COST_USD ${config.MAX_BATCH_COST_USD}. Aborting batch."
        )
        return {
            "target_count": len(plan["targets"]), "sources_resolved": len(sources),
            "requests_built": len(requests), "cost_estimate_usd": round(cost_estimate, 2),
            "submitted": False, "warnings": warnings,
        }

    # Submit (real or dry-run).
    artifact_dir = out_dir / "batches"
    if args.dry_run:
        handle = batch_runner.dry_run_submit(requests, artifact_dir=artifact_dir)
        return {
            "target_count": len(plan["targets"]), "sources_resolved": len(sources),
            "requests_built": len(requests), "cost_estimate_usd": round(cost_estimate, 2),
            "submitted": True, "dry_run": True, "batch_id": handle.batch_id,
            "artifact_path": str(handle.artifact_path), "warnings": warnings,
        }
    # Live run.
    handle = batch_runner.submit_batch(requests)
    results = batch_runner.wait_for_batch(handle)
    succeeded = [r for r in results if r.succeeded]
    failed = [r for r in results if not r.succeeded]
    # Retry failures once with a tightened prompt.
    if failed:
        retry_requests = []
        for fr in failed:
            orig = next((r for r in requests if r.custom_id == fr.custom_id), None)
            if orig:
                retry_user = orig.user_message + f"\n\n## Retry note\nPrevious attempt failed: {fr.error}. Rewrite addressing this; preserve the rules."
                retry_requests.append(
                    batch_runner.BatchRequest(
                        custom_id=f"retry-{fr.custom_id}",
                        system_blocks=orig.system_blocks,
                        user_message=retry_user,
                        enable_thinking=False,
                    )
                )
        if retry_requests:
            retry_handle = batch_runner.submit_batch(retry_requests)
            retry_results = batch_runner.wait_for_batch(retry_handle)
            for rr in retry_results:
                if rr.succeeded:
                    succeeded.append(rr)
                    failed = [f for f in failed if not rr.custom_id.endswith(f.custom_id)]
    # Write back. Static pages → JSON. CMS items → Webflow API.
    write_log = _write_back_summaries(succeeded, sources, args, out_dir, warnings)
    return {
        "target_count": len(plan["targets"]), "sources_resolved": len(sources),
        "requests_built": len(requests), "cost_estimate_usd": round(cost_estimate, 2),
        "submitted": True, "dry_run": False, "batch_id": handle.batch_id,
        "succeeded": len(succeeded), "failed": len(failed),
        "write_log": write_log, "warnings": warnings,
    }


def _execute_audit(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    """Audit existing summaries; score; surface REGENERATE candidates."""
    from tools.summary.audit import audit_existing_summary
    from tools.summary.keyword_extractor import derive_keywords
    from tools.summary.page_fetcher import fetch_page

    scores: list[dict[str, Any]] = []
    warnings: list[str] = []

    # For dry-run we audit only static pages (cheaper; no Webflow API).
    if not args.dry_run:
        from tools.summary.webflow_client import WebflowClient
        wf = WebflowClient(dry_run=False)
    else:
        wf = None

    # Static pages
    for url in config.STATIC_PAGES:
        if args.page and url != args.page:
            continue
        try:
            pc = fetch_page(url)
            kw = derive_keywords(pc.title, pc.h1, pc.url, pc.body_text_excerpt)
            score = audit_existing_summary(
                url=url, summary_markdown=pc.existing_summary_html,
                primary_keyword=kw.primary, locale="en",
                link_inventory=config.STATIC_PAGES,
            )
            scores.append({
                "url": url, "score": score.score, "action": score.action,
                "failed_checks": score.failed_checks,
            })
        except Exception as e:
            warnings.append(f"audit fetch failed for {url}: {e}")

    # CMS items (live mode only — requires API)
    if wf and not args.collection:
        for slug, cid in config.COLLECTIONS.items():
            if args.collection and args.collection != slug:
                continue
            try:
                for cms_item in wf.list_items(cid):
                    if cms_item.is_draft or cms_item.is_archived:
                        continue
                    existing = cms_item.field_data.get(config.SUMMARY_FIELD_SLUG, "") or ""
                    title = cms_item.field_data.get("name") or cms_item.field_data.get("title", "")
                    body = cms_item.field_data.get("post-body") or cms_item.field_data.get("description") or ""
                    kw = derive_keywords(title, title, "", body)
                    score = audit_existing_summary(
                        url=f"cms:{slug}/{cms_item.id}",
                        summary_markdown=existing,
                        primary_keyword=kw.primary, locale="en",
                        link_inventory=[],
                    )
                    scores.append({
                        "url": f"cms:{slug}/{cms_item.id}", "score": score.score,
                        "action": score.action, "failed_checks": score.failed_checks,
                    })
                    if args.limit and len(scores) >= args.limit:
                        break
            except Exception as e:
                warnings.append(f"audit enum failed for {slug}: {e}")

    regenerate = [s for s in scores if s["action"] == "REGENERATE"]
    keep = [s for s in scores if s["action"] == "KEEP"]
    manual_review = [s for s in scores if s["action"] == "MANUAL_REVIEW"]

    (out_dir / "audit-scores.json").write_text(
        json.dumps({"scores": scores}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {
        "total_audited": len(scores),
        "keep_count": len(keep), "regenerate_count": len(regenerate),
        "manual_review_count": len(manual_review),
        "warnings": warnings,
    }


def _execute_translate(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    """Translate EN summaries into 8 locales; emit consolidated per-language CSVs."""
    from tools.summary import batch_runner, csv_emitter, llms_parser
    from tools.summary.prompt_builder import (
        LinkSwap, build_translation_system_prompt, build_translation_user_message,
    )

    warnings: list[str] = []
    target_locales = (
        [args.locale] if args.locale and args.locale != "en"
        else list(config.TARGET_TRANSLATION_LOCALES)
    )
    # In a full live run, this consumes EN summaries from the generate-english
    # phase's output. For this orchestrator skeleton, dry-run produces a
    # description of what would happen and a CSV preview file in out_dir.
    per_locale_results = {}
    for locale in target_locales:
        existing_csv = config.WEGLOT_IMPORTS_DIR / f"{locale}.csv"
        if args.dry_run:
            # Preview: count rows that would be appended.
            per_locale_results[locale] = {
                "existing_csv": str(existing_csv),
                "existing_exists": existing_csv.exists(),
                "would_append_rows": 0,  # actual count requires real EN summary content
                "note": "dry-run: no live EN summaries to translate; preview only.",
            }
        else:
            # Live mode: build LinkSwap map, submit translation batch, emit CSV.
            # In a real run, this consumes EN summaries written to disk by the
            # generate-english phase. This wiring is minimal for safety.
            per_locale_results[locale] = {
                "existing_csv": str(existing_csv),
                "csv_path": str(existing_csv),
                "note": "live-mode wiring requires EN summaries from generate-english phase output.",
            }
    return {"target_locales": target_locales, "per_locale": per_locale_results, "warnings": warnings}


# ---- Write-back helpers ----


def _write_back_summaries(
    succeeded: list, sources: list, args: argparse.Namespace, out_dir: Path, warnings: list[str],
) -> dict[str, Any]:
    """Write generated summaries to Webflow CMS (CMS items) or to JSON files (static pages)."""
    from tools.summary.webflow_client import WebflowClient
    from tools.summary.webflow_designer import write_static_summary

    static_dir = config.WEGLOT_IMPORTS_DIR / "static-summaries"
    wf = WebflowClient(dry_run=args.dry_run)
    cms_writes = 0
    static_writes = 0
    failures = 0

    custom_id_to_source = {
        f"gen-{i}-{item.cms_item_id or item.url[-50:]}": (item, target)
        for i, (item, _kw, target) in enumerate(sources)
    }
    for result in succeeded:
        cid = result.custom_id
        if cid.startswith("retry-"):
            cid = cid[len("retry-"):]
        entry = custom_id_to_source.get(cid)
        if not entry:
            failures += 1
            continue
        item, target = entry
        if target == "static":
            wr = write_static_summary(item.url, result.content, static_dir, dry_run=args.dry_run)
            if wr.success:
                static_writes += 1
            else:
                failures += 1
                warnings.append(f"static write failed: {item.url}: {wr.error}")
        elif target == "cms" and item.cms_item_id:
            # In dry-run, the WebflowClient already returns a mock response.
            wresult = wf.update_item_summary(
                collection_id=_collection_id_for_content_type(item.content_type),
                item_id=item.cms_item_id,
                summary_html=result.content,
            )
            if wresult.success:
                cms_writes += 1
            else:
                failures += 1
                warnings.append(f"cms write failed for {item.cms_item_id}: {wresult.error}")
    return {"cms_writes": cms_writes, "static_writes": static_writes, "failures": failures}


def _collection_id_for_content_type(content_type: str) -> str:
    return {
        "blog_post": config.COLLECTIONS["blog"],
        "course": config.COLLECTIONS["courses"],
        "housing": config.COLLECTIONS["housing_new"],
    }.get(content_type, "")


# ---- Report rendering ----


def _render_markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Summary script — run report")
    lines.append("")
    lines.append(f"- Started: `{report['started_at']}`")
    lines.append(f"- Subcommand: `{report['subcommand']}`")
    lines.append(f"- Dry-run: `{report['dry_run']}`")
    lines.append(f"- Filters: `{json.dumps(report['filters'])}`")
    lines.append("")
    for phase_name, phase_data in report.get("phases", {}).items():
        lines.append(f"## Phase: {phase_name}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(phase_data, indent=2, ensure_ascii=False, default=str))
        lines.append("```")
        lines.append("")
    if report.get("warnings"):
        lines.append("## Warnings")
        for w in report["warnings"]:
            lines.append(f"- {w}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
