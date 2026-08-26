"""Tests for tools/weglot/api_sync.py GITHUB_OUTPUT emission.

Guards the heredoc multiline-safety fix (webflow tracker 138): `error` values can
contain newlines (exception reprs, Weglot/CMS response bodies). A bare
`error=<value>` line corrupts the GITHUB_OUTPUT block and can inject spurious
output variables. content-pipeline.yml consumes `steps.weglot.outputs.error`, so a
corrupt block would feed garbage to `update_log.py --error`.
"""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.weglot import api_sync  # noqa: E402


def _parse_gha_output(text: str) -> dict:
    """Mimic GitHub Actions' GITHUB_OUTPUT parser: `name=value` + `name<<delim` heredoc."""
    out: dict[str, str] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        head = ln.split("<<", 1)[0]
        if "<<" in ln and "=" not in head:
            name, delim = ln.split("<<", 1)
            body = []
            i += 1
            while i < len(lines) and lines[i] != delim:
                body.append(lines[i])
                i += 1
            out[name] = "\n".join(body)
        elif "=" in ln:
            k, v = ln.split("=", 1)
            out[k] = v
        i += 1
    return out


def test_multiline_error_cannot_corrupt_or_inject(tmp_path, monkeypatch):
    """A multiline error that embeds k=v lines must stay contained in the heredoc."""
    out_file = tmp_path / "gha_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    # Real-world nasty: multiline + an injection attempt (count=999 / updated=true).
    nasty = 'post_failed: HTTP 500\ncount=999\nupdated=true\nbody: {"err":"boom"'
    api_sync.emit_github_output(False, 5, ["slug-a", "slug-b"], error=nasty)

    parsed = _parse_gha_output(out_file.read_text())
    assert parsed["count"] == "5"          # NOT 999 — injection contained
    assert parsed["updated"] == "false"    # NOT true — injection contained
    assert parsed["slugs"] == "slug-a,slug-b"
    assert parsed["error"] == nasty        # preserved verbatim, newlines intact


def test_empty_error_parses_clean(tmp_path, monkeypatch):
    """The common path (no error) must still emit a valid, parseable block."""
    out_file = tmp_path / "gha_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    api_sync.emit_github_output(True, 0, [], error="")
    parsed = _parse_gha_output(out_file.read_text())
    assert parsed["updated"] == "true"
    assert parsed["count"] == "0"
    assert parsed["error"] == ""


def test_error_body_resembling_delimiter_round_trips(tmp_path, monkeypatch):
    """A body line that merely RESEMBLES the delimiter prefix must not prematurely
    terminate the heredoc — the real delimiter is a full random hex string, so the
    body round-trips intact. (The exact-collision guard `while delim in error` is
    defensive against a uuid4 hex collision and can't be triggered deterministically.)"""
    out_file = tmp_path / "gha_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    err = "ghadelim_collision\nreal error text"
    api_sync.emit_github_output(False, 1, [], error=err)
    parsed = _parse_gha_output(out_file.read_text())
    assert parsed["error"] == err


# ---------------------------------------------------------------------------
# Transient-4xx retry + loud failure paths.
#
# Content Pipeline run 32902744831 (2026-08-25) died on a single HTTP 406 from
# api.webflow.com. `_http_request` already had retries=4 with exponential
# backoff, but its 4xx branch returned immediately, so the backoff could never
# apply to an edge/WAF block. 98 of the surrounding 100 runs succeeded and the
# identical request returned 200 from a laptop, so the 406 was transient.
# The step also exited 1 having printed nothing but its last progress line.
# ---------------------------------------------------------------------------
import io  # noqa: E402
import urllib.error  # noqa: E402


class _FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, code, body=b'{"msg":"blocked"}'):
        super().__init__("http://x", code, "err", {}, io.BytesIO(body))


def _urlopen_failing_n_times(codes, monkeypatch):
    """Raise HTTPError(codes[i]) per call; succeed once the list is exhausted."""
    calls = {"n": 0}

    class _Resp:
        status = 200
        def read(self): return b'{"ok":true}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        i = calls["n"]; calls["n"] += 1
        if i < len(codes):
            raise _FakeHTTPError(codes[i])
        return _Resp()

    monkeypatch.setattr(api_sync, "urlopen", fake_urlopen)
    monkeypatch.setattr(api_sync.time, "sleep", lambda *_: None)
    return calls


def test_transient_406_is_retried_and_then_succeeds(monkeypatch):
    """A single edge/WAF 406 must not kill the run — this is the exact failure."""
    calls = _urlopen_failing_n_times([406], monkeypatch)
    status, body = api_sync._http_request("http://x")
    assert status == 200, "406 was not retried"
    assert calls["n"] == 2, f"expected 1 retry after the 406, got {calls['n']} calls"


def test_429_and_408_are_retried(monkeypatch):
    calls = _urlopen_failing_n_times([429, 408], monkeypatch)
    status, _ = api_sync._http_request("http://x")
    assert status == 200
    assert calls["n"] == 3


def test_genuine_client_errors_are_not_retried(monkeypatch):
    """401/403/404/422 are real errors — retrying only delays the signal."""
    for code in (400, 401, 403, 404, 422):
        calls = _urlopen_failing_n_times([code, code, code, code, code], monkeypatch)
        status, _ = api_sync._http_request("http://x")
        assert status == code, f"{code} should be returned as-is"
        assert calls["n"] == 1, f"{code} must not be retried (got {calls['n']} calls)"


def test_retryable_4xx_still_fails_loudly_when_it_never_recovers(monkeypatch):
    """Retry must not become an infinite mask: a persistent 406 still raises."""
    _urlopen_failing_n_times([406] * 99, monkeypatch)
    try:
        api_sync._http_request("http://x", retries=2)
    except RuntimeError as e:
        assert "406" in str(e) or "HTTP Error 406" in str(e)
    else:
        raise AssertionError("a persistent 406 must raise after retries are exhausted")


def test_every_error_path_prints_to_stderr(tmp_path, monkeypatch, capsys):
    """emit_github_output is the single funnel for main()'s failure paths."""
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    api_sync.emit_github_output(False, 0, [], error="CMS fetch failed: HTTP 406")
    assert "HTTP 406" in capsys.readouterr().err, "failure path was silent"


def test_success_path_stays_quiet(tmp_path, monkeypatch, capsys):
    """The print is scoped to failures — a clean run must not gain noise."""
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    api_sync.emit_github_output(True, 3, ["a", "b", "c"])
    assert capsys.readouterr().err == ""
