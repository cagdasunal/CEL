"""Reusable transactional email sender (Mailgun HTTP API). Stdlib-only.

Any CEL tool can send mail with this. Config comes from the environment so the
API key never lives in code or git:

    MAILGUN_API_KEY   Mailgun private API key (a GitHub Actions secret)
    MAILGUN_DOMAIN    sending domain, e.g. sandboxXXXX.mailgun.org or mg.englishcollege.com
    MAILGUN_FROM      optional "Name <addr@domain>"; defaults to postmaster@<domain>
    MAILGUN_API_BASE  optional; https://api.mailgun.net (US, default) or https://api.eu.mailgun.net

Usage (library):
    from tools.mailer.send import send_email
    send_email("a@b.com", "Subject", "Body text", html="<p>Body</p>")

Usage (CLI / workflows):
    python3 -m tools.mailer.send --to a@b.com --subject "Hi" --text "Body"
    python3 -m tools.mailer.send --to a@b.com --subject "Hi" --text "Body" --dry-run

NOTE (sandbox domains): a Mailgun *sandbox* domain only delivers to authorized
recipients added in the Mailgun dashboard (max 5). Use a verified domain to mail
arbitrary addresses.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_API_BASE = "https://api.mailgun.net"
_CTRL = {"\n", "\r", "\0"}


class EmailError(Exception):
    """Raised on misconfiguration or a non-2xx Mailgun response."""


def _clean_header(value: str, field: str) -> str:
    """Reject header-injection (CR/LF/NUL) in single-line header fields."""
    v = str(value or "")
    if any(c in v for c in _CTRL):
        raise EmailError(f"illegal control character in {field}")
    return v


def build_fields(to: str, subject: str, text: str, html: str | None, sender: str,
                 reply_to: str | None = None) -> dict:
    """Build the Mailgun form fields. Pure (no I/O) — unit-tested."""
    if not to:
        raise EmailError("'to' is required")
    if not subject:
        raise EmailError("'subject' is required")
    if not text and not html:
        raise EmailError("one of 'text' or 'html' is required")
    fields = {
        "from": _clean_header(sender, "from"),
        "to": _clean_header(to, "to"),
        "subject": _clean_header(subject, "subject"),
    }
    if text:
        fields["text"] = str(text)
    if html:
        fields["html"] = str(html)
    if reply_to:
        fields["h:Reply-To"] = _clean_header(reply_to, "reply_to")
    return fields


def _resolve_config(api_key, domain, sender, base_url):
    api_key = api_key or os.environ.get("MAILGUN_API_KEY", "")
    domain = domain or os.environ.get("MAILGUN_DOMAIN", "")
    base_url = base_url or os.environ.get("MAILGUN_API_BASE", "") or DEFAULT_API_BASE
    sender = sender or os.environ.get("MAILGUN_FROM", "")
    if not api_key:
        raise EmailError("MAILGUN_API_KEY is not set")
    if not domain:
        raise EmailError("MAILGUN_DOMAIN is not set")
    if not sender:
        sender = f"CEL Dashboard <postmaster@{domain}>"
    return api_key, domain, sender, base_url.rstrip("/")


def send_email(to: str, subject: str, text: str = "", html: str | None = None, *,
               reply_to: str | None = None, api_key: str | None = None,
               domain: str | None = None, sender: str | None = None,
               base_url: str | None = None, timeout: float = 20.0) -> dict:
    """Send one email via Mailgun. Returns the parsed JSON response (has 'id').

    Raises EmailError on misconfiguration or a non-2xx response.
    """
    api_key, domain, sender, base_url = _resolve_config(api_key, domain, sender, base_url)
    fields = build_fields(to, subject, text, html, sender, reply_to)
    url = f"{base_url}/v3/{domain}/messages"
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    auth = base64.b64encode(f"api:{api_key}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", "Basic " + auth)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300] if e.fp else ""
        raise EmailError(f"Mailgun HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise EmailError(f"Mailgun unreachable: {e.reason}") from None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Send an email via Mailgun (CEL).")
    ap.add_argument("--to", required=True)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--text", default="")
    ap.add_argument("--html", default=None)
    ap.add_argument("--reply-to", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="Build + validate the request but do not send.")
    args = ap.parse_args(argv)
    try:
        if args.dry_run:
            # Resolve config (validates env) + build fields, but don't POST.
            _, domain, sender, base_url = _resolve_config(None, None, None, None)
            fields = build_fields(args.to, args.subject, args.text, args.html, sender, args.reply_to)
            print(f"[dry-run] POST {base_url}/v3/{domain}/messages")
            print(f"[dry-run] from={fields['from']} to={fields['to']} subject={fields['subject']}")
            return 0
        resp = send_email(args.to, args.subject, args.text, args.html, reply_to=args.reply_to)
        print("sent:", resp.get("id") or resp)
        return 0
    except EmailError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
