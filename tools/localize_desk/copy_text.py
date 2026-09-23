"""Every word the Localization Desk shows, read from COPY.md.

The operator's rule (2026-09-23): all text in the project lives in one document, and the
code pulls it from there. `COPY.md` beside this file is that document; nothing that
renders the desk may carry a sentence of its own.

Two kinds of entry:

- **Table rows** — ``| `key` | text | where |``. Most of the copy.
- **Blocks** — ``<!-- block key -->`` … ``<!-- /block -->``, for long help text written as
  Markdown (### headings, paragraphs, ``- `` lists, **bold**, *italic*, `code`).

`{name}` in a text is filled in by the caller. `.one` / `.other` keys are singular/plural.
A missing key or an unfilled `{name}` raises: a desk that renders ``{language}`` or a
blank label is a desk that confuses the reviewer, and a build is the cheap place to find out.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from html import escape
from pathlib import Path

COPY_PATH = Path(__file__).resolve().parent / "COPY.md"

_ROW = re.compile(r"^\|\s*`([a-z0-9_.\-]+)`\s*\|(.*)\|(.*)\|\s*$")
_BLOCK = re.compile(r"<!-- block ([a-z0-9_.\-]+) -->\n(.*?)\n<!-- /block -->", re.S)
_VAR = re.compile(r"\{([A-Za-z_]+)\}")


def parse(text: str) -> dict[str, str]:
    """Key -> text for every table row and block in a COPY.md body."""
    out: dict[str, str] = {}
    for key, body in _BLOCK.findall(text):
        if key in out:
            raise ValueError(f"COPY.md: {key!r} is defined twice")
        out[key] = body.strip()
    for line in _BLOCK.sub("", text).splitlines():
        m = _ROW.match(line)
        if not m:
            continue
        key = m.group(1)
        # The Text column may itself contain `\|`; split on the LAST unescaped pipe.
        rest = (m.group(2) + "|" + m.group(3)).replace("\\|", "\0")
        value = rest.rsplit("|", 1)[0].replace("\0", "|").strip()
        if key in out:
            raise ValueError(f"COPY.md: {key!r} is defined twice")
        out[key] = value
    return out


@lru_cache(maxsize=1)
def load() -> dict[str, str]:
    return parse(COPY_PATH.read_text(encoding="utf-8"))


def fill(text: str, key: str, **values) -> str:
    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in values:
            raise KeyError(f"COPY.md {key!r} needs {{{name}}}, which the caller did not pass")
        return str(values[name])
    return _VAR.sub(sub, text)


def t(key: str, **values) -> str:
    """The text for `key`, plain (NOT escaped), with `{names}` filled in."""
    copy = load()
    if key not in copy:
        raise KeyError(f"COPY.md has no {key!r}")
    return fill(copy[key], key, **values)


def tn(key: str, n: int, **values) -> str:
    """Singular or plural: `key.one` when n == 1, else `key.other`."""
    return t(f"{key}.one" if n == 1 else f"{key}.other", n=n, **values)


def _inline(s: str) -> str:
    s = escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    return s


def block_html(key: str) -> str:
    """A block rendered from its Markdown subset to HTML (escaped first, then marked up)."""
    md = t(key)
    html: list[str] = []
    para: list[str] = []
    items: list[str] = []

    def flush() -> None:
        if para:
            html.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()
        if items:
            html.append("<ul>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for raw in md.splitlines():
        line = raw.strip()
        if not line:
            flush()
        elif line.startswith("### "):
            flush()
            html.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("- "):
            if para:
                flush()
            items.append(line[2:])
        elif items:
            items[-1] += " " + line          # a wrapped list item
        else:
            para.append(line)
    flush()
    return "\n".join(html)


def js_table(keys: list[str] | None = None) -> str:
    """The copy as a JS object literal, for `t()` / `tn()` in the page script."""
    copy = load()
    picked = {k: v for k, v in copy.items() if keys is None or k in keys}
    # `</` would end the enclosing <script>; JSON leaves it alone, so escape it here.
    return json.dumps(picked, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


# The page-side twin of t()/tn(). A missing key renders as ⟦key⟧ and is logged, so a
# copy gap is visible on screen in review rather than silently blank.
JS_HELPERS = """\
    function t(key, vals) {
      var s = COPY[key];
      if (s === undefined) { console.error('COPY.md has no ' + key); return '\\u27e6' + key + '\\u27e7'; }
      return s.replace(/\\{([A-Za-z_]+)\\}/g, function (m, name) {
        if (!vals || !(name in vals)) { console.error('COPY.md ' + key + ' needs {' + name + '}'); return m; }
        return String(vals[name]);
      });
    }
    function tn(key, n, vals) {
      var v = { n: n };
      for (var k in (vals || {})) v[k] = vals[k];
      return t(key + (n === 1 ? '.one' : '.other'), v);
    }
"""
