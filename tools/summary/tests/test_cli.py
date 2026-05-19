"""Tests for tools.summary.cli — public CLI integration via main([...])."""

import json
from pathlib import Path

import pytest

from tools.summary import cli


def test_plan_subcommand_writes_report(tmp_path: Path):
    """`plan --dry-run` writes report.json + report.md and exits 0."""
    rc = cli.main([
        "plan", "--dry-run", "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "report.md").exists()
    data = json.loads((tmp_path / "report.json").read_text())
    assert data["subcommand"] == "plan"
    assert data["dry_run"] is True
    assert "generate_english" in data["phases"]
    assert "audit" in data["phases"]
    assert "translate" in data["phases"]


def test_plan_target_count_includes_static_and_cms(tmp_path: Path):
    cli.main(["plan", "--out-dir", str(tmp_path)])
    data = json.loads((tmp_path / "report.json").read_text())
    targets = data["phases"]["generate_english"]["targets"]
    static_targets = [t for t in targets if t["kind"] == "static_page"]
    cms_targets = [t for t in targets if t["kind"] == "cms_collection"]
    assert len(static_targets) == 12  # all 12 static pages
    assert len(cms_targets) == 3  # blog + courses + housing_new


def test_collection_filter(tmp_path: Path):
    cli.main([
        "plan", "--collection", "courses", "--out-dir", str(tmp_path),
    ])
    data = json.loads((tmp_path / "report.json").read_text())
    targets = data["phases"]["generate_english"]["targets"]
    assert all(t.get("collection") == "courses" or t.get("kind") == "static_page" for t in targets)
    # With --collection, static pages are excluded
    assert not any(t["kind"] == "static_page" for t in targets)


def test_limit_applies(tmp_path: Path):
    cli.main([
        "plan", "--limit", "3", "--out-dir", str(tmp_path),
    ])
    data = json.loads((tmp_path / "report.json").read_text())
    targets = data["phases"]["generate_english"]["targets"]
    assert len(targets) <= 3


def test_generate_english_dry_run_writes_batch_jsonl(tmp_path: Path, monkeypatch):
    """`generate-english --dry-run` runs the orchestrator and writes JSONL artifact."""
    # Patch the live page fetcher to avoid real network.
    from tools.summary import page_fetcher

    def fake_fetch(url, timeout=20.0):
        return page_fetcher.PageContent(
            url=url, final_url=url, status=200,
            html="<html><body><h1>Test</h1><p>Body.</p></body></html>",
            title="Test Page | CEL", h1="Test Page", headings=("Test Page",),
            canonical=url, hreflang_urls=(), existing_summary_html="",
            body_text_excerpt="Test page body text for keyword derivation.",
        )

    monkeypatch.setattr(page_fetcher, "fetch_page", fake_fetch)
    monkeypatch.setattr(cli, "_execute_audit", lambda *a, **kw: {})
    monkeypatch.setattr(cli, "_execute_translate", lambda *a, **kw: {})

    rc = cli.main([
        "generate-english", "--dry-run", "--page",
        "https://www.englishcollege.com/learn-english-usa",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    data = json.loads((tmp_path / "report.json").read_text())
    phase = data["phases"]["generate_english"]
    assert phase["submitted"] is True
    assert phase["dry_run"] is True
    assert phase["batch_id"].startswith("dryrun-")
    assert phase["requests_built"] >= 1
    # JSONL artifact written under out_dir/batches/.
    batch_files = list((tmp_path / "batches").glob("*-batch.jsonl"))
    assert len(batch_files) == 1


def test_help_works():
    """Invoking with --help exits 0 (via SystemExit)."""
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0


# ---- A3b: generate-english writes en-summaries.json (tracker-087 F-2 closure) ----


def test_generate_english_dry_run_writes_en_summaries_manifest(tmp_path: Path, monkeypatch):
    """Dry-run generate-english writes a stub en-summaries.json so translate can read it."""
    from tools.summary import page_fetcher

    def fake_fetch(url, timeout=20.0):
        return page_fetcher.PageContent(
            url=url, final_url=url, status=200,
            html="<html><body><h1>Test</h1></body></html>",
            title="Test | CEL", h1="Test", headings=("Test",),
            canonical=url, hreflang_urls=(), existing_summary_html="",
            body_text_excerpt="Body excerpt for keyword derivation.",
        )

    monkeypatch.setattr(page_fetcher, "fetch_page", fake_fetch)
    monkeypatch.setattr(cli, "_execute_audit", lambda *a, **kw: {})
    monkeypatch.setattr(cli, "_execute_translate", lambda *a, **kw: {})

    rc = cli.main([
        "generate-english", "--dry-run",
        "--page", "https://www.englishcollege.com/learn-english-usa",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    manifest = tmp_path / "en-summaries.json"
    assert manifest.exists(), "en-summaries.json was not written"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert len(data) >= 1


# ---- A3: _execute_translate actually wires the pipeline (tracker-087 F-2 closure) ----


def test_execute_translate_dry_run_uses_manifest_and_builds_batches(tmp_path: Path):
    """Translate phase reads en-summaries.json and writes per-locale batch artifacts."""
    # Pre-stage a manifest with a single EN summary containing a Markdown link.
    manifest = {
        "gen-0-test": {
            "url": "https://www.englishcollege.com/learn-english-usa",
            "markdown": (
                "## How long does it take?\n\n"
                "Most students reach B2 in twelve weeks. See our "
                "[course catalog](https://www.englishcollege.com/courses) for details.\n"
            ),
            "content_type": "landing",
            "locale": "en",
        }
    }
    (tmp_path / "en-summaries.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    rc = cli.main([
        "translate", "--dry-run", "--locale", "de",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    data = json.loads((tmp_path / "report.json").read_text())
    phase = data["phases"]["translate"]
    assert phase["target_locales"] == ["de"]
    de_result = phase["per_locale"]["de"]
    assert de_result.get("dry_run") is True
    assert de_result.get("request_count") == 1
    assert "batch_id" in de_result
    # Artifact dir exists.
    assert (tmp_path / "translate-batches" / "de").exists()


def test_execute_translate_missing_manifest_warns(tmp_path: Path):
    """If en-summaries.json is missing, translate phase warns and returns empty."""
    rc = cli.main([
        "translate", "--dry-run", "--locale", "fr",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    data = json.loads((tmp_path / "report.json").read_text())
    phase = data["phases"]["translate"]
    assert phase["per_locale"] == {}
    assert any("no EN summaries manifest" in w for w in phase["warnings"])


def test_execute_translate_from_run_reads_external_manifest(tmp_path: Path):
    """--from-run reads en-summaries.json from a different directory."""
    prior_run = tmp_path / "prior"
    prior_run.mkdir()
    (prior_run / "en-summaries.json").write_text(
        json.dumps({
            "gen-0-x": {
                "url": "https://www.englishcollege.com/",
                "markdown": "## Welcome\n\nHello, students.\n",
                "content_type": "landing",
                "locale": "en",
            }
        }),
        encoding="utf-8",
    )
    new_run = tmp_path / "new"
    rc = cli.main([
        "translate", "--dry-run", "--locale", "es",
        "--from-run", str(prior_run),
        "--out-dir", str(new_run),
    ])
    assert rc == 0
    data = json.loads((new_run / "report.json").read_text())
    phase = data["phases"]["translate"]
    assert phase["manifest_path"].endswith("prior/en-summaries.json")
    assert phase["per_locale"]["es"].get("request_count") == 1
