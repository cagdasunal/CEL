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
    """The default max_tokens MUST be large enough that the observed-worst-case
    dynamic thinking consumption (~4000 tokens on the home page, despite
    thinking_budget=1500) does NOT clip visible output below ~1000 tokens.

    Tracker-091 M-12.5 (2026-05-19 smoke test): pilot run 26117270255 hit
    MAX_TOKENS with output_tokens=156 because Gemini's thinking_budget is
    advisory — actual thinking can exceed the configured value by 2.5×.
    Default raised from 4000 → 8000 to cover this. If this test fails
    because the default was lowered, run a fresh limit=1 pilot against
    the home page BEFORE accepting the lower value.
    """
    req = batch_runner.BatchRequest(
        custom_id="x",
        system_blocks=[],
        user_message="x",
    )
    # 6500 = observed-worst-case thinking (~4000) + visible target (1000) +
    # safety margin (1500). If a future model behaves better we can lower this.
    assert req.max_tokens >= 6500, (
        f"BatchRequest default max_tokens={req.max_tokens} is below the "
        f"M-12.5 floor of 6500. Smoke test 2026-05-19 (pilot 26117270255) "
        f"showed Gemini consumed ~3844 thinking tokens despite "
        f"THINKING_BUDGET_TOKENS={config.THINKING_BUDGET_TOKENS}, clipping "
        f"visible output to 156 tokens. Re-run a limit=1 pilot before "
        f"lowering this."
    )


# ---- Custom_id round-trip (regression guard) ----


def test_parse_uses_metadata_custom_id_when_present():
    """When metadata.custom_id is set, use it (not the index-fallback)."""
    inline = _make_inline_response(text="hi", finish_reason="STOP", custom_id="real-id")
    result = batch_runner._parse_inline_response(inline, fallback_custom_id="fallback-id")
    assert result.custom_id == "real-id"


def test_retry_transient_retries_then_succeeds(monkeypatch):
    """tracker-092 (2.3): a transient (503) failure is retried with backoff, then succeeds."""
    monkeypatch.setattr(batch_runner.time, "sleep", lambda s: None)  # no real sleep
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("503 Service Unavailable")
        return "ok"

    assert batch_runner._retry_transient(flaky, attempts=3, base_delay=0.0) == "ok"
    assert calls["n"] == 3


def test_retry_transient_reraises_permanent_immediately(monkeypatch):
    """A permanent error (e.g. API_KEY_INVALID) is NOT retried — fail fast."""
    import pytest as _pytest
    monkeypatch.setattr(batch_runner.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def permanent():
        calls["n"] += 1
        raise RuntimeError("400 API_KEY_INVALID")

    with _pytest.raises(RuntimeError, match="API_KEY_INVALID"):
        batch_runner._retry_transient(permanent, attempts=3, base_delay=0.0)
    assert calls["n"] == 1  # no retry burned on a permanent error


def test_retry_transient_gives_up_after_max_attempts(monkeypatch):
    """A persistently transient error re-raises after the attempt cap."""
    import pytest as _pytest
    monkeypatch.setattr(batch_runner.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def always_503():
        calls["n"] += 1
        raise RuntimeError("503 unavailable")

    with _pytest.raises(RuntimeError, match="503"):
        batch_runner._retry_transient(always_503, attempts=3, base_delay=0.0)
    assert calls["n"] == 3


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


# ---- M-12.2: BATCH_DISCOUNT removed; cost-estimate still sane ----


def test_batch_discount_constant_removed():
    """The dead Anthropic-era BATCH_DISCOUNT constant must not reappear.

    If a future migration re-introduces a discount multiplier it should be
    explicit and named for its purpose (e.g. PROMOTION_DISCOUNT_2027). The
    bare `BATCH_DISCOUNT` name was misleading — Gemini's Batch prices are
    pre-discounted at source.
    """
    assert not hasattr(batch_runner, "BATCH_DISCOUNT"), (
        "BATCH_DISCOUNT was removed in M-12.2 — Gemini's Batch tier "
        "carries no extra multiplier. If you need a discount factor, "
        "name it for its purpose."
    )


def test_estimate_batch_cost_zero_requests_returns_zero():
    """Empty input still returns 0.0 (no multiplier silently inflating it)."""
    assert batch_runner.estimate_batch_cost_usd(requests=[]) == 0.0


def test_estimate_batch_cost_scales_linearly_with_request_count():
    """Doubling request count should ~double cost; sanity check the formula
    after removing the * BATCH_DISCOUNT factor."""
    def _req(i: int) -> batch_runner.BatchRequest:
        return batch_runner.BatchRequest(
            custom_id=f"r-{i}", system_blocks=[], user_message="x"
        )
    cost_10 = batch_runner.estimate_batch_cost_usd([_req(i) for i in range(10)])
    cost_20 = batch_runner.estimate_batch_cost_usd([_req(i) for i in range(20)])
    # Not exactly 2× because the first request always "writes cache" (free),
    # but should be in (1.8×, 2.2×) range.
    ratio = cost_20 / cost_10
    assert 1.8 < ratio < 2.2, f"cost ratio 20/10 was {ratio:.2f}, expected near 2.0"


# ---- M-12.3: cache_creation_tokens still 0 via dataclass default ----


def test_parse_success_sets_cache_creation_tokens_to_dataclass_default():
    """After M-12.3 dropped the explicit `cache_creation_tokens=0` arg,
    the BatchResult dataclass default must still apply — Gemini doesn't
    expose this metric, so callers see 0 either way."""
    inline = _make_inline_response(text="ok", finish_reason="STOP")
    result = batch_runner._parse_inline_response(inline, fallback_custom_id="x")
    assert result.cache_creation_tokens == 0


def test_parse_max_tokens_truncation_sets_cache_creation_tokens_to_zero():
    """Same invariant on the truncation path."""
    inline = _make_inline_response(text="clipped", finish_reason="MAX_TOKENS")
    result = batch_runner._parse_inline_response(inline, fallback_custom_id="x")
    assert result.cache_creation_tokens == 0


# ---- M-12.1: _PENDING_BATCHES cleaned up on every wait_for_batch exit path ----


def test_pending_batches_pop_on_terminal_state_failure(monkeypatch):
    """wait_for_batch must drain _PENDING_BATCHES even when it raises
    RuntimeError because the batch ended in JOB_STATE_FAILED.

    Tracker-091 M-12.1: previously the .pop() ran only on the success
    branch, leaving one entry per failed batch alive for the process
    lifetime. The try/finally wrap fixes this.
    """
    import sys
    # Pre-stash an entry as if submit_batch had run.
    batch_runner._PENDING_BATCHES["test-fail-batch"] = [
        batch_runner.BatchRequest(custom_id="r-0", system_blocks=[], user_message="x"),
    ]

    # Fake genai module that returns a FAILED batch on the first .get() call.
    class _FakeBatchesAPI:
        def get(self, name):
            return SimpleNamespace(state=SimpleNamespace(name="JOB_STATE_FAILED"))

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.batches = _FakeBatchesAPI()

    fake_genai = SimpleNamespace(Client=_FakeClient)
    fake_google = SimpleNamespace(genai=fake_genai)
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    handle = batch_runner.BatchHandle(
        batch_id="test-fail-batch",
        request_count=1,
        submitted_at="now",
        dry_run=False,
    )
    try:
        batch_runner.wait_for_batch(handle, poll_interval_sec=0, timeout_sec=5)
    except RuntimeError as e:
        assert "JOB_STATE_FAILED" in str(e)
    else:
        raise AssertionError("expected RuntimeError on FAILED state")

    # The critical assertion — entry was popped despite the RuntimeError.
    assert "test-fail-batch" not in batch_runner._PENDING_BATCHES, (
        "_PENDING_BATCHES leaked an entry on the FAILED-state raise path"
    )


def test_pending_batches_pop_on_timeout(monkeypatch):
    """Same invariant for the TimeoutError path: deadline elapses with
    no terminal state, .pop() must still run via finally."""
    import sys
    batch_runner._PENDING_BATCHES["test-timeout-batch"] = [
        batch_runner.BatchRequest(custom_id="r-0", system_blocks=[], user_message="x"),
    ]

    class _FakeBatchesAPI:
        def get(self, name):
            # Always pending — never returns SUCCEEDED, never terminal.
            return SimpleNamespace(state=SimpleNamespace(name="JOB_STATE_PENDING"))

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.batches = _FakeBatchesAPI()

    fake_genai = SimpleNamespace(Client=_FakeClient)
    fake_google = SimpleNamespace(genai=fake_genai)
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    handle = batch_runner.BatchHandle(
        batch_id="test-timeout-batch",
        request_count=1,
        submitted_at="now",
        dry_run=False,
    )
    try:
        # timeout_sec=0 → deadline is in the past → loop body never executes.
        batch_runner.wait_for_batch(handle, poll_interval_sec=0, timeout_sec=0)
    except TimeoutError:
        pass
    else:
        raise AssertionError("expected TimeoutError when deadline already passed")

    assert "test-timeout-batch" not in batch_runner._PENDING_BATCHES, (
        "_PENDING_BATCHES leaked an entry on the TimeoutError path"
    )


# ---- tracker-096 review: synchronous (instant) generation path ----


def _fake_genai_for_sync(monkeypatch, *, fail_marker: str = "boom"):
    """Inject a fake google-genai whose models.generate_content returns a STOP
    response (or raises on `fail_marker`)."""
    import sys

    class _FakeModels:
        def generate_content(self, model, contents, config):
            if fail_marker and fail_marker in contents:
                raise RuntimeError("400 bad request")  # permanent → isolated failure
            return SimpleNamespace(
                text=f"summary::{contents}",
                candidates=[SimpleNamespace(
                    finish_reason=SimpleNamespace(name="STOP"),
                    content=SimpleNamespace(parts=[SimpleNamespace(text=f"summary::{contents}")]),
                )],
                usage_metadata=SimpleNamespace(
                    prompt_token_count=10, candidates_token_count=20, cached_content_token_count=0,
                ),
            )

    class _FakeClient:
        def __init__(self, *a, **k):
            self.models = _FakeModels()

    fake_genai = SimpleNamespace(Client=_FakeClient)
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")


def test_generate_sync_returns_result_per_request(monkeypatch):
    """generate_sync calls generate_content per request and parses results immediately."""
    _fake_genai_for_sync(monkeypatch)
    reqs = [
        batch_runner.BatchRequest(custom_id="ok-1", system_blocks=[{"type": "text", "text": "sys"}], user_message="hello"),
        batch_runner.BatchRequest(custom_id="bad-1", system_blocks=[], user_message="boom please"),
    ]
    results = batch_runner.generate_sync(reqs)
    assert len(results) == 2
    by_id = {r.custom_id: r for r in results}
    assert by_id["ok-1"].succeeded is True
    assert "summary::hello" in by_id["ok-1"].content
    # Per-request failure is isolated, not raised.
    assert by_id["bad-1"].succeeded is False
    assert "400" in by_id["bad-1"].error


def test_generate_sync_empty_returns_empty():
    assert batch_runner.generate_sync([]) == []


def test_generate_sync_requires_api_key(monkeypatch):
    import pytest as _pytest
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    reqs = [batch_runner.BatchRequest(custom_id="x", system_blocks=[], user_message="hi")]
    with _pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        batch_runner.generate_sync(reqs)
