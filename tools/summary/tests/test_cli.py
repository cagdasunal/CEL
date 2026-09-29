"""Tests for tools.summary.cli — public CLI integration via main([...])."""

import json
from pathlib import Path

import pytest

from tools.summary import cli


@pytest.fixture(autouse=True)
def _offline_landing_fetch(monkeypatch):
    """Stub the live page fetch offline by default, so no test reaches the network (a
    dry-run generate-english still fetches its static pages). generate-english tests set
    their own page_fetcher.fetch_page, which overrides this."""
    import types
    from tools.summary import page_fetcher
    monkeypatch.setattr(
        page_fetcher, "fetch_page",
        lambda *a, **k: types.SimpleNamespace(existing_summary_parts={}),
        raising=False,
    )


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
    assert "translate" not in data["phases"]


def test_translate_and_translate_meta_are_retired(tmp_path: Path):
    """U3-S (2026-09-29): the localization desk is the one translation engine; the summary
    tool's translate / translate-meta commands are gone, and so is their workflow option."""
    for sub in ("translate", "translate-meta"):
        with pytest.raises(SystemExit) as e:
            cli.main([sub, "--dry-run", "--out-dir", str(tmp_path / sub)])
        assert e.value.code == 2, sub  # argparse: invalid choice
    wf = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "summary.yml"
    options = [ln.strip() for ln in wf.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("- ")]
    assert not [o for o in options if o.split("#")[0].strip() in ("- translate", "- translate-meta")]


def test_link_blogs_is_retired(tmp_path: Path):
    """U3-S batch 3 (the Manager's ruling): link-blogs rewrote summaries that already exist,
    against the operator's rule "Never rewrite or translate already we have". It's gone."""
    with pytest.raises(SystemExit) as e:
        cli.main(["link-blogs", "--dry-run", "--out-dir", str(tmp_path / "lb")])
    assert e.value.code == 2  # argparse: invalid choice
    assert not hasattr(cli, "_execute_link_blogs")


def test_plan_target_count_includes_static_and_cms(tmp_path: Path):
    cli.main(["plan", "--out-dir", str(tmp_path)])
    data = json.loads((tmp_path / "report.json").read_text())
    targets = data["phases"]["generate_english"]["targets"]
    static_targets = [t for t in targets if t["kind"] == "static_page"]
    cms_targets = [t for t in targets if t["kind"] == "cms_collection"]
    # The catalogue: planned + held back by a localization round's English freeze
    # (data/localize/freeze.json, monorepo runbook WO-30) -- the same 16 either way.
    held = data["phases"]["generate_english"]["frozen"]
    assert len(static_targets) + len(held) == 16  # 12 original + 4 Vancouver (tracker-096) + /courses (tracker-098 follow-up) - LA page (campus closed 2026-09-22)
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


# ---- M-13: link candidate pool builder (tracker-091) ----
#
# _execute_generate_english previously passed only config.STATIC_PAGES (12
# curated landing URLs) as link candidates, so the model could never suggest
# links to CMS items (housing /housing/<slug>, courses, blog). The new helper
# _build_link_candidate_pool merges STATIC_PAGES (prepended) with the source
# locale's llms.txt URLs (minus legacy vc/sd/sm segments), and — when the
# source is housing — also drops other /housing/ DETAIL pages so housing summaries
# don't link to sibling accommodation pages (mirrors prompts/housing.md).


def _fake_llms_index():
    """A small LlmsIndex: the /housing hub, one housing DETAIL (/housing/<slug>), one
    course, and one legacy /sd/ (per-city housing, always excluded)."""
    from tools.summary import llms_parser

    return llms_parser.LlmsIndex(entries=[
        llms_parser.LlmsEntry(
            url="https://www.englishcollege.com/housing",
            title="Housing", description="", section="Housing", locale="en",
        ),
        llms_parser.LlmsEntry(
            url="https://www.englishcollege.com/housing/test-residence",
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
    """A landing-page source sees housing /housing/ + course URLs as link candidates,
    and STATIC_PAGES come first (so they survive the 30-URL prompt cap)."""
    from tools.summary import config

    pool = cli._build_link_candidate_pool("landing", _fake_llms_index(), "en")
    assert "https://www.englishcollege.com/housing/test-residence" in pool
    assert "https://www.englishcollege.com/courses/general-english" in pool
    assert pool[0] == config.STATIC_PAGES[0]  # curated entry prepended


def test_link_candidate_pool_housing_excludes_other_housing():
    """A housing source must NOT see other /housing/ DETAIL siblings (housing.md), but
    the /housing hub stays linkable and non-housing candidates (courses) are kept."""
    pool = cli._build_link_candidate_pool("housing", _fake_llms_index(), "en")
    assert "https://www.englishcollege.com/housing/test-residence" not in pool  # detail sibling excluded
    assert "https://www.englishcollege.com/housing" in pool  # hub stays an acceptable target
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
    # U3-S batch 5 (U4-1): QA passing none of the run's summaries alerts (exit 3).
    assert rc == cli._NO_WORK_DONE_EXIT_CODE
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


def test_cms_item_url_per_collection_prefix():
    """tracker-092 (1.5/M-14): each collection's CMS item URL uses the right
    live path prefix. housing_new migrated /pb/ → /housing/ (2026-05-24); the old
    /pb/ path now 404s, the slug is unchanged."""
    assert cli._cms_item_url("housing", "cel-shared-apartment-premium") == \
        "https://www.englishcollege.com/housing/cel-shared-apartment-premium"
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


def test_link_candidate_pool_offers_all_housing_first(tmp_path, monkeypatch):
    """2026-05-22: NO cap on /housing candidates — the site has many new accommodation
    pages that need inbound links, so ALL housing candidates are offered, ordered FIRST
    after the curated STATIC_PAGES so they survive the downstream 60-candidate prompt cap.
    Non-housing candidates are unaffected."""
    from tools.summary import llms_parser

    # 6 housing detail candidates + 1 course; the /housing hub also comes via STATIC_PAGES.
    idx = llms_parser.LlmsIndex(entries=[
        llms_parser.LlmsEntry(
            url=f"https://www.englishcollege.com/housing/residence-{i}",
            title=f"Residence {i}", description="", section="Housing", locale="en",
        )
        for i in range(6)
    ] + [
        llms_parser.LlmsEntry(
            url="https://www.englishcollege.com/courses/general-english",
            title="General English", description="", section="Courses", locale="en",
        ),
    ])
    pool = cli._build_link_candidate_pool("landing", idx, "en")
    housing_paths = [u for u in pool if cli._is_housing_path(u)]
    # ALL 6 detail pages + the hub survive — no cap.
    assert len(housing_paths) == 7, housing_paths
    assert "https://www.englishcollege.com/housing" in housing_paths
    for i in range(6):
        assert f"https://www.englishcollege.com/housing/residence-{i}" in housing_paths
    # Housing is ordered ahead of non-housing llms URLs (so it survives the prompt cap):
    # every housing index < the course's index.
    course_idx = pool.index("https://www.englishcollege.com/courses/general-english")
    assert all(pool.index(h) < course_idx for h in housing_paths), pool
    # Non-housing candidates are still present.
    assert "https://www.englishcollege.com/courses/general-english" in pool


def test_link_candidate_pool_omits_en_static_for_non_en_locale():
    """2026-05-22 fix: non-EN summaries must link only same-locale URLs, so the EN
    STATIC_PAGES (unprefixed) are NOT offered to a non-EN locale (they previously caused
    cross-locale demotions). EN still gets them."""
    from tools.summary import config, llms_parser

    idx = llms_parser.LlmsIndex(entries=[
        llms_parser.LlmsEntry(
            url="https://www.englishcollege.com/de/vancouver",
            title="DE Vancouver", description="", section="Campus", locale="de",
        ),
        llms_parser.LlmsEntry(
            url="https://www.englishcollege.com/de/housing/homestay-vancouver",
            title="DE Homestay", description="", section="Housing", locale="de",
        ),
    ])
    pool_de = cli._build_link_candidate_pool("blog_post", idx, "de")
    # No EN STATIC_PAGES leaked into the DE pool.
    assert not any(sp in pool_de for sp in config.STATIC_PAGES), pool_de
    # The DE pool is non-empty and all-DE (de housing is offered, ordered first).
    assert "https://www.englishcollege.com/de/housing/homestay-vancouver" in pool_de
    assert all("/de/" in u for u in pool_de), pool_de
    # EN still gets its curated static pages.
    pool_en = cli._build_link_candidate_pool("blog_post", idx, "en")
    assert "https://www.englishcollege.com/" in pool_en


def test_detect_city():
    assert cli._detect_city("https://www.englishcollege.com/post/living-in-vancouver") == "vancouver"
    assert cli._detect_city("studying in Canada") == "vancouver"  # CEL's only Canadian campus
    assert cli._detect_city("https://www.englishcollege.com/post/why-san-diego-rocks") == "san-diego"
    assert cli._detect_city("a guide to Los Angeles") == "los-angeles"
    assert cli._detect_city("https://www.englishcollege.com/post/grammar-tips") == ""
    assert cli._detect_city("studying in California") == ""  # ambiguous (SD or LA)


def test_link_candidate_pool_city_matched_housing_first():
    """2026-05-23: a Vancouver post is offered Vancouver housing BEFORE San Diego housing,
    so the city's apartments/student-houses surface (not just whichever appears first)."""
    from tools.summary import llms_parser

    idx = llms_parser.LlmsIndex(entries=[
        llms_parser.LlmsEntry(
            url="https://www.englishcollege.com/housing/homestay-san-diego",
            title="", description="", section="Housing", locale="en"),
        llms_parser.LlmsEntry(
            url="https://www.englishcollege.com/housing/student-house-vancouver",
            title="", description="", section="Housing", locale="en"),
        llms_parser.LlmsEntry(
            url="https://www.englishcollege.com/housing/shared-apartment-downtown-vancouver",
            title="", description="", section="Housing", locale="en"),
    ])
    pool = cli._build_link_candidate_pool(
        "blog_post", idx, "en",
        source_url="https://www.englishcollege.com/post/5-surprises-living-vancouver-student",
    )
    details = [u for u in pool if cli._is_housing_path(u) and not u.rstrip("/").endswith("/housing")]
    van_idx = next(i for i, u in enumerate(details) if "vancouver" in u)
    sd_idx = next(i for i, u in enumerate(details) if "san-diego" in u)
    assert van_idx < sd_idx, details


def test_is_housing_path_helper():
    """_is_housing_path matches the /housing hub + details in EVERY locale (localized hub
    slugs de=unterkunft, fr=logements, es=alojamiento), not /pb/ or others."""
    # EN
    assert cli._is_housing_path("https://www.englishcollege.com/housing")
    assert cli._is_housing_path("https://www.englishcollege.com/housing/kitsilano")
    # Localized hubs + details (2026-05-23)
    assert cli._is_housing_path("https://www.englishcollege.com/de/unterkunft")
    assert cli._is_housing_path("https://www.englishcollege.com/de/unterkunft/gastfamilie-san-diego")
    assert cli._is_housing_path("https://www.englishcollege.com/fr/logements")
    assert cli._is_housing_path("https://www.englishcollege.com/es/alojamiento/homestay-san-diego")
    assert cli._is_housing_path("https://www.englishcollege.com/it/housing")  # it keeps "housing"
    # Not housing
    assert not cli._is_housing_path("https://www.englishcollege.com/pb/some-residence")
    assert not cli._is_housing_path("https://www.englishcollege.com/courses/general-english")
    assert not cli._is_housing_path("https://www.englishcollege.com/de/kurse")
    assert not cli._is_housing_path("https://www.englishcollege.com/")


def test_is_housing_detail_path_helper():
    """_is_housing_detail_path distinguishes housing DETAIL pages (/housing/<slug>) from the
    hub (/housing) so a housing summary excludes detail siblings but keeps the hub linkable."""
    # Detail pages (any locale) → True
    assert cli._is_housing_detail_path("https://www.englishcollege.com/housing/homestay-vancouver")
    assert cli._is_housing_detail_path("https://www.englishcollege.com/de/unterkunft/gastfamilie-san-diego")
    assert cli._is_housing_detail_path("https://www.englishcollege.com/es/alojamiento/homestay-san-diego")
    # Hubs → False (the hub stays an acceptable link target)
    assert not cli._is_housing_detail_path("https://www.englishcollege.com/housing")
    assert not cli._is_housing_detail_path("https://www.englishcollege.com/de/unterkunft")
    # Non-housing / dead-legacy → False
    assert not cli._is_housing_detail_path("https://www.englishcollege.com/courses/general-english")
    assert not cli._is_housing_detail_path("https://www.englishcollege.com/pb/old-residence")


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
    # Inject a known pool that includes a housing /housing/ URL. This bypasses the
    # dry-run network gate (which leaves llms_index None) so the integration
    # path is exercised regardless.
    monkeypatch.setattr(
        cli, "_build_link_candidate_pool",
        lambda *a, **kw: (
            "https://www.englishcollege.com/",
            "https://www.englishcollege.com/housing/test-residence",
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
    assert "https://www.englishcollege.com/housing/test-residence" in user_msg, (
        "housing URL from the link pool did not reach the prompt's user_message"
    )


# ---- tracker-096: write-back branches by content type ----


def test_write_back_branches_by_content_type(tmp_path, monkeypatch):
    """tracker-098: course/housing CMS items → update_item_summary_body (Paragraphs +
    Content RichText, both HTML, Tagline/Title preserved); blog → update_item_summary
    (single block, Markdown rendered to HTML); landing → 4-section static file."""
    from tools.summary import batch_runner, webflow_client, config
    from tools.summary.prompt_builder import KeywordPlan, SourceItem

    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", tmp_path / "weglot-out")
    calls = {"single": [], "body": []}

    def rec_single(self, **kw):
        calls["single"].append(kw)
        return webflow_client.WriteResult(dry_run=False, success=True, method="PATCH", url="x")

    def rec_body(self, **kw):
        calls["body"].append(kw)
        return webflow_client.WriteResult(dry_run=False, success=True, method="PATCH", url="x")

    monkeypatch.setattr(webflow_client.WebflowClient, "_get_token", lambda self: "fake")
    monkeypatch.setattr(webflow_client.WebflowClient, "update_item_summary", rec_single)
    monkeypatch.setattr(webflow_client.WebflowClient, "update_item_summary_body", rec_body)

    four_part = (
        "## English School Life\n\n### A good section title\n\n"
        "A short lead paragraph with [a campus link](https://www.englishcollege.com/vancouver).\n\n"
        "A second lead paragraph.\n\n"
        "#### A detail heading\n\nSome body text here.\n"
    )
    single = "## A blog question\n\nA blog answer paragraph with a [sibling post](https://www.englishcollege.com/post/x).\n"
    van_url = "https://www.englishcollege.com/vancouver"
    sources = [
        (SourceItem(url="https://www.englishcollege.com/courses/x", title="C", body_excerpt="b",
                    locale="en", content_type="course", cms_item_id="c1"), KeywordPlan(primary="x"), "cms"),
        (SourceItem(url="https://www.englishcollege.com/housing/y", title="H", body_excerpt="b",
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
    # course + housing → 4-part body writes (2 calls); blog → single (1 call); landing → static file.
    assert len(calls["body"]) == 2, calls
    assert len(calls["single"]) == 1, calls
    assert out["cms_writes"] == 3
    assert out["static_writes"] == 1
    assert out["failures"] == 0
    # The 4-part body write carries ONLY the two RichText bodies as HTML; Tagline/Title
    # are NOT in the call (they are preserved on the item, never overwritten).
    bcall = calls["body"][0]
    assert set(bcall.keys()) == {"collection_id", "item_id", "paragraph_html", "content_html"}
    # Both lead paragraphs are rendered, the inline link survives, Content has the H4.
    assert bcall["paragraph_html"].count("<p>") == 2
    assert '<a href="https://www.englishcollege.com/vancouver">a campus link</a>' in bcall["paragraph_html"]
    assert "<h4>A detail heading</h4>" in bcall["content_html"]
    # Blog single-block write now carries HTML (tracker-098), not raw Markdown.
    blog_html = calls["single"][0]["summary_html"]
    assert "<h2>A blog question</h2>" in blog_html
    assert '<a href="https://www.englishcollege.com/post/x">sibling post</a>' in blog_html
    assert "## " not in blog_html  # no literal Markdown headings leaked
    # The static 4-section file was written for the Vancouver landing page.
    assert (tmp_path / "weglot-out" / "static-summaries" / "vancouver.summary.md").exists()


def test_write_back_publishes_written_items_when_publish_flag_set(tmp_path, monkeypatch):
    """--publish (autopilot): after writing, publish_items is called ONCE PER COLLECTION
    with exactly the item ids written this run; without the flag it is never called."""
    from tools.summary import batch_runner, webflow_client, config
    from tools.summary.prompt_builder import KeywordPlan, SourceItem

    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", tmp_path / "weglot-out")
    monkeypatch.setattr(webflow_client.WebflowClient, "_get_token", lambda self: "fake")
    monkeypatch.setattr(
        webflow_client.WebflowClient, "update_item_summary",
        lambda self, **kw: webflow_client.WriteResult(dry_run=False, success=True, method="PATCH", url="x"),
    )
    monkeypatch.setattr(
        webflow_client.WebflowClient, "update_item_summary_body",
        lambda self, **kw: webflow_client.WriteResult(dry_run=False, success=True, method="PATCH", url="x"),
    )
    pub_calls = []

    def rec_publish(self, collection_id, item_ids):
        pub_calls.append((collection_id, list(item_ids)))
        return webflow_client.WriteResult(
            dry_run=False, success=True, method="POST", url="x",
            response={"publishedItemIds": list(item_ids), "errors": []},
        )

    monkeypatch.setattr(webflow_client.WebflowClient, "publish_items", rec_publish)

    single = "## Q\n\nAn answer paragraph.\n"
    blog_coll = config.COLLECTIONS["blog"]
    course_coll = config.COLLECTIONS["courses"]
    sources = [
        (SourceItem(url="https://www.englishcollege.com/post/a", title="A", body_excerpt="b",
                    locale="de", content_type="blog_post", cms_item_id="b1"), KeywordPlan(primary="x"), "cms"),
        (SourceItem(url="https://www.englishcollege.com/post/b", title="B", body_excerpt="b",
                    locale="fr", content_type="blog_post", cms_item_id="b2"), KeywordPlan(primary="x"), "cms"),
        (SourceItem(url="https://www.englishcollege.com/courses/c", title="C", body_excerpt="b",
                    locale="en", content_type="course", cms_item_id="c1"), KeywordPlan(primary="x"), "cms"),
    ]
    results = [
        batch_runner.BatchResult(custom_id="gen-0-b1", succeeded=True, content=single),
        batch_runner.BatchResult(custom_id="gen-1-b2", succeeded=True, content=single),
        batch_runner.BatchResult(custom_id="gen-2-c1", succeeded=True,
                                 content="## T\n\n### S\n\nLead.\n\nLead two.\n\n#### D\n\nBody.\n"),
    ]

    class _ArgsNoPublish:
        dry_run = False
        publish = False

    out = cli._write_back_summaries(results, sources, _ArgsNoPublish(), tmp_path, [])
    assert pub_calls == [], "publish must NOT run without --publish"
    assert out["publish"] == {}

    class _ArgsPublish:
        dry_run = False
        publish = True

    pub_calls.clear()
    out = cli._write_back_summaries(results, sources, _ArgsPublish(), tmp_path, [])
    # One publish call per collection, each carrying exactly its written item ids.
    by_coll = {c: ids for c, ids in pub_calls}
    assert set(by_coll[blog_coll]) == {"b1", "b2"}
    assert by_coll[course_coll] == ["c1"]
    assert out["publish"]["requested"] == 3
    assert out["publish"]["published"] == 3
    assert out["publish"]["collection_failures"] == 0


def test_generate_english_blog_run_is_bounded_and_checkpoints_incrementally(tmp_path, monkeypatch):
    """tracker-138 WIRING regression (the 6-week daily-timeout incident): drive the WHOLE live blog pipeline
    end-to-end and prove (1) _execute_generate_english threads ONE shared run-deadline into generate_sync
    (bounded, NOT the legacy 2400s per-call budget) and (2) it checkpoints summary-state.json INCREMENTALLY
    as each item is written — so a run that ends early still drains the backlog. A green unit test of each
    piece is necessary but not sufficient; this proves the pieces are actually wired together."""
    import types as _types
    from tools.summary import batch_runner, webflow_client, config, llms_parser
    from tools.summary import qa as _qa

    state_file = tmp_path / "summary-state.json"
    monkeypatch.setattr(config, "SUMMARY_STATE_FILE", state_file)
    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", tmp_path / "weglot-out")
    monkeypatch.setattr(config, "GENERATE_DEADLINE_SEC", 200.0)     # generation budget (< run budget)
    monkeypatch.setattr(config, "RUN_DEADLINE_SEC", 300.0)          # bounded, positive → a real shared deadline
    monkeypatch.setattr(cli, "_start_run_watchdog", lambda *_a, **_k: None)  # isolate: no real timer in the test
    monkeypatch.setattr(llms_parser, "fetch_and_parse", lambda *a, **kw: llms_parser.LlmsIndex(entries=[]))
    monkeypatch.setattr(cli, "_execute_audit", lambda *a, **kw: {})
    # QA is not under test here — force pass so all three items reach write-back.
    monkeypatch.setattr(_qa, "qa_checks", lambda *a, **kw: _types.SimpleNamespace(passed=True, score=95.0, notes=[]))
    monkeypatch.setattr(_qa, "boilerplate_pairs", lambda *a, **kw: [])

    blog_cid = config.COLLECTIONS["blog"]
    items = [
        webflow_client.CmsItem(
            id=f"b{i}", collection_id=blog_cid,
            field_data={"name": f"Post {i}", "slug": f"post-{i}", "post-body": "Some blog body text about studying."},
            is_archived=False, is_draft=False,
        )
        for i in range(3)
    ]
    monkeypatch.setattr(webflow_client.WebflowClient, "_get_token", lambda self: "fake")
    monkeypatch.setattr(webflow_client.WebflowClient, "list_items", lambda self, cid, **kw: iter(items))
    monkeypatch.setattr(
        webflow_client.WebflowClient, "update_item_summary",
        lambda self, **kw: webflow_client.WriteResult(dry_run=False, success=True, method="PATCH", url="x"),
    )
    monkeypatch.setattr(
        webflow_client.WebflowClient, "publish_items",
        lambda self, collection_id, item_ids: webflow_client.WriteResult(
            dry_run=False, success=True, method="POST", url="x",
            response={"publishedItemIds": item_ids},
        ),
    )

    captured_deadline: list = []

    def fake_sync(requests, run_deadline_sec=None, **kw):
        captured_deadline.append(run_deadline_sec)
        return [batch_runner.BatchResult(custom_id=r.custom_id, succeeded=True,
                                         content="## A blog question\n\nA clear answer paragraph.\n")
                for r in requests]

    monkeypatch.setattr(batch_runner, "generate_sync", fake_sync)

    rc = cli.main([
        "generate-english", "--collection", "blog", "--no-dry-run", "--sync",
        "--confirm-cost", "--publish", "--out-dir", str(tmp_path / "run"),
    ])

    assert rc == 0
    # (1) generate_sync got a BOUNDED, shared generation deadline — derived from GENERATE_DEADLINE_SEC (which
    #     is reserved to fire EARLIER than the run deadline so write-back never starves), never the legacy
    #     per-call 2400s. (This is the wiring the tracker-138 "fix" silently lacked.)
    assert captured_deadline and captured_deadline[0] is not None
    assert 0 < captured_deadline[0] <= 200.0, captured_deadline
    assert captured_deadline[0] != config.SYNC_RUN_DEADLINE_SEC
    # (2) state was checkpointed INCREMENTALLY through the real run — all three written items are persisted,
    #     so a SIGKILL/watchdog exit after this point would still let the backlog drain next run.
    assert state_file.exists(), "summary-state.json was never written — the backlog can never drain"
    persisted = json.loads(state_file.read_text())
    assert set(persisted) == {"b0", "b1", "b2"}, persisted
    phase = json.loads((tmp_path / "run" / "report.json").read_text())["phases"]["generate_english"]
    assert phase["write_log"]["cms_writes"] == 3
    assert phase["write_log"]["deferred"] == 0


def test_generate_english_retry_pass_is_also_bounded_by_the_shared_deadline(tmp_path, monkeypatch):
    """tracker-138 ROOT-CAUSE regression: the failure that ran for 6 weeks was a RETRY pass that got a FRESH
    budget. Drive a full run where the FIRST generate pass fails an item (triggering the retry at cli.py:919)
    and assert the retry pass ALSO receives a bounded, shared generation deadline — not None, not the legacy
    2400s, and no larger than the first pass. A green suite that never exercises the retry pass is exactly why
    the original 'fix' silently didn't work."""
    import types as _types
    from tools.summary import batch_runner, webflow_client, config, llms_parser
    from tools.summary import qa as _qa

    monkeypatch.setattr(config, "SUMMARY_STATE_FILE", tmp_path / "summary-state.json")
    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", tmp_path / "weglot-out")
    monkeypatch.setattr(config, "GENERATE_DEADLINE_SEC", 200.0)
    monkeypatch.setattr(config, "RUN_DEADLINE_SEC", 300.0)
    monkeypatch.setattr(cli, "_start_run_watchdog", lambda *_a, **_k: None)
    monkeypatch.setattr(llms_parser, "fetch_and_parse", lambda *a, **kw: llms_parser.LlmsIndex(entries=[]))
    monkeypatch.setattr(cli, "_execute_audit", lambda *a, **kw: {})
    monkeypatch.setattr(_qa, "qa_checks", lambda *a, **kw: _types.SimpleNamespace(passed=True, score=95.0, notes=[]))
    monkeypatch.setattr(_qa, "boilerplate_pairs", lambda *a, **kw: [])

    blog_cid = config.COLLECTIONS["blog"]
    items = [webflow_client.CmsItem(
        id="b0", collection_id=blog_cid,
        field_data={"name": "Post 0", "slug": "post-0", "post-body": "Some blog body text about studying."},
        is_archived=False, is_draft=False)]
    monkeypatch.setattr(webflow_client.WebflowClient, "_get_token", lambda self: "fake")
    monkeypatch.setattr(webflow_client.WebflowClient, "list_items", lambda self, cid, **kw: iter(items))
    monkeypatch.setattr(
        webflow_client.WebflowClient, "update_item_summary",
        lambda self, **kw: webflow_client.WriteResult(dry_run=False, success=True, method="PATCH", url="x"))
    monkeypatch.setattr(
        webflow_client.WebflowClient, "publish_items",
        lambda self, collection_id, item_ids: webflow_client.WriteResult(
            dry_run=False, success=True, method="POST", url="x", response={"publishedItemIds": item_ids}))

    calls: list = []

    def fake_sync(requests, run_deadline_sec=None, **kw):
        calls.append(run_deadline_sec)
        succeeded = len(calls) > 1                      # first pass FAILS the item → forces the retry pass
        return [batch_runner.BatchResult(
            custom_id=r.custom_id, succeeded=succeeded,
            content=("## A blog question\n\nA clear answer.\n" if succeeded else ""),
            error=(None if succeeded else "transient boom")) for r in requests]

    monkeypatch.setattr(batch_runner, "generate_sync", fake_sync)

    rc = cli.main([
        "generate-english", "--collection", "blog", "--no-dry-run", "--sync",
        "--confirm-cost", "--publish", "--out-dir", str(tmp_path / "run"),
    ])

    assert rc == 0
    assert len(calls) == 2, f"retry pass did not run (calls={calls})"
    assert calls[0] is not None and calls[1] is not None
    # The RETRY pass got a bounded, shared generation budget — never None, never the legacy 2400s per-call
    # budget, and no larger than the first pass (they share one shrinking deadline).
    assert 0 < calls[1] <= 200.0, calls
    assert calls[1] != config.SYNC_RUN_DEADLINE_SEC
    assert calls[1] <= calls[0]


def test_submit_and_wait_shares_one_run_deadline_across_passes(monkeypatch):
    """tracker-138 ROOT CAUSE: the retry pass used to get a FRESH per-call budget, so the main pass AND
    the retry pass could each run ~40 min and ride the run past the 60-min GitHub Actions cap (SIGKILL
    before any checkpoint → the blog autopilot timed out every day for 6+ weeks). Both passes must now be
    bounded by the REMAINING budget to ONE shared absolute deadline, so the retry gets only what's left."""
    import argparse
    from tools.summary import batch_runner

    captured: list = []

    def fake_gs(requests, run_deadline_sec=None, **kw):
        captured.append(run_deadline_sec)
        return [batch_runner.BatchResult(custom_id=r.custom_id, succeeded=True, content="x") for r in requests]

    monkeypatch.setattr(batch_runner, "generate_sync", fake_gs)
    clock = [1000.0]
    monkeypatch.setattr(cli.time, "monotonic", lambda: clock[0])

    args = argparse.Namespace(sync=True)
    reqs = [batch_runner.BatchRequest(custom_id="a", system_blocks=[], user_message="m")]
    deadline = clock[0] + 100.0                                # 100s whole-run budget
    cli._submit_and_wait(reqs, args, run_deadline=deadline)     # main pass → remaining 100
    clock[0] += 30.0                                            # 30s elapses before the retry
    cli._submit_and_wait(reqs, args, run_deadline=deadline)     # retry pass → remaining 70

    assert captured == [100.0, 70.0]
    assert captured[1] < captured[0], "retry must share the run budget, not get a fresh one"


def test_write_back_stops_at_run_deadline_and_checkpoints_each_write(tmp_path, monkeypatch):
    """tracker-138: write-back must (a) STOP starting new writes past the shared run deadline (returning the
    rest as `deferred`, so the run stays under the cap) and (b) fire on_written per SUCCESSFUL write so the
    caller checkpoints idempotency state incrementally — the two properties that make a partial run DRAIN
    instead of losing everything when the process ends early."""
    from tools.summary import batch_runner, webflow_client, config
    from tools.summary.prompt_builder import KeywordPlan, SourceItem

    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", tmp_path / "weglot-out")
    monkeypatch.setattr(webflow_client.WebflowClient, "_get_token", lambda self: "fake")
    monkeypatch.setattr(
        webflow_client.WebflowClient, "update_item_summary",
        lambda self, **kw: webflow_client.WriteResult(dry_run=False, success=True, method="PATCH", url="x"),
    )
    sources = [
        (SourceItem(url=f"https://www.englishcollege.com/post/{i}", title="B", body_excerpt="b",
                    locale="en", content_type="blog_post", cms_item_id=f"b{i}"), KeywordPlan(primary="x"), "cms")
        for i in range(3)
    ]
    results = [
        batch_runner.BatchResult(custom_id=f"gen-{i}-b{i}", succeeded=True, content="## Q\n\nAn answer.\n")
        for i in range(3)
    ]

    class _Args:
        dry_run = False

    clock = [5000.0]
    monkeypatch.setattr(cli.time, "monotonic", lambda: clock[0])

    # (a) deadline already in the past → nothing written, ALL deferred.
    written: list = []
    log = cli._write_back_summaries(
        results, sources, _Args(), tmp_path, [],
        run_deadline=clock[0] - 1.0, on_written=lambda it: written.append(it.cms_item_id),
    )
    assert log["cms_writes"] == 0 and log["deferred"] == 3 and written == []

    # (b) generous deadline → all written AND on_written fires exactly once per item, in order.
    written.clear()
    log2 = cli._write_back_summaries(
        results, sources, _Args(), tmp_path, [],
        run_deadline=clock[0] + 10_000.0, on_written=lambda it: written.append(it.cms_item_id),
    )
    assert log2["cms_writes"] == 3 and log2["deferred"] == 0
    assert written == ["b0", "b1", "b2"]


def test_run_watchdog_force_exits_nonzero_to_alert(monkeypatch):
    """tracker-138 backstop: the normal bounded run stops COOPERATIVELY at the generate/run deadlines and
    exits 0 on its own, so the watchdog only ever fires on a genuine HANG the cooperative stops did not
    catch. That is abnormal, so it must exit NON-ZERO — that is what makes the workflow's 'Notify on failure'
    step fire (an earlier cut exited 0 and re-created the exact silent-hang the alert exists to prevent).
    Durability is independent of the exit code (incremental checkpoint + always()-commit), so exiting
    non-zero drains AND alerts. Verifies it fires with a non-zero code (os._exit is stubbed so the test
    process survives)."""
    import threading as _threading

    fired = _threading.Event()
    codes: list = []
    monkeypatch.setattr(cli.os, "_exit", lambda code: (codes.append(code), fired.set()) and None)

    timer = cli._start_run_watchdog(0.05)
    assert timer.daemon is True, "watchdog must be a daemon so it never blocks a normal exit"
    assert fired.wait(2.0), "watchdog did not fire within its hard budget"
    assert codes == [cli._WATCHDOG_EXIT_CODE], codes
    assert cli._WATCHDOG_EXIT_CODE != 0, "watchdog must exit NON-ZERO so the failure alert fires"


def test_run_deadline_ordering_reserves_writeback_and_stays_under_the_job_cap():
    """tracker-138 STARVATION + cap guard: generation must stop before write-back's deadline (else a big
    backlog eats the whole budget and starves write-back → nothing written or checkpointed → never drains),
    write-back must stop before the hard watchdog, and the watchdog must fire before the 60-min GitHub
    Actions job cap SIGKILLs the process. This ordering is the whole fix; lock it so it can't silently drift."""
    from tools.summary import config
    assert config.GENERATE_DEADLINE_SEC < config.RUN_DEADLINE_SEC, "generation must reserve write-back headroom"
    assert config.RUN_DEADLINE_SEC < config.RUN_WATCHDOG_HARD_SEC, "write-back must finish before the hard backstop"
    assert config.RUN_WATCHDOG_HARD_SEC < 60 * 60, "the watchdog must exit cleanly BEFORE the 60-min job cap"


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


def test_sanitize_summary_normalizes_html_to_markdown():
    """tracker-098: the model (esp. Flash) sometimes emits raw inline HTML (<a>/<strong>/
    <em>) despite the Markdown-only rule. _sanitize_summary normalizes it back to Markdown
    BEFORE QA + write-back, so QA's Markdown link checks see the links and the
    Markdown->HTML converter emits real <a> rather than escaped &lt;a&gt; (the live blog bug)."""
    out = cli._sanitize_summary('See <a href="https://www.englishcollege.com/fr/cours">nos cours</a> today.')
    assert out == "See [nos cours](https://www.englishcollege.com/fr/cours) today."
    # Single-quoted href + extra attributes around href are handled.
    assert cli._sanitize_summary("<a href='https://x.com/p'>p</a>") == "[p](https://x.com/p)"
    assert cli._sanitize_summary('<a class="c" href="https://x.com/p" target="_blank">p</a>') == "[p](https://x.com/p)"
    # strong/b -> **, em/i -> *.
    assert cli._sanitize_summary("<strong>bold</strong> and <em>it</em>") == "**bold** and *it*"
    # Already-Markdown is left untouched (no double-conversion).
    md = "See [our courses](https://www.englishcollege.com/courses)."
    assert cli._sanitize_summary(md) == md


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


def test_link_candidate_pool_drops_retired_campus_urls():
    """2026-09-22: CEL no longer operates in Los Angeles. No LA URL — any locale, the LA
    homestay, LA blog posts — may be offered as a link candidate, for any source."""
    from tools.summary import llms_parser

    la = [
        "https://www.englishcollege.com/los-angeles-ca/language-courses",
        "https://www.englishcollege.com/housing/homestay-los-angeles",
        "https://www.englishcollege.com/post/things-to-do-in-los-angeles",
    ]
    keep = "https://www.englishcollege.com/housing/homestay-san-diego"
    idx = llms_parser.LlmsIndex(entries=[
        llms_parser.LlmsEntry(url=u, title="x", description="", section="S", locale="en")
        for u in la + [keep]
    ])
    for ct in ("landing", "housing", "course", "blog_post"):
        pool = cli._build_link_candidate_pool(ct, idx, "en")
        assert not [u for u in pool if u in la], f"retired LA URL offered for {ct}: {pool}"
    assert keep in cli._build_link_candidate_pool("landing", idx, "en")


# ---- U3-S (2026-09-29): a blog post that already has a summary is never regenerated ----
# The operator: "we have already translations and summaries, don't do that. But there might be
# some blog posts which misses summaries etc. ... Never rewrite or translate already we have".
# The blog run fills ONLY an empty summary field. Nothing regenerates a post that has one: not a
# changed hash, prompt version or model, and not --force.

def _live_blog_run(tmp_path, monkeypatch, field_data_by_id, *extra, fail_first_pass=False,
                   fail_all=False, fail_ids=(), write_ok=True, qa_pass=True, list_raises=False,
                   out_name="run"):
    """Drive the live blog pipeline offline. Returns (rc, seen, phase): what reached Gemini
    (custom ids, and each request's model + thinking level), every Webflow field write, and
    every publish. fail_first_pass fails every first-pass request, so the retry pass runs;
    fail_all fails every request, retries included, and fail_ids only those items' requests;
    write_ok=False fails every Webflow write; qa_pass=False makes QA reject every summary
    (seen["qa_sources"] holds the source_text QA was given); list_raises makes the CMS read
    fail. Calls sharing a tmp_path share summary-state.json (use a new out_name per run)."""
    import types as _types
    from tools.summary import batch_runner, webflow_client, config, llms_parser
    from tools.summary import qa as _qa

    monkeypatch.setattr(config, "SUMMARY_STATE_FILE", tmp_path / "summary-state.json")
    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", tmp_path / "weglot-out")
    monkeypatch.setattr(cli, "_start_run_watchdog", lambda *_a, **_k: None)
    monkeypatch.setattr(llms_parser, "fetch_and_parse", lambda *a, **kw: llms_parser.LlmsIndex(entries=[]))
    monkeypatch.setattr(cli, "_execute_audit", lambda *a, **kw: {})
    def fake_qa(*a, **kw):
        seen["qa_sources"].append(kw.get("source_text", ""))
        return _types.SimpleNamespace(passed=qa_pass, score=95.0 if qa_pass else 40.0,
                                      notes=[] if qa_pass else ["fact_grounding_numbers: numbers not in the post"])

    monkeypatch.setattr(_qa, "qa_checks", fake_qa)
    monkeypatch.setattr(_qa, "boilerplate_pairs", lambda *a, **kw: [])

    blog_cid = config.COLLECTIONS["blog"]
    items = [
        webflow_client.CmsItem(
            id=iid, collection_id=blog_cid,
            field_data={"name": f"Post {iid}", "slug": f"post-{iid}",
                        "post-body": "Some blog body text about studying.", **fd},
            is_archived=False, is_draft=False,
        )
        for iid, fd in field_data_by_id.items()
    ]
    seen: dict = {"requests": [], "sent": [], "messages": [], "patched": [], "published": [], "qa_sources": []}

    def fake_sync(requests, run_deadline_sec=None, **kw):
        seen["requests"].extend(r.custom_id for r in requests)
        seen["sent"].extend((r.custom_id, r.model, r.thinking_level) for r in requests)
        seen["messages"].extend(r.user_message for r in requests)
        first_pass_fails = fail_first_pass and not requests[0].custom_id.startswith("retry-")

        def ok(r):
            return not (fail_all or first_pass_fails or r.custom_id.endswith(tuple(f"-{i}" for i in fail_ids)))
        return [batch_runner.BatchResult(custom_id=r.custom_id, succeeded=ok(r),
                                         content="## A blog question\n\nA clear answer paragraph.\n" if ok(r) else "",
                                         error=None if ok(r) else "boom")
                for r in requests]

    def no_batch(*a, **kw):
        raise AssertionError("the blog run must not use the Batch API here")

    def fake_patch(self, collection_id, item_id, field_data):
        seen["patched"].append(item_id)
        return webflow_client.WriteResult(dry_run=False, success=write_ok, method="PATCH", url="x",
                                          error=None if write_ok else "HTTP 500")

    def fake_publish(self, collection_id, item_ids):
        seen["published"].extend(item_ids)
        return webflow_client.WriteResult(dry_run=False, success=True, method="POST", url="x",
                                          response={"publishedItemIds": item_ids})

    monkeypatch.setattr(batch_runner, "generate_sync", fake_sync)
    monkeypatch.setattr(batch_runner, "submit_batch", no_batch)
    monkeypatch.setattr(webflow_client.WebflowClient, "_get_token", lambda self: "fake")
    def fake_list(self, cid, **kw):
        if list_raises:
            raise RuntimeError("HTTP 401 Unauthorized")
        return iter(items)

    monkeypatch.setattr(webflow_client.WebflowClient, "list_items", fake_list)
    monkeypatch.setattr(webflow_client.WebflowClient, "patch_fields", fake_patch)
    monkeypatch.setattr(webflow_client.WebflowClient, "publish_items", fake_publish)

    out = tmp_path / out_name
    rc = cli.main([
        "generate-english", "--collection", "blog", "--no-dry-run", "--sync",
        "--confirm-cost", "--publish", "--out-dir", str(out), *extra,
    ])
    phase = json.loads((out / "report.json").read_text())["phases"]["generate_english"]
    return rc, seen, phase


def test_blog_post_with_a_summary_is_never_regenerated_even_with_force(tmp_path, monkeypatch):
    """Only the posts whose summary field is empty reach Gemini, Webflow and publish. --force
    and a missing or stale hash (no state file here, so every hash "changed") change nothing."""
    rc, seen, phase = _live_blog_run(tmp_path, monkeypatch, {
        "has": {"summary": "<p>Ein vorhandener Text mit <a href='/de'>Link</a>.</p>"},
        "empty": {"summary": ""},
        "missing": {},
        "tags-only": {"summary": "<p> </p>"},
        "plain": {"summary": "An existing summary."},
    }, "--force")

    assert rc == 0
    assert sorted(seen["patched"]) == ["empty", "missing", "tags-only"], seen
    assert sorted(seen["published"]) == ["empty", "missing", "tags-only"], seen
    assert all(not cid.endswith(("-has", "-plain")) for cid in seen["requests"]), seen["requests"]
    assert len(seen["requests"]) == 3, seen["requests"]
    assert phase["has_summary_skipped"] == 2


def test_blog_run_where_every_post_has_a_summary_sends_and_writes_nothing(tmp_path, monkeypatch):
    """A post with a summary: no request, no write, no publish — even with --force."""
    rc, seen, phase = _live_blog_run(tmp_path, monkeypatch, {
        "a": {"summary": "<p>Un résumé existant.</p>"},
        "b": {"summary": "<p>Un riassunto esistente.</p>"},
    }, "--force")

    assert rc == 0
    assert seen == {"requests": [], "sent": [], "messages": [], "patched": [], "published": [], "qa_sources": []}
    assert phase["requests_built"] == 0
    assert phase["has_summary_skipped"] == 2


def test_blog_autopilot_workflow_cannot_force_a_regeneration():
    """The daily workflow offers no way to pass --force (the flag has no effect on blog in the
    code either; this keeps the dispatch form from suggesting otherwise)."""
    wf = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "blog-summary-autopilot.yml"
    code = [ln for ln in wf.read_text(encoding="utf-8").splitlines() if not ln.strip().startswith("#")]
    # ARGS is the summary command's argv (`gh label create --force` elsewhere is not ours).
    assert not [ln for ln in code if "ARGS" in ln and "--force" in ln], "the autopilot can pass --force"
    assert not [ln for ln in code if "inputs.force" in ln or ln.strip() == "force:"], \
        "the autopilot still offers a force input"


def test_blog_requests_go_to_the_engines_model_at_thinking_high_retry_included(tmp_path, monkeypatch):
    """U3-S step 3: every blog request, the retry pass's too, names 3.1 Pro and thinking high."""
    rc, seen, _phase = _live_blog_run(tmp_path, monkeypatch, {"e1": {}, "e2": {"summary": ""}},
                                      fail_first_pass=True)
    assert rc == 0
    assert [cid for cid, _m, _t in seen["sent"]] == ["gen-0-e1", "gen-1-e2", "retry-gen-0-e1", "retry-gen-1-e2"]
    assert {(m, t) for _cid, m, t in seen["sent"]} == {("gemini-3.1-pro-preview", "high")}


# ---- U3-S step 5: a run whose every request failed exits non-zero ----
# The blog autopilot stayed green for weeks while every Gemini request failed (402/429 no
# credit, then 404 on a gone model). Such a run must fail the workflow step, so its "Notify on
# failure" alert fires.

def test_every_request_failing_exits_non_zero(tmp_path, monkeypatch, capsys):
    rc, seen, phase = _live_blog_run(tmp_path, monkeypatch, {"e1": {}, "e2": {}}, fail_all=True)
    assert rc == cli._NO_WORK_DONE_EXIT_CODE != 0
    assert phase["succeeded"] == 0 and seen["patched"] == []
    assert "every request failed" in capsys.readouterr().err


def test_every_write_failing_exits_non_zero(tmp_path, monkeypatch, capsys):
    rc, seen, phase = _live_blog_run(tmp_path, monkeypatch, {"e1": {}}, write_ok=False)
    assert rc == cli._NO_WORK_DONE_EXIT_CODE
    assert phase["succeeded"] == 1 and seen["published"] == []
    assert "every write failed" in capsys.readouterr().err


def test_a_cost_cap_stop_exits_non_zero(tmp_path, monkeypatch, capsys):
    """The Manager's ruling (U3-S batch 3): the hard cost cap stopping the run alerts too."""
    from tools.summary import config
    monkeypatch.setattr(config, "MAX_BATCH_COST_USD", 0.000001)
    rc, seen, phase = _live_blog_run(tmp_path, monkeypatch, {"e1": {}})
    assert rc == cli._NO_WORK_DONE_EXIT_CODE
    assert phase["submitted"] is False and seen["requests"] == []
    assert "cost cap" in capsys.readouterr().err


def test_partial_success_and_nothing_to_do_still_exit_zero(tmp_path, monkeypatch):
    """Only a run that did none of its work alerts. One success among failures is a normal day
    (the rest go to manual review), and a day with nothing to fill is the steady state. (A
    pilot-first confirm stop keeps exit 0 too: test_confirm_gate_blocks_paid_run_over_threshold.)"""
    rc, seen, phase = _live_blog_run(tmp_path / "none", monkeypatch, {"a": {"summary": "<p>Have one.</p>"}})
    assert rc == 0 and phase["requests_built"] == 0

    rc2, seen2, phase2 = _live_blog_run(tmp_path / "some", monkeypatch, {"x": {}, "y": {}}, fail_ids=("y",))
    assert rc2 == 0
    assert seen2["patched"] == ["x"] and phase2["succeeded"] == 1 and phase2["failed"] == 1


def test_a_dry_run_never_alerts(tmp_path):
    assert cli.main(["generate-english", "--collection", "blog", "--dry-run",
                     "--out-dir", str(tmp_path / "dry")]) == 0


def test_a_blog_request_carries_the_blog_keyword_plan_and_the_post_as_text(tmp_path, monkeypatch):
    """U3-S batch 4: the blog path derives its plan with content_type="blog_post" (the
    live test's "vancouver a student guide" came from the generic path), and the post reaches
    Gemini and QA as text, not HTML (the model saw ~half the post, much of it markup)."""
    body = ("<p><strong>Day trips from Vancouver</strong> are easy. Plan day trips from Vancouver "
            "by bus; the ferry takes 20 minutes.</p>")
    rc, seen, phase = _live_blog_run(tmp_path, monkeypatch, {"dt": {
        "name": "Day Trips from Vancouver: A Student Guide to Weekend Escapes",
        "slug": "day-trips-from-vancouver", "post-body": body}})
    assert rc == 0
    manifest = json.loads(Path(phase["manifest_path"]).read_text())
    assert [e["keyword_plan"]["primary"] for e in manifest.values()] == ["day trips from vancouver"]
    assert seen["messages"] and all("<strong>" not in m and "<p>" not in m for m in seen["messages"])


# ---- U3-S batch 5 (U4-1, the Reviewer's P1): a post QA rejects is not re-paid every night ----
# QA demoted a post to manual-review.json (kept 14 days) and nowhere else, so the next night
# queued it, paid for it and demoted it again, green, forever.

def test_a_run_whose_every_summary_qa_rejects_exits_non_zero(tmp_path, monkeypatch, capsys):
    rc, seen, phase = _live_blog_run(tmp_path, monkeypatch, {"e1": {}, "e2": {}}, qa_pass=False)
    assert rc == cli._NO_WORK_DONE_EXIT_CODE
    assert phase["qa_gate"]["checked"] == 2 and phase["qa_gate"]["passed"] == 0
    assert seen["patched"] == []
    assert "QA passed none" in capsys.readouterr().err


def _state(tmp_path):
    return json.loads((tmp_path / "summary-state.json").read_text())


def test_a_post_that_fails_is_recorded_with_its_hash_and_an_attempt_count(tmp_path, monkeypatch):
    _live_blog_run(tmp_path, monkeypatch, {"e1": {}}, qa_pass=False)
    entry = _state(tmp_path)["e1"]
    assert entry["failed_attempts"] == 1 and entry["source_hash"] and "last_error" in entry
    assert "generated_at" not in entry  # not a written post

    _live_blog_run(tmp_path, monkeypatch, {"e2": {}}, fail_all=True, out_name="run2")
    assert _state(tmp_path)["e2"]["failed_attempts"] == 1  # a Gemini failure counts too


def test_a_post_that_failed_twice_is_held_until_its_body_changes(tmp_path, monkeypatch):
    post = {"post-body": "Some blog body text about studying."}
    _live_blog_run(tmp_path, monkeypatch, {"e1": post}, qa_pass=False, out_name="n1")
    _live_blog_run(tmp_path, monkeypatch, {"e1": post}, qa_pass=False, out_name="n2")
    assert _state(tmp_path)["e1"]["failed_attempts"] == 2

    rc, seen, phase = _live_blog_run(tmp_path, monkeypatch, {"e1": post}, out_name="n3")
    assert rc == 0 and seen["requests"] == []              # held: nothing sent, nothing paid
    assert phase["held_for_review"] == ["https://www.englishcollege.com/post/post-e1"]

    edited = {"post-body": "The post was edited, so its body is new."}
    rc, seen, phase = _live_blog_run(tmp_path, monkeypatch, {"e1": edited}, out_name="n4")
    assert rc == 0 and seen["requests"] == ["gen-0-e1"] and seen["patched"] == ["e1"]
    assert "failed_attempts" not in _state(tmp_path)["e1"]   # written: the checkpoint replaces it


def test_a_failure_counts_only_against_the_same_body(tmp_path, monkeypatch):
    _live_blog_run(tmp_path, monkeypatch, {"e1": {"post-body": "Version one of the post."}},
                   qa_pass=False, out_name="v1")
    _live_blog_run(tmp_path, monkeypatch, {"e1": {"post-body": "Version two of the post."}},
                   qa_pass=False, out_name="v2")
    assert _state(tmp_path)["e1"]["failed_attempts"] == 1
