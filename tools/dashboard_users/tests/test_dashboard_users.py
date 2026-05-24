"""Tests for the dashboard password workflow modules (stdlib unittest).

Run from the CEL repo root:
    python3 -m unittest tools.dashboard_users.tests.test_dashboard_users
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.dashboard_users import _common as c
from tools.dashboard_users import change_password

PWD = "test-pass-ONE"          # the user's current plaintext password


def inner(pw):
    return c.sha256hex(pw)


def pwhash(pw):
    return c.sha256hex(c.sha256hex(pw))


_ENV_KEYS = ("INPUT_EMAIL", "INPUT_CUR_HASH", "INPUT_NEW_PW_HASH")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.users_path = Path(self.tmp) / "users.json"
        self.users_path.write_text(json.dumps([
            {"firstName": "Ada", "lastName": "L", "email": "ada@x.com", "pwHash": pwhash(PWD)},
        ]) + "\n", encoding="utf-8")
        self._orig_users_file = c.USERS_FILE
        c.USERS_FILE = self.users_path
        self._saved_env = {k: os.environ.get(k) for k in _ENV_KEYS}
        for k in _ENV_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        c.USERS_FILE = self._orig_users_file
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def stored_hash(self, email="ada@x.com"):
        users = json.loads(self.users_path.read_text())
        return c.find_user(users, email)["pwHash"]


class TestCryptoSpec(Base):
    def test_double_hash_direction(self):
        # pwHash is SHA256 of the inner hash (not of the raw password).
        self.assertEqual(pwhash(PWD), c.sha256hex(inner(PWD)))
        self.assertNotEqual(pwhash(PWD), inner(PWD))
        self.assertEqual(len(pwhash(PWD)), 64)

    def test_seed_migration_matches_existing_hash(self):
        # The migrated seed value equals SHA256 of the OLD single-hash.
        # Live example: SHA256("chris.20.26") == e8ff7132... ; double == 728886ee...
        old_inner = "e8ff7132aa00ae3886b10e2608498d040462fefe392df4aebfc6ffef024236be"
        self.assertEqual(c.sha256hex(old_inner),
                         "728886ee668020f70c6f866e864948b0e846b6e010fd47ea31e3719e85327a47")

    def test_validators(self):
        self.assertTrue(c.valid_email("a@b.com"))
        self.assertFalse(c.valid_email("nope"))
        self.assertFalse(c.valid_email("a@b.com\nx@y.com"))
        self.assertTrue(c.valid_hex64("a" * 64))
        self.assertFalse(c.valid_hex64("a" * 63))
        self.assertFalse(c.valid_hex64("Z" * 64))


class TestChangePassword(Base):
    def test_accept_with_correct_current(self):
        os.environ["INPUT_EMAIL"] = "ada@x.com"
        os.environ["INPUT_CUR_HASH"] = inner(PWD)
        os.environ["INPUT_NEW_PW_HASH"] = pwhash("brand-new-pw")
        self.assertEqual(change_password.main(), 0)
        self.assertEqual(self.stored_hash(), pwhash("brand-new-pw"))

    def test_reject_using_public_pwhash_as_current(self):
        # Attacker reads the public pwHash and replays it as the "current" proof.
        # sha256hex(pwHash) != pwHash, so this must fail and leave the hash intact.
        before = self.stored_hash()
        os.environ["INPUT_EMAIL"] = "ada@x.com"
        os.environ["INPUT_CUR_HASH"] = before
        os.environ["INPUT_NEW_PW_HASH"] = pwhash("attacker-pw")
        self.assertEqual(change_password.main(), 1)
        self.assertEqual(self.stored_hash(), before)

    def test_reject_wrong_password(self):
        before = self.stored_hash()
        os.environ["INPUT_EMAIL"] = "ada@x.com"
        os.environ["INPUT_CUR_HASH"] = inner("not-the-password")
        os.environ["INPUT_NEW_PW_HASH"] = pwhash("x")
        self.assertEqual(change_password.main(), 1)
        self.assertEqual(self.stored_hash(), before)

    def test_reject_unknown_user(self):
        os.environ["INPUT_EMAIL"] = "ghost@x.com"
        os.environ["INPUT_CUR_HASH"] = inner(PWD)
        os.environ["INPUT_NEW_PW_HASH"] = pwhash("x")
        self.assertEqual(change_password.main(), 1)

    def test_reject_bad_hash_shape(self):
        os.environ["INPUT_EMAIL"] = "ada@x.com"
        os.environ["INPUT_CUR_HASH"] = "deadbeef"
        os.environ["INPUT_NEW_PW_HASH"] = pwhash("x")
        self.assertEqual(change_password.main(), 1)


if __name__ == "__main__":
    unittest.main()
