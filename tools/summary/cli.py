"""CLI orchestration: generate-english | audit | all | plan.

Subcommands:
  plan             — emit JSON describing what WOULD be processed (no fetches, no API)
  generate-english — fetch source content, derive keywords, generate EN summaries
  audit            — score existing summaries, surface REGENERATE candidates
  all              — run generate-english → audit

`translate` and `translate-meta` were retired 2026-09-29 (U3-S): the localization desk is the
one translation engine, and the operator's rule is "Never rewrite or translate already we have".

Default mode is `--dry-run`: no live Gemini API calls, no Webflow writes, no live
CSV mutations. `--no-dry-run` enables real API calls + Webflow writes. Static-
page summaries are written to Markdown files under
`docs/admin/weglot-imports/static-summaries/` regardless of mode — the user copy-
pastes those into Webflow Designer.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
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
            "pages and audit existing summaries. Default mode is --dry-run. (The "
            "translate / translate-meta commands were retired 2026-09-29, U3-S: the "
            "localization desk is the one translation engine.)"
        ),
    )
    parser.add_argument(
        "subcommand",
        choices=[
            "generate-english", "audit", "all", "plan",
            # tracker-097: orphaned-batch recovery (RC5). A submitted Gemini batch keeps
            # billing after its GHA run is cancelled; these stop / reclaim it by id.
            "cancel-batch", "retrieve-batch",
            # audit-108 H-1: FREE match-verification gate — fetch each translatable page
            # and report how many of its live summary blocks are present as word_from in
            # the committed CSVs (i.e. will actually apply in Weglot). No spend.
            "verify-emit",
            # audit-108 M-1/M-2: remove stale (markdown-laden) summary word_from rows from
            # the locale CSVs, keeping Fidelo + meta + clean rows. No spend.
            "purge-stale-rows",
            # FREE: print the chronological run ledger + latest summary/translation
            # state ("what ran when, with what result"). Read-only, no spend.
            "status",
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
            "summary-state idempotency skip). Never regenerates a blog post that "
            "already has a summary (U3-S)."
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
        "--publish", action="store_true", default=False,
        help=(
            "generate-english only — after writing summaries to the staged CMS items, "
            "publish ONLY those items to LIVE (POST /items/publish; never the whole site). "
            "Used by the blog-summary autopilot so a new post's summary goes live without a "
            "manual publish. No effect in dry-run."
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
            "verify-emit — directory containing en-summaries.json from "
            "a prior generate-english run. Defaults to <out-dir>/en-summaries.json."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # FREE, read-only: print the run ledger + latest summary/translation state.
    # Handled before any out_dir creation — it neither spends nor writes.
    if args.subcommand == "status":
        from tools.summary import run_ledger
        print(run_ledger.format_status())
        return 0

    # A page frozen for a localization round is refused BY NAME, before anything runs or
    # spends.
    if args.subcommand in ("generate-english", "all") and args.page:
        try:
            frozen_now = _frozen_paths()
        except FreezeInvalid as e:
            # Unreadable is not "nothing frozen": that would unprotect the round.
            print(f"[summary] REFUSED: {config.FREEZE_FILE.name} is not valid ({e}), so it "
                  "cannot say whether this page is frozen. Fix the file first.", file=sys.stderr)
            return 2
        if _page_path(args.page) in frozen_now:
            print(f"[summary] REFUSED: {args.page} is frozen for a localization round "
                  f"({config.FREEZE_FILE.name}): its English may not change until the round "
                  "ends.", file=sys.stderr)
            return 2

    out_dir = args.out_dir or (config.DRYRUN_DIR / _timestamp_slug())
    out_dir.mkdir(parents=True, exist_ok=True)

    # tracker-097: orphaned-batch recovery short-circuits the report pipeline.
    if args.subcommand in ("cancel-batch", "retrieve-batch"):
        return _execute_batch_recovery(args, out_dir)

    # audit-108: standalone, FREE CSV utilities (no spend, no Webflow) — print + return.
    if args.subcommand == "verify-emit":
        return _execute_verify_emit(args, out_dir)
    if args.subcommand == "purge-stale-rows":
        return _execute_purge_stale_rows(args, out_dir)

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

    # M4 (2026-05-23): write report.json in a `finally` so a partial / exception-raising
    # run still leaves the cost_gate + counts on disk (the big run-098-full left NO
    # report.json — its phase wrote manual-review + manifest then the process ended before
    # the report was written). A hard SIGKILL still can't write, but the exception path now does.
    try:
        # 'plan' subcommand: planners only, no orchestration.
        if args.subcommand == "plan":
            report["phases"]["generate_english"] = _plan_generate_english(args)
            report["phases"]["audit"] = _plan_audit(args)
        else:
            # All other subcommands run the orchestrator (real or dry-run).
            if args.subcommand in ("generate-english", "all"):
                ge = _execute_generate_english(args, out_dir)
                # Every outcome says what the freeze held back -- a real run said nothing,
                # so "why was /vancouver not regenerated?" had no answer (review round 2, L3 P2-3).
                if isinstance(ge, dict):
                    held = _plan_generate_english(args)
                    ge.setdefault("frozen", held["frozen"])
                    if held.get("freeze_error"):
                        ge.setdefault("freeze_error", held["freeze_error"])
                report["phases"]["generate_english"] = ge
            if args.subcommand in ("audit", "all"):
                report["phases"]["audit"] = _execute_audit(args, out_dir)
    finally:
        report["finished_at"] = _now_iso()
        (out_dir / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (out_dir / "report.md").write_text(_render_markdown_report(report), encoding="utf-8")
        print(f"[summary] report.json + report.md → {out_dir}", file=sys.stderr)
        # Append one compact line to the chronological run ledger (what ran, when,
        # with what result — across summaries AND translations). Never raises.
        from tools.summary import run_ledger
        run_ledger.record_run(report, out_dir)
    if not args.dry_run:
        reason = _no_work_done(report["phases"].get("generate_english"))
        if reason:
            print(f"[summary] ALERT: this run had work and did none of it: {reason}. Exiting "
                  f"{_NO_WORK_DONE_EXIT_CODE} so the workflow's failure alert fires.", file=sys.stderr)
            return _NO_WORK_DONE_EXIT_CODE
    if args.dry_run:
        print("[summary] Dry-run complete. No API calls fired, no Webflow writes performed.", file=sys.stderr)
    return 0


# U3-S (2026-09-29): the blog autopilot stayed green for weeks while every Gemini request failed
# (402/429 no credit, then 404 on a gone model). A live run whose every request failed, to Gemini
# or to Webflow, now exits non-zero, so the workflow step fails and its "Notify on failure" alert
# fires; so does a run the hard cost cap stopped (the Manager's ruling: a cap that silently stops
# every night drains nothing either), and so does a run whose every summary QA rejected (U4-1:
# otherwise the same posts are re-paid every night, green). A partial run, a day with nothing
# to do, and a pilot-first confirm stop still exit 0.
_NO_WORK_DONE_EXIT_CODE = 3


def _no_work_done(ge: Any) -> str:
    """Why a live generate-english phase with work did none of it, or "" when it did some, had
    none, or was a pilot-first confirm stop."""
    if not isinstance(ge, dict) or not ge.get("requests_built"):
        return ""
    if not ge.get("submitted"):
        gate = ge.get("cost_gate") or {}
        if "projected_usd" in gate and gate["projected_usd"] > gate.get("cost_cap_usd", float("inf")):
            return (f"it stopped at the cost cap (${gate['projected_usd']:.2f} projected > "
                    f"${gate['cost_cap_usd']}), so nothing was sent")
        return ""
    qa = ge.get("qa_gate") or {}
    if not qa.get("checked"):  # no Gemini answer at all, retries included
        return f"every request failed ({ge.get('failed', 0)} of {ge['requests_built']})"
    if not qa.get("passed"):
        return f"QA passed none of the {qa['checked']} summaries (all held for manual review)"
    wl = ge.get("write_log") or {}
    if wl.get("failures") and not (wl.get("cms_writes") or wl.get("static_writes")):
        return f"every write failed ({wl['failures']})"
    return ""


# ---- Plan-only helpers (informational; used by 'plan' subcommand) ----


def _page_path(url: str) -> str:
    """"/vancouver" for "https://www.englishcollege.com/vancouver/" -- what freeze.json lists."""
    path = re.sub(r"^https?://[^/]+", "", url.strip())
    return path.rstrip("/") or "/"


class FreezeInvalid(ValueError):
    """freeze.json exists but cannot be trusted to say which pages are frozen."""


_FREEZE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A site path as the site writes it: lowercase slug segments. "/Vancouver" or "//vancouver"
# passed the old check and matched nothing, so the page they meant stayed unfrozen
# (round 3 review of WO-32).
_FREEZE_PATH = re.compile(r"^/(?:[a-z0-9-]+(?:/[a-z0-9-]+)*)?$")


def _frozen_paths() -> set[str]:
    """Pages whose English generate-english may not change (monorepo runbook WO-30).

    The monorepo's `data/localize/freeze.json`, vendored: while a localization round is
    open, regenerating a page's English changes the text every approval was made against.
    `frozen_until` (a UTC date, YYYY-MM-DD, inclusive) ends the freeze; null means until
    further notice. A missing file is no freeze -- `test_freeze.py` insists the vendored
    one is there. A file that is there but malformed raises FreezeInvalid: reading it as
    "nothing frozen" would unprotect the round (review round 2, L3 P2-2).
    """
    try:
        raw = config.FREEZE_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return set()
    try:
        doc = json.loads(raw)
    except ValueError as e:
        raise FreezeInvalid(f"not JSON: {e}") from None
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        raise FreezeInvalid("expected an object with schema_version 1")
    pages = doc.get("frozen_pages")
    if not isinstance(pages, list) or not all(isinstance(x, str) and _FREEZE_PATH.match(x) for x in pages):
        raise FreezeInvalid("frozen_pages must be a list of site paths like /vancouver/vs-toronto")
    until = doc.get("frozen_until")
    if until is not None and not (isinstance(until, str) and _FREEZE_DATE.match(until)):
        raise FreezeInvalid("frozen_until must be null or a YYYY-MM-DD date")
    if until and datetime.now(timezone.utc).date().isoformat() > until:
        return set()
    return {_page_path(p) for p in pages}


def _plan_generate_english(args: argparse.Namespace) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    held: list[str] = []
    freeze_error = None
    if not args.collection:
        # Read only when static pages are in scope: the blog autopilot (--collection blog)
        # crashed on a malformed freeze.json that has nothing to say about blog posts
        # (review round 2, L3 P2-1). Malformed here holds EVERY static page back.
        try:
            frozen = _frozen_paths()
        except FreezeInvalid as e:
            freeze_error = str(e)
            frozen = {_page_path(u) for u in config.STATIC_PAGES}
        for url in config.STATIC_PAGES:
            if args.page and url != args.page:
                continue
            if _page_path(url) in frozen:
                held.append(url)          # frozen for a localization round -- see _frozen_paths
                continue
            targets.append({
                "kind": "static_page", "url": url, "locale": "en", "content_type": "landing",
                "model": config.model_for_content_type("landing"),
            })
    for slug, cid in config.COLLECTIONS.items():
        if args.collection and args.collection != slug:
            continue
        # --page names one page; it planned every collection as well (review round 2, L3 P2-5).
        if args.page and not args.collection:
            continue
        if getattr(args, "exclude_blog", False) and slug == "blog":
            continue
        content_type = {"blog": "blog_post", "courses": "course", "housing_new": "housing"}[slug]
        targets.append({
            "kind": "cms_collection", "collection": slug, "collection_id": cid,
            "locale": "native_per_item" if slug in config.NATIVE_LANGUAGE_COLLECTIONS else "en",
            "content_type": content_type,
            # tracker-097: show each target's model in `plan`.
            "model": config.model_for_content_type(content_type),
        })
    if args.limit:
        targets = targets[: args.limit]
    plan = {"target_count": len(targets), "targets": targets, "model": config.MODEL_ID,
            "frozen": held}
    if freeze_error:
        plan["freeze_error"] = freeze_error
    elif not args.collection:
        # A frozen path no static page has freezes nothing here: say so, rather than let a
        # typo look like protection.
        static = {_page_path(u) for u in config.STATIC_PAGES}
        unmatched = sorted(p for p in frozen if p not in static)
        if unmatched:
            plan["freeze_unmatched"] = unmatched
    return plan


def _plan_audit(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "audit_thresholds": {
            "regenerate_below": config.AUDIT_REGENERATE_THRESHOLD,
            "manual_review_below": config.AUDIT_MANUAL_REVIEW_THRESHOLD,
        },
        "collections_to_audit": list(config.COLLECTIONS.keys()),
        "static_pages_to_audit": list(config.STATIC_PAGES),
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
        # A cancelled batch is terminal — drop the recovery pointer when it names
        # THIS batch, so the next cancel/retrieve doesn't re-target a dead id (and
        # the summary.yml `|| echo` doesn't mask it as "nothing to cancel"). Only
        # clear on a match, never a pointer to a different in-flight batch.
        try:
            persisted = json.loads(config.LAST_BATCH_FILE.read_text(encoding="utf-8"))
            if persisted.get("batch_id") == batch_id:
                config.LAST_BATCH_FILE.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
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


def _submit_and_wait(requests: list, args: argparse.Namespace, run_deadline: Optional[float] = None):
    """Run a batch of requests and collect results (tracker-097).

    --sync: one synchronous generate_sync over all requests (per-request model).
    Batch (default): group requests by resolved model and run one Batch job per
    model — the Batch API accepts a single model per job, so tiering (blog → Flash,
    rest → Pro) requires per-model jobs. Returns (results, primary_handle, batch_ids).

    tracker-138 (2026-07-13): `run_deadline` is an ABSOLUTE time.monotonic() timestamp shared
    across the WHOLE run. Every generate_sync pass (the main pass AND the retry pass) is bounded
    by the REMAINING budget to that one deadline — so the retry can no longer get a fresh 40-min
    budget and ride the run past the 60-min job cap. Falls back to the legacy per-call budget only
    when no run-deadline is threaded (e.g. a unit test calling this directly).
    """
    from tools.summary import batch_runner

    if args.sync:
        handle = batch_runner.BatchHandle(
            batch_id=f"sync-{_timestamp_slug()}", request_count=len(requests),
            submitted_at=_now_iso(), dry_run=False,
        )
        remaining = (
            max(1.0, run_deadline - time.monotonic())
            if run_deadline is not None else config.SYNC_RUN_DEADLINE_SEC
        )
        return (
            batch_runner.generate_sync(requests, run_deadline_sec=remaining),
            handle,
            [handle.batch_id],
        )

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


def _execute_verify_emit(args: argparse.Namespace, out_dir: Path) -> int:
    """audit-108 H-1: FREE Weglot match-verification gate. For each translatable page,
    fetch the live page, derive its summary blocks, and report how many appear as
    word_from in the committed per-locale CSVs (i.e. will actually APPLY in Weglot).
    No Gemini, no Webflow. Exit 0 if every page matches 100%, 2 otherwise."""
    import json
    from tools.summary import match_verify, page_fetcher

    manifest_path = (
        (args.from_run / "en-summaries.json") if args.from_run
        else (out_dir / "en-summaries.json")
    )
    if not manifest_path.exists():
        print(f"[verify-emit] no manifest at {manifest_path}; pass --from-run <dir>", file=sys.stderr)
        return 1
    en_summaries = json.loads(manifest_path.read_text(encoding="utf-8"))
    locales = (
        [args.locale] if args.locale and args.locale != "en"
        else list(config.TARGET_TRANSLATION_LOCALES)
    )
    result = match_verify.verify_pages(
        en_summaries, config.WEGLOT_IMPORTS_DIR, locales, page_fetcher.fetch_page,
    )
    print(match_verify.format_report(result))
    full = match_verify.all_pages_full_match(result)
    print(f"[verify-emit] {'PASS — every block will apply' if full else 'GAPS — some blocks will machine-translate'}",
          file=sys.stderr)
    return 0 if full else 2


def _execute_purge_stale_rows(args: argparse.Namespace, out_dir: Path) -> int:
    """audit-108 M-1/M-2: remove stale (markdown-laden) summary word_from rows from the
    per-locale CSVs — keeping Fidelo, meta, and clean block rows. FREE; --dry-run reports
    only. Lets a re-emit be authoritative (the dedup 'existing-wins' no longer pins a
    superseded chunk row) and de-bloats the staged CSVs."""
    from tools.translator import weglot

    locales = (
        [args.locale] if args.locale and args.locale != "en"
        else list(config.TARGET_TRANSLATION_LOCALES)
    )
    total_dropped = 0
    for loc in locales:
        path = config.WEGLOT_IMPORTS_DIR / f"{loc}.csv"
        rows = weglot.read_existing_csv(path)
        if not rows:
            print(f"  {loc}.csv: absent/empty — skipped", file=sys.stderr)
            continue
        kept, dropped = weglot.filter_out_stale_summary_rows(rows)
        total_dropped += len(dropped)
        action = "would drop" if args.dry_run else "dropped"
        print(f"  {loc}.csv: {len(rows)} rows → {action} {len(dropped)} stale, kept {len(kept)}", file=sys.stderr)
        if not args.dry_run and dropped:
            weglot.atomic_write_text(path, weglot.format_csv_text(kept))
    mode = "DRY-RUN (no files changed)" if args.dry_run else "written"
    print(f"[purge-stale-rows] {mode}; {total_dropped} stale summary rows across {len(locales)} locales",
          file=sys.stderr)
    return 0


_WATCHDOG_EXIT_CODE = 2  # non-zero: a watchdog fire is an ABNORMAL hang worth alerting (see _start_run_watchdog).


def _start_run_watchdog(hard_sec: float) -> "threading.Timer":
    """Defense-in-depth backstop (tracker-138): if the whole run hangs past ``hard_sec`` — a stuck
    network read, an unforeseen loop — a daemon timer force-exits the process rather than let it ride the
    job cap to a SIGKILL. The NORMAL bounded run stops COOPERATIVELY at the generate/run deadlines and exits
    0 on its own well before this, so the watchdog only ever fires on a genuine hang the cooperative stops
    did NOT catch. That is an abnormal condition, so it exits NON-ZERO (``_WATCHDOG_EXIT_CODE``) — which is
    what makes the workflow's "Notify on failure" step fire; exiting 0 here (the first cut of this fix) would
    have re-created the exact silent-hang the alert exists to prevent. Durability does NOT depend on the exit
    code: write-back has already checkpointed summary-state.json INCREMENTALLY, and the commit step runs on
    ``always()``, so the backlog still drains AND the owner is told a run hung. Daemon so it never blocks a
    normal exit (a run that finishes first discards it at interpreter shutdown). Returns the started Timer.
    """
    def _fire() -> None:
        print(
            f"[summary] run watchdog: exceeded {hard_sec:.0f}s hard budget — a phase HUNG past the cooperative "
            f"deadlines. Exiting {_WATCHDOG_EXIT_CODE} (alert) with progress already checkpointed; investigate.",
            file=sys.stderr, flush=True,
        )
        os._exit(_WATCHDOG_EXIT_CODE)  # immediate; the incremental checkpoint is already on disk (+ always()-commit).

    t = threading.Timer(hard_sec, _fire)
    t.daemon = True
    t.start()
    return t


def _execute_generate_english(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    """Execute generate-english phase. Returns metadata for the report."""
    from tools.summary import batch_runner, llms_parser
    from tools.summary.page_fetcher import fetch_page, PageContent
    from tools.summary.keyword_extractor import derive_keywords, html_to_text
    from tools.summary.prompt_builder import (
        KeywordPlan, SourceItem, build_system_prompt, build_user_message,
    )

    # tracker-138 (2026-07-13): TWO shared wall-clock deadlines for the whole live run, plus a hard watchdog.
    # generate_deadline (both generate passes) fires EARLIER than run_deadline (write-back) so a large first-run
    # backlog cannot consume the whole budget and STARVE write-back — the failure that left items generated but
    # never written or checkpointed. The reserved gap lets write-back persist what this run generated.
    # SCOPE: only the --sync path (the interactive autopilot, which runs under a ~60-min CI cap) is bounded.
    # A DEFAULT (Batch API) run legitimately takes up to the 24h batch SLA, so bounding it — or the watchdog
    # force-exiting it at 52 min — would be wrong; batch runs stay unbounded. Dry-run also opts out (no network,
    # no cap). When they opt out the deadlines stay None → every phase runs unbounded, exactly as today.
    generate_deadline: Optional[float] = None
    run_deadline: Optional[float] = None
    if not args.dry_run and getattr(args, "sync", False):
        _now = time.monotonic()
        generate_deadline = _now + config.GENERATE_DEADLINE_SEC
        run_deadline = _now + config.RUN_DEADLINE_SEC
        _start_run_watchdog(config.RUN_WATCHDOG_HARD_SEC)

    plan = _plan_generate_english(args)
    items_to_process: list[dict[str, Any]] = []
    warnings: list[str] = []
    qa_scores: dict[str, float] = {}  # tracker-092 (1.2): cid → QA score; recorded in manifest + report

    # tracker-091 M-13: fetch llms.txt once for the whole phase so every item's
    # link-candidate pool can include CMS items (housing /housing/, courses, blog) —
    # not just the 12 curated STATIC_PAGES. Dry-run skips the network; failure falls back
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
    has_summary_skipped = 0  # U3-S: blog posts left alone because they already have a summary
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
                    # U3-S (2026-09-29), the operator: "Never rewrite or translate already we have".
                    # A blog post whose summary field has text is never regenerated or re-published:
                    # not for a changed hash, prompt version or model, and not with --force. Only an
                    # empty field (or one holding tags and no text) is filled.
                    if target["content_type"] == "blog_post" and _existing_summary_seed(
                        field_data.get(config.SUMMARY_CONTENT_FIELD_SLUG, "") or ""
                    ):
                        has_summary_skipped += 1
                        continue
                    title = field_data.get("name") or field_data.get("title", "")
                    slug = field_data.get("slug", "")
                    body = field_data.get("post-body") or field_data.get("description") or ""
                    if target["content_type"] == "blog_post":
                        # U3-S batch 4: the post as TEXT. Gemini and QA read its words, not its
                        # markup (8,000 chars of HTML held about half of a 12k-char post).
                        body = html_to_text(body)
                    locale = _resolve_item_locale(field_data, target["locale"])
                    url = _cms_item_url(target["content_type"], slug)  # per-collection prefix (M-14)
                    kw = derive_keywords(title, title, url, body, locale=locale,
                                         content_type=target["content_type"])
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
                model=config.model_for_content_type(item.content_type),
                # U3-S: the blog generator pins thinking at high (the engine's decision).
                thinking_level=config.BLOG_THINKING_LEVEL if item.content_type == "blog_post" else "",
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
            "has_summary_skipped": has_summary_skipped,
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

    # Helper to build the EN-summaries manifest (read by verify-emit and the admin
    # Summaries page).
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
        # Dry-run: write a stub manifest, so a dry run leaves the same files as a live one.
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
    results, handle, batch_ids = _submit_and_wait(requests, args, run_deadline=generate_deadline)
    # M5 (2026-05-23): surface silently-failed cache creates — a cache that didn't engage
    # means full-rate input billing with no signal (a burst contributor).
    _cache_create_failures = getattr(handle, "cache_create_failures", 0)
    if _cache_create_failures:
        warnings.append(
            f"explicit cache: {_cache_create_failures} eligible cache(s) failed to create "
            f"— affected requests billed input at full rate (no cache discount)."
        )
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
                        thinking_level=orig.thinking_level,
                    )
                )
        if retry_requests:
            retry_results, _retry_handle, _retry_ids = _submit_and_wait(retry_requests, args, run_deadline=generate_deadline)
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
    # Write the EN-summaries manifest.
    mpath, mcount = _write_en_summaries_manifest(succeeded, sources)
    # tracker-092 (2.1) + tracker-138 (2026-07-13): persist idempotency state per item AS IT IS WRITTEN,
    # not once at the end. Two reasons: (1) DURABILITY — the run is bounded by a wall-clock deadline, so it
    # can stop partway; an end-only save meant a SIGKILL (or the watchdog) lost EVERYTHING and the backlog
    # never drained (the 6-week incident). Incremental + atomic saves mean progress up to the last written
    # item always survives and the CI commit step persists it. (2) CORRECTNESS — checkpoint ONLY items whose
    # Webflow write actually SUCCEEDED (the old end-loop marked every generated item done, so an item that
    # FAILED to write was skipped forever). The callback fires from inside the write loop on each success.
    def _checkpoint_written(sitem) -> None:
        if args.dry_run:
            return
        cid_key = sitem.cms_item_id or sitem.url
        summary_state[cid_key] = {
            "source_hash": _source_hash(
                sitem.body_excerpt, cid_key,
                config.model_for_content_type(sitem.content_type),
            ),
            "generated_at": _now_iso(),
        }
        _save_summary_state(summary_state)

    # Write back. Static pages → JSON. CMS items → Webflow API. Bounded by the shared run deadline (stops
    # STARTING new writes past it and publishes what it already wrote) and checkpoints each written item.
    write_log = _write_back_summaries(
        succeeded, sources, args, out_dir, warnings,
        run_deadline=run_deadline, on_written=_checkpoint_written,
    )

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
        "has_summary_skipped": has_summary_skipped,
        "degraded": degraded,
        "write_log": write_log,
        "manifest_path": str(mpath), "manifest_entries": mcount,
        "manual_review_path": str(manual_review_path),
        "manual_review_count": len(failed),
        "warnings": warnings,
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


# ---- Write-back helpers ----


def _write_back_summaries(
    succeeded: list, sources: list, args: argparse.Namespace, out_dir: Path, warnings: list[str],
    run_deadline: Optional[float] = None, on_written=None,
) -> dict[str, Any]:
    """Write generated summaries to Webflow CMS (CMS items) or to JSON files (static pages).

    tracker-138 (2026-07-13): ``run_deadline`` (an absolute time.monotonic() timestamp) bounds the write
    loop — past it we STOP starting new writes and fall through to publish + return whatever was written,
    so the whole run stays under the job cap. ``on_written(item)`` is invoked after each SUCCESSFUL write
    so the caller can checkpoint idempotency state incrementally (durable across an early stop).
    """
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
    deferred = 0
    # --publish (autopilot): the item ids successfully written this run, grouped by
    # collection, so we can publish ONLY them to LIVE after the write loop.
    written_by_collection: dict[str, list[str]] = {}

    custom_id_to_source = {
        f"gen-{i}-{item.cms_item_id or item.url[-50:]}": (item, target)
        for i, (item, _kw, target) in enumerate(sources)
    }
    for result in succeeded:
        # tracker-138: stop STARTING new writes past the shared run deadline. The items already written
        # this pass still get published + checkpointed below; the rest are deferred to the next run (their
        # idempotency state was never set, so they are simply re-picked-up — no loss, no double-write).
        if run_deadline is not None and time.monotonic() >= run_deadline:
            deferred = len(succeeded) - (cms_writes + static_writes + failures)
            warnings.append(
                f"run deadline reached during write-back: wrote {cms_writes + static_writes}, "
                f"deferred {deferred} to the next run."
            )
            break
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
                if on_written is not None:
                    on_written(item)
            else:
                failures += 1
                warnings.append(f"static write failed: {item.url}: {wr.error}")
        elif target == "cms" and item.cms_item_id:
            # tracker-098: convert Markdown → HTML before PATCH so the RichText field
            # renders headings + links instead of literal `##` / `[](url)`.
            if item.content_type == "blog_post":
                bodies = {config.SUMMARY_FIELD_SLUG: summary_markdown_to_html(result.content)}
            else:
                # Courses / Housing → 4-part: write ONLY the two RichText bodies
                # (Paragraphs + Content), preserving the author-owned Tagline + Title.
                parts = parse_four_part(result.content)
                bodies = {
                    config.SUMMARY_PARAGRAPH_FIELD_SLUG: four_part_paragraph_html(parts.paragraph),
                    config.SUMMARY_CONTENT_FIELD_SLUG: four_part_content_html(parts.content_md),
                }
            # M1 (2026-05-23): pre-write render guard. Refuse to PATCH a RichText body that
            # still contains literal Markdown link syntax `](` — that means the MD→HTML
            # conversion regressed and the page would show literal `[text](url)` (the
            # historical render-corruption class that shipped undetected). Cheap (no extra
            # CMS read); skip + warn instead of writing corrupt content.
            corrupt_fields = [k for k, v in bodies.items() if "](" in v]
            if corrupt_fields:
                failures += 1
                warnings.append(
                    f"render guard: {item.cms_item_id} field(s) {corrupt_fields} still "
                    f"contain literal Markdown link syntax after MD→HTML conversion; NOT written."
                )
                continue
            if item.content_type == "blog_post":
                wresult = wf.update_item_summary(
                    collection_id=_collection_id_for_content_type(item.content_type),
                    item_id=item.cms_item_id,
                    summary_html=bodies[config.SUMMARY_FIELD_SLUG],
                )
            else:
                wresult = wf.update_item_summary_body(
                    collection_id=_collection_id_for_content_type(item.content_type),
                    item_id=item.cms_item_id,
                    paragraph_html=bodies[config.SUMMARY_PARAGRAPH_FIELD_SLUG],
                    content_html=bodies[config.SUMMARY_CONTENT_FIELD_SLUG],
                )
            if wresult.success:
                cms_writes += 1
                written_by_collection.setdefault(
                    _collection_id_for_content_type(item.content_type), []
                ).append(item.cms_item_id)
                if on_written is not None:
                    on_written(item)
            else:
                failures += 1
                warnings.append(f"cms write failed for {item.cms_item_id}: {wresult.error}")

    # --publish (autopilot): push ONLY the items written this run to LIVE, per
    # collection (never the whole site). Mirrors the offers-auto-extend pattern.
    publish_log: dict[str, Any] = {}
    if getattr(args, "publish", False) and written_by_collection:
        published_total = 0
        publish_failures = 0
        for coll_id, item_ids in written_by_collection.items():
            pres = wf.publish_items(coll_id, item_ids)
            n_pub = len(pres.response.get("publishedItemIds", []) or [])
            published_total += n_pub
            if not pres.success:
                publish_failures += 1
                warnings.append(f"publish failed for collection {coll_id}: {pres.error}")
        publish_log = {
            "requested": sum(len(v) for v in written_by_collection.values()),
            "published": published_total,
            "collection_failures": publish_failures,
        }

    return {
        "cms_writes": cms_writes, "static_writes": static_writes, "failures": failures,
        "deferred": deferred, "publish": publish_log,
    }


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

    URL path prefix differs by collection — verified live via the sitemap:
      blog  → /post/<slug>     (HTTP 200)
      course→ /courses/<slug>  (HTTP 200)
      housing→ /housing/<slug> (HTTP 200) — the housing_new collection. NOTE: this was
               `/pb/<slug>` until 2026-05-24, when housing_new migrated /pb/ → /housing/
               (the slug is unchanged; old /pb/ URLs now 404 / 301). Updated then.
    The previous code hardcoded /post/ for ALL collections, producing 404 URLs
    for housing + courses in the prompt context.
    """
    prefix = {
        "blog_post": "post",
        "course": "courses",
        "housing": "housing",
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
    (deduplicated), minus EXCLUDED_LINK_PATH_SEGMENTS (the legacy per-city housing
    slugs vc/sd/sm). When the source item is housing, also drop other `/housing/`
    DETAIL pages so a housing summary can't link to sibling accommodation pages (the
    `/housing` hub stays linkable; mirrors the prompt rule in prompts/housing.md).

    Housing (2026-05-22, NO cap): the site has many new `/housing` accommodation pages
    (hub + per-city detail pages, in every locale) that need inbound internal links, so
    EVERY housing candidate in the locale is offered — there is no count cap. To make sure
    they actually reach the model (not get buried past the 60-candidate prompt cap in
    `build_user_message`), housing URLs are ordered FIRST after the curated STATIC_PAGES.
    The model still links housing only where contextually relevant (city-matched per the
    prompt), and the link-stuffing + 6–8-link QA caps the total — so abundance in the pool
    does not mean spam in the output. A housing-page summary still excludes other `/housing/`
    DETAIL siblings (keeping only the hub).

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
        llms_urls = llms_index.urls_in_locale_excluding(source_locale, excluded)
    # Housing first (right after the curated STATIC_PAGES), then everything else — so the
    # new accommodation pages survive the downstream 60-candidate prompt cap.
    housing = [u for u in llms_urls if _is_housing_path(u)]
    non_housing = [u for u in llms_urls if not _is_housing_path(u)]
    # A housing-source summary must not link to OTHER housing DETAIL pages (housing.md);
    # the /housing hub stays an acceptable target. Replaces the stale `/pb/` segment-exclude
    # after the housing_new /pb/ → /housing/ migration (2026-05-24).
    if source_content_type == "housing":
        housing = [u for u in housing if not _is_housing_detail_path(u)]
    # City-matched ordering (2026-05-23): when the source post names a city, put THAT city's
    # housing first so a Vancouver post is offered Vancouver apartments/student-houses (not
    # just whichever homestay appears first in llms order). Stable sort preserves order
    # within the city / non-city groups, and the hub (`/housing`, no city slug) stays high.
    city = _detect_city(source_url)
    if city:
        housing.sort(key=lambda u: 0 if (city in u.lower() or u.rstrip("/").endswith("/housing")) else 1)
    seen: set[str] = set()
    out: list[str] = []
    from tools.summary.qa import is_retired_campus_link

    for u in static + housing + non_housing:
        if u in seen or is_retired_campus_link(u):
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


def _is_housing_detail_path(url: str) -> bool:
    """True if `url` is a housing DETAIL page (e.g. `/housing/<slug>`, `/de/unterkunft/<slug>`),
    NOT the hub (`/housing`, `/de/unterkunft`). The hub stays an acceptable link target for a
    housing summary; sibling detail pages do not (housing.md). Locale-prefix aware."""
    import urllib.parse

    segments = [s for s in urllib.parse.urlparse(url).path.strip("/").split("/") if s]
    if segments and segments[0] in _LOCALE_PREFIX_SLUGS:  # skip a leading locale prefix
        segments = segments[1:]
    return len(segments) >= 2 and segments[0] in _HOUSING_ROOT_SLUGS


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
