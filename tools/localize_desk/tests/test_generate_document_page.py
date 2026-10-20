"""Tests for the document page generator (desk v2, CEL-026, design B).

The page is one page of the website read as a document. These tests hold the three things
that can go wrong without a browser noticing: the DATA (which text comes first, which are left
out as the site's menu and footer, which translations are carried), the PAGE (the shell the
runtime builds on, the order of its scripts, every word from COPY.md, tokens-only CSS) and the
FILES (nothing of the client's rules in them, and the committed ones are what the generator
writes today).

Every shown text is editable (operator, 2026-10-19 21:00): the generator sets no lock, and the
tests say so rather than keep the priority rules that served the old ones.

The runtime itself (`document_desk.js`) is another builder's file; most tests here stand a
stub in its place (`stub_js`), so they hold whether or not it exists yet. The tests that read
the real one say so.
"""
from __future__ import annotations

import html as _html
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from localize_desk import copy_text as C  # noqa: E402
from localize_desk import desk_shared as S  # noqa: E402
from localize_desk import generate_document_page as GD  # noqa: E402
from localize_desk.tests import test_desk_privacy as P  # noqa: E402

TOOLS = Path(__file__).resolve().parents[2]
STUB = "/* document_desk stub for tests */\nwindow.__docStub = true;\n"

PATHS = {
    "vancouver": "/vancouver",
    "vs-toronto": "/vancouver/vs-toronto",
    "cost-of-studying-english": "/vancouver/cost-of-studying-english",
    "how-long-to-learn-english": "/vancouver/how-long-to-learn-english",
}


# ── Fixtures: a small corpus in the shape of data/localize/units/*.json ─────────────────

def _unit(uid: str, word_from: str = "Hello", *, pages: list[str] | None = None, role: str = "body",
          markup: str = "plain", noise: bool = False, summary: bool = False, section: str = "Sec",
          tag: str = "p", ord_: int | None = None, current: dict | None = None, chrome: bool = False) -> dict:
    unit = {
        "unit_id": uid, "word_from": word_from, "type": "Text", "role": role, "section": section,
        "markup_class": markup, "noise": noise, "summary_owned": summary,
        "current": current if current is not None else {"de": {"word_to": "Hallo", "translated": True}},
        "tag": tag,
    }
    if pages is not None:
        unit["pages"] = pages
    if ord_ is not None:
        unit["ord"] = ord_
    if chrome:                                  # the engine writes the flag on a menu / footer text only, never `false`
        unit["chrome"] = True
    return unit


def _on(n: int, own: str = "/vancouver") -> list[str]:
    """A `pages` list of n paths: the page's own and n-1 pages of the rest of the site."""
    return [own] + [f"/site/p{i:02d}" for i in range(n - 1)]


def _menu(uid: str, **kw) -> dict:
    """A menu / footer text as the engine's manifest writes it: `chrome: true` (its rule, contract
    section 10 and monorepo gates.is_chrome: on 30 paths of the site, outside every heading, not the title
    or description). The flag is what the generator reads. Any keyword overrides."""
    base = dict(section="", pages=_on(30), chrome=True)
    base.update(kw)
    return _unit(uid, **base)


def _looks_like_menu(uid: str, **kw) -> dict:
    """The same text WITHOUT the flag: what the old generator rule would have dropped. The engine did not
    flag it, so it is a body text."""
    return _menu(uid, **{**dict(chrome=False), **kw})


def _write(d: Path, key: str, units: list[dict], *, order: list | None | str = "file",
           built: str = "2026-10-19T10:00:00Z") -> None:
    """One page file. `order="file"`: the order list is the units in file order, each with its
    tag as block; a list of (unit_id, block) pairs: that; None: no `order` key at all."""
    units = [dict(u) for u in units]
    for u in units:
        u.setdefault("pages", [PATHS[key]])
    doc = {"page": key, "path": PATHS[key], "built_at": built, "units": units}
    if order == "file":
        order = [(u["unit_id"], u["tag"]) for u in units]
    if order is not None:
        doc["order"] = [{"unit_id": uid, "index": i, "block": block} for i, (uid, block) in enumerate(order)]
    (d / f"{key}.json").write_text(json.dumps(doc), encoding="utf-8")


def _corpus(d: Path) -> Path:
    """All four pages, one text each (what main() needs to write anything)."""
    for i, key in enumerate(S.PAGE_KEYS):
        units = [_unit(f"u{i}", f"Text of {key}")]
        if i == 0:                                      # a real corpus always has menu texts the engine flagged
            units.append(_menu("m0"))
        _write(d, key, units, built=f"2026-10-19T1{i}:00:00Z")
    return d


@pytest.fixture()
def units_dir(tmp_path, monkeypatch):
    d = tmp_path / "units"
    d.mkdir()
    monkeypatch.setattr(GD, "UNITS_DIR", d)
    return d


@pytest.fixture()
def stub_js(tmp_path, monkeypatch):
    f = tmp_path / "document_desk_stub.js"
    f.write_text(STUB, encoding="utf-8")
    monkeypatch.setattr(GD, "DOC_JS", f)
    return f


@pytest.fixture()
def page(stub_js):
    return GD.render_page()


@pytest.fixture()
def out_dir(tmp_path, monkeypatch):
    d = tmp_path / "out" / "document"
    monkeypatch.setattr(GD, "OUT_DIR", d)
    return d


def _blocks(docs: dict, key: str = "vancouver") -> list[dict]:
    return docs[key]["blocks"]


def _real_corpus():
    """(raw page files by key, documents) for the real unit files. The four files are committed
    with their `order` lists, so a missing file or list fails: a skip here would turn the
    independent all-pages checks green with nothing checked."""
    files = sorted(S.UNITS_DIR.glob("*.json")) if S.UNITS_DIR.is_dir() else []
    raw = {d["page"]: d for d in (json.loads(p.read_text(encoding="utf-8")) for p in files)
           if d.get("page") in S.PAGE_KEYS}
    if len(raw) != len(S.PAGE_KEYS) or not all(d.get("order") for d in raw.values()):
        pytest.fail(f"the unit files carry {len(raw)} of the {len(S.PAGE_KEYS)} pages, or a page "
                    "with no `order` list")
    return raw, GD.load_documents(S.UNITS_DIR)


def _is_chrome(unit: dict, block: str, scope: set[str]) -> bool:
    """The test's own statement of the rule (contract section 10), written from the contract and
    not from the generator: outside the four, on 30 paths or more, outside every heading, and not
    the page's title or description."""
    pages = unit.get("pages") or []
    return (any(p not in scope for p in pages) and len(pages) >= 30
            and unit.get("section", "") == "" and block not in ("meta-title", "meta-description"))


def _block_of(raw_doc: dict) -> dict[str, str]:
    return {o["unit_id"]: o["block"] for o in raw_doc["order"]}


# ── The document order ──────────────────────────────────────────────────────────────────

class TestDocumentOrder:
    def test_blocks_follow_the_order_list_not_the_file(self, units_dir):
        units = [_unit("a", "A", tag="p"), _unit("b", "B", tag="p"), _unit("c", "C", tag="p")]
        _write(units_dir, "vancouver", units, order=[("c", "h2"), ("a", "p"), ("b", "li")])
        blocks = _blocks(GD.load_documents(units_dir))
        assert [(b["id"], b["b"]) for b in blocks] == [("c", "h2"), ("a", "p"), ("b", "li")]

    def test_the_block_is_the_order_entrys_not_the_units_tag(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a", tag="p")], order=[("a", "h1")])
        assert _blocks(GD.load_documents(units_dir))[0]["b"] == "h1"

    def test_a_block_carries_role_section_and_english(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a", "Is it dear?", role="title", section="Cost")])
        b = _blocks(GD.load_documents(units_dir))[0]
        assert (b["r"], b["sec"], b["en"]) == ("title", "Cost", "Is it dear?")

    def test_a_unit_the_list_forgot_is_kept_after_the_listed_ones(self, units_dir):
        units = [_unit("a", ord_=0), _unit("b", ord_=1), _unit("c", ord_=2)]
        _write(units_dir, "vancouver", units, order=[("b", "p")])
        assert [b["id"] for b in _blocks(GD.load_documents(units_dir))] == ["b", "a", "c"]

    def test_a_listed_id_with_no_unit_or_listed_twice_is_passed_over(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a"), _unit("b")],
               order=[("ghost", "p"), ("b", "p"), ("b", "h3"), ("a", "p")])
        blocks = _blocks(GD.load_documents(units_dir))
        assert [(b["id"], b["b"]) for b in blocks] == [("b", "p"), ("a", "p")]

    def test_without_an_order_list_ord_then_file_position_decide(self, units_dir):
        units = [_unit("late", ord_=5, tag="h2"), _unit("first", ord_=1, tag="h1"),
                 _unit("tie-1", ord_=3), _unit("tie-2", ord_=3)]
        units.append({k: v for k, v in _unit("untagged", ord_=4).items() if k != "tag"})
        _write(units_dir, "vancouver", units, order=None)
        blocks = _blocks(GD.load_documents(units_dir))
        assert [b["id"] for b in blocks] == ["first", "tie-1", "tie-2", "untagged", "late"]
        assert [b["b"] for b in blocks] == ["h1", "p", "p", "p", "h2"]       # tag; default p

    def test_pages_come_out_in_the_desks_order_whatever_the_files_are_called(self, units_dir):
        for key in reversed(S.PAGE_KEYS):
            _write(units_dir, key, [_unit("x")])
        (units_dir / "stray.json").write_text(json.dumps({"page": "not-a-page", "path": "/x", "units": []}))
        assert list(GD.load_documents(units_dir)) == S.PAGE_KEYS

    def test_the_real_corpus_follows_its_order_list_minus_the_menu_and_footer(self):
        raw, docs = _real_corpus()
        scope = {d["path"] for d in raw.values()}
        for key, d in raw.items():
            by_id = {u["unit_id"]: u for u in d["units"]}
            want = [o for o in d["order"] if not _is_chrome(by_id[o["unit_id"]], o["block"], scope)]
            blocks = docs[key]["blocks"]
            assert [b["id"] for b in blocks] == [o["unit_id"] for o in want], key
            assert [b["b"] for b in blocks] == [o["block"] for o in want], key
            assert len({b["id"] for b in blocks}) == len(blocks), key


# ── Every shown text is editable ────────────────────────────────────────────────────────

LINK = '<a wg-1="">Apply now</a>'


def _only(units_dir, **kw) -> dict:
    _write(units_dir, "vancouver", [_unit("a", **kw)])
    return _blocks(GD.load_documents(units_dir))[0]


class TestEveryTextIsEditable:
    def test_an_ordinary_text_has_no_lock_and_no_shared_note(self, units_dir):
        b = _only(units_dir)
        assert b["lock"] == "" and "out" not in b and "outEg" not in b

    @pytest.mark.parametrize("flags", [
        dict(summary=True),
        dict(markup="a_only", word_from=LINK),
        dict(word_from="+", noise=True),
        dict(summary=True, markup="a_only", word_from=LINK, noise=True),
    ], ids=["summary-owned", "link-only", "noise", "all three"])
    def test_a_text_the_gates_used_to_lock_is_editable_now(self, units_dir, flags):
        _write(units_dir, "vancouver", [_unit("a", **flags), _unit("b")])
        docs = GD.load_documents(units_dir)
        b = _blocks(docs)[0]
        assert b["lock"] == ""
        assert GD.pages_payload(docs)["pages"][0]["ids"] == ["a", "b"]

    def test_the_lock_field_stays_in_every_block_for_the_day_a_row_is_flagged(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a"), _unit("b", pages=_on(3))])
        for b in _blocks(GD.load_documents(units_dir)):
            assert b["lock"] == ""

    def test_there_is_no_site_lock_and_no_lock_logic_left_in_the_generator(self):
        src = Path(GD.__file__).read_text(encoding="utf-8")
        assert not hasattr(GD, "LOCKS") and not hasattr(GD, "_lock_of")
        assert '"site"' not in src and "data-lock=\"site\"" not in src
        for word in ("summary_owned", "markup_class", "noise"):
            assert word not in src, f"{word}: the generator still looks at it"

    def test_a_text_also_on_pages_outside_the_four_is_editable_and_says_how_many(self, units_dir):
        b = _only(units_dir, pages=["/vancouver", "/housing", "/"])
        assert (b["lock"], b["out"], b["outEg"]) == ("", 2, "/")

    def test_outeg_is_the_first_outside_path_and_a_lone_slash_stays_a_slash(self, units_dir):
        b = _only(units_dir, pages=["/vancouver", "/san-diego-ca", "/housing"])
        assert (b["out"], b["outEg"]) == (2, "/housing")
        assert _only(units_dir, pages=["/vancouver", "/"])["outEg"] == "/"

    def test_other_pages_of_the_four_are_not_outside(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a", pages=["/vancouver", "/vancouver/vs-toronto"])])
        _write(units_dir, "vs-toronto", [_unit("a", pages=["/vancouver", "/vancouver/vs-toronto"])])
        b = _blocks(GD.load_documents(units_dir))[0]
        assert "out" not in b and "outEg" not in b

    def test_a_shared_text_that_is_also_flagged_by_a_gate_still_says_it_is_shared(self, units_dir):
        b = _only(units_dir, pages=["/vancouver", "/housing"], noise=True)
        assert (b["lock"], b["out"], b["outEg"]) == ("", 1, "/housing")

    def test_a_blocks_keys_are_in_the_documented_order(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a"), _unit("b", pages=["/vancouver", "/housing", "/vancouver/vs-toronto"])])
        _write(units_dir, "vs-toronto", [_unit("z")])
        plain, shared = _blocks(GD.load_documents(units_dir))
        assert list(plain) == ["id", "b", "r", "sec", "en", "lock", "w"]
        assert list(shared) == ["id", "b", "r", "sec", "en", "lock", "also", "out", "outEg", "outAll", "w"]

    def test_a_text_on_several_outside_pages_carries_all_their_paths_sorted(self, units_dir):
        """CEL-072: the sentence says `N other pages (<example>, …)`; the popover lists them all."""
        _write(units_dir, "vancouver", [_unit("a", pages=["/vancouver", "/zebra", "/housing", "/apple"])])
        for key in S.PAGE_KEYS[1:]:
            _write(units_dir, key, [_unit("x")])
        (b,) = _blocks(GD.load_documents(units_dir))[:1]
        assert (b["out"], b["outEg"], b["outAll"]) == (3, "/apple", ["/apple", "/housing", "/zebra"])

    def test_the_real_corpus_has_no_locked_text_at_all(self):
        _raw, docs = _real_corpus()
        for key, doc in docs.items():
            assert [b["id"] for b in doc["blocks"] if b["lock"]] == [], key
            assert all(("out" in b) == ("outEg" in b) == ("outAll" in b) for b in doc["blocks"]), key
            # the popover lists every page outside the four (CEL-072): the whole sorted list, whose first is the example
            assert all(b["outAll"] == sorted(b["outAll"]) and b["outAll"][0] == b["outEg"] and len(b["outAll"]) == b["out"]
                       for b in doc["blocks"] if "outAll" in b), key


# ── The site's menu and footer are left out ─────────────────────────────────────────────

class TestTheMenuAndFooterAreLeftOut:
    """CEL-039: the engine decides (a unit's `chrome: true`, monorepo gates.is_chrome); the generator drops
    exactly the flagged units and holds no copy of the rule. The rule itself is pinned in the monorepo."""

    def test_the_generator_no_longer_holds_a_copy_of_the_rule(self):
        for gone in ("is_chrome", "CHROME_MIN_PAGES", "META_BLOCKS"):
            assert not hasattr(GD, gone), f"{gone}: the engine's flag replaced the generator's own rule"

    def test_a_flagged_text_is_dropped_whole(self, units_dir):
        _write(units_dir, "vancouver", [_unit("keep-1"), _menu("menu"), _unit("keep-2")])
        docs = GD.load_documents(units_dir)
        assert [b["id"] for b in _blocks(docs)] == ["keep-1", "keep-2"]
        assert docs["vancouver"]["chrome"] == 1
        entry = GD.pages_payload(docs)["pages"][0]
        assert (entry["count"], entry["chrome"], entry["ids"]) == (2, 1, ["keep-1", "keep-2"])

    @pytest.mark.parametrize("looks_like", [
        dict(),                                                   # on 30 paths, outside every heading: the old rule's three conditions
        dict(pages=_on(31)),
        dict(pages=_on(29)),
        dict(pages=list(PATHS.values())),                         # the four pages alone
        dict(section="Frequently Asked Questions"),
    ], ids=["all three old conditions", "31 pages", "29 pages", "in scope only", "under a heading"])
    def test_a_text_the_engine_did_not_flag_is_kept_whatever_it_looks_like(self, units_dir, looks_like):
        """CEL-039: the old generator rule would have dropped the first three; the engine's answer, not a copy of
        its rule, decides, so an unflagged text is a body text, editable and in the payload."""
        _write(units_dir, "vancouver", [_looks_like_menu("a", **looks_like), _unit("z")])
        docs = GD.load_documents(units_dir)
        assert [b["id"] for b in _blocks(docs)] == ["a", "z"]
        assert docs["vancouver"]["chrome"] == 0
        assert _blocks(docs)[0]["lock"] == "" and "a" in GD.pages_payload(docs)["pages"][0]["ids"]

    @pytest.mark.parametrize("flagged", [
        dict(), dict(pages=_on(2)), dict(section="Some heading"), dict(pages=["/vancouver"]),
    ], ids=["menu", "2 pages", "under a heading", "own page only"])
    def test_a_flagged_text_is_dropped_whatever_else_is_true_of_it(self, units_dir, flagged):
        """The flag is the whole decision: the generator does not second-guess the engine."""
        _write(units_dir, "vancouver", [_menu("a", **flagged), _unit("z")])
        docs = GD.load_documents(units_dir)
        assert [b["id"] for b in _blocks(docs)] == ["z"] and docs["vancouver"]["chrome"] == 1

    def test_a_body_text_on_many_pages_keeps_its_shared_note(self, units_dir):
        _write(units_dir, "vancouver", [_unit("faq", "Yes. The weekly rate drops.", section="FAQ", pages=_on(35))])
        b = _blocks(GD.load_documents(units_dir))[0]
        assert (b["lock"], b["out"], b["outEg"], b["sec"]) == ("", 34, "/site/p00", "FAQ")

    def test_a_text_on_twenty_nine_pages_is_kept_editable_with_its_note(self, units_dir):
        _write(units_dir, "vancouver", [_looks_like_menu("shared", pages=_on(29))])
        docs = GD.load_documents(units_dir)
        b = _blocks(docs)[0]
        assert (b["id"], b["lock"], b["out"]) == ("shared", "", 28)
        assert b["outEg"] == "/site/p00"
        assert docs["vancouver"]["chrome"] == 0
        assert GD.pages_payload(docs)["pages"][0]["ids"] == ["shared"]

    def test_the_drop_does_not_care_what_else_a_gate_says(self, units_dir):
        _write(units_dir, "vancouver", [
            _menu("noise", pages=_on(31), noise=True), _menu("link", pages=_on(40), markup="a_only", word_from=LINK),
            _menu("summary", pages=_on(30), summary=True), _unit("ok")])
        docs = GD.load_documents(units_dir)
        assert [b["id"] for b in _blocks(docs)] == ["ok"] and docs["vancouver"]["chrome"] == 3

    def test_the_count_of_dropped_texts_is_reported_for_each_page(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a"), _menu("m1"), _menu("m2", pages=_on(35))])
        _write(units_dir, "vs-toronto", [_menu("b", pages=_on(30, "/vancouver/vs-toronto"))])
        docs = GD.load_documents(units_dir)
        payload = GD.pages_payload(docs)
        assert [(p["key"], p["count"], p["chrome"]) for p in payload["pages"]] == [
            ("vancouver", 1, 2), ("vs-toronto", 0, 1)]
        assert list(payload["pages"][0]) == ["key", "path", "count", "chrome", "ids"]
        assert list(docs["vancouver"]) == ["page", "path", "built", "chrome", "blocks"]

    def test_a_dropped_text_does_not_disturb_the_order_or_the_others(self, units_dir):
        units = [_unit("a"), _menu("menu"), _looks_like_menu("b", pages=_on(5)), _unit("c")]
        _write(units_dir, "vancouver", units, order=[("c", "h2"), ("menu", "link"), ("a", "p"), ("b", "li")])
        assert [(b["id"], b["b"]) for b in _blocks(GD.load_documents(units_dir))] == [
            ("c", "h2"), ("a", "p"), ("b", "li")]

    def test_main_refuses_when_no_unit_anywhere_carries_the_engines_flag(self, units_dir, stub_js, out_dir, capsys):
        """CEL-039: units files from before the engine wrote `chrome` would put the site's menu and footer into
        the desk; writing nothing and saying why is the only safe answer."""
        for i, key in enumerate(S.PAGE_KEYS):
            _write(units_dir, key, [_unit(f"u{i}"), _looks_like_menu(f"menu{i}")])
        assert GD.main() == 2 and not out_dir.exists()
        err = capsys.readouterr().err
        assert "chrome" in err and "refresh the manifest" in err

    def test_the_files_main_writes_carry_the_count(self, units_dir, stub_js, out_dir):
        _corpus(units_dir)
        _write(units_dir, "vancouver", [_unit("a"), _menu("menu", pages=_on(31))])
        GD.main()
        one = json.loads((out_dir / "data" / "vancouver.json").read_text(encoding="utf-8"))
        assert one["chrome"] == 1 and [b["id"] for b in one["blocks"]] == ["a"]
        entry = json.loads((out_dir / "data" / "pages.json").read_text(encoding="utf-8"))["pages"][0]
        assert (entry["key"], entry["count"], entry["chrome"], entry["ids"]) == ("vancouver", 1, 1, ["a"])
        assert "menu" not in (out_dir / "data" / "vancouver.json").read_text(encoding="utf-8")

    def test_the_real_corpus_shows_todays_counts(self):
        """Shown = editable, and the menu and footer left out, per page (2026-10-19 corpus). Asserted
        only when the files carry `order`; recomputed from the files too, so a rebuilt corpus fails
        on the number that moved and says so."""
        raw, docs = _real_corpus()
        scope = {d["path"] for d in raw.values()}
        for key, d in raw.items():
            block = _block_of(d)
            dropped = sum(1 for u in d["units"] if _is_chrome(u, block[u["unit_id"]], scope))
            assert len(docs[key]["blocks"]) == len(d["units"]) - dropped, key
            assert docs[key]["chrome"] == dropped, key
            assert (len(docs[key]["blocks"]), docs[key]["chrome"]) == REAL_COUNTS[key], key
        payload = {p["key"]: p for p in GD.pages_payload(docs)["pages"]}
        for key, (shown, chrome) in REAL_COUNTS.items():
            assert (payload[key]["count"], len(payload[key]["ids"]), payload[key]["chrome"]) == (shown, shown, chrome), key

    def test_the_real_corpus_drops_76_76_75_75_distinct_menu_and_footer_texts(self):
        raw, docs = _real_corpus()
        scope = {d["path"] for d in raw.values()}
        for key, d in raw.items():
            block = _block_of(d)
            texts = {u["word_from"] for u in d["units"] if _is_chrome(u, block[u["unit_id"]], scope)}
            assert len(texts) == REAL_CHROME[key] == docs[key]["chrome"], key

    def test_the_real_corpus_sweep_nothing_shown_is_a_menu_or_footer_text(self):
        """Every shown block of all four pages: not one of the page's own chrome texts, and none
        that stands outside every heading on 30 pages or more."""
        raw, docs = _real_corpus()
        scope = {d["path"] for d in raw.values()}
        for key, d in raw.items():
            block, by_id = _block_of(d), {u["unit_id"]: u for u in d["units"]}
            chrome_en = {u["word_from"] for u in d["units"] if _is_chrome(u, block[u["unit_id"]], scope)}
            assert chrome_en, key
            for b in docs[key]["blocks"]:
                assert b["en"] not in chrome_en, (key, b["en"][:60])
                u = by_id[b["id"]]
                outside = any(p not in scope for p in u["pages"])
                assert not (outside and not b["sec"] and len(u["pages"]) >= 30 and b["b"] not in ("meta-title", "meta-description")), (key, b["en"][:60])
            # and the page's own title and description are still there, as the first blocks
            assert [b["b"] for b in docs[key]["blocks"][:3]] == ["meta-title", "meta-description", "meta-title"], key

    def test_the_menu_and_footer_strings_of_the_design_sample_are_in_no_page_file(self):
        """The nav / footer rows of the design sample (design/sample.json, `menu` and `footer`
        blocks), and the names the operator pointed at, appear as the English of no shown block."""
        _raw, docs = _real_corpus()
        whole = ["San Diego", "Offers", "Schools", "About us", "Privacy Policy", "Vancouver Language School",
                 "info@englishcollege.com",
                 '<a wg-1="">Vancouver Language School</a><a wg-2="">Learn English in Canada</a>'
                 '<a wg-3="">Student Services</a><a wg-4="">School Policies</a>',
                 '<a wg-1="">info@englishcollege.com</a>', '<a wg-1="">Privacy Policy</a>',
                 "1190 Melville St, #300, Vancouver, BC V6E 3W1, Canada",
                 '© 2026 <a wg-1="">College of English Language</a>. All rights reserved.']
        inside = ["info@englishcollege.com", "1190 Melville St", "All rights reserved", "© 2026"]
        for key, doc in docs.items():
            for b in doc["blocks"]:
                assert b["en"] not in whole, (key, b["en"][:60])
                assert not any(s in b["en"] for s in inside), (key, b["en"][:60])


# What today's corpus (2026-10-19) shows and leaves out, per page: (shown = editable, chrome).
REAL_COUNTS = {"cost-of-studying-english": (224, 76), "how-long-to-learn-english": (193, 76),
               "vancouver": (347, 75), "vs-toronto": (216, 75)}
REAL_CHROME = {key: chrome for key, (_shown, chrome) in REAL_COUNTS.items()}


# ── The explicit menu and footer list (Ruling 21:01, round 2) ───────────────────────────
#
# The tests above state the generator's own rule (30 pages, outside every heading); a sweep that uses
# the rule to find the menu can never find a menu text the rule misses. This one compares the
# generator's output with a list that does not come from the rule: the texts of each page's menu and
# footer LANDMARKS on the live English page, found by tools/localize/align.py's landmark finder
# (fixtures/document_chrome_en.json, its `_about` says how it was built and what is kept on purpose).

CHROME_LIST = Path(__file__).resolve().parent / "fixtures" / "document_chrome_en.json"


def _dropped_texts(raw_doc: dict, doc: dict) -> set[str]:
    """Every distinct English text of the page file that is not among the shown blocks."""
    shown = {b["en"] for b in doc["blocks"]}
    return {u["word_from"] for u, _block in GD._in_order(raw_doc)} - shown


def _chrome_differences(listed: dict, raw_doc: dict, doc: dict) -> dict[str, list[str]]:
    """Where the page and the explicit list disagree. All three lists are empty when they agree."""
    expected = (set(listed["landmark_texts"]) - set(listed["kept_on_purpose"])) | set(listed["outside_landmarks"])
    shown = {b["en"] for b in doc["blocks"]}
    return {
        "listed_but_shown": sorted(expected & shown),                         # a menu / footer text still on the page
        "dropped_but_not_listed": sorted(_dropped_texts(raw_doc, doc) - expected),   # something else was left out
        "kept_but_not_shown": sorted(set(listed["kept_on_purpose"]) - shown),  # an exception that is not real
    }


def _real_pages():
    """The four real unit files and their documents. A checkout without them FAILS here: this is the
    check that the menu and footer are out of all four pages, not one to skip."""
    files = sorted(S.UNITS_DIR.glob("*.json")) if S.UNITS_DIR.is_dir() else []
    raw = {d["page"]: d for d in (json.loads(p.read_text(encoding="utf-8")) for p in files)
           if d.get("page") in S.PAGE_KEYS}
    assert set(raw) == set(S.PAGE_KEYS), f"the unit files of {sorted(set(S.PAGE_KEYS) - set(raw))} are not in {S.UNITS_DIR}"
    return raw, GD.load_documents(S.UNITS_DIR)


class TestTheExplicitMenuAndFooterList:
    @pytest.fixture(scope="class")
    def listed(self):
        return json.loads(CHROME_LIST.read_text(encoding="utf-8"))["pages"]

    def test_the_list_has_the_four_pages_and_every_exception_has_a_reason(self, listed):
        assert set(listed) == set(S.PAGE_KEYS)
        for key, entry in listed.items():
            assert entry["landmark_texts"], key
            assert len(set(entry["landmark_texts"])) == len(entry["landmark_texts"]), f"{key}: a text is listed twice"
            for text, why in entry["kept_on_purpose"].items():
                assert text in entry["landmark_texts"] and why.strip(), (key, text)
            assert not set(entry["outside_landmarks"]) & set(entry["landmark_texts"]), key

    def test_on_all_four_pages_every_listed_menu_and_footer_text_is_left_out_and_nothing_else_is(self, listed):
        raw, docs = _real_pages()
        for key in S.PAGE_KEYS:
            assert _chrome_differences(listed[key], raw[key], docs[key]) == {
                "listed_but_shown": [], "dropped_but_not_listed": [], "kept_but_not_shown": []}, key

    def test_the_distinct_texts_dropped_are_exactly_the_list_less_what_is_kept_plus_the_mobile_call_to_action_bar(self, listed):
        raw, docs = _real_pages()
        for key in S.PAGE_KEYS:
            entry = listed[key]
            expected = (set(entry["landmark_texts"]) - set(entry["kept_on_purpose"])) | set(entry["outside_landmarks"])
            assert _dropped_texts(raw[key], docs[key]) == expected, key
            assert len(expected) > 70, f"{key}: a page's menu and footer are about 75 texts, not {len(expected)}"

    def test_a_menu_text_below_the_threshold_is_caught_not_passed(self, units_dir):
        """The check can fail: a menu text on 5 pages (the rule keeps it) is reported as still shown."""
        _corpus(units_dir)
        _write(units_dir, "vancouver", [
            _unit("body", "Body text"),
            _menu("m-high", word_from="About us"),
            _looks_like_menu("m-low", word_from="Contact us", pages=_on(5)),       # below the threshold: not flagged
        ])
        raw = json.loads((units_dir / "vancouver.json").read_text(encoding="utf-8"))
        doc = GD.load_documents(units_dir)["vancouver"]
        listed = {"landmark_texts": ["About us", "Contact us"], "kept_on_purpose": {}, "outside_landmarks": []}
        assert _chrome_differences(listed, raw, doc) == {
            "listed_but_shown": ["Contact us"], "dropped_but_not_listed": [], "kept_but_not_shown": []}
        listed["landmark_texts"] = ["About us"]
        assert _chrome_differences(listed, raw, doc) == {
            "listed_but_shown": [], "dropped_but_not_listed": [], "kept_but_not_shown": []}

    def test_a_dropped_text_the_list_does_not_know_is_caught_not_passed(self, units_dir):
        _corpus(units_dir)
        _write(units_dir, "vancouver", [_unit("body", "Body text"), _menu("m-high", word_from="About us")])
        raw = json.loads((units_dir / "vancouver.json").read_text(encoding="utf-8"))
        doc = GD.load_documents(units_dir)["vancouver"]
        listed = {"landmark_texts": [], "kept_on_purpose": {}, "outside_landmarks": []}
        assert _chrome_differences(listed, raw, doc)["dropped_but_not_listed"] == ["About us"]


# ── Also-on, translations, the pages payload ────────────────────────────────────────────

class TestAlso:
    def test_also_lists_the_other_pages_of_the_four_in_the_desks_order(self, units_dir):
        every = list(PATHS.values())
        _write(units_dir, "how-long-to-learn-english", [_unit("a", pages=every)])
        _write(units_dir, "vancouver", [_unit("a", pages=every)])
        _write(units_dir, "cost-of-studying-english", [_unit("a", pages=every)])
        docs = GD.load_documents(units_dir)
        assert _blocks(docs, "vancouver")[0]["also"] == ["cost-of-studying-english", "how-long-to-learn-english"]
        assert _blocks(docs, "how-long-to-learn-english")[0]["also"] == ["vancouver", "cost-of-studying-english"]

    def test_also_is_left_out_when_there_is_nothing_to_say(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a")])
        assert "also" not in _blocks(GD.load_documents(units_dir))[0]

    def test_also_never_names_a_page_outside_the_four_or_the_page_itself(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a", pages=["/vancouver", "/housing", "/vancouver/vs-toronto"])])
        _write(units_dir, "vs-toronto", [_unit("z")])
        b = _blocks(GD.load_documents(units_dir))[0]
        assert b["also"] == ["vs-toronto"] and (b["lock"], b["out"]) == ("", 1)

    def test_also_names_only_pages_that_were_loaded(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a", pages=list(PATHS.values()))])
        assert _blocks(GD.load_documents(units_dir))[0].get("also") is None


class TestTranslations:
    def test_w_carries_only_translated_non_empty_texts(self, units_dir):
        current = {
            "de": {"word_to": "Hallo", "translated": True},
            "fr": {"word_to": "Salut", "translated": False},      # the website still shows the English
            "es": {"word_to": "", "translated": True},            # nothing to show
            "pt": {"translated": True},                           # no word_to at all
            # it: no entry
            "ja": {"word_to": "こんにちは", "translated": True},
        }
        _write(units_dir, "vancouver", [_unit("a", current=current)])
        assert _blocks(GD.load_documents(units_dir))[0]["w"] == {"de": "Hallo", "ja": "こんにちは"}

    def test_w_follows_the_desks_language_order(self, units_dir):
        current = {c: {"word_to": c, "translated": True} for c, *_ in reversed(S.LOCALES)}
        _write(units_dir, "vancouver", [_unit("a", current=current)])
        assert list(_blocks(GD.load_documents(units_dir))[0]["w"]) == [c for c, *_ in S.LOCALES]

    def test_w_is_always_there_as_an_object(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a", current={})])
        assert _blocks(GD.load_documents(units_dir))[0]["w"] == {}

    def test_markers_are_kept_as_they_are(self, units_dir):
        text = 'Click <a wg-1="">here</a> now'
        _write(units_dir, "vancouver", [_unit("a", word_from=text,
                                              current={"de": {"word_to": 'Hier <a wg-1="">klicken</a>', "translated": True}})])
        b = _blocks(GD.load_documents(units_dir))[0]
        assert b["en"] == text and b["w"]["de"] == 'Hier <a wg-1="">klicken</a>'


class TestPagesPayload:
    @pytest.fixture()
    def docs(self, units_dir):
        _write(units_dir, "vancouver", [_unit("a"), _unit("b", noise=True), _unit("c"),
                                        _unit("d", summary=True), _unit("e", pages=["/vancouver", "/"])],
               built="2026-10-19T09:00:00Z")
        _write(units_dir, "vs-toronto", [_unit("f")], built="2026-10-19T11:30:00Z")
        _write(units_dir, "how-long-to-learn-english", [_unit("g")], built="2026-10-18T23:00:00Z")
        return GD.load_documents(units_dir)

    def test_ids_are_every_shown_block_in_document_order(self, docs):
        first = GD.pages_payload(docs)["pages"][0]
        assert first["key"] == "vancouver" and first["path"] == "/vancouver"
        assert first["count"] == 5 and first["ids"] == ["a", "b", "c", "d", "e"]

    def test_ids_hold_no_block_that_carries_a_lock(self):
        """Nothing sets a lock today; a row a gate flags later will carry one, and the grid must not count it."""
        docs = {"vancouver": {"page": "vancouver", "path": "/vancouver", "built": "x", "chrome": 0, "blocks": [
            {"id": "a", "lock": ""}, {"id": "b", "lock": "broken"}, {"id": "c", "lock": ""}]}}
        entry = GD.pages_payload(docs)["pages"][0]
        assert (entry["count"], entry["ids"]) == (3, ["a", "c"])

    def test_pages_come_in_the_desks_order_with_the_five_fields(self, docs):
        payload = GD.pages_payload(docs)
        assert [p["key"] for p in payload["pages"]] == ["vancouver", "vs-toronto", "how-long-to-learn-english"]
        assert all(list(p) == ["key", "path", "count", "chrome", "ids"] for p in payload["pages"])
        assert list(payload) == ["built", "pages"]

    def test_built_is_the_latest_of_the_files(self, docs):
        assert GD.pages_payload(docs)["built"] == "2026-10-19T11:30:00Z"
        assert docs["vancouver"]["built"] == "2026-10-19T09:00:00Z"

    def test_no_pages_is_an_empty_payload_not_an_error(self):
        assert GD.pages_payload({}) == {"built": "", "pages": []}


# ── The files main() writes ─────────────────────────────────────────────────────────────

def _files(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


class TestMain:
    def test_it_writes_the_page_pages_json_and_one_file_per_page(self, units_dir, stub_js, out_dir):
        _corpus(units_dir)
        assert GD.main() == 0
        want = {"index.html", "data/pages.json"} | {f"data/{k}.json" for k in S.PAGE_KEYS}
        assert set(_files(out_dir)) == want

    def test_it_writes_the_root_redirect_beside_its_own_folder(self, units_dir, stub_js, out_dir):
        """/admin/localization/ is only a redirect to the document page (CEL-045); the dashboard's Localization tabs
        point at it, and since CEL-050 this generator is the one that writes it. It goes NEXT TO the document folder,
        so a test that points OUT_DIR elsewhere never touches the real one."""
        _corpus(units_dir)
        assert GD.main() == 0
        redirect = (out_dir.parent / "index.html").read_text(encoding="utf-8")
        assert redirect == S.render_index_redirect()
        assert S.INDEX_REDIRECT_TO in redirect and "location.replace(" in redirect
        assert not (S.OUT_ROOT / "index.html").samefile(out_dir.parent / "index.html"), "wrote into the real repo"

    def test_the_page_files_hold_the_documents(self, units_dir, stub_js, out_dir):
        _corpus(units_dir)
        GD.main()
        pages = json.loads((out_dir / "data" / "pages.json").read_text(encoding="utf-8"))
        assert [p["key"] for p in pages["pages"]] == S.PAGE_KEYS
        one = json.loads((out_dir / "data" / "vs-toronto.json").read_text(encoding="utf-8"))
        assert list(one) == ["page", "path", "built", "chrome", "blocks"]
        assert one["page"] == "vs-toronto" and one["path"] == PATHS["vs-toronto"] and one["chrome"] == 0
        assert one["built"] == "2026-10-19T11:00:00Z" and pages["built"] == "2026-10-19T13:00:00Z"

    def test_the_json_is_compact_and_keeps_every_script_as_written(self, units_dir, stub_js, out_dir):
        _write(units_dir, "vancouver", [_unit("a", "Café — “quoted”", current={
            "de": {"word_to": "Café — „zitiert“", "translated": True}, "ar": {"word_to": "مرحبا", "translated": True}}),
            _menu("m")])
        for key in S.PAGE_KEYS[1:]:
            _write(units_dir, key, [_unit("x")])
        GD.main()
        text = (out_dir / "data" / "vancouver.json").read_text(encoding="utf-8")
        assert "Café — „zitiert“" in text and "مرحبا" in text and "\\u" not in text
        assert text == json.dumps(json.loads(text), ensure_ascii=False, separators=(",", ":"))

    def test_it_is_deterministic(self, units_dir, stub_js, out_dir, tmp_path, monkeypatch):
        _corpus(units_dir)
        GD.main()
        first = _files(out_dir)
        monkeypatch.setattr(GD, "OUT_DIR", tmp_path / "again")
        GD.main()
        assert _files(tmp_path / "again") == first

    def test_no_file_carries_a_client_rule(self, units_dir, stub_js, out_dir):
        """The runbook's WO-36 scan (tests/test_desk_privacy.py) over what this generator wrote."""
        _corpus(units_dir)
        GD.main()
        files = [p for p in sorted(out_dir.rglob("*")) if p.is_file()]
        assert any(p.suffix == ".json" for p in files) and any(p.suffix == ".html" for p in files)
        assert P.leaks(files) == []
        for p in files:
            if p.suffix == ".json":
                keys = P._keys(json.loads(p.read_text(encoding="utf-8")))
                assert not keys & P.FINDING_KEYS, (p.name, keys & P.FINDING_KEYS)

    def test_the_scan_can_fail_on_what_this_generator_writes(self, units_dir, stub_js, out_dir):
        """verify the verifier: a rule id or a citation in a unit's text must reach the scan."""
        _write(units_dir, "vancouver", [_unit("a", "TG §4.2 says so"), _unit("b", "see XX-SAMPLE-01"), _menu("m")])
        for key in S.PAGE_KEYS[1:]:
            _write(units_dir, key, [_unit("x")])
        GD.main()
        found = P.leaks([out_dir / "data" / "vancouver.json"])
        assert ("vancouver.json", "TG §") in found and ("vancouver.json", "XX-SAMPLE-01") in found

    def test_no_unit_directory_is_exit_2_and_nothing_written(self, tmp_path, stub_js, out_dir, monkeypatch, capsys):
        monkeypatch.setattr(GD, "UNITS_DIR", tmp_path / "nope")
        assert GD.main() == 2 and not out_dir.exists()
        assert "no unit data" in capsys.readouterr().err

    @pytest.mark.parametrize("what", ["empty", "missing", "only the menu"])
    def test_a_page_with_no_texts_is_exit_2_and_nothing_written(self, units_dir, stub_js, out_dir, what, capsys):
        _corpus(units_dir)
        if what == "empty":
            _write(units_dir, "vs-toronto", [])
        elif what == "missing":
            (units_dir / "vs-toronto.json").unlink()
        else:
            _write(units_dir, "vs-toronto", [_menu("m", pages=_on(30, "/vancouver/vs-toronto"))])
        assert GD.main() == 2 and not out_dir.exists()
        assert "vs-toronto" in capsys.readouterr().err

    def test_an_empty_directory_is_exit_2(self, units_dir, stub_js, out_dir):
        assert GD.main() == 2 and not out_dir.exists()

    def test_a_missing_runtime_is_a_clear_error_and_nothing_written(self, units_dir, out_dir, tmp_path, monkeypatch, capsys):
        _corpus(units_dir)
        monkeypatch.setattr(GD, "DOC_JS", tmp_path / "document_desk.js")
        assert GD.main() == 2 and not out_dir.exists()
        assert "document_desk.js" in capsys.readouterr().err
        with pytest.raises(FileNotFoundError, match="document_desk.js"):
            GD.render_page()

    def test_importing_the_module_does_no_work(self):
        env = {"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"}
        done = subprocess.run([sys.executable, "-c", "import localize_desk.generate_document_page"],
                              cwd=TOOLS, env=env, capture_output=True, text=True)
        assert done.returncode == 0 and done.stdout == "" and done.stderr == "", done.stderr


# ── The page ────────────────────────────────────────────────────────────────────────────

class _Dom(HTMLParser):
    """Every element with its attributes and its parent, and whether the tags nest."""
    VOID = {"meta", "link", "img", "input", "br", "hr", "area", "base", "col", "embed", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elems: list[tuple[str, dict]] = []
        self.parent: list[int] = []
        self.texts: list[str] = []
        self.stack: list[int] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.elems.append((tag, dict(attrs)))
        self.parent.append(self.stack[-1] if self.stack else -1)
        if tag not in self.VOID:
            self.stack.append(len(self.elems) - 1)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.elems[self.stack[-1]][0] != tag:
            self.errors.append(f"</{tag}> closes {self.elems[self.stack[-1]][0] if self.stack else 'nothing'}")
        else:
            self.stack.pop()

    def handle_data(self, data):
        if data.strip() and self.stack:
            self.texts.append((self.stack[-1], data.strip()))

    def index(self, ident: str) -> int:
        found = [i for i, (_t, a) in enumerate(self.elems) if a.get("id") == ident]
        assert len(found) == 1, f"id {ident!r} appears {len(found)} times"
        return found[0]

    def by_id(self, ident: str) -> dict:
        return self.elems[self.index(ident)][1]

    def with_class(self, cls: str) -> list[dict]:
        return [a for _t, a in self.elems if cls in (a.get("class") or "").split()]

    def kids(self, i: int) -> list[tuple[str, dict]]:
        """(tag, attrs) of the direct children of element i."""
        return [self.elems[j] for j, p in enumerate(self.parent) if p == i]

    def kids_of_id(self, ident: str):
        return self.kids(self.index(ident))

    def kids_of_class(self, cls: str):
        found = [i for i, (_t, a) in enumerate(self.elems) if cls in (a.get("class") or "").split()]
        assert len(found) == 1, f"class {cls!r} appears {len(found)} times"
        return self.kids(found[0])

    def _within(self, node: int, i: int) -> bool:
        while node != -1:
            if node == i:
                return True
            node = self.parent[node]
        return False

    def text_of(self, ident: str) -> str:
        """The text of the element and everything inside it."""
        i = self.index(ident)
        return " ".join(s for owner, s in self.texts if self._within(owner, i))


def _main_markup(html: str) -> str:
    return html[html.index('<main id="doc"'):html.index("</main>") + len("</main>")]


def _dom(html: str) -> _Dom:
    p = _Dom()
    p.feed(_main_markup(html))
    return p


def _shape(kids) -> list[str]:
    """`tag#id.class` for each (tag, attrs): how the contract writes a child."""
    out = []
    for tag, a in kids:
        s = tag + (f"#{a['id']}" if "id" in a else "")
        if a.get("class"):
            s += "." + ".".join(a["class"].split())
        out.append(s)
    return out


IDS = ["doc", "doc-grid-title", "doc-grid", "doc-bar", "doc-title", "doc-translate", "doc-banner",
       "doc-banner-text", "doc-banner-translate", "doc-outline", "doc-outline-title", "doc-outline-list",
       "doc-sections", "doc-heads", "doc-blocks", "doc-status", "doc-save", "doc-undo", "doc-redo",
       "doc-weglot", "doc-words", "doc-history", "doc-history-title", "doc-history-close",
       "doc-history-list", "doc-confirm", "doc-confirm-title", "doc-confirm-body", "doc-confirm-cancel",
       "doc-confirm-ok", "doc-toasts"]
CLASSES = ["doc", "doc-gridwrap", "doc-grid-title", "scroll-x", "doc-grid", "doc-grid-lang", "doc-grid-page",
           "doc-cell", "doc-cell-status", "doc-cell-count", "doc-bar", "doc-title", "doc-actions", "desk-btn",
           "doc-banner", "is-strong", "doc-layout", "doc-outline", "doc-outline-title", "doc-outline-list",
           "doc-sheets", "doc-sections-wrap", "doc-sections-label", "desk-select", "doc-sections", "doc-heads",
           "doc-head", "doc-head-en", "doc-head-tgt", "doc-head-weglot", "doc-blocks", "doc-status", "doc-save",
           "doc-status-mid", "doc-btn-label", "doc-kbd", "doc-status-end", "doc-toggle", "doc-words",
           "doc-drawer", "doc-history-note", "doc-history-list", "cpw-overlay", "cpw-modal", "cpw-title",
           "cpw-actions", "cpw-btn", "cpw-cancel", "cpw-save", "toast-stack"]


class TestPageShell:
    def test_it_has_the_exact_save_switch_line(self, page):
        assert "var SAVE_OFF = false;" in page.splitlines()

    def test_the_switch_is_the_desks_one_switch(self, stub_js, monkeypatch):
        monkeypatch.setattr(S, "SAVE_OFF", True)
        on = GD.render_page()
        assert "var SAVE_OFF = true;" in on.splitlines() and "var SAVE_OFF = false;" not in on

    def test_the_harness_can_switch_it_the_way_it_switches_the_others(self, page):
        from localize_desk import harness as H
        assert page.count(H.SAVE_ON_LINE) == 1 and H.SAVE_OFF_LINE not in page

    def test_every_id_the_contract_names_is_there_once(self, page):
        dom = _dom(page)
        for ident in IDS:
            dom.index(ident)
        assert page.count('id="doc-config"') == 1

    def test_every_class_the_contract_names_is_there(self, page):
        dom = _dom(page)
        missing = [c for c in CLASSES if not dom.with_class(c)]
        assert not missing, missing

    def test_the_markup_nests(self, page):
        dom = _dom(page)
        assert dom.errors == [] and dom.stack == []

    def test_the_menu_and_the_old_bar_are_gone(self, page):
        main = _main_markup(page)
        for gone in ('class="doc-history"', 'class="doc-actions">\n        <button type="button" id="doc-undo"'):
            assert gone not in main
        dom = _dom(page)
        assert "doc-save" not in [a.get("id") for t, a in dom.kids_of_id("doc-bar")]

    def test_the_shells_children_come_in_the_contracts_order(self, page):
        dom = _dom(page)
        assert _shape(dom.kids_of_id("doc")) == [
            "section.doc-gridwrap", "header#doc-bar.doc-bar", "div#doc-banner.doc-banner", "div.doc-layout",
            "footer#doc-status.doc-status", "aside#doc-history.doc-drawer", "div#doc-confirm.cpw-overlay",
            "div#doc-toasts.toast-stack"]

    def test_the_bar_is_the_title_and_the_translate_button(self, page):
        dom = _dom(page)
        assert _shape(dom.kids_of_id("doc-bar")) == ["h1#doc-title.doc-title", "div.doc-actions"]
        # the rules page's entry point (CEL-046), then Translate
        assert _shape(dom.kids_of_class("doc-actions")) == ["a#doc-rules.desk-btn", "button#doc-translate.desk-btn"]
        assert dom.by_id("doc-rules")["href"] == "/admin/localization/rules/"
        assert dom.text_of("doc-rules") == C.t("doc.rules")
        assert dom.text_of("doc-translate") == C.t("doc.translate")
        assert dom.text_of("doc-title") == ""

    def test_the_layout_is_the_outline_then_the_sheets(self, page):
        dom = _dom(page)
        assert _shape(dom.kids_of_class("doc-layout")) == ["nav#doc-outline.doc-outline", "div.doc-sheets"]
        assert _shape(dom.kids_of_id("doc-outline")) == ["h2#doc-outline-title.doc-outline-title", "ol#doc-outline-list.doc-outline-list"]
        assert dom.by_id("doc-outline")["aria-labelledby"] == "doc-outline-title"
        assert dom.text_of("doc-outline-title") == C.t("doc.outline.title")
        assert dom.kids_of_id("doc-outline-list") == []                  # the runtime fills it

    def test_the_sheets_are_the_sections_select_the_heads_and_the_blocks(self, page):
        dom = _dom(page)
        assert _shape(dom.kids_of_class("doc-sheets")) == [
            "label.doc-sections-wrap", "div#doc-filter-empty.doc-banner", "div#doc-heads.doc-heads",
            "ol#doc-blocks.doc-blocks"]
        assert _shape(dom.kids_of_class("doc-sections-wrap")) == [
            "span.doc-sections-label", "select#doc-sections.desk-select.doc-sections"]
        assert dom.kids_of_id("doc-sections") == []
        assert dom.text_of("doc-sections") == "" and C.t("doc.sections") in " ".join(s for _o, s in dom.texts)
        assert _shape(dom.kids_of_id("doc-heads")) == [
            "span.doc-head.doc-head-en", "span.doc-head.doc-head-tgt", "span.doc-head.doc-head-weglot"]

    def test_the_status_bar_is_save_undo_redo_then_weglot_and_the_word_count(self, page):
        dom = _dom(page)
        assert _shape(dom.kids_of_id("doc-status")) == [
            "p#doc-save.doc-save", "div.doc-status-mid", "div.doc-status-end"]
        assert _shape(dom.kids_of_class("doc-status-mid")) == [
            "button#doc-undo.desk-btn", "button#doc-redo.desk-btn", "label.doc-filter-wrap",
            "button#doc-next.desk-btn", "span#doc-next-count.doc-next-count"]
        for ident, key in (("doc-undo", "doc.undo"), ("doc-redo", "doc.redo"), ("doc-next", "doc.next")):
            assert _shape(dom.kids_of_id(ident)) == ["span.doc-btn-label", "kbd.doc-kbd"]
            assert dom.text_of(ident) == C.t(key)
        assert _main_markup(page).count('<kbd class="doc-kbd"></kbd>') == 3          # the runtime fills them
        assert _shape(dom.kids_of_class("doc-status-end")) == ["label.doc-toggle", "a#doc-desk-version.doc-desk-version", "span#doc-words.doc-words"]
        assert _shape(dom.kids_of_class("doc-toggle")) == ["input#doc-weglot", "span"]
        assert dom.by_id("doc-weglot")["type"] == "checkbox"
        assert dom.text_of("doc-words") == "" and dom.text_of("doc-save") == ""

    def test_the_status_bar_holds_the_filter_and_next_to_check_in_copy_md_words(self, page):
        """CEL-036: a list that narrows the page (All / New from Gemini / Edited / Flagged) and a Next to
        check button with a shortcut; every word is COPY.md's, the key label and the count are the runtime's."""
        dom = _dom(page)
        assert _shape(dom.kids_of_class("doc-filter-wrap")) == ["span.doc-filter-label", "select#doc-filter.desk-select.doc-filter"]
        assert dom.text_of("doc-next-count") == ""                                  # the runtime says how many are left
        markup = _main_markup(page)
        for value, key in (("all", "doc.filter.all"), ("new", "doc.filter.new"),
                           ("edited", "doc.filter.edited"), ("flagged", "doc.filter.flagged")):
            assert f'<option value="{value}">{_html.escape(C.t(key))}</option>' in markup, key
        assert markup.index('value="all"') < markup.index('value="new"') < markup.index('value="edited"') < markup.index('value="flagged"')
        assert C.t("doc.filter.label") in " ".join(s for _o, s in dom.texts)
        assert dom.by_id("doc-next")["aria-keyshortcuts"] == "Alt+Enter"
        assert "disabled" in dom.by_id("doc-next")                                  # nothing to go to until a page is open
        empty = dom.by_id("doc-filter-empty")
        assert "hidden" in empty and "doc-banner" in empty["class"]
        assert C.t("doc.filter.empty") in " ".join(s for _o, s in dom.texts)

    def test_the_status_bar_shows_the_desk_version_from_the_one_source_and_links_to_what_changed(self, page):
        """CEL-042: 'Desk <version>' in the status bar; the number is DESK_VERSION (typed nowhere else) and the
        words are COPY.md's; it opens the CHANGELOG's desk section in a new tab."""
        dom = _dom(page)
        link = dom.by_id("doc-desk-version")
        assert re.fullmatch(r"\d+\.\d+\.\d+", GD.DESK_VERSION)
        assert dom.text_of("doc-desk-version") == C.t("doc.version", version=GD.DESK_VERSION) == f"Desk {GD.DESK_VERSION}"
        assert link["href"] == GD.DESK_CHANGELOG_URL and link["target"] == "_blank" and "noopener" in link["rel"]
        # The client opens this link: the PUBLIC CEL repo's CHANGELOG (the monorepo is private and answers a 404).
        assert GD.DESK_CHANGELOG_URL == "https://github.com/cagdasunal/CEL/blob/main/CHANGELOG.md"
        assert link["data-tip"] == C.t("doc.version.tip")
        src = Path(GD.__file__).read_text(encoding="utf-8")
        assert len(re.findall(r'"\d+\.\d+\.\d+"', src)) == 1                  # the number is typed once

    def test_the_history_drawer_is_a_dialog_with_a_title_a_note_and_an_empty_strip(self, page):
        dom = _dom(page)
        h = dom.by_id("doc-history")
        assert (h["role"], h["aria-modal"], h["aria-labelledby"]) == ("dialog", "false", "doc-history-title")
        assert _shape(dom.kids_of_id("doc-history")) == ["header", "p.doc-history-note", "ol#doc-history-list.doc-history-list"]
        assert dom.text_of("doc-history-title") == C.t("doc.history.title")
        assert dom.text_of("doc-history-close") == C.t("doc.history.close")
        assert dom.kids_of_id("doc-history-list") == []

    def test_the_confirm_window_is_a_dialog(self, page):
        dom = _dom(page)
        modal = dom.with_class("cpw-modal")[0]
        assert (modal["role"], modal["aria-modal"], modal["aria-labelledby"]) == ("dialog", "true", "doc-confirm-title")
        assert dom.text_of("doc-confirm-cancel") == C.t("doc.confirm.cancel")
        assert dom.text_of("doc-confirm-ok") == C.t("doc.translate")

    def test_the_shell_starts_in_its_loading_state(self, page):
        dom = _dom(page)
        assert dom.by_id("doc")["data-state"] == "loading"
        save = dom.by_id("doc-save")
        assert (save["role"], save["aria-live"], save["data-state"]) == ("status", "polite", "loading")
        assert dom.by_id("doc-blocks")["data-weglot"] == "off" and dom.by_id("doc-blocks").get("class") == "doc-blocks"
        assert dom.by_id("doc-toasts")["aria-live"] == "polite"
        assert dom.by_id("doc-heads")["aria-hidden"] == "true"

    def test_what_starts_hidden_or_off_is_hidden_or_off(self, page):
        dom = _dom(page)
        for ident in ("doc-banner", "doc-banner-translate", "doc-history", "doc-confirm"):
            assert "hidden" in dom.by_id(ident), ident
        assert "hidden" in dom.with_class("doc-head-weglot")[0]
        for ident in ("doc-undo", "doc-redo"):
            assert "disabled" in dom.by_id(ident), ident
        assert "disabled" not in dom.by_id("doc-translate")
        assert "hidden" not in dom.by_id("doc-outline") and "hidden" not in dom.by_id("doc-status")

    def test_the_banners_button_is_not_a_second_primary_button(self, page):
        """One filled button on the page at a time (ruling #53): Export, added by document_export.js, is the
        primary one; the banner's Translate page is the strong outlined button (QA of design B, CEL-031)."""
        dom = _dom(page)
        assert "is-primary" not in dom.by_id("doc-banner-translate")["class"]
        assert "is-strong" in dom.by_id("doc-banner-translate")["class"]
        assert dom.with_class("is-primary") == []

    def test_the_grid_is_four_pages_by_eight_languages_in_the_desks_order(self, page):
        dom = _dom(page)
        heads = dom.with_class("doc-grid-lang")
        assert [h["data-lang"] for h in heads] == [c for c, *_ in S.LOCALES]
        rows = [a for t, a in dom.elems if t == "tr" and "data-page" in a]
        assert [r["data-page"] for r in rows] == S.PAGE_KEYS
        cells = dom.with_class("doc-cell")
        assert len(cells) == len(S.PAGE_KEYS) * len(S.LOCALES)
        want = [(k, c) for k in S.PAGE_KEYS for c, *_ in S.LOCALES]
        assert [(a["data-page"], a["data-lang"]) for a in cells] == want
        assert all(a["data-status"] == "unknown" and a["aria-pressed"] == "false" and a["type"] == "button"
                   for a in cells)

    def test_the_grid_reads_as_a_table(self, page):
        dom = _dom(page)
        ths = [a for t, a in dom.elems if t == "th"]
        assert sum(1 for a in ths if a.get("scope") == "col") == 1 + len(S.LOCALES)
        assert sum(1 for a in ths if a.get("scope") == "row") == len(S.PAGE_KEYS)
        assert dom.with_class("doc-gridwrap")[0]["aria-labelledby"] == "doc-grid-title"

    def test_the_grids_words_are_the_desks_names(self, page):
        main = _main_markup(page)
        for key in S.PAGE_KEYS:
            assert C.t(f"page.{key}") in main
        for code, *_ in S.LOCALES:
            assert f">{S.lang_name(code)}</th>" in main
        assert C.t("doc.grid.label") in main and C.t("doc.status.unknown") in main

    def test_the_flags_are_decoration(self, page):
        main = _main_markup(page)
        for _c, _e, _d, flag in S.LOCALES:
            assert f'<span class="doc-flag" aria-hidden="true">{flag}</span>' in main

    def test_no_title_attribute_and_no_inline_style_in_the_markup(self, page):
        markup = page[page.index('<div class="dashboard-shell">'):]
        markup = markup[:markup.index("<script")]
        assert not re.search(r"\btitle\s*=", markup)
        assert not re.search(r"\sstyle\s*=", markup)
        assert not re.search(r"\sstyle\s*=", page[:page.index("<style>")])

    def test_it_is_deterministic(self, stub_js):
        assert GD.render_page() == GD.render_page()


class TestPageHead:
    def test_title_description_and_noindex_come_from_copy_and_the_v1_head(self, page):
        assert f"<title>{C.t('doc.meta.title')}</title>" in page
        assert f'<meta name="description" content="{C.t("doc.meta.description")}">' in page
        assert 'name="robots" content="noindex' in page and 'name="googlebot" content="noindex' in page
        assert S.DASHBOARD_CSS_LINK in page

    def test_exactly_one_inline_style_in_the_head_after_the_dashboard_sheet(self, page):
        head = page[:page.index("</head>")]
        assert head.count("<style>") == 1
        assert head.index(S.DASHBOARD_CSS_LINK) < head.index("<style>")
        assert page.count("<style>") == 1

    def test_the_style_is_the_fields_sheet_then_the_pages_own(self, page):
        style = page[page.index("<style>"):page.index("</style>")]
        rich = GD.RICH_CSS.read_text(encoding="utf-8")
        assert rich in style and GD.DOC_CSS in style
        assert style.index(rich) < style.index(GD.DOC_CSS)

    def test_no_important_anywhere_in_the_style(self, page):
        assert "!important" not in page[page.index("<style>"):page.index("</style>")]


class TestPageScripts:
    def test_the_scripts_come_after_the_markup_in_the_contracts_order(self, page):
        rich = GD.RICH_JS.read_text(encoding="utf-8")
        start = page.index("var SAVE_OFF = ")
        tail = page[start:]
        marks = [page.index("</main>"), start, start + tail.index("var COPY = "),
                 start + tail.index("function callProxy(payload, ms)"), start + tail.index("desk-tip"),
                 page.index('<script type="application/json" id="doc-config">'),
                 page.index(rich), page.index("window.__docStub = true;")]
        assert marks == sorted(marks) and len(set(marks)) == len(marks)
        # and nothing but the account menu's own script sits between the markup and the first of ours
        between = page[marks[0]:page.rindex("<script>", 0, start)]
        assert between.count("<script>") == 1 and "var COPY" not in between

    def test_the_runtime_and_the_field_are_inlined_as_they_are(self, page):
        assert STUB in page
        assert GD.RICH_JS.read_text(encoding="utf-8") in page

    def test_the_runtime_is_the_last_script_but_the_export_module(self, page):
        """CEL-027: document_export.js comes right after the runtime (it reads `window.DocDesk`, which the
        runtime sets before it boots) and is the page's last script."""
        last = page[page.rindex("<script>"):]
        before = page[:page.rindex("<script>")]
        assert GD.EXPORT_JS.read_text(encoding="utf-8") in last and last.rstrip().endswith("</body>\n</html>")
        assert STUB in before[before.rindex("<script>"):]

    def test_the_first_script_carries_the_copy_the_helpers_and_the_shared_scripts(self, page):
        first = page[page.index("var SAVE_OFF = "):]
        first = first[:first.index("</script>")]
        for needle in ("var COPY = {", "function t(key, vals)", "function tn(key, n, vals)",
                       "function callProxy(payload, ms)", "tip.className = 'desk-tip'"):
            assert needle in first, needle

    def test_copy_in_the_page_is_the_whole_document(self, page):
        m = re.search(r"var COPY = (\{.*?\});\n", page)
        assert json.loads(m.group(1).replace("<\\/", "</")) == C.load()

    def test_the_config_names_the_languages_the_pages_and_the_data(self, page):
        m = re.search(r'<script type="application/json" id="doc-config">(.*?)</script>', page, re.S)
        cfg = json.loads(m.group(1))
        assert cfg["locales"] == [{"code": c, "endonym": e, "dir": d, "flag": f} for c, e, d, f in S.LOCALES]
        assert cfg["pages"] == S.PAGE_KEYS
        assert cfg["data"] == "/admin/localization/document/data/" and cfg["version"] == "desk-v2"
        assert list(cfg) == ["locales", "pages", "data", "version"]

    def test_a_script_ender_inside_the_runtime_cannot_end_the_script(self, tmp_path, monkeypatch):
        f = tmp_path / "js.js"
        f.write_text('var s = "</script><b>x</b>"; var t = "</SCRIPT>";\nvar u = "</a>";\n', encoding="utf-8")
        monkeypatch.setattr(GD, "DOC_JS", f)
        html = GD.render_page()
        assert "<\\/script><b>x</b>" in html and "<\\/SCRIPT>" in html
        assert '"</a>"' in html                                  # only a script ender is touched
        assert "</script><b>" not in html

    def test_a_script_ender_in_the_config_cannot_end_the_script(self, stub_js, monkeypatch):
        monkeypatch.setattr(S, "LOCALES", [("de", "</script>", "ltr", "x")] + list(S.LOCALES[1:]))
        html = GD.render_page()
        m = re.search(r'<script type="application/json" id="doc-config">(.*?)</script>', html, re.S)
        assert json.loads(m.group(1))["locales"][0]["endonym"] == "</script>"

    def test_the_inlined_scripts_parse(self, page):
        """node --check over each inline script, when node is on the machine."""
        import shutil
        import tempfile
        node = shutil.which("node")
        if not node:
            pytest.skip("no node on this machine")
        scripts = re.findall(r"<script>\n(.*?)</script>", page, re.S)
        assert len(scripts) >= 3 and any("var COPY = " in js for js in scripts) and any(STUB in js for js in scripts)
        with tempfile.TemporaryDirectory() as tmp:
            for i, js in enumerate(scripts):
                f = Path(tmp) / f"s{i}.js"
                f.write_text(js, encoding="utf-8")
                done = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
                assert done.returncode == 0, (i, done.stderr[:300])


# ── Every word from COPY.md ─────────────────────────────────────────────────────────────

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
            if k in ("title", "aria-label", "placeholder", "data-tip", "data-placeholder", "alt") and v:
                self.out.append(v)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.out.append(data.strip())


def _desk_part(html: str) -> str:
    """The page's own markup: from its shell to the end of its <main> (the shared dashboard
    chrome -- topbar, account menu, which this page closes after its shell -- belongs to
    tools/dashboard.py, not to this document)."""
    start = html.index('<div class="dashboard-shell">')
    return html[start:html.index("</main>", start) + len("</main>")]


class TestNoWordOutsideTheDocument:
    def test_every_visible_word_comes_from_copy(self, stub_js, monkeypatch):
        real = C.load()
        monkeypatch.setattr(C, "load", lambda: {k: "§" for k in real})
        html = GD.render_page()
        p = _Visible()
        p.feed(_desk_part(html))
        assert p.out, "the sentinel page has no text at all"
        stray = [s for s in p.out if re.search(r"[A-Za-z]", s.replace("§", ""))]
        assert not stray, f"text not from COPY.md: {stray[:8]}"
        # and the head: title and description are copy too
        assert "<title>§</title>" in html and '<meta name="description" content="§">' in html

    def test_the_sentinel_page_reaches_the_places_a_person_reads(self, stub_js, monkeypatch):
        """verify the verifier: the sentinel scan sees buttons, headings, the grid, the outline and
        the status bar -- if it saw nothing it could not fail."""
        real = C.load()
        monkeypatch.setattr(C, "load", lambda: {k: "§" for k in real})
        p = _Visible()
        p.feed(_desk_part(GD.render_page()))
        # grid: corner + 8 heads + 4 rows + 32 cells; then the outline title, Sections, Translate x3, Undo, Redo,
        # Show Weglot, the history title, note and Close, Cancel
        assert p.out.count("§") >= 1 + len(S.LOCALES) + len(S.PAGE_KEYS) + len(S.PAGE_KEYS) * len(S.LOCALES) + 12

    def test_the_scan_can_fail(self, page):
        p = _Visible()
        p.feed(_desk_part(page.replace(C.t("doc.undo"), "Undo it", 1)))
        assert "Undo it" in p.out

    def test_the_real_copy_leaves_no_unfilled_placeholder_on_screen(self, page):
        p = _Visible()
        p.feed(_desk_part(page))
        text = " ".join(p.out)
        assert not re.search(r"\{[A-Za-z_]+\}", text), text[:200]
        assert "⟦" not in page

    def test_the_generator_types_no_sentence_of_its_own(self):
        """Its strings are markup, CSS, ids and COPY keys: every `t(...)` asks for a key, and the
        generator sets no text from a literal."""
        src = Path(GD.__file__).read_text(encoding="utf-8")
        body = src.replace(GD.DOC_CSS, "")
        calls = re.findall(r"""\bt\(\s*f?["']([^"']+)["']""", body)
        assert calls and all(re.fullmatch(r"[a-z]+(\.[a-z0-9_\-]+)*\.?", c) for c in calls), calls
        assert not re.search(r"""\.title\s*=|textContent\s*=\s*['"][A-Za-z]""", body)


class TestTheCopyKeysOfThisPage:
    """Contract sections 5, 7.3, 8, 9: the runtime asks for these by name, with these words."""

    NEW = {
        "doc.outline.title": "On this page",
        "doc.outline.search": "Search result",
        "doc.outline.count.one": "{n} text · {edited} edited",
        "doc.outline.count.other": "{n} texts · {edited} edited",
        "doc.sections": "Sections",
        "doc.words.one": "{n} word",
        "doc.words.other": "{n} words",
        "doc.tools.label": "Actions for this text",
        "doc.tool.weglot": "Use the website's text",
        "doc.tool.revert": "Back to Gemini's draft",
        "doc.chars": "{n} of {max}",
        "doc.shared.one": "Also used on 1 other page ({example}). Your wording becomes the wording there too.",
        "doc.shared.other": "Also used on {n} other pages ({example}, …). Your wording becomes the wording on all of them too.",
        "doc.job.waiting": "Gemini is still translating {page} into {language}. This page starts as soon as that one is done, as long as this page stays open.",
        "doc.status.none": "Not translated",
        "doc.status.translating": "Translating…",
        "doc.status.queued": "Queued",
    }

    def test_the_new_keys_have_exactly_the_contracts_words(self):
        copy = C.load()
        wrong = {k: copy.get(k) for k, v in self.NEW.items() if copy.get(k) != v}
        assert not wrong, wrong

    def test_the_replaced_and_the_kept_keys(self):
        copy = C.load()
        assert "doc.job.busy" not in copy                       # replaced by doc.job.waiting
        assert "doc.locked.tag" in copy and "doc.locked.noise" in copy      # the runtime still spells them
        assert "row.shared.home" in copy                         # the document desk spells it
        assert "row.shared.one" not in copy and "row.shared.other" not in copy   # the first desk's, gone with it (CEL-050)

    def test_every_doc_key_is_in_the_page_copy_table(self, page):
        m = re.search(r"var COPY = (\{.*?\});\n", page)
        table = json.loads(m.group(1).replace("<\\/", "</"))
        assert all(table[k] == v for k, v in self.NEW.items())


# ── The page's own CSS: tokens only ─────────────────────────────────────────────────────

def _rules(css: str):
    """(selector, body) for each rule, media queries flattened (as tests/test_desk_style.py does)."""
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        yield " ".join(m.group(1).split("*/")[-1].split()), " ".join(m.group(2).split())


def _declarations(css: str):
    for sel, body in _rules(css):
        for decl in body.split(";"):
            if ":" in decl:
                prop, _, value = decl.partition(":")
                yield sel, prop.strip(), value.strip()


def _rule(selector: str) -> str:
    bodies = [b for s, b in _rules(GD.DOC_CSS) if s == selector]
    assert bodies, f"no rule for {selector}"
    return " ".join(bodies)


COLOUR_PROPS = {"color", "background", "background-color", "background-image", "border", "border-color",
                "border-top", "border-bottom", "border-inline", "border-inline-start", "border-inline-end",
                "outline", "accent-color", "box-shadow", "fill", "stroke", "text-decoration-color", "caret-color"}
NAMED = re.compile(r"\b(white|black|red|green|blue|gray|grey|yellow|orange|purple|pink|brown|silver|"
                   r"transparent|currentcolor|indigo|navy|teal)\b", re.I)


class TestPageCss:
    def test_it_has_rules(self):
        assert len(list(_declarations(GD.DOC_CSS))) > 200

    def test_no_hex_rgb_hsl_or_named_colour(self):
        css = re.sub(r"/\*.*?\*/", "", GD.DOC_CSS, flags=re.S)
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)
        assert not re.search(r"\b(rgb|rgba|hsl|hsla|hwb|lab|lch|oklch|oklab|color)\(", css)
        bad = [(s, p, v) for s, p, v in _declarations(css)
               if p in COLOUR_PROPS and (NAMED.search(re.sub(r"var\([^)]*\)", "", v)))]
        assert not bad, bad

    def test_every_colour_value_is_a_token(self):
        for sel, prop, value in _declarations(GD.DOC_CSS):
            if prop in ("color", "background-color", "accent-color", "outline-color"):
                assert re.fullmatch(r"var\(--[a-z-]+\)", value), (sel, prop, value)
            elif prop == "background":
                assert value == "none" or re.fullmatch(r"var\(--[a-z-]+\)", value), (sel, prop, value)
            elif prop == "background-image":
                assert re.fullmatch(r"linear-gradient\(var\(--[a-z-]+\), var\(--[a-z-]+\)\)", value), (sel, prop, value)
            elif prop in ("border", "border-top", "border-bottom", "border-inline", "border-inline-start",
                          "border-inline-end", "outline") and value not in ("none", "0"):
                assert re.search(r"var\(--[a-z-]+\)", value), (sel, prop, value)
            elif prop == "box-shadow" and value != "none":
                assert re.search(r"var\(--[a-z-]+\)$", value), (sel, prop, value)

    def test_the_shared_marker_and_popover_are_cream_never_the_near_white_elevated(self):
        """Review CEL-072 fix 1 (Ruling 00:29: no near-white --elevated as a background for a card, modal or
        popover; WCAG AA): the marker chip and the popover sit on --surface (the rules page's floating menu does
        the same), their text is --fg, and --fg on --surface (values read from the dashboard stylesheet) is 4.5:1 or more."""
        for sel in (".doc-shared-mark", ".doc-shared-pop"):
            body = _rule(sel)
            assert "background: var(--surface)" in body and "--elevated" not in body, (sel, body)
            assert "color: var(--fg)" in body, (sel, body)
        assert "color: var(--fg)" in _rule(".doc-shared-pop-list")
        assert "--muted" not in _rule(".doc-shared-pop-list") and "--muted" not in _rule(".doc-shared-mark")
        dash = (Path(GD.__file__).resolve().parents[2] / "docs" / "assets" / "css" / "dashboard.css").read_text(encoding="utf-8")

        def hexrgb(name):
            m = re.search(rf"{re.escape(name)}:\s*#([0-9a-fA-F]{{6}});", dash)
            assert m, name
            return [int(m.group(1)[i:i + 2], 16) / 255 for i in (0, 2, 4)]

        def lum(rgb):
            ch = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
            return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
        la, lb = lum(hexrgb("--fg")), lum(hexrgb("--surface"))
        assert (max(la, lb) + 0.05) / (min(la, lb) + 0.05) >= 4.5

    def test_no_important_and_no_title(self):
        assert "!important" not in GD.DOC_CSS
        assert not re.search(r"\btitle\b\s*=", GD.DOC_CSS)

    def test_no_site_lock_selector_is_left(self):
        assert 'data-lock="site"' not in GD.DOC_CSS and '[data-lock="summary"]' not in GD.DOC_CSS
        assert '[data-lock="link"]' not in GD.DOC_CSS and '[data-lock="noise"]' not in GD.DOC_CSS

    def test_indigo_is_the_focus_ring_and_the_checkbox_tick_only(self):
        """The dashboard's rule (tests/test_desk_style.py), held for the page's own sheet. The one
        filled button is the dashboard's own `.desk-btn.is-primary`, which this sheet does not touch."""
        hits = [(s, b) for s, b in _rules(GD.DOC_CSS) if "var(--accent" in b]
        assert hits
        for sel, body in hits:
            assert ":focus-visible" in sel or (sel == ".doc-toggle input" and "accent-color" in body), (sel, body)
        assert "var(--accent-strong)" not in GD.DOC_CSS and "var(--accent-warm)" not in GD.DOC_CSS
        assert ".is-primary" not in GD.DOC_CSS

    def test_the_open_text_is_outlined_in_indigo_and_the_open_cell_is_dark_and_bold(self):
        assert "outline: 2px solid var(--accent)" in _rule(".doc-block > .doc-tgt:focus-visible")
        pressed = _rule('.doc-cell[aria-pressed="true"]')
        assert "var(--fg)" in pressed and "accent" not in pressed
        bold = _rule('.doc-cell[aria-pressed="true"] .doc-cell-status, .doc-cell[aria-pressed="true"] .doc-cell-count')
        assert "font-weight: 700" in bold and "accent" not in bold

    def test_the_current_outline_entry_is_bold_with_a_two_pixel_bar_of_the_text_colour(self):
        body = _rule('.doc-outline-item[aria-current="true"]')
        assert "font-weight: 700" in body and "inset 2px 0 0 var(--fg)" in body and "accent" not in body

    def test_edited_is_a_3px_bar_of_the_text_colour_at_reduced_opacity(self):
        body = _rule('.doc-block[data-source="edit"] .doc-tgt::after')
        assert "width: 3px" in body and "background: var(--fg)" in body
        assert re.search(r"opacity: 0\.\d+", body)

    def test_a_flagged_row_would_be_muted_and_not_a_text_cursor(self):
        body = _rule('.doc-block:not([data-lock=""]) :is(.doc-en, .doc-tgt)')
        assert "color: var(--muted)" in body and "cursor: default" in body

    def test_the_empty_cell_shows_its_placeholder_attribute(self):
        assert "content: attr(data-placeholder)" in _rule(".doc-tgt:empty::before, .doc-weglot:empty::before")

    def test_a_text_weglot_has_no_wording_for_says_so_with_the_same_placeholder_rule(self):
        """CEL-060: the Weglot column's empty cell reads `data-placeholder` (COPY `doc.weglot.none`)."""
        selectors = [s for s, _b in _rules(GD.DOC_CSS)]
        assert ".doc-tgt:empty::before, .doc-weglot:empty::before" in selectors
        assert "doc.weglot.none" in Path(GD.DOC_JS).read_text(encoding="utf-8")

    def test_the_same_as_weglot_mark_is_a_quiet_xs_line_shown_only_with_the_column_on(self):
        body = _rule(".doc-note-same")
        assert "font-size: var(--fs-xs)" in body and "color: var(--muted)" in body
        assert "display: none" in _rule('.doc-blocks:not([data-weglot="on"]) .doc-note-same')

    def test_a_blocks_state_is_the_notes_colour_only(self):
        assert _rule('.doc-block[data-state="saving"] .doc-note') == "color: var(--muted);"
        assert _rule('.doc-block[data-state="error"] .doc-note') == "color: var(--err);"
        assert _rule('.doc-block[data-state="conflict"] .doc-note') == "color: var(--warn);"

    def test_the_character_count_is_a_quiet_muted_xs_line(self):
        body = _rule(".doc-note-chars")
        assert "font-size: var(--fs-xs)" in body and "color: var(--muted)" in body

    def test_the_saving_lines_dot_follows_the_state(self):
        for state, token in (("saving", "--faint"), ("retrying", "--warn"), ("offline", "--warn"),
                             ("conflict", "--warn"), ("stopped", "--err"), ("refused", "--err")):
            sel = f'.doc-save[data-state="{state}"]::before'
            assert any(f"background: var({token})" in b for s, b in _rules(GD.DOC_CSS) if sel in s.split(", ")), state
        assert "background: var(--ok)" in _rule(".doc-save::before")

    def test_font_sizes_are_tokens(self):
        sizes = [(s, v) for s, p, v in _declarations(GD.DOC_CSS) if p == "font-size"]
        assert sizes
        for sel, value in sizes:
            assert re.fullmatch(r"var\(--fs-[a-z0-9-]+\)|calc\(var\(--fs-doc-body\) \+ 1px\)", value), (sel, value)
        used = {v for _s, v in sizes}
        for token in ("var(--fs-doc-body)", "var(--fs-doc-h1)", "var(--fs-doc-h2)", "var(--fs-sm)", "var(--fs-xs)"):
            assert token in used, token

    def test_block_types_have_the_contracts_type_scale(self):
        every = ".doc-block[data-b=\"{}\"] :is(.doc-en, .doc-tgt, .doc-weglot)"
        h1 = _rule(every.format("h1"))
        assert "var(--fs-doc-h1)" in h1 and "font-weight: 700" in h1
        # The page's section titles are h3 (the h2 is the small tagline above them): an h3 is sized like the
        # contract's h2, a card title (h4-h6) stays at body + 1px (QA of design B, CEL-031).
        h2 = _rule('.doc-block:is([data-b="h2"], [data-b="h3"]) :is(.doc-en, .doc-tgt, .doc-weglot)')
        assert "var(--fs-doc-h2)" in h2 and "font-weight: 650" in h2
        base = _rule(".doc-block .doc-en, .doc-block .doc-tgt, .doc-block .doc-weglot")
        assert "var(--fs-doc-body)" in base and "line-height: 1.6" in base
        small = _rule('.doc-block:is([data-b="h4"], [data-b="h5"], [data-b="h6"]) :is(.doc-en, .doc-tgt, .doc-weglot)')
        assert "calc(var(--fs-doc-body) + 1px)" in small and "font-weight: 650" in small
        button = _rule('.doc-block[data-b="button"] :is(.doc-en, .doc-tgt)')
        assert "border-radius: 999px" in button and "var(--border-strong)" in button

    def test_the_search_result_blocks_are_quiet_cards(self):
        card = _rule('.doc-block:is([data-b="meta-title"], [data-b="meta-description"]) :is(.doc-en, .doc-tgt)')
        assert "background: var(--panel)" in card and "border-radius: var(--radius)" in card
        assert "var(--border)" in card

    def test_there_is_no_type_gutter_and_the_tag_shows_on_hover_or_focus_only(self):
        assert "--doc-gutter" not in GD.DOC_CSS
        assert "opacity: 0" in _rule(".doc-tag")
        assert "opacity: 1" in _rule(".doc-block:hover .doc-tag, .doc-block:focus-within .doc-tag")

    def test_radii_are_the_dashboards(self):
        allowed = {"0", "var(--radius)", "var(--radius-sm)", "999px", "50%"}
        for sel, prop, value in _declarations(GD.DOC_CSS):
            if prop == "border-radius":
                assert set(value.split()) <= allowed, (sel, value)

    def test_the_sheets_are_papers_on_a_recessed_area(self):
        assert "background: var(--panel)" in _rule(".doc-sheets")
        assert "--doc-pad: 48px" in _rule(".doc-sheets")
        assert "--doc-pad: 28px" in _rule(".doc-blocks[data-weglot=\"on\"]")
        block = _rule(".doc-block")
        assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in block and "column-gap: 24px" in block
        assert "repeat(3, minmax(0, 1fr))" in _rule('.doc-blocks[data-weglot="on"] .doc-block')
        paper = _rule(".doc-block::before, .doc-block::after")
        assert "background: var(--elevated)" in paper and "border-inline: 1px solid var(--border)" in paper
        assert "grid-row: 1 / -1" in paper
        corners = _rule(".doc-block:last-child::before, .doc-block:last-child::after, .doc-block:last-child > .doc-weglot")
        assert "border-radius: 0 0 var(--radius) var(--radius)" in corners
        assert "border-radius: var(--radius) var(--radius) 0 0" in _rule(".doc-head")
        assert "max-width: 1400px" in _rule(".doc-blocks") and "max-width: 1400px" in _rule(".doc-heads")

    def test_a_flash_is_the_selected_background(self):
        assert _rule(".doc-block[data-flash]") == "background: var(--selected);"
        assert "var(--selected)" in _rule(".doc-block[data-flash]::before, .doc-block[data-flash]::after, .doc-block[data-flash] > .doc-weglot")

    def test_the_outline_rail_is_240px_and_sticky_below_the_dashboard_bar(self):
        assert "grid-template-columns: 240px minmax(0, 1fr)" in _rule(".doc-layout")
        rail = _rule(".doc-outline")
        assert "position: sticky" in rail and "var(--doc-topbar)" in rail and "overflow-y: auto" in rail

    def test_the_status_bar_sticks_to_the_bottom_at_44px(self):
        bar = _rule(".doc-status")
        assert "position: sticky" in bar and "bottom: 0" in bar and "min-height: 44px" in bar
        assert "background: var(--elevated)" in bar and "border-top: 1px solid var(--border)" in bar

    def test_the_history_drawer_slides_up_over_the_sheets_with_its_versions_side_by_side(self):
        d = _rule(".doc-drawer")
        for part in ("position: fixed", "left: 0", "right: 0", "bottom: 44px", "max-height: 50vh", "overflow: auto",
                     "background: var(--elevated)", "animation: doc-slide"):
            assert part in d, part
        assert "@keyframes doc-slide" in GD.DOC_CSS
        strip = _rule(".doc-history-list")
        assert "display: flex" in strip and "flex-direction: row" in strip and "overflow-x: auto" in strip
        assert "min-width: 260px" in _rule(".doc-version")

    def test_the_toolbar_floats_above_the_open_text_and_shows_with_focus_or_hover_only(self):
        tools = _rule(".doc-tools")
        assert "position: absolute" in tools and "visibility: hidden" in tools and "border-radius: 999px" in tools
        assert "visibility: visible" in _rule(".doc-block:focus-within .doc-tools, .doc-block:hover .doc-tools")   # CEL-075 item 14
        assert "display: none" in _rule(".doc-tool-weglot, .doc-tool-revert")
        assert "display: inline-block" in _rule('.doc-blocks[data-weglot="on"] .doc-tool-weglot')
        assert "display: inline-block" in _rule('.doc-block[data-source="edit"] .doc-tool-revert')
        assert "inset-inline-end: calc((100% - 48px) / 3 + 36px)" in _rule('.doc-blocks[data-weglot="on"] .doc-tools')

    def test_no_sticky_or_fixed_bar_can_hide_the_focused_text(self):
        html = _rule("html")
        assert "scroll-padding-bottom: 64px" in html and "scroll-padding-top" in html
        assert "scroll-margin-top" in _rule(".doc-block")

    def test_a_tablet_loses_the_rail_and_gets_the_sections_list(self):
        tablet = GD.DOC_CSS[GD.DOC_CSS.index("@media (max-width: 1024px)"):GD.DOC_CSS.index("@media (max-width: 767px)")]
        assert ".doc-outline { display: none; }" in tablet and ".doc-sections-wrap { display: flex; }" in tablet
        assert "grid-template-columns: minmax(0, 1fr)" in tablet

    def test_a_phone_gets_one_column_english_above_the_translation_and_the_toolbar_under_the_text(self):
        phone = GD.DOC_CSS[GD.DOC_CSS.index("@media (max-width: 767px)"):GD.DOC_CSS.index("@media (prefers-reduced-motion")]
        assert ".doc-heads { display: none; }" in phone
        assert "display: block" in phone and ".doc-block::before, .doc-block::after { display: none; }" in phone
        assert "position: static" in phone and "visibility: visible" in phone
        assert "flex-basis: 100%" in phone
        assert "font-size: var(--fs-base); color: var(--muted)" in phone       # English, muted

    def test_every_element_a_class_gives_a_display_to_has_a_hidden_rule(self):
        for sel in (".doc-weglot[hidden]", ".doc-head-weglot[hidden]", ".doc-conflict[hidden]", ".doc-banner[hidden]",
                    ".doc-drawer[hidden]", ".doc-sections-wrap[hidden]"):
            assert sel in GD.DOC_CSS, sel
        assert GD.DOC_CSS.rstrip().endswith(".doc [hidden] { display: none; }")
        assert "display: none" in _rule(".doc-weglot[hidden], .doc-head-weglot[hidden], .doc-conflict[hidden], "
                                        ".doc-banner[hidden], .doc-drawer[hidden], .doc-sections-wrap[hidden], .doc-tools[hidden]")

    def test_motion_is_switched_off_for_those_who_ask(self):
        assert "@media (prefers-reduced-motion: reduce)" in GD.DOC_CSS

    def test_every_class_the_sheet_styles_is_a_class_of_the_shell_or_the_runtime(self, page):
        """A rule for `.doc-typo` would style nothing: each `.doc-*` class in the sheet is in the
        shell or in the contract's runtime-built markup."""
        runtime = {"doc-block", "doc-tag", "doc-en", "doc-tgt", "doc-weglot", "doc-note", "doc-note-chars",
                   "doc-save-more", "doc-seen-reset",
                   "doc-note-same", "doc-conflict", "doc-tools", "doc-tool-weglot", "doc-tool-revert", "doc-history-btn",
                   "doc-keep-mine", "doc-take-theirs", "doc-outline-item", "doc-outline-name", "doc-outline-count",
                   "doc-version", "doc-version-meta", "doc-version-text", "doc-version-empty", "doc-restore",
                   "doc-shared", "doc-shared-mark", "doc-shared-pop", "doc-shared-pop-text", "doc-shared-pop-list",
                   "doc-shared-warn", "doc-shared-pop-up"}
        in_shell = set()
        for _tag, attrs in _dom(page).elems:
            in_shell |= set((attrs.get("class") or "").split())
        used = set(re.findall(r"\.(doc-[a-z-]+)", GD.DOC_CSS))
        unknown = sorted(c for c in used if c not in in_shell and c not in runtime)
        assert not unknown, unknown


# ── The committed page is what the generator writes today ───────────────────────────────

def test_the_committed_document_page_is_what_the_generator_writes_today(tmp_path, monkeypatch):
    """The browser tests serve the COMMITTED page, and the live check compares it with the site:
    a generator, copy or data change that was never regenerated leaves both on yesterday's page."""
    committed = S.OUT_ROOT / "document"
    if not S.UNITS_DIR.is_dir() or not committed.is_dir():
        pytest.skip("no unit data or no committed document page in this checkout")
    monkeypatch.setattr(GD, "UNITS_DIR", S.UNITS_DIR)
    monkeypatch.setattr(GD, "OUT_DIR", tmp_path / "document")
    assert GD.main() == 0
    fresh = _files(tmp_path / "document")
    have = _files(committed)
    stale = sorted(name for name in fresh if have.get(name) != fresh[name])
    left_over = sorted(set(have) - set(fresh))
    assert not stale and not left_over, (
        "committed document page differs from the generator -- run "
        "`cd tools && python3 -m localize_desk.generate_document_page`: "
        + ", ".join(stale + [f"{n} (no longer written)" for n in left_over]))


def test_the_committed_root_index_is_the_redirect_the_generator_writes_today():
    """docs/admin/localization/index.html: the page every Localization tab of the dashboard opens (CEL-045)."""
    committed = S.OUT_ROOT / "index.html"
    assert committed.is_file(), (
        f"{committed} is missing: it is a committed deliverable (every Localization tab opens it) -- run "
        "`cd tools && python3 -m localize_desk.generate_document_page`")
    assert committed.read_text(encoding="utf-8") == S.render_index_redirect(), (
        "the committed /admin/localization/ redirect differs from the generator -- run "
        "`cd tools && python3 -m localize_desk.generate_document_page`")


def test_the_real_runtime_is_inlined_when_it_exists(tmp_path, monkeypatch):
    """The real document_desk.js, not the stub: it is inlined as written and is valid JS."""
    if not GD.DOC_JS.is_file():
        pytest.skip("document_desk.js is not in this checkout yet")
    html = GD.render_page()
    assert GD.DOC_JS.read_text(encoding="utf-8").replace("</script", "<\\/script") in html
    assert html.count("var SAVE_OFF = ") == 1
