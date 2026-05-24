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
