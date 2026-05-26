"""Append-only run ledger for the summary / translation pipeline.

Why this exists
---------------
Per-run ``report.json`` files are scattered one-per-out-dir, and the live
status artifacts (``summary-state.json``, ``translation-status.json``) are
*overwritten* every run — so they answer "what is the latest state?" but not
"what ran, when, and with what result?". Reconstructing the timeline meant
forensically cross-referencing run dirs, ``.log`` files and git commits.

This module closes that gap: ``cli.main()`` appends ONE compact JSON line here
at the end of every run (auto-wired, in a ``finally`` that can never break the
run). ``python3 -m tools.summary status`` reads it back.

The ledger is the chronological history; ``summary-state.json`` /
``translation-status.json`` remain the authoritative "latest state".

Schema (one JSON object per line, ``run-ledger.jsonl``)::

    {
      "started_at": ISO8601, "finished_at": ISO8601,
      "subcommand": "translate", "dry_run": false, "out_dir": "<dir-name>",
      "generate_english": {"requests_built": N, "idempotency_skipped": N, "submitted": bool},
      "translate": {"locales": [...], "per_locale": {"de": {"translated": N,
                    "tm_hits": N, "gemini_calls": N, "failed": N}}}
    }

Fields are best-effort: a phase absent from the run is simply omitted.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _default_ledger_path() -> Path:
    # Lazy import so the module stays importable without config side effects.
    from tools.summary import config

    return config.SUMMARY_STATE_FILE.parent / "run-ledger.jsonl"


def _compact_entry(report: dict, out_dir: Path) -> dict:
    """Derive a compact ledger line from a full report dict. Defensive: every
    lookup tolerates a missing / differently-shaped phase result."""
    phases = report.get("phases", {}) if isinstance(report, dict) else {}
    entry: dict[str, Any] = {
        "started_at": report.get("started_at"),
        "finished_at": report.get("finished_at"),
        "subcommand": report.get("subcommand"),
        "dry_run": report.get("dry_run"),
        "out_dir": out_dir.name if isinstance(out_dir, Path) else str(out_dir),
    }

    ge = phases.get("generate_english")
    if isinstance(ge, dict):
        entry["generate_english"] = {
            k: ge.get(k)
            for k in ("requests_built", "idempotency_skipped", "submitted",
                      "target_count", "sources_resolved")
            if ge.get(k) is not None
        }

    tr = phases.get("translate")
    if isinstance(tr, dict):
        per = tr.get("per_locale", {})
        per_out: dict[str, Any] = {}
        if isinstance(per, dict):
            for loc, r in per.items():
                if not isinstance(r, dict):
                    continue
                per_out[loc] = {
                    k: r.get(k)
                    for k in ("translated", "succeeded", "tm_hits",
                              "gemini_calls", "failed", "request_count",
                              "rows_appended", "skipped")
                    if r.get(k) is not None
                }
        entry["translate"] = {
            "locales": tr.get("target_locales"),
            "per_locale": per_out,
        }
    return entry


def record_run(report: dict, out_dir: Path, path: Optional[Path] = None) -> None:
    """Append one compact line for this run. NEVER raises — a ledger write must
    not be able to fail a real pipeline run (wrapped by the caller's finally,
    and defensively here too)."""
    try:
        target = Path(path) if path is not None else _default_ledger_path()
        entry = _compact_entry(report, Path(out_dir))
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — ledger is never load-bearing
        pass


def read_ledger(path: Optional[Path] = None) -> list[dict]:
    """Return all ledger entries (oldest first). Skips blank / corrupt lines."""
    target = Path(path) if path is not None else _default_ledger_path()
    if not target.exists():
        return []
    out: list[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _load_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def format_status(
    ledger_path: Optional[Path] = None,
    summary_state_path: Optional[Path] = None,
    translation_status_path: Optional[Path] = None,
    recent: int = 12,
) -> str:
    """Human-readable 'what ran when' across summaries + translations.

    Reads only local artifacts (no network, no API): the run ledger, the
    generate-english idempotency state, and the last translation-status."""
    from tools.summary import config

    ledger = read_ledger(ledger_path)
    ss_path = Path(summary_state_path) if summary_state_path else config.SUMMARY_STATE_FILE
    ts_path = (Path(translation_status_path) if translation_status_path
               else config.WEGLOT_IMPORTS_DIR / "translation-status.json")
    summary_state = _load_json(ss_path) or {}
    translation_status = _load_json(ts_path) or {}

    lines: list[str] = []
    lines.append("SUMMARY / TRANSLATION STATUS")
    lines.append("=" * 60)

    # --- Summaries (generate-english) ---
    lines.append("")
    lines.append("Summaries (generate-english)")
    if isinstance(summary_state, dict) and summary_state:
        gens = sorted(
            (v.get("generated_at", "") for v in summary_state.values()
             if isinstance(v, dict)),
            reverse=True,
        )
        gens = [g for g in gens if g]
        latest = gens[0][:19].replace("T", " ") if gens else "—"
        earliest = gens[-1][:19].replace("T", " ") if gens else "—"
        lines.append(f"  pages tracked : {len(summary_state)}")
        lines.append(f"  last generated: {latest}")
        lines.append(f"  oldest        : {earliest}")
    else:
        lines.append("  (no summary-state.json)")

    # --- Translations (translate) ---
    lines.append("")
    lines.append("Translations (last run — translation-status.json)")
    if isinstance(translation_status, dict) and translation_status.get("per_locale"):
        gen_at = (translation_status.get("generated_at", "") or "")[:19].replace("T", " ")
        lines.append(f"  generated_at  : {gen_at}   source_run={translation_status.get('source_run','?')}")
        lines.append(f"  {'locale':6}  {'translated':>10}  {'failed':>6}  {'words':>7}")
        for loc, r in sorted(translation_status["per_locale"].items()):
            if not isinstance(r, dict):
                continue
            lines.append(
                f"  {loc:6}  {str(r.get('translated','?')):>10}  "
                f"{str(r.get('failed','?')):>6}  {str(r.get('words','?')):>7}"
            )
    else:
        lines.append("  (no translation-status.json)")

    # --- Recent runs (ledger) ---
    lines.append("")
    lines.append(f"Recent runs (ledger, last {recent})")
    if ledger:
        for e in ledger[-recent:]:
            ts = (e.get("finished_at") or e.get("started_at") or "")[:19].replace("T", " ")
            mode = "dry " if e.get("dry_run") else "LIVE"
            sub = e.get("subcommand", "?")
            extra = ""
            tr = e.get("translate")
            if isinstance(tr, dict) and tr.get("locales"):
                locs = tr["locales"]
                extra = f"  [{len(locs)} loc: {','.join(locs[:6])}{'…' if len(locs) > 6 else ''}]"
            ge = e.get("generate_english")
            if isinstance(ge, dict) and ge.get("requests_built") is not None:
                extra += f"  built={ge.get('requests_built')} skipped={ge.get('idempotency_skipped', 0)}"
            lines.append(f"  {ts}  {mode}  {sub:16}{extra}")
    else:
        lines.append("  (ledger empty — no runs recorded yet)")

    lines.append("")
    return "\n".join(lines)
