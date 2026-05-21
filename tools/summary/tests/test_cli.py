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
    assert len(static_targets) == 16  # 12 original + 4 Vancouver (tracker-096)
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


def test_exclude_blog_drops_blog_collection_target(tmp_path: Path):
    """tracker-096: --exclude-blog runs static + courses + housing but skips blog."""
    cli.main(["plan", "--exclude-blog", "--out-dir", str(tmp_path)])
    data = json.loads((tmp_path / "report.json").read_text())
    targets = data["phases"]["generate_english"]["targets"]
    cms_slugs = {t["collection"] for t in targets if t["kind"] == "cms_collection"}
    assert "blog" not in cms_slugs
    assert {"courses", "housing_new"} <= cms_slugs
    # Static pages still included.
    assert any(t["kind"] == "static_page" for t in targets)


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
    # tracker-092 (2.2): MANUAL_REVIEW carries triage metadata.
    assert mr["batch_id"] == "batch-x"
    detail = mr["details"][0]
    assert detail["content_type"] == "landing"
    assert detail["url"] == "https://www.englishcollege.com/learn-english-usa"
    assert "first_attempt_error" in detail


def _fake_live_generate(monkeypatch, content: str, llms_raises: bool = False):
    """Wire mocks for a live generate-english run. Returns the captured-requests dict.

    `content` is the Gemini-returned summary for every request. If `llms_raises`,
    the llms.txt fetch raises (to exercise the degraded flag).
    """
    from tools.summary import page_fetcher, batch_runner, llms_parser

    def fake_fetch(url, timeout=20.0):
        return page_fetcher.PageContent(
            url=url, final_url=url, status=200,
            html="<html><body><h1>Home</h1></body></html>",
            title="Home | CEL", h1="Home", headings=("Home",),
            canonical=url, hreflang_urls=(), existing_summary_html="",
            body_text_excerpt=(
                "CEL is an english language school with campuses in San Diego, "
                "Los Angeles, and Vancouver. Students reach B2 in twelve weeks."
            ),
        )

    monkeypatch.setattr(page_fetcher, "fetch_page", fake_fetch)
    monkeypatch.setattr(cli, "_execute_audit", lambda *a, **kw: {})
    monkeypatch.setattr(cli, "_execute_translate", lambda *a, **kw: {})

    if llms_raises:
        def boom(*a, **kw):
            raise RuntimeError("network down")
        monkeypatch.setattr(llms_parser, "fetch_and_parse", boom)
    else:
        monkeypatch.setattr(
            llms_parser, "fetch_and_parse",
            lambda *a, **kw: llms_parser.LlmsIndex(entries=[]),
        )

    captured: dict = {}

    def fake_submit(requests, **kw):
        captured["requests"] = requests
        return batch_runner.BatchHandle(
            batch_id="b", request_count=len(requests), submitted_at="t", dry_run=False
        )

    def fake_wait(handle, **kw):
        return [
            batch_runner.BatchResult(custom_id=r.custom_id, succeeded=True, content=content)
            for r in captured["requests"]
        ]

    monkeypatch.setattr(batch_runner, "submit_batch", fake_submit)
    monkeypatch.setattr(batch_runner, "wait_for_batch", fake_wait)
    return captured


# A QA-passing home-page summary (primary keyword = M-12.4 override "english language
# school"). tracker-096: the home page is a static landing page, so it now uses the
# 4-part structure (Tagline / Title / Paragraph / Content) and must pass the 4-part
# QA gate — keyword in the Title + first 120 chars of the Paragraph, tagline 2-3 words.
_PASSING_HOME = (
    "## English School Life\n\n"
    "### What to expect from an english language school\n\n"
    "An english language school like CEL serves students across San Diego, "
    "Los Angeles, and Vancouver, with most reaching B2 in twelve weeks.\n\n"
    "#### How long does it take to reach B2\n\n"
    "Most students at CEL reach B2 within twelve weeks, while beginners need "
    "longer depending on weekly hours.\n"
)


def test_generate_english_idempotency_skips_unchanged(tmp_path: Path, monkeypatch):
    """tracker-092 (2.1): a second live run with unchanged source is skipped; --force overrides."""
    from tools.summary import config

    _fake_live_generate(monkeypatch, _PASSING_HOME)
    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", tmp_path / "weglot-out")

    base = ["generate-english", "--no-dry-run", "--page", "https://www.englishcollege.com/", "--out-dir"]
    # Run 1: generates + records idempotency state.
    assert cli.main(base + [str(tmp_path / "run1")]) == 0
    p1 = json.loads((tmp_path / "run1" / "report.json").read_text())["phases"]["generate_english"]
    assert p1.get("idempotency_skipped") == 0
    assert p1["succeeded"] == 1

    # Run 2: same source hash → skipped, nothing submitted.
    assert cli.main(base + [str(tmp_path / "run2")]) == 0
    p2 = json.loads((tmp_path / "run2" / "report.json").read_text())["phases"]["generate_english"]
    assert p2.get("idempotency_skipped") == 1
    assert p2.get("submitted") is False

    # Run 3: --force regenerates despite unchanged source.
    assert cli.main(base + [str(tmp_path / "run3"), "--force"]) == 0
    p3 = json.loads((tmp_path / "run3" / "report.json").read_text())["phases"]["generate_english"]
    assert p3.get("idempotency_skipped") == 0
    assert p3["succeeded"] == 1


def test_generate_english_degraded_flag_on_llms_failure(tmp_path: Path, monkeypatch):
    """tracker-092 (2.4): a failed llms.txt fetch marks the run degraded."""
    from tools.summary import config

    _fake_live_generate(monkeypatch, _PASSING_HOME, llms_raises=True)
    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", tmp_path / "weglot-out")

    assert cli.main([
        "generate-english", "--no-dry-run", "--page",
        "https://www.englishcollege.com/", "--out-dir", str(tmp_path / "run"),
    ]) == 0
    phase = json.loads((tmp_path / "run" / "report.json").read_text())["phases"]["generate_english"]
    assert phase.get("degraded") is True
    assert any("llms.txt fetch failed" in w for w in phase["warnings"])


def test_translate_meta_dry_run_emits_typed_csv_rows(tmp_path: Path, monkeypatch):
    """tracker-092 (3.4): translate-meta extracts page title+description and emits
    Weglot CSV rows typed meta_title / meta_description via the translator."""
    from tools.summary import page_fetcher

    def fake_fetch(url, timeout=20.0):
        return page_fetcher.PageContent(
            url=url, final_url=url, status=200,
            html="<html></html>", title="Learn English at CEL", h1="Home",
            headings=(), canonical=url, hreflang_urls=(), existing_summary_html="",
            body_text_excerpt="x",
            description="Study English at CEL campuses in San Diego and Vancouver.",
        )

    monkeypatch.setattr(page_fetcher, "fetch_page", fake_fetch)

    rc = cli.main([
        "translate-meta", "--dry-run", "--locale", "de", "--page",
        "https://www.englishcollege.com/", "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    phase = json.loads((tmp_path / "report.json").read_text())["phases"]["translate_meta"]
    assert phase["meta_strings"] == 2  # title + description
    assert "de" in phase["per_locale"]
    csv_path = tmp_path / "meta-batches" / "de.csv"
    assert csv_path.exists()
    rows = csv_path.read_text(encoding="utf-8")
    assert "meta_title" in rows
    assert "meta_description" in rows


def test_translate_meta_live_emits_csv_via_engine(tmp_path: Path, monkeypatch):
    """tracker-092 (3.4) review gap-close: the LIVE translate-meta path (engine →
    Weglot CSV in WEGLOT_IMPORTS_DIR) was previously only covered in dry-run."""
    from tools.summary import page_fetcher, batch_runner, config

    def fake_fetch(url, timeout=20.0):
        return page_fetcher.PageContent(
            url=url, final_url=url, status=200, html="<html></html>",
            title="Learn English at CEL", h1="Home", headings=(), canonical=url,
            hreflang_urls=(), existing_summary_html="", body_text_excerpt="x",
            description="Study English at CEL campuses.",
        )

    monkeypatch.setattr(page_fetcher, "fetch_page", fake_fetch)
    weglot = tmp_path / "weglot"
    weglot.mkdir()
    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", weglot)

    captured: dict = {}

    def fake_submit(requests, **kw):
        captured["requests"] = requests
        return batch_runner.BatchHandle(batch_id="b", request_count=len(requests), submitted_at="t", dry_run=False)

    def fake_wait(handle, **kw):
        # Echo a German translation per unit, preserving any required tokens.
        out = []
        for r in captured["requests"]:
            field = "Titel" if "meta_title" in r.custom_id else "Beschreibung"
            out.append(batch_runner.BatchResult(custom_id=r.custom_id, succeeded=True, content=f"[DE {field}]"))
        return out

    monkeypatch.setattr(batch_runner, "submit_batch", fake_submit)
    monkeypatch.setattr(batch_runner, "wait_for_batch", fake_wait)

    rc = cli.main([
        "translate-meta", "--no-dry-run", "--locale", "de", "--page",
        "https://www.englishcollege.com/", "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    phase = json.loads((tmp_path / "report.json").read_text())["phases"]["translate_meta"]
    assert phase["per_locale"]["de"]["dry_run"] is False
    csv_path = weglot / "de.csv"
    assert csv_path.exists()
    rows = csv_path.read_text(encoding="utf-8")
    assert "meta_title" in rows and "meta_description" in rows
    assert "[DE Titel]" in rows  # the engine-translated value reached the CSV


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


# ---- tracker-096: write-back branches by content type ----


def test_write_back_branches_by_content_type(tmp_path, monkeypatch):
    """course/housing CMS items → update_item_summary_parts (4 fields, HTML Content);
    blog → update_item_summary (single block, UNCHANGED); landing → 4-section static file."""
    from tools.summary import batch_runner, webflow_client, config
    from tools.summary.prompt_builder import KeywordPlan, SourceItem

    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", tmp_path / "weglot-out")
    calls = {"single": [], "parts": []}

    def rec_single(self, **kw):
        calls["single"].append(kw)
        return webflow_client.WriteResult(dry_run=False, success=True, method="PATCH", url="x")

    def rec_parts(self, **kw):
        calls["parts"].append(kw)
        return webflow_client.WriteResult(dry_run=False, success=True, method="PATCH", url="x")

    monkeypatch.setattr(webflow_client.WebflowClient, "_get_token", lambda self: "fake")
    monkeypatch.setattr(webflow_client.WebflowClient, "update_item_summary", rec_single)
    monkeypatch.setattr(webflow_client.WebflowClient, "update_item_summary_parts", rec_parts)

    four_part = (
        "## English School Life\n\n### A good section title\n\nA short lead paragraph.\n\n"
        "#### A detail heading\n\nSome body text here.\n"
    )
    single = "## A blog question\n\nA blog answer paragraph.\n"
    van_url = "https://www.englishcollege.com/vancouver"
    sources = [
        (SourceItem(url="https://www.englishcollege.com/courses/x", title="C", body_excerpt="b",
                    locale="en", content_type="course", cms_item_id="c1"), KeywordPlan(primary="x"), "cms"),
        (SourceItem(url="https://www.englishcollege.com/pb/y", title="H", body_excerpt="b",
                    locale="en", content_type="housing", cms_item_id="h1"), KeywordPlan(primary="x"), "cms"),
        (SourceItem(url="https://www.englishcollege.com/post/z", title="B", body_excerpt="b",
                    locale="en", content_type="blog_post", cms_item_id="b1"), KeywordPlan(primary="x"), "cms"),
        (SourceItem(url=van_url, title="V", body_excerpt="b",
                    locale="en", content_type="landing"), KeywordPlan(primary="x"), "static"),
    ]
    results = [
        batch_runner.BatchResult(custom_id="gen-0-c1", succeeded=True, content=four_part),
        batch_runner.BatchResult(custom_id="gen-1-h1", succeeded=True, content=four_part),
        batch_runner.BatchResult(custom_id="gen-2-b1", succeeded=True, content=single),
        batch_runner.BatchResult(custom_id=f"gen-3-{van_url[-50:]}", succeeded=True, content=four_part),
    ]

    class _Args:
        dry_run = False

    out = cli._write_back_summaries(results, sources, _Args(), tmp_path, [])
    # course + housing → 4-part parts (2 calls); blog → single (1 call); landing → static file.
    assert len(calls["parts"]) == 2, calls
    assert len(calls["single"]) == 1, calls
    assert out["cms_writes"] == 3
    assert out["static_writes"] == 1
    assert out["failures"] == 0
    # The 4-part call carries the parsed fields, with the Content rendered to HTML.
    pcall = calls["parts"][0]
    assert pcall["tagline"] == "English School Life"
    assert pcall["title"] == "A good section title"
    assert "<h4>A detail heading</h4>" in pcall["content_html"]
    # Blog keeps the legacy single-field write with the raw Markdown (byte-identical).
    assert calls["single"][0]["summary_html"] == single
    # The static 4-section file was written for the Vancouver landing page.
    assert (tmp_path / "weglot-out" / "static-summaries" / "vancouver.summary.md").exists()


def test_generate_english_sync_uses_generate_sync_not_batch(tmp_path, monkeypatch):
    """tracker-096 review: --sync routes generation through batch_runner.generate_sync
    (instant) and must NOT touch the Batch API (submit_batch / wait_for_batch)."""
    from tools.summary import page_fetcher, batch_runner, llms_parser, config

    def fake_fetch(url, timeout=20.0):
        return page_fetcher.PageContent(
            url=url, final_url=url, status=200,
            html="<html><body><h1>Home</h1></body></html>",
            title="Home | CEL", h1="Home", headings=("Home",), canonical=url,
            hreflang_urls=(), existing_summary_html="",
            body_text_excerpt=(
                "CEL is an english language school with campuses in San Diego, "
                "Los Angeles, and Vancouver. Students reach B2 in twelve weeks."
            ),
        )

    monkeypatch.setattr(page_fetcher, "fetch_page", fake_fetch)
    monkeypatch.setattr(cli, "_execute_audit", lambda *a, **kw: {})
    monkeypatch.setattr(cli, "_execute_translate", lambda *a, **kw: {})
    monkeypatch.setattr(llms_parser, "fetch_and_parse", lambda *a, **kw: llms_parser.LlmsIndex(entries=[]))
    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", tmp_path / "weglot-out")

    captured = {"sync": 0}

    def fake_sync(requests, **kw):
        captured["sync"] += 1
        return [batch_runner.BatchResult(custom_id=r.custom_id, succeeded=True, content=_PASSING_HOME) for r in requests]

    def boom_submit(*a, **kw):
        raise AssertionError("submit_batch must NOT be called in --sync mode")

    monkeypatch.setattr(batch_runner, "generate_sync", fake_sync)
    monkeypatch.setattr(batch_runner, "submit_batch", boom_submit)

    rc = cli.main([
        "generate-english", "--no-dry-run", "--sync", "--page",
        "https://www.englishcollege.com/", "--out-dir", str(tmp_path / "run"),
    ])
    assert rc == 0
    phase = json.loads((tmp_path / "run" / "report.json").read_text())["phases"]["generate_english"]
    assert captured["sync"] == 1, "generate_sync was not called in --sync mode"
    assert phase["succeeded"] == 1
    assert phase["batch_id"].startswith("sync-")


def test_sanitize_summary_strips_em_and_en_dashes():
    """tracker-097 follow-up: the model emits banned em/en-dashes ~1 in 6; they are
    deterministically replaced with the prompt's prescribed comma before QA/write-back."""
    assert "—" not in cli._sanitize_summary("Vancouver — a great city — for students.")
    assert "–" not in cli._sanitize_summary("Most students need 6–12 months.")
    assert cli._sanitize_summary("Vancouver — a great city.") == "Vancouver, a great city."
    assert cli._sanitize_summary("") == ""
    # No banned dash means the text is returned unchanged.
    clean = "Most students reach B2 in twelve weeks."
    assert cli._sanitize_summary(clean) == clean


def test_resolve_item_locale_blog_language_reference():
    """tracker-096: blog posts resolve their `language` Reference to the post's locale
    (native-per-item), so e.g. a French post yields a French summary — not English."""
    from tools.summary import config

    fr_id = "687659b3281d98a9803a86ae"  # French, per BLOG_LANGUAGE_ID_TO_LOCALE
    assert config.BLOG_LANGUAGE_ID_TO_LOCALE[fr_id] == "fr"
    # Blog (native_per_item) → resolves to the post's language.
    assert cli._resolve_item_locale({"language": fr_id}, "native_per_item") == "fr"
    # Unknown language id, or no language field → en fallback.
    assert cli._resolve_item_locale({"language": "unknown-id"}, "native_per_item") == "en"
    assert cli._resolve_item_locale({}, "native_per_item") == "en"
    # Non-native target (courses/housing summarized in English) → forced en.
    assert cli._resolve_item_locale({"language": fr_id}, "en") == "en"
