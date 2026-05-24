"""The canonical Weglot import-CSV engine — format + IO, shared across CEL tools.

ONE source of truth for the Weglot translation-import CSV format:

    id;language_from;language_to;word_from;word_to;type

(semicolon-delimited; header bare; `word_from`/`word_to` ALWAYS double-quoted with
`""` escaping; `id`/`language_*`/`type` cells bare; UTF-8 with NO BOM; LF line endings.)

Consumers — vendored BYTE-IDENTICAL in cagdasunal/CEL and cagdasunal/webflow, kept in
lockstep by `system_inspector.check_dashboard_parity`:
  - CEL  `tools/translator/weglot.py`   — translator + summary (re-exports this module
    and adds the `Translation`→`WeglotPair` adapter `pairs_from_translations`).
  - monorepo `tools/weglot/csv_export.py`  — Fidelo per-locale exporter (`write_csv`).
  - monorepo `tools/weglot/mirror_csvs.py` — merges Fidelo + translator rows into the
    published per-locale CSVs.

Pure stdlib; import-safe; `Translation`-free so any tool can reuse it. Created in the
weglot-engine consolidation (2026-05-24) by extracting the format+IO core that had been
duplicated by hand across the three consumers above.
"""
from __future__ import annotations

import csv
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

_CSV_COLUMNS = ("id", "language_from", "language_to", "word_from", "word_to", "type")
# Public alias (review-109 LOW-2): consumers (csv_export, mirror_csvs, future tools)
# import the public `CSV_COLUMNS` instead of reaching into the private `_CSV_COLUMNS`.
# `_CSV_COLUMNS` stays the primary name used internally below (same tuple object).
CSV_COLUMNS = _CSV_COLUMNS
_CSV_DIALECT = "weglot-semicolon"
_SEPARATOR = ";"

# Weglot's GENERAL translation CSV import — the word_from/word_to overrides this
# emitter produces — has NO documented row maximum; the only limits are a 5 MB
# file size and a UTF-8 encoding requirement (Weglot Help Center articles 432 +
# 206, 2026). The separate 500-element cap applies to Dynamic Content / URL-slug /
# Exclusion-rule imports, NOT this file (verified tracker-098 T5; live locale
# files are 538-593 rows and import fine — a row-count cap on this CSV is a
# non-applicable limit). So we guard the REAL constraint: warn if the written file
# approaches 5 MB. The largest live file today is ~222 KB, so this is dormant
# headroom that fires only if the consolidated CSV genuinely grows toward the cap.
# Decimal MB (5,000,000), not MiB: Weglot states "5 MB" and web file-size limits
# are conventionally decimal. Using the smaller value means the warning never
# *under*-warns relative to the real cap (review 104 M1).
_WEGLOT_IMPORT_MAX_BYTES = 5 * 1000 * 1000  # 5 MB — Weglot CSV import hard limit
_WEGLOT_IMPORT_WARN_BYTES = int(_WEGLOT_IMPORT_MAX_BYTES * 0.9)  # warn at 90% (4.5 MB)


# Register a dialect with semicolon separator (Weglot's required format).
class _WeglotDialect(csv.Dialect):
    delimiter = _SEPARATOR
    quotechar = '"'
    doublequote = True
    skipinitialspace = False
    lineterminator = "\n"
    quoting = csv.QUOTE_MINIMAL


csv.register_dialect(_CSV_DIALECT, _WeglotDialect)


def _weglot_quote(s: str) -> str:
    """Wrap in double quotes, escaping internal `"` as `""`. The Fidelo writer + this
    engine ALWAYS quote word_from/word_to, leaving id, the language codes, and type
    bare. `csv.QUOTE_MINIMAL` omitted quotes on quote-free values, so the two outputs
    diverged historically (tracker-095 I1); this is the single canonical implementation."""
    return '"' + s.replace('"', '""') + '"'


# Public alias (the consolidation, 2026-05-24): new tools import `weglot_quote`;
# `_weglot_quote` stays the primary name so existing importers (csv_export, mirror_csvs)
# keep working unchanged.
weglot_quote = _weglot_quote


def _format_row(r: list[str]) -> str:
    """One CSV row: header + id/lang/type bare; word_from/word_to ALWAYS quoted with
    `""` escaping (Fidelo-exporter parity, tracker-095 I1)."""
    if r == list(_CSV_COLUMNS):
        return _SEPARATOR.join(r)  # header stays bare
    cells = list(r)
    cells[3] = _weglot_quote(cells[3])  # word_from
    cells[4] = _weglot_quote(cells[4])  # word_to
    return _SEPARATOR.join(cells)


def format_csv_text(rows: Sequence[Sequence[str]]) -> str:
    """Render rows to Weglot CSV text (trailing LF). The single canonical row writer."""
    return "\n".join(_format_row(list(r)) for r in rows) + "\n"


def atomic_write_text(path: Path, text: str) -> None:
    """Atomic UTF-8 write (no BOM) with LF newlines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


# audit-108 M-1/M-2: a `word_from` that begins with an ATX heading marker (`## …`) or
# contains a markdown link (`[text](url)`) is an unambiguous STALE summary chunk from the
# pre-block-level emission — it can never match a rendered page node, and Fidelo/meta rows
# never carry this markdown. So it is safe to purge. (Clean block rows + Fidelo + meta have
# no such markdown; a bare URL or "(ESTA)" is NOT matched — the link form needs `](`.)
_STALE_SUMMARY_WF_RE = re.compile(r"^\s*#{1,6}\s|\[[^\]]*\]\([^)]*\)")


def is_stale_summary_word_from(word_from: str) -> bool:
    """True iff `word_from` is an unambiguous stale (markdown-laden) summary chunk."""
    return bool(_STALE_SUMMARY_WF_RE.search(word_from or ""))


def filter_out_stale_summary_rows(
    rows: Sequence[Sequence[str]],
) -> tuple[list[list[str]], list[list[str]]]:
    """Split CSV rows into (kept, dropped). The header, Fidelo rows, meta rows, and clean
    block rows are KEPT; only rows whose `word_from` is a stale summary chunk are dropped."""
    kept: list[list[str]] = []
    dropped: list[list[str]] = []
    for r in rows:
        r = list(r)
        if len(r) >= 4 and r[0] != "id" and is_stale_summary_word_from(r[3]):
            dropped.append(r)
        else:
            kept.append(r)
    return kept, dropped


@dataclass(frozen=True)
class WeglotPair:
    """One Weglot row: source English text → target-language translation."""

    word_from: str
    word_to: str
    type_: str = "Text"

    def as_row(self, target_locale: str) -> list[str]:
        return ["", "en", target_locale, self.word_from, self.word_to, self.type_]


@dataclass
class EmissionReport:
    existing_row_count: int = 0
    new_row_count: int = 0
    duplicates_skipped: int = 0
    written_to: Path | None = None
    warnings: list[str] = field(default_factory=list)


def read_existing_csv(path: Path) -> list[list[str]]:
    """Read an existing Weglot CSV. Returns [] if the file doesn't exist."""
    if not path.exists():
        return []
    rows: list[list[str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, dialect=_CSV_DIALECT)
        for row in reader:
            if len(row) == len(_CSV_COLUMNS):
                rows.append(row)
    return rows


def emit_consolidated_csv(
    target_locale: str,
    existing_csv_path: Path,
    summary_pairs: Sequence[WeglotPair],
    out_path: Path,
) -> EmissionReport:
    """Merge existing rows (incl. Fidelo) with new translation rows; atomic-write.

    Idempotent: re-running with the same inputs produces byte-identical output.
    Dedup key: (word_from, language_to). Existing rows are preserved as-is; new
    rows are appended in order; collisions (same word_from + language_to) are
    skipped. (`summary_pairs` is the historical param name; it accepts any
    WeglotPair sequence.)
    """
    report = EmissionReport()
    rows: list[list[str]] = []
    seen: set[tuple[str, str]] = set()
    header_written = False

    existing = read_existing_csv(existing_csv_path)
    for row in existing:
        if not header_written and row == list(_CSV_COLUMNS):
            rows.append(row)
            header_written = True
            continue
        key = (row[3], row[2])  # word_from, language_to
        if key in seen:
            report.duplicates_skipped += 1
            continue
        seen.add(key)
        rows.append(row)
        report.existing_row_count += 1

    # If no header was found (e.g. brand-new file), prepend one.
    if not header_written:
        rows.insert(0, list(_CSV_COLUMNS))

    # Append translation pairs.
    for pair in summary_pairs:
        key = (pair.word_from, target_locale)
        if key in seen:
            report.duplicates_skipped += 1
            continue
        seen.add(key)
        rows.append(pair.as_row(target_locale))
        report.new_row_count += 1

    # Atomic write — header + id/language/type cells bare; word_from/word_to ALWAYS
    # quoted with `""` escaping (see _format_row / format_csv_text).
    out_text = format_csv_text(rows)
    atomic_write_text(out_path, out_text)

    written_bytes = len(out_text.encode("utf-8"))
    if written_bytes >= _WEGLOT_IMPORT_WARN_BYTES:
        report.warnings.append(
            f"{target_locale}: CSV is {written_bytes / 1_000_000:.1f} MB, approaching "
            f"Weglot's 5 MB import limit — split the file or prune stale rows before importing"
        )

    report.written_to = out_path
    return report
