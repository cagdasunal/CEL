"""Prompt builder — system = copywriter common.md + the reused per-locale layer."""
from tools.copywriter.brief import CopyRequest
from tools.copywriter.prompt_builder import build_system_prompt, build_user_message


def test_system_prompt_en_has_common_and_locale_layer():
    joined = "\n".join(b["text"] for b in build_system_prompt("en"))
    assert "CEL Copywriter" in joined          # the universal common.md
    assert "Locale layer (en)" in joined        # the reused en.md layer is appended
    assert "em dash" in joined.lower()          # the hard-ban contract is present


def test_system_prompt_ko_includes_korean_layer():
    joined = "\n".join(b["text"] for b in build_system_prompt("ko"))
    assert "Locale layer (ko)" in joined
    assert ("한국어" in joined) or ("합니다체" in joined)  # ko.md content reused


def test_user_message_includes_brief_current_copy_and_facts():
    req = CopyRequest(brief="warmer tone", locale="en", must_keep_facts=("DLI #123",))
    msg = build_user_message(req, "Current copy here.", link_candidates=["https://www.englishcollege.com/courses"])
    assert "warmer tone" in msg
    assert "Current copy here." in msg
    assert "DLI #123" in msg
    assert "englishcollege.com/courses" in msg
