"""Weglot CSV emission — the reusable translate→CSV output adapter (tracker-094).

Relocated from `tools/summary/csv_emitter.py` so the `translator` package owns the
Weglot import-CSV format and any tool can produce one. Format is byte-identical to
the Fidelo exporter `tools/weglot/csv_export.py` (monorepo), so translator rows and
Fidelo rows interleave cleanly in the same per-locale file:

    id;language_from;language_to;word_from;word_to;type   (semicolon, minimal-quote)

`emit_consolidated_csv` reads the existing CSV (which already holds Fidelo rows),
dedups on (word_from, language_to), appends the new rows, and atomic-writes — so a
translator run never clobbers Fidelo translations. The CSVs are published on the
dashboard.

Pure stdlib; no dependency on the summary tool, so other projects can reuse it.
"""
from __future__ import annotations

import csv
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from tools.translator.units import Translation

_CSV_COLUMNS = ("id", "language_from", "language_to", "word_from", "word_to", "type")
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
    """Wrap in double quotes, escaping internal `"` as `""`. Byte-identical to
    the Fidelo exporter `tools/weglot/csv_export.py:_weglot_quote` (tracker-095
    I1) — the Fidelo writer ALWAYS quotes word_from/word_to, leaving id, the
    language codes, and type bare. `csv.QUOTE_MINIMAL` omitted quotes on
    quote-free values, so the two outputs diverged; this restores parity."""
    return '"' + s.replace('"', '""') + '"'


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


def pairs_from_translations(
    translations: Iterable[Translation], type_: str = "Text"
) -> list[WeglotPair]:
    """Map engine `Translation` objects → Weglot rows (one row per translation).

    Skips empty/failed targets. This is the simple 1:1 path for callers whose
    units map directly to rows (meta tags, future tools). The summary caller uses
    paragraph-level pairing instead (see csv_emitter.pair_from_paragraphs).
    """
    return [
        WeglotPair(word_from=t.source, word_to=t.target, type_=type_)
        for t in translations
        if t.target.strip()
    ]


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

    # Atomic write — match the Fidelo exporter byte-for-byte (tracker-095 I1):
    # header + id/language/type cells bare; word_from/word_to ALWAYS quoted with
    # `""` escaping. (csv.writer + QUOTE_MINIMAL omits quotes on simple values,
    # which diverged from tools/weglot/csv_export.py.)
    def _fmt_row(r: list[str]) -> str:
        if r == list(_CSV_COLUMNS):
            return _SEPARATOR.join(r)  # header stays bare
        cells = list(r)
        cells[3] = _weglot_quote(cells[3])  # word_from
        cells[4] = _weglot_quote(cells[4])  # word_to
        return _SEPARATOR.join(cells)

    out_text = "\n".join(_fmt_row(r) for r in rows) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=f".{out_path.name}.", suffix=".tmp", dir=str(out_path.parent)
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(out_text)
        os.replace(tmp_path, out_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    written_bytes = len(out_text.encode("utf-8"))
    if written_bytes >= _WEGLOT_IMPORT_WARN_BYTES:
        report.warnings.append(
            f"{target_locale}: CSV is {written_bytes / 1_000_000:.1f} MB, approaching "
            f"Weglot's 5 MB import limit — split the file or prune stale rows before importing"
        )

    report.written_to = out_path
    return report
