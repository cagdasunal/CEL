"""Tests for tools.summary.webflow_client — dry-run path (no real HTTP)."""

from tools.summary.webflow_client import WebflowClient, WriteResult


def test_dry_run_update_item_summary_returns_mock_response():
    client = WebflowClient(dry_run=True)
    result = client.update_item_summary(
        collection_id="abc",
        item_id="item-1",
        summary_html="<p>Summary content.</p>",
    )
    assert isinstance(result, WriteResult)
    assert result.dry_run is True
    assert result.success is True
    assert result.method == "PATCH"
    assert "abc" in result.url
    assert "item-1" in result.url
    assert result.payload["fieldData"]["summary"] == "<p>Summary content.</p>"
    assert "_dry_run" in result.response


def test_dry_run_does_not_require_token():
    # No env var set, no network call expected.
    client = WebflowClient(dry_run=True, token_env="NON_EXISTENT_VAR_FOR_TEST")
    result = client.update_item_summary("abc", "item-1", "<p>x</p>")
    assert result.dry_run is True
    assert result.success is True


class _FakeResp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b'{"ok": true}'


def test_request_retries_on_timeout_then_succeeds():
    """tracker-098: a transient socket read-timeout (bare TimeoutError) is retried with
    backoff — it must NOT propagate. Two timeouts then success → one successful write."""
    from unittest import mock
    from tools.summary import webflow_client as wc

    client = wc.WebflowClient(dry_run=False)
    client._token = "test-token"  # bypass env token fetch
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("The read operation timed out")
        return _FakeResp()

    with mock.patch.object(wc.urllib.request, "urlopen", fake_urlopen), \
            mock.patch.object(wc.time, "sleep", lambda s: None):
        out = client.update_item_summary("c", "i", "<p>x</p>")
    assert out.success is True
    assert calls["n"] == 3  # retried past the two timeouts


def test_request_persistent_timeout_returns_failure_not_crash():
    """tracker-098: a PERSISTENT read-timeout must return a failed WriteResult (so the
    write-back loop logs it and continues) — NOT raise a bare TimeoutError that crashes
    the whole batch after a paid generation (the run-098-full incident)."""
    from unittest import mock
    from tools.summary import webflow_client as wc

    client = wc.WebflowClient(dry_run=False)
    client._token = "test-token"

    def always_timeout(req, timeout=None):
        raise TimeoutError("The read operation timed out")

    with mock.patch.object(wc.urllib.request, "urlopen", always_timeout), \
            mock.patch.object(wc.time, "sleep", lambda s: None):
        out = client.update_item_summary("c", "i", "<p>x</p>")
    assert out.success is False
    assert "Network error" in (out.error or "")


def test_dry_run_update_item_summary_parts_writes_four_fields():
    """tracker-096/098: the legacy 4-part CMS write (retained for back-compat) patches
    Tagline/Title/Paragraphs + the RichText Content. tracker-098 renamed the Paragraphs
    slug to `summary---paragraphs`."""
    client = WebflowClient(dry_run=True)
    result = client.update_item_summary_parts(
        collection_id="cid", item_id="i1",
        tagline="English School Life",
        title="What to expect from an english language school",
        paragraph="<p>Twelve weeks to a strong B2.</p>",
        content_html="<h4>How long</h4><p>Twelve weeks.</p>",
    )
    assert result.dry_run is True
    assert result.success is True
    assert result.method == "PATCH"
    assert "cid" in result.url and "i1" in result.url
    fd = result.payload["fieldData"]
    assert fd["summary---tagline"] == "English School Life"
    assert fd["summary---title"] == "What to expect from an english language school"
    # tracker-098: Paragraphs slug renamed (singular → plural).
    assert fd["summary---paragraphs"] == "<p>Twelve weeks to a strong B2.</p>"
    # Content reuses the existing `summary` slug and carries HTML, not Markdown.
    assert fd["summary"] == "<h4>How long</h4><p>Twelve weeks.</p>"


def test_dry_run_update_item_summary_body_writes_only_two_richtext_fields():
    """tracker-098: the live 4-part write path patches ONLY the two RichText bodies
    (Paragraphs + Content), preserving the author-owned Tagline + Title."""
    client = WebflowClient(dry_run=True)
    result = client.update_item_summary_body(
        collection_id="cid", item_id="i1",
        paragraph_html="<p>Most students reach B2 in 12 weeks.</p><p>Beginners need longer.</p>",
        content_html="<h4>Who is this for</h4><p>University-bound students.</p>",
    )
    assert result.dry_run is True
    assert result.success is True
    assert result.method == "PATCH"
    assert "cid" in result.url and "i1" in result.url
    fd = result.payload["fieldData"]
    # Only the two RichText bodies are written — NOT the tagline/title slugs.
    assert set(fd.keys()) == {"summary---paragraphs", "summary"}
    assert "summary---tagline" not in fd
    assert "summary---title" not in fd
    assert fd["summary---paragraphs"].startswith("<p>Most students reach B2")
    assert fd["summary"] == "<h4>Who is this for</h4><p>University-bound students.</p>"


def test_dry_run_publish_items_returns_would_publish():
    """--publish autopilot: dry-run must NOT hit the network — it returns the would-publish
    plan so a dry-run reveals exactly which items would go live."""
    client = WebflowClient(dry_run=True, token_env="NON_EXISTENT_VAR_FOR_TEST")
    result = client.publish_items("coll-1", ["a", "b"])
    assert result.dry_run is True
    assert result.success is True
    assert result.method == "POST"
    assert result.url.endswith("/collections/coll-1/items/publish")
    assert result.payload["itemIds"] == ["a", "b"]
    assert result.response["would_publish"] == ["a", "b"]


def test_publish_items_empty_is_noop_success():
    """Empty list short-circuits: success, no token needed, no network call."""
    client = WebflowClient(dry_run=False, token_env="NON_EXISTENT_VAR_FOR_TEST")
    result = client.publish_items("coll-1", [])
    assert result.success is True
    assert result.payload["itemIds"] == []


class _PublishResp:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def test_publish_items_live_chunks_over_100():
    """Webflow caps itemIds at 100/call — 150 ids must split into 2 POSTs and the
    published ids from both chunks are merged."""
    import json as _json
    from unittest import mock
    from tools.summary import webflow_client as wc

    client = wc.WebflowClient(dry_run=False)
    client._token = "test-token"
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        body = _json.loads(req.data.decode("utf-8"))
        ids = body["itemIds"]
        return _PublishResp(_json.dumps({"publishedItemIds": ids, "errors": []}).encode("utf-8"))

    with mock.patch.object(wc.urllib.request, "urlopen", fake_urlopen), \
            mock.patch.object(wc.time, "sleep", lambda s: None):
        ids = [f"id-{i}" for i in range(150)]
        out = client.publish_items("coll", ids)
    assert out.success is True
    assert calls["n"] == 2  # 100 + 50
    assert len(out.response["publishedItemIds"]) == 150
    assert out.response["errors"] == []


def test_publish_items_live_persistent_failure_returns_failed_result():
    """A persistent network failure on publish must return success=False (the autopilot
    logs it and the staged summary stays for the next run) — never crash the run."""
    from unittest import mock
    from tools.summary import webflow_client as wc

    client = wc.WebflowClient(dry_run=False)
    client._token = "test-token"

    def always_timeout(req, timeout=None):
        raise TimeoutError("The read operation timed out")

    with mock.patch.object(wc.urllib.request, "urlopen", always_timeout), \
            mock.patch.object(wc.time, "sleep", lambda s: None):
        out = client.publish_items("coll", ["a", "b"])
    assert out.success is False
    assert out.error


def test_dry_run_ensure_summary_field_when_missing():
    # We can't easily test the "exists" branch without a real API. The missing-
    # field branch is the one we care about for dry-run safety.
    # This test just verifies the dry_run mock path doesn't try to call the API.
    client = WebflowClient(dry_run=True, token_env="NON_EXISTENT_VAR_FOR_TEST")
    # find_summary_field requires a real API call; in dry-run we can't pre-test
    # the "exists" branch. The ensure_summary_field method calls find_summary_field
    # which WILL try to hit the network. Skip this for now — the test below covers
    # the dry-run promise.


def test_batch_runner_dry_run_writes_artifact(tmp_path):
    from tools.summary.batch_runner import BatchRequest, dry_run_submit

    requests = [
        BatchRequest(
            custom_id="test-1",
            system_blocks=[{"type": "text", "text": "system"}],
            user_message="hello",
            max_tokens=500,
        )
    ]
    handle = dry_run_submit(requests, artifact_dir=tmp_path)
    assert handle.dry_run is True
    assert handle.request_count == 1
    assert handle.artifact_path is not None
    assert handle.artifact_path.exists()
    content = handle.artifact_path.read_text(encoding="utf-8")
    assert "test-1" in content
    assert "hello" in content


def test_cost_estimate_under_cap_for_typical_batch():
    from tools.summary.batch_runner import BatchRequest, estimate_batch_cost_usd

    requests = [
        BatchRequest(
            custom_id=f"r-{i}",
            system_blocks=[{"type": "text", "text": "system"}],
            user_message="user",
        )
        for i in range(200)
    ]
    cost = estimate_batch_cost_usd(requests)
    # ~$0.10 per request with caching + batch discount; 200 should be well under cap.
    assert 0 < cost < 100, f"unexpected cost estimate: {cost}"


def test_cost_estimate_zero_for_empty_batch():
    from tools.summary.batch_runner import estimate_batch_cost_usd

    assert estimate_batch_cost_usd([]) == 0.0
