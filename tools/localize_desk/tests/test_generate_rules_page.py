"""Tests for the rules page generator (CEL-046): /admin/localization/rules/.

They hold what a browser would not notice: the page is one document that inlines both scripts,
the committed file is what the generator writes today, the CSS has no white or near-white
background (operator ruling 2026-10-20 00:29), the config carries the eight languages and the
four pages, the client's rule text is not in the page (this repository is public), the Markdown
round trip is byte-equal on the seeded bodies (spec section 1), and every COPY key the page
asks for exists.

User-facing words are read from COPY.md through copy_text, never typed here.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from localize_desk import copy_text as C  # noqa: E402
from localize_desk import desk_shared as S  # noqa: E402
from localize_desk import generate_rules_page as GR  # noqa: E402

TOOLS = Path(__file__).resolve().parents[2]
REPO = TOOLS.parent
MD_JS = GR.MD_JS
PAGE_JS = GR.PAGE_JS
COMMITTED = REPO / "docs" / "admin" / "localization" / "rules" / "index.html"
SEED_BODIES = Path("/Users/cagdas/Desktop/dev/webflow/runtime/out/loc2/CEL-046/seed-bodies.json")

# Phrases from the client's own documents: none may be inside the page.
CLIENT_PHRASES = ("Klassengrösse", "Never use *ß*", "Lehrer:innen", "Durchschnittliche")

# Backgrounds the page may use: cream surfaces, the stage, stripes, the notice, and the
# status colours of the 8px save dot. Never a white or near-white one.
# CEL-089: a Done-by pill or tone example is a tint of a token over the cream (never white); a pill's mark is
# filled with its own text colour.
BACKGROUND_OK = re.compile(
    r"^(?:var\(--(?:surface|panel|selected|stripe|notice-bg|ok|warn|muted|faint)\)|transparent|none|currentColor"
    r"|color-mix\(in srgb, var\(--(?:ok|warn|accent-strong)\) \d{1,2}%, transparent\)"
    r"|linear-gradient\(90deg, currentColor 50%, transparent 50%\))$")


@pytest.fixture(scope="module")
def page() -> str:
    return GR.render_page()


@pytest.fixture(scope="module")
def config(page: str) -> dict:
    m = re.search(r'<script type="application/json" id="rules-config">(.*?)</script>', page, re.S)
    assert m, "the config script is missing"
    return json.loads(m.group(1).replace("<\\/", "</"))


def _declarations(css: str, prop: str) -> list[str]:
    return [v.strip() for v in re.findall(r"(?<![\w-])" + prop + r"\s*:\s*([^;}]+)", css)]


# ── 1. The page ─────────────────────────────────────────────────────────────────────────

def test_render_page_is_one_html_page_with_both_scripts_inlined(page):
    assert page.count("</html>") == 1
    assert 'id="rules-app"' in page
    assert 'id="rules-config"' in page
    assert "var COPY =" in page
    for path in (MD_JS, PAGE_JS):
        source = path.read_text(encoding="utf-8")
        line = next(ln for ln in source.splitlines() if len(ln.strip()) > 30 and "</" not in ln)
        assert line in page, f"{path.name} is not inlined (looked for: {line!r})"


# ── 2. The committed page ───────────────────────────────────────────────────────────────

def test_committed_page_equals_what_the_generator_writes_today():
    assert COMMITTED.read_text(encoding="utf-8") == GR.render_page()


# ── 3. No white or near-white background ────────────────────────────────────────────────

def test_css_has_no_elevated_white_hex_rgba_or_important():
    css = GR.RULES_CSS
    assert "--elevated" not in css
    assert not re.search(r"(?<![\w-])white(?![\w-])", css, re.I)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), "a hex colour is in the page CSS"
    assert "rgba(" not in css
    assert "!important" not in css


def test_every_background_value_is_a_cream_token_or_transparent():
    values = _declarations(GR.RULES_CSS, "background(?:-color)?")
    assert values, "the regex found no background declaration"
    bad = [v for v in values if not BACKGROUND_OK.match(v)]
    assert not bad, f"backgrounds outside the allowed set: {sorted(set(bad))}"


# ── 4. The config ───────────────────────────────────────────────────────────────────────

def _token(css: str, name: str) -> str:
    m = re.findall(rf"{re.escape(name)}:\s*([^;]+);", css)
    assert m, f"{name} is not set"
    return m[-1].strip()


def _rgb(value: str, over: tuple[float, float, float], fg: str = "") -> tuple[float, float, float]:
    """A #hex, rgba() or `color-mix(in srgb, var(--fg) N%, transparent)` colour, composited over `over`."""
    if value.startswith("#"):
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    m = re.fullmatch(r"color-mix\(in srgb, var\(--fg\) (\d+(?:\.\d+)?)%, transparent\)", value)
    if m:
        a = float(m.group(1)) / 100
        return tuple(c * a + o * (1 - a) for c, o in zip(_rgb(fg, over), over))
    r, g, b, a = (float(x) for x in re.match(r"rgba\(([^)]*)\)", value).group(1).split(","))
    return tuple(c * a + o * (1 - a) for c, o in zip((r, g, b), over))


def _contrast(fg, bg) -> float:
    def lum(c):
        ch = [v / 255 for v in c]
        ch = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    la, lb = lum(fg), lum(bg)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_every_text_colour_reaches_wcag_aa_on_the_cream_and_on_the_selected_stage():
    """Review CEL-046 fix 4 (Ruling 00:29: WCAG AA): the page's muted and faint text on --surface and on the
    --selected stage reach 4.5:1. The values come from the dashboard stylesheet and this page's overrides."""
    dash = (Path(GR.__file__).resolve().parents[2] / "docs" / "assets" / "css" / "dashboard.css").read_text(encoding="utf-8")
    surface = _rgb(_token(dash, "--surface"), (255, 255, 255))
    stage = _rgb(_token(dash, "--selected"), surface)
    fg = _rgb(_token(dash, "--fg"), surface)
    for name in ("--muted", "--faint"):
        value = _token(GR.RULES_CSS, name)                       # the page's own, not the dashboard's 0.65 / 0.45
        for bg_name, bg in (("--surface", surface), ("--selected", stage)):
            ratio = _contrast(_rgb(value, bg, fg=_token(dash, "--fg")), bg)
            assert ratio >= 4.5, f"{name} on {bg_name}: {ratio:.2f}:1"
    assert _contrast(fg, surface) >= 4.5 and _contrast(fg, stage) >= 4.5


def test_config_carries_the_eight_locales(config):
    locales = config["locales"]
    assert len(locales) == 8
    for loc in locales:
        assert loc["code"] and loc["name"] and loc["flag"]


def test_config_carries_the_locales_and_the_page_keys_and_nothing_of_the_editor(config):
    # CEL-080: no checked or suggested rules. CEL-085: the desk's page keys, for the keyword briefs it shows read-only.
    # CEL-089: the Done-by map of option A. CEL-099: our quality checks per language.
    assert set(config) == {"locales", "pages", "doneBy", "quality"}
    assert config["pages"] == list(S.PAGE_KEYS)


def test_the_quality_list_holds_copy_keys_and_numbers_only(config):
    # CEL-099: per language [kind, key, params], built from the engine's sources in the monorepo
    # (runtime/out/loc2/CEL-099/build_quality.py): every key is a COPY line, every number one its words show,
    # and no rule id or client word (the repository is public).
    q = config["quality"]
    assert set(q) == {"langs"} and set(q["langs"]) == {code for code, *_ in S.LOCALES}
    table = C.load()
    for lang, lines in q["langs"].items():
        kinds = [e[0] for e in lines]
        assert kinds and set(kinds) == {"prompt", "check"}, lang
        assert kinds == sorted(kinds, key=lambda k: k != "prompt"), lang            # the prompt's rules first
        for kind, key, params in lines:
            assert re.fullmatch(r"[a-z0-9_]+", key), (lang, key)
            line = table[f"rules.qc.{key}"]
            assert all(isinstance(v, int) and "{" + p + "}" in line for p, v in params.items()), (lang, key)
            assert not re.findall(r"\{(\w+)\}", line) or set(re.findall(r"\{(\w+)\}", line)) <= set(params) | {"language"}


def test_the_done_by_map_holds_hashes_and_codes_and_no_client_words(config):
    # The repository is public: the map keys a client line by an 8-hex hash, its values are a Done-by kind, a
    # reason key and an optional warn mark. Nothing else: no client words, no rule ids (test_desk_privacy).
    done = config["doneBy"]
    assert set(done) == {"v", "sections", "langs"}
    assert set(done["langs"]) == {code for code, *_ in S.LOCALES}
    code = re.compile(r"^(?:meta|rule|builtin\.(?:page|structure|export)|slug|glossary|flag|keywords|schema|warn|)$")
    for lang, lines in done["langs"].items():
        assert lines, lang
        for key, val in lines.items():
            assert re.fullmatch(r"[0-9a-f]{8}", key), (lang, key)
            assert val[0] in ("check", "prompt", "none") and 1 <= len(val) <= 3, (lang, val)
            assert all(code.match(v) for v in val[1:]), (lang, val)


def test_config_json_has_no_script_closer():
    assert "</" not in GR._config()


# ── 5. Privacy ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase", CLIENT_PHRASES)
def test_page_embeds_no_client_rule_text(page, phrase):
    assert phrase not in page


# ── 6. Round trip (spec section 1 guard) ────────────────────────────────────────────────

NODE = shutil.which("node")

ROUND_TRIP_JS = r"""
const assert = require('assert');
const md = require(process.argv[1]);
const bodies = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
const bad = Object.keys(bodies).filter(k => md.serialize(md.parse(bodies[k])) !== bodies[k]);
assert.deepStrictEqual(bad, [], 'round trip differs for: ' + bad.join(', '));
console.log('bodies ' + Object.keys(bodies).length);
"""

EDIT_JS = r"""
const assert = require('assert');
const md = require(process.argv[1]);

// adjacent pipes in a glossary cell survive a round trip
const out = md.serializeGlossary('German', [{ en: 'a||b', to: 'x|y', keep: true }]);
const g = md.parseGlossary(out);
assert.strictEqual(g.terms.length, 1);
assert.strictEqual(g.terms[0].en, 'a||b');
assert.strictEqual(g.terms[0].to, 'x|y');
assert.strictEqual(g.terms[0].keep, true);

// one edited item changes only its own line
const body = '# T\n\n- one\n- two\n- three\n\n| h | i |\n| --- | --- |\n| a | b |\n';
const blocks = md.parse(body);
const item = blocks.filter(b => b.kind === 'item')[1];
item.edited = true;
item.text = 'new';
const after = md.serialize(blocks);
const a = body.split('\n'), b = after.split('\n');
assert.strictEqual(a.length, b.length);
const changed = a.map((l, i) => i).filter(i => a[i] !== b[i]);
assert.deepStrictEqual(changed, [3]);
assert.strictEqual(b[3], '- new');
const fc = md.firstChange(body, after);
assert.deepStrictEqual(fc, { before: '- two', after: '- new' });
console.log('ok');
"""


def _node(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([NODE, "-e", script, *args], capture_output=True, text=True, timeout=60)


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_seeded_bodies_round_trip_byte_equal():
    if not SEED_BODIES.is_file():
        pytest.skip("seed-bodies.json is not readable here")
    try:
        SEED_BODIES.read_text(encoding="utf-8")
    except OSError:
        pytest.skip("seed-bodies.json is not readable here")
    res = _node(ROUND_TRIP_JS, str(MD_JS), str(SEED_BODIES))
    assert res.returncode == 0, res.stderr or res.stdout


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_glossary_pipes_and_single_edit_change_only_their_own_text():
    res = _node(EDIT_JS, str(MD_JS))
    assert res.returncode == 0, res.stderr or res.stdout


# ── 7. Every key the page asks for exists ───────────────────────────────────────────────

KEY = r"[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+"


def _keys_used() -> tuple[set[str], set[str]]:
    js = PAGE_JS.read_text(encoding="utf-8")
    py = Path(GR.__file__).read_text(encoding="utf-8")
    plain = set(re.findall(r"(?<![\w.$])t\(\s*['\"](" + KEY + r")['\"]", js))
    plain |= set(re.findall(r"(?<![\w.$])t\(\s*\"(" + KEY + r")\"", py))
    plural = set(re.findall(r"(?<![\w.$])tn\(\s*['\"](" + KEY + r")['\"]", js))
    return plain, plural


def test_page_finds_the_copy_keys_it_uses():
    plain, plural = _keys_used()
    assert len(plain) >= 8 and not plural, "the key scan found almost nothing: the regex is wrong"


def test_every_copy_key_the_page_asks_for_exists():
    table = C.load()
    plain, plural = _keys_used()
    missing = sorted(k for k in plain if k not in table)
    missing += sorted(k + suffix for k in plural for suffix in (".one", ".other") if k + suffix not in table)
    assert not missing, f"keys missing from COPY.md: {missing}"
