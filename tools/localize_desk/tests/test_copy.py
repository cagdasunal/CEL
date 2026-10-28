"""Every word on the desk comes from COPY.md, and COPY.md carries nothing unused.

Operator, 2026-09-23: "all texts in the project must be in a document, and you need to
pull and use it that way." These tests make that a property of the build rather than a
promise: a sentence typed straight into the generator, a key the code asks for that the
document lacks, or a line in the document nothing uses, each fails here.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from localize_desk import copy_text as C  # noqa: E402
from localize_desk import desk_shared as S  # noqa: E402

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parents[1]
SOURCES = [TOOLS / "desk_shared.py",
           TOOLS / "generate_document_page.py", TOOLS / "document_desk.js", TOOLS / "document_export.js",
           TOOLS / "generate_rules_page.py", TOOLS / "rules_page.js",
           TOOLS / "rules_import.js", TOOLS / "download_rules_md.js"]
KEY = re.compile(r"""['"]([a-z][a-z0-9_]*(?:\.[a-z0-9_\-]+)+)['"]""")


def _code() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in SOURCES)


def _dynamic_families() -> set[str]:
    """Keys the code builds at runtime rather than spelling out."""
    keys = {f"lang.{code}" for code, *_ in S.LOCALES}
    keys |= {f"page.{slug}" for slug in S.PAGE_KEYS}
    keys |= {f"save.reason.{r}" for r in S.SAVE_REASONS}
    # U1: the engine's ids, worded by the panel as 'refusal.' + rule and 'job.failed.' + code.
    codes = json.loads((REPO / "data" / "localize" / "reason-codes.json").read_text(encoding="utf-8"))
    keys |= {f"refusal.{r}" for r in codes["refusal"] + codes["export_skip"]}
    keys |= {f"refusal.suffix.{x}" for x in codes["refusal_suffix"]}
    keys |= {f"job.failed.{c}" for c in codes["job_failed"]}
    # CEL-099: the rules page's "Our quality checks", worded as 'rules.qc.' + key (rules_quality.json)
    quality = json.loads((TOOLS / "rules_quality.json").read_text(encoding="utf-8"))
    keys |= {f"rules.qc.{e[1]}" for lines in quality["langs"].values() for e in lines}
    return keys


def test_every_reason_a_save_can_stop_for_has_its_words():
    """failureReason() builds `save.reason.<name>` at runtime: each name it can return is
    one of SAVE_REASONS, and each of those is a COPY.md line (WO-17). The page's is the document desk's."""
    src = (TOOLS / "document_desk.js").read_text(encoding="utf-8")
    body = src.split("function failureReason(r) {", 1)[1].split("\n  }\n", 1)[0]
    returned = set(re.findall(r"'([a-z_]+)'", body))     # its only quoted words are its answers
    assert returned == set(S.SAVE_REASONS), (returned, S.SAVE_REASONS)
    copy = C.load()
    assert all(f"save.reason.{r}" in copy for r in S.SAVE_REASONS)


class TestTheConflictWords:
    """M1 review P3 (#1). "Decide again" read as "click your choice again", and clicking your own
    highlighted choice undoes it, wiping both. (The first desk's own conflict lines went with it.)"""

    def test_no_line_says_decide_again(self):
        assert not [k for k, v in C.load().items() if re.search(r"decid(e|ing) again", v, re.I)]

    def test_no_refusal_points_at_a_note_that_is_not_there(self):
        """The Reviewer's E3-2: the client-rule refusals said "the note under the translation says
        which" -- the desk shows no such note (WO-36's desk line is not built)."""
        copy = C.load()
        assert not [k for k, v in copy.items() if k.startswith("refusal.") and "note under the translation" in v]


class TestTheDocument:
    def test_it_parses_and_has_no_duplicate_keys(self):
        copy = C.load()
        assert len(copy) > 100
        assert "doc.translate" in copy

    def test_a_block_is_read_as_one_text(self):
        """COPY.md may hold a long text as a block (`<!-- block key -->` ... `<!-- /block -->`); none is left in the
        file since the first desk's help text went (CEL-050), but the syntax is still the document's."""
        assert C.parse("<!-- block a.b -->\nfirst\nsecond\n<!-- /block -->\n")["a.b"] == "first\nsecond"

    def test_a_duplicate_key_is_refused(self):
        with pytest.raises(ValueError):
            C.parse("| `a.b` | one | |\n| `a.b` | two | |\n")

    def test_an_escaped_pipe_survives_in_the_text(self):
        assert C.parse("| `a.b` | left \\| right | where |\n")["a.b"] == "left | right"

    def test_every_key_the_code_asks_for_exists(self):
        copy = C.load()
        asked = set()
        for m in re.finditer(r"""\btn?\(\s*f?['"]([a-z][a-z0-9_.\-]*)['"]""", _code()):
            asked.add(m.group(1))
        missing = []
        for key in asked:
            if key.endswith("."):                  # a prefix built at runtime ('lang.' + c)
                continue
            if key in copy or (f"{key}.one" in copy and f"{key}.other" in copy):
                continue
            missing.append(key)
        assert not missing, f"the code asks COPY.md for keys it does not have: {sorted(missing)}"

    def test_nothing_in_the_document_is_unused(self):
        code = _code()
        quoted = set(KEY.findall(code))
        used = quoted | _dynamic_families()
        orphans = []
        for key in C.load():
            base = key.rsplit(".", 1)[0]
            if key in used:
                continue
            if key.endswith((".one", ".other")) and base in quoted:
                continue
            orphans.append(key)
        assert not orphans, f"COPY.md lines nothing uses: {sorted(orphans)}"

    def test_every_reason_the_engine_can_give_has_a_sentence(self):
        """U1: the engine hands the desk ids (data/localize/reason-codes.json, identical to the
        monorepo's); each needs its sentence here, or the desk shows a key."""
        codes = json.loads((REPO / "data" / "localize" / "reason-codes.json").read_text(encoding="utf-8"))
        copy = C.load()
        keys = ([f"refusal.{r}" for r in codes["refusal"] + codes["export_skip"]]
                + [f"refusal.suffix.{s}" for s in codes["refusal_suffix"]]
                + [f"job.failed.{c}" for c in codes["job_failed"]])
        assert not [k for k in keys if k not in copy]

    def test_a_missing_key_or_placeholder_is_an_error_not_a_blank(self):
        with pytest.raises(KeyError):
            C.t("no.such.key")
        with pytest.raises(KeyError):
            C.t("doc.banner.none")             # needs {language}


class TestNoSentenceTypedIntoAScript:
    def test_the_page_scripts_type_no_sentences(self):
        """The desk's own scripts carry COPY; a sentence typed into one would never be translated or reviewed.
        (The first desk's version of this ran over its rendered pages; the v2 scripts are checked as written.)"""
        scripts = "\n".join([(TOOLS / f).read_text(encoding="utf-8")
                             for f in ("document_desk.js", "document_export.js", "rules_page.js", "rules_md.js",
                                       "rules_import.js", "download_rules_md.js")]
                            + [S._STAGE_JS, S._PROXY_JS, S._TIP_JS])
        assert "function" in scripts
        for pattern in (r"textContent\s*=\s*'[A-Za-z]", r"\.title\s*=\s*'[A-Za-z]",
                        r"toast\(\s*'[A-Za-z]", r"confirm\(\s*'[A-Za-z]",
                        r"'aria-label',\s*'[A-Za-z]", r"'data-tip',\s*'[A-Za-z]"):
            hit = re.search(pattern, scripts)
            assert not hit, f"a sentence typed into the script: {hit.group(0)!r}"
