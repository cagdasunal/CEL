"""Gemini-vision visual-analysis pass for the Arabic RTL engine.

For each /ar/ page that is ELIGIBLE — never analyzed, OR its Webflow CSS changed AND it
hasn't been analyzed in >= 7 days — screenshot the live RTL page, ask Gemini 3.1 Pro what
still looks wrong, and write VALIDATED, html[lang="ar"]-scoped corrective CSS to
data/arabic-visual/<slug>.css (+ a <slug>.report.md). Per-page state (css_hash +
analyzed_at) lives in data/arabic-visual/state.json. The hourly build.py folds every
<slug>.css into the minified cel-arabic.css.

Run from repo root:
    python -m tools.arabic_rtl.visual                       # all eligible pages
    python -m tools.arabic_rtl.visual --only /ar/vancouver  # one page (smoke test)
    python -m tools.arabic_rtl.visual --limit 2             # cap pages this run
    python -m tools.arabic_rtl.visual --dry-run             # show eligibility only
    python -m tools.arabic_rtl.visual --force               # ignore the eligibility gate

google-genai and playwright are imported lazily (inside the call sites) so this module —
and its unit tests — import without those optional deps installed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from tools.arabic_rtl import build, generator, screenshot

_REPO_ROOT = Path(__file__).resolve().parents[2]
VISUAL_DIR = _REPO_ROOT / "data" / "arabic-visual"
STATE_PATH = VISUAL_DIR / "state.json"
SHOTS_DIR = VISUAL_DIR / "screenshots"  # PNGs for review; gitignored, uploaded as CI artifact
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "visual_system.md"
REANALYZE_AFTER = timedelta(days=7)

_CLASS_ATTR = re.compile(r'class="([^"]*)"')
_CLASS_TOKEN = re.compile(r"\.([A-Za-z0-9_-]+)")
_STRUCT_BAD = re.compile(r"[{}<>]")


# ---- page helpers -----------------------------------------------------------

def slug_for(url: str) -> str:
    path = urlparse(url).path.strip("/")
    s = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
    return s or "ar-home"


def ltr_url_for(url: str) -> str:
    """The English (LTR) equivalent of an /ar/ URL — the reference Gemini compares against.
    /ar/vancouver -> /vancouver ; /ar -> / (Weglot serves English at the root, Arabic at /ar/)."""
    p = urlparse(url)
    path = p.path
    if "/ar/" in path:
        path = path.replace("/ar/", "/", 1)
    elif path.rstrip("/") == "/ar":
        path = "/"
    return f"{p.scheme}://{p.netloc}{path}"


def class_inventory(html: str, limit: int = 400) -> list[str]:
    classes: set[str] = set()
    for chunk in _CLASS_ATTR.findall(html):
        for c in chunk.split():
            if c:
                classes.add(c)
    return sorted(classes)[:limit]


def page_css_hash(html: str) -> str:
    return build.fingerprint(build.extract_css_urls(html))


# ---- state ------------------------------------------------------------------

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — corrupt state shouldn't crash the run
            return {}
    return {}


def save_state(state: dict) -> None:
    VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    build.atomic_write_text(STATE_PATH, json.dumps(state, indent=2, sort_keys=True) + "\n")


def is_eligible(url: str, css_hash: str, state: dict, now: datetime) -> bool:
    rec = state.get(url)
    if not rec:
        return True  # never analyzed
    if rec.get("css_hash") == css_hash:
        return False  # CSS unchanged → never re-analyze
    try:
        last = datetime.fromisoformat(rec.get("analyzed_at", ""))
    except Exception:  # noqa: BLE001 — unparseable timestamp → treat as due
        return True
    return (now - last) >= REANALYZE_AFTER  # changed, but only re-check once/week


# ---- Gemini -----------------------------------------------------------------

def build_user_text(url: str, classes: list[str]) -> str:
    return (
        f"PAGE: {url}\n"
        "IMAGE 1 = the ENGLISH (LTR) original (your reference). IMAGE 2 = the current ARABIC "
        "(RTL) render — it already has dir=rtl, the mechanical rtlcss flip, and the Cairo font "
        "applied. Compare them: the Arabic should be a proper MIRROR of the English (minus the "
        "never-flip items). Audit section by section and find EVERYTHING still wrong.\n\n"
        "REAL CSS class names on this page (build selectors only from these + plain elements):\n"
        + ", ".join(classes)
    )


def _parse_json_array(text: str) -> list:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001 — salvage the first [...] block
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            return []
    return data if isinstance(data, list) else []


def gemini_corrections(system_prompt: str, user_text: str, images: list[bytes]) -> list:
    """Call Gemini 3.1 Pro (vision) with one or more PNGs (English ref + Arabic render);
    return the raw list of correction dicts."""
    from google import genai  # lazy — optional dep
    from google.genai import types
    from tools.summary import config  # MODEL_ID = "gemini-3.1-pro-preview"

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set (needed for the visual pass).")
    client = genai.Client(api_key=api_key)
    parts: list = [system_prompt + "\n\n" + user_text]
    parts += [types.Part.from_bytes(data=png, mime_type="image/png") for png in images]
    resp = client.models.generate_content(
        model=config.MODEL_ID,
        contents=parts,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return _parse_json_array(getattr(resp, "text", "") or "")


# ---- validation (trust boundary) -------------------------------------------

def _decl_safe(decl: str) -> bool:
    if _STRUCT_BAD.search(decl):
        return False
    low = decl.lower()
    if any(b in low for b in ("@import", "expression(", "javascript:", "behavior:")):
        return False
    for m in re.finditer(r"url\(\s*['\"]?([^'\")]*)", decl, re.I):
        u = m.group(1).strip().lower()
        if u and not (
            u.startswith("data:")
            or u.startswith("https://cel.englishcollege.com")
            or u.startswith("/")
            or u.startswith("#")
        ):
            return False
    return True


def _selector_grounded(sel: str, class_set: set[str]) -> bool:
    if _STRUCT_BAD.search(sel) or "@" in sel or ";" in sel:
        return False
    return all(c in class_set for c in _CLASS_TOKEN.findall(sel))


def validate_rules(rules: list, class_set: set[str]) -> list[str]:
    """Turn Gemini's raw correction dicts into safe, html[lang="ar"]-scoped CSS rule
    strings. Drops anything unscopable, structurally unsafe, or referencing a class that
    isn't actually on the page."""
    out: list[str] = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        sel = str(r.get("selector", "")).strip()
        decl = str(r.get("declarations", "")).strip().rstrip(";").strip()
        if not sel or not decl:
            continue
        if not _selector_grounded(sel, class_set) or not _decl_safe(decl):
            continue
        decls = generator.split_decls(decl)
        if not decls:
            continue
        scoped = ",".join(generator.scope(s) for s in generator.split_selector_list(sel))
        body = ";".join(f"{p}:{v}" for p, v in decls.items())
        out.append(f"{scoped}{{{body}}}")
    return out


# ---- outputs ----------------------------------------------------------------

def write_outputs(slug: str, css_rules: list[str], raw_rules: list, url: str) -> None:
    VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    css = generator.minify("".join(css_rules)) if css_rules else ""
    build.atomic_write_text(VISUAL_DIR / f"{slug}.css", (css + "\n") if css else "")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# Arabic visual corrections — {url}",
        "",
        f"_generated {ts} · {len(css_rules)} rule(s) applied of {len(raw_rules)} suggested_",
        "",
    ]
    for r in raw_rules:
        if isinstance(r, dict):
            sev = str(r.get("severity", "")).strip()
            nat = " [native-review]" if r.get("needs_native_review") else ""
            tag = (f"**[{sev}]**{nat} " if sev else (nat + " " if nat else ""))
            lines.append(
                f"- {tag}`{str(r.get('selector', ''))[:80]}` — {str(r.get('reason', ''))[:300]}"
            )
    build.atomic_write_text(VISUAL_DIR / f"{slug}.report.md", "\n".join(lines) + "\n")


# ---- main -------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Gemini-vision Arabic RTL visual analysis.")
    ap.add_argument("--only", help="only analyze /ar/ URLs containing this substring")
    ap.add_argument("--limit", type=int, default=0, help="cap pages analyzed this run (0 = no cap)")
    ap.add_argument("--dry-run", action="store_true", help="print eligibility only; no screenshots/Gemini")
    ap.add_argument("--force", action="store_true", help="ignore the eligibility gate")
    args = ap.parse_args()

    ar_urls = build.get_ar_urls(build.fetch(build.SITEMAP_URL))
    if args.only:
        ar_urls = [u for u in ar_urls if args.only in u]
    if not ar_urls:
        print("no /ar/ URLs in scope", file=sys.stderr)
        return 1
    print(f"{len(ar_urls)} /ar/ URL(s) in scope")

    state = load_state()
    now = datetime.now(timezone.utc)
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    analyzed = 0

    for url in ar_urls:
        try:
            html = build.fetch(url)
        except Exception as e:  # noqa: BLE001 — one flaky page must not abort the batch
            print(f"  skip (fetch failed) {url}: {e}", file=sys.stderr)
            continue
        css_hash = page_css_hash(html)
        if not (args.force or is_eligible(url, css_hash, state, now)):
            continue
        if args.dry_run:
            print(f"  ELIGIBLE {url}")
            continue
        if args.limit and analyzed >= args.limit:
            print(f"  limit {args.limit} reached — stopping")
            break
        slug = slug_for(url)
        try:
            rtl_png = screenshot.capture(url, expect_rtl=True)
            ltr_png = screenshot.capture(ltr_url_for(url), expect_rtl=False)
        except Exception as e:  # noqa: BLE001
            print(f"  skip (screenshot failed) {url}: {e}", file=sys.stderr)
            continue
        SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        (SHOTS_DIR / f"{slug}.png").write_bytes(rtl_png)      # Arabic (RTL) — review
        (SHOTS_DIR / f"{slug}-ltr.png").write_bytes(ltr_png)  # English (LTR) — reference
        classes = class_inventory(html)
        try:
            raw = gemini_corrections(system_prompt, build_user_text(url, classes), [ltr_png, rtl_png])
        except Exception as e:  # noqa: BLE001
            print(f"  skip (gemini failed) {url}: {e}", file=sys.stderr)
            continue
        css_rules = validate_rules(raw, set(classes))
        write_outputs(slug, css_rules, raw, url)
        state[url] = {"slug": slug, "css_hash": css_hash, "analyzed_at": now.isoformat()}
        save_state(state)  # persist per page — an interruption keeps completed Gemini work
        analyzed += 1
        print(f"  analyzed {url} -> {slug}.css ({len(css_rules)} of {len(raw)} suggestions kept)")

    save_state(state)
    print(f"done: analyzed {analyzed} page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
