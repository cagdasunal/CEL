"""The desk's public files carry none of the client's rules (runbook WO-36, build plan §13).

docs/admin/localization/** is served to anyone, and this repository is public. The client's
rule findings -- which rule, its message, the paragraph of their guidelines it cites -- live
only in the desk's private storage, read by a signed-in reviewer (the Worker's desk-read). The
engine checks the manifest before it writes it (the monorepo's findings.leaks); this checks
what the desk generator wrote from it.

It cannot list the messages themselves: that list would publish them here. So it looks for
what every finding carries -- a rule id and a citation of the client's guidelines -- and for
the private record's own fields in the public data.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[3] / "docs" / "admin" / "localization"

# A rule id: a language and a rule family, or the site-wide brand family, then a number.
RULE_ID = re.compile(r"\b(?:[A-Z]{2}-[A-Z]{3,10}|BRAND)-\d{2}\b")
# A citation of the client's translation guidelines ("TG §7.2").
CITE = re.compile(r"\bTG\s*§")
# What only a finding carries (the storage's `findings` table): never a key in the public data.
FINDING_KEYS = frozenset({"findings", "rule", "rules", "message", "cite", "hits", "severity",
                          "subject_sha"})


def _public_files() -> list[Path]:
    files = sorted(p for p in DOCS.rglob("*") if p.is_file() and p.suffix in (".html", ".json"))
    if not files:
        pytest.skip(f"no generated desk at {DOCS}")
    return files


def _readable(path: Path) -> str:
    """The text as a reader gets it: JSON decoded ("§" may be stored as \\u00a7), HTML
    unescaped ("&sect;")."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.dumps(json.loads(text), ensure_ascii=False)
    return html.unescape(text)


def _keys(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _keys(v)}
    return set()


def leaks(paths: list[Path]) -> list[tuple[str, str]]:
    """(file, what) for every rule id, guideline citation or finding field in `paths`."""
    out = []
    for p in paths:
        text = _readable(p)
        out += [(p.name, m) for m in sorted(set(RULE_ID.findall(text)))]
        out += [(p.name, "TG §") for _ in CITE.findall(text)[:1]]
        if p.suffix == ".json":
            out += [(p.name, f"key {k!r}") for k in sorted(_keys(json.loads(p.read_text(encoding="utf-8"))) & FINDING_KEYS)]
    return out


def test_no_public_desk_file_carries_a_client_rule():
    files = _public_files()
    assert any(p.suffix == ".json" for p in files) and any(p.suffix == ".html" for p in files)
    found = leaks(files)
    assert not found, f"the client's rules reached a public desk file: {found}"


# ── The guard can fail (rules/verify-the-verifier.md): each marker, planted, is found ────────

@pytest.mark.parametrize("planted, found", [
    ("<p>XX-SAMPLE-01</p>", "XX-SAMPLE-01"),
    ("<p>BRAND-99</p>", "BRAND-99"),
    ("<p>see TG &sect;0.1</p>", "TG §"),
    ("<p>TG §0</p>", "TG §"),
], ids=["language rule id", "brand rule id", "citation as an entity", "citation"])
def test_the_guard_finds_a_planted_marker_in_a_page(tmp_path, planted, found):
    page = tmp_path / "index.html"
    page.write_text(f"<html><body>{planted}</body></html>", encoding="utf-8")
    assert (page.name, found) in leaks([page])


@pytest.mark.parametrize("record, found", [
    ({"id": "a", "why": "TG §0"}, "TG §"),
    ({"id": "a", "findings": []}, "key 'findings'"),
    ({"id": "a", "sec": [{"cite": "x"}]}, "key 'cite'"),
], ids=["citation stored as \\u00a7", "a findings list", "a nested cite"])
def test_the_guard_finds_a_planted_marker_in_the_data(tmp_path, record, found):
    data = tmp_path / "units.json"
    data.write_text(json.dumps([record]), encoding="utf-8")      # ensure_ascii: § as §
    assert (data.name, found) in leaks([data])


def test_the_guard_passes_what_the_desk_does_say(tmp_path):
    """Its own citations of our documents ("process doc §1", "WO-36") are not the client's."""
    page = tmp_path / "index.html"
    page.write_text("<script>// runbook WO-36, contract §8 S3, process doc §1</script>", encoding="utf-8")
    assert leaks([page]) == []
