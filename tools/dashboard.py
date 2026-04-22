"""Shared theme for Fidelo viewer.html and Weglot log.html dashboards.

Consumers: tools.fidelo.build_viewer · tools.weglot.generate_status_page
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
LOGO_SVG_PATH = _REPO_ROOT / "sites" / "englishcollege" / "shared" / "cel-logo-multicolor.svg"

# Brand palette — mirrored from sites/englishcollege/site.json css_variables.
BG_COLOR       = "#F1EAD8"
FG_COLOR       = "#37332c"
ACCENT_PRIMARY = "#5d60ee"
ACCENT_WARM    = "#e78b10"
SURFACE        = "#F1EAD8"
BORDER         = "rgba(55,51,44,0.12)"
BORDER_STRONG  = "rgba(55,51,44,0.18)"
MUTED          = "rgba(55,51,44,0.65)"
PANEL          = "rgba(55,51,44,0.04)"

_XML_PROLOG_RE = re.compile(r"^\s*<\?xml[^?]*\?>\s*", re.DOTALL)
_DOCTYPE_RE    = re.compile(r"^\s*<!DOCTYPE[^>]*>\s*", re.DOTALL | re.IGNORECASE)


def load_logo_svg() -> str:
    if not LOGO_SVG_PATH.exists():
        print(
            f"[dashboard] WARNING: logo not found at {LOGO_SVG_PATH}",
            file=sys.stderr,
        )
        return "<svg width='108' height='32' xmlns='http://www.w3.org/2000/svg'></svg>"
    raw = LOGO_SVG_PATH.read_text(encoding="utf-8")
    raw = _XML_PROLOG_RE.sub("", raw)
    raw = _DOCTYPE_RE.sub("", raw)
    return raw.strip()


def render_logo_mark(extra_class: str = "") -> str:
    inline_svg = load_logo_svg()
    cls = f"brand-mark {extra_class}".strip()
    return (
        f'<div class="{cls}">'
        f'<span class="brand-logo" aria-label="English College">{inline_svg}</span>'
        f"</div>"
    )


# Shared dashboard theme — tools/dashboard.py. Consumers: viewer.html (Fidelo) · log.html (Weglot).
SHARED_CSS = """
  /* === Reset + Root === */
  :root {
    --bg: #F1EAD8;
    --fg: #37332c;
    --muted: rgba(55,51,44,0.65);
    --faint: rgba(55,51,44,0.45);
    --border: rgba(55,51,44,0.12);
    --border-strong: rgba(55,51,44,0.18);
    --stripe: rgba(55,51,44,0.04);
    --panel: rgba(55,51,44,0.03);
    --accent: #5d60ee;
    --accent-warm: #e78b10;
    --surface: #F1EAD8;
    --ok: #1d6b3a;
    --warn: #a65f1f;
    --err: #a02624;
    --notice-bg: rgba(166,95,31,0.08);
    --notice-border: rgba(166,95,31,0.28);
    --notice-fg: #7a4314;
    --radius: 10px;
    --radius-sm: 6px;
  }
  * { box-sizing: border-box; }
  html, body { background: var(--bg); }
  body {
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    margin: 0;
  }

  /* === Dashboard shell === */
  .dashboard-shell {
    max-width: 1120px;
    margin: 0 auto;
    padding: 0 28px;
  }

  /* === Header === */
  .dashboard-header {
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 28px 0 18px;
    flex-wrap: wrap;
  }

  /* === Brand mark === */
  .brand-mark {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 0 0 auto;
  }
  .brand-logo {
    display: inline-flex;
  }
  .brand-logo svg {
    display: block;
    height: 36px;
    width: auto;
  }

  /* === Title area === */
  .brand-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .brand-text h1 {
    margin: 0;
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.01em;
  }
  .brand-text .subtitle,
  .brand-text p {
    margin: 0;
    font-size: 13px;
    color: var(--muted);
  }
  .brand-text .eyebrow {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted);
    margin: 0 0 2px;
  }

  /* === Controls toolbar === */
  .controls {
    position: sticky;
    top: 0;
    z-index: 10;
    padding: 14px 0;
    background: rgba(241,234,216,0.92);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
  }
  .controls .dashboard-shell {
    padding-top: 0;
    padding-bottom: 0;
  }
  .controls-inner {
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    align-items: flex-end;
    justify-content: flex-end;
  }
  .controls .control-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .controls label {
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .controls select {
    font: inherit;
    font-size: 13px;
    padding: 9px 34px 9px 12px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--fg);
    min-width: 200px;
    appearance: none;
    -webkit-appearance: none;
    -moz-appearance: none;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'><path fill='none' stroke='%2337332c' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round' d='M1 1.5l5 5 5-5'/></svg>");
    background-repeat: no-repeat;
    background-position: right 12px center;
    background-size: 10px auto;
    transition: border-color 120ms ease, box-shadow 120ms ease;
  }
  .controls select:hover { border-color: rgba(55,51,44,0.35); }
  .controls select:focus-visible {
    outline: 0;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(93,96,238,0.18);
  }
  .controls select:disabled { opacity: 0.45; cursor: not-allowed; }

  /* === Main content area === */
  .dashboard-main { padding: 24px 0 96px; }

  /* === Headings & body blocks === */
  h2 {
    font-size: 18px;
    font-weight: 600;
    margin: 40px 0 12px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 6px;
  }
  p.lede {
    margin: 0 0 24px;
    color: var(--muted);
    font-size: 14px;
  }

  /* === Scroll containers === */
  .scroll-x { overflow-x: auto; }

  /* === Tables === */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0;
    font-size: 14px;
  }
  th, td {
    text-align: left;
    padding: 10px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  th {
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
  }
  tr:last-child td { border-bottom: 0; }
  tbody tr:hover td { background: var(--stripe); }

  /* === KV table === */
  .kv-table { width: 100%; border-collapse: collapse; font-size: 14px; margin: 8px 0; }
  .kv-table td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  .kv-table tr:last-child td { border-bottom: 0; }
  .kv-table .k {
    font-weight: 600;
    white-space: nowrap;
    color: var(--faint);
    font-size: 12px;
    width: 34%;
  }
  .kv-table .v { color: var(--fg); }

  /* === Mono / pre === */
  .mono, pre.mono {
    font-family: "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
    font-size: 12px;
    background: var(--stripe);
    padding: 2px 6px;
    border-radius: 4px;
  }
  pre.mono {
    padding: 12px 14px;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
    margin: 8px 0;
  }

  /* === Bullets === */
  ul.bullets { padding-left: 20px; margin: 8px 0; }
  ul.bullets li { margin: 4px 0; }

  /* === Hero image === */
  .hero-img-wrap { margin: 0 0 24px; }
  .hero-img-wrap img {
    max-width: 100%;
    border-radius: var(--radius);
    border: 1px solid var(--border);
  }

  /* === Missing notice === */
  .missing-notice {
    display: inline-block;
    background: var(--notice-bg);
    border: 1px solid var(--notice-border);
    color: var(--notice-fg);
    border-radius: var(--radius-sm);
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 600;
  }

  /* === Status indicators === */
  .status-ok    { color: var(--ok); }
  .status-partial { color: var(--warn); }
  .status-failed  { color: var(--err); }
  .dash { color: var(--faint); }
  .rt { color: var(--muted); font-size: 12px; }

  /* === log.html: status card === */
  .status {
    background: var(--stripe);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    margin: 24px 0;
  }
  .status.error {
    background: rgba(192,57,43,0.08);
    border-color: rgba(192,57,43,0.3);
  }
  .status-label { font-size: 20px; font-weight: 600; margin: 0 0 6px; }
  .status-ok .status-label  { color: #1d6b3a; }
  .status-error .status-label { color: #a02624; }
  .subtle { color: var(--muted); font-size: 14px; margin: 6px 0 0; }

  /* === log.html: file list === */
  ul.files, ul.activity { list-style: none; padding: 0; margin: 8px 0; }
  ul.files li, ul.activity li {
    padding: 10px 0;
    border-bottom: 1px solid rgba(55,51,44,0.1);
  }
  ul.files li:last-child, ul.activity li:last-child { border-bottom: 0; }
  ul.files .file-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 8px;
  }
  ul.files .file-name { font-weight: 600; }
  ul.activity .when {
    color: var(--muted);
    font-size: 13px;
    margin-right: 10px;
  }
  .empty { color: var(--muted); font-style: italic; padding: 16px 0; }

  /* === Slug / lang / when cell types (log.html table) === */
  td.slug {
    font-family: "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
    font-size: 13px;
    word-break: break-word;
  }
  td.lang {
    font-variant: all-small-caps;
    letter-spacing: 0.05em;
    color: var(--muted);
    white-space: nowrap;
  }
  td.when { color: var(--muted); white-space: nowrap; font-size: 13px; }

  /* === Links === */
  a { color: var(--fg); text-decoration: underline; }
  a:hover { color: var(--accent); }

  /* === Footer === */
  footer {
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    font-size: 13px;
    color: var(--muted);
  }

  /* === Responsive === */
  @media (max-width: 960px) {
    .dashboard-header { padding: 22px 0 14px; }
    .controls-inner { gap: 12px; }
    .controls select { min-width: 180px; }
  }
  @media (max-width: 640px) {
    .dashboard-header { padding: 20px 0 14px; }
    .brand-text h1 { font-size: 20px; }
    .controls-inner {
      flex-direction: column;
      align-items: stretch;
      justify-content: stretch;
    }
    .controls .control-group { width: 100%; }
    .controls select { width: 100%; min-width: 0; }
  }
  @media (max-width: 500px) {
    table { font-size: 13px; }
    td.slug { font-size: 12px; }
    h2 { font-size: 17px; }
  }
  @media (max-width: 420px) {
    .dashboard-shell { padding: 0 16px; }
    .kv-table .k,
    .kv-table .v { display: block; width: 100%; }
    .kv-table .k { padding-bottom: 2px; }
  }
"""


# ---------------------------------------------------------------------------
# Dashboard shell (sidebar + iframe) + public gate + listing images
# Consumers: cel.englishcollege.com/private/index.html (shell),
#            cel.englishcollege.com/index.html (password gate),
#            cel.englishcollege.com/private/housing/index.html (listing imgs).
# ---------------------------------------------------------------------------

SHELL_CSS = """
  /* === Dashboard shell (top-bar + iframe) === */
  .shell-root {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    background: var(--bg);
  }
  .shell-sidebar { display: none; }

  /* === Top-bar shell (2026-04-22) === */
  .shell-topbar {
    display: flex;
    align-items: center;
    gap: 24px;
    padding: 12px 28px;
    background: var(--bg);
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 20;
  }
  .shell-topbar .shell-brand {
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
    text-decoration: none;
  }
  .shell-topbar .shell-brand .brand-logo-img { height: 32px; }
  .shell-tabs {
    flex: 1 1 auto;
    display: flex;
    gap: 4px;
    min-width: 0;
    overflow-x: auto;
  }
  .shell-tab {
    display: inline-flex;
    align-items: center;
    padding: 8px 14px;
    border-radius: var(--radius-sm);
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
    color: var(--muted);
    white-space: nowrap;
    transition: background 120ms ease, color 120ms ease;
  }
  .shell-tab:hover { color: var(--fg); background: var(--stripe); }
  .shell-tab.is-active {
    color: var(--accent);
    background: var(--stripe);
    font-weight: 600;
  }
  .shell-logout {
    flex: 0 0 auto;
    padding: 8px 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--muted);
    font: inherit;
    font-size: 13px;
    cursor: pointer;
  }
  .shell-logout:hover { color: var(--err); border-color: var(--err); }

  .shell-content { flex: 1 1 auto; min-height: 0; }
  .shell-content iframe {
    border: 0;
    width: 100%;
    height: calc(100vh - 57px);
    background: var(--bg);
  }

  /* === Two-column page layout: filters (left) + content (right) === */
  .page-grid {
    display: grid;
    grid-template-columns: 220px 1fr;
    gap: 28px;
    margin: 24px 0 96px;
  }
  .filters-col {
    position: sticky;
    top: 16px;
    align-self: start;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .filters-col .control-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .filters-col label {
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .filters-col select {
    font: inherit;
    font-size: 13px;
    padding: 9px 34px 9px 12px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--fg);
    width: 100%;
    appearance: none;
    -webkit-appearance: none;
    -moz-appearance: none;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'><path fill='none' stroke='%2337332c' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round' d='M1 1.5l5 5 5-5'/></svg>");
    background-repeat: no-repeat;
    background-position: right 12px center;
    background-size: 10px auto;
    transition: border-color 120ms ease, box-shadow 120ms ease;
  }
  .filters-col select:hover { border-color: rgba(55,51,44,0.35); }
  .filters-col select:focus-visible {
    outline: 0;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(93,96,238,0.18);
  }
  .filters-col select:disabled { opacity: 0.45; cursor: not-allowed; }

  /* === Hero images === */
  .hero-img, .hero {
    width: 100%;
    max-width: 240px;
    aspect-ratio: 4 / 3;
    height: auto;
    object-fit: cover;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    display: block;
    margin: 0 0 12px;
  }
  .hero-sm {
    width: 64px;
    height: 48px;
    object-fit: cover;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
  }

  /* === Technical-details accordion === */
  details.tech-details {
    margin: 32px 0 0;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: transparent;
  }
  details.tech-details > summary {
    cursor: pointer;
    padding: 12px 16px;
    font-size: 13px;
    font-weight: 600;
    color: var(--muted);
    list-style: none;
    user-select: none;
  }
  details.tech-details > summary::-webkit-details-marker { display: none; }
  details.tech-details > summary::after {
    content: "\\25B8";
    float: right;
    transition: transform 120ms ease;
  }
  details.tech-details[open] > summary::after { transform: rotate(90deg); }
  details.tech-details > .tech-body {
    padding: 0 16px 16px;
    border-top: 1px solid var(--border);
  }

  /* === Public landing (password gate) === */
  .gate-root {
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 32px;
    background: var(--bg);
  }
  .gate-card {
    width: 100%;
    max-width: 360px;
    background: var(--bg);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    padding: 32px 28px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
    box-shadow: 0 6px 24px rgba(55,51,44,0.08);
  }
  .gate-card .brand-mark { justify-content: center; margin-bottom: 4px; }
  .gate-card h1 {
    font-size: 18px;
    font-weight: 600;
    margin: 0;
    text-align: center;
    color: var(--fg);
  }
  .gate-card p.gate-hint {
    margin: 0;
    font-size: 13px;
    color: var(--muted);
    text-align: center;
  }
  .gate-card input[type="password"] {
    font: inherit;
    font-size: 14px;
    padding: 10px 12px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--bg);
    color: var(--fg);
  }
  .gate-card input[type="password"]:focus-visible {
    outline: 0;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(93,96,238,0.18);
  }
  .gate-card button {
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    padding: 10px 12px;
    border: 0;
    border-radius: var(--radius-sm);
    background: var(--accent);
    color: #fff;
    cursor: pointer;
  }
  .gate-card button:hover { background: #4e51be; }
  .gate-error {
    min-height: 18px;
    font-size: 13px;
    color: var(--err);
    text-align: center;
  }

  /* === Brand logo image === */
  .brand-logo-img { height: 36px; width: auto; display: block; }

  /* === Housing viewer extras (status badges, label cells, content wrap) === */
  .housing-content { padding: 16px 0; max-width: 1100px; }
  .housing-content h2 { margin: 24px 0 12px; }
  .housing-content h3 { font-size: 15px; font-weight: 600; margin: 16px 0 8px; color: var(--muted); }
  .label-cell {
    font-weight: 600;
    width: 30%;
    color: var(--muted);
    font-size: 12px;
  }
  .missing {
    color: var(--faint);
    font-style: italic;
    font-size: 12px;
  }
  .badge-ok, .badge-partial, .badge-failed {
    display: inline-block;
    border-radius: 3px;
    padding: 1px 6px;
    font-size: 11px;
    font-weight: 600;
  }
  .badge-ok      { background: rgba(29,107,58,0.12);  color: var(--ok); }
  .badge-partial { background: rgba(166,95,31,0.15);  color: var(--warn); }
  .badge-failed  { background: rgba(160,38,36,0.12);  color: var(--err); }

  .gallery-grid { display: flex; flex-wrap: wrap; gap: 6px; }
  .section-block { margin-bottom: 20px; }
  ul.item-list { padding-left: 18px; margin: 4px 0; }
  ul.item-list li { margin-bottom: 3px; }
  .prop-list { list-style: none; padding: 0; margin: 0; }
  .prop-list li {
    display: flex;
    gap: 8px;
    border-bottom: 1px solid var(--border);
    padding: 6px 0;
    font-size: 13px;
  }
  .prop-list li .pos { font-weight: 600; min-width: 24px; color: var(--muted); }
  .hidden { display: none; }

  /* === Listing images (housing viewer) — kept for backwards compat === */
  .listing-hero-img {
    width: 100%;
    max-width: 240px;
    aspect-ratio: 4 / 3;
    height: auto;
    object-fit: cover;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    display: block;
  }
  .listing-thumb-img {
    width: 64px;
    height: 48px;
    object-fit: cover;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    display: inline-block;
  }

  /* === Responsive === */
  @media (max-width: 820px) {
    .page-grid { grid-template-columns: 1fr; }
    .filters-col {
      position: static;
      flex-direction: row;
      flex-wrap: wrap;
      gap: 12px;
    }
    .filters-col .control-group { flex: 1 1 160px; }
  }
  @media (max-width: 600px) {
    .shell-topbar { gap: 12px; padding: 10px 16px; }
    .shell-tabs { order: 3; flex-basis: 100%; }
    .shell-content iframe { height: calc(100vh - 110px); }
  }
"""


AUTH_SCRIPT_TAG = '<script src="/assets/js/auth.js"></script>'

FAVICON_HREF = "/assets/img/favicon.png"

TABS = (
    {"key": "log",     "label": "Blog",    "href": "/private/log/"},
    {"key": "housing", "label": "Housing", "href": "/private/housing/"},
    {"key": "courses", "label": "Courses", "href": "/private/courses/"},
)

# Web-publishing root inside the CEL external repo.
# GitHub Pages serves this subdirectory (main:/docs). Override via CEL_EXTERNAL_ROOT env var for CI.
EXTERNAL_REPO_ROOT = Path(os.environ.get(
    "CEL_EXTERNAL_ROOT",
    "/Users/cagdas/Desktop/dev/englishcollege/docs",
))


def write_external_css(repo_root: Path) -> Path:
    """Write combined dashboard CSS to <repo_root>/assets/css/dashboard.css."""
    target = repo_root / "assets" / "css" / "dashboard.css"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(SHARED_CSS + "\n" + SHELL_CSS, encoding="utf-8")
    return target


def render_favicon_tag() -> str:
    return f'<link rel="icon" type="image/png" href="{FAVICON_HREF}">'


def render_page_chrome(eyebrow: str, subtitle: str) -> str:
    """Standard page header — eyebrow + subtitle, no logo, no h1."""
    return (
        '<header class="dashboard-header">'
        '<div class="brand-text">'
        f'<p class="eyebrow">{eyebrow}</p>'
        f'<p class="subtitle">{subtitle}</p>'
        '</div>'
        '</header>'
    )


def render_sync_status_card(label: str, last_synced: str, is_ok: bool = True) -> str:
    """Status banner matching the log-page pattern."""
    status_class = "status-ok" if is_ok else "status-error"
    status_modifier = "" if is_ok else " error"
    return (
        f'<section class="status {status_class}{status_modifier}">'
        f'<p class="status-label">{label}</p>'
        f'<p>Last checked on <strong>{last_synced}</strong> (San Diego time).</p>'
        '</section>'
    )


_SHELL_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <script src="/assets/js/auth.js"></script>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>English College \u2014 Internal Dashboard</title>
  <link rel="icon" type="image/png" href="/assets/img/favicon.png">
  <link rel="stylesheet" href="/assets/css/dashboard.css">
</head>
<body>
  <div class="shell-root">
    <header class="shell-topbar">
      <a class="shell-brand" href="/private/" aria-label="English College">
        <img class="brand-logo-img" src="/assets/img/cel-logo-multicolor.svg" alt="English College">
      </a>
      <nav class="shell-tabs" aria-label="Dashboard sections">
        <a class="shell-tab" href="#log" data-target="log">Blog</a>
        <a class="shell-tab" href="#housing" data-target="housing">Housing</a>
        <a class="shell-tab" href="#courses" data-target="courses">Courses</a>
      </nav>
      <button class="shell-logout" id="shell-logout" type="button">Sign out</button>
    </header>
    <main class="shell-content">
      <iframe id="shell-frame" title="Dashboard content" src="/private/log/"></iframe>
    </main>
  </div>
  <script>
  (function () {
    var TARGETS = {
      log:     '/private/log/',
      housing: '/private/housing/',
      courses: '/private/courses/'
    };
    var frame = document.getElementById('shell-frame');
    var tabs = document.querySelectorAll('.shell-tab');
    function pick() {
      var key = (location.hash || '#log').slice(1);
      if (!TARGETS[key]) key = 'log';
      return key;
    }
    function apply() {
      var key = pick();
      if (frame.dataset.key !== key) {
        frame.dataset.key = key;
        frame.src = TARGETS[key];
      }
      tabs.forEach(function (a) {
        a.classList.toggle('is-active', a.getAttribute('data-target') === key);
      });
    }
    window.addEventListener('hashchange', apply);
    apply();
    document.getElementById('shell-logout').addEventListener('click', function () {
      try { sessionStorage.removeItem('cel_unlocked'); } catch (_) {}
      location.replace('/');
    });
  })();
  </script>
</body>
</html>
"""


def write_shell_html(repo_root: Path) -> Path:
    """Write the dashboard shell HTML to <repo_root>/private/index.html."""
    target = repo_root / "private" / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_SHELL_HTML, encoding="utf-8")
    return target
