"""Self-test of the harness plumbing RE 5 needs: respond(), clipboard context, upload, download."""
from __future__ import annotations

import json
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from localize_desk import harness as H  # noqa: E402

PROBE = """<!doctype html><title>probe</title>
<input type=file id=f><pre id=out></pre><button id=dl>dl</button><button id=cp>cp</button>
<script>
document.getElementById('f').addEventListener('change', async e => {
  const text = await e.target.files[0].text();
  const r = await fetch('/__worker', {method: 'POST', body: JSON.stringify({action: 'desk-rules-import-read', text})});
  document.getElementById('out').textContent = r.status + ' ' + JSON.stringify(await r.json());
});
document.getElementById('dl').onclick = () => {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['rules body\\n'], {type: 'text/markdown'}));
  a.download = 'rules-de.md'; document.body.appendChild(a); a.click(); a.remove();
};
document.getElementById('cp').onclick = () => navigator.clipboard.writeText('copied text');
</script>"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@contextmanager
def probe(browser):
    root = H.stage_copy(save_on=True)
    worker = H.MockWorker(root)
    server = H.make_server(root, worker, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with H.page_with_clipboard(browser) as pg:
            pg.route("**/probe.html", lambda r: r.fulfill(status=200, content_type="text/html", body=PROBE))
            pg.goto(f"http://127.0.0.1:{server.server_address[1]}/probe.html")
            yield pg, worker
    finally:
        server.shutdown()
        server.server_close()


def shown(pg, status: str) -> tuple[int, dict]:
    pg.wait_for_function("s => document.getElementById('out').textContent.startsWith(s)", arg=status)
    code, _, body = pg.inner_text("#out").partition(" ")
    return int(code), json.loads(body)


def test_respond_returns_the_chosen_body_and_status_for_a_named_action(browser):
    with probe(browser) as (pg, worker):
        worker.respond("desk-rules-import-read", lambda b: {"ok": True, "changes": [], "echo": b["text"]})
        H.upload(pg, "#f", "rules.md", "hello")
        assert shown(pg, "200") == (200, {"ok": True, "changes": [], "echo": "hello"})
        assert worker.calls == ["desk-rules-import-read"]
        worker.respond("desk-rules-import-read", {"ok": False, "error": "too big"}, status=413)
        H.upload(pg, "#f", "rules2.md", "x")
        assert shown(pg, "413") == (413, {"ok": False, "error": "too big"})


def test_respond_refuses_an_unknown_action_and_an_unset_action_is_the_stand_ins(browser):
    with probe(browser) as (pg, worker):
        with pytest.raises(ValueError):
            worker.respond("desk-nope", {})
        # Nothing chosen yet: the stand-in's own answer (the Worker's shapes), here a refusal of an empty request.
        assert worker.handle({"action": "desk-rules-import-apply"}) == (400, {"ok": False, "error": "invalid: send 1 to 500 changes"})
        worker.respond("desk-rules-import-apply", {"ok": True})
        assert worker.handle({"action": "desk-rules-import-apply"}) == (200, {"ok": True})
        # ... and the stand-in reads with its fake reader: nothing found, until a test sets import_answer.
        worker.responses.clear()
        code, out = worker.handle({"action": "desk-rules-import-read", "text": "hello", "languages": ["de"]})
        assert code == 200 and out["changes"] == [] and out["problems"] == [] and out["unplaced"] == []


def test_clipboard_context_can_write_and_read(browser):
    with probe(browser) as (pg, worker):
        pg.click("#cp")
        pg.wait_for_function("navigator.clipboard.readText().then(t => t === 'copied text')")
        assert pg.evaluate("navigator.clipboard.readText()") == "copied text"


def test_download_text_returns_name_and_text(browser):
    with probe(browser) as (pg, worker):
        name, text = H.download_text(pg, lambda: pg.click("#dl"))
        assert (name, text) == ("rules-de.md", "rules body\n")
