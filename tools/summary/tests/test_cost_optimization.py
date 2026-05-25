"""Tests for tracker-097 — Gemini cost-efficiency.

Covers the offline-verifiable surface of the cost work: honest per-model /
batch-vs-interactive / cache-aware estimation, the cache plan, model tiering,
the pilot-first confirm gate + lowered cap, batch-id persistence, cancel/retrieve,
and the per-model batch grouping. The live cache create/delete + Batch submit are
exercised structurally with a faked google-genai client (no real API calls).
"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from tools.summary import batch_runner, cli, config


# ---- Estimator: batch vs interactive, per-model, cache-aware (RC1/RC2) ----


def _req(cid: str, *, system: str, user: str, model: str = "") -> batch_runner.BatchRequest:
    return batch_runner.BatchRequest(
        custom_id=cid, system_blocks=[{"type": "text", "text": system}],
        user_message=user, model=model,
    )


def test_estimate_interactive_is_pricier_than_batch():
    """RC2: --sync bills at interactive ($2/$12 Pro); the estimator must price it
    higher than the Batch tier ($1/$6). The old estimator priced both at batch."""
    reqs = [_req(f"r{i}", system="s" * 1000, user="u" * 400) for i in range(5)]
    batch = batch_runner.estimate_batch_cost_usd(reqs, mode="batch")
    interactive = batch_runner.estimate_batch_cost_usd(reqs, mode="interactive")
    assert interactive > batch
    # Pro interactive input is exactly 2× batch; output 2× too → overall ~2×.
    assert 1.9 < interactive / batch < 2.1


def test_estimate_flash_cheaper_than_pro():
    """Tiering payoff: a Flash request costs materially less than a Pro request."""
    pro = batch_runner.estimate_batch_cost_usd(
        [_req("p", system="s" * 1000, user="u" * 400, model="gemini-3.1-pro-preview")],
        mode="batch",
    )
    flash = batch_runner.estimate_batch_cost_usd(
        [_req("f", system="s" * 1000, user="u" * 400, model="gemini-2.5-flash")],
        mode="batch",
    )
    assert flash < pro
    assert flash < pro / 2  # Flash batch is ~6.7× input / ~4.8× output cheaper


def test_estimate_caching_reduces_cost_for_eligible_group():
    """RC1: with caching engaged and an eligible shared-prefix group, the cost is
    lower than the same run without caching."""
    big = "x" * 30000  # ~7500 tokens > Pro cache_min (4096)
    reqs = [_req(f"r{i}", system=big, user="u" * 200) for i in range(4)]
    uncached = batch_runner.estimate_batch_cost_usd(reqs, mode="batch", cached=False)
    cached = batch_runner.estimate_batch_cost_usd(reqs, mode="batch", cached=True)
    assert cached < uncached


def test_estimate_caching_no_credit_for_tiny_prefix():
    """A prefix below the model minimum is NOT cacheable → cached==uncached."""
    reqs = [_req(f"r{i}", system="tiny", user="u") for i in range(4)]
    assert (
        batch_runner.estimate_batch_cost_usd(reqs, mode="batch", cached=True)
        == batch_runner.estimate_batch_cost_usd(reqs, mode="batch", cached=False)
    )


def test_estimate_robust_to_non_batchrequest_objects():
    """translate-meta passes TranslationUnit-like objects (no system_blocks /
    user_message). The estimator must fall back to avg input, not crash."""
    units = [SimpleNamespace(id=f"u{i}", text="t", content_type="meta_title") for i in range(3)]
    cost = batch_runner.estimate_batch_cost_usd(units)
    assert cost > 0


def test_estimate_empty_and_keyword_arg_preserved():
    """Back-compat: requests= keyword + []→0.0 (existing callers/tests rely on this)."""
    assert batch_runner.estimate_batch_cost_usd(requests=[]) == 0.0


# ---- plan_caches ----


def test_plan_caches_eligible_when_group_big_and_prefix_long():
    big = "x" * 30000
    reqs = [_req("a", system=big, user="u1"), _req("b", system=big, user="u2")]
    plan = batch_runner.plan_caches(reqs, model=config.MODEL_ID)
    assert len(plan) == 1
    assert plan[0].eligible is True
    assert plan[0].request_count == 2


def test_plan_caches_ineligible_when_group_too_small():
    big = "x" * 30000
    plan = batch_runner.plan_caches([_req("a", system=big, user="u")], model=config.MODEL_ID)
    assert plan[0].eligible is False
    assert "too small" in plan[0].reason


def test_plan_caches_ineligible_when_prefix_too_short():
    reqs = [_req("a", system="short", user="u"), _req("b", system="short", user="u")]
    plan = batch_runner.plan_caches(reqs, model=config.MODEL_ID)
    assert plan[0].eligible is False
    assert "min" in plan[0].reason


def test_plan_caches_separates_models():
    big = "x" * 30000
    reqs = [
        _req("a", system=big, user="u", model="gemini-3.1-pro-preview"),
        _req("b", system=big, user="u", model="gemini-2.5-flash"),
    ]
    plan = batch_runner.plan_caches(reqs)
    assert len(plan) == 2  # same prefix, different models → distinct cache groups


# ---- Model tiering ----


def test_model_for_content_type_tiers_blog_to_flash():
    assert config.model_for_content_type("blog_post") == config.MODEL_BLOG
    assert "flash" in config.MODEL_BLOG.lower()
    for ct in ("course", "housing", "landing", "anything-else"):
        assert config.model_for_content_type(ct) == config.MODEL_ID


def test_flash_generation_config_disables_thinking():
    """Flash supports thinking_budget=0 (cost). Pro keeps a positive budget."""
    r = batch_runner.BatchRequest(custom_id="x", system_blocks=[], user_message="u", enable_thinking=True)
    flash_cfg = batch_runner._build_generation_config(r, "sys", model="gemini-2.5-flash")
    assert flash_cfg["thinking_config"]["thinking_budget"] == 0
    pro_cfg = batch_runner._build_generation_config(r, "sys", model="gemini-3.1-pro-preview")
    assert pro_cfg["thinking_config"]["thinking_budget"] == config.THINKING_BUDGET_TOKENS


def test_cached_content_omits_system_instruction():
    r = batch_runner.BatchRequest(custom_id="x", system_blocks=[], user_message="u")
    cfg = batch_runner._build_generation_config(r, "sys", model=config.MODEL_ID, cached_content_name="cachedContents/0")
    assert cfg["cached_content"] == "cachedContents/0"
    assert "system_instruction" not in cfg


def test_source_hash_includes_model():
    """Hotspot #3: retiering an item changes its hash (forces regeneration)."""
    h_pro = cli._source_hash("body", "cid", "gemini-3.1-pro-preview")
    h_flash = cli._source_hash("body", "cid", "gemini-2.5-flash")
    assert h_pro != h_flash
    assert cli._source_hash("body", "cid", "gemini-3.1-pro-preview") == h_pro  # stable


# ---- _submit_and_wait groups the Batch path by model ----


def test_submit_and_wait_groups_by_model(monkeypatch):
    submits = []

    def fake_submit(requests, **kw):
        submits.append((kw.get("model"), [r.custom_id for r in requests]))
        return batch_runner.BatchHandle(
            batch_id=f"b-{kw.get('model')}", request_count=len(requests),
            submitted_at="t", dry_run=False,
        )

    monkeypatch.setattr(batch_runner, "submit_batch", fake_submit)
    monkeypatch.setattr(batch_runner, "wait_for_batch", lambda h, **kw: [])

    reqs = [
        _req("pro1", system="s", user="u", model="gemini-3.1-pro-preview"),
        _req("flash1", system="s", user="u", model="gemini-2.5-flash"),
        _req("pro2", system="s", user="u", model="gemini-3.1-pro-preview"),
    ]

    class _Args:
        sync = False

    _results, _primary, batch_ids = cli._submit_and_wait(reqs, _Args())
    assert len(submits) == 2  # one Batch job per model
    assert {m for m, _ in submits} == {"gemini-3.1-pro-preview", "gemini-2.5-flash"}
    pro_ids = next(ids for m, ids in submits if m == "gemini-3.1-pro-preview")
    assert pro_ids == ["pro1", "pro2"]
    assert len(batch_ids) == 2


# ---- Pilot-first confirm gate + lowered cap ----

_PASSING = (
    "## English School Life\n\n### What to expect from an english language school\n\n"
    "An english language school like CEL serves students across San Diego, Los Angeles, "
    "and Vancouver, with most reaching B2 in twelve weeks.\n\n"
    "#### How long does it take\n\nMost students reach B2 within twelve weeks.\n"
)


def _run_home_live(monkeypatch, tmp_path, *, estimate: float, extra_args=()):
    from tools.summary import page_fetcher, llms_parser

    def fake_fetch(url, timeout=20.0):
        return page_fetcher.PageContent(
            url=url, final_url=url, status=200,
            html="<html><body><h1>Home</h1></body></html>", title="Home | CEL", h1="Home",
            headings=("Home",), canonical=url, hreflang_urls=(), existing_summary_html="",
            body_text_excerpt="CEL is an english language school in San Diego, Los Angeles, and Vancouver.",
        )

    monkeypatch.setattr(page_fetcher, "fetch_page", fake_fetch)
    monkeypatch.setattr(cli, "_execute_audit", lambda *a, **kw: {})
    monkeypatch.setattr(cli, "_execute_translate", lambda *a, **kw: {})
    monkeypatch.setattr(llms_parser, "fetch_and_parse", lambda *a, **kw: llms_parser.LlmsIndex(entries=[]))
    monkeypatch.setattr(config, "WEGLOT_IMPORTS_DIR", tmp_path / "weglot")
    monkeypatch.setattr(batch_runner, "estimate_batch_cost_usd", lambda *a, **kw: estimate)

    submits = {"n": 0}
    captured: dict = {}

    def fake_submit(requests, **kw):
        submits["n"] += 1
        captured["requests"] = list(requests)
        return batch_runner.BatchHandle(batch_id="b", request_count=len(requests), submitted_at="t", dry_run=False)

    def fake_wait(handle, **kw):
        return [batch_runner.BatchResult(custom_id=r.custom_id, succeeded=True, content=_PASSING) for r in captured.get("requests", [])]

    monkeypatch.setattr(batch_runner, "submit_batch", fake_submit)
    monkeypatch.setattr(batch_runner, "wait_for_batch", fake_wait)

    run_dir = tmp_path / "run"
    rc = cli.main([
        "generate-english", "--no-dry-run", "--page", "https://www.englishcollege.com/",
        "--out-dir", str(run_dir), *extra_args,
    ])
    assert rc == 0
    phase = json.loads((run_dir / "report.json").read_text())["phases"]["generate_english"]
    return phase, submits


def test_confirm_gate_blocks_paid_run_over_threshold(monkeypatch, tmp_path):
    """A LIVE run projected over COST_CONFIRM_THRESHOLD_USD ($1) without --confirm-cost
    refuses to submit (pilot-first)."""
    phase, submits = _run_home_live(monkeypatch, tmp_path, estimate=5.0)
    assert phase["submitted"] is False
    assert phase["cost_gate"]["confirm_required"] is True
    assert any("COST CONFIRM REQUIRED" in w for w in phase["warnings"])
    assert submits["n"] == 0  # no batch submitted


def test_confirm_flag_authorizes_paid_run(monkeypatch, tmp_path):
    """--confirm-cost authorizes the same run → it submits."""
    phase, submits = _run_home_live(monkeypatch, tmp_path, estimate=5.0, extra_args=("--confirm-cost",))
    assert phase["submitted"] is True
    assert phase["cost_gate"]["confirmed"] is True
    assert submits["n"] == 1


def test_cost_cap_blocks_even_with_confirm(monkeypatch, tmp_path):
    """The hard cap (MAX_BATCH_COST_USD=15) aborts regardless of --confirm-cost."""
    phase, submits = _run_home_live(monkeypatch, tmp_path, estimate=20.0, extra_args=("--confirm-cost",))
    assert phase["submitted"] is False
    assert any("COST CAP" in w for w in phase["warnings"])
    assert submits["n"] == 0


def test_tiny_pilot_proceeds_without_confirm(monkeypatch, tmp_path):
    """A run under the threshold does NOT need --confirm-cost (small pilots stay frictionless)."""
    phase, submits = _run_home_live(monkeypatch, tmp_path, estimate=0.05)
    assert phase["submitted"] is True
    assert submits["n"] == 1


def test_dry_run_report_has_cost_gate_and_cache_plan(monkeypatch, tmp_path):
    """DONE CRITERIA: the dry-run report surfaces the cost gate + cache plan."""
    from tools.summary import page_fetcher

    def fake_fetch(url, timeout=20.0):
        return page_fetcher.PageContent(
            url=url, final_url=url, status=200, html="<html><body><h1>X</h1></body></html>",
            title="X | CEL", h1="X", headings=("X",), canonical=url, hreflang_urls=(),
            existing_summary_html="", body_text_excerpt="Body.",
        )

    monkeypatch.setattr(page_fetcher, "fetch_page", fake_fetch)
    monkeypatch.setattr(cli, "_execute_audit", lambda *a, **kw: {})
    monkeypatch.setattr(cli, "_execute_translate", lambda *a, **kw: {})

    rc = cli.main([
        "generate-english", "--dry-run", "--page", "https://www.englishcollege.com/learn-english-usa",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    phase = json.loads((tmp_path / "report.json").read_text())["phases"]["generate_english"]
    assert "cost_gate" in phase
    assert "cache_plan" in phase
    assert phase["cost_gate"]["mode"] == "batch"


# ---- Batch persistence + cancel + caching live path (faked SDK) ----


def _install_fake_genai(monkeypatch, client_cls):
    fake_genai = SimpleNamespace(Client=client_cls)
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")


def test_submit_batch_persists_last_batch_and_caches(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LAST_BATCH_FILE", tmp_path / "last.json")
    monkeypatch.setattr("tools.core.gemini.config.LAST_BATCH_FILE", tmp_path / "last.json")  # Plan A: client reads core
    state = {"caches": [], "deleted": [], "src": None, "model": None}

    class _Caches:
        def create(self, model, config):
            name = f"cachedContents/{len(state['caches'])}"
            state["caches"].append(model)
            return SimpleNamespace(name=name)

        def delete(self, name):
            state["deleted"].append(name)

    class _Batches:
        def create(self, model, src, config):
            state["src"], state["model"] = src, model
            return SimpleNamespace(name="batches/xyz")

    class _Client:
        def __init__(self, *a, **k):
            self.caches, self.batches = _Caches(), _Batches()

    _install_fake_genai(monkeypatch, _Client)

    big = [{"type": "text", "text": "x" * 30000}]
    reqs = [
        batch_runner.BatchRequest(custom_id="a", system_blocks=big, user_message="u1", model=config.MODEL_ID),
        batch_runner.BatchRequest(custom_id="b", system_blocks=big, user_message="u2", model=config.MODEL_ID),
    ]
    handle = batch_runner.submit_batch(reqs)

    assert handle.batch_id == "batches/xyz"
    assert state["model"] == config.MODEL_ID
    # one cache created for the shared prefix; referenced by every request; system_instruction omitted
    assert len(state["caches"]) == 1
    assert handle.cache_names == ["cachedContents/0"]
    for item in state["src"]:
        assert item["config"]["cached_content"] == "cachedContents/0"
        assert "system_instruction" not in item["config"]
    # submit does NOT delete caches (wait_for_batch does, after the batch completes)
    assert state["deleted"] == []
    # last-batch persisted for recovery
    last = json.loads((tmp_path / "last.json").read_text())
    assert last["batch_id"] == "batches/xyz"
    assert last["custom_ids"] == ["a", "b"]


def test_submit_batch_falls_back_to_uncached_on_rejection(monkeypatch, tmp_path):
    """Fallback-safety: if the cached submit is rejected, rebuild + submit uncached."""
    monkeypatch.setattr(config, "LAST_BATCH_FILE", tmp_path / "last.json")
    monkeypatch.setattr("tools.core.gemini.config.LAST_BATCH_FILE", tmp_path / "last.json")  # Plan A: client reads core
    state = {"create_calls": 0, "deleted": []}

    class _Caches:
        def create(self, model, config):
            return SimpleNamespace(name="cachedContents/0")

        def delete(self, name):
            state["deleted"].append(name)

    class _Batches:
        def create(self, model, src, config):
            state["create_calls"] += 1
            if any(item["config"].get("cached_content") for item in src):
                raise RuntimeError("400 cached_content unsupported in batch")  # permanent
            return SimpleNamespace(name="batches/uncached")

    class _Client:
        def __init__(self, *a, **k):
            self.caches, self.batches = _Caches(), _Batches()

    _install_fake_genai(monkeypatch, _Client)

    big = [{"type": "text", "text": "x" * 30000}]
    reqs = [
        batch_runner.BatchRequest(custom_id="a", system_blocks=big, user_message="u1"),
        batch_runner.BatchRequest(custom_id="b", system_blocks=big, user_message="u2"),
    ]
    handle = batch_runner.submit_batch(reqs)
    assert handle.batch_id == "batches/uncached"
    assert state["create_calls"] == 2  # cached attempt (rejected) + uncached fallback
    assert handle.cache_names == []  # caching disabled after fallback
    assert state["deleted"] == ["cachedContents/0"]  # orphaned cache cleaned up


def test_cancel_batch_calls_sdk_and_returns_state(monkeypatch):
    calls = {}

    class _Batches:
        def cancel(self, name):
            calls["cancelled"] = name

        def get(self, name):
            return SimpleNamespace(state=SimpleNamespace(name="JOB_STATE_CANCELLED"))

    class _Client:
        def __init__(self, *a, **k):
            self.batches = _Batches()

    _install_fake_genai(monkeypatch, _Client)
    state = batch_runner.cancel_batch("batches/abc")
    assert calls["cancelled"] == "batches/abc"
    assert state == "JOB_STATE_CANCELLED"


def test_cli_cancel_batch_uses_persisted_id(monkeypatch, tmp_path):
    """`cancel-batch` with no --batch-id falls back to config.LAST_BATCH_FILE."""
    monkeypatch.setattr(config, "LAST_BATCH_FILE", tmp_path / "last.json")
    (tmp_path / "last.json").write_text(json.dumps({"batch_id": "batches/persisted"}), encoding="utf-8")
    seen = {}
    monkeypatch.setattr(batch_runner, "cancel_batch", lambda bid, **kw: seen.setdefault("id", bid) or "JOB_STATE_CANCELLED")

    rc = cli.main(["cancel-batch", "--out-dir", str(tmp_path / "o")])
    assert rc == 0
    assert seen["id"] == "batches/persisted"


def test_cli_cancel_batch_clears_matching_persisted_pointer(monkeypatch, tmp_path):
    """After cancelling the persisted batch, last-batch.json is removed so a later
    cancel/retrieve can't re-target the dead id (review 100, finding 2)."""
    monkeypatch.setattr(config, "LAST_BATCH_FILE", tmp_path / "last.json")
    (tmp_path / "last.json").write_text(json.dumps({"batch_id": "batches/persisted"}), encoding="utf-8")
    monkeypatch.setattr(batch_runner, "cancel_batch", lambda bid, **kw: "JOB_STATE_CANCELLED")

    rc = cli.main(["cancel-batch", "--out-dir", str(tmp_path / "o")])
    assert rc == 0
    assert not (tmp_path / "last.json").exists()


def test_cli_cancel_batch_keeps_pointer_for_different_id(monkeypatch, tmp_path):
    """Cancelling a DIFFERENT batch via --batch-id must not drop the pointer to the
    actual last batch (review 100, finding 2 — match-only clear)."""
    monkeypatch.setattr(config, "LAST_BATCH_FILE", tmp_path / "last.json")
    (tmp_path / "last.json").write_text(json.dumps({"batch_id": "batches/the-real-last"}), encoding="utf-8")
    monkeypatch.setattr(batch_runner, "cancel_batch", lambda bid, **kw: "JOB_STATE_CANCELLED")

    rc = cli.main(["cancel-batch", "--batch-id", "batches/some-other", "--out-dir", str(tmp_path / "o")])
    assert rc == 0
    assert (tmp_path / "last.json").exists()


def test_cost_estimate_accounts_for_pro_thinking_output():
    """C1 (2026-05-23): Gemini bills thinking AS output, so a Pro request WITH thinking
    must project materially higher than the same request without thinking (the old flat
    800-token assumption under-projected Pro ~6x — the ~806 TRY burst RC). Same input,
    same rate tier; only the output allowance differs by (family, thinking)."""
    sys_blocks = [{"type": "text", "text": "system " * 1500}]
    pro_think = batch_runner.BatchRequest(
        custom_id="a", system_blocks=sys_blocks, user_message="u " * 200,
        model="gemini-3.1-pro-preview", enable_thinking=True,
    )
    pro_nothink = batch_runner.BatchRequest(
        custom_id="b", system_blocks=sys_blocks, user_message="u " * 200,
        model="gemini-3.1-pro-preview", enable_thinking=False,
    )
    cost_think = batch_runner.estimate_batch_cost_usd([pro_think], mode="batch")
    cost_nothink = batch_runner.estimate_batch_cost_usd([pro_nothink], mode="batch")
    # Thinking output (5500 tok) dominates vs no-think (1000 tok) on the same input.
    assert cost_think > cost_nothink * 1.5, (cost_think, cost_nothink)
    # And the allowance is wired off config (not a hard-coded 800).
    assert config.OUTPUT_TOKEN_ESTIMATE[("pro", True)] > config.OUTPUT_TOKEN_ESTIMATE[("pro", False)]
