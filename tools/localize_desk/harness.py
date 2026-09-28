"""Click-test the Localization Desk locally, with sign-in and the storage simulated.

    cd tools && python3 -m localize_desk.harness                 # http://127.0.0.1:8765/admin/localization/
    cd tools && python3 -m localize_desk.harness --save-on       # the desk with saving switched on

Why this exists: the desk's first three audits never loaded the page (the admin area is
behind sign-in, and the sign-in service only answers cel.englishcollege.com), and every
defect a real click found on 2026-09-23 had survived them -- a 5,012px table on a tablet,
English text reversed in the Arabic column, a Save that said "Not saved" after saving. A
desk change is not done until it has been clicked through here (process doc §9).

It serves a TEMPORARY COPY of docs/ -- the real files are never written -- with:
  * auth.js replaced by a stub that signs you in as a test reviewer;
  * dashboard-config.js pointing the desk at this server's mock Worker;
  * the Worker's desk storage actions (desk-read / desk-write / desk-history / desk-summary), answered by
    `desk_store.DeskStore` -- held to the real Worker by the monorepo's differential test
    (runbook WO-33) -- over the same page map deploy.sh loads.

--save-on serves the copy with SAVE_OFF switched off, so the save path (runbook WO-17) can
be clicked through before the storage is deployed; the committed pages keep it off.
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

from localize_desk.desk_store import DeskStore  # noqa: E402

REPO_DOCS = Path(__file__).resolve().parents[2] / "docs"
UNITS_DIR = Path(__file__).resolve().parents[2] / "data" / "localize" / "units"
REVIEWER = "reviewer@example.test"

AUTH_STUB = (b"window.__CEL_USER__={firstName:'Test',lastName:'Reviewer',"
             b"email:'reviewer@example.test'};"
             b"document.cookie='cel_session=h.eyJzdWIiOiJyZXZpZXdlckBleGFtcGxlLnRlc3QifQ.s; Path=/';")
CONFIG_STUB = b"window.CEL_DISPATCH_URL = '/__worker';"
SAVE_OFF_LINE = "var SAVE_OFF = true;"


class MockWorker:
    """The sign-in Worker's answers the desk needs, in memory."""

    def __init__(self, root: Path | None = None):
        self.root = root
        self.lock = threading.Lock()
        # Slow or failing files, for the races the desk must survive (review round 2):
        # {"<part of the path>": {"delay": seconds, "status": 503}}. Tests set it live.
        self.faults: dict[str, dict] = {}
        # A failing storage, for the save path's failures (WO-17): {"status": 429,
        # "error": "over the cap"} answers every desk-write that way; None = working.
        # {"drop": True} applies the write and then loses the answer (a timeout, WO-18);
        # {"status": 502, "apply": True} applies it and then answers with that error (a gateway
        # failing after the write landed); {"status": 200, "empty": True} answers with no body;
        # {"delay": seconds} holds the answer back (a slow storage), then answers normally.
        self.desk_fault: dict | None = None
        # The same for any other storage action, by name: {"desk-summary": {"status": 503}}.
        self.action_faults: dict[str, dict] = {}
        # Every action the desk asked for, in order -- what a test checks was never sent.
        self.calls: list[str] = []
        # desk-write requests being answered right now, and the most there ever were at once:
        # autosave sends one at a time, across every tab of a browser (runbook WO-18).
        self.inflight = 0
        self.max_inflight = 0
        # The desk storage (WO-16's actions), as the deployed Worker will answer them.
        self.store = DeskStore.from_units_dir(UNITS_DIR)

    def handle(self, body: dict) -> tuple[int, dict]:
        action = body.get("action")
        with self.lock:
            self.calls.append(str(action))
        if action == "validate":
            return 200, {"ok": True, "user": {"firstName": "Test", "email": REVIEWER}}
        if action == "changepw":
            # The shell's change-password dialog; the harness has no password to check.
            return 200, {"ok": True}
        if action == "desk-write":
            with self.lock:
                self.inflight += 1
                self.max_inflight = max(self.max_inflight, self.inflight)
            try:
                return self._desk(action, body)
            finally:
                with self.lock:
                    self.inflight -= 1
        if action in ("desk-read", "desk-history", "desk-summary"):
            return self._desk(action, body)
        return 400, {"error": "invalid action"}

    def _desk(self, action: str, body: dict) -> tuple[int, dict]:
        """The storage's answer to one desk action, through whatever fault a test has set."""
        fault = self.desk_fault if action == "desk-write" else self.action_faults.get(action)
        if fault and fault.get("delay"):
            time.sleep(float(fault["delay"]))
        if fault and (fault.get("drop") or fault.get("apply")):
            self.store.handle(action, body, REVIEWER)
        if fault and fault.get("drop"):
            return 0, {}
        if fault and fault.get("empty"):
            return int(fault.get("status", 200)), None
        if fault and "status" in fault:
            return int(fault["status"]), {"ok": False, "error": fault.get("error", "server error")}
        # The harness signs everyone in as the test reviewer.
        return self.store.handle(action, body, REVIEWER)


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
            if code == 0:                  # the answer is lost on the way back: no response at all
                self.close_connection = True
                return None
            if out is None:                # an answer with nothing in it
                return self._send(code, b"", "text/plain")
            return self._send(code, json.dumps(out).encode())

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def stage_copy(docs: Path = REPO_DOCS, save_on: bool = False) -> Path:
    """A throwaway copy of the files the desk needs; nothing is written to docs/.

    `save_on` switches the copy's SAVE_OFF off, so the save path can be exercised here
    before the storage is deployed (WO-17). A page without the line is left alone.
    """
    root = Path(tempfile.mkdtemp(prefix="desk-harness-"))
    # The whole admin area, so the dashboard's navigation leads somewhere (review round
    # 2 found all nine nav links 404ing here) -- minus the bulk import files it never shows.
    shutil.copytree(docs / "admin", root / "admin",
                    ignore=shutil.ignore_patterns("*.csv", "*.zip", "*.bak", "*.poisoned.bak"))
    shutil.copytree(docs / "assets", root / "assets")
    if save_on:
        for page in (root / "admin" / "localization").rglob("index.html"):
            text = page.read_text(encoding="utf-8")
            if SAVE_OFF_LINE in text:
                page.write_text(text.replace(SAVE_OFF_LINE, "var SAVE_OFF = false;"), encoding="utf-8")
    return root


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--save-on", action="store_true",
                    help="serve the desk with saving switched on (the storage is simulated)")
    args = ap.parse_args(argv)
    if not (REPO_DOCS / "admin" / "localization" / "index.html").is_file():
        print("ERROR: no generated desk in docs/admin/localization -- run "
              "`python3 -m localize_desk.generate_desk_page` first", file=sys.stderr)
        return 2
    root = stage_copy(save_on=args.save_on)
    server = make_server(root, MockWorker(root), args.port)
    print(f"Desk harness ({'saving on' if args.save_on else 'saving off, as live'}) on "
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
