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
