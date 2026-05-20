"""Glossary: do-not-translate / forbidden / preferred term enforcement.

Per the Phase 3 research: per-unit lexical match (inject only the terms present
in a given source string). Enforcement tiers (tracker-095 M2):
  - **forbidden** term in the output → BLOCKING (the engine sets `ok=False`).
  - **do-not-translate** → enforced via the prompt; `enforce()` only flags (warn)
    if a source DNT term vanished from the target — it never rewrites the text.
  - **preferred** → SOFT (warn only).
Over-rigid post-edit replacement lowers quality, so `enforce()` never rewrites;
the one hard gate (forbidden) lives in the engine.

The default glossary lives in `glossary.json` next to this module and is seeded
from CEL's brand/entity terms (the same entities common.md spells out). Bump
`version` whenever it changes — the translation memory keys on the version so a
glossary change invalidates stale cached translations.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parent / "glossary.json"


@dataclass(frozen=True)
class GlossaryTerm:
    term: str
    do_not_translate: bool = False
    forbidden: bool = False
    preferred: dict[str, str] = field(default_factory=dict)  # locale -> preferred translation
    case_sensitive: bool = False


@dataclass
class Glossary:
    terms: list[GlossaryTerm]
    version: str = "0"

    def match(self, text: str) -> list[GlossaryTerm]:
        """Return the glossary terms that occur in `text` (word-boundary match)."""
        out: list[GlossaryTerm] = []
        for t in self.terms:
            flags = 0 if t.case_sensitive else re.IGNORECASE
            if re.search(rf"\b{re.escape(t.term)}\b", text, flags):
                out.append(t)
        return out

    def prompt_slice(self, matched: list[GlossaryTerm], locale: str) -> str:
        """Render matched terms as a short instruction block for the system prompt."""
        if not matched:
            return ""
        dnt = [t.term for t in matched if t.do_not_translate]
        forbidden = [t.term for t in matched if t.forbidden]
        preferred = [
            f"{t.term} → {t.preferred[locale]}"
            for t in matched
            if locale in t.preferred
        ]
        lines = ["## Terminology (obey exactly)"]
        if dnt:
            lines.append("Keep these terms VERBATIM (do not translate): " + ", ".join(dnt) + ".")
        if preferred:
            lines.append("Preferred translations: " + "; ".join(preferred) + ".")
        if forbidden:
            lines.append("NEVER use these words: " + ", ".join(forbidden) + ".")
        return "\n".join(lines)

    def enforce(self, source: str, target: str, locale: str) -> tuple[str, list[str]]:
        """Post-edit: flag glossary violations. Does NOT rewrite the target.

        Returns (target unchanged, list of flags):
          - `forbidden_term_present:<t>` — the engine treats this as BLOCKING
            (sets ok=False); a forbidden word must never reach output.
          - `dnt_term_dropped:<t>` — advisory; do-not-translate is enforced by
            the prompt, this only warns when a source DNT term vanished.
          - `preferred_not_used:<t>` — advisory (SOFT); never force-replaced.
        We never force-replace text here, to avoid the over-rigid quality penalty
        the research flagged — forbidden is the single hard gate (in the engine).
        """
        flags: list[str] = []
        # DNT + preferred are evaluated for terms present in the SOURCE.
        for t in self.match(source):
            tflags = 0 if t.case_sensitive else re.IGNORECASE
            if t.do_not_translate and not re.search(rf"\b{re.escape(t.term)}\b", target, tflags):
                flags.append(f"dnt_term_dropped:{t.term}")
            if locale in t.preferred:
                pref = t.preferred[locale]
                if pref and re.search(re.escape(pref), target) is None:
                    flags.append(f"preferred_not_used:{t.term}")
        # Forbidden terms must NEVER appear in the target, regardless of source.
        for t in self.terms:
            if not t.forbidden:
                continue
            tflags = 0 if t.case_sensitive else re.IGNORECASE
            if re.search(rf"\b{re.escape(t.term)}\b", target, tflags):
                flags.append(f"forbidden_term_present:{t.term}")
        return target, flags


def load_glossary(path: Path | None = None) -> Glossary:
    """Load the glossary JSON. Falls back to the bundled default."""
    p = path or _DEFAULT_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    terms = [
        GlossaryTerm(
            term=t["term"],
            do_not_translate=bool(t.get("do_not_translate", False)),
            forbidden=bool(t.get("forbidden", False)),
            preferred=dict(t.get("preferred", {})),
            case_sensitive=bool(t.get("case_sensitive", False)),
        )
        for t in data.get("terms", [])
    ]
    return Glossary(terms=terms, version=str(data.get("version", "0")))
