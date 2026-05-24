"""Weglot match-verification gate (audit-108 H-1, 2026-05-24).

Weglot applies an imported CSV row only when its `word_from` byte-equals a text node
Weglot extracted from the live page ("read, parse, cut" of the HTML — Weglot Help Center
206/432). A correctly-FORMATTED row whose `word_from` matches no live node is silently
ignored → Weglot machine-translates instead. That mismatch — not the CSV format — was the
root cause of the translation-import struggle (audit 108 §3).

This module is the missing gate: for each translatable page it re-derives the live summary
nodes (the SAME normalization the emit uses, via `structure.summary_page_blocks`) and checks
how many appear as `word_from` in the per-locale CSV — answering, per page + locale, "how
many of this summary's blocks will Weglot actually apply?".

Pure logic + injectable I/O: `verify_pages` takes a `fetch` callback and reads CSVs from
disk, so tests never hit the network. Import-safe (no module-level I/O).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from tools.summary import structure
from tools.translator.weglot import read_existing_csv

# Content types that ARE translated (blog is native-per-locale; others are EN-only).
TRANSLATABLE_CONTENT_TYPES = ("landing", "course", "housing")


def live_summary_nodes(parts_or_markdown) -> list[str]:
    """The page's rendered summary blocks as PLAIN TEXT — the strings Weglot keys on.

    Accepts either the `existing_summary_parts` dict (from page_fetcher) or raw Markdown;
    both route through `structure.summary_page_blocks`, so the comparison is apples-to-
    apples with what the translate phase emits as `word_from`.
    """
    if isinstance(parts_or_markdown, dict):
        md = structure.parts_to_markdown(parts_or_markdown or {})
    else:
        md = parts_or_markdown or ""
    return structure.summary_page_blocks(md)


def csv_word_from_set(csv_path: Path) -> set[str]:
    """Set of `word_from` values (col 3) in a Weglot CSV, excluding the header. {} if absent."""
    out: set[str] = set()
    for row in read_existing_csv(Path(csv_path)):
        if len(row) >= 4 and row[0] != "id":  # skip the header row
            out.add(row[3].strip())
    return out


def verify_pages(
    en_summaries: dict,
    csv_dir: Path,
    locales: Iterable[str],
    fetch: Callable[[str], object],
) -> dict:
    """Check each translatable page's live summary nodes against the per-locale CSVs.

    For every translatable item in `en_summaries`, fetch the live page via `fetch(url)`
    (returns an object exposing `existing_summary_parts`), derive its summary node set,
    and count how many nodes are present as `word_from` in each locale's CSV. A node not
    present means Weglot will machine-translate that block instead of applying our row.

    Returns `{pages: [...], aggregate: {locale: {matched,total,rate}}, locales: [...]}`.
    Read-only; no network unless `fetch` performs one.
    """
    locales = list(locales)
    csv_dir = Path(csv_dir)
    csv_sets = {loc: csv_word_from_set(csv_dir / f"{loc}.csv") for loc in locales}

    pages: list[dict] = []
    for cid, en in en_summaries.items():
        if en.get("content_type") not in TRANSLATABLE_CONTENT_TYPES:
            continue
        url = en.get("url", "")
        try:
            pc = fetch(url)
            parts = getattr(pc, "existing_summary_parts", None) or {}
            nodes = live_summary_nodes(parts) or live_summary_nodes(en.get("markdown", ""))
        except Exception as e:  # noqa: BLE001 — a fetch failure is a per-page finding, not fatal
            pages.append({"cid": cid, "url": url, "error": str(e)})
            continue
        per_locale: dict[str, dict] = {}
        for loc in locales:
            wf = csv_sets[loc]
            missing = [n for n in nodes if n.strip() not in wf]
            per_locale[loc] = {
                "matched": len(nodes) - len(missing),
                "total": len(nodes),
                "missing": missing,
            }
        pages.append({
            "cid": cid, "url": url, "content_type": en.get("content_type"),
            "nodes": len(nodes), "per_locale": per_locale,
        })

    aggregate: dict[str, dict] = {}
    scored = [p for p in pages if "per_locale" in p]
    for loc in locales:
        matched = sum(p["per_locale"][loc]["matched"] for p in scored)
        total = sum(p["per_locale"][loc]["total"] for p in scored)
        aggregate[loc] = {
            "matched": matched, "total": total,
            "rate": round(matched / total, 4) if total else 0.0,
        }
    return {"pages": pages, "aggregate": aggregate, "locales": locales}


def format_report(result: dict) -> str:
    """Render a `verify_pages` result as a compact human-readable report."""
    lines: list[str] = []
    locales = result.get("locales", [])
    lines.append(f"Weglot match-verification — {len(result.get('pages', []))} pages × {len(locales)} locales")
    for p in result.get("pages", []):
        if "error" in p:
            lines.append(f"  ! {p.get('url')}: FETCH FAILED ({p['error']})")
            continue
        cells = []
        for loc in locales:
            pl = p["per_locale"][loc]
            cells.append(f"{loc} {pl['matched']}/{pl['total']}")
        lines.append(f"  {p['url']}  ({p['nodes']} nodes)  " + "  ".join(cells))
    lines.append("  ── aggregate ──")
    for loc in locales:
        a = result["aggregate"][loc]
        lines.append(f"  {loc}: {a['matched']}/{a['total']} blocks will apply ({a['rate']*100:.0f}%)")
    return "\n".join(lines)


def all_pages_full_match(result: dict) -> bool:
    """True iff every scored page matches 100% in every locale (gate pass/fail)."""
    for p in result.get("pages", []):
        if "error" in p:
            return False
        for loc in result.get("locales", []):
            pl = p["per_locale"][loc]
            if pl["total"] and pl["matched"] != pl["total"]:
                return False
    return True
