"""rtlcss post-processor: turn an LTR stylesheet + its rtlcss mirror into a small,
scoped (`html[lang="ar"]`) diff+reset override that layers safely on top of
Webflow's stylesheet.

Why a diff+reset rather than shipping the full rtlcss mirror: rtlcss is designed to
REPLACE the LTR sheet. On the live site we can only ADD CSS on Arabic pages, never
remove Webflow's stylesheet. So for any rule where rtlcss renamed a one-sided
physical property (e.g. `margin-left` -> `margin-right`), we must also RESET the
now-unused side — otherwise the base rule's `margin-left` still applies and the
element gets margin on BOTH sides.

Pure stdlib. No I/O at import time.
"""
from __future__ import annotations

from tools.arabic_rtl.exclusions import EXCLUDE_SUBSTRINGS

# When rtlcss removes a one-sided physical property (because it moved the value to
# the opposite side), the original side must be reset to its default so the base
# rule stops applying it.
RESET = {
    "margin-left": "0", "margin-right": "0",
    "padding-left": "0", "padding-right": "0",
    "left": "auto", "right": "auto",
    "border-top-left-radius": "0", "border-top-right-radius": "0",
    "border-bottom-left-radius": "0", "border-bottom-right-radius": "0",
    "border-left-width": "0", "border-right-width": "0",
    "border-left-style": "none", "border-right-style": "none",
    "border-left-color": "currentColor", "border-right-color": "currentColor",
    "border-left": "0", "border-right": "0",
}


def split_top(css: str):
    """Split CSS into top-level rules: [(prelude, body|None)], quote/brace aware.

    `body` is the inner text for block rules; None for statements (e.g. `@import …;`).
    """
    res = []
    i, n, start, q = 0, len(css), 0, None
    while i < n:
        c = css[i]
        if q:
            if c == q and css[i - 1] != "\\":
                q = None
            i += 1
            continue
        if c in "\"'":
            q = c
            i += 1
            continue
        if c == "{":
            prelude = css[start:i].strip()
            depth, j, q2 = 1, i + 1, None
            while j < n and depth:
                d = css[j]
                if q2:
                    if d == q2 and css[j - 1] != "\\":
                        q2 = None
                elif d in "\"'":
                    q2 = d
                elif d == "{":
                    depth += 1
                elif d == "}":
                    depth -= 1
                j += 1
            res.append((prelude, css[i + 1:j - 1]))
            i = start = j
        elif c == ";":
            s = css[start:i].strip()
            if s:
                res.append((s, None))
            i += 1
            start = i
        else:
            i += 1
    tail = css[start:].strip()
    if tail:
        res.append((tail, None))
    return res


def split_decls(body: str):
    """Parse a declaration block into {property: value}; paren/quote aware (url(), calc())."""
    parts = []
    i, n, start, q, depth = 0, len(body), 0, None, 0
    while i < n:
        c = body[i]
        if q:
            if c == q and body[i - 1] != "\\":
                q = None
        elif c in "\"'":
            q = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == ";" and depth == 0:
            parts.append(body[start:i])
            start = i + 1
        i += 1
    if body[start:].strip():
        parts.append(body[start:])
    out = {}
    for d in parts:
        if ":" in d:
            p, v = d.split(":", 1)
            out[p.strip().lower()] = v.strip()
    return out


def scope(sel: str) -> str:
    """Prefix a selector with html[lang="ar"] (Arabic-only effect + higher specificity)."""
    sel = sel.strip()
    if sel.startswith("html"):
        return 'html[lang="ar"]' + sel[4:]
    return 'html[lang="ar"] ' + sel


def diff_rule(src_body: str, rtl_body: str):
    """Override declarations for one rule, or None if unchanged.

    Emits rtlcss's changed values, plus a RESET for any source property rtlcss
    renamed away (carrying `!important` if the source declaration had it, so the
    reset still wins over a base `!important`).
    """
    s = split_decls(src_body)
    r = split_decls(rtl_body)
    if s == r:
        return None
    out = []
    for p, v in r.items():
        if s.get(p) != v:
            out.append(f"{p}:{v}")  # rtlcss preserves !important inside v
    for p in s:
        if p not in r:
            reset = RESET.get(p, "initial")
            if s[p].rstrip().endswith("!important"):
                reset = f"{reset}!important"
            out.append(f"{p}:{reset}")
    return out


def emit(src_rules, rtl_rules, exclude=None) -> str:
    """Build the scoped override CSS from paired (src, rtl) rule lists.

    Raises if rule counts diverge (rtlcss should preserve count+order; a mismatch
    means positional pairing would silently corrupt the output — fail loud instead).
    """
    if exclude is None:
        exclude = EXCLUDE_SUBSTRINGS
    if len(src_rules) != len(rtl_rules):
        raise RuntimeError(
            f"rtlcss rule-count drift {len(src_rules)} != {len(rtl_rules)} "
            "— refusing to emit a misaligned override"
        )
    parts = []
    for (sp, sb), (_rp, rb) in zip(src_rules, rtl_rules):
        if sb is None:
            continue
        if sp.startswith("@media") or sp.startswith("@supports"):
            inner = emit(split_top(sb), split_top(rb), exclude)
            if inner:
                parts.append(sp + "{" + inner + "}")
            continue
        if sp.startswith("@"):  # @keyframes / @font-face — see changed_atrules()
            continue
        if any(x in sp for x in exclude):
            continue
        decls = diff_rule(sb, rb)
        if decls:
            sel = ",".join(scope(s) for s in sp.split(","))
            parts.append(sel + "{" + ";".join(decls) + "}")
    return "".join(parts)


def changed_atrules(src_rules, rtl_rules) -> int:
    """Count @keyframes/@font-face blocks rtlcss changed.

    These are NOT auto-flipped (they can't be scoped with a selector prefix). v1
    surfaces the count so a directional keyframe animation can be handled by hand
    in arabic_static.css.
    """
    n = 0
    for (sp, sb), (_rp, rb) in zip(src_rules, rtl_rules):
        if sp.startswith(("@keyframes", "@-webkit-keyframes", "@font-face")) and sb != rb:
            n += 1
    return n
