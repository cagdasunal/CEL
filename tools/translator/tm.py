"""Translation memory — never re-translate an unchanged source string.

Minimal viable TM (Phase 3 research): a single JSON file keyed by
sha256(normalize(source) + locale + glossary_version + tone). Including
glossary_version is mandatory — a glossary change must invalidate stale hits.
Exact-match only (no fuzzy matching). SQLite is a documented future swap behind
the same interface; not needed at CEL's scale.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


# tracker-093 L3: cap the memory so the JSON file can't grow unbounded across
# runs (the repo's documented anti-pattern). Generous — at CEL's scale (~756
# URLs × paragraphs × 8 locales) this won't bite in normal use; it's a safety
# valve. FIFO eviction (oldest insertion first); a bumped glossary_version
# naturally ages out stale keys anyway.
_MAX_ENTRIES = 20000


def _normalize(source: str) -> str:
    """Collapse whitespace so trivial reformatting doesn't bust the cache."""
    return re.sub(r"\s+", " ", source).strip()


def tm_key(source: str, locale: str, glossary_version: str, tone: str = "") -> str:
    payload = f"{_normalize(source)}\x00{locale}\x00{glossary_version}\x00{tone}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TranslationMemory:
    """JSON-backed exact-match translation memory.

    Construct with a path; call get()/put() during a run; call save() once at
    the end. In-memory until save() to avoid per-write disk churn.
    """

    def __init__(self, path: Path | None):
        self.path = path
        self._store: dict[str, dict] = {}
        if path and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._store = data
            except (OSError, ValueError):
                self._store = {}

    def get(self, source: str, locale: str, glossary_version: str, tone: str = "") -> str | None:
        entry = self._store.get(tm_key(source, locale, glossary_version, tone))
        return entry.get("target") if isinstance(entry, dict) else None

    def put(self, source: str, locale: str, glossary_version: str, target: str, tone: str = "") -> None:
        key = tm_key(source, locale, glossary_version, tone)
        # FIFO eviction when at capacity for a NEW key (updating an existing key
        # never grows the store). Dict preserves insertion order, so the first
        # key is the oldest.
        if key not in self._store and len(self._store) >= _MAX_ENTRIES:
            self._store.pop(next(iter(self._store)))
        self._store[key] = {
            "target": target,
            "locale": locale,
            "glossary_version": glossary_version,
            "source_preview": _normalize(source)[:80],
        }

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tfd, tpath = tempfile.mkstemp(dir=str(self.path.parent), prefix=".tm.", suffix=".tmp")
        try:
            with os.fdopen(tfd, "w", encoding="utf-8") as f:
                json.dump(self._store, f, indent=2, ensure_ascii=False)
            os.replace(tpath, self.path)
        except OSError:
            try:
                os.remove(tpath)
            except OSError:
                pass
            raise

    def __len__(self) -> int:
        return len(self._store)
