"""Click-test the Localization Desk locally, with sign-in and saving simulated.

    cd tools && python3 -m localize_desk.harness            # http://127.0.0.1:8765/admin/localization/
    cd tools && python3 -m localize_desk.harness --worker old --port 8766

Why this exists: the desk's first three audits never loaded the page (the admin area is
behind sign-in, and the sign-in service only answers cel.englishcollege.com), and every
defect a real click found on 2026-09-23 had survived them -- a 5,012px table on a tablet,
English text reversed in the Arabic column, a Save that said "Not saved" after saving. A
desk change is not done until it has been clicked through here (process doc §9).

It serves a TEMPORARY COPY of docs/ -- the real files are never written -- with:
  * auth.js replaced by a stub that signs you in as a test reviewer;
  * dashboard-config.js pointing the desk at this server's mock dispatch Worker;
  * a mock Worker (validate / dispatch / poll) and a mock GitHub run that applies the
    save with the real `save_decisions.apply`, into the temporary copy;
  * the Worker's desk storage actions (desk-read / desk-write / desk-history), answered by
    `desk_store.DeskStore` -- held to the real Worker by the monorepo's differential test
    (runbook WO-33) -- over the same page map deploy.sh loads.

--worker picks what the mock Worker does, to exercise the desk's failure handling:
  new   dispatch returns the run id and poll-by-id works (the deployed Worker since 2026-09-23)
  old   poll answers WITHOUT run ids (the Worker before 2026-09-23): Save must refuse
  race  another reviewer's run succeeds while ours is cancelled: Save must say "Not saved"
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from localize_desk import save_decisions  # noqa: E402
from localize_desk.desk_store import DeskStore  # noqa: E402

REPO_DOCS = Path(__file__).resolve().parents[2] / "docs"
UNITS_DIR = Path(__file__).resolve().parents[2] / "data" / "localize" / "units"
MODES = ("new", "old", "race")

AUTH_STUB = (b"window.__CEL_USER__={firstName:'Test',lastName:'Reviewer',"
             b"email:'reviewer@example.test'};"
             b"document.cookie='cel_session=h.eyJzdWIiOiJyZXZpZXdlckBleGFtcGxlLnRlc3QifQ.s; Path=/';")
CONFIG_STUB = b"window.CEL_DISPATCH_URL = '/__worker';"


class MockWorker:
    """The dispatch Worker and a GitHub run queue, in memory."""

    def __init__(self, root: Path, mode: str = "new", run_seconds: float = 2.0,
                 history: bool = True):
        self.out = root / "admin" / "localization"
        self.mode = mode
        self.run_seconds = run_seconds
        # A live workflow on GitHub always has earlier runs, and the desk's refusal of a
        # Worker that cannot name runs depends on seeing one (runbook R67). `history=False`
        # models a workflow that has never run -- the one case that refusal misses.
        self.runs: list[dict] = ([{"id": 999, "status": "completed", "conclusion": "success",
                                   "inputs": {}}] if history else [])
        self._next_id = 1000
        self.lock = threading.Lock()
        # Slow or failing files, for the races the desk must survive (review round 2):
        # {"<part of the path>": {"delay": seconds, "status": 503}}. Tests set it live.
        self.faults: dict[str, dict] = {}
        # The desk storage (WO-16's actions), as the deployed Worker will answer them.
        self.store = DeskStore.from_units_dir(UNITS_DIR)

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id - 1

    @property
    def dispatched(self) -> list[dict]:
        """The runs a dispatch created (the seeded history excluded)."""
        return [r for r in self.runs if r["id"] >= 1000]

    def _run(self, run: dict) -> None:
        time.sleep(self.run_seconds / 2)
        with self.lock:
            run["status"] = "in_progress"
        time.sleep(self.run_seconds / 2)
        if run.get("cancel"):
            with self.lock:
                run["status"], run["conclusion"] = "completed", "cancelled"
            return
        try:
            save_decisions.apply(run["inputs"]["locale"], run["inputs"]["payload"], self.out)
            conclusion = "success"
        except Exception:  # noqa: BLE001 -- a failed save is a "failure" run, as on GitHub
            conclusion = "failure"
        with self.lock:
            run["status"], run["conclusion"] = "completed", conclusion

    def handle(self, body: dict) -> tuple[int, dict]:
        action = body.get("action")
        if action == "validate":
            return 200, {"ok": True, "user": {"firstName": "Test", "email": "reviewer@example.test"}}
        if action == "dispatch":
            payload = (body.get("inputs") or {}).get("payload", "")
            if len(payload) > 64000:
                return 400, {"ok": False, "error": "invalid input: payload has a disallowed value"}
            with self.lock:
                run = {"id": self._new_id(), "status": "queued", "conclusion": None,
                       "inputs": body.get("inputs") or {}, "cancel": self.mode == "race"}
                self.runs.append(run)
                if self.mode == "race":   # a colleague's run lands, and succeeds, right after ours
                    self.runs.append({"id": self._new_id(), "status": "completed",
                                      "conclusion": "success", "inputs": {}})
            threading.Thread(target=self._run, args=(run,), daemon=True).start()
            if self.mode == "old":
                return 200, {"ok": True}
            return 200, {"ok": True, "run_id": run["id"]}
        if action == "poll":
            with self.lock:
                if body.get("run_id") is not None and self.mode != "old":
                    run = next((r for r in self.runs if r["id"] == int(body["run_id"])), None)
                else:
                    run = self.runs[-1] if self.runs else None
                if run is None:
                    return 200, {"ok": True, "run": None}
                out = {"status": run["status"], "conclusion": run["conclusion"]}
                if self.mode != "old":
                    out["id"] = run["id"]
            return 200, {"ok": True, "run": out}
        if action == "changepw":
            # The shell's change-password dialog; the harness has no password to check.
            return 200, {"ok": True}
        if action in ("desk-read", "desk-write", "desk-history"):
            # The harness signs everyone in as the test reviewer.
            return self.store.handle(action, body, "reviewer@example.test")
        return 400, {"error": "invalid action"}


def make_server(root: Path, worker: MockWorker, port: int) -> ThreadingHTTPServer:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def log_message(self, *a):
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            for part, fault in list(worker.faults.items()):
                if part in self.path:
                    if fault.get("delay"):
                        time.sleep(fault["delay"])
                    if fault.get("status"):
                        return self._send(int(fault["status"]), b"{}")
            if self.path.startswith("/assets/js/auth.js"):
                return self._send(200, AUTH_STUB, "application/javascript")
            if self.path.startswith("/assets/js/dashboard-config.js"):
                return self._send(200, CONFIG_STUB, "application/javascript")
            return super().do_GET()

        def do_POST(self):
            if not self.path.startswith("/__worker"):
                return self._send(404, b"{}")
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            code, out = worker.handle(body)
            return self._send(code, json.dumps(out).encode())

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def stage_copy(docs: Path = REPO_DOCS) -> Path:
    """A throwaway copy of the files the desk needs; saves land here, never in docs/."""
    root = Path(tempfile.mkdtemp(prefix="desk-harness-"))
    # The whole admin area, so the dashboard's navigation leads somewhere (review round
    # 2 found all nine nav links 404ing here) -- minus the bulk import files it never shows.
    shutil.copytree(docs / "admin", root / "admin",
                    ignore=shutil.ignore_patterns("*.csv", "*.zip", "*.bak", "*.poisoned.bak"))
    shutil.copytree(docs / "assets", root / "assets")
    return root


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--worker", choices=MODES, default="new")
    args = ap.parse_args(argv)
    if not (REPO_DOCS / "admin" / "localization" / "index.html").is_file():
        print("ERROR: no generated desk in docs/admin/localization -- run "
              "`python3 -m localize_desk.generate_desk_page` first", file=sys.stderr)
        return 2
    root = stage_copy()
    server = make_server(root, MockWorker(root, args.worker), args.port)
    print(f"Desk harness (mock Worker: {args.worker}) on "
          f"http://127.0.0.1:{args.port}/admin/localization/  -- copy in {root}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
