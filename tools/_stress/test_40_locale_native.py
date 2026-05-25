"""(e) Locale-native improve + the ENFORCED anti-AI/human-voice QA — the heart of the ask.

Two contracts, both per the user's words ("Korean first but not Korean-only",
"genuinely human, no em dashes, no AI phrases", "a Korean post is improved IN Korean,
never translated"):

  1. improve_copy is locale-native: for ko AND en, through BOTH the dry-run and the
     live (stubbed) path, it NEVER calls the translator. A spy asserts call-count 0.
  2. copywriter_qa blocks the AI tells universally: an em-dash draft, an AI-template
     opener, and a ≥3-flag hype draft all FAIL in English; a Korean translationese
     draft FAILS in ko; clean human copy PASSES in both. (Fixtures use the REAL banlist
     terms parsed from tools/summary/prompts/locales/{en,ko}.md.)
"""
import pytest

from tools.copywriter import CopyRequest, improve_copy
from tools.copywriter.qa import copywriter_qa

pytestmark = pytest.mark.stress

_CLEAN_EN = "Study English in Vancouver. Classes stay small. Your teacher learns your name by week one."
_CLEAN_KO = "밴쿠버 캠퍼스에서 영어를 배우고 IELTS 점수를 올려요."


# ---------------------------------------------------------------- locale-native (no translate)

@pytest.fixture
def _translate_spy(monkeypatch):
    """Replace translate_batch everywhere it could be reached with a call-counter."""
    calls = {"n": 0}

    def _spy(*a, **k):
        calls["n"] += 1
        return []

    import tools.translator
    import tools.translator.engine
    monkeypatch.setattr(tools.translator.engine, "translate_batch", _spy)
    monkeypatch.setattr(tools.translator, "translate_batch", _spy)
    return calls


@pytest.mark.parametrize("locale", ["ko", "en"])
def test_improve_dry_run_never_translates(locale, _translate_spy):
    clean = _CLEAN_KO if locale == "ko" else _CLEAN_EN
    r = improve_copy(CopyRequest(brief="improve", locale=locale, existing_copy=clean), dry_run=True)
    assert r.locale == locale
    assert _translate_spy["n"] == 0      # locale-native: no translation step, ever


def test_improve_live_path_uses_locale_prompt_and_never_translates(monkeypatch, _translate_spy):
    """The LIVE pipeline (Gemini stubbed) must call the shared client EXACTLY once with the
    TARGET LOCALE's system prompt, return same-locale copy, and never reach the translator.
    (M4: the old test only asserted spy==0 — vacuous, since improve_copy imports no
    translator on any path. These positive assertions prove locale-native generation.)"""
    from tools.core.gemini import client as gemini
    captured: dict = {}

    def _fake_generate_sync(reqs, **k):
        captured["reqs"] = reqs
        return [gemini.BatchResult(custom_id="copy-1", succeeded=True, content=_CLEAN_KO,
                                   input_tokens=12, output_tokens=24)]

    monkeypatch.setattr(gemini, "generate_sync", _fake_generate_sync)
    r = improve_copy(CopyRequest(brief="tighten", locale="ko", existing_copy="옛날 초안."), dry_run=False)

    assert len(captured.get("reqs", [])) == 1          # the shared client was invoked once
    sys_text = "\n".join(b["text"] for b in captured["reqs"][0].system_blocks)
    assert "Locale layer (ko)" in sys_text             # ...with the KO locale layer (native)
    assert r.ok is True and r.locale == "ko" and r.text == _CLEAN_KO  # same-locale result
    assert _translate_spy["n"] == 0                    # translator NEVER called


# ---------------------------------------------------------------- enforced anti-AI QA

def test_qa_blocks_em_dash_en():
    rep = copywriter_qa("Vancouver is a wonderful place to learn — truly.", "en")
    assert rep.ok is False and "em_dash" in rep.hard_fails


def test_qa_blocks_ai_template_opener_en():
    rep = copywriter_qa("In today's fast-paced world, students need English now.", "en")
    assert rep.ok is False and rep.hard_fails  # opener:* hard-fail


def test_qa_blocks_hype_word_threshold_en():
    rep = copywriter_qa(
        "We leverage robust, seamless tools to elevate and unlock your future.", "en"
    )
    assert rep.ok is False and len(rep.flags) >= 3  # >=3 flags => fail


def test_qa_blocks_korean_translationese():
    # 다양한 / 살펴보겠습니다 / 또한 / 매우 / 혁신적인 — all on ko.md's AI-tell banlist.
    rep = copywriter_qa("다양한 강좌를 살펴보겠습니다. 또한 매우 혁신적인 수업을 제공합니다.", "ko")
    assert rep.ok is False
    assert any(f.startswith("banlist[ko]:") for f in rep.flags)


def test_qa_passes_clean_human_copy_en_and_ko():
    assert copywriter_qa(_CLEAN_EN, "en").ok is True
    assert copywriter_qa(_CLEAN_KO, "ko").ok is True


def test_qa_flags_missing_must_keep_fact():
    rep = copywriter_qa(_CLEAN_EN, "en", must_keep_facts=("DLI #O19283785432",))
    assert rep.ok is False
    assert any(f.startswith("missing_fact:") for f in rep.hard_fails)
