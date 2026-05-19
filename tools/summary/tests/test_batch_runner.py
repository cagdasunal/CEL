"""Tests for tools.summary.batch_runner — focused on parse-side defenses.

Tracker-091 M-11 (2026-05-19): pilot batch silently truncated `home.summary.md`
at ~60 words because Gemini's `max_output_tokens` is a CEILING on thinking +
visible tokens combined. With THINKING_BUDGET_TOKENS=1500 and the previous
max_tokens=2000 default, visible output was clipped at ~500 tokens. The
file was then auto-committed to production. These tests guard against a
recurrence:

  1. A response with `finish_reason=MAX_TOKENS` MUST be marked failed,
     regardless of how much text it returned. Truncated copy must never
     write back to production.
  2. A response with `finish_reason=STOP` and text MUST be marked succeeded.
  3. The default `BatchRequest.max_tokens` MUST leave headroom over
     `THINKING_BUDGET_TOKENS` — otherwise the same bug recurs by default.
"""
from __future__ import annotations

from types import SimpleNamespace

from tools.summary import batch_runner, config


# ---- Helpers: fabricate Gemini SDK response shapes ----


def _make_inline_response(
    *,
    text: str,
    finish_reason: str | None,
    custom_id: str = "test-id",
    input_tokens: int = 1000,
    output_tokens: int = 500,
):
    """Build a duck-typed InlinedResponse the parser will accept.

    Mirrors the google-genai 2.4.0 shape: response.candidates[0].finish_reason
    is the standard truncation signal; response.text is the convenience
    accessor; response.usage_metadata.* carries token counts.
    """
    candidate = SimpleNamespace(
        finish_reason=SimpleNamespace(name=finish_reason) if finish_reason else None,
        content=SimpleNamespace(parts=[SimpleNamespace(text=text)]),
    )
    response = SimpleNamespace(
        text=text,
        candidates=[candidate],
        usage_metadata=SimpleNamespace(
            prompt_token_count=input_tokens,
            candidates_token_count=output_tokens,
            cached_content_token_count=0,
        ),
    )
    return SimpleNamespace(
        metadata={"custom_id": custom_id},
        response=response,
        error=None,
    )


# ---- M-11: MAX_TOKENS truncation MUST mark the result failed ----


def test_parse_max_tokens_truncation_marks_failed():
    """A finish_reason=MAX_TOKENS response is a truncated answer.

    Even though `text` is non-empty, the caller (cli.py write-back path)
    must NOT persist this content — the response was clipped mid-thought.
    """
    inline = _make_inline_response(
        text="Over 195 recent student reviews rate",  # mid-sentence cutoff
        finish_reason="MAX_TOKENS",
    )
    result = batch_runner._parse_inline_response(inline, fallback_custom_id="fallback")
    assert result.succeeded is False, (
        "MAX_TOKENS truncation must NOT be reported as a successful response"
    )
    assert "truncated" in result.error.lower()
    assert "max_tokens" in result.error.lower()
    # Content is preserved for forensics (so we can see what the model said before clipping).
    assert result.content == "Over 195 recent student reviews rate"
    # Token counts still populated so cost-accounting remains accurate.
    assert result.input_tokens == 1000
    assert result.output_tokens == 500


def test_parse_clean_finish_marks_succeeded():
    """A finish_reason=STOP response with text is a successful completion."""
    inline = _make_inline_response(
        text="Full clean summary ending with a period.",
        finish_reason="STOP",
    )
    result = batch_runner._parse_inline_response(inline, fallback_custom_id="fallback")
    assert result.succeeded is True
    assert result.error == ""
    assert result.content == "Full clean summary ending with a period."


def test_parse_missing_finish_reason_falls_through_to_text_check():
    """When finish_reason is absent, fall back to the bool(text) heuristic.

    Some response shapes (older SDK builds, fallback edges) may not surface
    finish_reason at all. Treat empty text as failure, non-empty as success.
    """
    inline = _make_inline_response(
        text="Some content was returned.",
        finish_reason=None,
    )
    result = batch_runner._parse_inline_response(inline, fallback_custom_id="fallback")
    assert result.succeeded is True


def test_parse_empty_text_marks_failed():
    """No text + STOP shouldn't claim success — there's nothing to write back."""
    inline = _make_inline_response(text="", finish_reason="STOP")
    result = batch_runner._parse_inline_response(inline, fallback_custom_id="fallback")
    assert result.succeeded is False


# ---- M-11: BatchRequest default must leave headroom over thinking budget ----


def test_batchrequest_default_max_tokens_leaves_visible_headroom():
    """The default max_tokens MUST exceed THINKING_BUDGET_TOKENS by enough to
    fit a 200-word summary (~300 visible output tokens). Anything less and
    we recreate the home.summary.md truncation bug by default.

    Margin: at least 1500 visible tokens after subtracting thinking budget
    (≈2× a 200-word summary, leaves room for tables/lists).
    """
    req = batch_runner.BatchRequest(
        custom_id="x",
        system_blocks=[],
        user_message="x",
    )
    headroom = req.max_tokens - config.THINKING_BUDGET_TOKENS
    assert headroom >= 1500, (
        f"BatchRequest default max_tokens={req.max_tokens} only leaves "
        f"{headroom} visible tokens after THINKING_BUDGET_TOKENS="
        f"{config.THINKING_BUDGET_TOKENS}. Pilot home.summary.md was "
        f"clipped at ~500. Bump max_tokens or shrink THINKING_BUDGET_TOKENS."
    )


# ---- Custom_id round-trip (regression guard) ----


def test_parse_uses_metadata_custom_id_when_present():
    """When metadata.custom_id is set, use it (not the index-fallback)."""
    inline = _make_inline_response(text="hi", finish_reason="STOP", custom_id="real-id")
    result = batch_runner._parse_inline_response(inline, fallback_custom_id="fallback-id")
    assert result.custom_id == "real-id"


def test_parse_falls_back_to_index_when_metadata_missing():
    """When metadata is absent, use the fallback custom_id (index-mapped)."""
    inline = SimpleNamespace(
        metadata=None,
        response=SimpleNamespace(
            text="hi",
            candidates=[SimpleNamespace(
                finish_reason=SimpleNamespace(name="STOP"),
                content=SimpleNamespace(parts=[SimpleNamespace(text="hi")]),
            )],
            usage_metadata=SimpleNamespace(
                prompt_token_count=0,
                candidates_token_count=0,
                cached_content_token_count=0,
            ),
        ),
        error=None,
    )
    result = batch_runner._parse_inline_response(inline, fallback_custom_id="from-index")
    assert result.custom_id == "from-index"
