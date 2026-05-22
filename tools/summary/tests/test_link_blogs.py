"""Tests for the `link-blogs` mode (2026-05-22) — insert internal links into existing
under-linked blog summaries (Flash, link-only). Dry-run only: no API/Webflow calls.

Target selection is the contract that matters offline: only blog_post entries whose
existing summary has <= --max-existing-links internal links are processed; 4-part pages
(course/housing/landing) and already-linked blogs are never touched.
"""

import json
from pathlib import Path

from tools.summary import cli


def _write_manifest(run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        # zero-link EN blog → a target
        "gen-0": {
            "url": "https://www.englishcollege.com/post/zero-link-en",
            "markdown": (
                "## How long to learn English in Vancouver\n\n"
                "Most students reach B2 in 12 weeks at CEL with small classes and "
                "intensive options that genuinely accelerate progress for everyone."
            ),
            "content_type": "blog_post", "locale": "en",
            "keyword_plan": {"primary": "learn english in vancouver"},
        },
        # already-linked EN blog (1 internal link) → skipped at the default cap of 0
        "gen-1": {
            "url": "https://www.englishcollege.com/post/already-linked-en",
            "markdown": (
                "## Title\n\nText with [a real link](https://www.englishcollege.com/courses) "
                "already present, so this post is left alone."
            ),
            "content_type": "blog_post", "locale": "en",
        },
        # a course (4-part) → never a link-blogs target
        "gen-2": {
            "url": "https://www.englishcollege.com/courses/general-english",
            "markdown": "## Tagline\n\n### Title\n\nCourse summary body.",
            "content_type": "course", "locale": "en",
        },
        # zero-link DE blog → a target (locale de)
        "gen-3": {
            "url": "https://www.englishcollege.com/de/post/de-zero-link",
            "markdown": (
                "## Wie lange dauert es, Englisch zu lernen\n\n"
                "Die meisten Lernenden erreichen B2 in etwa zwoelf Wochen mit kleinen Klassen."
            ),
            "content_type": "blog_post", "locale": "de",
        },
    }
    (run_dir / "en-summaries.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_dir


def _run(tmp_path: Path, extra_args: list[str]) -> dict:
    run_dir = _write_manifest(tmp_path / "run")
    out_dir = tmp_path / "out"
    rc = cli.main(["link-blogs", "--from-run", str(run_dir), "--out-dir", str(out_dir), *extra_args])
    assert rc == 0
    report = json.loads((out_dir / "report.json").read_text())
    return report["phases"]["link_blogs"]


def test_link_blogs_selects_only_underlinked_blogs(tmp_path):
    """Default --max-existing-links=0: the two zero-link blogs (EN + DE) are targets;
    the already-linked blog and the course are skipped."""
    lb = _run(tmp_path, [])
    assert lb["targets_found"] == 2, lb
    assert lb["requests_built"] == 2, lb
    assert lb["dry_run"] is True
    # Cost is computed and tiny (Flash, 2 items).
    assert lb["cost_gate"]["projected_usd"] >= 0
    assert lb["cost_gate"]["model_breakdown"]  # blog model present


def test_link_blogs_locale_filter(tmp_path):
    """--locale en restricts targets to EN blogs only (1 of the 2 zero-link blogs)."""
    lb = _run(tmp_path, ["--locale", "en"])
    assert lb["targets_found"] == 1, lb


def test_link_blogs_max_existing_links_includes_thinly_linked(tmp_path):
    """--max-existing-links 1 also picks up the 1-link blog (now 3 targets)."""
    lb = _run(tmp_path, ["--max-existing-links", "1"])
    assert lb["targets_found"] == 3, lb


def test_link_blogs_limit_caps_requests(tmp_path):
    """--limit caps the number of requests built."""
    lb = _run(tmp_path, ["--limit", "1"])
    assert lb["requests_built"] == 1, lb


def test_dedup_md_links_unwraps_repeated_targets():
    """The 2026-05-22 pilot saw one duplicate link; _dedup_md_links keeps the first
    occurrence and unwraps later ones to plain text."""
    md = (
        "See [San Diego school](https://www.englishcollege.com/san-diego-ca/language-school) "
        "and later [the SD school again](https://www.englishcollege.com/san-diego-ca/language-school) "
        "plus [courses](https://www.englishcollege.com/courses)."
    )
    out = cli._dedup_md_links(md)
    # First SD link kept; second unwrapped to its anchor text; courses untouched.
    assert out.count("(https://www.englishcollege.com/san-diego-ca/language-school)") == 1
    assert "the SD school again" in out  # anchor text preserved as plain prose
    assert "[the SD school again]" not in out  # but no longer a link
    assert "(https://www.englishcollege.com/courses)" in out
    assert cli._count_internal_md_links(out) == 2  # SD (once) + courses


def test_trim_links_to_ceiling_unwraps_excess():
    """An over-linked short post (links > 1 per ~80 words) is trimmed to the ceiling so it
    passes no_link_stuffing instead of being demoted (2026-05-22 full-run finding)."""
    body = " ".join(["word"] * 120)
    links = " ".join(
        f"[anchor phrase {i}](https://www.englishcollege.com/page-{i})" for i in range(10)
    )
    md = f"## Heading\n\n{body} {links}"
    assert cli._count_internal_md_links(md) == 10
    out = cli._trim_links_to_ceiling(md)
    after = cli._count_internal_md_links(out)
    assert after < 10  # trimmed
    import re
    wc = len(re.findall(r"\b\w+\b", re.sub(r"<[^>]+>", " ", out)))
    assert after <= wc // 80  # at/under the 1-per-80 ceiling


def test_trim_output_passes_qa_no_link_stuffing():
    """Regression for the 2026-05-22 stragglers (7 links / 556 words slipped past): QA's
    no_link_stuffing counts URL tokens as words, so the trim must count the DE-LINKED text
    to stay strictly under QA's ceiling. After trim, no_link_stuffing must PASS."""
    from tools.summary.qa import qa_checks

    body = " ".join(["word"] * 556)
    links = " ".join(
        f"[anchor phrase {i}](https://www.englishcollege.com/page-{i})" for i in range(9)
    )
    md = f"## a section heading\n\n{body} {links}"
    trimmed = cli._trim_links_to_ceiling(md)
    rep = qa_checks(trimmed, "a section", "en", [])
    assert rep.checks["no_link_stuffing"], (cli._count_internal_md_links(trimmed), rep.notes)


def test_trim_links_to_ceiling_leaves_within_ceiling_untouched():
    body = " ".join(["word"] * 700)  # ~700 words → ceiling ~8
    links = " ".join(
        f"[anchor phrase {i}](https://www.englishcollege.com/page-{i})" for i in range(6)
    )
    md = f"## Heading\n\n{body} {links}"
    out = cli._trim_links_to_ceiling(md)
    assert cli._count_internal_md_links(out) == 6  # 6 within ceiling → unchanged


def test_link_blogs_missing_manifest_is_clean_error(tmp_path):
    out_dir = tmp_path / "out"
    rc = cli.main(["link-blogs", "--from-run", str(tmp_path / "nope"), "--out-dir", str(out_dir)])
    assert rc == 0
    lb = json.loads((out_dir / "report.json").read_text())["phases"]["link_blogs"]
    assert lb["submitted"] is False
    assert lb["requests_built"] == 0
    assert "manifest not found" in lb["reason"]
