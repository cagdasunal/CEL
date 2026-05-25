"""Anti-AI / human-voice QA for the copywriter — the first ENFORCED banned-phrase gate
(tools/summary/qa.py only had structural checks; the AI-tell banlists were prompt-only).

Pure stdlib. Two layers, both run for every locale:
  (a) UNIVERSAL: em-dash + emoji + English-origin hard AI-template patterns (hard fails)
      and an English-origin hype/transition/hedge word list (flags).
  (b) PER-LOCALE: the `## AI-tell banlist` parsed from the reused locale layer
      (tools/summary/prompts/locales/<locale>.md) — e.g. Korean translationese.
Rule: ANY hard fail ⇒ not ok; >= _FLAG_FAIL_THRESHOLD flags ⇒ not ok; a missing
must_keep_fact ⇒ not ok. The engine retries once on a fail, then surfaces to the user.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from tools.copywriter import config

_FLAG_FAIL_THRESHOLD = 3

_EM_DASH_CHARS = ("—", "–")  # — –
# Emoji / pictographic ranges (enough to catch ✅🚀🧠… without false-flagging text).
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F02F✅✨⭐]"
)

# Unambiguous AI sentence templates + cold-open clichés (HARD — these alone fail a draft).
_HARD_TEMPLATES = [
    ("opener:in_todays_world", re.compile(r"\bin today'?s\b", re.I)),
    ("opener:in_the_era_of", re.compile(r"\bin (?:the|an?) (?:era|age|world|landscape) of\b", re.I)),
    ("opener:in_a_world_where", re.compile(r"\bin a world where\b", re.I)),
    ("opener:lets_dive_in", re.compile(r"\blet'?s dive in\b", re.I)),
    ("opener:picture_this", re.compile(r"\bpicture this\b", re.I)),
    ("opener:ever_evolving", re.compile(r"\b(?:in an? )?(?:ever[- ]evolving|fast[- ]paced|rapidly changing) (?:world|landscape|environment)\b", re.I)),
    ("template:not_just_x_its_y", re.compile(r"\bit'?s not just\b.{1,60}?\bit'?s\b", re.I)),
    ("template:not_only_but_also", re.compile(r"\bnot only\b.{1,60}?\bbut also\b", re.I)),
]

# English-origin hype / transition / hedge crutches (FLAGS — counted; >=3 fails).
_UNIVERSAL_FLAG_TERMS = (
    "delve", "leverage", "robust", "seamless", "seamlessly", "elevate", "unlock",
    "foster", "holistic", "tapestry", "multifaceted", "cutting-edge", "game-changer",
    "transformative", "furthermore", "moreover", "additionally", "consequently",
    "notably", "underscore", "utilize", "harness", "nestled", "vibrant", "pivotal",
    "embark", "navigate the", "in the realm of", "when it comes to",
    "it's important to note", "it's worth noting", "serves as", "stands as",
    "allowing you to", "needless to say", "in conclusion",
)


@dataclass
class CopyQaReport:
    ok: bool
    flags: list[str] = field(default_factory=list)       # soft tells (>= threshold => fail)
    hard_fails: list[str] = field(default_factory=list)  # any one => fail

    def summary(self) -> str:
        parts = []
        if self.hard_fails:
            parts.append("HARD: " + ", ".join(self.hard_fails))
        if self.flags:
            parts.append(f"flags({len(self.flags)}): " + ", ".join(self.flags))
        return " | ".join(parts) or "clean"


@lru_cache(maxsize=16)
def _load_locale_banlist(locale: str) -> tuple[str, ...]:
    """Parse the `## AI-tell banlist` terms from the reused locale layer. Strips
    parenthetical annotations like '다양한 (남용)' → '다양한'. Returns () if unavailable."""
    path = Path(config.LOCALE_LAYERS_DIR) / f"{locale}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    out: list[str] = []
    in_section = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_section = line.lower().startswith("## ai-tell banlist")
            continue
        if in_section and line.strip():
            for raw in line.split(","):
                term = re.sub(r"\s*\([^)]*\)\s*", " ", raw).strip().strip(".").lstrip("~").strip()
                # Drop a leading parenthetical-only or empty fragment; keep real terms.
                if len(term) >= 2:
                    out.append(term)
    return tuple(dict.fromkeys(out))  # dedupe, preserve order


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def copywriter_qa(text: str, locale: str, *, must_keep_facts: tuple[str, ...] = ()) -> CopyQaReport:
    """Run the universal + per-locale anti-AI checks. See module docstring for the rule."""
    hard_fails: list[str] = []
    flags: list[str] = []
    low = text.lower()

    # --- Hard fails ---
    if any(ch in text for ch in _EM_DASH_CHARS):
        hard_fails.append("em_dash")
    if _EMOJI_RE.search(text):
        hard_fails.append("emoji")
    for name, rx in _HARD_TEMPLATES:
        if rx.search(text):
            hard_fails.append(name)

    # --- Universal flag terms (English-origin; word-boundary, case-insensitive) ---
    for term in _UNIVERSAL_FLAG_TERMS:
        if " " in term or "-" in term:
            if term in low:
                flags.append(f"ai_term:{term}")
        elif re.search(rf"\b{re.escape(term)}\b", low):
            flags.append(f"ai_term:{term}")

    # --- Per-locale banlist ---
    for term in _load_locale_banlist(locale):
        tl = term.lower()
        if " " in term:
            present = term in text  # multi-word phrase: exact substring
        elif not term.isascii():
            # Hangul-aware boundary: don't match a term embedded inside a longer Hangul
            # run (사또한테 must NOT flag 또한). Lightweight heuristic — full correctness
            # needs a morphological analyzer (deferred). No-op for non-Hangul scripts.
            present = re.search(rf"(?<![가-힣]){re.escape(term)}(?![가-힣])", text) is not None
        else:
            present = re.search(rf"\b{re.escape(tl)}\b", low) is not None
        if present:
            flags.append(f"banlist[{locale}]:{term}")

    # --- Fact preservation (content requirement; a miss is a hard fail) ---
    ntext = _norm(text)
    for fact in must_keep_facts:
        nf = _norm(fact)
        if not nf:
            continue
        if nf.isascii():
            # alnum-boundary so a short fact ("cat") isn't "found" inside a word
            # ("category"), while still matching symbol-flanked facts ("$1,200", "DLI #O19…").
            present = re.search(rf"(?<![a-z0-9]){re.escape(nf)}(?![a-z0-9])", ntext) is not None
        else:
            present = nf in ntext  # non-Latin: substring
        if not present:
            hard_fails.append(f"missing_fact:{fact[:40]}")

    # Threshold on DISTINCT tells: a term in BOTH the universal list and a locale banlist
    # is ONE tell, not two (M1 — double-counting was failing copy at 2 distinct tells).
    distinct_tells = {f.split(":", 1)[1].lower() for f in flags}
    ok = not hard_fails and len(distinct_tells) < _FLAG_FAIL_THRESHOLD
    return CopyQaReport(ok=ok, flags=flags, hard_fails=hard_fails)
