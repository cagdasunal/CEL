"""The Export window and Re-translate of the document page (desk v2, CEL-027): the pieces a unit test can hold.

The module itself (`document_export.js`) is exercised in a real browser by
`tests/browser/test_document_export_browser.py`. Here: it is inlined where the contract says, it only
reads what the runtime hands it (`window.DocDesk`), its decision builder says what the plan says, and the
zip it makes is a real zip (read back with Python's own `zipfile`, whatever node makes of the bytes).
"""
from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from localize_desk import generate_document_page as GD  # noqa: E402

HERE = Path(__file__).resolve().parents[1]
MODULE = HERE / "document_export.js"
RUNTIME = HERE / "document_desk.js"
NODE = shutil.which("node")


def _node(script: str) -> dict:
    """Run `script` in node with the module loaded as `M`; it prints one JSON value."""
    prog = f"const M = require({json.dumps(str(MODULE))});\n" + script
    done = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


# ── the page ────────────────────────────────────────────────────────────────────────────────────
def test_the_committed_page_inlines_the_module_and_its_style_after_the_runtime():
    page = (GD.OUT_DIR / "index.html").read_text(encoding="utf-8")
    assert MODULE.read_text(encoding="utf-8") in page
    style = page[page.index("<style>"):page.index("</style>")]
    assert GD.EXPORT_CSS.read_text(encoding="utf-8") in style
    assert page.index(RUNTIME.read_text(encoding="utf-8")) < page.index(MODULE.read_text(encoding="utf-8"))


def test_the_module_is_never_served_as_a_file_of_its_own():
    served = {p.name for p in (GD.OUT_DIR).rglob("*")}
    assert "document_export.js" not in served and "document_export.css" not in served


def test_the_modules_style_follows_the_desks_rules():
    css = GD.EXPORT_CSS.read_text(encoding="utf-8")
    assert "!important" not in css and "font-weight: 600" not in css and "#fff" not in css.lower()
    # indigo only on focus and the checkbox tick, as the desk's colour rule says
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if "var(--accent)" in body or "93,96,238" in body:
            assert any(ok in sel for ok in (":focus-visible", "input")), sel


def test_the_module_builds_its_dom_by_script_not_by_the_generator():
    """Nothing of the window is in the generator's markup (CEL-026's `_dom()` is not touched)."""
    dom = GD._dom()
    for needle in ("doc-export", "ex-modal", "rt-modal", "rp-modal"):
        assert needle not in dom, needle


def test_the_module_uses_no_innerhtml_and_no_title_attribute():
    src = MODULE.read_text(encoding="utf-8")
    assert "innerHTML" not in src and "insertAdjacentHTML" not in src
    assert not re.search(r"setAttribute\(\s*'title'", src)


# ── the one door ────────────────────────────────────────────────────────────────────────────────
def test_every_name_the_module_reads_from_the_runtime_is_handed_over():
    """`D.x` in document_export.js must be a property of the `window.DocDesk = {...}` block of
    document_desk.js: a later edit of the runtime cannot drop one unseen."""
    used = set(re.findall(r"\bD\.([A-Za-z]+)\b", MODULE.read_text(encoding="utf-8")))
    runtime = RUNTIME.read_text(encoding="utf-8")
    block = runtime[runtime.index("window.DocDesk = {"):]
    block = block[:block.index("};")]
    handed = set(re.findall(r"\b([A-Za-z]+)\s*:", block))
    assert used, "the module reads nothing from DocDesk?"
    assert used <= handed, f"the runtime does not hand over: {sorted(used - handed)}"


def test_the_module_does_nothing_without_the_runtime_or_with_saving_off():
    src = MODULE.read_text(encoding="utf-8")
    assert "if (!D || D.saveOff) return;" in src


# ── the pure parts, in node ─────────────────────────────────────────────────────────────────────
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


@needs_node
def test_crc32_matches_the_standard_check_value():
    got = _node("console.log(JSON.stringify({c: M.crc32(new TextEncoder().encode('123456789'))}))")
    assert got["c"] == 0xCBF43926


@needs_node
def test_the_zip_is_a_real_zip_with_utf8_names_and_exact_bytes():
    script = r'''
    const enc = new TextEncoder();
    const files = [
      {name: 'weglot-de-vancouver.csv', data: enc.encode(`id;language_from\n;en;de;"a ""b""";"ä ö ü ß";Text\n`)},
      {name: 'weglot-ja-cost-of-studying-english.csv', data: enc.encode('日本語 🙂\r\nzwei\n')},
      {name: 'weglot-ar-vs-toronto.csv', data: enc.encode('')},
    ];
    const bytes = M.zip(files, new Date(2026, 9, 19, 22, 30, 12));
    console.log(JSON.stringify({bytes: Array.from(bytes)}));
    '''
    got = _node(script)
    blob = bytes(got["bytes"])
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        assert z.testzip() is None
        assert z.namelist() == ["weglot-de-vancouver.csv", "weglot-ja-cost-of-studying-english.csv",
                                "weglot-ar-vs-toronto.csv"]
        assert z.read("weglot-de-vancouver.csv").decode("utf-8") == 'id;language_from\n;en;de;"a ""b""";"ä ö ü ß";Text\n'
        assert z.read("weglot-ja-cost-of-studying-english.csv").decode("utf-8") == "日本語 🙂\r\nzwei\n"
        assert z.read("weglot-ar-vs-toronto.csv") == b""
        assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
        assert z.infolist()[0].date_time == (2026, 10, 19, 22, 30, 12)


@needs_node
def test_the_zip_is_deterministic_and_one_byte_changes_the_crc():
    script = r"""
    const enc = new TextEncoder(), when = new Date(2026, 9, 19, 22, 30, 12);
    const a = M.zip([{name: 'a.csv', data: enc.encode('x')}], when);
    const b = M.zip([{name: 'a.csv', data: enc.encode('x')}], when);
    const c = M.zip([{name: 'a.csv', data: enc.encode('y')}], when);
    console.log(JSON.stringify({same: Buffer.compare(Buffer.from(a), Buffer.from(b)) === 0,
                                differs: Buffer.compare(Buffer.from(a), Buffer.from(c)) !== 0}));
    """
    assert _node(script) == {"same": True, "differs": True}


CANON = """
const FIELDS = ['tray', 'text', 'approvedAgainst', 'rejected'];
const canon = (r) => { if (!r) return null; const o = {};
  FIELDS.forEach((k) => { const v = r[k]; if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)) return; o[k] = v; });
  return Object.keys(o).length ? o : null; };
"""


@needs_node
@pytest.mark.parametrize("rec, draft, block, expect", [
    # the reviewer's edit wins over the draft; approved against what the website shows now
    ({"text": "mine"}, "gemini", {"en": "Hello", "w": {"de": "Hallo"}}, {"tray": "csv", "text": "mine", "approvedAgainst": "Hallo"}),
    # no edit: the draft
    (None, "gemini", {"en": "Hello", "w": {"de": "Hallo"}}, {"tray": "csv", "text": "gemini", "approvedAgainst": "Hallo"}),
    # the page shows English there (no `w`): approved against the English
    (None, "gemini", {"en": "Hello"}, {"tray": "csv", "text": "gemini", "approvedAgainst": "Hello"}),
    # neither an edit nor a draft: nothing to say, never Weglot's own text
    (None, "", {"en": "Hello", "w": {"de": "Hallo"}}, None),
    ({"tray": "csv"}, None, {"en": "Hello", "w": {"de": "Hallo"}}, None),
    # a note the reviewer gave is kept
    ({"text": "mine", "rejected": "old"}, "", {"en": "Hello"}, {"tray": "csv", "text": "mine", "approvedAgainst": "Hello", "rejected": "old"}),
])
def test_the_decision_a_text_is_exported_as(rec, draft, block, expect):
    script = CANON + f"""
    console.log(JSON.stringify({{r: M.exportRecord({json.dumps(rec)}, {json.dumps(draft)}, {json.dumps(block)}, 'de', canon)}}));
    """
    got = _node(script)["r"]
    assert got == expect


@needs_node
def test_an_exported_text_exports_to_the_very_same_record():
    """Idempotent: a second export of an unchanged page writes nothing (the desk compares canon records)."""
    script = CANON + """
    const block = {en: 'Hello', w: {de: 'Hallo'}};
    const once = M.exportRecord({text: 'mine'}, '', block, 'de', canon);
    const twice = M.exportRecord(once, '', block, 'de', canon);
    console.log(JSON.stringify({same: JSON.stringify(once) === JSON.stringify(twice)}));
    """
    assert _node(script) == {"same": True}
