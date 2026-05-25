"""Unit tests for tools.mailer.send — pure logic only, no network."""
import os
import unittest

from tools.mailer import send as m


class TestBuildFields(unittest.TestCase):
    def test_text_only(self):
        f = m.build_fields("a@b.com", "Hi", "Body", None, "From <x@y.com>")
        self.assertEqual(f["to"], "a@b.com")
        self.assertEqual(f["from"], "From <x@y.com>")
        self.assertEqual(f["subject"], "Hi")
        self.assertEqual(f["text"], "Body")
        self.assertNotIn("html", f)

    def test_html_and_reply_to(self):
        f = m.build_fields("a@b.com", "Hi", "", "<p>x</p>", "x@y.com", reply_to="r@y.com")
        self.assertEqual(f["html"], "<p>x</p>")
        self.assertEqual(f["h:Reply-To"], "r@y.com")
        self.assertNotIn("text", f)

    def test_requires_to(self):
        with self.assertRaises(m.EmailError):
            m.build_fields("", "Hi", "Body", None, "x@y.com")

    def test_requires_subject(self):
        with self.assertRaises(m.EmailError):
            m.build_fields("a@b.com", "", "Body", None, "x@y.com")

    def test_requires_body(self):
        with self.assertRaises(m.EmailError):
            m.build_fields("a@b.com", "Hi", "", None, "x@y.com")

    def test_rejects_header_injection(self):
        for bad in ("a@b.com\r\nBcc: evil@x.com", "a@b.com\nX: y", "a\0b@x.com"):
            with self.assertRaises(m.EmailError):
                m.build_fields(bad, "Hi", "Body", None, "x@y.com")
        with self.assertRaises(m.EmailError):
            m.build_fields("a@b.com", "Hi\r\nEvil: 1", "Body", None, "x@y.com")


class TestResolveConfig(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ("MAILGUN_API_KEY", "MAILGUN_DOMAIN", "MAILGUN_FROM", "MAILGUN_API_BASE")}
        for k in self._saved:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_missing_key_raises(self):
        os.environ["MAILGUN_DOMAIN"] = "d.org"
        with self.assertRaises(m.EmailError):
            m._resolve_config(None, None, None, None)

    def test_missing_domain_raises(self):
        os.environ["MAILGUN_API_KEY"] = "k"
        with self.assertRaises(m.EmailError):
            m._resolve_config(None, None, None, None)

    def test_defaults_sender_and_base(self):
        os.environ["MAILGUN_API_KEY"] = "k"
        os.environ["MAILGUN_DOMAIN"] = "d.org"
        key, domain, sender, base = m._resolve_config(None, None, None, None)
        self.assertEqual(key, "k")
        self.assertEqual(domain, "d.org")
        self.assertIn("postmaster@d.org", sender)
        self.assertEqual(base, m.DEFAULT_API_BASE)

    def test_respects_overrides(self):
        os.environ["MAILGUN_API_KEY"] = "k"
        os.environ["MAILGUN_DOMAIN"] = "d.org"
        os.environ["MAILGUN_FROM"] = "Me <me@d.org>"
        os.environ["MAILGUN_API_BASE"] = "https://api.eu.mailgun.net/"
        _, _, sender, base = m._resolve_config(None, None, None, None)
        self.assertEqual(sender, "Me <me@d.org>")
        self.assertEqual(base, "https://api.eu.mailgun.net")  # trailing slash stripped


if __name__ == "__main__":
    unittest.main()
