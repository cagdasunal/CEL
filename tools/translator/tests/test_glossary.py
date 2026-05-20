"""Tests for the translator glossary."""
from tools.translator.glossary import Glossary, GlossaryTerm, load_glossary


def test_load_default_glossary_has_brand_dnt_terms():
    g = load_glossary()
    assert g.version  # non-empty
    cel = next((t for t in g.terms if t.term == "CEL"), None)
    assert cel is not None and cel.do_not_translate
    college = next((t for t in g.terms if t.term == "College of English Language"), None)
    assert college is not None and college.do_not_translate


def test_match_finds_present_terms_only():
    g = Glossary(terms=[
        GlossaryTerm(term="CEL", do_not_translate=True, case_sensitive=True),
        GlossaryTerm(term="IELTS", do_not_translate=True, case_sensitive=True),
    ], version="1")
    matched = g.match("Study at CEL and prepare for your exam.")
    assert {t.term for t in matched} == {"CEL"}


def test_prompt_slice_lists_dnt_terms():
    g = Glossary(terms=[GlossaryTerm(term="CEL", do_not_translate=True)], version="1")
    slice_ = g.prompt_slice(g.match("Welcome to CEL"), "de")
    assert "CEL" in slice_
    assert "verbatim" in slice_.lower()


def test_enforce_flags_dropped_dnt_term():
    g = Glossary(terms=[GlossaryTerm(term="CEL", do_not_translate=True, case_sensitive=True)], version="1")
    # Source has CEL; target dropped it → flag.
    _, flags = g.enforce("Study at CEL", "Studieren Sie bei uns", "de")
    assert any(f.startswith("dnt_term_dropped:CEL") for f in flags)


def test_enforce_clean_when_dnt_preserved():
    g = Glossary(terms=[GlossaryTerm(term="CEL", do_not_translate=True, case_sensitive=True)], version="1")
    _, flags = g.enforce("Study at CEL", "Studieren Sie bei CEL", "de")
    assert flags == []


def test_enforce_flags_forbidden_term():
    g = Glossary(terms=[GlossaryTerm(term="cheap", forbidden=True)], version="1")
    _, flags = g.enforce("affordable housing", "cheap housing", "en")
    assert any(f.startswith("forbidden_term_present:cheap") for f in flags)
