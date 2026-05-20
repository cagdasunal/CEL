"""Four-part Summary structure — parse + Markdown→HTML (tracker-096).

The redesigned Summary section has four parts:
  - Tagline   (H2, 2-3 words)        → plain text
  - Title     (H3)                   → plain text
  - Paragraph (one short lead block) → plain text
  - Content   (starts at H4, uses H5; the ONLY part with internal links) → rich text

`course` / `housing` / `landing` summaries are generated as ONE Markdown document in
that exact order; this module splits it into the four parts and renders the Content
part to the HTML subset Webflow's RichText field expects (`<h4>/<h5>/<p>/<a>/<strong>
/<em>`). Plain Markdown into a RichText field renders literal `####`, so the CMS
Content write needs real HTML; the three plain parts are written as stripped plain
text. Blog posts keep the single-block path and never touch this module.

Pure stdlib — no dependency on the rest of the tool.
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass

# Heading line: 1-6 leading '#'. Trailing '#'s (ATX-closed headings) are tolerated.
_H_LINE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
# Content headings only: H4 / H5.
_CONTENT_H = re.compile(r"^(#{4,5})\s+(.*?)\s*#*\s*$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


@dataclass(frozen=True)
class FourPartSummary:
    """The four parts parsed out of a generated 4-part Summary Markdown document."""

    tagline: str = ""
    title: str = ""
    paragraph: str = ""
    content_md: str = ""


def _emphasis(s: str) -> str:
    """Apply **bold** / *italic* to already-HTML-escaped text."""
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    return s


def _strip_inline_md(s: str) -> str:
    """Reduce inline Markdown to plain text (for the 3 plain-text fields).

    Links collapse to their anchor text; bold/italic/backtick markers are dropped.
    """
    s = _LINK_RE.sub(r"\1", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = s.replace("`", "")
    return s.strip()


def _inline_md_to_html(text: str) -> str:
    """Render inline Markdown (links + emphasis) to safe HTML.

    Non-link text is HTML-escaped; `[t](u)` becomes `<a href="u">t</a>` with the
    href attribute-escaped. The allowed inline subset matches what the 4-part
    Content contract emits.
    """
    out: list[str] = []
    pos = 0
    for m in _LINK_RE.finditer(text):
        out.append(_emphasis(_html.escape(text[pos:m.start()], quote=False)))
        anchor = _emphasis(_html.escape(m.group(1), quote=False))
        href = _html.escape(m.group(2), quote=True)
        out.append(f'<a href="{href}">{anchor}</a>')
        pos = m.end()
    out.append(_emphasis(_html.escape(text[pos:], quote=False)))
    return "".join(out)


def parse_four_part(markdown: str) -> FourPartSummary:
    """Split a 4-part Summary Markdown document into its four parts.

    Contract (emitted in this order): `## Tagline` → `### Title` → lead paragraph →
    `#### …` Content (H4/H5 + the only links). Tolerant of missing parts — a
    malformed draft returns empty strings for the parts it lacks, so the QA gate
    fails it (and the orchestrator demotes it to MANUAL_REVIEW) rather than crashing.
    """
    tagline = ""
    title = ""
    para_lines: list[str] = []
    content_lines: list[str] = []
    seen_h2 = False
    seen_h3 = False
    in_content = False

    for raw in markdown.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        m = _H_LINE.match(stripped)
        level = len(m.group(1)) if m else 0

        if in_content:
            content_lines.append(line)
            continue
        if level == 2 and not seen_h2:
            tagline = _strip_inline_md(m.group(2))
            seen_h2 = True
            continue
        if level == 3 and not seen_h3:
            title = _strip_inline_md(m.group(2))
            seen_h3 = True
            continue
        if level >= 4:
            in_content = True
            content_lines.append(line)
            continue
        # Non-heading text becomes the lead paragraph once we are past the Title.
        if seen_h3 and stripped:
            para_lines.append(stripped)

    paragraph = _strip_inline_md(" ".join(para_lines)).strip()
    content_md = "\n".join(content_lines).strip()
    return FourPartSummary(
        tagline=tagline, title=title, paragraph=paragraph, content_md=content_md
    )


def four_part_content_html(content_md: str) -> str:
    """Render the Content part's Markdown to the Webflow RichText HTML subset.

    `#### X` → `<h4>X</h4>`, `##### X` → `<h5>X</h5>`, blank-line-separated prose →
    `<p>…</p>`, `[t](u)` → `<a href="u">t</a>`, `**b**`/`*i*` → `<strong>`/`<em>`.
    Line-oriented so a heading immediately followed by prose (no blank line) still
    splits correctly. Returns "" for empty input.
    """
    out: list[str] = []
    para: list[str] = []

    def _flush() -> None:
        if para:
            text = _inline_md_to_html(" ".join(para).strip())
            if text:
                out.append(f"<p>{text}</p>")
            para.clear()

    for raw in content_md.splitlines():
        line = raw.strip()
        hm = _CONTENT_H.match(line)
        if hm:
            _flush()
            level = len(hm.group(1))
            out.append(f"<h{level}>{_inline_md_to_html(hm.group(2).strip())}</h{level}>")
        elif not line:
            _flush()
        else:
            para.append(line)
    _flush()
    return "".join(out)


def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _strip_tags(html: str) -> str:
    return _collapse_ws(re.sub(r"<[^>]+>", " ", html or ""))


def _content_html_to_markdown(html: str) -> str:
    """Reconstruct Content Markdown from captured live-page HTML (h4/h5/p in order).

    Best-effort and lossy — `page_fetcher` drops tag attributes, so link hrefs are
    absent (audit link checks then pass vacuously). Anchor text survives inside the
    paragraph text. Used only for audit reconstruction, never for generation.
    """
    blocks: list[str] = []
    for m in re.finditer(r"<(h4|h5|p)[^>]*>(.*?)</\1>", html or "", re.DOTALL | re.IGNORECASE):
        tag = m.group(1).lower()
        inner = _strip_tags(m.group(2))
        if not inner:
            continue
        if tag == "h4":
            blocks.append(f"#### {inner}")
        elif tag == "h5":
            blocks.append(f"##### {inner}")
        else:
            blocks.append(inner)
    return "\n\n".join(blocks)


def parts_to_markdown(parts: dict) -> str:
    """Rebuild a 4-part Markdown document from `page_fetcher.existing_summary_parts`
    (the captured inner HTML of `#summary-tagline/title/paragraph/content`) so the
    audit phase can score a live 4-part page with `qa_checks(structure="four_part")`.

    Best-effort (see `_content_html_to_markdown`). Returns "" if no parts are present.
    """
    out: list[str] = []
    tagline = _strip_tags(parts.get("summary-tagline", ""))
    title = _strip_tags(parts.get("summary-title", ""))
    paragraph = _strip_tags(parts.get("summary-paragraph", ""))
    content_md = _content_html_to_markdown(parts.get("summary-content", ""))
    if tagline:
        out.append(f"## {tagline}")
    if title:
        out.append(f"### {title}")
    if paragraph:
        out.append(paragraph)
    if content_md:
        out.append(content_md)
    return "\n\n".join(out)
