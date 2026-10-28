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
(`desk-summary`, the first desk's index counts, was removed with it in CEL-054: the Worker and this refuse it as an unknown action.)

The desk's jobs (runbook U1): `desk-job-start` records a job the way the Worker does, and
"dispatches" it by adding its id to `dispatched` -- no engine runs here. The harness plays the
engine with `finish_job` and `seed_export` (the rows the engine writes through /engine-query);
`dispatch_status` stands for GitHub's answer (204 took it; anything else, the Worker fails the
job at once); `engine_configured` False stands for a Worker with no GitHub credential or no
ENGINE_SECRET (503). A user's starts are capped per day as the Worker caps them (JOB_DAILY).
`desk-job-get` and `desk-export-get` read them back.

The client's translation rules (schema v5, monorepo CEL-038 / CEL-043): `desk-rules-read` /
`desk-rules-write` / `desk-rules-history`, one Markdown body per scope ('global', a language,
'glossary:<lang>', 'words:<lang>', 'brief:<page>:<lang>') with a version. `desk-rules-write` IS the publish: the
editor's draft lives in the reviewer's browser, so there is no draft action here either, and
restoring a version is a write of its body. `byName` beside an email comes from `users` (the
Worker's user store, `{email, firstName, lastName}`; none = nameless); desk-history's does not.

The changes-file reader (CEL-112, desk 2.5.0): `desk-rules-import-read` sends the uploaded text (at most 64 KB of
UTF-8) and the languages ticked; the reader (Gemini in the Worker, `import_answer` here -- a dict or a function the
test sets) proposes changes, and CODE checks each (rule ID is there, real language, no empty rule, no duplicate or
conflicting term). It writes nothing. `desk-rules-import-apply` takes the accepted changes and `bases` (one version per
scope), re-checks them, and writes every changed scope or none: a stale base on any scope is a 409 and nothing moves.
Both are the Worker's code ported answer for answer (a rule line ends in ` [DE-12]`; a language's word list is scope
`words:<lang>`, a table `| Term | Translation | Type |` whose Translation is filled only for Always translate as).

What it leaves out: the session check (the harness signs everyone in), the signature's
value (it is never returned), and the per-user caps (they need thousands of requests; the
Worker's own tests hold them -- a click test makes a 429 with the harness's `action_faults`).
"""
from __future__ import annotations

import hashlib
import hmac
import json
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
# The Worker's per-user cap (DESK_CAP), which this stand-in does not enforce (see above). The
# desk's own ceiling is held to it (runbook WO-18), and these to the Worker by the parity test.
CAP_CHANGES, CAP_WINDOW_SEC = 2000, 600
# Used with fullmatch(), never match(): Python's `$` also matches before a final newline,
# JavaScript's does not -- so "<id>\n" passed here and was refused by the Worker (parity test).
UNIT = re.compile(r"[0-9a-f]{16}")
PAGE = re.compile(r"[a-z0-9_-]{1,80}")
# The Worker's jobs (runbook U1): the kinds, and how long an open job may go unanswered before the sweep fails it.
# Desk v2 has three, each for ONE language (CEL-054 removed verify, plan, submit and collect, and the locale "all").
JOB_KINDS = ("export", "translate-page", "retranslate")
JOB_STALE_SEC = 35 * 60
# A Weglot file is handed over only within the engine's FRESH_MINUTES of being made (U3, A4-1).
EXPORT_FRESH_SEC = 60 * 60
JOB_DAILY = 60                  # starts a day per user, a refused one too (each is a billed run)
JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,63}")
BATCH_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}")      # a Weglot file's batch id: the runner's rule
# Desk v2 (CEL-022): a job that works on ONE page carries it in `ref` as JSON text -- the Worker's JOB_PAGES,
# JOB_REF_JSON and jobRefJson. The desk sends the object; it is stored in a fixed key order, only these keys.
JOB_PAGES = ("cost-of-studying-english", "how-long-to-learn-english", "vancouver", "vs-toronto")
JOB_REF_JSON = {"translate-page": ("page", "note", "keepEdited"),
                "retranslate": ("page", "unit", "note", "keepEdited"), "export": ("page",)}
JOB_NOTE_MAX = 500
# The changes-file reader (CEL-112), the Worker's constants: the upload cap, the change kinds, the word Types, the
# "couldn't place" reasons and the model it asks.
IMPORT_MAX_BYTES = 65_536
IMPORT_MAX_CHANGES = 500
IMPORT_KINDS = ("add_rule", "edit_rule", "remove_rule", "add_word", "edit_word", "remove_word")
IMPORT_TYPES = ("Keep as is", "Always translate as", "Search keyword")
IMPORT_REASONS = ("unknown_language", "rule_not_found", "ambiguous", "type_unclear", "already_exists", "unreadable")
GEMINI_MODEL = "gemini-3.1-pro-preview"
_CONTROL = re.compile("[\u0000-\u001f\u007f]")
# The client's translation rules (CEL-038 Worker): its RULES_MAX_BYTES and RULES_HISTORY_LIMIT, and the whitespace
# String.prototype.trim() removes -- not Python's str.strip() ("\x85" and "\x1c" are not blank in JavaScript,
# "﻿" is).
RULES_MAX_BYTES = 262_144
RULES_HISTORY_LIMIT = 50
_JS_SPACE = ("\t\n\u000b\u000c\r              "
             "    　﻿")


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


def _js_trim(s: str) -> str:
    """String.prototype.trim()."""
    return s.strip(_JS_SPACE)


def _norm_email(e) -> str:
    """The Worker's normEmail(): String(e || '').trim().toLowerCase()."""
    return _js_trim(_js_str(e)).lower()


def _dumps(value) -> str:
    """JSON.stringify for the shapes this module sends: no spaces, non-ASCII as is."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _iso(t: datetime) -> str:
    """Date.prototype.toISOString(): milliseconds, Z."""
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def _job_ref_json(kind: str, ref) -> str | None:
    """The Worker's jobRefJson(): the stored text of a job's ref, or None when it is not one this kind takes."""
    keys = JOB_REF_JSON.get(kind)
    if keys is None or not isinstance(ref, dict) or not all(k in keys for k in ref):
        return None
    if not isinstance(ref.get("page"), str) or ref["page"] not in JOB_PAGES:
        return None
    out = {"page": ref["page"]}
    if "unit" in ref:
        if not isinstance(ref["unit"], str) or not UNIT.fullmatch(ref["unit"]):
            return None
        out["unit"] = ref["unit"]
    if "note" in ref:
        n = ref["note"]
        if (not isinstance(n, str) or _js_len(n) < 1 or _js_len(n) > JOB_NOTE_MAX or not _well_formed(n)
                or _CONTROL.search(n)):
            return None
        out["note"] = n
    if kind != "export":
        if not isinstance(ref.get("keepEdited"), bool):
            return None
        out["keepEdited"] = ref["keepEdited"]
    return _dumps(out)


def _job_ref_out(r: dict):
    """The Worker's jobRefOut(): a page job's ref is the object it was sent as; text that is not JSON as it is."""
    if r["kind"] not in JOB_REF_JSON:
        return r["ref"]
    try:
        return json.loads(r["ref"])
    except ValueError:
        return r["ref"]


def _job_out(r: dict | None) -> dict | None:
    """The Worker's jobOut(): the row in the desk's names, each optional field only when set."""
    if r is None:
        return None
    out = {"id": r["id"], "kind": r["kind"], "locale": r["locale"], "status": r["status"]}
    if r.get("amount_usd") is not None:
        out["amountUsd"] = r["amount_usd"]
    if r.get("ref"):
        out["ref"] = _job_ref_out(r)
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



def sig_input(locale: str, unit: str, record: dict, by: str, at: str) -> str:
    """The Worker's deskSigInput -- byte for byte (data/localize/desk-signature-vectors.json)."""
    return _dumps(["desk-approval/v1", locale, unit, record.get("tray") or "", record.get("text") or "",
                   record.get("approvedAgainst") or "", by, at])


class DeskStore:
    """desk-read / desk-write / desk-history over in-memory tables shaped like schema.sql's."""

    def __init__(self, page_map: dict[str, set[str]] | None = None, signing_key: str = "harness-key",
                 users: list[dict] | None = None):
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
        # schema v5 (CEL-038): the client's rules, scope -> {body, version, updated_at, updated_by}, and every
        # published version of every scope (append-only). `users` is the Worker's user store, for byName only.
        self.rules: dict[str, dict] = {}
        self.rules_history: list[dict] = []
        self.users: list[dict] = list(users or [])
        # CEL-112: the reader the Worker asks (Gemini). `import_answer`: None = no changes found, a dict in the
        # answer shape ({changes, unplaced}), a function (text, languages) -> that, or a str = the raw text it returned;
        # `import_status` = its HTTP status (not 2xx: a 502), `import_fault` = "timeout" | "unreachable", `import_usage`
        # = Gemini's usageMetadata, `reader_configured` False = a Worker with no GEMINI_API_KEY (503).
        # `import_calls` = every upload that reached the reader.
        self.import_answer = None
        self.import_status = 200
        self.import_fault: str | None = None
        self.import_usage: dict = {}
        self.reader_configured = True
        self.import_calls: list[tuple[str, tuple[str, ...]]] = []
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
            if action == "desk-job-start":
                return self._job_start(body, email)
            if action == "desk-job-get":
                return self._job_get(body)
            if action == "desk-export-get":
                return self._export_get(body)
            if action == "desk-rules-read":
                return self._rules_read(body)
            if action == "desk-rules-write":
                return self._rules_write(body, email)
            if action == "desk-rules-history":
                return self._rules_history(body)
            if action == "desk-rules-import-read":
                return self._rules_import_read(body)
            if action == "desk-rules-import-apply":
                return self._rules_import_apply(body, email)
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
        if "amount_usd" in body:                      # JavaScript's `!== undefined`: a null counts
            return 400, {"ok": False, "error": "invalid: a job carries no amount"}
        ref = body.get("ref")
        if ref is not None:
            ref = _job_ref_json(kind, ref)
            if ref is None:
                return 400, {"ok": False, "error": "invalid: ref"}
        elif kind != "export":                        # the page to work on is not optional
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
                             "amount_usd": None, "ref": ref, "requested_by": email,
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
            made = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).timestamp()
        except ValueError:
            made = None
        if made is None or datetime.now(timezone.utc).timestamp() - made > EXPORT_FRESH_SEC:
            return 410, {"ok": False, "error": "this file is out of date -- get the file again"}
        try:
            refused = json.loads(r["refused"])
        except ValueError:
            refused = []
        return 200, {"ok": True, "export": {"batchId": r["batch_id"], "locale": r["locale"], "rows": r["rows"],
                                            "createdAt": r["created_at"], "csv": r["csv"],
                                            "refused": refused if isinstance(refused, list) else []}}

    # ── the client's translation rules (schema v5; the Worker's rulesScope / deskRules*) ────────
    @staticmethod
    def _rules_scope(body: dict) -> str:
        """The Worker's rulesScope(): 'global', a real language (not the smoke's), 'glossary:<lang>',
        'words:<lang>' or 'brief:<page>:<lang>' for one of the four desk pages; anything else is refused."""
        scope = body.get("scope")
        scope = scope if isinstance(scope, str) else ""
        p = scope.split(":")
        ok = (scope == "global" or scope in REAL_LOCALES
              or (len(p) == 2 and p[0] in ("glossary", "words") and p[1] in REAL_LOCALES)
              or (len(p) == 3 and p[0] == "brief" and p[1] in JOB_PAGES and p[2] in REAL_LOCALES))
        if not ok:
            raise Invalid("unknown rules scope")
        return scope

    def _rules_names(self) -> dict[str, str]:
        """The Worker's rulesNames(): normalised email -> 'First Last', for the users who have a name."""
        names: dict[str, str] = {}
        for u in self.users:
            name = " ".join(p for p in (_js_trim(_js_str(u.get("firstName"))), _js_trim(_js_str(u.get("lastName")))) if p)
            if name:
                names[_norm_email(u.get("email"))] = name
        return names

    def _rules_row(self, r: dict, scope: str) -> dict:
        """The Worker's rulesRow(): a stored version as the editor reads it, the name beside the email when known."""
        out = {"scope": scope, "version": r["version"], "body": r["body"], "updatedAt": r["updated_at"],
               "updatedBy": r["updated_by"]}
        name = self._rules_names().get(_norm_email(r["updated_by"]))
        if name:
            out["byName"] = name
        return out

    def _rules_read(self, body: dict) -> tuple[int, dict]:
        try:
            scope = self._rules_scope(body)
        except Invalid as e:
            return 400, {"ok": False, "error": f"invalid: {e}"}
        r = self.rules.get(scope)
        if r is None:           # never published: version 0 with no body, the editor's empty state
            return 200, {"ok": True, "api": API, "scope": scope, "version": 0, "body": None}
        return 200, {"ok": True, "api": API, **self._rules_row(r, scope)}

    def _rules_write(self, body: dict, email: str) -> tuple[int, dict]:
        """The PUBLISH: the only thing that moves a scope's version or appends to its history."""
        try:
            scope = self._rules_scope(body)
            text = body.get("body")
            if not isinstance(text, str):
                raise Invalid("body must be text")
            if not text.strip(_JS_SPACE):
                raise Invalid("a rules block cannot be empty")
            if not _well_formed(text):
                raise Invalid("body is not valid text")
            if len(text.encode("utf-8")) > RULES_MAX_BYTES:
                raise Invalid(f"body is over {RULES_MAX_BYTES} bytes")
            base = body.get("baseVersion")
            try:
                ok = _safe_int(base) and base >= 0
            except OverflowError:       # JSON "1" + 400 zeros: JavaScript reads Infinity, which is not a safe integer
                ok = False
            if not ok:
                raise Invalid("bad baseVersion")
            base = int(base)
        except Invalid as e:
            return 400, {"ok": False, "error": f"invalid: {e}"}
        at = _iso(datetime.now(timezone.utc))
        cur = self.rules.get(scope)
        # Written by this request: an update of the version the editor was looking at (and only when the text
        # really changes), or the first insert (base 0, nothing there yet).
        if cur is not None and base > 0 and cur["version"] == base and cur["body"] != text:
            cur.update(body=text, version=base + 1, updated_at=at, updated_by=email)
            wrote = True
        elif cur is None and base == 0:
            cur = self.rules[scope] = {"body": text, "version": 1, "updated_at": at, "updated_by": email}
            wrote = True
        else:
            wrote = False
        if wrote:
            self.rules_history.append({"scope": scope, **cur})
            return 200, {"ok": True, "api": API, "scope": scope, "version": cur["version"], "at": at,
                         "updatedBy": email}
        # The text in use is the text sent, whatever version the editor saw: nothing to publish and no conflict
        # (a publish re-sent after a lost answer, a double click).
        if cur is not None and cur["body"] == text:
            return 200, {"ok": True, "api": API, "scope": scope, "version": cur["version"], "unchanged": True}
        current = self._rules_row(cur, scope) if cur is not None else {"scope": scope, "version": 0, "body": None}
        return 409, {"ok": False, "error": "someone published these rules first", "api": API, "current": current}

    def _rules_history(self, body: dict) -> tuple[int, dict]:
        try:
            scope = self._rules_scope(body)
        except Invalid as e:
            return 400, {"ok": False, "error": f"invalid: {e}"}
        rows = sorted((h for h in self.rules_history if h["scope"] == scope), key=lambda h: -h["version"])
        return 200, {"ok": True, "api": API, "scope": scope,
                     "history": [self._rules_row(h, scope) for h in rows[:RULES_HISTORY_LIMIT]]}

    # ── the changes-file reader (CEL-112): import-read proposes, import-apply writes ────────────
    # A port of the Worker's deskRulesImportRead / deskRulesImportApply / checkImport (tools/dashboard-dispatch/
    # cloudflare-worker.js, "Rules import"), answer for answer: scripts/tests/test_desk_standin_parity.py replays the same
    # requests through both. The reader (Gemini in the Worker) is the test's `import_answer`; the per-user caps are the
    # Worker's own tests' (the stand-in does not count reads, as it does not count writes).
    def _rules_import_read(self, body: dict) -> tuple[int, dict]:
        """Read an uploaded changes file: ask the reader, check what it proposes in code, write NOTHING."""
        try:
            text = body.get("text")
            if not isinstance(text, str) or not _js_trim(text):
                raise _ImportFail(400, "invalid: the upload is empty")
            if not _well_formed(text):
                raise _ImportFail(400, "invalid: the upload is not valid text")
            if len(text.encode("utf-8")) > IMPORT_MAX_BYTES:
                raise _ImportFail(413, f"invalid: the upload is over {IMPORT_MAX_BYTES} bytes")
            langs = body.get("languages")
            langs = list(dict.fromkeys(langs)) if isinstance(langs, list) and all(isinstance(x, str) for x in langs) else []
            if not langs or not all(x in REAL_LOCALES for x in langs):
                raise _ImportFail(400, "invalid: name 1 to 8 desk languages")
            if not self.reader_configured:
                raise _ImportFail(503, "reader not configured")
            cur, versions = self._import_state(langs)
            data, usage = self._ask_reader(text, langs)
            # The reader's own list, minus any line it returned that is a QUESTION: line, plus those lines once each from the code.
            asked = _question_lines(text)
            asked_keys = {_question_key(q) for q in asked}
            unplaced = [{"source_text": _js_slice(_js_string(u.get("source_text") if isinstance(u, dict) else None), 2000),
                         "language": u.get("language") if isinstance(u, dict) and u.get("language") in REAL_LOCALES else None,
                         "reason": u.get("reason") if isinstance(u, dict) and u.get("reason") in IMPORT_REASONS else "unreadable"}
                        for u in data["unplaced"][:IMPORT_MAX_CHANGES] if isinstance(u, (dict, list))]
            unplaced = [u for u in unplaced if _question_key(u["source_text"]) not in asked_keys]
            unplaced += [{"source_text": _js_slice(q, 2000), "language": None, "reason": "unreadable"}
                         for q in asked[:IMPORT_MAX_CHANGES]]
            res = _check_import(data["changes"][:IMPORT_MAX_CHANGES], cur, langs, self._import_max_nums(langs, cur))
            return 200, {"ok": True, "api": API, "model": GEMINI_MODEL, "changes": res["accepted"], "unplaced": unplaced,
                         "problems": res["problems"], "bases": versions, "usage": usage}
        except _ImportFail as e:
            return e.status, {"ok": False, "error": str(e)}

    def _ask_reader(self, text: str, langs: list[str]) -> tuple[dict, dict]:
        """The Worker's askGemini(), with the model replaced by what a test set: `import_answer` (None = nothing found,
        a dict in the answer shape, a function (text, languages) -> that, or a str = the raw text the model returned),
        `import_status` (an upstream status other than 2xx), `import_fault` ('timeout' | 'unreachable')."""
        self.import_calls.append((text, tuple(langs)))
        if self.import_fault == "timeout":
            raise _ImportFail(504, "the reader timed out")
        if self.import_fault == "unreachable":
            raise _ImportFail(502, "the reader could not be reached")
        if not 200 <= self.import_status <= 299:
            raise _ImportFail(502, f"the reader answered {self.import_status}")
        answer = self.import_answer(text, tuple(langs)) if callable(self.import_answer) else self.import_answer
        answer = {"changes": [], "unplaced": []} if answer is None else answer
        raw = answer if isinstance(answer, str) else json.dumps(answer)
        raw = re.sub(r"\A```(?:json)?\s*", "", _js_trim(raw), flags=re.I)
        raw = re.sub(r"\s*```\Z", "", raw)
        try:
            data = json.loads(raw)
        except ValueError:
            raise _ImportFail(502, "the reader answer was not readable")
        if not (isinstance(data, dict) and isinstance(data.get("changes"), list) and isinstance(data.get("unplaced"), list)):
            raise _ImportFail(502, "the reader answer had the wrong shape")
        u = self.import_usage
        return data, {"promptTokens": _num(u.get("promptTokenCount")),
                      "outputTokens": _num(u.get("candidatesTokenCount")) + _num(u.get("thoughtsTokenCount"))}

    def _import_state(self, langs: list[str]) -> tuple[dict, dict]:
        """The Worker's importState(): each language's rules and word-list bodies, and every scope's version (0 = none)."""
        cur, versions = {}, {}
        for lg in langs:
            r, w = self.rules.get(lg), self.rules.get(f"words:{lg}")
            cur[lg] = {"rules": r["body"] if r else None, "words": w["body"] if w else None}
            versions[lg] = r["version"] if r else 0
            versions[f"words:{lg}"] = w["version"] if w else 0
        return cur, versions

    def _import_max_nums(self, langs: list[str], cur: dict) -> dict[str, int]:
        """The Worker's importMaxNums(): the highest rule number ever used per language, over the current body and EVERY
        history row of that language (rules scopes only, no row limit) -- a removed rule's number is never given again."""
        return {lg: max(_max_rule_number(lg, [cur[lg]["rules"]]),
                        _max_rule_number(lg, [h["body"] for h in self.rules_history if h["scope"] == lg])) for lg in langs}

    def _rules_import_apply(self, body: dict, email: str) -> tuple[int, dict]:
        """Apply accepted changes: the code re-checks them against the CURRENT bodies and builds the new bodies itself
        (a body from the browser is never read); every scope they touch is written in this one call, or none is."""
        try:
            changes = body.get("changes")
            if not isinstance(changes, list) or not changes or len(changes) > IMPORT_MAX_CHANGES:
                raise _ImportFail(400, f"invalid: send 1 to {IMPORT_MAX_CHANGES} changes")
            bases = body.get("bases")
            if not isinstance(bases, dict):
                raise _ImportFail(400, "invalid: bases must name each language's version")
            langs = list(dict.fromkeys(c["language"] for c in changes if isinstance(c, dict) and c.get("language") in REAL_LOCALES))
            if not langs:
                raise _ImportFail(400, "invalid: no change names a desk language")
            cur, versions = self._import_state(langs)
            res = _check_import(changes, cur, langs, self._import_max_nums(langs, cur))
            if res["problems"]:
                return 400, {"ok": False, "error": "invalid: some changes do not fit the current rules", "problems": res["problems"]}
            written = [(lg, b) for lg, b in res["rules"].items()] + [(f"words:{lg}", b) for lg, b in res["words"].items()]
            written = [(sc, b) for sc, b in written
                       if b != ("null" if (cur[sc[6:]]["words"] if sc.startswith("words:") else cur[sc]["rules"]) is None
                                else (cur[sc[6:]]["words"] if sc.startswith("words:") else cur[sc]["rules"]))]
            for sc, b in written:
                if not _js_trim(b) or not _well_formed(b) or len(b.encode("utf-8")) > RULES_MAX_BYTES:
                    raise _ImportFail(400, f"invalid: the new {sc} is empty, not valid text or over {RULES_MAX_BYTES} bytes")
                if not _base_ok(bases.get(sc)):
                    raise _ImportFail(400, f"invalid: no base version for {sc}")
            if not written:
                return 200, {"ok": True, "api": API, "unchanged": True, "versions": {}, "applied": len(res["accepted"])}
            now = versions
            stale = [sc for sc, _ in written if now[sc] != bases[sc]]
            if stale:
                return 409, {"ok": False, "error": "someone published these rules first", "api": API, "stale": stale,
                             "current": {sc: now[sc] for sc, _ in written}}
            at, new_versions = _iso(datetime.now(timezone.utc)), {}
            for sc, text in written:        # nothing below can fail: the writes are the last step
                row = self.rules.get(sc)
                if row is None:
                    row = self.rules[sc] = {"body": text, "version": 1, "updated_at": at, "updated_by": email}
                else:
                    row.update(body=text, version=row["version"] + 1, updated_at=at, updated_by=email)
                self.rules_history.append({"scope": sc, **row})
                new_versions[sc] = row["version"]
            return 200, {"ok": True, "api": API, "versions": new_versions, "at": at, "updatedBy": email,
                         "applied": len(res["accepted"]),
                         "assigned": [{"language": o["language"], "id": o["assigned_id"]} for o in res["accepted"] if o.get("assigned_id")]}
        except _ImportFail as e:
            return e.status, {"ok": False, "error": str(e)}


# ── the changes-file reader's checks: the Worker's checkImport() and its line parsers, in Python ───────────────────────
class _ImportFail(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


_WS = "[" + re.escape(_JS_SPACE) + "]"                           # JavaScript's \s, which Python's is not
_RULE_TOKEN = re.compile(_WS + r"\[([A-Z]{2}-[0-9]+)\]" + _WS + r"*\Z")
_RULE_MARK = re.compile(r"\A" + _WS + r"*(?:[-*+]|[0-9]+[.)])" + _WS + "+")
# A line of the upload that starts QUESTION: (after an optional list mark or bold) is the client's AI asking the client
# something (Ruling CEL-112 18:2x): the Worker's isQuestionLine / questionKey / questionLines, answer for answer.
_ROW_END = re.compile(r"\|" + _WS + r"*\Z")
_ROW_RULE = re.compile(r":?-+:?\Z")
_RULE_ID = re.compile(r"[A-Z]{2}-[0-9]+\Z")
_WORD_HEAD = ["| Term | Translation | Type |", "|---|---|---|"]


def _base_ok(b) -> bool:
    """A usable base version: a safe integer from 0 up (JSON digits too long for a float are not one: JavaScript reads Infinity)."""
    try:
        return _safe_int(b) and b >= 0
    except OverflowError:
        return False


def _js_string(v) -> str:
    """String(v == null ? '' : v) for the values a reader may put in a text field."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, dict):
        return "[object Object]"
    if isinstance(v, list):
        return ",".join(_js_string(x) for x in v)
    return v if isinstance(v, str) else json.dumps(v)


def _num(v):
    """Number(v) || 0 for the token counts Gemini reports ("12" is 12, junk is 0)."""
    try:
        n = float(int(v) if isinstance(v, bool) else _js_trim(v) or 0) if isinstance(v, (bool, str)) else float(v)
    except (TypeError, ValueError, OverflowError):
        return 0
    return 0 if n != n or abs(n) == float("inf") else (int(n) if n.is_integer() else n)


def _js_slice(s: str, n: int) -> str:
    """s.slice(0, n) in UTF-16 units."""
    b = s.encode("utf-16-le", "surrogatepass")
    return s if len(b) <= 2 * n else b[:2 * n].decode("utf-16-le", "surrogatepass")


def _rule_text_of(line: str) -> str:
    return _js_trim(_RULE_MARK.sub("", _RULE_TOKEN.sub("", line, count=1), count=1))


def _question_key(s) -> str:
    """The Worker's questionKey(): a line with its list mark and bold markers off, blanks collapsed (to match the reader's copy)."""
    s = _RULE_MARK.sub("", "" if s is None else s, count=1).replace("**", "").replace("__", "")
    return _js_trim(re.sub(_WS + "+", " ", s))


def _drop_bold(s: str) -> str:
    return s[2:] if s.startswith(("**", "__")) else s


def _is_question_line(raw: str) -> bool:
    """The Worker's isQuestionLine(): plain string tests, no regular expression (Ruling 20:5x), so a 64 KB line of blanks is one pass.
    The forms read: one list mark (- * + or digits then . or ) and a blank), one ** or __, then QUESTION, blanks, one ** or __, blanks, the colon."""
    s, n = raw.lstrip(_JS_SPACE), 0
    if s[:1] in ("-", "*", "+"):
        n = 1
    else:
        while n < len(s) and "0" <= s[n] <= "9":
            n += 1
        n = n + 1 if n and s[n:n + 1] in (".", ")") else 0
    if n and s[n:n + 1] and s[n] in _JS_SPACE:
        s = s[n:].lstrip(_JS_SPACE)
    s = _drop_bold(s).lstrip(_JS_SPACE)
    return s.startswith("QUESTION") and _drop_bold(s[8:].lstrip(_JS_SPACE)).lstrip(_JS_SPACE).startswith(":")


def _question_lines(text: str) -> list[str]:
    """The Worker's questionLines(): every upload line that starts QUESTION:, trimmed, each distinct line once."""
    out = []
    for raw in re.split(r"\r\n|\r|\n", text):
        line = _js_trim(raw)
        if _is_question_line(raw) and line not in out:
            out.append(line)
    return out


def _body_lines(body) -> list[str]:
    return re.sub(r"\n+\Z", "", body).split("\n") if isinstance(body, str) and _js_trim(body) else []


def _parse_rules(body) -> dict:
    lines, ids = _body_lines(body), {}
    for i, ln in enumerate(lines):
        m = _RULE_TOKEN.search(ln)
        if m and m.group(1) not in ids:
            ids[m.group(1)] = i
    return {"lines": lines, "ids": ids}


def _split_row(line: str):
    t = _js_trim(line)
    if not t.startswith("|"):
        return None
    t = _ROW_END.sub("", t[1:], count=1)
    return [_js_trim(c).replace("\\|", "|") for c in re.split(r"(?<!\\)\|", t)]


def _word_cell(c) -> str:
    return str(c).replace("|", "\\|")


def _word_line(term, tr, typ) -> str:
    return f"| {_word_cell(term)} | {_word_cell(tr)} | {typ} |"


def _parse_words(body) -> dict:
    lines, rows = _body_lines(body), {}
    for i, ln in enumerate(lines):
        c = _split_row(ln)
        if not c or len(c) < 3 or all(_ROW_RULE.match(x) for x in c):
            continue
        if c[0].lower() == "term" and c[2].lower() == "type":
            continue
        rows.setdefault(c[0].lower(), {"i": i, "term": c[0], "translation": c[1], "type": c[2]})
    return {"lines": lines, "rows": rows}


def _max_rule_number(lang: str, bodies) -> int:
    pre, top = lang.upper(), 0
    for b in bodies:
        for m in re.finditer(r"\[([A-Z]{2})-([0-9]+)\]", b or ""):
            if m.group(1) == pre:
                top = max(top, int(m.group(2)))
    return top


def _check_import(changes: list, cur: dict, allowed: set, max_num: dict) -> dict:
    """The Worker's checkImport(): the code's verdict on every proposed change, and the new bodies. Returns
    {accepted, problems, rules: {lang: body}, words: {lang: body}} -- a body only for a scope that really changes."""
    problems, cand = [], []

    def bad(c, reason):
        src = c.get("source_text") if isinstance(c, dict) else None
        problems.append({"reason": reason, "source_text": _js_slice(_js_string(src), 2000), "change": c})

    parsed_r, parsed_w = {}, {}
    rules_of = lambda lg: parsed_r.setdefault(lg, _parse_rules(cur[lg]["rules"]))
    words_of = lambda lg: parsed_w.setdefault(lg, _parse_words(cur[lg]["words"]))
    tidy = lambda s: _js_trim(_RULE_TOKEN.sub("", str(s), count=1))
    for c in changes:
        if not isinstance(c, dict):
            bad({"source_text": ""}, "bad_shape")
            continue
        if c.get("language") not in REAL_LOCALES:
            bad(c, "unknown_language")
            continue
        if c["language"] not in allowed:
            bad(c, "language_not_requested")
            continue
        if c.get("kind") not in IMPORT_KINDS:
            bad(c, "bad_shape")
            continue
        lang, kind = c["language"], c["kind"]
        out = {"language": lang, "kind": kind, "target_id": None, "term": None, "before": None, "after": None, "type": None,
               "matched_by": None, "source_text": _js_slice(_js_string(c.get("source_text")), 2000)}
        if kind.endswith("_rule"):
            r = rules_of(lang)
            if kind != "add_rule":
                tid = _js_trim(c["target_id"]) if isinstance(c.get("target_id"), str) else ""
                if not _RULE_ID.match(tid) or tid[:2] != lang.upper() or tid not in r["ids"]:
                    bad(c, "rule_not_found")
                    continue
                out["target_id"], out["before"] = tid, _rule_text_of(r["lines"][r["ids"][tid]])
                out["matched_by"] = "meaning" if c.get("matched_by") == "meaning" else "id"
            if kind != "remove_rule":
                if not isinstance(c.get("after"), str) or not tidy(c["after"]):
                    bad(c, "empty_rule")
                    continue
                if re.search(r"[\r\n]", tidy(c["after"])):
                    bad(c, "multiline")
                    continue
                out["after"] = tidy(c["after"])
                if kind == "add_rule" and any(_rule_text_of(r["lines"][i]).lower() == out["after"].lower() for i in r["ids"].values()):
                    bad(c, "already_exists")
                    continue
                if kind == "edit_rule" and out["after"] == out["before"]:
                    bad(c, "unchanged")
                    continue
            out["key"] = f"addrule:{lang}:{out['after'].lower()}" if kind == "add_rule" else f"rule:{lang}:{out['target_id']}"
        else:
            w = words_of(lang)
            term = _js_trim(c["term"]) if isinstance(c.get("term"), str) else ""
            tr = _js_trim(c["after"]) if isinstance(c.get("after"), str) else ""
            if not term or re.search(r"[\r\n]", term):
                bad(c, "bad_shape")
                continue
            if c.get("type") is not None and c["type"] not in IMPORT_TYPES:
                bad(c, "type_unclear")
                continue
            if c.get("type") == "Search keyword" and tr and tr != term:
                term = tr                       # a Search keyword's Term IS the target-language phrase
            if re.search(r"[\r\n]", term):
                bad(c, "multiline")
                continue
            out["term"] = term
            have = w["rows"].get(term.lower())
            if kind == "add_word":
                if have:
                    bad(c, "already_exists")
                    continue
                if c.get("type") is None:
                    bad(c, "type_unclear")
                    continue
            elif not have:
                bad(c, "term_not_found")
                continue
            if kind != "remove_word":
                out["type"] = c["type"] if c.get("type") is not None else have["type"]
                if re.search(r"[\r\n]", tr):
                    bad(c, "multiline")
                    continue
                if out["type"] == "Always translate as":      # only this Type carries a Translation
                    if not tr:
                        bad(c, "empty_rule")
                        continue
                    out["after"] = tr
            else:
                out["type"] = have["type"]
            if have:
                out["before"] = have["translation"] or None
            out["key"] = f"word:{lang}:{term.lower()}"
        cand.append(out)
    # Two lines about the same rule or term: identical ones collapse, different ones are a conflict (both refused).
    groups: dict[str, list[dict]] = {}
    for o in cand:
        groups.setdefault(o["key"], []).append(o)
    accepted = []
    for g in groups.values():
        same = all(o["kind"] == g[0]["kind"] and o["after"] == g[0]["after"] and o["type"] == g[0]["type"] for o in g)
        if len(g) == 1 or same:
            accepted.append(g[0])
            for o in g[1:]:
                bad(o, "duplicate")
        else:
            for o in g:
                bad(o, "conflict")
    pos = {id(o): i for i, o in enumerate(cand)}
    accepted.sort(key=lambda o: pos[id(o)])
    # Build the new bodies. Edits and removes address the ORIGINAL line numbers, adds go on the end.
    bodies: dict[str, dict] = {"rules": {}, "words": {}}
    for lang in allowed:
        mine = [o for o in accepted if o["language"] == lang]
        for side in ("rules", "words"):
            lst = [o for o in mine if o["kind"].endswith("_rule" if side == "rules" else "_word")]
            if not lst:
                continue
            p = rules_of(lang) if side == "rules" else words_of(lang)
            lines = list(_WORD_HEAD) if side == "words" and not p["lines"] else list(p["lines"])
            add_at, n = [], max_num.get(lang, 0)
            for o in lst:
                if o["kind"] == "add_rule":
                    n += 1
                    o["assigned_id"] = f"{lang.upper()}-{n}"
                    add_at.append(f"- {o['after']} [{o['assigned_id']}]")
                elif o["kind"] == "add_word":
                    add_at.append(_word_line(o["term"], o["after"] or "", o["type"]))
                elif side == "rules":
                    i = p["ids"][o["target_id"]]
                    m = _RULE_MARK.match(lines[i])
                    lines[i] = None if o["kind"] == "remove_rule" else f"{m.group(0) if m else ''}{o['after']} [{o['target_id']}]"
                else:
                    i = p["rows"][o["term"].lower()]["i"]
                    lines[i] = None if o["kind"] == "remove_word" else _word_line(o["term"], o["after"] or "", o["type"])
            nxt = [x for x in lines if x is not None] + add_at
            # A rules block cannot be empty: refuse the whole group, change nothing there.
            if side == "rules" and not any(_js_trim(x) for x in nxt):
                for o in lst:
                    accepted[:] = [x for x in accepted if x is not o]
                    bad(o, "empty_result")
                continue
            bodies[side][lang] = "\n".join(nxt) + "\n"
    for o in accepted:
        del o["key"]
    return {"accepted": accepted, "problems": problems, "rules": bodies["rules"], "words": bodies["words"]}
