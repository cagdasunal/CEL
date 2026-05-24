"""Set a user's password after verifying the current-password proof.

Inputs (env, set by dashboard-change-password.yml):
  INPUT_EMAIL        registered email
  INPUT_CUR_HASH     inner hash of the current password: SHA256(utf8(current_pw))
  INPUT_NEW_PW_HASH  new stored value: SHA256(SHA256(utf8(new_pw)))

Verifies sha256hex(INPUT_CUR_HASH) == stored pwHash, then sets pwHash to
INPUT_NEW_PW_HASH. Commits handled by the workflow.
"""
from __future__ import annotations

import os
import sys

from tools.dashboard_users import _common as c


def main() -> int:
    email = os.environ.get("INPUT_EMAIL", "")
    cur_hash = (os.environ.get("INPUT_CUR_HASH", "") or "").strip().lower()
    new_pw_hash = (os.environ.get("INPUT_NEW_PW_HASH", "") or "").strip().lower()

    if not c.valid_email(email):
        print("invalid email", file=sys.stderr)
        return 1
    if not c.valid_hex64(cur_hash) or not c.valid_hex64(new_pw_hash):
        print("invalid hash input", file=sys.stderr)
        return 1

    users = c.load_users()
    user = c.find_user(users, email)
    if user is None:
        print("no such user", file=sys.stderr)
        return 1
    if c.sha256hex(cur_hash) != str(user.get("pwHash", "")).strip().lower():
        print("current password does not match", file=sys.stderr)
        return 1

    user["pwHash"] = new_pw_hash
    c.save_users(users)
    print("password updated for %s" % c.normalize_email(email))
    return 0


if __name__ == "__main__":
    sys.exit(main())
