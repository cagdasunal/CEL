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
LOGO_SVG_PATH = _REPO_ROOT / "sites" / "cel" / "shared" / "cel-logo-multicolor.svg"

# Brand palette — mirrored from sites/cel/site.json css_variables.
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
    --fs-xs: 11px;
    --fs-sm: 12px;
    --fs-md: 13px;
    --fs-base: 14px;
    --fs-lg: 18px;
    --fs-xl: 20px;
    --fs-doc-body: 16px;
    --fs-doc-h1: 30px;
    --fs-doc-h2: 22px;
    --radius: 10px;
    --radius-sm: 6px;
  }
  * { box-sizing: border-box; }
  html, body { background: var(--bg); }
  body {
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: var(--fs-base);
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    margin: 0;
  }

  /* === Dashboard shell === */
  .dashboard-shell {
    width: 100%;
    margin: 0;
    padding: 20px 28px 0;
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
    font-size: var(--fs-xl);
    font-weight: 600;
    letter-spacing: -0.01em;
  }
  .brand-text .subtitle,
  .brand-text p {
    margin: 0;
    font-size: var(--fs-md);
    color: var(--muted);
  }
  .brand-text .eyebrow {
    font-size: var(--fs-xs);
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
    font-size: var(--fs-xs);
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .controls select {
    font: inherit;
    font-size: var(--fs-md);
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
    font-size: var(--fs-lg);
    font-weight: 600;
    margin: 40px 0 12px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 6px;
  }
  p.lede {
    margin: 0 0 24px;
    color: var(--muted);
    font-size: var(--fs-base);
  }

  /* === Scroll containers === */
  .scroll-x { overflow-x: auto; }

  /* === Tables === */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0;
    font-size: var(--fs-base);
  }
  th, td {
    text-align: left;
    padding: 10px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  td.is-vmid {
    vertical-align: middle;
  }
  th {
    font-weight: 600;
    font-size: var(--fs-sm);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
  }
  tr:last-child td { border-bottom: 0; }
  tbody tr:hover td { background: var(--stripe); }

  /* === KV table === */
  .kv-table { width: 100%; border-collapse: collapse; font-size: var(--fs-base); margin: 8px 0; }
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
    font-size: var(--fs-sm);
    width: 34%;
  }
  .kv-table .v { color: var(--fg); }

  /* === Mono / pre === */
  .mono, pre.mono {
    font-family: "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
    font-size: var(--fs-sm);
    background: var(--stripe);
    padding: 13px 6px;
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
    font-size: var(--fs-sm);
    font-weight: 600;
  }

  /* === Status indicators === */
  .status-ok    { color: var(--ok); }
  .status-partial { color: var(--warn); }
  .status-failed  { color: var(--err); }
  .dash { color: var(--faint); }
  .rt { color: var(--muted); font-size: var(--fs-sm); }

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
  .status-label { font-size: var(--fs-xl); font-weight: 600; margin: 0 0 6px; }
  .status-ok .status-label  { color: #1d6b3a; }
  .status-error .status-label { color: #a02624; }
  .subtle { color: var(--muted); font-size: var(--fs-md); margin: 6px 0 0; }

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
    font-size: var(--fs-md);
    margin-right: 10px;
  }
  .empty { color: var(--muted); font-style: italic; padding: 16px 0; }

  /* === Slug / lang / when cell types (log.html table) === */
  td.slug {
    font-family: "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
    font-size: var(--fs-md);
    word-break: break-word;
  }
  td.lang {
    color: var(--muted);
    white-space: nowrap;
    font-size: var(--fs-md);
  }
  td.when { color: var(--muted); white-space: nowrap; font-size: var(--fs-md); }

  /* === Links === */
  a { color: var(--fg); text-decoration: underline; }
  a:hover { color: var(--accent); }

  /* === Footer === */
  footer {
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    font-size: var(--fs-md);
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
    .brand-text h1 { font-size: var(--fs-xl); }
    .controls-inner {
      flex-direction: column;
      align-items: stretch;
      justify-content: stretch;
    }
    .controls .control-group { width: 100%; }
    .controls select { width: 100%; min-width: 0; }
  }
  @media (max-width: 500px) {
    table { font-size: var(--fs-md); }
    td.slug { font-size: var(--fs-sm); }
    h2 { font-size: var(--fs-lg); }
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
# Consumers: cel.englishcollege.com/admin/index.html (shell),
#            cel.englishcollege.com/index.html (password gate),
#            cel.englishcollege.com/admin/housing/index.html (listing imgs).
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

  /* === Top-bar shell v3 (single row: logo | tabs | logout) === */
  .shell-header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 10px 20px;
    background: var(--bg);
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 20;
  }
  .shell-header .shell-brand {
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
    text-decoration: none;
  }
  .shell-header .shell-brand .brand-logo-img { height: 32px; }
  .shell-logout {
    flex: 0 0 auto;
    margin-left: auto;
    padding: 8px 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--muted);
    font: inherit;
    font-size: var(--fs-md);
    cursor: pointer;
  }
  .shell-logout:hover { color: var(--err); border-color: var(--err); }

  .shell-tabs {
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
  }
  .shell-tab {
    display: inline-flex;
    align-items: center;
    padding: 8px 14px;
    border-radius: var(--radius-sm);
    text-decoration: none;
    font-size: var(--fs-base);
    font-weight: 500;
    color: var(--muted);
    white-space: nowrap;
    transition: background 120ms ease, color 120ms ease;
    cursor: pointer;
  }
  .shell-tab:hover { color: var(--fg); background: var(--stripe); }
  .shell-tab.is-active,
  [data-topbar].is-active > .shell-tab {
    color: var(--accent);
    background: var(--stripe);
    font-weight: 600;
  }

  .shell-tab-dropdown {
    position: relative;
    display: inline-block;
  }
  .shell-tab-dropdown > summary { list-style: none; }
  .shell-tab-dropdown > summary::-webkit-details-marker { display: none; }
  .shell-tab-chevron {
    margin-left: 6px;
    width: 12px;
    height: 12px;
    opacity: 0.65;
    flex-shrink: 0;
    transition: transform 150ms ease, opacity 150ms ease;
  }
  .shell-tab-dropdown[open] > summary .shell-tab-chevron { transform: rotate(180deg); opacity: 1; }
  [data-topbar].is-active > .shell-tab .shell-tab-chevron { opacity: 1; }
  .shell-tab-submenu {
    position: absolute;
    left: 0;
    top: calc(100% + 6px);
    margin: 0;
    padding: 4px;
    list-style: none;
    background: var(--bg);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    box-shadow: 0 8px 24px rgba(55,51,44,0.12);
    min-width: 160px;
    z-index: 30;
  }
  .shell-tab-submenu li { margin: 0; padding: 0; }
  .shell-tab-subitem {
    display: block;
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    text-decoration: none;
    font-size: var(--fs-base);
    color: var(--fg);
    white-space: nowrap;
  }
  .shell-tab-subitem:hover { background: var(--stripe); color: var(--accent); }
  .shell-tab-subitem.is-active { background: var(--stripe); color: var(--accent); font-weight: 600; }

  .shell-content { flex: 1 1 auto; min-height: 0; }
  .shell-content iframe {
    border: 0;
    width: 100%;
    height: calc(100vh - 58px);
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
    font-size: var(--fs-xs);
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .filters-col select {
    font: inherit;
    font-size: var(--fs-md);
    padding: 9px 34px 9px 12px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: #EAE3D1;
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
    font-size: var(--fs-md);
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
    font-size: var(--fs-lg);
    font-weight: 600;
    margin: 0;
    text-align: center;
    color: var(--fg);
  }
  .gate-card p.gate-hint {
    margin: 0;
    font-size: var(--fs-md);
    color: var(--muted);
    text-align: center;
  }
  .gate-card input[type="password"],
  .gate-card input[type="email"],
  .gate-card input[type="text"] {
    font: inherit;
    font-size: var(--fs-base);
    padding: 10px 12px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--bg);
    color: var(--fg);
  }
  .gate-card input[type="password"]:focus-visible,
  .gate-card input[type="email"]:focus-visible,
  .gate-card input[type="text"]:focus-visible {
    outline: 0;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(93,96,238,0.18);
  }
  /* Tertiary action (Forgot password? / Back / Go to sign in) — low-emphasis
     text link, never a second filled CTA. (NN/g, IBM Carbon, Material 3.) */
  .gate-link {
    align-self: center;
    background: none;
    border: 0;
    padding: 6px 8px;
    font: inherit;
    font-size: var(--fs-md);
    font-weight: 500;
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 2px;
    cursor: pointer;
    border-radius: var(--radius-sm);
  }
  .gate-link:hover { color: #4e51be; }
  .gate-link:focus-visible { outline: 0; box-shadow: 0 0 0 3px rgba(93,96,238,0.35); }
  .gate-ok { font-size: var(--fs-md); color: var(--ok); text-align: center; min-height: 18px; }
  .gate-card[hidden] { display: none; }
  /* Visible field labels — placeholders never replace labels (NN/g + WCAG 3.3.2). */
  .gate-field { display: flex; flex-direction: column; gap: 6px; align-items: stretch; }
  .gate-label { font-size: var(--fs-sm); font-weight: 600; color: var(--muted); text-align: left; }
  /* Primary CTA — exactly ONE high-emphasis button per view (WCAG-AA indigo pill,
     white-on-#5d60ee = 4.8:1). Full-width via the card's stretch alignment. */
  .gate-card button[type="submit"] {
    font: inherit;
    font-size: var(--fs-base);
    font-weight: 600;
    padding: 13px 22px;
    border: 0;
    border-radius: 999px;
    background: var(--accent);
    color: #fff;
    cursor: pointer;
    box-shadow: 0 1px 2px rgba(55,51,44,0.12);
    transition: background .15s ease, transform .15s ease;
  }
  .gate-card button[type="submit"]:hover { background: #4e51be; transform: translateY(-1px); }
  .gate-card button[type="submit"]:active { transform: translateY(0); }
  .gate-card button[type="submit"]:focus-visible { outline: 0; box-shadow: 0 0 0 3px rgba(93,96,238,0.35); }
  .gate-card button[type="submit"]:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
  /* Neutral status note (e.g. the forgot-password confirmation) — NOT an error. */
  .gate-note { min-height: 18px; font-size: var(--fs-md); color: var(--muted); text-align: center; }
  /* Error — color + icon + text, never color alone (WCAG 1.4.1); role=alert announces it. */
  .gate-error { font-size: var(--fs-md); color: var(--err); text-align: center; }
  .gate-error:not(:empty) {
    position: relative;
    text-align: left;
    padding: 10px 12px 10px 38px;
    border: 1px solid var(--err);
    border-radius: var(--radius-sm);
    background: rgba(160,38,36,0.09);
    color: var(--err);
    font-weight: 600;
  }
  .gate-error:not(:empty)::before {
    content: "!";
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: var(--err);
    color: #fff;
    font-size: var(--fs-sm);
    font-weight: 700;
    display: grid;
    place-items: center;
    line-height: 1;
  }

  /* === Top-bar user menu (shell) === */
  .shell-user { position: relative; margin-left: auto; flex: 0 0 auto; }
  .shell-user > summary {
    list-style: none;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--fg);
    font: inherit;
    font-size: var(--fs-md);
    cursor: pointer;
  }
  .shell-user > summary::-webkit-details-marker { display: none; }
  .shell-user[open] > summary { border-color: var(--accent); color: var(--accent); }
  .shell-user-menu {
    position: absolute;
    right: 0;
    top: calc(100% + 6px);
    min-width: 240px;
    padding: 12px;
    background: var(--bg);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    box-shadow: 0 8px 24px rgba(55,51,44,0.12);
    z-index: 30;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .shell-user-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }
  .shell-user-field { margin: 0; display: flex; justify-content: space-between; gap: 12px; font-size: var(--fs-sm); }
  .shell-user-k { color: var(--faint); }
  .shell-user-v { color: var(--fg); font-weight: 600; word-break: break-all; text-align: right; }
  .shell-user-action {
    font: inherit;
    font-size: var(--fs-md);
    text-align: left;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--fg);
    cursor: pointer;
  }
  .shell-user-action:hover { background: var(--stripe); }
  .shell-user-signout { color: var(--muted); }
  .shell-user-signout:hover { color: var(--err); border-color: var(--err); }

  /* === Change-password modal (shell) === */
  .cpw-overlay {
    position: fixed;
    inset: 0;
    background: rgba(55,51,44,0.45);
    display: grid;
    place-items: center;
    padding: 24px;
    z-index: 50;
  }
  .cpw-overlay[hidden] { display: none; }
  .cpw-modal {
    width: 100%;
    max-width: 380px;
    background: var(--bg);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    box-shadow: 0 12px 40px rgba(55,51,44,0.2);
  }
  .cpw-title { margin: 0; font-size: var(--fs-lg); font-weight: 600; }
  .cpw-readonly {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }
  .cpw-field { margin: 0; display: flex; justify-content: space-between; gap: 12px; font-size: var(--fs-sm); }
  .cpw-k { color: var(--faint); }
  .cpw-v { color: var(--fg); font-weight: 600; word-break: break-all; text-align: right; }
  .cpw-label { display: flex; flex-direction: column; gap: 4px; font-size: var(--fs-sm); color: var(--muted); }
  .cpw-input {
    font: inherit;
    font-size: var(--fs-base);
    padding: 10px 12px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--bg);
    color: var(--fg);
  }
  .cpw-input:focus-visible { outline: 0; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(93,96,238,0.18); }
  .cpw-actions { display: flex; justify-content: flex-end; gap: 10px; }
  .cpw-btn {
    font: inherit;
    font-size: var(--fs-base);
    font-weight: 600;
    padding: 9px 18px;
    border-radius: 999px;
    border: 1px solid var(--border-strong);
    cursor: pointer;
  }
  .cpw-btn:focus-visible { outline: 0; box-shadow: 0 0 0 3px rgba(93,96,238,0.35); }
  /* Cancel = the paired negative action → medium-emphasis ghost (Carbon). */
  .cpw-cancel { background: transparent; color: var(--fg); }
  .cpw-cancel:hover { background: var(--stripe); }
  /* Save = the single primary action → filled indigo pill. */
  .cpw-save { background: var(--accent); color: #fff; border-color: var(--accent); }
  .cpw-save:hover { background: #4e51be; }
  .cpw-save:disabled { opacity: 0.5; cursor: not-allowed; }
  .cpw-status { min-height: 18px; font-size: var(--fs-md); color: var(--muted); }
  .cpw-status.is-ok { color: var(--ok); }
  .cpw-status.is-error { color: var(--err); }

  /* === Brand logo image === */
  .brand-logo-img { height: 36px; width: auto; display: block; }

  /* === Housing viewer extras (status badges, label cells, content wrap) === */
  .housing-content { padding: 16px 0; max-width: 100%; }
  .housing-content h2 { margin: 24px 0 12px; }
  .housing-content h3 { font-size: var(--fs-base); font-weight: 600; margin: 16px 0 8px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }
  .label-cell {
    font-weight: 600;
    width: 30%;
    color: var(--muted);
    font-size: var(--fs-sm);
  }
  .missing {
    color: var(--faint);
    font-style: italic;
    font-size: var(--fs-sm);
  }
  .badge-ok, .badge-partial, .badge-failed {
    display: inline-block;
    border-radius: 3px;
    padding: 1px 6px;
    font-size: var(--fs-xs);
    font-weight: 600;
  }
  .badge-ok      { background: rgba(29,107,58,0.12);  color: var(--ok); }
  .badge-partial { background: rgba(166,95,31,0.15);  color: var(--warn); }
  .badge-failed  { background: rgba(160,38,36,0.12);  color: var(--err); }
  .badge-when    { font-size: var(--fs-xs); color: var(--muted); font-weight: 400; }

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
    font-size: var(--fs-base);
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
  /* === Responsive tables (narrow viewports) === */
  @media (max-width: 820px) {
    table { display: block; overflow-x: auto; white-space: nowrap; }
    .kv-table { display: table; white-space: normal; }
    .kv-table tr, .kv-table tbody, .kv-table tbody tr { display: table-row; }
    .shell-header { padding: 8px 12px; gap: 8px; flex-wrap: wrap; }
    .shell-content iframe { height: calc(100vh - 110px); }
  }
  @media (max-width: 600px) {
    .dashboard-shell { padding: 12px 16px 0; }
    .shell-tab { padding: 6px 10px; font-size: var(--fs-md); }
    .shell-content iframe { height: calc(100vh - 140px); }
  }

  /* === Client Docs: REAL pages at /admin/docs/ and /admin/docs/<slug>/
     (built by tools/dashboard_docs.py). Each page renders the dashboard top bar
     (render_docs_topbar) under .shell-root, so the nav is always present — no
     iframe, no frame-buster. These rules style the centered "Guides" index
     (the card list) and the single-doc reading view. */
  .docs-page { padding: 44px 24px 80px; }

  /* Guides index (landing) */
  .docs-index { max-width: 780px; margin: 0 auto; }
  .docs-index-head { margin: 0 0 28px; }
  .docs-index-eyebrow {
    margin: 0 0 6px;
    font-size: var(--fs-xs); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.12em; color: var(--accent-warm);
  }
  .docs-index-title { margin: 0 0 10px; font-size: var(--fs-doc-h1); line-height: 1.15; font-weight: 700; letter-spacing: -0.01em; }
  .docs-cards { display: flex; flex-direction: column; gap: 14px; }
  .docs-card {
    display: block; padding: 22px 24px;
    background: var(--panel); border: 1px solid var(--border);
    border-radius: var(--radius); color: var(--fg); text-decoration: none;
    transition: border-color 120ms ease, transform 120ms ease, box-shadow 120ms ease;
  }
  .docs-card:hover { border-color: var(--accent); transform: translateY(-1px); box-shadow: 0 6px 18px rgba(0, 0, 0, 0.07); }
  .docs-card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .docs-card-title { margin: 0 0 6px; padding: 0; border: 0; font-size: var(--fs-xl); font-weight: 600; line-height: 1.3; color: var(--fg); }
  .docs-card-sub { margin: 0 0 16px; font-size: var(--fs-base); color: var(--muted); line-height: 1.55; }
  .docs-card-meta { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
  .docs-card-cta { font-size: var(--fs-md); font-weight: 600; color: var(--accent); }
  .docs-card-updated { font-size: var(--fs-sm); color: var(--faint); }

  /* Single-doc reading view */
  .doc-view { max-width: 720px; margin: 0 auto; }
  .doc-back {
    display: inline-flex; align-items: center; gap: 6px;
    margin: 0 0 26px; font-size: var(--fs-md); font-weight: 500;
    color: var(--muted); text-decoration: none;
  }
  .doc-back:hover { color: var(--accent); }
  .doc-back:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
  .doc-prose { color: var(--fg); font-size: var(--fs-doc-body); line-height: 1.7; }
  .doc-eyebrow {
    margin: 0 0 6px;
    font-size: var(--fs-xs); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.12em; color: var(--accent-warm);
  }
  .doc-title { margin: 0 0 6px; font-size: var(--fs-doc-h1); line-height: 1.2; font-weight: 700; letter-spacing: -0.01em; }
  .doc-updated { margin: 0 0 32px; font-size: var(--fs-sm); color: var(--faint); }
  .doc-prose h2 {
    margin: 40px 0 12px; font-size: var(--fs-doc-h2); font-weight: 600; line-height: 1.25;
    letter-spacing: -0.01em; padding-bottom: 8px; border-bottom: 1px solid var(--border);
  }
  .doc-prose h3 { margin: 28px 0 8px; font-size: var(--fs-lg); font-weight: 600; }
  .doc-prose h4 {
    margin: 22px 0 6px; font-size: var(--fs-base); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted);
  }
  .doc-prose p { margin: 0 0 16px; }
  .doc-prose ul, .doc-prose ol { margin: 0 0 16px; padding-left: 22px; }
  .doc-prose li { margin: 0 0 7px; }
  .doc-prose strong { font-weight: 600; }
  .doc-prose a { color: var(--accent); text-decoration: underline; text-underline-offset: 2px; }
  .doc-prose code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.88em; background: var(--stripe);
    border: 1px solid var(--border); border-radius: 5px; padding: 1px 6px; white-space: nowrap;
  }
  .doc-prose blockquote.doc-quote {
    margin: 0 0 16px; padding: 4px 16px;
    border-left: 3px solid var(--accent-warm);
    background: var(--notice-bg); color: var(--notice-fg);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  }
  .doc-prose blockquote.doc-quote p:last-child { margin-bottom: 0; }
  .doc-prose hr { border: 0; border-top: 1px solid var(--border); margin: 32px 0; }
  .doc-pre {
    margin: 0 0 16px; padding: 14px 16px;
    background: var(--panel); border: 1px solid var(--border);
    border-radius: var(--radius-sm); overflow-x: auto; font-size: var(--fs-md);
  }

  /* Reference tables (event names) */
  .doc-table-wrap { margin: 0 0 20px; overflow-x: auto; border: 1px solid var(--border); border-radius: var(--radius-sm); }
  .doc-table { width: 100%; border-collapse: collapse; font-size: var(--fs-base); margin: 0; }
  .doc-table th, .doc-table td { text-align: left; padding: 10px 14px; vertical-align: top; border-bottom: 1px solid var(--border); }
  .doc-table thead th {
    font-size: var(--fs-sm); text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--muted); font-weight: 600; background: var(--stripe);
  }
  .doc-table tbody tr:last-child td { border-bottom: 0; }
  .doc-table tbody tr:nth-child(even) { background: var(--stripe); }
  .doc-table td code { white-space: nowrap; }
  .doc-empty { padding: 40px; color: var(--muted); }

  @media (max-width: 720px) {
    .docs-page { padding: 28px 16px 60px; }
    .docs-card { padding: 18px 18px; }
  }
"""


# Gate scripts for /admin/* sub-pages: dashboard-config.js MUST load before
# auth.js (auth.js reads window.CEL_DISPATCH_URL to validate the session).
# _SHELL_HTML inlines the same order for the main dashboard shell.
AUTH_SCRIPT_TAG = ('<script src="/assets/js/dashboard-config.js"></script>\n'
                   '  <script src="/assets/js/auth.js"></script>')

FAVICON_HREF = "/assets/img/favicon.png"

TABS = (
    {"key": "log",     "label": "WEGLOT",  "href": "/admin/log/"},
    {"key": "housing", "label": "Housing", "href": "/admin/housing/"},
    {"key": "courses", "label": "Courses", "href": "/admin/courses/"},
    {"key": "images",  "label": "IMAGES",  "href": "/admin/images/"},
)

def _default_external_root() -> Path:
    """Resolve the CEL external-repo docs root.

    Priority:
      1. CEL_EXTERNAL_ROOT env var (set by fidelo-sync.yml CI).
      2. Auto-detect — if <repo-root>/docs/index.html exists, we're inside the
         external repo itself (content-pipeline.yml CI runs from cagdasunal/cel).
         Monorepo's docs/ dir has no index.html, so the marker is unambiguous.
      3. Fallback — local Mac dev path (monorepo convention).
    """
    env = os.environ.get("CEL_EXTERNAL_ROOT")
    if env:
        return Path(env)
    repo_root = Path(__file__).resolve().parents[1]
    candidate = repo_root / "docs"
    if (candidate / "index.html").exists():
        return candidate
    return Path("/Users/cagdas/Desktop/dev/englishcollege/docs")


EXTERNAL_REPO_ROOT = _default_external_root()


def write_external_css(repo_root: Path) -> Path:
    """Write combined dashboard CSS to <repo_root>/assets/css/dashboard.css."""
    target = repo_root / "assets" / "css" / "dashboard.css"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(SHARED_CSS + "\n" + SHELL_CSS, encoding="utf-8")
    return target


def write_dashboard_config(repo_root: Path) -> Path:
    """Write the public dispatch-proxy config to <repo_root>/assets/js/dashboard-config.js.

    The Cloudflare Worker URL is a GitHub Actions Variable (DASHBOARD_DISPATCH_PROXY_URL),
    not committed to the repo. The login, shell, and reset pages read
    window.CEL_DISPATCH_URL from this generated file.

    Defensive: when the env var is empty AND the file already exists, leave it
    untouched so an env-less regen (e.g. the daily monorepo run) never blanks a
    good URL. Only write when the env value is non-empty, or when the file is absent.
    """
    target = repo_root / "assets" / "js" / "dashboard-config.js"
    url = os.environ.get("DASHBOARD_DISPATCH_PROXY_URL", "").strip()
    if not url and target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("window.CEL_DISPATCH_URL = " + json.dumps(url) + ";\n", encoding="utf-8")
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


# Section -> which top-level nav group it belongs to (drives active highlighting).
_SECTION_GROUP = {
    "offers": "offers", "images": "images", "docs": "docs",
    "translations": "weglot", "log": "weglot",
    "summaries": "seo", "files": "seo",
    "housing": "fidelo", "courses": "fidelo",
}


# The dashboard top bar, rendered on EVERY admin page. The dashboard is a set of
# REAL pages now (not an iframe SPA): every tab is a real link to /admin/<section>/
# and `active` is highlighted. Pairs with ADMIN_CHROME_MODAL + ADMIN_CHROME_JS
# (the account menu's change-password + sign-out). Reuses the .shell-* classes in
# dashboard.css. Used by every section builder + tools/dashboard_docs.py.
def render_topbar(active: str = "offers") -> str:
    group = _SECTION_GROUP.get(active, "")
    chevron = (
        '<svg class="shell-tab-chevron" aria-hidden="true" viewBox="0 0 12 12" '
        'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" '
        'stroke-linejoin="round"><polyline points="3 4.5 6 7.5 9 4.5"></polyline></svg>'
    )
    def tab(key):
        return "shell-tab is-active" if active == key else "shell-tab"
    def grp(g):
        return "shell-tab is-active" if group == g else "shell-tab"
    def sub(key):
        return "shell-tab-subitem is-active" if active == key else "shell-tab-subitem"
    return f"""\
    <header class="shell-header">
      <a class="shell-brand" href="/admin/offers/" aria-label="English College">
        <img class="brand-logo-img" src="/assets/img/cel-logo-multicolor.svg" alt="English College">
      </a>
      <nav class="shell-tabs" aria-label="Dashboard sections">
        <a class="{tab('offers')}" href="/admin/offers/">OFFERS</a>
        <a class="{tab('images')}" href="/admin/images/">IMAGES</a>
        <a class="{tab('docs')}" href="/admin/docs/">DOCS</a>
        <details class="shell-tab-dropdown">
          <summary class="{grp('weglot')}">WEGLOT {chevron}</summary>
          <ul class="shell-tab-submenu">
            <li><a class="{sub('translations')}" href="/admin/translations/">Translations</a></li>
            <li><a class="{sub('log')}" href="/admin/log/">Synced Posts</a></li>
          </ul>
        </details>
        <details class="shell-tab-dropdown">
          <summary class="{grp('seo')}">SEO {chevron}</summary>
          <ul class="shell-tab-submenu">
            <li><a class="{sub('summaries')}" href="/admin/summaries/">Summaries</a></li>
            <li><a class="{sub('files')}" href="/admin/files/">Files</a></li>
          </ul>
        </details>
        <details class="shell-tab-dropdown">
          <summary class="{grp('fidelo')}">FIDELO {chevron}</summary>
          <ul class="shell-tab-submenu">
            <li><a class="{sub('housing')}" href="/admin/housing/">Housing</a></li>
            <li><a class="{sub('courses')}" href="/admin/courses/">Courses</a></li>
          </ul>
        </details>
      </nav>
      <details class="shell-user" id="shell-user">
        <summary class="shell-user-trigger"><span id="shell-user-name">Account</span> {chevron}</summary>
        <div class="shell-user-menu">
          <div class="shell-user-info">
            <p class="shell-user-field"><span class="shell-user-k">Name</span><span class="shell-user-v" id="shell-user-fullname">&mdash;</span></p>
            <p class="shell-user-field"><span class="shell-user-k">Email</span><span class="shell-user-v" id="shell-user-email">&mdash;</span></p>
          </div>
          <button type="button" class="shell-user-action" id="shell-change-pw">Change password</button>
          <button type="button" class="shell-user-action shell-user-signout" id="shell-logout">Sign out</button>
        </div>
      </details>
    </header>"""


# The change-password modal — rendered once per admin page, driven by ADMIN_CHROME_JS.
ADMIN_CHROME_MODAL = """\
  <div class="cpw-overlay" id="cpw-overlay" hidden>
    <form class="cpw-modal" id="cpw-form" autocomplete="off">
      <h2 class="cpw-title">Change password</h2>
      <div class="cpw-readonly">
        <p class="cpw-field"><span class="cpw-k">First name</span><span class="cpw-v" id="cpw-first">&mdash;</span></p>
        <p class="cpw-field"><span class="cpw-k">Last name</span><span class="cpw-v" id="cpw-last">&mdash;</span></p>
        <p class="cpw-field"><span class="cpw-k">Email</span><span class="cpw-v" id="cpw-email">&mdash;</span></p>
      </div>
      <label class="cpw-label">Current password<input type="password" id="cpw-current" class="cpw-input" autocomplete="current-password" required></label>
      <label class="cpw-label">New password<input type="password" id="cpw-new" class="cpw-input" autocomplete="new-password" required></label>
      <label class="cpw-label">Confirm new password<input type="password" id="cpw-confirm" class="cpw-input" autocomplete="new-password" required></label>
      <div class="cpw-actions">
        <button type="button" class="cpw-btn cpw-cancel" id="cpw-cancel">Cancel</button>
        <button type="submit" class="cpw-btn cpw-save" id="cpw-save">Save</button>
      </div>
      <div class="cpw-status" id="cpw-status" role="status" aria-live="polite"></div>
    </form>
  </div>"""


# Account-menu behavior for every admin page: identity (from the validated
# session token auth.js sets via window.__CEL_USER__), sign-out, and the
# change-password flow (double SHA-256 -> the cel-dashboard Cloudflare Worker,
# KV-backed). Extracted verbatim from the old SPA shell so behavior is unchanged;
# it just runs on every real page now (its own IIFE, guarded so it is inert if
# the modal is absent).
ADMIN_CHROME_JS = """\
(function () {
    function setText(id, val) { var el = document.getElementById(id); if (el) el.textContent = val; }
    function fullName(u) { return [u.firstName || '', u.lastName || ''].join(' ').trim() || (u.email || 'Account'); }
    var currentUser = (window.__CEL_USER__ && window.__CEL_USER__.email) ? window.__CEL_USER__ : null;
    var changePwBtn = document.getElementById('shell-change-pw');
    if (currentUser && currentUser.email) {
      setText('shell-user-name', currentUser.firstName || currentUser.email);
      setText('shell-user-fullname', fullName(currentUser));
      setText('shell-user-email', currentUser.email);
      setText('cpw-first', currentUser.firstName || '—');
      setText('cpw-last', currentUser.lastName || '—');
      setText('cpw-email', currentUser.email);
    } else if (changePwBtn) {
      changePwBtn.style.display = 'none';
    }

    var logoutBtn = document.getElementById('shell-logout');
    if (logoutBtn) logoutBtn.addEventListener('click', function () {
      document.cookie = 'cel_session=; Max-Age=0; Path=/; Secure; SameSite=Strict';
      location.replace('/');
    });

    function sha256hex(str) {
      return crypto.subtle.digest('SHA-256', new TextEncoder().encode(str)).then(function (buf) {
        return Array.from(new Uint8Array(buf)).map(function (b) { return b.toString(16).padStart(2, '0'); }).join('');
      });
    }
    function innerHash(pw) { return sha256hex(pw); }
    function pwHashOf(pw) { return sha256hex(pw).then(sha256hex); }

    var DISPATCH_URL = (typeof window.CEL_DISPATCH_URL === 'string') ? window.CEL_DISPATCH_URL : '';
    function callProxy(payload) {
      if (!DISPATCH_URL) return Promise.reject(new Error('Password tool not configured yet.'));
      var m = document.cookie.match(/(?:^|; )cel_session=([^;]*)/);
      payload.token = m ? m[1] : '';
      return fetch(DISPATCH_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        .then(function (resp) {
          return resp.json().catch(function () { return {}; }).then(function (j) {
            return { status: resp.status, ok: resp.ok && j.ok !== false, body: j };
          });
        });
    }

    var overlay = document.getElementById('cpw-overlay');
    var cpwForm = document.getElementById('cpw-form');
    var cpwStatus = document.getElementById('cpw-status');
    var cpwSave = document.getElementById('cpw-save');
    if (changePwBtn && overlay && cpwForm) {
      function closeModal() {
        overlay.setAttribute('hidden', '');
        cpwForm.reset();
        cpwStatus.textContent = '';
        cpwStatus.className = 'cpw-status';
        cpwSave.disabled = false;
      }
      changePwBtn.addEventListener('click', function () {
        var dd = document.getElementById('shell-user');
        if (dd) dd.removeAttribute('open');
        overlay.removeAttribute('hidden');
        document.getElementById('cpw-current').focus();
      });
      document.getElementById('cpw-cancel').addEventListener('click', closeModal);
      overlay.addEventListener('click', function (ev) { if (ev.target === overlay) closeModal(); });
      cpwForm.addEventListener('submit', function (ev) {
        ev.preventDefault();
        if (!currentUser || !currentUser.email) return;
        var cur = document.getElementById('cpw-current').value;
        var nw = document.getElementById('cpw-new').value;
        var cf = document.getElementById('cpw-confirm').value;
        if (!cur || !nw) return;
        if (nw !== cf) {
          cpwStatus.textContent = 'New passwords do not match.';
          cpwStatus.className = 'cpw-status is-error';
          return;
        }
        cpwSave.disabled = true;
        cpwStatus.textContent = 'Saving…';
        cpwStatus.className = 'cpw-status';
        Promise.all([innerHash(cur), pwHashOf(nw)]).then(function (h) {
          return callProxy({ action: 'changepw', email: currentUser.email, cur_hash: h[0], new_pw_hash: h[1] });
        }).then(function (r) {
          if (r.ok) {
            cpwStatus.textContent = '✓ Saved — use your new password next time you sign in.';
            cpwStatus.className = 'cpw-status is-ok';
          } else {
            cpwStatus.textContent = '✗ Current password is incorrect.';
            cpwStatus.className = 'cpw-status is-error';
            cpwSave.disabled = false;
          }
        }).catch(function () {
          cpwStatus.textContent = '✗ Could not save right now. Please try again.';
          cpwStatus.className = 'cpw-status is-error';
          cpwSave.disabled = false;
        });
      });
    }
})();
"""


# Convenience for section builders: the body-top (shell-root open + top bar) and
# the body-tail (account modal + shell-root close + chrome script). A section page
# is:  <body> + render_admin_open(active) + <existing content> + render_admin_close()
#      + </body>
def render_admin_open(active: str = "offers") -> str:
    return '  <div class="shell-root">\n' + render_topbar(active)


def render_admin_close() -> str:
    return ADMIN_CHROME_MODAL + "\n  </div>\n  <script>" + ADMIN_CHROME_JS + "</script>"


_SHELL_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <meta http-equiv="refresh" content="0; url=/admin/offers/">
  <title>English College \u2014 Admin Dashboard</title>
  <link rel="icon" type="image/png" href="/assets/img/favicon.png">
  <script>location.replace('/admin/offers/');</script>
</head>
<body></body>
</html>
"""


def write_shell_html(repo_root: Path) -> Path:
    """Write the dashboard shell HTML to <repo_root>/admin/index.html."""
    target = repo_root / "admin" / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_SHELL_HTML, encoding="utf-8")
    return target
