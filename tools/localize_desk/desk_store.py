"""The sign-in Worker's desk storage actions, in memory -- the click-test harness's stand-in.

The desk (runbook WO-17) will save through the Worker's `desk-read` / `desk-write` /
`desk-history` actions, which keep decisions in Cloudflare D1. The Worker's code lives in
the private monorepo; the harness that clicks through the desk lives here. This module
answers the three actions the way the Worker does, so the desk can be built and
browser-tested against it before the storage is deployed.

It is not a second implementation to trust. The monorepo's differential test
(`scripts/tests/test_desk_standin_parity.py`) sends the same requests to this and to the
real Worker -- node, with D1's SQL run on SQLite -- and requires the same answers, status
and body, for every rule: versions and conflicts, the page map, the smoke's scope, the
client handshake, the record's shape, the size limit, history. Change the Worker and this
together, or that test fails (monorepo runbook WO-33, decision (b)).

desk-read also carries the engine's findings (schema v2, WO-36; `seed_findings` puts them in).
`desk-summary` (runbook WO-18) is the index's: each language's decisions as the shapes the
desk's stageOf() reads, with their counts, and the shape of each flagged text it names.

The desk's jobs (runbook U1): `desk-job-start` records a job the way the Worker does, and
"dispatches" it by adding its id to `dispatched` -- no engine runs here. The harness plays the
engine with `finish_job` and `seed_export` (the rows the engine writes through /engine-query);
`dispatch_status` stands for GitHub's answer (204 took it; anything else, the Worker fails the
job at once); `engine_configured` False stands for a Worker with no GitHub credential or no
ENGINE_SECRET (503). A user's starts are capped per day as the Worker caps them (JOB_DAILY).
`desk-job-get` and `desk-export-get` read them back.

What it leaves out: the session check (the harness signs everyone in), the signature's
value (it is never returned), and the per-user cap (it needs thousands of requests; the
Worker's own tests hold it).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

API = 1
MIN_CLIENT = 1
REAL_LOCALES = ("de", "fr", "es", "pt", "it", "ja", "ko", "ar")     # the Worker's order
LOCALES = frozenset({*REAL_LOCALES, "zz"})
SMOKE_LOCALE, SMOKE_PAGE, SMOKE_UNIT = "zz", "_smoke", "0000000000000000"
MAX_CHANGES = 200
MAX_TEXT = 8000
MAX_BYTES = 1_900_000
MAX_FLAGGED = 8000
# The Worker's per-user cap (DESK_CAP), which this stand-in does not enforce (see above). The
# desk's own ceiling is held to it (runbook WO-18), and these to the Worker by the parity test.
CAP_CHANGES, CAP_WINDOW_SEC = 2000, 600
# Used with fullmatch(), never match(): Python's `$` also matches before a final newline,
# JavaScript's does not -- so "<id>\n" passed here and was refused by the Worker (parity test).
UNIT = re.compile(r"[0-9a-f]{16}")
PAGE = re.compile(r"[a-z0-9_-]{1,80}")
# The Worker's jobs (runbook U1): the kinds, the one-run cap on a submit's amount, and how long
# an open job may go unanswered before the sweep fails it.
JOB_KINDS = ("export", "verify", "plan", "submit", "collect")
JOB_RUN_CAP_USD = 40
JOB_STALE_SEC = 35 * 60
JOB_DAILY = 30                  # starts a day per user, a refused one too (each is a billed run)
JOB_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}")       # verify's batch, collect's run: the runner's rule
JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,63}")
BATCH_ID = JOB_REF


class Invalid(ValueError):
    """A write the Worker refuses as `invalid: <reason>`."""


def _js_len(s: str) -> int:
    """String length as JavaScript counts it: UTF-16 code units -- counted, not encoded, so a
    lone surrogate (which the length check meets before the well-formed check) is one unit."""
    return sum(2 if ord(ch) > 0xFFFF else 1 for ch in s)


def _well_formed(s: str) -> bool:
    """String.prototype.isWellFormed: no lone surrogate."""
    return not any(0xD800 <= ord(ch) <= 0xDFFF for ch in s)


def _safe_int(x) -> bool:
    """Number.isSafeInteger: JSON's 1.0 is JavaScript's 1; true is not a number."""
    return (isinstance(x, (int, float)) and not isinstance(x, bool) and float(x).is_integer()
            and abs(x) <= 2 ** 53 - 1)


def _js_str(v) -> str:
    """String(v || ''): a missing, empty, zero or false value is ''."""
    if v is None or v is False or v == "" or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0):
        return ""
    if v is True:
        return "true"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return v if isinstance(v, str) else json.dumps(v)


def _dumps(value) -> str:
    """JSON.stringify for the shapes this module sends: no spaces, non-ASCII as is."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _iso(t: datetime) -> str:
    """Date.prototype.toISOString(): milliseconds, Z."""
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def _job_out(r: dict | None) -> dict | None:
    """The Worker's jobOut(): the row in the desk's names, each optional field only when set."""
    if r is None:
        return None
    out = {"id": r["id"], "kind": r["kind"], "locale": r["locale"], "status": r["status"]}
    if r.get("amount_usd") is not None:
        out["amountUsd"] = r["amount_usd"]
    if r.get("ref"):
        out["ref"] = r["ref"]
    out["requestedBy"] = r["requested_by"]
    out["createdAt"] = r["created_at"]
    for k, name in (("started_at", "startedAt"), ("finished_at", "finishedAt")):
        if r.get(k):
            out[name] = r[k]
    if r.get("result"):
        try:
            out["result"] = json.loads(r["result"])
        except ValueError:
            out["result"] = None
    if r.get("error"):
        out["error"] = r["error"]
    return out


def record_of(raw) -> dict:
    """The Worker's deskRecord(): only the reviewer's fields, in its order."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise Invalid("record must be an object or null")
    out: dict = {}
    if raw.get("tray") is not None:
        if raw["tray"] not in ("csv", "draft"):
            raise Invalid("tray must be csv or draft")
        out["tray"] = raw["tray"]
    for k in ("text", "approvedAgainst"):
        v = raw.get(k)
        if v is None:
            continue
        if not isinstance(v, str):
            raise Invalid(f"{k} must be a string")
        if _js_len(v) > MAX_TEXT:
            raise Invalid(f"{k} is over {MAX_TEXT} characters")
        if not _well_formed(v):
            raise Invalid(f"{k} is not valid text")
        out[k] = v
    rej = raw.get("rejected")
    if rej is not None:
        if not isinstance(rej, list) or not all(isinstance(r, str) and _well_formed(r) for r in rej):
            raise Invalid("rejected must be a list of strings")
        out["rejected"] = ["".join(list(r)[:MAX_TEXT]) for r in rej[-5:]]
    return out


def _shape(tray, edited: bool) -> dict:
    """The Worker's deskShape(): what stageOf() reads of a decision, and nothing else."""
    out: dict = {}
    if tray:
        out["tray"] = tray
    if edited:
        out["text"] = True
    return out


def sig_input(locale: str, unit: str, record: dict, by: str, at: str) -> str:
    """The Worker's deskSigInput -- byte for byte (data/localize/desk-signature-vectors.json)."""
    return _dumps(["desk-approval/v1", locale, unit, record.get("tray") or "", record.get("text") or "",
                   record.get("approvedAgainst") or "", by, at])


class DeskStore:
    """desk-read / desk-write / desk-history over in-memory tables shaped like schema.sql's."""

    def __init__(self, page_map: dict[str, set[str]] | None = None, signing_key: str = "harness-key"):
        self.units: set[tuple[str, str]] = {(SMOKE_UNIT, SMOKE_PAGE)}
        for unit, pages in (page_map or {}).items():
            self.units.update((unit, p) for p in pages)
        self.key = signing_key.encode()
        self.decisions: dict[tuple[str, str], dict] = {}
        self.history: list[dict] = []
        self.pipeline: dict[tuple[str, str], dict] = {}
        self.drafts: dict[tuple[str, str], dict] = {}
        # schema v2 (WO-36): the engine's findings, (locale, unit, subject, rule) -> the row.
        self.findings: dict[tuple[str, str, str, str], dict] = {}
        # schema v3 (U1): the desk's jobs, and the import files the engine made.
        self.jobs: dict[str, dict] = {}
        self.exports: dict[str, dict] = {}
        self.dispatched: list[str] = []
        self.dispatch_status = 204
        self.engine_configured = True
        self.job_starts: list[tuple[str, float]] = []      # (who, when): the Worker's attempts rows
        self.lock = threading.Lock()

    @classmethod
    def from_units_dir(cls, units_dir: Path, **kw) -> "DeskStore":
        """The page map deploy.sh loads (d1-sql.mjs): every text of every manifest page."""
        pages: dict[str, set[str]] = {}
        for f in sorted(units_dir.glob("*.json")):
            doc = json.loads(f.read_text(encoding="utf-8"))
            for u in doc["units"]:
                pages.setdefault(u["unit_id"], set()).add(doc["page"])
        return cls(pages, **kw)

    def seed_findings(self, locale: str, rows: list[dict]) -> None:
        """Findings as the engine's refresh writes them (storage.findings_statements' rows):
        what the harness and the parity test put in, since no desk action writes them."""
        with self.lock:
            for r in rows:
                hits = r["hits"] if isinstance(r["hits"], str) else _dumps(list(r["hits"]))
                self.findings[(locale, r["unit_id"], r["subject"], r["rule"])] = {**r, "hits": hits}

    def finish_job(self, locale: str, kind: str, status: str = "done", result=None,
                   error: str | None = None) -> str | None:
        """The engine answering the open job of a language and kind (what its /engine-query
        writes): `running` claims it, `done` / `failed` end it. The job's id, or None."""
        with self.lock:
            open_ = [j for j in self.jobs.values() if j["locale"] == locale and j["kind"] == kind
                     and j["status"] in ("queued", "running")]
            if not open_:
                return None
            j, at = open_[0], _iso(datetime.now(timezone.utc))
            j["status"] = status
            if status == "running":
                j["started_at"] = j.get("started_at") or at
            else:
                j["finished_at"] = at
                j["result"] = None if result is None else _dumps(result)
                j["error"] = error
            return j["id"]

    def seed_export(self, batch_id: str, locale: str, csv: str, rows: int, refused: list,
                    created_at: str | None = None) -> None:
        """An import file as the engine's export job writes it into `exports`."""
        with self.lock:
            self.exports[batch_id] = {"batch_id": batch_id, "locale": locale, "csv": csv, "rows": rows,
                                      "refused": _dumps(refused),
                                      "created_at": created_at or _iso(datetime.now(timezone.utc))}

    # ── the actions ─────────────────────────────────────────────────────────────────
    def handle(self, action: str, body: dict, email: str) -> tuple[int, dict]:
        with self.lock:
            if action == "desk-read":
                return self._read(body)
            if action == "desk-write":
                return self._write(body, email)
            if action == "desk-history":
                return self._history(body)
            if action == "desk-summary":
                return self._summary(body)
            if action == "desk-job-start":
                return self._job_start(body, email)
            if action == "desk-job-get":
                return self._job_get(body)
            if action == "desk-export-get":
                return self._export_get(body)
        return 400, {"error": "invalid action"}

    @staticmethod
    def _locale(body: dict) -> str:
        locale = str(body.get("locale") or "")
        if locale not in LOCALES:
            raise Invalid("unknown language")
        return locale

    def _write(self, body: dict, email: str) -> tuple[int, dict]:
        client = body.get("client")
        if not _safe_int(client):
            return 400, {"ok": False, "error": "invalid: which desk version is writing (client) is missing"}
        if client < MIN_CLIENT:
            return 409, {"ok": False, "error": "desk out of date -- reload the page", "api": API}
        try:
            locale = self._locale(body)
            raw = body.get("changes")
            if not isinstance(raw, list) or not raw:
                raise Invalid("no changes")
            if len(raw) > MAX_CHANGES:
                raise Invalid(f"more than {MAX_CHANGES} changes")
            seen, changes = set(), []
            for c in raw:
                # typeof [] is 'object' in JavaScript: a list passes here and fails as a text id.
                if not isinstance(c, (dict, list)):
                    raise Invalid("a change must be an object")
                c = c if isinstance(c, dict) else {}
                unit, page = _js_str(c.get("unit")), _js_str(c.get("page"))
                if not UNIT.fullmatch(unit):
                    raise Invalid("bad text id")
                if not PAGE.fullmatch(page):
                    raise Invalid("bad page")
                if (locale == SMOKE_LOCALE) != (page == SMOKE_PAGE):
                    raise Invalid("language zz and page _smoke go only together")
                base = c.get("base")
                if not _safe_int(base) or base < 0:
                    raise Invalid("bad base version")
                base = int(base)
                if unit in seen:
                    raise Invalid("the same text twice in one request")
                seen.add(unit)
                changes.append({"unit": unit, "page": page, "base": base, "record": record_of(c.get("record"))})
        except Invalid as e:
            return 400, {"ok": False, "error": f"invalid: {e}"}
        early = len(_dumps([{"unit": c["unit"], "page": c["page"], "base": c["base"],
                             "record": _dumps(c["record"]), "sig": "0" * 64} for c in changes]).encode())
        if early > MAX_BYTES:
            return 400, {"ok": False, "error": f"invalid: the save is too large ({early} bytes) -- send fewer changes at once"}
        now = datetime.now(timezone.utc)
        at = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"   # toISOString()
        req = str(uuid.uuid4())
        refused = [{"unit": c["unit"], "reason": "not on this page"}
                   for c in changes if (c["unit"], c["page"]) not in self.units]
        off = {r["unit"] for r in refused}
        applied, conflicts = [], []
        for c in (c for c in changes if c["unit"] not in off):
            key = (locale, c["unit"])
            cur = self.decisions.get(key)
            ok = (cur is None and c["base"] == 0) or (cur is not None and c["base"] > 0 and cur["version"] == c["base"])
            if ok:
                version = 1 if cur is None else cur["version"] + 1
                sig = hmac.new(self.key, sig_input(locale, c["unit"], c["record"], email, at).encode(),
                               hashlib.sha256).hexdigest()
                row = {"page": c["page"], "record": c["record"], "by": email, "at": at,
                       "version": version, "sig": sig, "req": req}
                self.decisions[key] = row
                self.history.append({"locale": locale, "unit": c["unit"], **row})
                applied.append({"unit": c["unit"], "version": version})
            else:
                conflicts.append({"unit": c["unit"], "current": None if cur is None else {
                    **cur["record"], "version": cur["version"], "by": cur["by"], "at": cur["at"]}})
        return 200, {"ok": True, "api": API, "at": at, "applied": applied, "conflicts": conflicts,
                     "refused": refused}

    def _read(self, body: dict) -> tuple[int, dict]:
        try:
            locale = self._locale(body)
        except Invalid as e:
            return 400, {"ok": False, "error": f"invalid: {e}"}
        decisions = {u: {**r["record"], "page": r["page"], "version": r["version"], "by": r["by"], "at": r["at"]}
                     for (loc, u), r in sorted(self.decisions.items()) if loc == locale}
        pipeline = {u: dict(s) for (loc, u), s in sorted(self.pipeline.items()) if loc == locale}
        drafts = {u: dict(d) for (loc, u), d in sorted(self.drafts.items()) if loc == locale}
        findings: dict[str, list] = {}
        for (loc, u, _subject, _rule), r in sorted(self.findings.items()):
            if loc != locale:
                continue
            try:
                hits = json.loads(r["hits"])
            except ValueError:
                hits = []                       # a bad row is shown without its hits
            findings.setdefault(u, []).append({
                "subject": r["subject"], "subjectSha": r["subject_sha"], "rule": r["rule"],
                "severity": r["severity"], "message": r["message"], "cite": r["cite"],
                "hits": hits if isinstance(hits, list) else []})
        return 200, {"ok": True, "api": API, "locale": locale,
                     "readAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                     "decisions": decisions, "pipeline": pipeline, "drafts": drafts,
                     **({"findings": findings} if findings else {})}

    def _summary(self, body: dict) -> tuple[int, dict]:
        pairs: list[tuple[str, str]] = []
        try:
            f = body.get("flagged")
            if f is not None:
                if not isinstance(f, dict):
                    raise Invalid("flagged must be an object of lists")
                for locale, ids in f.items():
                    if locale not in REAL_LOCALES:
                        raise Invalid("unknown language")
                    if not isinstance(ids, list):
                        raise Invalid("flagged must be an object of lists")
                    for u in ids:
                        if not isinstance(u, str) or not UNIT.fullmatch(u):
                            raise Invalid("bad text id")
                        pairs.append((locale, u))
                if len(pairs) > MAX_FLAGGED:
                    raise Invalid(f"more than {MAX_FLAGGED} flagged texts")
        except Invalid as e:
            return 400, {"ok": False, "error": f"invalid: {e}"}
        counts: dict[tuple[str, str | None, bool], int] = {}
        for (loc, _u), r in self.decisions.items():
            if loc != SMOKE_LOCALE:
                key = (loc, r["record"].get("tray"), r["record"].get("text") is not None)
                counts[key] = counts.get(key, 0) + 1
        languages = {loc: {"shapes": [], "flagged": {}} for loc in REAL_LOCALES}
        # SQLite's ORDER BY tray, edited: no tray first, then csv, draft; unedited first.
        for loc, tray, edited in sorted(counts, key=lambda k: (k[0], k[1] is not None, k[1] or "", k[2])):
            languages[loc]["shapes"].append([_shape(tray, edited), counts[(loc, tray, edited)]])
        for loc, u in pairs:
            r = self.decisions.get((loc, u))
            if r is not None:
                languages[loc]["flagged"][u] = _shape(r["record"].get("tray"), r["record"].get("text") is not None)
        return 200, {"ok": True, "api": API,
                     "readAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                     "languages": languages}

    def _history(self, body: dict) -> tuple[int, dict]:
        try:
            locale = self._locale(body)
        except Invalid as e:
            return 400, {"ok": False, "error": f"invalid: {e}"}
        unit = str(body.get("unit") or "")
        if not UNIT.fullmatch(unit):
            return 400, {"ok": False, "error": "invalid: bad text id"}
        rows = [h for h in self.history if h["locale"] == locale and h["unit"] == unit][::-1][:50]
        return 200, {"ok": True, "history": [
            {**h["record"], "page": h["page"], "version": h["version"], "by": h["by"], "at": h["at"]}
            for h in rows]}

    # ── the desk's jobs (runbook U1) ────────────────────────────────────────────────
    def _sweep(self, locale: str) -> None:
        """jobSweep(): a job still open 35 minutes after it started is failed, in the row."""
        now = datetime.now(timezone.utc)
        cutoff = _iso(datetime.fromtimestamp(now.timestamp() - JOB_STALE_SEC, timezone.utc))
        for j in self.jobs.values():
            if (j["locale"] == locale and j["status"] in ("queued", "running")
                    and (j.get("started_at") or j["created_at"]) < cutoff):
                j.update(status="failed", finished_at=_iso(now), error="engine-never-answered")

    def _job_start(self, body: dict, email: str) -> tuple[int, dict]:
        try:
            locale = self._locale(body)
        except Invalid as e:
            return 400, {"ok": False, "error": f"invalid: {e}"}
        if locale not in REAL_LOCALES:
            return 400, {"ok": False, "error": "invalid: not a desk language"}
        kind = body.get("kind")
        if not isinstance(kind, str) or kind not in JOB_KINDS:
            return 400, {"ok": False, "error": "invalid: kind"}
        amount = None
        if kind == "submit":
            amount = body.get("amount_usd")
            if (not isinstance(amount, (int, float)) or isinstance(amount, bool) or not math.isfinite(amount)
                    or amount <= 0 or amount > JOB_RUN_CAP_USD):
                return 400, {"ok": False, "error": "invalid: amount_usd must be the plan's estimate, "
                                                   f"above 0 and at most {JOB_RUN_CAP_USD}"}
        elif "amount_usd" in body:                    # JavaScript's `!== undefined`: a null counts
            return 400, {"ok": False, "error": "invalid: only a submit carries an amount"}
        ref = body.get("ref")
        if ref is not None:
            if kind not in ("verify", "collect") or not isinstance(ref, str) or not JOB_REF.fullmatch(ref):
                return 400, {"ok": False, "error": "invalid: ref"}
        if not self.engine_configured:
            return 503, {"ok": False, "error": "the engine is not configured"}
        now = datetime.now(timezone.utc).timestamp()
        if sum(1 for who, t in self.job_starts if who == email and t > now - 86400) + 1 > JOB_DAILY:
            return 429, {"ok": False, "error": "over the daily budget"}
        self.job_starts.append((email, now))
        self._sweep(locale)
        open_ = next((j for j in self.jobs.values() if j["locale"] == locale and j["kind"] == kind
                      and j["status"] in ("queued", "running")), None)
        if open_ is not None:
            return 409, {"ok": False, "error": "already running", "job": _job_out(open_)}
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = {"id": job_id, "kind": kind, "locale": locale, "status": "queued",
                             "amount_usd": amount, "ref": ref, "requested_by": email,
                             "created_at": _iso(datetime.now(timezone.utc))}
        if self.dispatch_status not in (200, 204):
            self.jobs[job_id].update(status="failed", finished_at=_iso(datetime.now(timezone.utc)),
                                     error="engine-did-not-start")
            return 502, {"ok": False, "error": "the engine did not start", "job": _job_out(self.jobs[job_id])}
        self.dispatched.append(job_id)
        return 200, {"ok": True, "job": _job_out(self.jobs[job_id])}

    def _job_get(self, body: dict) -> tuple[int, dict]:
        try:
            locale = self._locale(body)
        except Invalid as e:
            return 400, {"ok": False, "error": f"invalid: {e}"}
        self._sweep(locale)
        if "id" in body:
            job_id = body["id"]
            if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
                return 400, {"ok": False, "error": "invalid: id"}
            one = self.jobs.get(job_id)
            if one is None or one["locale"] != locale:
                return 404, {"ok": False, "error": "no such job"}
            return 200, {"ok": True, "job": _job_out(one)}
        latest: dict[str, dict] = {}
        for j in self.jobs.values():                 # insertion order: the newest of a kind wins
            if j["locale"] == locale and (j["kind"] not in latest or j["created_at"] >= latest[j["kind"]]["created_at"]):
                latest[j["kind"]] = j
        return 200, {"ok": True, "jobs": {k: _job_out(latest[k]) for k in sorted(latest)}}

    def _export_get(self, body: dict) -> tuple[int, dict]:
        batch_id = body.get("batch_id")
        if not isinstance(batch_id, str) or not BATCH_ID.fullmatch(batch_id):
            return 400, {"ok": False, "error": "invalid: batch_id"}
        r = self.exports.get(batch_id)
        if r is None:
            return 404, {"ok": False, "error": "no such file"}
        try:
            refused = json.loads(r["refused"])
        except ValueError:
            refused = []
        return 200, {"ok": True, "export": {"batchId": r["batch_id"], "locale": r["locale"], "rows": r["rows"],
                                            "createdAt": r["created_at"], "csv": r["csv"],
                                            "refused": refused if isinstance(refused, list) else []}}
