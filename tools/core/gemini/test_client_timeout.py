"""Regression guards for the genai client reliability bounds (tracker 138).

A hung Gemini request must fail in seconds, not ride the 60-min GitHub job cap (the
blog-summary-autopilot incident: it hung for ~6 weeks and never once succeeded, because
the sync `generate_content` path never tripped the SDK's own HttpOptions timeout on
CI's google-genai 2.10.0). Two layers are covered here:

  1. the per-request HttpOptions timeout passed to the SDK client (belt), and
  2. the caller-side HARD wall-clock bound + per-run deadline in `generate_sync`
     (suspenders — SDK-independent, the layer that actually fixes the hang).

The generate_sync tests inject a fake `google.genai` so they run with no real SDK, no
API key, and no network — and they assert the OBSERVABLE behavior (a stuck call is
isolated as a failed result; a run stops at its budget), not merely that a constant was
passed. The original file only did the latter, which is why the hang slipped through.
"""
import sys
import time
import types
from types import SimpleNamespace

import pytest

from tools.core.gemini import client as gc
from tools.core.gemini.client import BatchRequest, BatchResult


# ---- Layer 1: per-request HttpOptions timeout (existing guards) ----


def test_timeout_constant_is_sane():
    # 1–10 minutes, in milliseconds (google-genai HttpOptions.timeout is ms).
    assert 60_000 <= gc._GEMINI_HTTP_TIMEOUT_MS <= 600_000


def test_client_applies_http_timeout_when_types_available():
    """Real-SDK shape (genai.types present) → client gets http_options w/ the timeout."""
    captured = {}
    fake = SimpleNamespace(
        Client=lambda **kw: (captured.update(kw), SimpleNamespace(**kw))[1],
        types=SimpleNamespace(HttpOptions=lambda **kw: SimpleNamespace(**kw)),
    )
    gc._gemini_client(fake, "key")
    assert "http_options" in captured
    assert captured["http_options"].timeout == gc._GEMINI_HTTP_TIMEOUT_MS


def test_client_degrades_when_types_absent():
    """Unit-test mocks inject a SimpleNamespace `genai` with `.Client` but no `.types`.
    The helper must NOT raise (it degrades to http_options=None). This reproduces the
    AttributeError that reddened cel stress-test on 2026-06-01."""
    captured = {}
    fake = SimpleNamespace(Client=lambda **kw: (captured.update(kw), SimpleNamespace(**kw))[1])
    gc._gemini_client(fake, "key")  # must not raise AttributeError
    assert captured.get("http_options") is None


# ---- Layer 2: caller-side hard timeout + per-run deadline (tracker-138 reopened) ----


def test_hard_timeout_constant_is_sane():
    # 30s–10min: long enough for a real Flash/Pro generate, short enough that a stuck
    # call fails well under a 60-min job cap.
    assert 30 <= gc._GEMINI_CALL_HARD_TIMEOUT_SEC <= 600


def test_run_with_hard_timeout_returns_value_fast():
    assert gc._run_with_hard_timeout(lambda: 7, 5) == 7


def test_run_with_hard_timeout_disabled_runs_inline():
    # None / 0 opt out of the bound (still returns the value) — for callers that don't
    # want a wall-clock cap.
    assert gc._run_with_hard_timeout(lambda: "x", None) == "x"
    assert gc._run_with_hard_timeout(lambda: "y", 0) == "y"


def test_run_with_hard_timeout_propagates_fn_error():
    def _boom():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        gc._run_with_hard_timeout(_boom, 5)


def test_run_with_hard_timeout_raises_fast_and_is_transient():
    """A call over budget raises TimeoutError WITHOUT waiting for it to finish, and the
    error is classified transient so _retry_transient / generate_sync handle it."""
    def _slow():
        time.sleep(3.0)
        return "never"

    start = time.monotonic()
    with pytest.raises(TimeoutError) as excinfo:
        gc._run_with_hard_timeout(_slow, 0.2)
    elapsed = time.monotonic() - start
    assert elapsed < 1.5, f"must fail fast, waited {elapsed:.2f}s"
    assert gc._is_transient(excinfo.value)


def _install_fake_genai(monkeypatch, generate_content):
    """Inject a fake `google.genai` + isolate prompt/response plumbing so generate_sync
    runs with no real SDK, key, or network — leaving only the timeout/deadline control
    flow under test."""
    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    fake_genai = SimpleNamespace(
        Client=lambda **kw: fake_client,
        types=SimpleNamespace(HttpOptions=lambda **kw: SimpleNamespace(**kw)),
    )
    google_mod = types.ModuleType("google")
    google_mod.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gc, "_flatten_system_blocks", lambda blocks: "")
    monkeypatch.setattr(gc, "_build_generation_config", lambda *a, **k: {})
    monkeypatch.setattr(
        gc, "_result_from_response",
        lambda resp, cid: BatchResult(custom_id=cid, succeeded=True, content=str(resp)),
    )


def _reqs(n):
    return [BatchRequest(custom_id=f"c{i}", system_blocks=[], user_message="hi") for i in range(n)]


def test_generate_sync_hard_timeout_isolates_stuck_call(monkeypatch):
    """One request that hangs becomes a failed BatchResult; the others still succeed —
    a stuck call can never freeze the whole run."""
    def gen(model, contents, config):
        if contents == "hang":
            time.sleep(3)  # would ride the job cap without the hard timeout
        return SimpleNamespace(ok=True)

    _install_fake_genai(monkeypatch, gen)
    reqs = [
        BatchRequest(custom_id="c0", system_blocks=[], user_message="ok"),
        BatchRequest(custom_id="c1", system_blocks=[], user_message="hang"),
        BatchRequest(custom_id="c2", system_blocks=[], user_message="ok"),
    ]
    out = gc.generate_sync(reqs, call_timeout_sec=0.3)  # tiny bound → fast test
    assert [r.succeeded for r in out] == [True, False, True]
    assert "hard timeout" in (out[1].error or "").lower()


def test_generate_sync_stops_at_run_deadline(monkeypatch):
    """Past the run budget, generate_sync stops starting calls and returns partial —
    deferred requests are simply absent (an idempotent caller retries them next run)."""
    def gen(model, contents, config):
        time.sleep(0.1)
        return SimpleNamespace(ok=True)

    _install_fake_genai(monkeypatch, gen)
    # ~0.1s/call, 0.25s budget → a few calls then stop, well short of 20.
    out = gc.generate_sync(_reqs(20), run_deadline_sec=0.25, call_timeout_sec=5)
    assert 0 < len(out) < 20, f"expected partial results, got {len(out)}"
    assert all(r.succeeded for r in out)


def test_generate_sync_no_deadline_processes_all(monkeypatch):
    """Default (run_deadline_sec=None) processes every request — copywriter/translator,
    which pass no deadline, are unaffected by the new backlog logic."""
    def gen(model, contents, config):
        return SimpleNamespace(ok=True)

    _install_fake_genai(monkeypatch, gen)
    out = gc.generate_sync(_reqs(5))
    assert len(out) == 5 and all(r.succeeded for r in out)
