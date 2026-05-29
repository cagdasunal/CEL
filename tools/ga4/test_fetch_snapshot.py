#!/usr/bin/env python3
"""Tests for tools/ga4/fetch_snapshot.py — the PURE curation logic (no network).

Guards the client-facing contract: friendly labels, locale badges, trend arrow,
zero/(not set) suppression, and a jargon-free / zero-free assembled snapshot.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.ga4.fetch_snapshot import (  # noqa: E402
    assemble,
    build_insight,
    curate_channels,
    curate_countries,
    curate_pages,
    friendly_page_title,
    momentum,
    visitors_phrase,
)


class TestPureHelpers(unittest.TestCase):
    def test_visitors_phrase_rounds_down(self):
        self.assertEqual(visitors_phrase(8095), "Over 8,000 people visited your website in the last 28 days")
        self.assertIn("Over 12,500", visitors_phrase(12990))
        # small counts shown exactly, never "Over 0"
        self.assertTrue(visitors_phrase(300).startswith("300 "))

    def test_momentum_direction_and_phrase(self):
        self.assertEqual(momentum(105, 100)["direction"], "up")
        self.assertEqual(momentum(90, 100)["direction"], "down")
        self.assertEqual(momentum(100, 100)["direction"], "flat")
        self.assertEqual(momentum(100, 0)["direction"], "flat")  # no prior -> no fake trend
        self.assertEqual(momentum(90, 100)["pct"], 10)  # always positive magnitude

    def test_friendly_page_title_locale_badge(self):
        self.assertEqual(friendly_page_title("/pt/san-diego-ca/clases-de-ingles"),
                         {"title": "Clases De Ingles", "badge": "Portuguese",
                          "path": "/pt/san-diego-ca/clases-de-ingles"})
        self.assertEqual(friendly_page_title("/")["title"], "Home page")
        self.assertIsNone(friendly_page_title("/courses/general-english")["badge"])  # en = no badge

    def test_curate_channels_top3_labels_and_zero_drop(self):
        rows = [("Direct", 4280), ("Organic Search", 3406), ("Referral", 177),
                ("Organic Social", 125), ("(not set)", 50), ("Paid Search", 0)]
        out = curate_channels(rows)
        self.assertEqual(len(out), 3)                       # top-3 only
        self.assertEqual(out[0]["raw"], "Direct")           # sorted desc
        self.assertEqual(out[0]["label"], "Came to you directly")  # friendly label
        self.assertTrue(all(c["users"] > 0 for c in out))   # no zero rows
        self.assertNotIn("(not set)", [c["raw"] for c in out])
        self.assertEqual(out[0]["pct"], 54)                 # 4280/(4280+3406+177+125)=53.6% -> 54 ((not set) dropped first)

    def test_curate_pages_drops_empty_and_caps(self):
        rows = [(f"/p{i}", 100 - i) for i in range(8)] + [("/zero", 0), ("", 5)]
        out = curate_pages(rows, limit=5)
        self.assertEqual(len(out), 5)
        self.assertTrue(all(p["views"] > 0 and p["path"] for p in out))

    def test_curate_countries_names_and_zero_drop(self):
        out = curate_countries([("United States", 5000), ("(not set)", 9), ("Brazil", 1000), ("Nowhere", 0)])
        self.assertEqual([c["name"] for c in out], ["United States", "Brazil"])

    def test_build_insight_picks_top_channel(self):
        self.assertIn("brand", build_insight(curate_channels([("Direct", 100), ("Referral", 10)])))
        self.assertIn("SEO", build_insight(curate_channels([("Organic Search", 100), ("Direct", 10)])))
        self.assertEqual(build_insight([]), "")

    def test_assemble_is_jargon_free_and_zero_free(self):
        snap = assemble(
            total_28d=8095, last14=2100, prior14=2000,
            channel_rows=[("Direct", 4280), ("Organic Search", 3406), ("(not set)", 9)],
            page_rows=[("/pt/x-y", 50), ("/", 40)],
            country_rows=[("United States", 5000), ("(not set)", 3)],
            generated_at="2026-05-29 11:00 AM PDT",
        )
        blob = repr(snap)
        for banned in ("(not set)", "GTM", "dataLayer", "Consent Mode", "measurement ID",
                       "sessionDefaultChannelGroup", "screenPageViews", "totalUsers"):
            self.assertNotIn(banned, blob, f"jargon/raw leaked into snapshot: {banned}")
        self.assertEqual(snap["visitors_28d"], 8095)
        self.assertEqual(snap["momentum"]["direction"], "up")
        self.assertTrue(snap["insight"])
        self.assertTrue(all(c["users"] > 0 for c in snap["channels"]))
        self.assertTrue(all(c["users"] > 0 for c in snap["countries"]))


if __name__ == "__main__":
    unittest.main()
