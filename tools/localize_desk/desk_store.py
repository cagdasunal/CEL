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

`desk-summary` (runbook WO-18) is the index's: each language's decisions as the shapes the
desk's stageOf() reads, with their counts, and the shape of each flagged text it names.

What it leaves out: the session check (the harness signs everyone in), the signature's
value (it is never returned), and the per-user cap (it needs thousands of requests; the
Worker's own tests hold it).
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
MAX_FLAGGED = 8000
# The Worker's per-user cap (DESK_CAP), which this stand-in does not enforce (see above). The
# desk's own ceiling is held to it (runbook WO-18), and these to the Worker by the parity test.
CAP_CHANGES, CAP_WINDOW_SEC = 2000, 600
# Used with fullmatch(), never match(): Python's `$` also matches before a final newline,
# JavaScript's does not -- so "<id>\n" passed here and was refused by the Worker (parity test).
UNIT = re.compile(r"[0-9a-f]{16}")
PAGE = re.compile(r"[a-z0-9_-]{1,80}")


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
        return 200, {"ok": True, "api": API, "locale": locale,
                     "readAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                     "decisions": decisions, "pipeline": pipeline, "drafts": drafts}

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
