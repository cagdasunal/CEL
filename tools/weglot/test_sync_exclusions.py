#!/usr/bin/env python3
"""Tests for Weglot exclusion sync script."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add the tools/weglot directory to path
sys.path.insert(0, str(Path(__file__).parent))
import sync_exclusions
from sync_exclusions import (
    compute_excluded_languages,
    extract_post_data,
    create_robust_session,
    HTTP,
    HTTP_TIMEOUT,
    LANGUAGE_ID_MAP,
    ALL_TRANSLATED_LANGS,
)


# ---------------------------------------------------------------------------
# compute_excluded_languages
# ---------------------------------------------------------------------------

class TestComputeExcludedLanguages:
    def test_english_post_excludes_all_translated(self):
        result = compute_excluded_languages("en")
        assert result == sorted(ALL_TRANSLATED_LANGS)
        assert len(result) == 8
        assert "en" not in result

    def test_german_post_excludes_all_except_german(self):
        result = compute_excluded_languages("de")
        assert "de" not in result
        assert len(result) == 7
        assert "ar" in result
        assert "es" in result
        assert "fr" in result

    def test_french_post_excludes_all_except_french(self):
        result = compute_excluded_languages("fr")
        assert "fr" not in result
        assert "de" in result
        assert len(result) == 7

    def test_korean_post_excludes_all_except_korean(self):
        result = compute_excluded_languages("ko")
        assert "ko" not in result
        assert len(result) == 7

    def test_italian_post_excludes_all_except_italian(self):
        result = compute_excluded_languages("it")
        assert "it" not in result
        assert len(result) == 7

    def test_all_languages_covered(self):
        """Every language in ALL_TRANSLATED_LANGS should produce correct exclusions."""
        for lang in ALL_TRANSLATED_LANGS:
            result = compute_excluded_languages(lang)
            assert lang not in result
            assert len(result) == 7

    def test_result_is_sorted(self):
        result = compute_excluded_languages("en")
        assert result == sorted(result)

    def test_english_matches_csv_pattern(self):
        """English posts should produce the same exclusion list as seen in the CSV."""
        result = compute_excluded_languages("en")
        expected = ["ar", "de", "es", "fr", "it", "ja", "ko", "pt"]
        assert result == expected

    def test_german_matches_csv_pattern(self):
        """German posts should produce: ar,es,fr,it,ja,ko,pt (no de)."""
        result = compute_excluded_languages("de")
        expected = ["ar", "es", "fr", "it", "ja", "ko", "pt"]
        assert result == expected


# ---------------------------------------------------------------------------
# extract_post_data
# ---------------------------------------------------------------------------

class TestExtractPostData:
    def _make_item(self, slug, lang_id, draft=False, archived=False):
        return {
            "id": f"item-{slug}",
            "isDraft": draft,
            "isArchived": archived,
            "lastPublished": "2026-04-13T10:00:00Z",
            "fieldData": {
                "slug": slug,
                "name": f"Post {slug}",
                "language": lang_id,
            },
        }

    def test_extracts_published_post(self):
        items = [self._make_item("my-post", "6876590744e1f69b128ef245")]  # English
        result = extract_post_data(items)
        assert len(result) == 1
        assert result[0]["slug"] == "my-post"
        assert result[0]["language"] == "en"
        assert result[0]["url_path"] == "/post/my-post"

    def test_includes_draft_with_lastPublished(self):
        """isDraft=True + lastPublished set = published with unsaved edits → still live."""
        item = self._make_item("draft-post", "6876590744e1f69b128ef245", draft=True)
        item["lastPublished"] = "2026-03-05T14:49:54.784Z"
        result = extract_post_data([item])
        assert len(result) == 1

    def test_skips_draft_never_published(self):
        """isDraft=True + no lastPublished = truly unpublished draft."""
        item = self._make_item("draft-post", "6876590744e1f69b128ef245", draft=True)
        item["lastPublished"] = None
        result = extract_post_data([item])
        assert len(result) == 0

    def test_skips_archived(self):
        items = [self._make_item("archived-post", "6876590744e1f69b128ef245", archived=True)]
        result = extract_post_data(items)
        assert len(result) == 0

    def test_skips_unpublished_scheduled(self):
        """Scheduled posts have isDraft=False but lastPublished=None."""
        item = self._make_item("scheduled-post", "6876590744e1f69b128ef245")
        item["lastPublished"] = None
        result = extract_post_data([item])
        assert len(result) == 0

    def test_includes_published_post(self):
        """Published posts have a lastPublished timestamp."""
        item = self._make_item("published-post", "6876590744e1f69b128ef245")
        item["lastPublished"] = "2026-04-13T10:00:00Z"
        result = extract_post_data([item])
        assert len(result) == 1

    def test_skips_no_language(self):
        item = self._make_item("no-lang", "6876590744e1f69b128ef245")
        item["fieldData"]["language"] = ""
        result = extract_post_data([item])
        assert len(result) == 0

    def test_skips_unknown_language_ref(self):
        items = [self._make_item("unknown-lang", "000000000000000000000000")]
        result = extract_post_data(items)
        assert len(result) == 0

    def test_maps_all_languages(self):
        """Every language ID in LANGUAGE_ID_MAP should map correctly."""
        for lang_id, expected_code in LANGUAGE_ID_MAP.items():
            items = [self._make_item(f"post-{expected_code}", lang_id)]
            result = extract_post_data(items)
            assert len(result) == 1
            assert result[0]["language"] == expected_code

    def test_multiple_posts(self):
        items = [
            self._make_item("en-post", "6876590744e1f69b128ef245"),  # English
            self._make_item("de-post", "6876596a3a4d6e078bebe528"),  # German
            self._make_item("fr-post", "687659b3281d98a9803a86ae"),  # French
        ]
        result = extract_post_data(items)
        assert len(result) == 3
        langs = {r["language"] for r in result}
        assert langs == {"en", "de", "fr"}


# ---------------------------------------------------------------------------
# LANGUAGE_ID_MAP consistency
# ---------------------------------------------------------------------------

class TestLanguageIdMap:
    def test_all_translated_langs_have_ids(self):
        """Every language in ALL_TRANSLATED_LANGS should have a mapping."""
        mapped_codes = set(LANGUAGE_ID_MAP.values())
        for lang in ALL_TRANSLATED_LANGS:
            assert lang in mapped_codes, f"Language '{lang}' missing from LANGUAGE_ID_MAP"

    def test_english_has_id(self):
        assert "en" in LANGUAGE_ID_MAP.values()

    def test_nine_languages_total(self):
        assert len(LANGUAGE_ID_MAP) == 9  # 8 translated + English

    def test_all_ids_are_24_char_hex(self):
        for lang_id in LANGUAGE_ID_MAP:
            assert len(lang_id) == 24, f"ID '{lang_id}' is not 24 chars"


# ---------------------------------------------------------------------------
# Sitemap filtering (is_excluded_translation)
# ---------------------------------------------------------------------------

class TestSitemapExclusionFiltering:
    """Test the is_excluded_translation function from the sitemap generator."""

    def test_import_sitemap_function(self):
        """Verify we can import the filtering function."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from generate_master_sitemap import is_excluded_translation
        assert callable(is_excluded_translation)

    def test_excluded_translation_detected(self):
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from generate_master_sitemap import is_excluded_translation

        exclusion_map = {"/post/my-english-post": ["ar", "de", "es", "fr", "it", "ja", "ko", "pt"]}
        assert is_excluded_translation(
            "https://www.englishcollege.com/de/post/my-english-post", exclusion_map
        ) is True

    def test_non_excluded_translation_passes(self):
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from generate_master_sitemap import is_excluded_translation

        exclusion_map = {"/post/my-german-post": ["ar", "es", "fr", "it", "ja", "ko", "pt"]}
        # German is NOT in the exclusion list → should pass
        assert is_excluded_translation(
            "https://www.englishcollege.com/de/post/my-german-post", exclusion_map
        ) is False

    def test_non_post_url_passes(self):
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from generate_master_sitemap import is_excluded_translation

        exclusion_map = {"/post/something": ["de"]}
        assert is_excluded_translation(
            "https://www.englishcollege.com/de/about", exclusion_map
        ) is False

    def test_empty_exclusion_map(self):
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from generate_master_sitemap import is_excluded_translation

        assert is_excluded_translation(
            "https://www.englishcollege.com/de/post/anything", {}
        ) is False

    def test_slug_not_in_map(self):
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from generate_master_sitemap import is_excluded_translation

        exclusion_map = {"/post/other-slug": ["de"]}
        assert is_excluded_translation(
            "https://www.englishcollege.com/de/post/different-slug", exclusion_map
        ) is False


class TestRetryAdapter:
    """Verify the HTTP session retry configuration is wired correctly.

    The real-world behavior was verified against a live Webflow outage
    on 2026-04-14 (scheduled run 24404045978 retried for roughly 3
    minutes before bubbling the error). These tests are regression
    guards — if someone removes the retry adapter, drops the backoff,
    or reverts HTTP.get to a bare requests.get, at least one of these
    tests will fail.
    """

    def test_http_timeout_is_60s(self):
        # Bumped from 30s after Apr 14 flake where a cold Webflow API
        # connection took slightly over 30s to respond.
        assert HTTP_TIMEOUT == 60

    def test_module_level_session_is_a_session(self):
        import requests
        assert isinstance(HTTP, requests.Session)

    def test_https_has_retry_adapter(self):
        from requests.adapters import HTTPAdapter
        session = create_robust_session()
        adapter = session.get_adapter("https://api.webflow.com")
        assert isinstance(adapter, HTTPAdapter)
        assert adapter.max_retries.total == 4

    def test_http_has_retry_adapter(self):
        from requests.adapters import HTTPAdapter
        session = create_robust_session()
        adapter = session.get_adapter("http://example.com")
        assert isinstance(adapter, HTTPAdapter)

    def test_retry_config_matches_spec(self):
        session = create_robust_session()
        retry = session.get_adapter("https://api.webflow.com").max_retries
        assert retry.total == 4
        assert retry.connect == 4
        assert retry.read == 4
        assert retry.backoff_factor == 2
        # Must retry on rate limit and transient 5xx
        assert 429 in retry.status_forcelist
        assert 500 in retry.status_forcelist
        assert 502 in retry.status_forcelist
        assert 503 in retry.status_forcelist
        assert 504 in retry.status_forcelist
        # GET must be allowed (idempotent). allowed_methods can be None
        # (meaning "all verbs") or a set on older urllib3 versions.
        assert retry.allowed_methods is None or "GET" in retry.allowed_methods

    def test_fetch_all_blog_posts_uses_session(self):
        """If someone replaces HTTP.get with a bare requests.get, the retry
        adapter gets bypassed. This test catches that regression by
        patching HTTP.get and verifying fetch_all_blog_posts reaches it
        with the configured 60s timeout."""
        with patch.object(sync_exclusions.HTTP, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"items": [], "pagination": {"total": 0}}
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            sync_exclusions.fetch_all_blog_posts("dummy-token")

            mock_get.assert_called_once()
            _, kwargs = mock_get.call_args
            assert kwargs.get("timeout") == HTTP_TIMEOUT

    def test_fetch_weglot_exclusions_uses_session(self):
        """Same regression guard for the Weglot read path."""
        with patch.object(sync_exclusions.HTTP, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"excluded_paths": []}
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            sync_exclusions.fetch_weglot_exclusions("dummy-key")

            mock_get.assert_called_once()
            _, kwargs = mock_get.call_args
            assert kwargs.get("timeout") == HTTP_TIMEOUT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
