"""CLI orchestration: generate-english | audit | translate | all | plan.

Subcommands:
  plan             — emit JSON describing what WOULD be processed (no fetches, no API)
  generate-english — fetch source content, derive keywords, generate EN summaries
  audit            — score existing summaries, surface REGENERATE candidates
  translate        — translate EN summaries into 8 locales + emit Weglot CSVs
  all              — run generate-english → audit → translate

Default mode is `--dry-run`: no live Gemini API calls, no Webflow writes, no live
CSV mutations. `--no-dry-run` enables real API calls + Webflow writes. Static-
page summaries are written to Markdown files under
`docs/admin/weglot-imports/static-summaries/` regardless of mode — the user copy-
pastes those into Webflow Designer.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from tools.summary import config

if TYPE_CHECKING:
    # Type-only import — llms_parser is pure-stdlib but kept lazy at runtime
    # to mirror the existing per-phase import pattern (cli.py:200, :525).
    from tools.summary.llms_parser import LlmsIndex


# ---- Helpers ----


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


_EM_DASH_SUB_RE = re.compile(r"\s*[—–]\s*")
# www rule (2026-05-22): full URLs must use www.englishcollege.com, never the bare apex.
# Rewrites http(s)://englishcollege.com → https://www.englishcollege.com. Does NOT touch
# www. (already correct) or any other subdomain (cel., etc.) — the `\.com` is anchored so
# only the bare apex host matches.
_BARE_DOMAIN_RE = re.compile(r"https?://englishcollege\.com", re.IGNORECASE)


def _sanitize_summary(text: str) -> str:
    """Deterministically remove the banned em/en-dash AI-tell from a generated summary.

    The model violates the no-em-dash prompt rule ~1 in 6 (confirmed on a live blog
    pilot), which would demote an otherwise-good summary on the CRITICAL `no_em_dashes`
    check. The prompt's own prescribed alternative is a comma, so we substitute one and
    tidy any doubled comma/space. Applied before QA + write-back so shipped copy is clean
    and a recoverable tell doesn't cost a generation. NOT applied to anything else —
    genuine quality failures still demote.

    tracker-098: ALSO normalizes raw inline HTML the model sometimes emits. Flash in
    particular returns `<a href>` / `<strong>` / `<em>` tags despite the Markdown-only
    rule. Left as-is they get HTML-escaped on RichText write-back into literal
    `&lt;a&gt;` (broken links on the page) AND are invisible to QA's Markdown link
    checks (so `links_locale_matched` / `link_density` pass vacuously on 0 detected
    links). Converting them back to Markdown here — before QA and before write-back —
    makes the Markdown→HTML converter emit real `<a>`/`<strong>`/`<em>` and lets QA see
    and validate the links.
    """
    if not text:
        return text
    # Raw inline HTML the model emitted → Markdown (so QA + the converter handle it).
    text = re.sub(
        r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        r'[\2](\1)', text, flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r'</?(?:strong|b)>', '**', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:em|i)>', '*', text, flags=re.IGNORECASE)
    # www rule (2026-05-22): normalize any bare apex link to www. before QA + write-back.
    text = _BARE_DOMAIN_RE.sub("https://www.englishcollege.com", text)
    out = _EM_DASH_SUB_RE.sub(", ", text)
    out = re.sub(r",\s*,", ", ", out)   # collapse ", ," from a dash next to existing punctuation
    out = re.sub(r"\s+,", ",", out)      # no space before a comma
    return out


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_EXISTING_SUMMARY_SEED_CAP = 1500  # chars; keeps the reuse seed within a sane prompt window


def _existing_summary_seed(*parts: str) -> str:
    """tracker-098 pass 2: build the reuse seed from an item's CURRENT summary fields.

    Each `part` is an existing field value (RichText HTML or plain text) — typically the
    CMS Content (`summary`) value, optionally followed by the Paragraphs
    (`summary---paragraphs`) value. HTML tags are stripped, whitespace collapsed, the
    non-empty parts joined with a blank line, and the result capped at
    `_EXISTING_SUMMARY_SEED_CAP` chars so generation expands what exists rather than
    starting from a blank page. Returns "" when no part carries content.
    """
    cleaned: list[str] = []
    for part in parts:
        if not part:
            continue
        text = re.sub(r"\s+", " ", _HTML_TAG_RE.sub(" ", part)).strip()
        if text:
            cleaned.append(text)
    seed = "\n\n".join(cleaned).strip()
    return seed[:_EXISTING_SUMMARY_SEED_CAP]


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
        choices=[
            "generate-english", "audit", "translate", "translate-meta", "all", "plan",
            # tracker-097: orphaned-batch recovery (RC5). A submitted Gemini batch keeps
            # billing after its GHA run is cancelled; these stop / reclaim it by id.
            "cancel-batch", "retrieve-batch",
            # 2026-05-22: insert internal links into existing under-linked blog summaries
            # (Flash, link-only — does NOT regenerate the prose).
            "link-blogs",
        ],
    )
    parser.add_argument(
        "--dry-run", dest="dry_run", action="store_true", default=True,
        help="Default. No Gemini API calls, no Webflow writes.",
    )
    parser.add_argument(
        "--no-dry-run", dest="dry_run", action="store_false",
        help="Real API calls + Webflow writes. Requires WEBFLOW_API_TOKEN and GEMINI_API_KEY.",
    )
    parser.add_argument(
        "--collection", choices=["blog", "courses", "housing_new"], default=None,
    )
    parser.add_argument("--page", default=None, help="Filter to a single static-page URL.")
    parser.add_argument(
        "--exclude-blog", dest="exclude_blog", action="store_true", default=False,
        help=(
            "Skip the blog collection (blog keeps its single-block summary; tracker-096 "
            "'except Blog Posts'). Lets static + courses + housing run in one pass without "
            "regenerating blog."
        ),
    )
    parser.add_argument("--locale", choices=config.LOCALES, default=None)
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap items processed (pilot batches).",
    )
    parser.add_argument(
        "--force", action="store_true", default=False,
        help=(
            "generate-english only — regenerate every item even if its source "
            "content is unchanged since the last successful run (bypasses the "
            "summary-state idempotency skip)."
        ),
    )
    parser.add_argument(
        "--sync", action="store_true", default=False,
        help=(
            "generate-english only — use synchronous Gemini generateContent calls "
            "(instant, no Batch API ≤24h SLA) instead of the Batch API. Higher "
            "per-call cost; intended for fast testing + small runs. Use the default "
            "(Batch) for the full catalog."
        ),
    )
    parser.add_argument(
        "--confirm-cost", dest="confirm_cost", action="store_true", default=False,
        help=(
            "generate-english only — authorize a LIVE run whose projected cost exceeds "
            "COST_CONFIRM_THRESHOLD_USD. Without it, such a run prints the projection and "
            "refuses to submit (pilot-first). Tiny pilots (under the threshold) don't need it."
        ),
    )
    parser.add_argument(
        "--batch-id", dest="batch_id", default=None,
        help="cancel-batch / retrieve-batch — the Gemini batch resource name to act on.",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=None,
        help="Override output artifact directory.",
    )
    parser.add_argument(
        "--from-run", type=Path, default=None,
        help=(
            "Translate / link-blogs phases — directory containing en-summaries.json from "
            "a prior generate-english run. Defaults to <out-dir>/en-summaries.json."
        ),
    )
    parser.add_argument(
        "--max-existing-links", dest="max_existing_links", type=int, default=0,
        help=(
            "link-blogs only — process blog summaries that currently have AT MOST this "
            "many internal links (default 0 = only the zero-link blogs). Raise to also "
            "top up thinly-linked posts."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    out_dir = args.out_dir or (config.DRYRUN_DIR / _timestamp_slug())
    out_dir.mkdir(parents=True, exist_ok=True)

    # tracker-097: orphaned-batch recovery short-circuits the report pipeline.
    if args.subcommand in ("cancel-batch", "retrieve-batch"):
        return _execute_batch_recovery(args, out_dir)

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
        if args.subcommand in ("translate-meta", "all"):
            report["phases"]["translate_meta"] = _execute_translate_meta(args, out_dir)
        if args.subcommand == "link-blogs":
            report["phases"]["link_blogs"] = _execute_link_blogs(args, out_dir)

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
            targets.append({
                "kind": "static_page", "url": url, "locale": "en", "content_type": "landing",
                "model": config.model_for_content_type("landing"),
            })
    for slug, cid in config.COLLECTIONS.items():
        if args.collection and args.collection != slug:
            continue
        if getattr(args, "exclude_blog", False) and slug == "blog":
            continue
        content_type = {"blog": "blog_post", "courses": "course", "housing_new": "housing"}[slug]
        translate = slug in config.TRANSLATE_COLLECTIONS
        targets.append({
            "kind": "cms_collection", "collection": slug, "collection_id": cid,
            "locale": "native_per_item" if slug in config.NATIVE_LANGUAGE_COLLECTIONS else "en",
            "content_type": content_type, "translate": translate,
            # tracker-097: show the tiered model so `plan` reveals blog → Flash.
            "model": config.model_for_content_type(content_type),
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


# ---- Orphaned-batch recovery (tracker-097 RC5) ----


def _execute_batch_recovery(args: argparse.Namespace, out_dir: Path) -> int:
    """Cancel or retrieve a Gemini batch by id.

    A submitted Gemini batch keeps processing + billing even after the GitHub
    Actions run that launched it is cancelled. `cancel-batch` stops it;
    `retrieve-batch` fetches its results and dumps them to JSON (reclaims output
    a cancelled run would otherwise discard). The batch id resolves from
    --batch-id, else the last persisted submit (config.LAST_BATCH_FILE).
    """
    from tools.summary import batch_runner

    batch_id = args.batch_id
    if not batch_id:
        try:
            last = json.loads(config.LAST_BATCH_FILE.read_text(encoding="utf-8"))
            batch_id = last.get("batch_id")
        except (OSError, ValueError):
            batch_id = None
    if not batch_id:
        print(
            "[summary] no --batch-id and no persisted last batch "
            f"({config.LAST_BATCH_FILE}); nothing to do.",
            file=sys.stderr,
        )
        return 1

    if args.subcommand == "cancel-batch":
        state = batch_runner.cancel_batch(batch_id)
        print(f"[summary] cancel-batch {batch_id} -> state {state}", file=sys.stderr)
        return 0

    # retrieve-batch: poll to terminal state, then dump results keyed by custom_id
    # (round-tripped via response metadata, so this works cross-process).
    handle = batch_runner.BatchHandle(
        batch_id=batch_id, request_count=0, submitted_at=_now_iso(), dry_run=False,
    )
    results = batch_runner.wait_for_batch(handle, poll_interval_sec=10, timeout_sec=6 * 3600)
    dump = {
        r.custom_id: {
            "succeeded": r.succeeded, "content": r.content, "error": r.error,
            "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
            "cache_read_tokens": r.cache_read_tokens,
        }
        for r in results
    }
    out_path = out_dir / "retrieved-batch.json"
    out_path.write_text(json.dumps(dump, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[summary] retrieve-batch {batch_id} -> {len(results)} results -> {out_path}",
        file=sys.stderr,
    )
    return 0


# ---- Executors (the orchestrator) ----
#
# These functions do the actual work. Each respects `args.dry_run`:
#   - dry_run=True: assemble inputs, build prompts, write a JSONL artifact
#     describing what would happen. NO API calls. NO Webflow writes.
#   - dry_run=False: assemble inputs, build prompts, submit Gemini batches,
#     parse results, write to Webflow CMS (or to static-summaries Markdown
#     for static pages).
#
# Imports of network-touching modules are lazy so dry-run + --help work
# without the google-genai SDK installed.


def _submit_and_wait(requests: list, args: argparse.Namespace):
    """Run a batch of requests and collect results (tracker-097).

    --sync: one synchronous generate_sync over all requests (per-request model).
    Batch (default): group requests by resolved model and run one Batch job per
    model — the Batch API accepts a single model per job, so tiering (blog → Flash,
    rest → Pro) requires per-model jobs. Returns (results, primary_handle, batch_ids).
    """
    from tools.summary import batch_runner

    if args.sync:
        handle = batch_runner.BatchHandle(
            batch_id=f"sync-{_timestamp_slug()}", request_count=len(requests),
            submitted_at=_now_iso(), dry_run=False,
        )
        return batch_runner.generate_sync(requests), handle, [handle.batch_id]

    groups: dict[str, list] = {}
    order: list[str] = []
    for r in requests:
        m = r.model or config.MODEL_ID
        if m not in groups:
            groups[m] = []
            order.append(m)
        groups[m].append(r)

    results: list = []
    handles = []
    for m in order:
        h = batch_runner.submit_batch(groups[m], model=m)
        handles.append(h)
        results.extend(batch_runner.wait_for_batch(h))
    primary = handles[0] if handles else batch_runner.BatchHandle(
        batch_id="none", request_count=0, submitted_at=_now_iso(), dry_run=False,
    )
    return results, primary, [h.batch_id for h in handles]


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
    qa_scores: dict[str, float] = {}  # tracker-092 (1.2): cid → QA score; recorded in manifest + report

    # tracker-091 M-13: fetch llms.txt once for the whole phase so every item's
    # link-candidate pool can include CMS items (housing /pb/, courses, blog) —
    # not just the 12 curated STATIC_PAGES. Mirrors the translate-phase pattern
    # (cli.py _execute_translate). Dry-run skips the network; failure falls back
    # to STATIC_PAGES-only via _build_link_candidate_pool's None handling.
    llms_index = None
    if not args.dry_run:
        try:
            llms_index = llms_parser.fetch_and_parse(config.LLMS_TXT_URL)
        except Exception as e:
            warnings.append(
                f"llms.txt fetch failed; link pool falls back to STATIC_PAGES only: {e}"
            )

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
                kw = derive_keywords(pc.title, pc.h1, pc.url, pc.body_text_excerpt, locale="en")
                # tracker-098 pass 2: seed with the page's existing summary if readily
                # available (the captured #summary HTML). Best-effort — skip if absent.
                item = SourceItem(
                    url=pc.url, title=pc.title, body_excerpt=pc.body_text_excerpt[:8000],
                    locale="en", content_type="landing",
                    existing_summary_excerpt=_existing_summary_seed(pc.existing_summary_html),
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
                    locale = _resolve_item_locale(field_data, target["locale"])
                    url = _cms_item_url(target["content_type"], slug)  # per-collection prefix (M-14)
                    kw = derive_keywords(title, title, url, body, locale=locale)
                    # tracker-098 pass 2: seed generation with the item's CURRENT summary
                    # so it expands what exists instead of regenerating from scratch.
                    # Content (`summary`) first, then the Paragraphs RichText if present.
                    existing_seed = _existing_summary_seed(
                        field_data.get(config.SUMMARY_CONTENT_FIELD_SLUG, "") or "",
                        field_data.get(config.SUMMARY_PARAGRAPH_FIELD_SLUG, "") or "",
                    )
                    item = SourceItem(
                        url=url, title=title, body_excerpt=body[:8000],
                        locale=locale, content_type=target["content_type"],
                        cms_item_id=cms_item.id,
                        existing_summary_excerpt=existing_seed,
                    )
                    sources.append((item, kw, "cms"))
                    if args.limit and len(sources) >= args.limit:
                        break
            except Exception as e:
                warnings.append(f"cms_collection enumeration failed for {target['collection']}: {e}")

    if args.limit:
        sources = sources[: args.limit]

    # tracker-092 Phase 2 (2.1): idempotency — skip items whose source content is
    # unchanged since the last successful run (live mode only; --force bypasses;
    # dry-run never reads/writes state so tests stay deterministic).
    idempotency_skipped = 0
    summary_state = _load_summary_state() if not args.dry_run else {}
    if not args.dry_run and not args.force and summary_state:
        kept = []
        for (sitem, kw, tgt) in sources:
            cid_key = sitem.cms_item_id or sitem.url
            model = config.model_for_content_type(sitem.content_type)
            if summary_state.get(cid_key, {}).get("source_hash") == _source_hash(sitem.body_excerpt, cid_key, model):
                idempotency_skipped += 1
                continue
            kept.append((sitem, kw, tgt))
        if idempotency_skipped:
            warnings.append(
                f"idempotency: skipped {idempotency_skipped} unchanged item(s) "
                f"(use --force to regenerate)"
            )
        sources = kept

    # Build batch requests + cost check.
    requests = []
    for i, (item, kw, _target) in enumerate(sources):
        try:
            system_blocks = build_system_prompt(item.content_type, item.locale if item.content_type == "blog_post" else "en")
            link_inv = _build_link_candidate_pool(item.content_type, llms_index, item.locale)
            # tracker-098 pass 2: pass the item's existing summary as the reuse seed so
            # generation expands it rather than starting blank (empty string = no seed).
            user_msg = build_user_message(
                item, link_inv, kw, existing_summary_excerpt=item.existing_summary_excerpt
            )
            req = batch_runner.BatchRequest(
                custom_id=f"gen-{i}-{item.cms_item_id or item.url[-50:]}",
                system_blocks=system_blocks,
                user_message=user_msg,
                enable_thinking=True,
                # tracker-097: tier the model by content type (blog → Flash, rest → Pro).
                model=config.model_for_content_type(item.content_type),
            )
            requests.append(req)
        except Exception as e:
            warnings.append(f"prompt-build failed for {item.url}: {e}")

    if not requests:
        # tracker-092 (2.1): nothing to do — every item was skipped as unchanged
        # (or none resolved). Return cleanly instead of submitting an empty batch.
        return {
            "target_count": len(plan["targets"]), "sources_resolved": len(sources),
            "requests_built": 0, "idempotency_skipped": idempotency_skipped,
            "submitted": False, "dry_run": args.dry_run,
            "reason": "no items to process (all unchanged or none resolved)",
            "warnings": warnings,
        }

    # tracker-097: estimate at the rate tier actually billed (--sync = interactive,
    # else batch) and credit explicit caching only when it will engage this run.
    est_mode = "interactive" if args.sync else "batch"
    cache_plan = [] if (args.sync or not config.ENABLE_EXPLICIT_CACHE) else batch_runner.plan_caches(requests)
    cache_will_engage = any(e.eligible for e in cache_plan)
    cost_estimate = batch_runner.estimate_batch_cost_usd(
        requests, mode=est_mode, cached=cache_will_engage,
    )
    model_breakdown: dict[str, int] = {}
    for r in requests:
        m = r.model or config.MODEL_ID
        model_breakdown[m] = model_breakdown.get(m, 0) + 1
    cost_gate = {
        "projected_usd": round(cost_estimate, 4),
        "mode": est_mode,
        "cost_cap_usd": config.MAX_BATCH_COST_USD,
        "confirm_threshold_usd": config.COST_CONFIRM_THRESHOLD_USD,
        "caching_engaged": cache_will_engage,
        "cacheable_groups": sum(1 for e in cache_plan if e.eligible),
        "model_breakdown": model_breakdown,
        "confirm_required": False,
        "confirmed": bool(getattr(args, "confirm_cost", False)),
    }
    # Hard cost cap — abort regardless of confirmation.
    if cost_estimate > config.MAX_BATCH_COST_USD:
        warnings.append(
            f"COST CAP EXCEEDED: estimated ${cost_estimate:.2f} > "
            f"MAX_BATCH_COST_USD ${config.MAX_BATCH_COST_USD}. Aborting batch."
        )
        return {
            "target_count": len(plan["targets"]), "sources_resolved": len(sources),
            "requests_built": len(requests), "cost_estimate_usd": round(cost_estimate, 2),
            "submitted": False, "cost_gate": cost_gate, "warnings": warnings,
        }
    # tracker-097 pilot-first: a LIVE run over the confirm threshold needs --confirm-cost.
    if (not args.dry_run) and cost_estimate > config.COST_CONFIRM_THRESHOLD_USD and not getattr(args, "confirm_cost", False):
        cost_gate["confirm_required"] = True
        warnings.append(
            f"COST CONFIRM REQUIRED: projected ${cost_estimate:.2f} > "
            f"${config.COST_CONFIRM_THRESHOLD_USD:.2f}. Re-run with --confirm-cost to authorize "
            f"this paid run (pilot-first). No batch submitted."
        )
        return {
            "target_count": len(plan["targets"]), "sources_resolved": len(sources),
            "requests_built": len(requests), "cost_estimate_usd": round(cost_estimate, 2),
            "submitted": False, "cost_gate": cost_gate, "warnings": warnings,
        }

    # Helper to build the EN-summaries manifest that the translate phase consumes.
    def _write_en_summaries_manifest(succeeded_results, _sources):
        manifest: dict[str, dict] = {}
        src_by_cid: dict[str, Any] = {}
        kw_by_cid: dict[str, Any] = {}
        for i, (sitem, kw, _tgt) in enumerate(_sources):
            cid = f"gen-{i}-{sitem.cms_item_id or sitem.url[-50:]}"
            src_by_cid[cid] = sitem
            kw_by_cid[cid] = kw
        for r in succeeded_results:
            cid = r.custom_id
            if cid.startswith("retry-"):
                cid = cid[len("retry-"):]
            sitem = src_by_cid.get(cid)
            if not sitem:
                continue
            kw_plan = kw_by_cid.get(cid)
            manifest[cid] = {
                "url": sitem.url,
                "markdown": r.content,
                "content_type": sitem.content_type,
                "locale": sitem.locale,
                # tracker-090 C1: persist keyword plan so the Summaries dashboard
                # page can show keyword counts. Backward-compatible — readers
                # treat absence as "—" and don't error.
                "keyword_plan": {
                    "primary": kw_plan.primary if kw_plan else "",
                    "secondaries": list(kw_plan.secondaries) if kw_plan else [],
                    "entities": list(kw_plan.entities) if kw_plan else [],
                },
                # tracker-092 (1.2): QA score (0-100) over the stable scored set.
                # None for dry-run / unmapped entries — readers treat absence as "—".
                "qa_score": qa_scores.get(cid),
            }
        manifest_path = out_dir / "en-summaries.json"
        # Atomic write.
        import os as _os, tempfile as _tempfile
        out_dir.mkdir(parents=True, exist_ok=True)
        tfd, tpath = _tempfile.mkstemp(dir=str(out_dir), prefix=".en-summaries.", suffix=".tmp")
        try:
            with _os.fdopen(tfd, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            _os.replace(tpath, manifest_path)
        except OSError:
            try:
                _os.remove(tpath)
            except OSError:
                pass
            raise
        return manifest_path, len(manifest)

    # Submit (real or dry-run).
    artifact_dir = out_dir / "batches"
    cache_plan_report = {
        "groups": len(cache_plan),
        "cacheable_groups": sum(1 for e in cache_plan if e.eligible),
        "entries": [
            {"model": e.model, "request_count": e.request_count,
             "prefix_tokens": e.prefix_tokens, "eligible": e.eligible, "reason": e.reason}
            for e in cache_plan
        ],
    }
    if args.dry_run:
        handle = batch_runner.dry_run_submit(requests, artifact_dir=artifact_dir)
        # Dry-run: write a stub manifest so test_execute_translate_dry_run can read it.
        stub_results = [
            batch_runner.BatchResult(custom_id=r.custom_id, succeeded=True, content="")
            for r in requests
        ]
        mpath, mcount = _write_en_summaries_manifest(stub_results, sources)
        return {
            "target_count": len(plan["targets"]), "sources_resolved": len(sources),
            "requests_built": len(requests), "cost_estimate_usd": round(cost_estimate, 2),
            "submitted": True, "dry_run": True, "batch_id": handle.batch_id,
            "artifact_path": str(handle.artifact_path),
            "manifest_path": str(mpath), "manifest_entries": mcount,
            "cost_gate": cost_gate, "cache_plan": cache_plan_report,
            "warnings": warnings,
        }
    # Live run. _submit_and_wait: --sync = instant generate_sync (per-request model);
    # else group requests by model and run one Batch job per model (the Batch API
    # takes a single model per job — tracker-097 tiering).
    results, handle, batch_ids = _submit_and_wait(requests, args)
    succeeded = [r for r in results if r.succeeded]
    failed = [r for r in results if not r.succeeded]
    _first_errors = {r.custom_id: r.error for r in failed}  # tracker-092 (2.2): first-attempt errors for triage
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
                        model=orig.model,  # tracker-097: retry on the same tier
                    )
                )
        if retry_requests:
            retry_results, _retry_handle, _retry_ids = _submit_and_wait(retry_requests, args)
            for rr in retry_results:
                if rr.succeeded:
                    succeeded.append(rr)
                    # Retry IDs are exactly "retry-<orig>"; strip prefix for explicit equality
                    # match (tracker-088 F-5: previous endswith() worked but was fragile —
                    # would mis-handle two IDs that happen to be suffixes of each other).
                    # Explicit raise instead of assert so the check survives
                    # `python -O` (tracker-089 M-1).
                    if not rr.custom_id.startswith("retry-"):
                        raise ValueError(
                            f"retry result has unexpected custom_id: {rr.custom_id!r}"
                        )
                    orig_cid = rr.custom_id[len("retry-"):]
                    failed = [f for f in failed if f.custom_id != orig_cid]

    # tracker-097 follow-up: deterministically strip the banned em/en-dash AI-tell from
    # generated copy BEFORE QA + write-back. The model violates the no-em-dash rule
    # ~1 in 6 (live blog pilot), and that recoverable tell would otherwise demote an
    # otherwise-good summary on the CRITICAL no_em_dashes check.
    for r in succeeded:
        r.content = _sanitize_summary(r.content)

    # tracker-092 (1.2): QA-GATE every succeeded summary BEFORE write-back. A draft
    # that fails a CRITICAL check (em-dash / list / keyword-placement / fabricated
    # price / embedded schema) is demoted to MANUAL_REVIEW and never written to
    # production. Non-critical warnings (answer-first, anchors, near-duplicate,
    # figures, link-in-inventory) are recorded in the score/notes but do not block.
    from tools.summary.qa import qa_checks
    _src_by_cid = {
        f"gen-{i}-{s.cms_item_id or s.url[-50:]}": (s, kw)
        for i, (s, kw, _t) in enumerate(sources)
    }
    qa_passed = []
    for r in succeeded:
        base_cid = r.custom_id[len("retry-"):] if r.custom_id.startswith("retry-") else r.custom_id
        mapped = _src_by_cid.get(base_cid)
        if mapped is None:
            qa_passed.append(r)  # unmappable result → don't block on QA
            continue
        sitem, kw = mapped
        link_inv = _build_link_candidate_pool(sitem.content_type, llms_index, sitem.locale)
        rep = qa_checks(
            r.content, kw.primary if kw else "", sitem.locale, link_inv,
            excluded_path_segments=config.EXCLUDED_LINK_PATH_SEGMENTS,
            source_text=sitem.body_excerpt,
            structure=_structure_for_content_type(sitem.content_type),
        )
        qa_scores[base_cid] = round(rep.score, 1)
        if rep.passed:
            qa_passed.append(r)
        else:
            failed.append(batch_runner.BatchResult(
                custom_id=r.custom_id, succeeded=False,
                error="QA gate failed: " + "; ".join(rep.notes[:5] or ["critical check failed"]),
            ))
    qa_gate_summary = {
        "checked": len(succeeded),
        "passed": len(qa_passed),
        "demoted_to_review": len(succeeded) - len(qa_passed),
    }
    succeeded = qa_passed

    # tracker-092 (1.3): cross-page boilerplate guard (non-blocking). Flag pairs
    # of shipped summaries that are near-duplicates of EACH OTHER — templated
    # content across pages is the scaled-content-abuse footprint Google penalizes.
    from tools.summary.qa import boilerplate_pairs
    _bp_texts = {
        (r.custom_id[len("retry-"):] if r.custom_id.startswith("retry-") else r.custom_id): r.content
        for r in succeeded
    }
    for a, b, ov in boilerplate_pairs(_bp_texts):
        warnings.append(f"boilerplate risk: summaries {a} and {b} are {ov:.0%} similar (templated-content footprint)")

    # MANUAL_REVIEW state for persistent failures (closes audit-086 H-5 / tracker-087 F-4).
    # tracker-092 (2.2): enrich each item with triage metadata so an operator can
    # act without opening every URL (content_type, cms_item_id, locale, url,
    # batch_id, first-attempt error).
    def _mr_detail(f):
        base = f.custom_id[len("retry-"):] if f.custom_id.startswith("retry-") else f.custom_id
        mapped = _src_by_cid.get(base)
        sitem = mapped[0] if mapped else None
        return {
            "custom_id": f.custom_id,
            "error": f.error,
            "retry_attempted": True,
            "content_type": sitem.content_type if sitem else None,
            "cms_item_id": sitem.cms_item_id if sitem else None,
            "locale": sitem.locale if sitem else None,
            "url": sitem.url if sitem else None,
            "first_attempt_error": _first_errors.get(base),
        }

    manual_review_path = out_dir / "manual-review.json"
    manual_review_payload = {
        "custom_ids": [f.custom_id for f in failed],
        "batch_id": handle.batch_id,
        "details": [_mr_detail(f) for f in failed],
    }
    manual_review_path.write_text(
        json.dumps(manual_review_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # Write the EN-summaries manifest for the translate phase to read.
    mpath, mcount = _write_en_summaries_manifest(succeeded, sources)
    # Write back. Static pages → JSON. CMS items → Webflow API.
    write_log = _write_back_summaries(succeeded, sources, args, out_dir, warnings)

    # tracker-092 (2.1): persist idempotency state for successfully written items
    # so the next run skips them while their source content is unchanged.
    if not args.dry_run:
        for r in succeeded:
            base = r.custom_id[len("retry-"):] if r.custom_id.startswith("retry-") else r.custom_id
            mapped = _src_by_cid.get(base)
            if mapped:
                sitem = mapped[0]
                cid_key = sitem.cms_item_id or sitem.url
                summary_state[cid_key] = {
                    "source_hash": _source_hash(
                        sitem.body_excerpt, cid_key,
                        config.model_for_content_type(sitem.content_type),
                    ),
                    "generated_at": _now_iso(),
                }
        _save_summary_state(summary_state)

    # tracker-092 (2.4): observability — flag the run as degraded when a critical
    # input failed (llms.txt unreachable, or a source page/collection fetch failed),
    # so an operator knows the output may be missing links or items.
    degraded = any(
        ("llms.txt fetch failed" in w) or ("fetch failed" in w) or ("enumeration failed" in w)
        for w in warnings
    )
    return {
        "target_count": len(plan["targets"]), "sources_resolved": len(sources),
        "requests_built": len(requests), "cost_estimate_usd": round(cost_estimate, 2),
        "submitted": True, "dry_run": False, "batch_id": handle.batch_id,
        "batch_ids": batch_ids,
        "succeeded": len(succeeded), "failed": len(failed),
        "qa_gate": qa_gate_summary,
        "cost_gate": cost_gate, "cache_plan": cache_plan_report,
        "idempotency_skipped": idempotency_skipped,
        "degraded": degraded,
        "write_log": write_log,
        "manifest_path": str(mpath), "manifest_entries": mcount,
        "manual_review_path": str(manual_review_path),
        "manual_review_count": len(failed),
        "warnings": warnings,
    }


# ---- Link-insertion mode (2026-05-22): add internal links to under-linked blogs ----

_INTERNAL_MD_LINK_RE = re.compile(
    r"\]\(\s*(?:https?://(?:www\.)?englishcollege\.com|/)[^)]*\)"
)


def _count_internal_md_links(md: str) -> int:
    """Count internal (englishcollege.com / root-relative) Markdown links in `md`."""
    return len(_INTERNAL_MD_LINK_RE.findall(md or ""))


_MD_LINK_FULL_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _dedup_md_links(md: str) -> str:
    """Keep the FIRST occurrence of each link target; unwrap later duplicates to plain
    anchor text (first-occurrence-only). The link-insertion pass occasionally wraps the
    same URL twice (the 2026-05-22 pilot saw one duplicate); `first_occurrence_only` is a
    scored, non-critical QA check, so this deterministically fixes it before write-back
    rather than demoting an otherwise-good summary."""
    seen: set[str] = set()

    def _repl(m: "re.Match") -> str:
        url = m.group(2).strip()
        if url in seen:
            return m.group(1)  # unwrap the duplicate → plain anchor text
        seen.add(url)
        return m.group(0)

    return _MD_LINK_FULL_RE.sub(_repl, md)


_LINK_CEILING_WORDS = 80  # mirror qa._LINK_STUFFING_WORDS_PER_LINK

# Acceptance gate for the link-INSERTION pass. Because the pass preserves the prose
# verbatim (guarded separately by qa.text_preserved), the keyword-PLACEMENT checks
# (keyword_in_h2 / keyword_in_p1) are intentionally NOT gated here — they judge the
# original prose, not the links, and a CMS-sourced summary may have no stored keyword_plan.
# These are the LINK + formatting invariants that actually matter for inserting links:
_LINK_INSERTION_CRITICAL = (
    "no_em_dashes", "no_lists", "no_faq_schema",
    "links_internal_domain", "links_locale_matched", "no_link_stuffing",
)


def _trim_links_to_ceiling(md: str) -> str:
    """Unwrap excess links (keep the FIRST N) so the link rate stays at/under 1 per ~80
    words — the QA `no_link_stuffing` ceiling. The link-insertion model occasionally
    over-links a short post (the 2026-05-22 full run held ~several for stuffing); trimming
    the tail deterministically recovers them instead of demoting the whole summary. Keeps
    the earliest links (usually the most contextually anchored).

    Word count is taken on the DE-LINKED text (link markup → anchor text only, URLs
    dropped). QA's `no_link_stuffing` counts URL tokens as words, which inflates its
    word_count and would let one extra link through; counting prose+anchors only makes the
    trim's ceiling a touch stricter than QA's, so a trimmed summary is GUARANTEED to pass
    (the first full run left 2 blogs at 7 links / 556 words because the trim counted URLs)."""
    de_linked = _MD_LINK_FULL_RE.sub(lambda m: m.group(1), md)
    word_count = len(re.findall(r"\b\w+\b", _HTML_TAG_RE.sub(" ", de_linked)))
    max_links = word_count // _LINK_CEILING_WORDS
    matches = list(_MD_LINK_FULL_RE.finditer(md))
    if len(matches) <= max_links:
        return md
    # Unwrap every link past the first `max_links` (by position).
    keep = max(max_links, 0)
    idx = {"n": 0}

    def _repl(m: "re.Match") -> str:
        idx["n"] += 1
        return m.group(0) if idx["n"] <= keep else m.group(1)

    return _MD_LINK_FULL_RE.sub(_repl, md)


def _slug_from_url(url: str) -> str:
    import urllib.parse

    return urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]


def _execute_link_blogs(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    """Insert internal links into existing UNDER-LINKED blog summaries (Flash, link-only).

    The 2026-05-22 internal-linking remediation: 138/241 blog summaries shipped with 0
    internal links (Flash under-followed the link instruction; the 4-part designed pages
    were fine). Rather than REGENERATE the prose (the user's explicit constraint: "only
    set links, do not regenerate texts"), this pass feeds each under-linked summary back
    to Flash with the locale-filtered link inventory and a strict link-INSERTION prompt:
    wrap existing phrases in links, change no words. The de-linked output must match the
    original (`qa.text_preserved`) AND pass the critical QA checks (internal-domain,
    same-locale, anti-stuffing) or the item is held back (never written). Source summaries
    come from the `--from-run` manifest; the live blog collection supplies the cms_item_id
    for the staged write-back. Reuses the generate-english helpers; the generation path is
    untouched.
    """
    from tools.summary import batch_runner, llms_parser
    from tools.summary.prompt_builder import (
        build_link_insertion_system_prompt, build_link_insertion_user_message,
    )
    from tools.summary.qa import qa_checks, text_preserved
    from tools.summary.structure import summary_markdown_to_html

    warnings: list[str] = []
    max_existing = getattr(args, "max_existing_links", 0)
    locale_filter = args.locale

    # 1. Load the source manifest (existing summaries to link into).
    from_run = args.from_run or out_dir
    manifest_path = from_run / "en-summaries.json"
    if not manifest_path.exists():
        return {
            "submitted": False, "requests_built": 0,
            "reason": f"manifest not found: {manifest_path}",
            "warnings": ["--from-run must point at a dir containing en-summaries.json"],
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # 2. Select under-linked blog targets from the manifest.
    targets: list[dict[str, Any]] = []
    for _cid, entry in manifest.items():
        if entry.get("content_type") != "blog_post":
            continue
        md = entry.get("markdown", "") or ""
        if not md.strip():
            continue
        if _count_internal_md_links(md) > max_existing:
            continue  # already has enough links
        loc = entry.get("locale", "en")
        if locale_filter and loc != locale_filter:
            continue
        targets.append({
            "slug": _slug_from_url(entry.get("url", "")),
            "existing_md": md, "url": entry.get("url", ""), "locale": loc,
            "kw": entry.get("keyword_plan", {}) or {},
        })

    # 3. llms.txt → link candidates (live only).
    llms_index = None
    if not args.dry_run:
        try:
            llms_index = llms_parser.fetch_and_parse(config.LLMS_TXT_URL)
        except Exception as e:
            warnings.append(f"llms.txt fetch failed; candidate pool falls back to STATIC_PAGES: {e}")

    # 4. Map slug → cms_item_id from the live blog collection (for the staged write-back).
    item_ids: dict[str, str] = {}
    item_titles: dict[str, str] = {}
    wf = None
    if not args.dry_run:
        from tools.summary.webflow_client import WebflowClient

        wf = WebflowClient(dry_run=False)
        try:
            for it in wf.list_items(config.COLLECTIONS["blog"]):
                if it.is_draft or it.is_archived:
                    continue
                s = it.field_data.get("slug", "")
                if s:
                    item_ids[s] = it.id
                    item_titles[s] = it.field_data.get("name") or it.field_data.get("title", "")
        except Exception as e:
            warnings.append(f"blog collection enumeration failed: {e}")

    # 5. Build link-insertion requests (Flash, no thinking — link-only).
    requests = []
    req_meta: dict[str, dict] = {}
    for i, t in enumerate(targets):
        cms_item_id = item_ids.get(t["slug"])
        if (not args.dry_run) and not cms_item_id:
            warnings.append(f"no live blog item for slug {t['slug']!r}; skipped")
            continue
        candidates = _build_link_candidate_pool(
            "blog_post", llms_index, t["locale"], source_url=t["url"],
        )
        user_msg = build_link_insertion_user_message(
            t["existing_md"], candidates, t["locale"], post_title=item_titles.get(t["slug"], ""),
        )
        cid = f"link-{i}-{t['slug'][:40]}"
        requests.append(batch_runner.BatchRequest(
            custom_id=cid, system_blocks=build_link_insertion_system_prompt(),
            user_message=user_msg, enable_thinking=False, model=config.MODEL_BLOG,
        ))
        req_meta[cid] = {**t, "cms_item_id": cms_item_id}
        if args.limit and len(requests) >= args.limit:
            break

    if not requests:
        return {
            "submitted": False, "targets_found": len(targets), "requests_built": 0,
            "reason": "no under-linked blog targets resolved", "warnings": warnings,
        }

    # 6. Cost gate — mirror generate-english (hard cap + pilot-first confirm).
    est_mode = "interactive" if args.sync else "batch"
    cost_estimate = batch_runner.estimate_batch_cost_usd(requests, mode=est_mode, cached=False)
    cost_gate = {
        "projected_usd": round(cost_estimate, 4), "mode": est_mode,
        "cost_cap_usd": config.MAX_BATCH_COST_USD,
        "confirm_threshold_usd": config.COST_CONFIRM_THRESHOLD_USD,
        "confirm_required": False, "confirmed": bool(getattr(args, "confirm_cost", False)),
        "model_breakdown": {config.MODEL_BLOG: len(requests)},
    }
    if cost_estimate > config.MAX_BATCH_COST_USD:
        warnings.append(
            f"COST CAP EXCEEDED: ${cost_estimate:.2f} > ${config.MAX_BATCH_COST_USD}. Aborting."
        )
        return {"submitted": False, "targets_found": len(targets), "requests_built": len(requests),
                "cost_gate": cost_gate, "warnings": warnings}
    if (not args.dry_run) and cost_estimate > config.COST_CONFIRM_THRESHOLD_USD and not getattr(args, "confirm_cost", False):
        cost_gate["confirm_required"] = True
        warnings.append(
            f"COST CONFIRM REQUIRED: projected ${cost_estimate:.2f} > "
            f"${config.COST_CONFIRM_THRESHOLD_USD:.2f}. Re-run with --confirm-cost."
        )
        return {"submitted": False, "targets_found": len(targets), "requests_built": len(requests),
                "cost_gate": cost_gate, "warnings": warnings}

    # 7. Dry-run: stop at the plan.
    if args.dry_run:
        return {"submitted": False, "dry_run": True, "targets_found": len(targets),
                "requests_built": len(requests), "cost_gate": cost_gate, "warnings": warnings}

    # 8. Submit (Flash; sync or batch).
    results, handle, batch_ids = _submit_and_wait(requests, args)
    succeeded = [r for r in results if r.succeeded]
    failed = [r for r in results if not r.succeeded]

    # 9. Sanitize → QA (link rules + TEXT PRESERVATION) → staged write-back.
    cms_writes = 0
    write_failures = 0
    demoted: list[dict] = []
    links_added: list[int] = []
    for r in succeeded:
        meta = req_meta.get(r.custom_id)
        if not meta:
            continue
        linked = _trim_links_to_ceiling(_dedup_md_links(_sanitize_summary(r.content)))
        ok_preserved, ratio = text_preserved(meta["existing_md"], linked)
        rep = qa_checks(
            linked, (meta["kw"] or {}).get("primary", ""), meta["locale"],
            _build_link_candidate_pool("blog_post", llms_index, meta["locale"], source_url=meta["url"]),
            excluded_path_segments=config.EXCLUDED_LINK_PATH_SEGMENTS,
        )
        n_links = _count_internal_md_links(linked)
        # Accept only if the prose is preserved, the LINK/formatting invariants hold (NOT the
        # keyword-placement checks — those judge the preserved prose, and CMS-sourced blogs
        # have no stored keyword), and links were actually added (≥1 is a strict improvement
        # over the current 0; the link_density score still records whether it hit 6–8).
        link_ok = all(rep.checks.get(c, True) for c in _LINK_INSERTION_CRITICAL)
        if ok_preserved and link_ok and n_links >= 1:
            wres = wf.update_item_summary(
                collection_id=config.COLLECTIONS["blog"], item_id=meta["cms_item_id"],
                summary_html=summary_markdown_to_html(linked),
            )
            if wres.success:
                cms_writes += 1
                links_added.append(n_links)
            else:
                write_failures += 1
                warnings.append(f"cms write failed for {meta['slug']}: {wres.error}")
        else:
            reasons = []
            if not ok_preserved:
                reasons.append(f"text not preserved (sim {ratio:.2f})")
            if not link_ok:
                failed_link_checks = [c for c in _LINK_INSERTION_CRITICAL if not rep.checks.get(c, True)]
                reasons.append("QA link checks: " + ", ".join(failed_link_checks))
            if n_links < 1:
                reasons.append("no links added")
            demoted.append({"slug": meta["slug"], "url": meta["url"], "reason": "; ".join(reasons)})

    review = {
        "demoted": demoted,
        "failed": [{"custom_id": f.custom_id, "error": f.error} for f in failed],
    }
    (out_dir / "link-blogs-review.json").write_text(
        json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    avg_links = round(sum(links_added) / len(links_added), 1) if links_added else 0
    return {
        "submitted": True, "dry_run": False, "targets_found": len(targets),
        "requests_built": len(requests), "succeeded": len(succeeded), "failed": len(failed),
        "cms_writes": cms_writes, "write_failures": write_failures,
        "avg_links_added": avg_links, "links_added_distribution": sorted(links_added),
        "demoted_count": len(demoted), "demoted": demoted[:20],
        "cost_gate": cost_gate, "batch_ids": batch_ids,
        "review_path": str(out_dir / "link-blogs-review.json"), "warnings": warnings,
    }


def _execute_audit(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    """Audit existing summaries; score; surface REGENERATE candidates."""
    from tools.summary import structure
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
            # tracker-096: static pages use the 4-part structure. Reconstruct the
            # 4-part Markdown from the live elements and score with the 4-part rule
            # set; fall back to the legacy single #summary element if a page hasn't
            # been migrated yet.
            if pc.existing_summary_parts:
                reconstructed = structure.parts_to_markdown(pc.existing_summary_parts)
                score = audit_existing_summary(
                    url=url, summary_markdown=reconstructed,
                    primary_keyword=kw.primary, locale="en",
                    link_inventory=config.STATIC_PAGES, structure="four_part",
                )
            else:
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


_MARKDOWN_LINK_RE = __import__("re").compile(r"\[[^\]]+\]\(([^)]+)\)")


def _extract_markdown_links(md: str) -> list[str]:
    """Extract URLs from `[anchor](url)` patterns in Markdown."""
    if not md:
        return []
    return _MARKDOWN_LINK_RE.findall(md)


def _execute_translate(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    """Translate EN summaries into 8 locales; emit consolidated per-language CSVs.

    Reads `en-summaries.json` from `--from-run <dir>` if provided, else from
    `<out_dir>/en-summaries.json` (the path generate-english writes to in the
    same run). Closes audit-086 C-4 (tracker-087 F-2).
    """
    from tools.summary import batch_runner, csv_emitter, llms_parser
    from tools.summary.prompt_builder import (
        LinkSwap, build_translation_system_prompt, build_translation_user_message,
    )
    from tools.translator import translate_batch, TranslationUnit
    from tools.translator.glossary import load_glossary
    from tools.translator.tm import TranslationMemory

    warnings: list[str] = []
    target_locales = (
        [args.locale] if args.locale and args.locale != "en"
        else list(config.TARGET_TRANSLATION_LOCALES)
    )

    # Resolve manifest path: --from-run takes precedence.
    manifest_path = (
        (args.from_run / "en-summaries.json")
        if args.from_run
        else (out_dir / "en-summaries.json")
    )
    if not manifest_path.exists():
        warnings.append(
            f"no EN summaries manifest at {manifest_path}; nothing to translate. "
            f"Run generate-english first or pass --from-run <dir>."
        )
        return {
            "target_locales": target_locales,
            "per_locale": {},
            "manifest_path": str(manifest_path),
            "warnings": warnings,
        }

    en_summaries: dict[str, dict] = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Manifest shape: {"<custom_id>": {"url": ..., "markdown": ..., "content_type": ..., "locale": ...}}

    # Content-type → collection-slug mapping (mirrors _collection_id_for_content_type).
    # Skip any content_type that maps to a collection NOT meant for translation.
    # Static pages (content_type="landing") have no mapping → never skipped (tracker-091 M-10).
    _CT_TO_COLLECTION = {
        "blog_post": "blog",
        "course":    "courses",
        "housing":   "housing_new",
    }
    _SKIP_TRANSLATE_TYPES = {
        ct for ct, slug in _CT_TO_COLLECTION.items()
        if slug in config.NATIVE_LANGUAGE_COLLECTIONS
        or slug in config.NO_TRANSLATE_COLLECTIONS
    }

    # llms.txt for cross-locale link swaps (live only — dry-run skips the network).
    llms_index = None
    if not args.dry_run:
        try:
            llms_index = llms_parser.fetch_and_parse(config.LLMS_TXT_URL)
        except Exception as e:
            warnings.append(f"llms.txt fetch failed: {e}; link swaps will all REMOVE")

    # tracker-092 Phase 3: translation runs through the dedicated engine (glossary
    # + translation-memory + translation-QA). The engine reuses batch_runner as
    # its Gemini client; this caller keeps the M-10 content-type filter, the
    # llms.txt link-swaps (via the request_builder, for prompt parity), and the
    # paragraph-split → Weglot-CSV emission. Dry-run keeps the original
    # build-requests + dry_run_submit path UNCHANGED (request_count + JSONL
    # artifact parity for the M-10 tests).
    glossary = load_glossary()
    tm = None if args.dry_run else TranslationMemory(config.TRANSLATION_MEMORY_FILE)

    per_locale_results: dict[str, dict] = {}
    for locale in target_locales:
        # Build TranslationUnits (one per non-skipped, non-empty EN summary).
        units = []
        for cid, en in en_summaries.items():
            if en.get("content_type") in _SKIP_TRANSLATE_TYPES:
                continue
            md = en.get("markdown", "") or ""
            if not md.strip():
                continue
            units.append(TranslationUnit(
                id=f"tr-{locale}-{cid}", text=md,
                content_type=en.get("content_type", "landing"),
            ))

        if not units:
            per_locale_results[locale] = {
                "skipped": True,
                "reason": "no EN summaries had non-empty markdown",
            }
            continue

        # request_builder reproduces the existing summary-translation prompt
        # (llms.txt link swaps) so behaviour + CSV structure are preserved.
        def _summary_rb(unit, loc, gslice, _llms=llms_index):
            link_swaps = []
            for src_url in _extract_markdown_links(unit.text):
                target_url = _llms.find_equivalent(src_url, loc) if _llms else None
                link_swaps.append(LinkSwap(source_url=src_url, target_url=target_url))
            # tracker-095 M1: inject the per-unit glossary slice (do-not-translate
            # brand/entity terms) into the summary translation prompt. The engine
            # computes it; previously this builder discarded it, so brand terms
            # were never told to the model for summaries.
            system_blocks = build_translation_system_prompt(loc)
            if gslice:
                system_blocks = system_blocks + [{"type": "text", "text": gslice}]
            return (
                system_blocks,
                build_translation_user_message(unit.text, loc, link_swaps),
            )

        # Cost check (build the would-be requests once via the same builder).
        requests = []
        for u in units:
            sb, um = _summary_rb(u, locale, "")
            requests.append(batch_runner.BatchRequest(
                custom_id=u.id, system_blocks=sb, user_message=um, enable_thinking=False,
            ))
        cost_estimate = batch_runner.estimate_batch_cost_usd(requests)
        if cost_estimate > config.MAX_BATCH_COST_USD:
            warnings.append(
                f"locale {locale}: cost cap exceeded "
                f"(${cost_estimate:.2f} > ${config.MAX_BATCH_COST_USD}). Skipping."
            )
            per_locale_results[locale] = {
                "skipped": True, "cost_estimate_usd": round(cost_estimate, 2),
                "reason": "exceeded MAX_BATCH_COST_USD",
            }
            continue

        # Dry-run: original path (request_count + JSONL artifact parity).
        if args.dry_run:
            artifact_dir = out_dir / "translate-batches" / locale
            handle = batch_runner.dry_run_submit(requests, artifact_dir=artifact_dir)
            per_locale_results[locale] = {
                "dry_run": True,
                "batch_id": handle.batch_id,
                "request_count": len(requests),
                "cost_estimate_usd": round(cost_estimate, 2),
                "artifact_path": str(handle.artifact_path),
            }
            continue

        # Live: translate via the dedicated engine (TM skip + glossary + QA).
        # qa_check_urls=False: this path swaps/removes links per locale (see
        # _summary_rb), so source URLs are intentionally absent from the target
        # — url_drift would false-flag every linked paragraph (tracker-095 H2).
        translations = translate_batch(
            units, locale, glossary, request_builder=_summary_rb, tm=tm,
            qa_check_urls=False,
        )
        pairs: list[csv_emitter.SummaryPair] = []
        succeeded_count = 0
        failed_count = 0
        for t in translations:
            if not t.target.strip():
                failed_count += 1
                continue
            # tracker-095 H1: a translation that failed a BLOCKING QA check
            # (ok=False — placeholder/number drift, forbidden term, empty) must
            # NOT ship. url_drift is excluded for summaries (qa_check_urls=False).
            if not t.ok:
                failed_count += 1
                warnings.append(f"locale {locale} {t.id}: QA blocked, not shipped — {t.qa_flags}")
                continue
            succeeded_count += 1
            if t.qa_flags and not t.from_tm:
                warnings.append(f"locale {locale} {t.id}: QA flags {t.qa_flags}")
            parts = t.id.split("-", 2)
            if len(parts) < 3:
                continue
            orig_cid = parts[2]
            en_md = en_summaries.get(orig_cid, {}).get("markdown", "")
            en_paragraphs = csv_emitter.split_summary_into_paragraphs(en_md)
            tr_paragraphs = csv_emitter.split_summary_into_paragraphs(t.target)
            if len(en_paragraphs) != len(tr_paragraphs):
                warnings.append(
                    f"locale {locale} cid {orig_cid}: paragraph count mismatch "
                    f"(en={len(en_paragraphs)} tr={len(tr_paragraphs)}); skipping"
                )
                continue
            try:
                pairs.extend(csv_emitter.pair_from_paragraphs(en_paragraphs, tr_paragraphs))
            except ValueError as e:
                warnings.append(f"pair_from_paragraphs failed for {orig_cid}: {e}")

        # Emit consolidated CSV.
        existing_csv = config.WEGLOT_IMPORTS_DIR / f"{locale}.csv"
        out_csv = config.WEGLOT_IMPORTS_DIR / f"{locale}.csv"  # overwrite in place
        emission_report = csv_emitter.emit_consolidated_csv(
            target_locale=locale,
            existing_csv_path=existing_csv,
            summary_pairs=pairs,
            out_path=out_csv,
        )
        per_locale_results[locale] = {
            "dry_run": False,
            "engine": "translator",
            "request_count": len(units),
            "succeeded": succeeded_count,
            "failed": failed_count,
            "cost_estimate_usd": round(cost_estimate, 2),
            "csv_path": str(out_csv),
            "rows_appended": emission_report.new_row_count,
            "duplicates_skipped": emission_report.duplicates_skipped,
            "existing_rows": emission_report.existing_row_count,
        }

    return {
        "target_locales": target_locales,
        "per_locale": per_locale_results,
        "manifest_path": str(manifest_path),
        "warnings": warnings,
    }


# ---- Meta-tags translation caller (tracker-092 Phase 3, caller #2) ----

# Mobile-safe char limits (mirror scripts/meta_locale_audit.py). Latin scripts
# only — ar/ko/ja render fewer characters per pixel, so length isn't enforced.
_META_TITLE_LIMIT = 60
_META_DESC_LIMIT = 130
_NON_LATIN_LOCALES = ("ar", "ko", "ja")


def _execute_translate_meta(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    """Translate static-page meta titles/descriptions into the 8 locales via the
    dedicated translator; emit Weglot CSV rows typed `meta_title` /
    `meta_description`. The engine's second caller (tracker-092 Phase 3).

    Scope: the 12 STATIC_PAGES (bounded, high-value). Each page contributes up to
    two source strings (title + meta description). Weglot serves the translated
    meta on the locale URLs.
    """
    import urllib.parse as _urlparse
    from tools.summary import batch_runner, csv_emitter
    from tools.summary.page_fetcher import fetch_page
    from tools.translator import translate_batch, TranslationUnit
    from tools.translator.glossary import load_glossary
    from tools.translator.tm import TranslationMemory

    warnings: list[str] = []
    target_locales = (
        [args.locale] if args.locale and args.locale != "en"
        else list(config.TARGET_TRANSLATION_LOCALES)
    )
    glossary = load_glossary()
    tm = None if args.dry_run else TranslationMemory(config.TRANSLATION_MEMORY_FILE)

    # Extract EN meta (title + description) per static page.
    pages = [u for u in config.STATIC_PAGES if not args.page or u == args.page]
    if args.limit:
        pages = pages[: args.limit]
    en_meta: list[tuple[str, str, str]] = []  # (slug, field, text)
    for url in pages:
        try:
            pc = fetch_page(url)
        except Exception as e:
            warnings.append(f"meta fetch failed for {url}: {e}")
            continue
        slug = _urlparse.urlparse(url).path.strip("/").replace("/", "-") or "home"
        if pc.title.strip():
            en_meta.append((slug, "meta_title", pc.title.strip()))
        if pc.description.strip():
            en_meta.append((slug, "meta_description", pc.description.strip()))

    if not en_meta:
        warnings.append("no EN meta titles/descriptions extracted")
        return {
            "target_locales": target_locales, "per_locale": {},
            "pages": len(pages), "warnings": warnings,
        }

    per_locale: dict[str, dict] = {}
    for locale in target_locales:
        units = [
            TranslationUnit(id=f"meta-{field}-{slug}", text=text, content_type=field)
            for (slug, field, text) in en_meta
        ]
        # tracker-095 L2: cost cap mirroring the summary path. estimate_batch_cost_usd
        # is count-based, so the unit list is a valid proxy for the request count.
        cost_estimate = batch_runner.estimate_batch_cost_usd(units)
        if not args.dry_run and cost_estimate > config.MAX_BATCH_COST_USD:
            warnings.append(
                f"locale {locale}: meta cost cap exceeded "
                f"(${cost_estimate:.2f} > ${config.MAX_BATCH_COST_USD}). Skipping."
            )
            per_locale[locale] = {
                "skipped": True, "cost_estimate_usd": round(cost_estimate, 2),
                "reason": "exceeded MAX_BATCH_COST_USD",
            }
            continue
        translations = translate_batch(units, locale, glossary, tm=tm, dry_run=args.dry_run)
        by_id = {t.id: t for t in translations}
        pairs: list[csv_emitter.SummaryPair] = []
        for (slug, field, text) in en_meta:
            t = by_id.get(f"meta-{field}-{slug}")
            if not t or not t.target.strip():
                continue
            # tracker-095 H1: don't ship a meta string that failed a BLOCKING QA
            # check (placeholder/number/URL drift, forbidden term). dry-run stubs
            # are ok=True so they still pass for wiring parity.
            if not t.ok:
                warnings.append(f"locale {locale} {t.id}: QA blocked, not shipped — {t.qa_flags}")
                continue
            if t.qa_flags and not t.from_tm and "dry_run" not in t.qa_flags:
                warnings.append(f"locale {locale} {t.id}: QA flags {t.qa_flags}")
            if locale not in _NON_LATIN_LOCALES:
                limit = _META_TITLE_LIMIT if field == "meta_title" else _META_DESC_LIMIT
                if len(t.target) > limit:
                    warnings.append(
                        f"locale {locale} {field} {slug}: {len(t.target)} chars "
                        f"exceeds mobile-safe {limit}"
                    )
            pairs.append(csv_emitter.SummaryPair(word_from=text, word_to=t.target, type_=field))

        # Dry-run writes to an isolated artifact dir; live writes the real CSV.
        if args.dry_run:
            out_csv = out_dir / "meta-batches" / f"{locale}.csv"
            existing_csv = out_csv
        else:
            out_csv = config.WEGLOT_IMPORTS_DIR / f"{locale}.csv"
            existing_csv = out_csv
        emission_report = csv_emitter.emit_consolidated_csv(
            target_locale=locale,
            existing_csv_path=existing_csv,
            summary_pairs=pairs,
            out_path=out_csv,
        )
        per_locale[locale] = {
            "dry_run": args.dry_run,
            "unit_count": len(units),
            "rows_appended": emission_report.new_row_count,
            "duplicates_skipped": emission_report.duplicates_skipped,
            "csv_path": str(out_csv),
        }

    return {
        "target_locales": target_locales,
        "per_locale": per_locale,
        "pages": len(pages),
        "meta_strings": len(en_meta),
        "warnings": warnings,
    }


# ---- Write-back helpers ----


def _write_back_summaries(
    succeeded: list, sources: list, args: argparse.Namespace, out_dir: Path, warnings: list[str],
) -> dict[str, Any]:
    """Write generated summaries to Webflow CMS (CMS items) or to JSON files (static pages)."""
    from tools.summary.structure import (
        four_part_content_html,
        four_part_paragraph_html,
        parse_four_part,
        summary_markdown_to_html,
    )
    from tools.summary.webflow_client import WebflowClient
    from tools.summary.webflow_designer import write_static_summary_parts

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
            # tracker-096: static landing pages use the 4-part structure — write the
            # 4 sections for paste into #summary-tagline/title/paragraph/content.
            parts = parse_four_part(result.content)
            wr = write_static_summary_parts(item.url, parts, static_dir, dry_run=args.dry_run)
            if wr.success:
                static_writes += 1
            else:
                failures += 1
                warnings.append(f"static write failed: {item.url}: {wr.error}")
        elif target == "cms" and item.cms_item_id:
            # In dry-run, the WebflowClient already returns a mock response.
            if item.content_type == "blog_post":
                # Blog keeps the single-block Summary, but tracker-098: convert the
                # Markdown to HTML before PATCH so the RichText field renders headings
                # + links instead of literal `##` / `[](url)`.
                wresult = wf.update_item_summary(
                    collection_id=_collection_id_for_content_type(item.content_type),
                    item_id=item.cms_item_id,
                    summary_html=summary_markdown_to_html(result.content),
                )
            else:
                # Courses / Housing → 4-part. tracker-098: write ONLY the two RichText
                # bodies (Paragraphs + Content), both as HTML, preserving the
                # author-owned Tagline + Title (never regenerate-overwrite them).
                parts = parse_four_part(result.content)
                wresult = wf.update_item_summary_body(
                    collection_id=_collection_id_for_content_type(item.content_type),
                    item_id=item.cms_item_id,
                    paragraph_html=four_part_paragraph_html(parts.paragraph),
                    content_html=four_part_content_html(parts.content_md),
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


def _structure_for_content_type(content_type: str) -> str:
    """tracker-096: blog posts keep the single-block Summary; courses, housing, and
    static landing pages use the 4-part Tagline/Title/Paragraph/Content structure."""
    return "single_block" if content_type == "blog_post" else "four_part"


def _resolve_item_locale(field_data: dict, target_locale_mode: str) -> str:
    """Resolve a CMS item's locale shortcode (tracker-096 follow-up).

    Blog posts carry their language as a `language` Reference (an item id) → mapped via
    config.BLOG_LANGUAGE_ID_TO_LOCALE so a French post yields a French summary, etc.
    Other collections fall back to a shortcode field or 'en'. Non-native targets
    (courses/housing — summarized in English) force 'en'. Any unknown/unsupported value
    falls back to 'en'.
    """
    locale = field_data.get("language-shortcode") or field_data.get("locale", "en")
    lang_ref = field_data.get("language")
    if isinstance(lang_ref, str) and lang_ref in config.BLOG_LANGUAGE_ID_TO_LOCALE:
        locale = config.BLOG_LANGUAGE_ID_TO_LOCALE[lang_ref]
    if target_locale_mode != "native_per_item":
        locale = "en"
    if locale not in config.LOCALES:
        locale = "en"
    return locale


def _cms_item_url(content_type: str, slug: str) -> str:
    """Build the live public URL for a CMS item (tracker-092 1.5 / M-14).

    URL path prefix differs by collection — verified live 2026-05-20 via llms.txt:
      blog  → /post/<slug>   (HTTP 200)
      course→ /courses/<slug> (HTTP 200)
      housing→ /pb/<slug>     (HTTP 200; /post/ and /housing/ both 404)
    The previous code hardcoded /post/ for ALL collections, producing 404 URLs
    for housing + courses in the prompt context.
    """
    prefix = {
        "blog_post": "post",
        "course": "courses",
        "housing": "pb",
    }.get(content_type, "post")
    return f"https://www.englishcollege.com/{prefix}/{slug}"


# ---- tracker-092 Phase 2: idempotency state ----


def _source_hash(source_text: str, content_id: str, model: str = "") -> str:
    """Stable hash of an item's source content + identity + prompt version + model.

    Including SUMMARY_PROMPT_VERSION means a prompt/keyword-logic change bumps every
    hash, forcing regeneration — a source-only hash would freeze stale summaries
    after a prompt improvement. tracker-097 (Hotspot #3): the resolved model is also
    folded in, so retiering an item (e.g. blog Pro → Flash) regenerates it without a
    version bump while unchanged items still skip.
    """
    import hashlib
    payload = f"{content_id}\x00{config.SUMMARY_PROMPT_VERSION}\x00{model}\x00{source_text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_summary_state() -> dict[str, dict]:
    """Load the idempotency state ({content_id: {source_hash, generated_at}}). {} if absent/corrupt."""
    path = config.SUMMARY_STATE_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_summary_state(state: dict[str, dict]) -> None:
    """Atomically persist the idempotency state."""
    import os as _os, tempfile as _tempfile
    path = config.SUMMARY_STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tfd, tpath = _tempfile.mkstemp(dir=str(path.parent), prefix=".summary-state.", suffix=".tmp")
    try:
        with _os.fdopen(tfd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        _os.replace(tpath, path)
    except OSError:
        try:
            _os.remove(tpath)
        except OSError:
            pass
        raise


_CEL_CITIES = ("vancouver", "san-diego", "los-angeles")


def _detect_city(text: str) -> str:
    """Map a blog URL/title to a CEL city slug for city-matched housing ordering, or ''.
    Canada → Vancouver (CEL's only Canadian campus). California alone is ambiguous (SD or
    LA) → '' (let the model choose)."""
    t = (text or "").lower()
    if "vancouver" in t or "canada" in t:
        return "vancouver"
    if "san-diego" in t or "san diego" in t:
        return "san-diego"
    if "los-angeles" in t or "los angeles" in t:
        return "los-angeles"
    return ""


def _build_link_candidate_pool(
    source_content_type: str,
    llms_index: "Optional[LlmsIndex]",
    source_locale: str = "en",
    source_url: str = "",
) -> tuple[str, ...]:
    """Build the per-item link-candidate pool for `_execute_generate_english`.

    Pool = STATIC_PAGES (curated, prepended) + llms.txt URLs in `source_locale`
    (deduplicated), minus EXCLUDED_LINK_PATH_SEGMENTS. When the source item is
    housing, also exclude `/pb/` so a housing summary can't link to other housing
    items (mirrors the prompt rule in tools/summary/prompts/housing.md line 28).

    Housing (2026-05-22, NO cap): the site has many new `/housing` accommodation pages
    (hub + per-city detail pages, in every locale) that need inbound internal links, so
    EVERY housing candidate in the locale is offered — there is no count cap. To make sure
    they actually reach the model (not get buried past the 60-candidate prompt cap in
    `build_user_message`), housing URLs are ordered FIRST after the curated STATIC_PAGES.
    The model still links housing only where contextually relevant (city-matched per the
    prompt), and the link-stuffing + 6–8-link QA caps the total — so abundance in the pool
    does not mean spam in the output. A housing-page summary still excludes `/pb/` siblings.

    STATIC_PAGES are prepended so the curated set survives the prompt cap in
    prompt_builder.build_user_message. Returns the FULL pool; the prompt cap is
    applied one layer down, not here (tracker-091 M-13).
    """
    # STATIC_PAGES are EN (unprefixed) URLs — valid only for EN content. A non-EN summary
    # must link ONLY same-locale URLs (the blog `links_locale_matched` rule), so for non-EN
    # locales the curated EN set is omitted and the locale's own llms URLs (which include
    # that locale's landing + housing pages) are the whole pool. 2026-05-22 fix: previously
    # the EN STATIC_PAGES were offered to every locale, so non-EN blogs linked EN pages
    # (e.g. `/`, `/san-diego-ca/language-school`) and were correctly held by QA — starving
    # those locales. Omitting EN static pages for non-EN keeps the pool same-locale-clean.
    static = list(config.STATIC_PAGES) if source_locale == "en" else []
    llms_urls: list[str] = []
    if llms_index is not None:
        excluded = list(config.EXCLUDED_LINK_PATH_SEGMENTS)
        if source_content_type == "housing":
            excluded.append("pb")
        llms_urls = llms_index.urls_in_locale_excluding(source_locale, excluded)
    # Housing first (right after the curated STATIC_PAGES), then everything else — so the
    # new accommodation pages survive the downstream 60-candidate prompt cap.
    housing = [u for u in llms_urls if _is_housing_path(u)]
    non_housing = [u for u in llms_urls if not _is_housing_path(u)]
    # City-matched ordering (2026-05-23): when the source post names a city, put THAT city's
    # housing first so a Vancouver post is offered Vancouver apartments/student-houses (not
    # just whichever homestay appears first in llms order). Stable sort preserves order
    # within the city / non-city groups, and the hub (`/housing`, no city slug) stays high.
    city = _detect_city(source_url)
    if city:
        housing.sort(key=lambda u: 0 if (city in u.lower() or u.rstrip("/").endswith("/housing")) else 1)
    seen: set[str] = set()
    out: list[str] = []
    for u in static + housing + non_housing:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return tuple(out)


# Localized housing-hub root slugs (2026-05-23, derived from llms.txt). The /housing
# collection is URL-translated in some locales: de→unterkunft, fr→logements,
# es→alojamiento; it/pt/ko/ja/ar keep `housing`. A path is "housing" if its first segment
# (after an optional /<locale>/ prefix) is one of these.
_HOUSING_ROOT_SLUGS = frozenset({"housing", "unterkunft", "logements", "alojamiento"})
_LOCALE_PREFIX_SLUGS = frozenset({"de", "fr", "es", "it", "pt", "ko", "ja", "ar"})


def _is_housing_path(url: str) -> bool:
    """True if `url` is a /housing hub or detail page in ANY locale (tracker-098;
    2026-05-23 locale-aware). Recognizes the localized hub slug (e.g. `/de/unterkunft`,
    `/fr/logements`, `/es/alojamiento`) + their detail pages, not just the EN `/housing`."""
    import urllib.parse

    segments = [s for s in urllib.parse.urlparse(url).path.strip("/").split("/") if s]
    if not segments:
        return False
    if segments[0] in _LOCALE_PREFIX_SLUGS:  # skip a leading locale prefix
        segments = segments[1:]
    return bool(segments) and segments[0] in _HOUSING_ROOT_SLUGS


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
