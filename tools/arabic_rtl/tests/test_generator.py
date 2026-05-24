"""Unit tests for the rtlcss diff+reset+scope generator."""
import pytest

from tools.arabic_rtl import generator as g


def _emit(src_css: str, rtl_css: str, exclude=None) -> str:
    return g.emit(g.split_top(src_css), g.split_top(rtl_css),
                  exclude=[] if exclude is None else exclude)


def test_one_sided_margin_flips_and_resets():
    # base has only margin-left; rtlcss renamed it to margin-right -> we must
    # also reset margin-left:0 or the base's margin-left would still apply.
    out = _emit(".x{margin-left:5px}", ".x{margin-right:5px}")
    assert out == 'html[lang="ar"] .x{margin-right:5px;margin-left:0}'


def test_two_sided_margins_swap_without_reset():
    out = _emit(".x{margin-left:5px;margin-right:10px}",
                ".x{margin-left:10px;margin-right:5px}")
    assert out == 'html[lang="ar"] .x{margin-left:10px;margin-right:5px}'


def test_important_carried_on_reset():
    # E1: a reset must keep !important so it beats a base !important.
    out = _emit(".x{margin-left:5px!important}", ".x{margin-right:5px!important}")
    assert out == 'html[lang="ar"] .x{margin-right:5px!important;margin-left:0!important}'


def test_media_query_nesting_preserved():
    out = _emit("@media screen{.x{left:0}}", "@media screen{.x{right:0}}")
    assert out == '@media screen{html[lang="ar"] .x{right:0;left:auto}}'


def test_parity_mismatch_raises():
    # E4: rule-count drift must fail loud, not silently misalign via zip().
    with pytest.raises(RuntimeError):
        g.emit([("a", "x:1")], [("a", "x:1"), ("b", "y:2")], exclude=[])


def test_exclusion_drops_rule():
    # E2: a selector matching an exclude substring is omitted from the override.
    out = _emit(".skip{margin-left:5px}.keep{margin-left:5px}",
                ".skip{margin-right:5px}.keep{margin-right:5px}",
                exclude=[".skip"])
    assert out == 'html[lang="ar"] .keep{margin-right:5px;margin-left:0}'


def test_changed_atrules_counts_keyframes():
    src = g.split_top("@keyframes slide{from{left:0}to{left:9px}}")
    rtl = g.split_top("@keyframes slide{from{right:0}to{right:9px}}")
    assert g.changed_atrules(src, rtl) == 1


def test_split_selector_list_splits_top_level_commas_only():
    # commas inside :is()/:where() must NOT split
    assert g.split_selector_list(".a,.b:is(.c,.d),.e") == [".a", ".b:is(.c,.d)", ".e"]


def test_is_selector_not_corrupted_by_scoping():
    # regression for the scope() comma-split bug: :is(.a,.b) stays intact
    out = _emit(".x:is(.a,.b){margin-left:5px}", ".x:is(.a,.b){margin-right:5px}")
    assert out == 'html[lang="ar"] .x:is(.a,.b){margin-right:5px;margin-left:0}'


def test_font_overrides_direct_usage():
    out = g.font_overrides(g.split_top(".dur-title{font-family:Cameraobscura,serif}"))
    assert out == ('html[lang="ar"] .dur-title{font-family:\'Cairo\',sans-serif;'
                   'letter-spacing:normal;text-transform:none}')


def test_font_overrides_css_variable_targets_root():
    # `:root` must map to html[lang="ar"] (not `html[lang="ar"] :root`, which matches nothing)
    out = g.font_overrides(g.split_top(":root{--h1--font-family:Cameraobscura,serif}"))
    assert out == 'html[lang="ar"]{--h1--font-family:\'Cairo\',sans-serif}'


def test_font_overrides_skips_font_face_definition():
    out = g.font_overrides(g.split_top("@font-face{font-family:'Cameraobscura';src:url(x.woff2)}"))
    assert out == ""


def test_minify_collapses_whitespace_keeping_significant_spaces():
    css = ("@font-face {\n  font-family: 'Cairo';\n  font-weight: 400 700;\n"
           "  src: url(x.woff2) format('woff2');\n}\n.a {\n  margin-left: 0;\n}\n")
    out = g.minify(css)
    assert "\n" not in out
    assert out == ("@font-face{font-family:'Cairo';font-weight:400 700;"
                   "src:url(x.woff2) format('woff2')}.a{margin-left:0}")


def test_minify_preserves_duplicate_properties():
    assert g.minify(".a{display:-webkit-box;display:flex}") == ".a{display:-webkit-box;display:flex}"


def test_minify_recurses_into_media_keeping_query_text():
    assert g.minify("@media screen and (max-width: 991px){\n .a{ left: 0 }\n}") == \
        "@media screen and (max-width: 991px){.a{left:0}}"
