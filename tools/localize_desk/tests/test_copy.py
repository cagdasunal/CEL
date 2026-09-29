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
from html.parser import HTMLParser
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from localize_desk import copy_text as C  # noqa: E402
from localize_desk import generate_desk_page as G  # noqa: E402
from localize_desk import recommend as R  # noqa: E402

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parents[1]
SOURCES = [TOOLS / "generate_desk_page.py", TOOLS / "recommend.py"]
KEY = re.compile(r"""['"]([a-z][a-z0-9_]*(?:\.[a-z0-9_\-]+)+)['"]""")


def _code() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in SOURCES)


def _dynamic_families() -> set[str]:
    """Keys the code builds at runtime rather than spelling out."""
    keys = {f"lang.{code}" for code, *_ in G.LOCALES}
    keys |= {f"page.{slug}" for slug in G.PAGE_KEYS}
    keys |= {f"show.{k}" for k in ("check", "arrived", "todo", "all", "csv", "edited",
                                   "draft", "sending", "failed", "exported", "live")}
    for tray in ("draft", "csv"):
        keys |= {f"list.{tray}.title", f"list.{tray}.notice",
                 f"list.{tray}.summary.one", f"list.{tray}.summary.other"}
    keys |= {f"why.register.{loc}" for loc in R._FORMAL}
    keys |= {f"save.reason.{r}" for r in G.SAVE_REASONS}
    # U1: the engine's ids, worded by the panel as 'refusal.' + rule and 'job.failed.' + code.
    codes = json.loads((REPO / "data" / "localize" / "reason-codes.json").read_text(encoding="utf-8"))
    keys |= {f"refusal.{r}" for r in codes["refusal"] + codes["export_skip"]}
    keys |= {f"refusal.suffix.{x}" for x in codes["refusal_suffix"]}
    keys |= {f"job.failed.{c}" for c in codes["job_failed"]}
    return keys


def test_every_reason_a_save_can_stop_for_has_its_words():
    """failureReason() builds `save.reason.<name>` at runtime: each name it can return is
    one of SAVE_REASONS, and each of those is a COPY.md line (WO-17)."""
    src = G.Path(G.__file__).read_text(encoding="utf-8")
    body = src.split("function failureReason(r) {", 1)[1].split("\n    }\n", 1)[0]
    returned = set(re.findall(r"'([a-z_]+)'", body))     # its only quoted words are its answers
    assert returned == set(G.SAVE_REASONS), (returned, G.SAVE_REASONS)
    copy = C.load()
    assert all(f"save.reason.{r}" in copy for r in G.SAVE_REASONS)


class TestTheConflictWords:
    """M1 review P3 (#1). "Decide again" read as "click your choice again", and clicking your own
    highlighted choice undoes it, wiping both. And the export skips an approval whose website text
    changed, so approvals wait for the import file; they do not all go into it."""

    CONFLICT = ("status.conflict.tip", "status.conflict.gone", "autosave.conflict.hint",
                "save.conflicts.detail.one", "save.conflicts.detail.other", "how.saving.on")

    def test_a_conflict_says_choose_again_or_edit(self):
        copy = C.load()
        for key in self.CONFLICT:
            assert "choose again, or edit, to keep yours" in copy[key].lower(), key
        assert not [k for k, v in copy.items() if re.search(r"decid(e|ing) again", v, re.I)]

    def test_no_refusal_points_at_a_note_that_is_not_there(self):
        """The Reviewer's E3-2: the client-rule refusals said "the note under the translation says
        which" -- the desk shows no such note (WO-36's desk line is not built)."""
        copy = C.load()
        assert not [k for k, v in copy.items() if k.startswith("refusal.") and "note under the translation" in v]

    def test_approvals_wait_for_the_import_file(self):
        assert C.load()["list.csv.notice"] == ("Nothing reaches the website by itself. Your approvals "
                                               "are saved and wait for the next Weglot file.")


class TestTheDocument:
    def test_it_parses_and_has_no_duplicate_keys(self):
        copy = C.load()
        assert len(copy) > 100
        assert "how.body" in copy

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
        for m in re.finditer(r"""block_html\(\s*['"]([a-z0-9_.\-]+)['"]""", _code()):
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
            C.t("index.card.texts")            # needs {total}

    def test_the_help_text_renders_as_escaped_html(self):
        html = C.block_html("how.body")
        assert "<h3>" in html and "<ul>" in html and "<strong>" in html
        assert "<script" not in html


class _Visible(HTMLParser):
    """Visible text plus the attributes a person reads (tooltips, aria-label, placeholder)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        for k, v in attrs:
            if k in ("title", "aria-label", "placeholder", "data-tip") and v:
                self.out.append(v)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.out.append(data.strip())


def _desk_part(html: str) -> str:
    """The desk's own markup: from its shell to its script (the shared dashboard chrome
    -- topbar, account menu -- belongs to tools/dashboard.py, not to this document)."""
    return html[html.index('<div class="dashboard-shell">'):html.index("<script>\n  (function")]


class TestNoWordOutsideTheDocument:
    @pytest.fixture()
    def sentinel(self, monkeypatch):
        real = C.load()
        monkeypatch.setattr(C, "load", lambda: {k: "§" for k in real})

    def test_the_rendered_pages_carry_no_english_of_their_own(self, sentinel):
        units = G.load_units()
        if not units:
            pytest.skip("no unit data in this checkout")
        endonyms = {endonym for _code, endonym, _dir, _flag in G.LOCALES}
        for html in (G.render_index(units), G.render_locale("de", units),
                     G.render_locale("ar", units)):
            p = _Visible()
            p.feed(_desk_part(html))
            stray = [s for s in p.out
                     if re.search(r"[A-Za-z]", s.replace("§", "")) and s not in endonyms]
            assert not stray, f"text not from COPY.md: {stray[:8]}"

    def test_the_page_scripts_type_no_sentences(self):
        units = G.load_units() or [{"unit_id": "x", "word_from": "x", "current": {"de": {"word_to": "y"}},
                                    "_pages": {"vancouver"}, "_outside": []}]
        for html in (G.render_index(units), G.render_locale("de", units)):
            # The desk's own scripts only (they carry COPY). The account menu's script is
            # shared dashboard chrome from tools/dashboard.py, outside this document.
            scripts = "".join(s for s in re.findall(r"<script>(.*?)</script>", html, re.S)
                              if "var COPY = " in s)
            assert scripts
            for pattern in (r"textContent\s*=\s*'[A-Za-z]", r"\.title\s*=\s*'[A-Za-z]",
                            r"toast\(\s*'[A-Za-z]", r"confirm\(\s*'[A-Za-z]",
                            r"'aria-label',\s*'[A-Za-z]", r"'data-tip',\s*'[A-Za-z]"):
                hit = re.search(pattern, scripts)
                assert not hit, f"a sentence typed into the script: {hit.group(0)!r}"

    def test_real_copy_leaves_no_unfilled_placeholder_on_screen(self):
        units = G.load_units()
        if not units:
            pytest.skip("no unit data in this checkout")
        for html in (G.render_index(units), G.render_locale("de", units)):
            p = _Visible()
            p.feed(_desk_part(html))
            text = " ".join(p.out)
            assert not re.search(r"\{[A-Za-z_]+\}", text), text[:200]
            assert "⟦" not in html
