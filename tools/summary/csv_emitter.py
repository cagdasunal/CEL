"""Consolidated per-language Weglot CSV emitter.

Reads existing Fidelo CSV (semicolon-separated, columns
`id;language_from;language_to;word_from;word_to;type`), appends new Summary
translation rows, deduplicates on (word_from + language_to), atomic-writes.

Existing CSVs live at `data/weglot-imports/<lang>.csv` and are written by
`tools/weglot/csv_export.py`. The Summary script reads them, appends rows,
and writes back — replacing the prior split-file pattern (Fidelo separate
from Summary) with a single consolidated CSV per target language.
"""
from __future__ import annotations

import csv
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

_CSV_COLUMNS = ("id", "language_from", "language_to", "word_from", "word_to", "type")
_CSV_DIALECT = "weglot-semicolon"
_SEPARATOR = ";"


# Register a dialect with semicolon separator (Weglot's required format).
class _WeglotDialect(csv.Dialect):
    delimiter = _SEPARATOR
    quotechar = '"'
    doublequote = True
    skipinitialspace = False
    lineterminator = "\n"
    quoting = csv.QUOTE_MINIMAL


csv.register_dialect(_CSV_DIALECT, _WeglotDialect)


@dataclass(frozen=True)
class SummaryPair:
    """One row pair: source English paragraph → target-language translation."""

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
    summary_pairs: Sequence[SummaryPair],
    out_path: Path,
) -> EmissionReport:
    """Merge existing Fidelo rows with new Summary rows; atomic-write to out_path.

    Idempotent: re-running with the same inputs produces byte-identical output.
    Dedup key: (word_from, language_to). Existing rows are preserved as-is;
    new rows are appended in order; collisions (same word_from + language_to)
    are skipped.
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

    # Append Summary pairs.
    for pair in summary_pairs:
        key = (pair.word_from, target_locale)
        if key in seen:
            report.duplicates_skipped += 1
            continue
        seen.add(key)
        rows.append(pair.as_row(target_locale))
        report.new_row_count += 1

    # Atomic write — write to tempfile in same directory, then rename.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=f".{out_path.name}.", suffix=".tmp", dir=str(out_path.parent)
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, dialect=_CSV_DIALECT)
            for row in rows:
                writer.writerow(row)
        os.replace(tmp_path, out_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    report.written_to = out_path
    return report


def split_summary_into_paragraphs(rich_text_html_or_markdown: str) -> list[str]:
    """Split a rich-text Summary into paragraphs for row-level translation.

    Per LOCKED DECISION: ONE row per paragraph (not per sentence). Handles both
    plain Markdown (blank-line-separated) and Webflow rich-text HTML (`<p>` tags).
    """
    text = rich_text_html_or_markdown.strip()
    if not text:
        return []

    # Strip simple `<p>...</p>` wrappers if present.
    if "<p" in text:
        import re

        parts = re.findall(r"<p[^>]*>(.*?)</p>", text, re.DOTALL | re.IGNORECASE)
        cleaned = [_strip_html(p).strip() for p in parts]
        return [p for p in cleaned if p]

    # Markdown: split on double-newline.
    parts = [p.strip() for p in text.split("\n\n")]
    return [p for p in parts if p]


def _strip_html(s: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", s)


def pair_from_paragraphs(
    en_paragraphs: Sequence[str], translated_paragraphs: Sequence[str]
) -> list[SummaryPair]:
    """Zip EN paragraphs with translated paragraphs into SummaryPair objects.

    Caller is responsible for ensuring both sequences are the same length and
    aligned (Claude produces paragraph-for-paragraph translations).
    """
    if len(en_paragraphs) != len(translated_paragraphs):
        raise ValueError(
            f"paragraph count mismatch: en={len(en_paragraphs)} "
            f"target={len(translated_paragraphs)}"
        )
    return [
        SummaryPair(word_from=src, word_to=tgt)
        for src, tgt in zip(en_paragraphs, translated_paragraphs)
        if src.strip()
    ]
