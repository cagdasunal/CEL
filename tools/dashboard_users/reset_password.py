"""Set a user's password from a valid stateless reset link.

Inputs (env, set by dashboard-reset-password.yml):
  INPUT_EMAIL        registered email
  INPUT_EXP          unix-seconds expiry from the reset link
  INPUT_SIG          HMAC signature from the reset link
  INPUT_NEW_PW_HASH  new stored value SHA256(SHA256(utf8(new_pw)))
  RESET_SIGNING_KEY  (secret) HMAC key

Verifies sig == HMAC(key, email|exp|currentPwHash) and now < exp. Because the
signature binds the CURRENT pwHash, completing a reset changes pwHash and so
invalidates the link (single-use). Commit handled by the workflow.
"""
from __future__ import annotations

import os
import sys
import time

from tools.dashboard_users import _common as c


def main() -> int:
    email = os.environ.get("INPUT_EMAIL", "")
    exp_raw = (os.environ.get("INPUT_EXP", "") or "").strip()
    sig = (os.environ.get("INPUT_SIG", "") or "").strip().lower()
    new_pw_hash = (os.environ.get("INPUT_NEW_PW_HASH", "") or "").strip().lower()

    if not c.valid_email(email):
        print("invalid email", file=sys.stderr)
        return 1
    if not c.valid_hex64(new_pw_hash) or not c.valid_hex64(sig):
        print("invalid input", file=sys.stderr)
        return 1
    try:
        exp = int(exp_raw)
    except ValueError:
        print("invalid exp", file=sys.stderr)
        return 1
    if int(time.time()) >= exp:
        print("reset link expired", file=sys.stderr)
        return 1

    key = c.reset_signing_key()
    users = c.load_users()
    user = c.find_user(users, email)
    if user is None:
        print("no such user", file=sys.stderr)
        return 1

    current_pw_hash = str(user.get("pwHash", ""))
    if not c.verify_reset_signature(email, exp, current_pw_hash, key, sig):
        print("invalid signature", file=sys.stderr)
        return 1

    user["pwHash"] = new_pw_hash
    c.save_users(users)
    print("password reset for %s" % c.normalize_email(email))
    return 0


if __name__ == "__main__":
    sys.exit(main())
