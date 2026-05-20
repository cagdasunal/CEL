"""Tests for the translation memory."""
from tools.translation_engine.tm import TranslationMemory, tm_key


def test_key_includes_glossary_version():
    """A glossary-version change MUST produce a different key (invalidates stale hits)."""
    k1 = tm_key("hello", "de", "v1")
    k2 = tm_key("hello", "de", "v2")
    assert k1 != k2


def test_key_normalizes_whitespace():
    assert tm_key("hello   world", "de", "v1") == tm_key("hello world", "de", "v1")


def test_get_put_roundtrip(tmp_path):
    tm = TranslationMemory(tmp_path / "tm.json")
    assert tm.get("Welcome", "de", "v1") is None
    tm.put("Welcome", "de", "v1", "Willkommen")
    assert tm.get("Welcome", "de", "v1") == "Willkommen"
    # Different locale / version → miss.
    assert tm.get("Welcome", "fr", "v1") is None
    assert tm.get("Welcome", "de", "v2") is None


def test_save_and_reload(tmp_path):
    path = tmp_path / "tm.json"
    tm = TranslationMemory(path)
    tm.put("Hello", "es", "v1", "Hola")
    tm.save()
    assert path.exists()
    reloaded = TranslationMemory(path)
    assert reloaded.get("Hello", "es", "v1") == "Hola"
    assert len(reloaded) == 1


def test_glossary_version_bump_invalidates_hit(tmp_path):
    tm = TranslationMemory(tmp_path / "tm.json")
    tm.put("Courses", "de", "v1", "Kurse")
    assert tm.get("Courses", "de", "v1") == "Kurse"
    assert tm.get("Courses", "de", "v2") is None  # version bump → cache miss
