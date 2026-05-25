"""Four-part Summary structure — parse + Markdown→HTML (tracker-096, tracker-098).

The redesigned Summary section has four parts:
  - Tagline    (H2, 2-3 words)              → plain text
  - Title      (H3)                         → plain text
  - Paragraphs (1-2 lead blocks, may link)  → rich text  (tracker-098)
  - Content    (starts at H4, uses H5)      → rich text

`course` / `housing` / `landing` summaries are generated as ONE Markdown document in
that exact order; this module splits it into the four parts and renders the RichText
parts (Paragraphs + Content) to the HTML subset Webflow's RichText field expects
(`<h2>/<h3>/<h4>/<h5>/<p>/<a>/<strong>/<em>`). Plain Markdown into a RichText field
renders literal `####`/`[](url)`, so every RichText write needs real HTML; only the
two plain-text parts (Tagline, Title) are written as stripped plain text.

tracker-098: the Paragraph field became RichText holding 1-2 paragraphs that may carry
inline internal links, so `FourPartSummary.paragraph` is now the MARKDOWN source (no
longer plain-text-stripped) and `four_part_paragraph_html` renders it. Blog posts keep
the single-block path; their Markdown is rendered to HTML by `summary_markdown_to_html`
(also a RichText write) before the CMS PATCH.

Pure stdlib — no dependency on the rest of the tool.
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass

# Heading line: 1-6 leading '#'. Trailing '#'s (ATX-closed headings) are tolerated.
_H_LINE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


@dataclass(frozen=True)
class FourPartSummary:
    """The four parts parsed out of a generated 4-part Summary Markdown document.

    tracker-098: `paragraph` holds the MARKDOWN source of the lead Paragraphs part
    (1-2 blank-line-separated paragraphs that MAY contain inline links/emphasis), not
    stripped plain text. Render it to RichText HTML via `four_part_paragraph_html`.
    `tagline` and `title` remain stripped plain text.
    """

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

    Contract (emitted in this order): `## Tagline` → `### Title` → 1-2 lead Paragraphs
    → `#### …` Content (H4/H5). tracker-098: the Paragraphs part is captured as MARKDOWN
    preserving blank-line separation between the two paragraphs and any inline links —
    `four_part_paragraph_html` renders it. Tolerant of missing parts — a malformed draft
    returns empty strings for the parts it lacks, so the QA gate fails it (and the
    orchestrator demotes it to MANUAL_REVIEW) rather than crashing.
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
        # Non-heading text becomes the lead Paragraphs once we are past the Title. Blank
        # lines are KEPT (as empty strings) so the 1-2 paragraph breaks survive into the
        # captured Markdown; leading blanks before the first prose line are dropped.
        if seen_h3 and (stripped or para_lines):
            para_lines.append(stripped)

    paragraph = "\n".join(para_lines).strip()
    content_md = "\n".join(content_lines).strip()
    return FourPartSummary(
        tagline=tagline, title=title, paragraph=paragraph, content_md=content_md
    )


def _markdown_to_html(md: str, allowed_heading_levels: tuple[int, ...]) -> str:
    """Render a Markdown block to the Webflow RichText HTML subset.

    Heading lines whose level is in `allowed_heading_levels` become `<hN>…</hN>`;
    blank-line-separated prose becomes `<p>…</p>`; `[t](u)` → `<a href="u">t</a>`,
    `**b**`/`*i*` → `<strong>`/`<em>`. Heading lines OUTSIDE the allowed set are treated
    as prose (their `#` markers stripped) so an unexpected level never leaks raw `#`
    into the field. Line-oriented so a heading immediately followed by prose (no blank
    line) still splits correctly. Returns "" for empty input.
    """
    out: list[str] = []
    para: list[str] = []

    def _flush() -> None:
        if para:
            text = _inline_md_to_html(" ".join(para).strip())
            if text:
                out.append(f"<p>{text}</p>")
            para.clear()

    for raw in md.splitlines():
        line = raw.strip()
        hm = _H_LINE.match(line)
        if hm and len(hm.group(1)) in allowed_heading_levels:
            _flush()
            level = len(hm.group(1))
            out.append(f"<h{level}>{_inline_md_to_html(hm.group(2).strip())}</h{level}>")
        elif not line:
            _flush()
        elif hm:
            # A heading at a non-allowed level — keep its text as prose, drop the marker.
            para.append(hm.group(2).strip())
        else:
            para.append(line)
    _flush()
    return "".join(out)


def four_part_content_html(content_md: str) -> str:
    """Render the Content part's Markdown to the Webflow RichText HTML subset.

    `#### X` → `<h4>X</h4>`, `##### X` → `<h5>X</h5>`, blank-line-separated prose →
    `<p>…</p>`, `[t](u)` → `<a href="u">t</a>`, `**b**`/`*i*` → `<strong>`/`<em>`.
    Only H4/H5 are recognized as headings (the Content contract). Returns "" for empty
    input.
    """
    return _markdown_to_html(content_md, allowed_heading_levels=(4, 5))


def four_part_paragraph_html(paragraph_md: str) -> str:
    """Render the lead Paragraphs part's Markdown to RichText HTML (tracker-098).

    Blank-line-separated paragraphs → `<p>…</p>` each, with inline `[t](u)` →
    `<a href="u">t</a>` and `**b**`/`*i*` → `<strong>`/`<em>`. No headings are expected
    in the Paragraphs part, so none are emitted (a stray heading line degrades to prose).
    Returns "" for empty input.
    """
    return _markdown_to_html(paragraph_md, allowed_heading_levels=())


def summary_markdown_to_html(md: str) -> str:
    """Render a single-block (blog) Summary Markdown document to RichText HTML (tracker-098).

    `## X`→`<h2>`, `### X`→`<h3>`, `#### X`→`<h4>`, blank-line-separated prose →`<p>`,
    inline `[t](u)`→`<a href>`, `**b**`/`*i*`→`<strong>`/`<em>`. Fixes literal `##` /
    `[](url)` rendering when blog Markdown was PATCHed straight into the RichText
    `summary` field. Returns "" for empty input.
    """
    return _markdown_to_html(md, allowed_heading_levels=(2, 3, 4))


def summary_html_to_markdown(html: str) -> str:
    """Inverse of summary_markdown_to_html for the limited tag set this module emits
    (`<h2>/<h3>/<h4>/<h5>/<p>/<a>/<strong>/<em>`). Used (2026-05-23) to recover the
    EXISTING summary of a blog whose Markdown isn't in a run manifest — read the staged
    RichText `summary` HTML from the CMS and convert it back to Markdown so the
    link-insertion pass has a faithful base to preserve. Unhandled tags are stripped;
    HTML entities are unescaped. Returns "" for empty input."""
    if not html:
        return ""
    s = html
    # Inline first (so heading/paragraph wrapping doesn't swallow them).
    s = re.sub(r'<a\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*>(.*?)</a>', r'[\2](\1)', s, flags=re.IGNORECASE | re.DOTALL)
    s = re.sub(r'</?(?:strong|b)\b[^>]*>', '**', s, flags=re.IGNORECASE)
    s = re.sub(r'</?(?:em|i)\b[^>]*>', '*', s, flags=re.IGNORECASE)
    # Block elements → Markdown, each on its own blank-line-separated block.
    for level, hashes in ((2, "## "), (3, "### "), (4, "#### "), (5, "##### ")):
        s = re.sub(
            rf'<h{level}\b[^>]*>(.*?)</h{level}>',
            lambda m, h=hashes: f"\n\n{h}{m.group(1).strip()}\n",
            s, flags=re.IGNORECASE | re.DOTALL,
        )
    s = re.sub(r'<p\b[^>]*>(.*?)</p>', lambda m: f"\n\n{m.group(1).strip()}\n", s, flags=re.IGNORECASE | re.DOTALL)
    s = re.sub(r'<br\s*/?>', "\n", s, flags=re.IGNORECASE)
    s = re.sub(r'<[^>]+>', "", s)  # strip any remaining tags
    s = _html.unescape(s)
    s = re.sub(r'[ \t]+\n', "\n", s)       # trailing spaces
    s = re.sub(r'\n{3,}', "\n\n", s)       # collapse extra blank lines
    return s.strip()


def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _strip_tags(html: str) -> str:
    return _collapse_ws(re.sub(r"<[^>]+>", " ", html or ""))


def _html_block_texts(html: str) -> list[str]:
    """Extract each block element's PLAIN TEXT from rendered RichText HTML, in order.

    One entry per `<h2>/<h3>/<h4>/<h5>/<p>` block: inner tags removed (inline
    `<a>/<strong>/<em>` collapse to their text), HTML entities decoded, whitespace
    collapsed. This is the exact per-node string Weglot extracts from the live page, so a
    translation CSV keyed on these strings matches (tracker-107, 2026-05-24)."""
    out: list[str] = []
    for m in re.finditer(r"<(h2|h3|h4|h5|p)\b[^>]*>(.*?)</\1>", html or "", re.DOTALL | re.IGNORECASE):
        text = _collapse_ws(_html.unescape(_strip_tags(m.group(2))))
        if text:
            out.append(text)
    return out


def summary_page_blocks(markdown: str) -> list[str]:
    """The summary's live-page text nodes, in order, as PLAIN TEXT — what Weglot keys on.

    A 4-part summary renders as Tagline (`<h2>`), Title (`<h3>`), the Paragraphs part
    (`<p>` blocks), then the Content part (`<h4>/<h5>/<p>` blocks). Mirroring that exactly
    (via `parse_four_part` + `four_part_*_html`) yields `word_from`/`word_to` values that
    equal the page's rendered text nodes, so Weglot applies the imported translation
    instead of machine-translating. Inline links collapse to their anchor text (Weglot
    localizes the hrefs itself). tracker-107, 2026-05-24."""
    fp = parse_four_part(markdown)
    blocks: list[str] = []
    if fp.tagline:
        blocks.append(fp.tagline)
    if fp.title:
        blocks.append(fp.title)
    blocks.extend(_html_block_texts(four_part_paragraph_html(fp.paragraph)))
    blocks.extend(_html_block_texts(four_part_content_html(fp.content_md)))
    return [b for b in blocks if b]


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

    Best-effort (see `_content_html_to_markdown`). The Paragraphs part is reconstructed
    as stripped plain text (page_fetcher drops link hrefs, so anchor text survives but
    links don't); `parse_four_part` then captures it as a single-paragraph Markdown
    source — consistent with the new RichText Paragraphs contract. Returns "" if no
    parts are present.
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
