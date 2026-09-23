"""The click-test harness behaves like the real Worker in each of its three modes.

If the harness drifts from the Worker it stands in for, a desk change can pass a
click-test here and still fail for the reviewer -- the same "passes locally, breaks in
production" gap that let the sign-in crash through on 2026-09-23.
"""
from __future__ import annotations

import base64
import gzip
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from localize_desk import harness as H  # noqa: E402


def _payload(locale="de", decisions=None) -> str:
    doc = {"schema": "cel-localization-desk/1", "locale": locale,
           "decisions": decisions or {"u1": {"tray": "csv"}}}
    return base64.b64encode(gzip.compress(json.dumps(doc).encode())).decode()


def _wait(worker, run_id, seconds=3.0):
    end = time.time() + seconds
    while time.time() < end:
        code, out = worker.handle({"action": "poll", "run_id": run_id})
        if out["run"] and out["run"]["status"] == "completed":
            return out["run"]
        time.sleep(0.02)
    raise AssertionError("run never completed")


def test_new_worker_names_the_run_and_the_save_lands(tmp_path):
    (tmp_path / "admin" / "localization" / "de").mkdir(parents=True)
    w = H.MockWorker(tmp_path, "new", run_seconds=0.05)
    code, out = w.handle({"action": "dispatch", "inputs": {"locale": "de", "payload": _payload()}})
    assert code == 200 and out["run_id"] == 1000
    assert _wait(w, 1000)["conclusion"] == "success"
    saved = json.loads((tmp_path / "admin" / "localization" / "de" / "decisions.json").read_text())
    assert saved["decisions"] == {"u1": {"tray": "csv"}}


def test_old_worker_cannot_name_runs(tmp_path):
    w = H.MockWorker(tmp_path, "old", run_seconds=0.05)
    code, out = w.handle({"action": "dispatch", "inputs": {"locale": "de", "payload": _payload()}})
    assert "run_id" not in out
    assert "id" not in w.handle({"action": "poll"})[1]["run"]


def test_race_cancels_ours_while_a_colleagues_run_succeeds(tmp_path):
    w = H.MockWorker(tmp_path, "race", run_seconds=0.05)
    _, out = w.handle({"action": "dispatch", "inputs": {"locale": "de", "payload": _payload()}})
    assert _wait(w, out["run_id"])["conclusion"] == "cancelled"
    newest = w.handle({"action": "poll"})[1]["run"]
    assert newest["id"] != out["run_id"] and newest["conclusion"] == "success"


def test_the_payload_cap_matches_the_real_worker(tmp_path):
    w = H.MockWorker(tmp_path, "new")
    code, _ = w.handle({"action": "dispatch", "inputs": {"locale": "de", "payload": "A" * 64001}})
    assert code == 400


def test_it_serves_the_stubs_and_never_touches_the_real_docs(tmp_path):
    docs = tmp_path / "docs"
    (docs / "admin" / "localization").mkdir(parents=True)
    (docs / "admin" / "localization" / "index.html").write_text("<p>desk</p>")
    (docs / "assets" / "js").mkdir(parents=True)
    root = H.stage_copy(docs)
    assert root != docs and (root / "admin" / "localization" / "index.html").is_file()
    server = H.make_server(root, H.MockWorker(root), 0)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        auth = urllib.request.urlopen(f"http://127.0.0.1:{port}/assets/js/auth.js").read()
        cfg = urllib.request.urlopen(f"http://127.0.0.1:{port}/assets/js/dashboard-config.js").read()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/__worker",
                                     data=json.dumps({"action": "validate"}).encode(),
                                     headers={"Content-Type": "application/json"})
        ok = json.loads(urllib.request.urlopen(req).read())
    finally:
        server.shutdown()
        server.server_close()
    assert b"__CEL_USER__" in auth and b"/__worker" in cfg and ok["ok"] is True
    assert not (docs / "admin" / "localization" / "de").exists()   # nothing written back
