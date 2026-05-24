"""Issue a stateless password-reset link for a registered email.

Inputs (env, set by dashboard-forgot-password.yml):
  INPUT_EMAIL        the email typed on the login screen
  RESET_SIGNING_KEY  (secret) HMAC key
  RESET_BASE_URL     optional; default https://cel.englishcollege.com/reset/
  RESET_TTL_SECONDS  optional; default 3600

Emits step outputs to $GITHUB_OUTPUT:
  found=true|false       whether the email is registered
  recipient=<email>      (only when found) — the address to mail
  reset_url=<url>        (only when found) — masked in logs

Never reveals existence to the client (the workflow always succeeds; the client
always shows a neutral message). No repo write, no commit — pure link issuer.
"""
from __future__ import annotations

import os
import sys
import time
from urllib.parse import quote

from tools.dashboard_users import _common as c

DEFAULT_BASE = "https://cel.englishcollege.com/reset/"
DEFAULT_TTL = 3600


def _write_output(pairs: dict) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    with open(out, "a", encoding="utf-8") as fh:
        for k, v in pairs.items():
            fh.write("%s=%s\n" % (k, v))


def main() -> int:
    email = os.environ.get("INPUT_EMAIL", "")
    if not c.valid_email(email):
        _write_output({"found": "false"})
        print("email not registered (or invalid)")
        return 0

    users = c.load_users()
    user = c.find_user(users, email)
    if user is None:
        _write_output({"found": "false"})
        print("email not registered")
        return 0

    key = c.reset_signing_key()
    try:
        ttl = int(os.environ.get("RESET_TTL_SECONDS", "") or DEFAULT_TTL)
    except ValueError:
        ttl = DEFAULT_TTL
    exp = int(time.time()) + ttl
    pw_hash = str(user.get("pwHash", ""))
    sig = c.reset_signature(email, exp, pw_hash, key)
    base = (os.environ.get("RESET_BASE_URL", "") or DEFAULT_BASE).strip()
    recipient = c.normalize_email(email)
    reset_url = "%s?email=%s&exp=%d&sig=%s" % (base, quote(recipient), exp, sig)

    # Keep the signed link out of plaintext build logs.
    print("::add-mask::%s" % sig)
    print("::add-mask::%s" % reset_url)
    _write_output({"found": "true", "recipient": recipient, "reset_url": reset_url})
    print("reset link issued")
    return 0


if __name__ == "__main__":
    sys.exit(main())
