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


def test_tm_evicts_oldest_over_cap(monkeypatch):
    """tracker-093 L3: the memory caps its size (FIFO) so it can't grow unbounded."""
    from tools.translation_engine import tm as tm_mod

    monkeypatch.setattr(tm_mod, "_MAX_ENTRIES", 3)
    m = tm_mod.TranslationMemory(None)
    for i in range(5):
        m.put(f"src{i}", "de", "v1", f"tgt{i}")
    assert len(m) == 3
    # The two oldest (src0, src1) were evicted; the three newest remain.
    assert m.get("src0", "de", "v1") is None
    assert m.get("src1", "de", "v1") is None
    assert m.get("src4", "de", "v1") == "tgt4"


def test_tm_update_existing_key_does_not_evict(monkeypatch):
    """Updating an existing key must not trigger eviction (store size unchanged)."""
    from tools.translation_engine import tm as tm_mod

    monkeypatch.setattr(tm_mod, "_MAX_ENTRIES", 2)
    m = tm_mod.TranslationMemory(None)
    m.put("a", "de", "v1", "A")
    m.put("b", "de", "v1", "B")
    m.put("a", "de", "v1", "A2")  # update, not new → no eviction
    assert len(m) == 2
    assert m.get("a", "de", "v1") == "A2"
    assert m.get("b", "de", "v1") == "B"
