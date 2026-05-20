"""Translation unit + result dataclasses (tracker-092 Phase 3).

Callers pass neutral `TranslationUnit`s and get back `Translation`s. The engine
never sees caller-specific concepts (Webflow, Weglot CSV, summary paragraphs) —
that keeps it reusable across the summary-translate and meta-tag callers.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TranslationUnit:
    """One source string to translate.

    id          stable caller key (round-trips to the Translation). For the
                summary caller this is the batch custom_id `tr-<locale>-<cid>`;
                for the meta caller `meta-<field>-<page-slug>`.
    text        the English source text.
    content_type a hint the caller can use ("marketing", "meta_title", ...);
                the engine passes it to the request builder, doesn't interpret it.
    context     optional disambiguation hint surfaced in the prompt (e.g. link
                swap instructions for summary markdown).
    """

    id: str
    text: str
    content_type: str = "marketing"
    context: str = ""


@dataclass(frozen=True)
class Translation:
    """One translated result.

    from_tm   True when served from the translation memory (no API call).
    qa_flags  list of QA findings (e.g. "untranslated_passthrough",
              "number_drift:12", "length_ratio:3.1"); empty = clean.
    ok        False when a BLOCKING QA check failed (placeholder/number/URL),
              a forbidden glossary term is present, or the translation is empty.
              Callers MUST NOT ship a translation with ok=False (tracker-095 H1).
    """

    id: str
    source: str
    target: str
    target_locale: str
    from_tm: bool = False
    qa_flags: list[str] = field(default_factory=list)
    ok: bool = True
