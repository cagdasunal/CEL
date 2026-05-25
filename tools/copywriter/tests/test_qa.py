"""The anti-AI / human-voice QA gate — the copywriter's centerpiece (Plan C)."""
import pytest

from tools.copywriter.qa import _load_locale_banlist, copywriter_qa

CLEAN_EN = (
    "Most students reach a working B2 in about 12 weeks here. The catch: that assumes "
    "25 hours of class a week plus real homework most evenings. Skip the homework, add a "
    "month. Vancouver helps. You're surrounded by English the moment you leave campus."
)


def test_clean_english_passes():
    r = copywriter_qa(CLEAN_EN, "en")
    assert r.ok, r.summary()


def test_em_dash_is_hard_fail():
    r = copywriter_qa("Vancouver is vibrant, dynamic, and immersive — come study here.", "en")
    assert not r.ok
    assert "em_dash" in r.hard_fails


def test_ai_opener_is_hard_fail():
    r = copywriter_qa("In today's fast-paced world, learning English has never mattered more.", "en")
    assert not r.ok
    assert any(h.startswith(("opener", "template")) for h in r.hard_fails)


def test_three_ai_words_fail_via_flags():
    txt = ("We delve into grammar, leverage a proven methodology, and offer a seamless "
           "path to fluency. Furthermore, our classes stay small.")
    r = copywriter_qa(txt, "en")
    assert not r.ok
    assert len(r.flags) >= 3, r.summary()


def test_missing_must_keep_fact_is_hard_fail():
    r = copywriter_qa(CLEAN_EN, "en", must_keep_facts=("DLI #O19395677113",))
    assert not r.ok
    assert any(h.startswith("missing_fact") for h in r.hard_fails)


def test_present_must_keep_fact_ok():
    txt = CLEAN_EN + " Our DLI number is O19395677113."
    r = copywriter_qa(txt, "en", must_keep_facts=("O19395677113",))
    assert not any(h.startswith("missing_fact") for h in r.hard_fails)
    assert r.ok, r.summary()


def test_korean_banlist_loads_from_reused_locale_layer():
    bl = _load_locale_banlist("ko")
    assert "다양한" in bl and "또한" in bl


def test_korean_translationese_fails():
    # banlist[ko] hits: 매우, 다양한, 또한, 결론적으로, 정말로 (>= 3 => fail)
    txt = "매우 다양한 프로그램입니다. 또한 결론적으로 정말로 좋습니다."
    r = copywriter_qa(txt, "ko")
    assert not r.ok, r.summary()
    assert len([f for f in r.flags if f.startswith("banlist[ko]")]) >= 3


def test_korean_clean_passes():
    txt = "대부분의 학생은 밴쿠버 캠퍼스에서 12주 풀타임 학습으로 B2 수준에 도달합니다. 주당 25시간 수업과 매일 저녁 한 시간의 자습이 전제입니다."
    r = copywriter_qa(txt, "ko")
    assert r.ok, r.summary()
