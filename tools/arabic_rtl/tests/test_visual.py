"""Unit tests for the Gemini-vision visual pass (offline — no SDK/browser/network)."""
from datetime import datetime, timedelta, timezone

from tools.arabic_rtl import visual as v

NOW = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)


# ---- slug / inventory -------------------------------------------------------

def test_slug_for():
    assert v.slug_for("https://www.englishcollege.com/ar/vancouver") == "ar-vancouver"
    assert v.slug_for("https://www.englishcollege.com/ar") == "ar"
    assert v.slug_for("https://www.englishcollege.com/ar/vancouver/cost-of-studying") \
        == "ar-vancouver-cost-of-studying"


def test_ltr_url_for():
    assert v.ltr_url_for("https://www.englishcollege.com/ar/vancouver") \
        == "https://www.englishcollege.com/vancouver"
    assert v.ltr_url_for("https://www.englishcollege.com/ar") == "https://www.englishcollege.com/"
    assert v.ltr_url_for("https://www.englishcollege.com/ar/vancouver/cost") \
        == "https://www.englishcollege.com/vancouver/cost"


def test_class_inventory_dedupes_and_splits():
    html = '<div class="a b"></div><span class="b c"></span>'
    assert v.class_inventory(html) == ["a", "b", "c"]


# ---- eligibility state machine (the four branches) --------------------------

def test_eligible_when_never_analyzed():
    assert v.is_eligible("/ar/x", "h1", {}, NOW) is True


def test_skip_when_css_unchanged():
    state = {"/ar/x": {"css_hash": "h1", "analyzed_at": NOW.isoformat()}}
    assert v.is_eligible("/ar/x", "h1", state, NOW) is False


def test_skip_when_changed_but_within_a_week():
    state = {"/ar/x": {"css_hash": "old", "analyzed_at": (NOW - timedelta(days=3)).isoformat()}}
    assert v.is_eligible("/ar/x", "new", state, NOW) is False


def test_eligible_when_changed_and_over_a_week():
    state = {"/ar/x": {"css_hash": "old", "analyzed_at": (NOW - timedelta(days=8)).isoformat()}}
    assert v.is_eligible("/ar/x", "new", state, NOW) is True


def test_eligible_when_timestamp_unparseable():
    state = {"/ar/x": {"css_hash": "old", "analyzed_at": "not-a-date"}}
    assert v.is_eligible("/ar/x", "new", state, NOW) is True


# ---- validation trust boundary ---------------------------------------------

def _rule(sel, decl):
    return {"selector": sel, "declarations": decl, "reason": "r"}


def test_validate_scopes_a_grounded_rule():
    out = v.validate_rules([_rule(".dur-title", "text-align:right;letter-spacing:normal")],
                           {"dur-title"})
    assert out == ['html[lang="ar"] .dur-title{text-align:right;letter-spacing:normal}']


def test_validate_allows_element_only_selector():
    out = v.validate_rules([_rule("blockquote", "border-right:3px solid #000")], set())
    assert out == ['html[lang="ar"] blockquote{border-right:3px solid #000}']


def test_validate_drops_hallucinated_class():
    assert v.validate_rules([_rule(".not-on-page", "left:0")], {"dur-title"}) == []


def test_validate_drops_external_url():
    assert v.validate_rules([_rule(".dur-title", "background:url(https://evil.com/x.png)")],
                            {"dur-title"}) == []


def test_validate_allows_self_hosted_url():
    out = v.validate_rules(
        [_rule(".dur-title", "background:url(https://cel.englishcollege.com/a.png)")],
        {"dur-title"})
    assert out == ['html[lang="ar"] .dur-title{background:url(https://cel.englishcollege.com/a.png)}']


def test_validate_drops_import_and_js_and_breakout():
    assert v.validate_rules([_rule(".dur-title", "@import url(x)")], {"dur-title"}) == []
    assert v.validate_rules([_rule(".dur-title", "background:url(javascript:alert(1))")],
                            {"dur-title"}) == []
    assert v.validate_rules([_rule(".dur-title", "color:red}html{x:1")], {"dur-title"}) == []


# ---- defensive JSON parse ---------------------------------------------------

def test_parse_plain_array():
    assert v._parse_json_array('[{"selector":".x","declarations":"left:0","reason":"r"}]') \
        == [{"selector": ".x", "declarations": "left:0", "reason": "r"}]


def test_parse_strips_code_fence():
    assert v._parse_json_array('```json\n[{"a":1}]\n```') == [{"a": 1}]


def test_parse_salvages_embedded_array():
    assert v._parse_json_array('here you go: [{"a":1}] thanks') == [{"a": 1}]


def test_parse_returns_empty_on_garbage_or_object():
    assert v._parse_json_array("not json at all") == []
    assert v._parse_json_array('{"a":1}') == []
