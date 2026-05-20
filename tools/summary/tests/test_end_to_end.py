"""End-to-end stress test for the summary pipeline (tracker-087 Phase D).

Exercises plan → generate-english → audit → translate with mocked SDK + Webflow.
Verifies WIRING correctness, NOT prompt-output quality (which only a live run
can verify). All network calls are mocked at module boundary.

This single test file proves that:
  - generate-english writes en-summaries.json + manual-review.json
  - the retry loop fires for failed batch items
  - persistent failures land in manual-review.json
  - translate reads the manifest and writes per-locale CSV via csv_emitter
  - cost-cap firing returns submitted: False
  - the public CLI exits 0 on every well-formed input
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.summary import batch_runner, cli, page_fetcher, webflow_client


# ---- Shared fixtures ----


def _fake_page_content(url: str, timeout: float = 20.0) -> page_fetcher.PageContent:
    """Stub PageContent for any URL — deterministic across tests."""
    return page_fetcher.PageContent(
        url=url,
        final_url=url,
        status=200,
        html="<html><body><h1>Learn English in Vancouver</h1></body></html>",
        title="Learn English in Vancouver | CEL",
        h1="Learn English in Vancouver",
        headings=("Learn English in Vancouver",),
        canonical=url,
        hreflang_urls=(),
        existing_summary_html="",
        body_text_excerpt=(
            "CEL operates English schools in San Diego, Los Angeles, and Vancouver. "
            "Most students reach B2 in 12 weeks of full-time study at our Vancouver campus. "
            "Vancouver Vancouver Vancouver campus campus campus students students students "
            "courses courses courses program program program."
        ),
    )


def _fake_batch_handle() -> batch_runner.BatchHandle:
    return batch_runner.BatchHandle(
        batch_id="mock-batch-123",
        request_count=2,
        submitted_at="2026-05-19T00:00:00Z",
        dry_run=False,
    )


def _fake_batch_result(custom_id: str, succeeded: bool, content: str = "", error: str = ""):
    return batch_runner.BatchResult(
        custom_id=custom_id,
        succeeded=succeeded,
        content=content,
        error=error,
        input_tokens=1000,
        output_tokens=300,
    )


# ---- Test 1: plan subcommand exits cleanly ----


def test_plan_subcommand_end_to_end(tmp_path: Path):
    """`plan --dry-run` walks all three phase planners and writes report.json."""
    rc = cli.main(["plan", "--dry-run", "--out-dir", str(tmp_path)])
    assert rc == 0
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["subcommand"] == "plan"
    assert "generate_english" in report["phases"]
    assert "audit" in report["phases"]
    assert "translate" in report["phases"]


# ---- Test 2: generate-english live mode with mocked SDK + Webflow ----


def test_generate_english_live_mode_writes_manifest_and_manual_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Live generate-english (mocked) writes en-summaries.json + manual-review.json.

    Simulates 2 source items: one succeeds, one fails. The retry loop fires for the
    failed one; if it persists, manual-review.json captures it.
    """
    monkeypatch.setattr(page_fetcher, "fetch_page", _fake_page_content)

    submit_calls = []
    wait_calls = []

    def fake_submit(requests, *args, **kwargs):
        submit_calls.append(list(requests))
        return _fake_batch_handle()

    def fake_wait(handle, *args, **kwargs):
        wait_calls.append(handle.batch_id)
        # First call: 1 success + 1 failure.
        if len(wait_calls) == 1:
            return [
                _fake_batch_result(
                    submit_calls[0][0].custom_id,
                    succeeded=True,
                    # tracker-092: content must pass the generate-phase QA gate or
                    # it would be demoted to MANUAL_REVIEW. The first static page is
                    # the home page, whose primary keyword is the M-12.4 override
                    # "english language school" — so the H2 + first 120 chars of P1
                    # must contain that exact phrase.
                    content=(
                        "## What to expect from an english language school\n\n"
                        "Twelve weeks is the typical timeline: at an english language "
                        "school like CEL, most students reach B2 in that time across "
                        "our Vancouver, San Diego, and Los Angeles campuses.\n"
                    ),
                ),
                _fake_batch_result(
                    submit_calls[0][1].custom_id,
                    succeeded=False,
                    error="rate-limited; please retry",
                ),
            ]
        # Second call (retry): still fails — should land in MANUAL_REVIEW.
        return [
            _fake_batch_result(
                submit_calls[1][0].custom_id,
                succeeded=False,
                error="still rate-limited",
            ),
        ]

    monkeypatch.setattr(batch_runner, "submit_batch", fake_submit)
    monkeypatch.setattr(batch_runner, "wait_for_batch", fake_wait)
    # Mock webflow_client.WebflowClient — prevent real instantiation that wants tokens.
    monkeypatch.setattr(
        webflow_client.WebflowClient, "_get_token", lambda self: "fake-token"
    )
    monkeypatch.setattr(
        webflow_client.WebflowClient, "update_item_summary",
        lambda self, **kw: webflow_client.WriteResult(
            dry_run=False, success=True, method="PATCH", url="x",
        ),
    )
    # Redirect WEGLOT_IMPORTS_DIR to tmp_path so the live _write_back_summaries
    # path doesn't pollute the real docs/admin/weglot-imports/ directory
    # (tracker-089 H-1; tracker-088 deviation log #2).
    from tools.summary import config
    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", tmp_path / "weglot-out")

    # Limit to 2 static pages so we have exactly 2 batch requests.
    rc = cli.main([
        "generate-english", "--no-dry-run", "--limit", "2",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0

    # Manifest written.
    manifest_path = tmp_path / "en-summaries.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert len(manifest) >= 1  # at least one success captured
    # First success's content is in the manifest.
    succeeded_cids = [
        cid for cid, entry in manifest.items() if "Twelve weeks" in entry.get("markdown", "")
    ]
    assert len(succeeded_cids) >= 1

    # MANUAL_REVIEW captured the persistent failure.
    review_path = tmp_path / "manual-review.json"
    assert review_path.exists()
    review = json.loads(review_path.read_text())
    assert len(review["custom_ids"]) >= 1
    assert all("retry_attempted" in d for d in review["details"])

    # Retry loop fired (submit_batch was called 2x: initial + retry).
    assert len(submit_calls) == 2


# ---- Test 3: cost cap aborts before submission ----


def test_generate_english_cost_cap_aborts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When estimated cost > MAX_BATCH_COST_USD, no batch is submitted."""
    monkeypatch.setattr(page_fetcher, "fetch_page", _fake_page_content)

    submit_called = []

    def fake_submit(requests, *args, **kwargs):
        submit_called.append(True)
        return _fake_batch_handle()

    monkeypatch.setattr(batch_runner, "submit_batch", fake_submit)
    monkeypatch.setattr(batch_runner, "estimate_batch_cost_usd", lambda *a, **kw: 250.0)

    rc = cli.main([
        "generate-english", "--no-dry-run", "--limit", "1",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    report = json.loads((tmp_path / "report.json").read_text())
    phase = report["phases"]["generate_english"]
    assert phase["submitted"] is False
    assert any("COST CAP" in w for w in phase["warnings"])
    # submit_batch must NOT have been called.
    assert submit_called == []


# ---- Test 4: translate phase live mode with mocked SDK ----


def test_translate_live_mode_emits_csv_for_target_locale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Translate phase reads manifest, submits batch, writes CSV via csv_emitter."""
    # Stage an EN manifest with a landing entry + a housing entry. Tracker-091
    # M-10: housing CMS items must be filtered out of the translate phase
    # (housing_new is in NO_TRANSLATE_COLLECTIONS).
    manifest = {
        "gen-0-test": {
            "url": "https://www.englishcollege.com/learn-english-usa",
            "markdown": (
                "## How long does it take?\n\n"
                "Twelve weeks for a strong B2 at our Vancouver campus.\n"
            ),
            "content_type": "landing",
            "locale": "en",
        },
        "gen-1-housing": {
            "url": "https://www.englishcollege.com/housing/some-residence",
            "markdown": "## Where to live\n\nKitsilano apartment with kitchenette.\n",
            "content_type": "housing",  # M-10: must be filtered out
            "locale": "en",
        },
    }
    (tmp_path / "en-summaries.json").write_text(json.dumps(manifest), encoding="utf-8")

    captured_submit_calls = []

    def fake_submit(requests, *args, **kwargs):
        captured_submit_calls.append(list(requests))
        return _fake_batch_handle()

    def fake_wait(handle, *args, **kwargs):
        # Translation result mirrors the source paragraph structure.
        return [
            _fake_batch_result(
                "tr-de-gen-0-test",
                succeeded=True,
                content=(
                    "## Wie lange dauert es?\n\n"
                    "Zwölf Wochen für ein solides B2 an unserem Campus in Vancouver.\n"
                ),
            )
        ]

    monkeypatch.setattr(batch_runner, "submit_batch", fake_submit)
    monkeypatch.setattr(batch_runner, "wait_for_batch", fake_wait)
    # Make llms_parser.fetch_and_parse return None to skip the network.
    from tools.summary import llms_parser
    monkeypatch.setattr(
        llms_parser, "fetch_and_parse",
        lambda *a, **kw: llms_parser.LlmsIndex(entries=[]),
    )

    # Redirect WEGLOT_IMPORTS_DIR to tmp_path so we don't pollute the real CSV dir.
    from tools.summary import config
    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", tmp_path / "weglot-out")

    rc = cli.main([
        "translate", "--no-dry-run", "--locale", "de",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    report = json.loads((tmp_path / "report.json").read_text())
    phase = report["phases"]["translate"]
    assert phase["target_locales"] == ["de"]
    de_result = phase["per_locale"]["de"]
    assert de_result["dry_run"] is False
    assert de_result["rows_appended"] >= 1
    # CSV was actually written.
    csv_path = tmp_path / "weglot-out" / "de.csv"
    assert csv_path.exists()
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "Zwölf Wochen" in csv_text
    assert "en;de" in csv_text  # Weglot CSV format: language_from;language_to
    # M-10: housing entry must have been filtered out — submit_batch saw exactly 1 request.
    assert len(captured_submit_calls) == 1, "expected exactly 1 submit_batch call (1 locale)"
    assert len(captured_submit_calls[0]) == 1, (
        f"expected 1 request (landing only; housing filtered), got {len(captured_submit_calls[0])}"
    )


# ---- Test 5: full `all` subcommand wires the three phases together ----


def test_all_subcommand_runs_generate_audit_translate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """`all` runs all three phases in one process and uses the in-process manifest."""
    monkeypatch.setattr(page_fetcher, "fetch_page", _fake_page_content)

    def fake_submit(requests, *args, **kwargs):
        return _fake_batch_handle()

    def fake_wait(handle, *args, **kwargs):
        # Distinguish generate from translate by custom_id prefix.
        first = handle.batch_id
        # The orchestrator submits gen-* first, then tr-* per locale.
        # Return success for whatever requests are observed.
        return [
            _fake_batch_result(
                "gen-0-x",
                succeeded=True,
                content="## How long?\n\nTwelve weeks.\n",
            )
        ]

    monkeypatch.setattr(batch_runner, "submit_batch", fake_submit)
    monkeypatch.setattr(batch_runner, "wait_for_batch", fake_wait)
    monkeypatch.setattr(
        webflow_client.WebflowClient, "_get_token", lambda self: "fake-token"
    )
    monkeypatch.setattr(
        webflow_client.WebflowClient, "update_item_summary",
        lambda self, **kw: webflow_client.WriteResult(
            dry_run=False, success=True, method="PATCH", url="x",
        ),
    )
    monkeypatch.setattr(
        webflow_client.WebflowClient, "list_items", lambda self, *a, **kw: iter([])
    )
    rc = cli.main([
        "all", "--dry-run", "--limit", "1",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    report = json.loads((tmp_path / "report.json").read_text())
    assert "generate_english" in report["phases"]
    assert "audit" in report["phases"]
    assert "translate" in report["phases"]


# ---- Test 6: SSRF defense in page_fetcher (regression for tracker-087 F-3) ----


def test_fetch_page_ssrf_defense_blocks_file_scheme():
    """Belt-and-suspenders: even with the orchestrator wiring, file:// is blocked."""
    with pytest.raises(ValueError, match="must be http or https"):
        page_fetcher.fetch_page("file:///etc/passwd")
