"""Translation memory — never re-translate an unchanged source string.

Minimal viable TM (Phase 3 research): a single JSON file keyed by
sha256(normalize(source) + locale + glossary_version + tone + prompt_version).
Including glossary_version is mandatory — a glossary change must invalidate
stale hits. So is prompt_version, for the same reason and a sharper one: the
locale prompt files carry the register rules, so an edit to `de.md` that swaps
*Sie* for *du* changes nothing at all while the cache still answers. That is not
hypothetical — without this term such a fix regenerates byte-identical copy and reports
success.
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


# ASCII whitespace ONLY. Python's `\s` also matches U+00A0 and U+202F, so a
# `\s+` normaliser silently folds "Tarifs\u00a0: 100" and "Tarifs : 100" onto one
# key and serves the same translation for both. French requires a non-breaking
# space before `:` `;` `?` `!` `»` (per-language rules §7.2/§9), so that collision
# corrupts exactly the locale with the strictest typography rule.
_WS = re.compile(r"[ \t\r\n\f\v]+")


def _normalize(source: str) -> str:
    """Collapse ASCII whitespace so trivial reformatting doesn't bust the cache.

    Deliberately does NOT touch U+00A0 / U+202F — they are meaningful content.
    """
    return _WS.sub(" ", source).strip()


def tm_key(source: str, locale: str, glossary_version: str, tone: str = "",
           prompt_version: str = "") -> str:
    payload = (f"{_normalize(source)}\x00{locale}\x00{glossary_version}"
               f"\x00{tone}\x00{prompt_version}")
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
            except (OSError, ValueError) as e:
                # T7 (2026-05-23): a corrupt TM file silently became {} (cache loss with
                # no signal). Warn so the loss is visible; still degrade to empty — the TM
                # is an optimization, never load-bearing, so this must not be fatal.
                import sys as _sys

                print(
                    f"[translator.tm] WARNING: could not load translation memory at "
                    f"{path} ({e}); starting empty (cache is not load-bearing).",
                    file=_sys.stderr,
                )
                self._store = {}

    def get(self, source: str, locale: str, glossary_version: str, tone: str = "",
            prompt_version: str = "") -> str | None:
        entry = self._store.get(
            tm_key(source, locale, glossary_version, tone, prompt_version))
        return entry.get("target") if isinstance(entry, dict) else None

    def put(self, source: str, locale: str, glossary_version: str, target: str,
            tone: str = "", prompt_version: str = "") -> None:
        key = tm_key(source, locale, glossary_version, tone, prompt_version)
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
