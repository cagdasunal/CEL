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
    # tracker-090 C1: keyword_plan persisted in manifest so the Summaries
    # dashboard page can show keyword counts.
    first_entry = next(iter(data.values()))
    assert "keyword_plan" in first_entry, "entry missing keyword_plan field"
    kp = first_entry["keyword_plan"]
    assert isinstance(kp, dict)
    assert "primary" in kp
    assert "secondaries" in kp and isinstance(kp["secondaries"], list)
    assert "entities" in kp and isinstance(kp["entities"], list)


# ---- A3: _execute_translate actually wires the pipeline (tracker-087 F-2 closure) ----


def test_execute_translate_dry_run_uses_manifest_and_builds_batches(tmp_path: Path):
    """Translate phase reads en-summaries.json and writes per-locale batch artifacts.

    Tracker-091 M-10: also verifies the content-type filter — a housing CMS
    entry is included in the manifest but MUST be skipped (housing_new is in
    NO_TRANSLATE_COLLECTIONS). Expected request_count == 1 (the landing
    entry), not 2.
    """
    # Pre-stage a manifest with a landing entry + a housing entry (filter target).
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
        },
        "gen-1-housing": {
            "url": "https://www.englishcollege.com/housing/some-residence",
            "markdown": "## Where to live\n\nKitsilano apartment with kitchenette.\n",
            "content_type": "housing",  # ← filter target (NO_TRANSLATE_COLLECTIONS)
            "locale": "en",
        },
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
    # M-10: housing entry must be filtered out — only the landing entry produces a request.
    assert de_result.get("request_count") == 1, (
        f"expected 1 request (landing only; housing filtered), got {de_result.get('request_count')}"
    )
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


# ---- M-13: link candidate pool builder (tracker-091) ----
#
# _execute_generate_english previously passed only config.STATIC_PAGES (12
# curated landing URLs) as link candidates, so the model could never suggest
# links to CMS items (housing /pb/<slug>, courses, blog). The new helper
# _build_link_candidate_pool merges STATIC_PAGES (prepended) with the source
# locale's llms.txt URLs (minus legacy vc/sd/sm segments), and — when the
# source is housing — also drops /pb/ so housing summaries don't link to other
# housing items (mirrors prompts/housing.md line 28).


def _fake_llms_index():
    """A small LlmsIndex with one housing /pb/, one course, and one legacy /sd/."""
    from tools.summary import llms_parser

    return llms_parser.LlmsIndex(entries=[
        llms_parser.LlmsEntry(
            url="https://www.englishcollege.com/pb/test-residence",
            title="Test Residence", description="", section="Housing", locale="en",
        ),
        llms_parser.LlmsEntry(
            url="https://www.englishcollege.com/courses/general-english",
            title="General English", description="", section="Courses", locale="en",
        ),
        llms_parser.LlmsEntry(
            url="https://www.englishcollege.com/sd/legacy-apartment",
            title="Legacy", description="", section="Legacy", locale="en",
        ),
    ])


def test_link_candidate_pool_nonhousing_includes_housing_items():
    """A landing-page source sees housing /pb/ + course URLs as link candidates,
    and STATIC_PAGES come first (so they survive the 30-URL prompt cap)."""
    from tools.summary import config

    pool = cli._build_link_candidate_pool("landing", _fake_llms_index(), "en")
    assert "https://www.englishcollege.com/pb/test-residence" in pool
    assert "https://www.englishcollege.com/courses/general-english" in pool
    assert pool[0] == config.STATIC_PAGES[0]  # curated entry prepended


def test_link_candidate_pool_housing_excludes_other_housing():
    """A housing source must NOT see other /pb/ items (housing.md rule) but
    still sees non-housing candidates like courses."""
    pool = cli._build_link_candidate_pool("housing", _fake_llms_index(), "en")
    assert "https://www.englishcollege.com/pb/test-residence" not in pool
    assert "https://www.englishcollege.com/courses/general-english" in pool


def test_link_candidate_pool_excludes_legacy_segments():
    """Legacy per-city housing segments (vc/sd/sm) are excluded for any source."""
    for ct in ("landing", "housing", "course"):
        pool = cli._build_link_candidate_pool(ct, _fake_llms_index(), "en")
        assert "https://www.englishcollege.com/sd/legacy-apartment" not in pool, (
            f"legacy /sd/ leaked into pool for content_type={ct}"
        )


def test_generate_english_qa_gate_demotes_critical_fail(tmp_path: Path, monkeypatch):
    """tracker-092 (1.2): a summary that fails a CRITICAL QA check (em-dash) is
    demoted to MANUAL_REVIEW and NOT written back. Exercises the LIVE path with a
    mocked Gemini batch so the gate (which only runs live) is reached."""
    from tools.summary import page_fetcher, batch_runner, llms_parser

    def fake_fetch(url, timeout=20.0):
        return page_fetcher.PageContent(
            url=url, final_url=url, status=200,
            html="<html><body><h1>Learn English USA</h1><p>Body.</p></body></html>",
            title="Learn English in the USA | CEL", h1="Learn English in the USA",
            headings=("Learn English in the USA",), canonical=url, hreflang_urls=(),
            existing_summary_html="", body_text_excerpt="Learn English in the USA at CEL.",
        )

    monkeypatch.setattr(page_fetcher, "fetch_page", fake_fetch)
    monkeypatch.setattr(cli, "_execute_audit", lambda *a, **kw: {})
    monkeypatch.setattr(cli, "_execute_translate", lambda *a, **kw: {})
    monkeypatch.setattr(llms_parser, "fetch_and_parse", lambda *a, **kw: llms_parser.LlmsIndex(entries=[]))

    captured: dict = {}

    def fake_submit(requests, **kw):
        captured["requests"] = requests
        return batch_runner.BatchHandle(
            batch_id="batch-x", request_count=len(requests), submitted_at="t", dry_run=False
        )

    def fake_wait(handle, **kw):
        # Echo each submitted custom_id with content that has an em-dash → CRITICAL fail.
        return [
            batch_runner.BatchResult(
                custom_id=r.custom_id, succeeded=True,
                content="## Learn English in the USA — a guide\n\nStudy at CEL.",
            )
            for r in captured["requests"]
        ]

    monkeypatch.setattr(batch_runner, "submit_batch", fake_submit)
    monkeypatch.setattr(batch_runner, "wait_for_batch", fake_wait)

    rc = cli.main([
        "generate-english", "--no-dry-run", "--page",
        "https://www.englishcollege.com/learn-english-usa",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    data = json.loads((tmp_path / "report.json").read_text())
    phase = data["phases"]["generate_english"]
    # The em-dash summary was demoted: 0 passed, 1 to review, written-back nothing.
    assert phase["qa_gate"]["checked"] == 1
    assert phase["qa_gate"]["passed"] == 0
    assert phase["qa_gate"]["demoted_to_review"] == 1
    assert phase["succeeded"] == 0
    assert phase["manual_review_count"] == 1
    # The demotion reason is recorded in manual-review.json.
    mr = json.loads((tmp_path / "manual-review.json").read_text())
    assert any("QA gate failed" in d["error"] for d in mr["details"])


def test_cms_item_url_per_collection_prefix():
    """tracker-092 (1.5/M-14): each collection's CMS item URL uses the right
    live path prefix. Verified against llms.txt 2026-05-20."""
    assert cli._cms_item_url("housing", "cel-shared-apartment-premium") == \
        "https://www.englishcollege.com/pb/cel-shared-apartment-premium"
    assert cli._cms_item_url("course", "english-academic-skills") == \
        "https://www.englishcollege.com/courses/english-academic-skills"
    assert cli._cms_item_url("blog_post", "3-common-mistakes-english-language") == \
        "https://www.englishcollege.com/post/3-common-mistakes-english-language"
    # Unknown content types fall back to /post/ (prior behavior).
    assert cli._cms_item_url("mystery", "x") == "https://www.englishcollege.com/post/x"


def test_link_candidate_pool_none_index_falls_back_to_static_only():
    """If llms.txt fetch failed (or dry-run), llms_index is None → STATIC_PAGES only."""
    from tools.summary import config

    pool = cli._build_link_candidate_pool("landing", None, "en")
    assert pool == tuple(config.STATIC_PAGES)


def test_link_candidate_pool_deduplicates_overlap():
    """A URL present in BOTH STATIC_PAGES and llms.txt appears only once."""
    from tools.summary import llms_parser

    # /housing is already a STATIC_PAGES entry; add it to llms.txt too.
    idx = llms_parser.LlmsIndex(entries=[
        llms_parser.LlmsEntry(
            url="https://www.englishcollege.com/housing",
            title="Housing hub", description="", section="Housing", locale="en",
        ),
    ])
    pool = cli._build_link_candidate_pool("landing", idx, "en")
    assert pool.count("https://www.englishcollege.com/housing") == 1


def test_generate_english_dry_run_passes_enriched_link_pool(tmp_path, monkeypatch):
    """End-to-end: _execute_generate_english uses _build_link_candidate_pool's
    output as the link inventory passed to the prompt builder. Patch the helper
    to return a known pool (bypasses the dry-run network gate) and assert the
    housing URL lands in the generated batch request's user_message."""
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
    # Inject a known pool that includes a housing /pb/ URL. This bypasses the
    # dry-run network gate (which leaves llms_index None) so the integration
    # path is exercised regardless.
    monkeypatch.setattr(
        cli, "_build_link_candidate_pool",
        lambda *a, **kw: (
            "https://www.englishcollege.com/",
            "https://www.englishcollege.com/pb/test-residence",
        ),
    )

    rc = cli.main([
        "generate-english", "--dry-run", "--page",
        "https://www.englishcollege.com/learn-english-usa",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    batch_files = list((tmp_path / "batches").glob("*-batch.jsonl"))
    assert len(batch_files) == 1
    lines = batch_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    first = json.loads(lines[0])
    user_msg = first["request"]["contents"][0]["parts"][0]["text"]
    assert "https://www.englishcollege.com/pb/test-residence" in user_msg, (
        "housing URL from the link pool did not reach the prompt's user_message"
    )
