"""Tests for scripts/watermark_cleaner.py — the CLI + Webflow replace orchestrator.

Every Webflow call is mocked. Nothing here touches a live site, and the tests
assert that: with ``--apply`` absent no write function is called at all, and
with the asset id changing under an unrewritable reference the tool REFUSES
rather than half-replacing.

The engine itself is covered by test_image_provenance.py; this file covers the
plumbing around it — filename recovery, URL matching, reference indexing,
re-pointing, the refusal rule, and the two safety gates on ``--apply``.
"""
from __future__ import annotations

import ast
import inspect
import io
import json
import struct
import urllib.error
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import image_provenance as ip  # noqa: E402
import watermark_cleaner as wc  # noqa: E402


# ── fixtures ─────────────────────────────────────────────────────────────────
C2PA_BLOB = (b"jumb jumdc2pa c2pa.actions.v2 softwareAgent gpt-image "
             b"digitalSourceType http://cv.iptc.org/newscodes/digitalsourcetype/"
             b"trainedAlgorithmicMedia c2pa.watermarked.unbound")


def _png(chunks: list[tuple[bytes, bytes]] | None = None, w: int = 4, h: int = 4) -> bytes:
    def chunk(t: bytes, p: bytes) -> bytes:
        return struct.pack(">I", len(p)) + t + p + struct.pack(">I", zlib.crc32(t + p) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(sum(([x * 7 % 256, y * 11 % 256, 90] for x in range(w)), []))
                   for y in range(h))
    out = ip._PNG_MAGIC + chunk(b"IHDR", ihdr)
    for t, p in (chunks or []):
        out += chunk(t, p)
    return out + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


DIRTY_PNG = _png([(b"caBX", C2PA_BLOB), (b"tEXt", b"hf-job-id\x00abc123")])
CLEAN_PNG = _png()

SITE_ID = "667453c576e8d35c454cc9ae"
# Webflow asset ids are exactly 24 lowercase hex characters. asset_basename()
# keys off that, so stand-in ids must have the real shape or the fixtures
# exercise the "not an id prefix" branch instead of the one under test.
AID_HERO = "6a7dad834766eebcddd96d9f"
AID_G1 = "6a620a101f6fcd374ae5ff6e"
AID_G2 = "6a5eacbdda5b625a401a9d27"
AID_BODY = "6a64cf0d1dca4280e32ebdab"
AID_NEW = "6b0000000000000000000001"
AID_LOGO = "6b0000000000000000000002"
CDN = f"https://cdn.prod.website-files.com/{SITE_ID}"


def _asset(aid: str, name: str) -> dict:
    return {
        "id": aid,
        "originalFileName": f"{aid}_{name}",
        "displayName": name,
        "hostedUrl": f"{CDN}/{aid}_{name}",
        "contentType": "image/png",
    }


# ── filename recovery ────────────────────────────────────────────────────────
class TestAssetBasename:
    def test_strips_the_asset_id_prefix(self):
        assert wc.asset_basename("6a7dad834766eebcddd96d9f_hero.png") == "hero.png"

    def test_keeps_underscores_that_are_not_an_asset_id(self):
        # 'my' is not 24 hex chars, so the underscore is part of the name.
        assert wc.asset_basename("my_photo_2026.png") == "my_photo_2026.png"

    def test_keeps_underscores_after_the_id_is_removed(self):
        assert wc.asset_basename("6a7dad834766eebcddd96d9f_cel_san_diego.avif") == "cel_san_diego.avif"

    def test_percent_decodes(self):
        assert wc.asset_basename("6a7dad834766eebcddd96d9f_CEL%20Hero.avif") == "CEL Hero.avif"

    def test_falls_back_to_display_name(self):
        assert wc.asset_basename("", "fallback.png") == "fallback.png"

    def test_empty_input(self):
        assert wc.asset_basename("", "") == ""

    def test_24_char_non_hex_prefix_is_not_treated_as_an_id(self):
        name = "z" * 24 + "_real.png"
        assert wc.asset_basename(name) == name


# ── URL matching ─────────────────────────────────────────────────────────────
class TestUrlKey:
    def test_matches_across_cdn_hosts(self):
        a = f"https://cdn.prod.website-files.com/{SITE_ID}/abc_hero.png"
        b = f"https://uploads-ssl.webflow.com/{SITE_ID}/abc_hero.png"
        assert wc._url_key(a) == wc._url_key(b)

    def test_matches_across_percent_encoding(self):
        a = f"{CDN}/abc_CEL%20Hero.avif"
        b = f"{CDN}/abc_CEL Hero.avif"
        assert wc._url_key(a) == wc._url_key(b)

    def test_ignores_query_string(self):
        assert wc._url_key(f"{CDN}/abc_hero.png?v=2") == wc._url_key(f"{CDN}/abc_hero.png")

    def test_distinguishes_different_files(self):
        assert wc._url_key(f"{CDN}/abc_a.png") != wc._url_key(f"{CDN}/abc_b.png")

    def test_empty(self):
        assert wc._url_key("") == ""


class TestBasenameMatching:
    """Regression: brightvalley's site assets and CMS images share NO exact key.

    On a WordPress-imported site the id stamped into a CMS field's URL is not
    the site-asset id — measured: 214 asset keys, 164 CMS keys, **zero** overlap
    under _url_key. Joining on the exact key there reported every flagged image
    as "referenced nowhere", which is the input to the refuse-or-proceed
    decision and reads as "safe to replace". All 7 were in fact one blog post.
    """

    def test_strips_a_single_id_prefix(self):
        assert wc._strip_id_prefixes(f"{AID_HERO}_hero.png") == "hero.png"

    def test_strips_stacked_id_prefixes(self):
        # Real shape from brightvalley: {id}_{id}_team-13-danny-v2.webp
        doubled = f"{AID_HERO}_{AID_G1}_team-13-danny-v2.webp"
        assert wc._strip_id_prefixes(doubled) == "team-13-danny-v2.webp"

    def test_leaves_a_non_id_prefix_alone(self):
        assert wc._strip_id_prefixes("my_photo_2026.png") == "my_photo_2026.png"

    def test_basename_key_matches_across_differing_ids(self):
        a = f"https://s3.amazonaws.com/webflow-prod-assets/{SITE_ID}/{AID_HERO}_shot.png"
        b = f"{CDN}/{AID_G1}_shot.png"
        assert wc._url_key(a) != wc._url_key(b), "the exact keys differ — that is the bug's premise"
        assert wc._basename_key(a) == wc._basename_key(b) == "shot.png"

    def test_lookup_prefers_an_exact_match(self):
        ref = wc.Reference(kind="image", collection_id="c", collection_slug="blog",
                           item_id="i", item_slug="s", field_slug="f")
        url = f"{CDN}/{AID_HERO}_shot.png"
        index = {wc._url_key(url): [ref], f"{AID_G1}_shot.png": []}
        refs, how = wc.lookup_refs(index, url)
        assert how == "exact" and refs == [ref]

    def test_lookup_falls_back_to_basename(self):
        ref = wc.Reference(kind="image", collection_id="c", collection_slug="blog",
                           item_id="i", item_slug="s", field_slug="f")
        index = {f"{AID_G1}_shot.png": [ref]}
        refs, how = wc.lookup_refs(index, f"{CDN}/{AID_HERO}_shot.png")
        assert how == "basename" and refs == [ref]

    def test_lookup_reports_ambiguity_instead_of_guessing(self):
        """Two different pictures sharing a filename must never be silently joined."""
        r1 = wc.Reference(kind="image", collection_id="c", collection_slug="blog",
                          item_id="i1", item_slug="a", field_slug="f")
        r2 = wc.Reference(kind="image", collection_id="c", collection_slug="team",
                          item_id="i2", item_slug="b", field_slug="f")
        index = {f"{AID_G1}_shot.png": [r1], f"{AID_G2}_shot.png": [r2]}
        refs, how = wc.lookup_refs(index, f"{CDN}/{AID_HERO}_shot.png")
        assert how == "ambiguous"
        assert len(refs) == 2

    def test_lookup_reports_none_when_truly_absent(self):
        refs, how = wc.lookup_refs({f"{AID_G1}_other.png": []}, f"{CDN}/{AID_HERO}_shot.png")
        assert how == "none" and refs == []


class TestSiteTokenRouting:
    """Self-contained: builds its own registry rather than reading the repo's.

    The CEL checkout carries a minimal CEL-only registry mirror, so tests that
    assume `brightvalley` is present pass in the monorepo and fail there — which
    is how the first version of these broke on the vendored copy.
    """

    @pytest.fixture
    def fake_repo(self, tmp_path, monkeypatch):
        (tmp_path / "sites").mkdir()
        (tmp_path / "sites" / "registry.json").write_text(json.dumps({
            "sites": {
                "sitea": {"webflow_connection": {"rest_token_env": "TOKEN_SITE_A"}},
                "siteb": {"webflow_connection": {"rest_token_env": "TOKEN_SITE_B"}},
                "nocfg": {},
            }
        }))
        monkeypatch.setattr(wc, "ROOT", tmp_path)
        return tmp_path

    def test_explicit_override_wins(self, fake_repo, monkeypatch):
        monkeypatch.setenv("TOKEN_SITE_A", "from-env")
        assert wc.resolve_site_token("sitea", "OVERRIDE") == "OVERRIDE"

    def test_reads_the_env_var_named_in_the_registry(self, fake_repo, monkeypatch):
        monkeypatch.setenv("TOKEN_SITE_A", "a-token")
        monkeypatch.setattr(wc, "get_api_token", lambda *a, **k: "generic")
        assert wc.resolve_site_token("sitea") == "a-token"

    def test_reads_it_from_dotenv_when_not_in_the_environment(self, fake_repo, monkeypatch):
        monkeypatch.delenv("TOKEN_SITE_B", raising=False)
        (fake_repo / ".env").write_text('OTHER=x\nTOKEN_SITE_B="b-token"\n')
        monkeypatch.setattr(wc, "get_api_token", lambda *a, **k: "generic")
        assert wc.resolve_site_token("siteb") == "b-token"

    def test_falls_back_to_the_generic_token_for_an_unknown_site(self, fake_repo, monkeypatch):
        monkeypatch.setattr(wc, "get_api_token", lambda *a, **k: "generic")
        assert wc.resolve_site_token("no-such-site") == "generic"

    def test_site_without_a_connection_block_falls_back(self, fake_repo, monkeypatch):
        monkeypatch.setattr(wc, "get_api_token", lambda *a, **k: "generic")
        assert wc.resolve_site_token("nocfg") == "generic"

    def test_two_sites_resolve_to_different_tokens(self, fake_repo, monkeypatch):
        """The failure this prevents is silent: wrong token -> 404 on every asset."""
        monkeypatch.setenv("TOKEN_SITE_A", "a")
        monkeypatch.setenv("TOKEN_SITE_B", "b")
        assert wc.resolve_site_token("sitea") != wc.resolve_site_token("siteb")

    def test_missing_registry_does_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wc, "ROOT", tmp_path)          # no sites/registry.json at all
        monkeypatch.setattr(wc, "get_api_token", lambda *a, **k: "generic")
        assert wc.resolve_site_token("anything") == "generic"


class TestPerceptualLineage:
    """Metadata detection cannot see an AI image that was resized or converted.

    Lineage answers the question metadata cannot: this uploaded WebP is a
    re-encode of a specific original that DID carry a Higgsfield/gpt-image
    marker. Measured on the real corpus: same image after resize+WebP scores
    1-9 of 512; different images score 228-270. PHASH_MATCH_MAX=40 sits in
    that gap with enormous margin on both sides.
    """

    @pytest.fixture(autouse=True)
    def _need_pillow(self):
        pytest.importorskip("PIL")

    def _img(self, seed: int, w: int = 96, h: int = 96) -> bytes:
        """A SMOOTH, photograph-like test image.

        Not a high-frequency pattern: a difference hash downsamples to 16x16, so
        content that cycles every few pixels turns into aliasing noise and its
        hash is unstable under any resampling. Real photographs — what this tool
        processes — are low-frequency. An earlier version of this fixture used
        `(x*seed) % 256`, which made a correct trim look like a failure and would
        have sent someone tuning the threshold to fit an artefact.
        """
        from PIL import Image
        import math
        im = Image.new("RGB", (w, h))
        im.putdata([
            (
                int(128 + 110 * math.sin((x / w) * 2.1 + seed)),
                int(128 + 110 * math.sin((y / h) * 1.7 + seed * 0.7)),
                int(128 + 110 * math.sin(((x + y) / (w + h)) * 2.6 + seed * 1.3)),
            )
            for y in range(h) for x in range(w)
        ])
        buf = io.BytesIO(); im.save(buf, format="PNG"); return buf.getvalue()

    def _resized_webp(self, data: bytes, w: int) -> bytes:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGB")
        im = im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)
        buf = io.BytesIO(); im.save(buf, format="WEBP", quality=80); return buf.getvalue()

    def test_hash_is_stable_for_identical_bytes(self):
        d = self._img(7)
        assert wc.perceptual_hash(d) == wc.perceptual_hash(d)

    def test_survives_resize_and_format_conversion(self):
        orig = self._img(11)
        derived = self._resized_webp(orig, 48)
        dist = wc.hamming(wc.perceptual_hash(orig), wc.perceptual_hash(derived))
        assert dist <= wc.PHASH_MATCH_MAX, f"resize+WebP moved the hash by {dist}"

    def test_different_images_are_far_apart(self):
        dist = wc.hamming(wc.perceptual_hash(self._img(3)), wc.perceptual_hash(self._img(29)))
        assert dist > wc.PHASH_MATCH_MAX * 2, f"unrelated images only {dist} apart"

    def test_the_threshold_sits_in_a_real_gap(self):
        """Guard the guard: if match and non-match distances ever overlap, the
        threshold is meaningless and this test must fail before the tool lies."""
        matches, nonmatches = [], []
        for seed in (5, 13, 23, 41):
            o = self._img(seed)
            matches.append(wc.hamming(wc.perceptual_hash(o),
                                      wc.perceptual_hash(self._resized_webp(o, 48))))
        for a, b in ((5, 13), (13, 23), (23, 41), (5, 41)):
            nonmatches.append(wc.hamming(wc.perceptual_hash(self._img(a)),
                                         wc.perceptual_hash(self._img(b))))
        assert max(matches) < wc.PHASH_MATCH_MAX < min(nonmatches), (
            f"threshold {wc.PHASH_MATCH_MAX} does not separate "
            f"matches{matches} from non-matches{nonmatches}")

    def test_padding_no_longer_defeats_the_match(self):
        """Regression, measured on the real team-headshot pipeline.

        The plain hash moved 99-205 bits under 92-284px of padding — past the
        threshold, so a padded derivative of a known AI original scored as
        unrelated. That is the transform the Team Members photos went through.
        """
        from PIL import Image
        orig = self._img(17, 200, 200)
        im = Image.open(io.BytesIO(orig)).convert("RGB")
        canvas = Image.new("RGB", (im.width + 160, im.height + 200), (255, 255, 255))
        canvas.paste(im, (80, 120))
        canvas = canvas.resize((300, int(canvas.height * 300 / canvas.width)), Image.LANCZOS)
        buf = io.BytesIO(); canvas.save(buf, format="WEBP", quality=82)
        padded = buf.getvalue()

        plain = wc.hamming(wc.perceptual_hash(orig), wc.perceptual_hash(padded))
        paired = wc.fingerprint_distance(wc.perceptual_fingerprint(orig),
                                         wc.perceptual_fingerprint(padded))
        assert plain > wc.PHASH_MATCH_MAX, (
            f"fixture is not actually padded enough to break the plain hash (got {plain}) — "
            "this test would pass vacuously")
        # A RELATIVE claim, deliberately: it holds for any fixture, so it cannot
        # be satisfied by tuning the threshold to fit this one. The absolute
        # "comes under the threshold" claim is asserted against REAL photographs
        # in test_padding_rescued_on_real_images, because that is the actual data
        # domain — a synthetic pattern downsampled to 16x16 is dominated by the
        # trim boundary and lands near the threshold no matter how good the fix is.
        assert paired < plain / 2, (
            f"trimming barely helped: {plain} -> {paired}. Expected a large reduction.")

    @pytest.mark.skipif(
        not (ROOT / "sites/brightvalley/assets/office-scenes/A1-gabriela-solo.png").is_file(),
        reason="needs a real photograph from the corpus")
    def test_padding_rescued_on_real_images(self):
        """The absolute claim, on the real data domain.

        Reproduces the actual team-headshot transform (scale + pad + 700px WebP,
        parameters from iod-report.json) against a real photograph. Measured
        before the fix: 99-205 bits, i.e. scored as unrelated. After: 3-8.
        """
        from PIL import Image
        src = (ROOT / "sites/brightvalley/assets/office-scenes/A1-gabriela-solo.png").read_bytes()
        im = Image.open(io.BytesIO(src)).convert("RGB")
        im = im.resize((int(im.width * 0.929), int(im.height * 0.929)), Image.LANCZOS)
        canvas = Image.new("RGB", (im.width + 81, im.height + 203), (255, 255, 255))
        canvas.paste(im, (0, 203))
        canvas = canvas.resize((700, int(canvas.height * 700 / canvas.width)), Image.LANCZOS)
        buf = io.BytesIO(); canvas.save(buf, format="WEBP", quality=82)

        plain = wc.hamming(wc.perceptual_hash(src), wc.perceptual_hash(buf.getvalue()))
        paired = wc.fingerprint_distance(wc.perceptual_fingerprint(src),
                                         wc.perceptual_fingerprint(buf.getvalue()))
        assert plain > wc.PHASH_MATCH_MAX, f"fixture no longer reproduces the defect ({plain})"
        assert paired <= wc.PHASH_MATCH_MAX, (
            f"a padded derivative of a real photograph still misses ({paired})")

    def test_trimming_does_not_make_unrelated_images_collide(self):
        a, b = self._img(5, 160, 160), self._img(37, 160, 160)
        d = wc.fingerprint_distance(wc.perceptual_fingerprint(a), wc.perceptual_fingerprint(b))
        assert d > wc.PHASH_MATCH_MAX * 2, f"trim-aware matching collided unrelated images ({d})"

    def test_near_uniform_image_is_not_trimmed_to_nothing(self):
        """A flat image must not trim away to a sliver — every flat image would
        then collide with every other."""
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (200, 200), (240, 240, 240)).save(buf, format="PNG")
        flat = buf.getvalue()
        trimmed = wc._autotrim(Image.open(io.BytesIO(flat)))
        assert trimmed.width >= 200 * 0.3 and trimmed.height >= 200 * 0.3

    def test_flat_images_are_degenerate_and_never_match(self):
        """A difference hash on a flat image is all zeros — so ALL flat images
        match each other at distance 0.

        Measured: five different solid colours all scored 0 against each other,
        while 25 real photographs from the corpus scored 189-241 bits of 512.
        Without a guard, lineage would report a client's plain-colour tile as a
        derivative of an AI original — the worst false positive available,
        because it labels real work as machine-made.
        """
        from PIL import Image
        fps = []
        for colour in [(128, 128, 128), (255, 255, 255), (0, 0, 0), (18, 110, 245)]:
            buf = io.BytesIO()
            Image.new("RGB", (200, 200), colour).save(buf, format="PNG")
            fp = wc.perceptual_fingerprint(buf.getvalue())
            assert wc.fingerprint_is_degenerate(fp), f"{colour} should be degenerate"
            fps.append(fp)
        # premise of the guard: they really are indistinguishable
        assert wc.fingerprint_distance(fps[0], fps[1]) <= wc.PHASH_MATCH_MAX

    def test_real_photographs_are_not_degenerate(self):
        """The guard must not exclude the images lineage exists to match."""
        for seed in (5, 13, 29):
            fp = wc.perceptual_fingerprint(self._img(seed, 160, 160))
            assert not wc.fingerprint_is_degenerate(fp), "a real image was called degenerate"

    def test_degenerate_originals_never_enter_the_corpus(self, tmp_path):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (200, 200), (255, 255, 255)).save(buf, format="PNG")
        flat = bytearray(buf.getvalue())
        # give it an AI marker so only the degeneracy check can exclude it
        import zlib as _z
        payload = b"hf-job-id\x00abc123"
        chunk = struct.pack(">I", len(payload)) + b"tEXt" + payload + \
            struct.pack(">I", _z.crc32(b"tEXt" + payload) & 0xFFFFFFFF)
        flat[33:33] = chunk
        (tmp_path / "flat.png").write_bytes(bytes(flat))
        assert ip.scan(bytes(flat)).is_ai_flagged, "fixture must be AI-marked"
        assert wc.build_lineage_corpus([str(tmp_path)], progress=False)[0] == [], \
            "a flat original identifies nothing and must not seed the corpus"

    def test_corpus_only_includes_ai_marked_files(self, tmp_path):
        (tmp_path / "clean.png").write_bytes(self._img(9))
        dirty = tmp_path / "dirty.png"
        dirty.write_bytes(_png([(b"tEXt", b"hf-job-id\x00abc123")]))
        corpus, _empty = wc.build_lineage_corpus([str(tmp_path)], progress=False)
        names = {Path(c["path"]).name for c in corpus}
        assert names == {"dirty.png"}, "a clean file must never enter the AI corpus"
        assert corpus[0]["generators"] == ["Higgsfield"]

    def test_corpus_deduplicates_identical_images(self, tmp_path):
        blob = _png([(b"tEXt", b"hf-job-id\x00abc123")])
        for n in ("a.png", "b.png"):
            (tmp_path / n).write_bytes(blob)
        assert len(wc.build_lineage_corpus([str(tmp_path)], progress=False)[0]) == 1

    def test_corpus_entries_carry_a_fingerprint_pair(self, tmp_path):
        (tmp_path / "d.png").write_bytes(_png([(b"tEXt", b"hf-job-id\x00abc")]))
        c = wc.build_lineage_corpus([str(tmp_path)], progress=False)[0][0]
        assert isinstance(c["fp"], tuple) and len(c["fp"]) == 2

    def test_empty_corpus_on_a_clean_tree(self, tmp_path):
        (tmp_path / "clean.png").write_bytes(self._img(4))
        assert wc.build_lineage_corpus([str(tmp_path)], progress=False)[0] == []

    def test_a_source_that_contributed_nothing_is_reported(self, tmp_path):
        """`iter_local_images` yields nothing for a directory that does not
        exist rather than raising, so a wrong --source produced a silently
        smaller corpus — and every query against it answered a confident
        "not AI-descended"."""
        (tmp_path / "d.png").write_bytes(_png([(b"tEXt", b"hf-job-id\x00abc")]))
        missing = str(tmp_path / "nope")
        corpus, empty = wc.build_lineage_corpus([str(tmp_path), missing], progress=False)
        assert len(corpus) == 1
        assert empty == [missing], "a source contributing nothing must be named"

    def test_a_fully_productive_source_list_reports_none(self, tmp_path):
        """Guard the guard: naming every source would be the same as naming none."""
        (tmp_path / "d.png").write_bytes(_png([(b"tEXt", b"hf-job-id\x00abc")]))
        _corpus, empty = wc.build_lineage_corpus([str(tmp_path)], progress=False)
        assert empty == []

    def test_the_default_sources_cover_where_replace_and_cms_actually_write(self):
        """cmd_clean mirrors the tree under the backup dir; replace and cms write
        FLAT into the backup ROOT. Defaulting to the mirrored path alone excluded
        every backup the scrub itself made."""
        src = inspect.getsource(wc.cmd_lineage)
        assert '"data/watermark-backup"' in src, \
            "the flat backup root is where replace/cms write — it must be a default source"
        rep = inspect.getsource(wc.cmd_replace)
        cms = inspect.getsource(wc.cmd_cms)
        assert 'backup_dir / f"{asset_id}_{name}"' in rep
        assert 'backup_dir / f"{args.site}_{_url_key(url)}"' in cms


class TestVerdictIsNotAGuess:
    """`verify` answers "is this clean?". It is the last place that may guess.

    Regression, demonstrated on a real file: corrupting one chunk header on a
    C2PA-bearing PNG makes the structural walk abort with zero signals — and
    "zero signals" was printed as CLEAN, on bytes that still contained a signed
    manifest and 44 matching provenance strings.
    """

    def _dirty_but_unparseable(self) -> bytes:
        d = bytearray(_png([(b"caBX", C2PA_BLOB)]))
        d[8:12] = struct.pack(">I", 0x7FFFFF00)      # corrupt IHDR length only
        return bytes(d)

    def test_unparseable_with_intact_manifest_is_UNKNOWN_not_clean(self):
        data = self._dirty_but_unparseable()
        assert b"caBX" in data and b"trainedAlgorithmicMedia" in data, "fixture lost its manifest"
        rep = ip.scan(data)
        assert rep.parse_error and not rep.signals, "fixture no longer reproduces the defect"
        v, _rep, residue = wc.verdict(data)
        assert v == "UNKNOWN", f"an unreadable file must never be CLEAN (got {v})"
        assert residue, "the byte backstop must still see the manifest"

    def test_clean_file_is_CLEAN(self):
        assert wc.verdict(CLEAN_PNG)[0] == "CLEAN"

    def test_dirty_parseable_file_is_DIRTY(self):
        """DIRTY-AI when an AI signal is present; plain DIRTY when it is only
        ordinary metadata. Collapsing the two let a scanned photograph with
        204 bytes of camera EXIF read as if it were AI-generated."""
        assert wc.verdict(DIRTY_PNG)[0] == "DIRTY-AI"
        exif_only = _png([(b"tEXt", b"Software\x00Adobe Photoshop 26.0")])
        v, rep, _ = wc.verdict(exif_only)
        assert v == "DIRTY" and not rep.is_ai_flagged

    def test_residue_alone_makes_it_dirty(self):
        """Provenance hidden outside any declared record still counts — and an AI
        marker found only by the byte backstop must read as DIRTY-AI, not as
        ordinary camera metadata."""
        v, _r, res = wc.verdict(CLEAN_PNG + b"trailing: trainedAlgorithmicMedia")
        assert v == "DIRTY-AI" and res

    def test_pixel_bytes_spelling_c2pa_are_not_dirty(self):
        """Regression I introduced: verdict() ORed in the 4-byte needles, so a
        metadata-free image whose compressed pixels spell "c2pa" was DIRTY with
        nothing to strip -> verify_failed -> exit 2 -> reprocessed forever."""
        import zlib as _z
        def ch(t, pl):
            return struct.pack(">I", len(pl)) + t + pl + struct.pack(">I", _z.crc32(t + pl) & 0xFFFFFFFF)
        payload = b"c2pa" * 9
        raw = b"".join(b"\x00" + payload for _ in range(4))
        img = (ip._PNG_MAGIC
               + ch(b"IHDR", struct.pack(">IIBBBBB", len(payload) // 3, 4, 8, 2, 0, 0, 0))
               + ch(b"IDAT", _z.compress(raw, 0)) + ch(b"IEND", b""))
        assert b"c2pa" in img, "fixture must actually contain the needle"
        assert wc.verdict(img)[0] == "CLEAN"
        assert ip.raw_residue(img), "strict mode must STILL see it, for post-strip assertions"

    def test_exit_codes_distinguish_dirty_from_unknown(self, tmp_path, capsys):
        clean = tmp_path / "c.png"; clean.write_bytes(CLEAN_PNG)
        dirty = tmp_path / "d.png"; dirty.write_bytes(DIRTY_PNG)
        unk = tmp_path / "u.png"; unk.write_bytes(self._dirty_but_unparseable())
        assert wc.main(["verify", "--file", str(clean)]) == 0
        assert wc.main(["verify", "--file", str(dirty)]) == 1, "DIRTY-AI must exit 1"
        assert wc.main(["verify", "--file", str(unk)]) == 2, "UNKNOWN must not exit 0"

    def test_print_report_does_not_label_an_unparseable_file_clean(self, capsys):
        wc._print_report("x", ip.scan(self._dirty_but_unparseable()), verbose=False)
        out = capsys.readouterr().out
        assert "UNKNOWN" in out and "clean" not in out.split("UNKNOWN")[0]

    def test_verify_live_reports_unknown_rather_than_clean(self, monkeypatch):
        monkeypatch.setattr(wc, "download_image",
                            lambda u, timeout=30: self._dirty_but_unparseable())
        r = wc.verify_live("https://x/y.png", tries=1)
        assert r["verdict"] == "UNKNOWN" and r["clean"] is False, (
            "replace/cms print this as proof an upload landed clean")


class TestUnreadableIsNotNoise:
    """An alarm that fires every night is an alarm nobody reads.

    A Webflow site holds fonts and PDFs. Those sniff as `unknown` and report
    "unsupported container" — a statement about the file TYPE, not a failure.
    Counting them as unreadable made a healthy site exit non-zero on every
    nightly run. A parse error on a container we DID recognise is the real
    concern: that is the shape in which a manifest hides behind zero signals.
    """

    def test_a_font_is_not_a_concerning_error(self):
        rep = ip.scan(b"\x00\x01\x00\x00\x00\x0c\x00\x80\x00\x03\x00@")
        assert rep.parse_error, "fixture should not parse"
        assert rep.container == "unknown"
        assert not wc._is_concerning_parse_error(rep)

    def test_a_truncated_png_IS_concerning(self):
        rep = ip.scan(ip._PNG_MAGIC + b"\x00\x00\x00\x0dIHDR")
        assert rep.container == "png" and rep.parse_error
        assert wc._is_concerning_parse_error(rep)

    def test_a_clean_image_is_not_concerning(self):
        assert not wc._is_concerning_parse_error(ip.scan(CLEAN_PNG))

    def test_scan_exits_zero_on_a_site_that_merely_contains_fonts(self, tmp_path):
        (tmp_path / "f.ttf").write_bytes(b"\x00\x01\x00\x00\x00\x0c\x00\x80\x00\x03\x00@")
        (tmp_path / "ok.png").write_bytes(CLEAN_PNG)
        assert wc.main(["scan", "--local", str(tmp_path)]) == 0

    def test_scan_exits_two_when_a_real_image_could_not_be_read(self, tmp_path, capsys):
        (tmp_path / "f.ttf").write_bytes(b"\x00\x01\x00\x00\x00\x0c\x00\x80\x00\x03\x00@")
        (tmp_path / "broken.png").write_bytes(ip._PNG_MAGIC + b"\x00\x00\x00\x0dIHDR")
        assert wc.main(["scan", "--local", str(tmp_path)]) == 2
        assert "UNKNOWN, not clean" in capsys.readouterr().err


class TestPagination:
    """Regression: the stop condition defaulted `total` to len(out).

    With the `pagination` block absent, the first full page looked like the whole
    collection — measured, a 250-asset site returned 100 and reported it complete.
    Every downstream command then operated on a partial site, and `scan` would
    report "0 AI-flagged" on one full of them.
    """

    def _server(self, n: int, with_pagination: bool):
        def fake(method, url, token, data=None):
            off = int(url.split("offset=")[1])
            key = "assets" if "/assets" in url else "items"
            batch = [{"id": f"x{off + i}"} for i in range(max(0, min(wc.PAGE_SIZE, n - off)))]
            resp = {key: batch}
            if with_pagination:
                resp["pagination"] = {"total": n}
            return resp
        return fake

    @pytest.mark.parametrize("n", [0, 1, 99, 100, 101, 199, 200, 250, 1547])
    @pytest.mark.parametrize("with_pagination", [True, False])
    def test_returns_every_record(self, monkeypatch, n, with_pagination):
        monkeypatch.setattr(wc, "rate_limited_request", self._server(n, with_pagination))
        assert len(wc.list_assets("t", "s")) == n
        assert len(wc.list_items("t", "c")) == n

    def test_exact_page_multiple_is_not_truncated_or_doubled(self, monkeypatch):
        """n == PAGE_SIZE is where an off-by-one lives in both directions."""
        monkeypatch.setattr(wc, "rate_limited_request", self._server(wc.PAGE_SIZE, False))
        assert len(wc.list_assets("t", "s")) == wc.PAGE_SIZE

    def test_limit_is_honoured(self, monkeypatch):
        monkeypatch.setattr(wc, "rate_limited_request", self._server(500, True))
        assert len(wc.list_assets("t", "s", limit=30)) == 30

    def test_a_server_that_never_ends_raises_instead_of_looping(self, monkeypatch):
        monkeypatch.setattr(wc, "rate_limited_request",
                            lambda m, u, t, data=None: {"assets": [{"id": "x"}] * wc.PAGE_SIZE,
                                                        "items": [{"id": "x"}] * wc.PAGE_SIZE})
        with pytest.raises(RuntimeError, match="refusing to loop"):
            wc.list_assets("t", "s")

    def test_a_lying_total_does_not_truncate(self, monkeypatch):
        """`total` is an early exit, never the sole stop rule — a wrong total
        must not be able to hide records the server is still returning."""
        def fake(method, url, token, data=None):
            off = int(url.split("offset=")[1])
            batch = [{"id": f"x{off + i}"} for i in range(max(0, min(wc.PAGE_SIZE, 250 - off)))]
            return {"assets": batch, "pagination": {"total": 999999}}
        monkeypatch.setattr(wc, "rate_limited_request", fake)
        assert len(wc.list_assets("t", "s")) == 250


class TestHonestCounters:
    """A summary line that conflates two different facts is a lie by omission."""

    def test_only_ai_skips_are_not_counted_as_clean(self, monkeypatch, tmp_path, capsys):
        """Regression: `--only-ai` folded 'no AI signal' into 'already clean', so
        the run printed "already clean 164" on a set where 38 carried camera EXIF.
        """
        # One image with ordinary EXIF and no AI signal — the exact conflation case.
        exif_only = _png([(b"tEXt", b"Software\x00Adobe Photoshop 26.0")])
        ref = wc.Reference(kind="image", collection_id="col1", collection_slug="blog",
                           item_id="i1", item_slug="post", field_slug="main-image",
                           source_url=f"{CDN}/{AID_HERO}_p.png")
        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "build_reference_index",
                            lambda *a, **k: ({wc._url_key(ref.source_url): [ref]}, []))
        monkeypatch.setattr(wc, "download_image", lambda u, timeout=30: exif_only)

        # Through the real parser, never a hand-rolled Namespace: this test broke
        # the moment cmd_cms gained --site-url, because its literal Namespace had
        # silently drifted from the CLI it claims to exercise.
        wc.cmd_cms(_cms_args(only_ai=True, verify=False, check_live_pages=False,
                             backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        out = capsys.readouterr().out
        assert "no AI signal" in out, "the skip must be reported as its own category"
        assert "NOT a statement that they are metadata-clean" in out
        assert "carried no removable metadata 1" not in out, (
            "an EXIF-bearing image skipped by --only-ai must NOT be counted as clean")


class TestPurgeSafety:
    """Deletion is irreversible, so every guard here is a hard requirement."""

    def test_exact_id_search_ignores_a_shared_filename(self, monkeypatch):
        """The basename fallback false-positives here: a replacement asset shares
        its filename with the original it replaced. Only the literal id counts."""
        items = {"col1": [{"id": "i1", "fieldData": {
            "slug": "post", "main-image": {"url": f"{CDN}/{AID_NEW}_hero.png", "fileId": AID_NEW}}}]}
        _install_fake(monkeypatch, _FakeApi(collections=[{"id": "col1", "slug": "blog"}],
                                            fields={"col1": [{"slug": "main-image", "type": "Image"}]},
                                            items=items))
        hits = wc.asset_id_appears_in_cms("tok", SITE_ID, {AID_HERO, AID_NEW})
        assert hits[AID_HERO] == [], "the OLD id is gone — must not be reported as referenced"
        assert hits[AID_NEW] == ["blog/post"], "the NEW id is present — must be reported"

    def test_finds_the_id_inside_richtext(self, monkeypatch):
        items = {"col1": [{"id": "i1", "fieldData": {
            "slug": "post", "post-body": f'<img src="{CDN}/{AID_HERO}_x.png">'}}]}
        _install_fake(monkeypatch, _FakeApi(collections=[{"id": "col1", "slug": "blog"}],
                                            fields={"col1": [{"slug": "post-body", "type": "RichText"}]},
                                            items=items))
        assert wc.asset_id_appears_in_cms("tok", SITE_ID, {AID_HERO})[AID_HERO] == ["blog/post"]

    @pytest.fixture
    def fake_registry(self, tmp_path, monkeypatch):
        """Self-contained: the CEL checkout carries a CEL-only registry mirror,
        so a test reading the real one passes here and fails there."""
        (tmp_path / "sites").mkdir()
        (tmp_path / "sites" / "registry.json").write_text(json.dumps({
            "sites": {
                "twohost": {"staging_url": "https://stg.example",
                            "production_url": "https://prod.example"},
                "onehost": {"staging_url": "https://only.example",
                            "production_url": "https://only.example"},
            }
        }))
        monkeypatch.setattr(wc, "ROOT", tmp_path)
        return tmp_path

    def test_evidence_uses_every_domain_that_could_serve_the_site(self, fake_registry):
        """Regression: purge crawled ONE domain, chosen by a fallback chain.

        "Production or staging?" is the wrong question. brightvalley's Webflow
        build lives on the .webflow.io staging host while its production domain
        still runs WordPress; CEL is the other way round. Crawling staging to
        justify deleting an asset production serves proves nothing — and so does
        crawling a WordPress host to justify deleting a Webflow staging asset,
        because it finds nothing and "proves" absence trivially.
        """
        doms = wc.evidence_domains("twohost", {"staging_url": "https://stg.example"}, "")
        assert "https://stg.example" in doms, "the Webflow build's own host must be crawled"
        assert "https://prod.example" in doms, "a distinct production host must also be crawled"

    def test_a_single_host_is_not_duplicated(self, fake_registry):
        assert wc.evidence_domains("onehost", {"staging_url": "https://only.example"}, "") \
            == ["https://only.example"]

    def test_explicit_site_url_overrides_everything(self, fake_registry):
        assert wc.evidence_domains("twohost", {"staging_url": "https://s"},
                                   "https://only.this") == ["https://only.this"]

    def test_domains_are_deduplicated_and_trailing_slashes_normalised(self):
        doms = wc.evidence_domains("nosuch",
                                   {"live_url": "https://x.example/",
                                    "staging_url": "https://x.example",
                                    "url": "https://x.example/"}, "")
        assert doms == ["https://x.example"]

    def test_no_domain_on_record_is_not_silently_treated_as_proof(self, monkeypatch, tmp_path, capsys):
        """With no domain, purge must record a failure rather than an empty index."""
        import argparse
        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets", lambda t, s, limit=None: [_asset(AID_HERO, "h.png")])
        monkeypatch.setattr(wc, "download_image", lambda u, timeout=30: DIRTY_PNG)
        monkeypatch.setattr(wc, "evidence_domains", lambda *a, **k: [])
        monkeypatch.setattr(wc, "asset_id_appears_in_cms", lambda *a, **k: {AID_HERO: []})
        args = argparse.Namespace(site="bv", apply=False, asset_id="", limit=0,
                                  check_live_pages=True, site_url="", backup_dir=str(tmp_path),
                                  quiet=True, token=None, keep_c2pa=False, keep_exif=False,
                                  strip_icc=False, drop_orientation=False, log_jsonl="",
                                  verbose=False, all=False, json=False)
        wc.cmd_purge(args)
        out = capsys.readouterr().out
        assert "No domain on record" in out
        assert "HOLD" in out, "with no evidence available nothing may be deleted"

    def test_purge_apply_is_gated_by_the_env_confirmation(self, monkeypatch):
        monkeypatch.delenv("WATERMARK_CLEANER_CONFIRM", raising=False)
        called = []
        monkeypatch.setattr(wc, "cmd_purge", lambda a: (called.append(1), 0)[1])
        assert wc.main(["purge", "--site", "cel", "--apply"]) == 3
        assert not called, "cmd_purge must not run without the env confirmation"


# ── local file discovery ─────────────────────────────────────────────────────
class TestIterLocalImages:
    def test_finds_images_in_a_directory(self, tmp_path):
        (tmp_path / "a.png").write_bytes(CLEAN_PNG)
        (tmp_path / "b.jpg").write_bytes(b"\xff\xd8\xff")
        (tmp_path / "notes.txt").write_text("nope")
        found = {p.name for p in wc.iter_local_images([str(tmp_path)])}
        assert found == {"a.png", "b.jpg"}

    def test_recurses(self, tmp_path):
        sub = tmp_path / "deep" / "deeper"
        sub.mkdir(parents=True)
        (sub / "c.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBP")
        assert [p.name for p in wc.iter_local_images([str(tmp_path)])] == ["c.webp"]

    def test_deduplicates(self, tmp_path):
        f = tmp_path / "a.png"
        f.write_bytes(CLEAN_PNG)
        assert len(wc.iter_local_images([str(f), str(f), str(tmp_path)])) == 1

    def test_missing_path_yields_nothing(self, tmp_path):
        assert wc.iter_local_images([str(tmp_path / "nope")]) == []


# ── reference index ──────────────────────────────────────────────────────────
class _FakeApi:
    """Records every call so tests can assert exactly which writes happened."""

    def __init__(self, *, collections, fields, items, assets=None, upload_id=None):
        self.collections, self.fields, self.items = collections, fields, items
        self.assets = assets or []
        self.upload_id = upload_id
        self.calls: list[tuple[str, str]] = []
        self.patches: list[dict] = []

    def request(self, method, url, token, data=None):
        self.calls.append((method, url))
        if method == "PATCH":
            self.patches.append({"url": url, "data": data})
            return {"id": "patched"}
        if "/assets" in url:
            return {"assets": self.assets, "pagination": {"total": len(self.assets)}}
        if url.endswith("/collections"):
            return {"collections": self.collections}
        if "/collections/" in url and "/items" in url:
            cid = url.split("/collections/")[1].split("/")[0]
            if "/items/" in url:                    # single-item GET
                iid = url.split("/items/")[1].split("?")[0]
                for it in self.items.get(cid, []):
                    if it["id"] == iid:
                        return it
                return {}
            its = self.items.get(cid, [])
            return {"items": its, "pagination": {"total": len(its)}}
        if "/collections/" in url:
            cid = url.rsplit("/", 1)[-1]
            return {"fields": self.fields.get(cid, [])}
        return {}


def _install_fake(monkeypatch, api: _FakeApi):
    monkeypatch.setattr(wc, "rate_limited_request", api.request)
    return api


COLLECTIONS = [{"id": "col1", "slug": "blog"}, {"id": "col2", "slug": "team"}]
FIELDS = {
    "col1": [{"slug": "main-image", "type": "Image"},
             {"slug": "gallery", "type": "MultiImage"},
             {"slug": "post-body", "type": "RichText"},
             {"slug": "title", "type": "PlainText"}],
    "col2": [{"slug": "headshot", "type": "Image"}],
}
ITEMS = {
    "col1": [{
        "id": "i1", "isDraft": False, "isArchived": False, "lastPublished": "2026-01-01",
        "fieldData": {
            "slug": "post-one",
            "main-image": {"url": f"{CDN}/{AID_HERO}_hero.png", "fileId": AID_HERO, "alt": "Hero"},
            "gallery": [{"url": f"{CDN}/{AID_G1}_g1.png", "fileId": AID_G1},
                        {"url": f"{CDN}/{AID_G2}_g2.png", "fileId": AID_G2}],
            "post-body": f'<p>x</p><img src="{CDN}/{AID_BODY}_body.png" alt="b">',
        },
    }],
    "col2": [{
        "id": "i2", "isDraft": True, "isArchived": False, "lastPublished": None,
        "fieldData": {"slug": "jane", "headshot": {"url": f"{CDN}/{AID_HERO}_hero.png", "fileId": AID_HERO}},
    }],
}


class TestReferenceIndex:
    def test_indexes_every_field_kind(self, monkeypatch):
        _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        index, summaries = wc.build_reference_index("tok", SITE_ID, progress=False)
        assert wc._url_key(f"{CDN}/{AID_HERO}_hero.png") in index
        assert wc._url_key(f"{CDN}/{AID_G1}_g1.png") in index
        assert wc._url_key(f"{CDN}/{AID_BODY}_body.png") in index
        kinds = {r.kind for refs in index.values() for r in refs}
        assert kinds == {"image", "multi", "richtext"}

    def test_same_asset_in_two_collections_yields_two_references(self, monkeypatch):
        _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        index, _ = wc.build_reference_index("tok", SITE_ID, progress=False)
        refs = index[wc._url_key(f"{CDN}/{AID_HERO}_hero.png")]
        assert {r.collection_slug for r in refs} == {"blog", "team"}

    def test_records_draft_and_published_state(self, monkeypatch):
        _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        index, _ = wc.build_reference_index("tok", SITE_ID, progress=False)
        by_col = {r.collection_slug: r for r in index[wc._url_key(f"{CDN}/{AID_HERO}_hero.png")]}
        assert by_col["blog"].was_published and not by_col["blog"].is_draft
        assert by_col["team"].is_draft and not by_col["team"].was_published

    def test_multiimage_index_position_is_recorded(self, monkeypatch):
        _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        index, _ = wc.build_reference_index("tok", SITE_ID, progress=False)
        assert index[wc._url_key(f"{CDN}/{AID_G2}_g2.png")][0].index == 1

    def test_collection_filter(self, monkeypatch):
        _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        index, _ = wc.build_reference_index("tok", SITE_ID, collections_filter="team", progress=False)
        assert {r.collection_slug for refs in index.values() for r in refs} == {"team"}

    def test_collection_without_image_fields_is_skipped(self, monkeypatch):
        cols = [{"id": "c9", "slug": "settings"}]
        _install_fake(monkeypatch, _FakeApi(collections=cols,
                                            fields={"c9": [{"slug": "k", "type": "PlainText"}]},
                                            items={"c9": []}))
        index, summaries = wc.build_reference_index("tok", SITE_ID, progress=False)
        assert index == {}
        assert summaries[0]["skipped"] == "no image fields"


# ── re-pointing ──────────────────────────────────────────────────────────────
class TestRepoint:
    def _ref(self, kind, field, index=-1, cid="col1", iid="i1"):
        return wc.Reference(kind=kind, collection_id=cid, collection_slug="blog",
                            item_id=iid, item_slug="post-one", field_slug=field, index=index)

    def test_dry_run_makes_no_call(self, monkeypatch):
        api = _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        out = wc.repoint_reference("tok", self._ref("image", "main-image"),
                                   old_url=f"{CDN}/{AID_HERO}_hero.png", new_url=f"{CDN}/zzz_hero.png",
                                   new_file_id="zzz", apply=False)
        assert out["status"] == "would-repoint"
        assert api.calls == []

    def test_image_field_url_and_fileid_updated(self, monkeypatch):
        api = _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        out = wc.repoint_reference("tok", self._ref("image", "main-image"),
                                   old_url=f"{CDN}/{AID_HERO}_hero.png", new_url=f"{CDN}/zzz_hero.png",
                                   new_file_id="zzz", apply=True)
        assert out["status"] == "repointed"
        patched = api.patches[0]["data"]["fieldData"]["main-image"]
        assert patched["url"] == f"{CDN}/zzz_hero.png"
        assert patched["fileId"] == "zzz"
        assert patched["alt"] == "Hero", "alt text must survive a re-point"

    def test_multiimage_updates_only_the_matching_entry(self, monkeypatch):
        api = _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        wc.repoint_reference("tok", self._ref("multi", "gallery", index=0),
                             old_url=f"{CDN}/{AID_G1}_g1.png", new_url=f"{CDN}/yyy_g1.png",
                             new_file_id="yyy", apply=True)
        arr = api.patches[0]["data"]["fieldData"]["gallery"]
        assert arr[0]["url"] == f"{CDN}/yyy_g1.png"
        assert arr[1]["url"] == f"{CDN}/{AID_G2}_g2.png", "sibling entries must not move"

    def test_richtext_src_is_rewritten_in_place(self, monkeypatch):
        api = _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        wc.repoint_reference("tok", self._ref("richtext", "post-body"),
                             old_url=f"{CDN}/{AID_BODY}_body.png", new_url=f"{CDN}/xxx_body.png",
                             new_file_id="xxx", apply=True)
        html = api.patches[0]["data"]["fieldData"]["post-body"]
        assert f'src="{CDN}/xxx_body.png"' in html
        assert 'alt="b"' in html, "surrounding markup must be preserved"

    def test_repoints_when_the_cms_id_differs_from_the_asset_id(self, monkeypatch):
        """Regression: this silently no-opped on brightvalley and still read as success.

        The CMS field's URL carries a DIFFERENT id than the site asset (a
        WordPress-import artefact). Comparing on the exact key made every
        re-point return "ref-stale": the new clean asset was uploaded, the CMS
        kept pointing at the un-stripped one, and the run printed a success line
        with "repointed 0/1" buried in it.
        """
        api = _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        # Same picture, different id stamped on it than the CMS field holds.
        old_url_other_id = f"{CDN}/{AID_G2}_hero.png"
        out = wc.repoint_reference("tok", self._ref("image", "main-image"),
                                   old_url=old_url_other_id,
                                   new_url=f"{CDN}/{AID_NEW}_hero.png",
                                   new_file_id=AID_NEW, apply=True)
        assert out["status"] == "repointed", "basename match must rescue a differing id"
        patched = api.patches[0]["data"]["fieldData"]["main-image"]
        assert patched["url"] == f"{CDN}/{AID_NEW}_hero.png"
        assert patched["fileId"] == AID_NEW

    def test_richtext_repoints_across_a_differing_id(self, monkeypatch):
        api = _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        wc.repoint_reference("tok", self._ref("richtext", "post-body"),
                             old_url=f"{CDN}/{AID_G2}_body.png",
                             new_url=f"{CDN}/{AID_NEW}_body.png",
                             new_file_id=AID_NEW, apply=True)
        assert f'src="{CDN}/{AID_NEW}_body.png"' in api.patches[0]["data"]["fieldData"]["post-body"]

    def test_a_genuinely_different_filename_still_does_not_match(self, monkeypatch):
        api = _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        out = wc.repoint_reference("tok", self._ref("image", "main-image"),
                                   old_url=f"{CDN}/{AID_G2}_totally-other.png",
                                   new_url=f"{CDN}/{AID_NEW}_x.png",
                                   new_file_id=AID_NEW, apply=True)
        assert out["status"] == "ref-stale"
        assert api.patches == []

    def test_multiimage_rewrites_only_the_indexed_entry(self, monkeypatch):
        """Regression: re-pointing gallery[0] also rewrote gallery[1].

        Two entries can share a filename under different asset ids — a very
        common shape (`hero.png` uploaded twice). `_same()` falls back to
        basename, and the old loop rewrote EVERY match, so a sibling holding a
        genuinely different picture was silently swapped. `Reference.index` was
        already recorded; it was simply ignored.
        """
        items = {"col1": [{"id": "i1", "isDraft": False, "isArchived": False, "fieldData": {
            "slug": "post", "gallery": [
                {"url": f"{CDN}/{AID_HERO}_hero.png", "fileId": AID_HERO},
                {"url": f"{CDN}/{AID_G1}_hero.png", "fileId": AID_G1},     # same NAME, different image
                {"url": f"{CDN}/{AID_G2}_other.png", "fileId": AID_G2}]}}]}
        api = _install_fake(monkeypatch, _FakeApi(
            collections=[{"id": "col1", "slug": "blog"}],
            fields={"col1": [{"slug": "gallery", "type": "MultiImage"}]}, items=items))
        ref = wc.Reference(kind="multi", collection_id="col1", collection_slug="blog",
                           item_id="i1", item_slug="post", field_slug="gallery", index=0,
                           source_url=f"{CDN}/{AID_HERO}_hero.png")
        out = wc.repoint_reference("tok", ref, old_url=f"{CDN}/{AID_HERO}_hero.png",
                                   new_url=f"{CDN}/{AID_NEW}_hero.png",
                                   new_file_id=AID_NEW, apply=True)
        assert out["status"] == "repointed"
        arr = api.patches[0]["data"]["fieldData"]["gallery"]
        assert arr[0]["fileId"] == AID_NEW
        assert arr[1]["fileId"] == AID_G1, "the sibling is a DIFFERENT image and must not move"
        assert arr[2]["fileId"] == AID_G2

    def test_multiimage_without_an_index_refuses_when_ambiguous(self, monkeypatch):
        items = {"col1": [{"id": "i1", "isDraft": False, "isArchived": False, "fieldData": {
            "slug": "post", "gallery": [
                {"url": f"{CDN}/{AID_HERO}_hero.png", "fileId": AID_HERO},
                {"url": f"{CDN}/{AID_G1}_hero.png", "fileId": AID_G1}]}}]}
        api = _install_fake(monkeypatch, _FakeApi(
            collections=[{"id": "col1", "slug": "blog"}],
            fields={"col1": [{"slug": "gallery", "type": "MultiImage"}]}, items=items))
        ref = wc.Reference(kind="multi", collection_id="col1", collection_slug="blog",
                           item_id="i1", item_slug="post", field_slug="gallery", index=-1)
        out = wc.repoint_reference("tok", ref, old_url=f"{CDN}/{AID_LOGO}_hero.png",
                                   new_url=f"{CDN}/{AID_NEW}_hero.png",
                                   new_file_id=AID_NEW, apply=True)
        assert out["status"] == "ref-ambiguous"
        assert api.patches == [], "an ambiguous reference must not be written"

    def test_richtext_refuses_two_body_images_sharing_a_filename(self, monkeypatch):
        items = {"col1": [{"id": "i1", "isDraft": False, "isArchived": False, "fieldData": {
            "slug": "post",
            "post-body": f'<img src="{CDN}/{AID_HERO}_hero.png"><img src="{CDN}/{AID_G1}_hero.png">'}}]}
        api = _install_fake(monkeypatch, _FakeApi(
            collections=[{"id": "col1", "slug": "blog"}],
            fields={"col1": [{"slug": "post-body", "type": "RichText"}]}, items=items))
        ref = wc.Reference(kind="richtext", collection_id="col1", collection_slug="blog",
                           item_id="i1", item_slug="post", field_slug="post-body")
        out = wc.repoint_reference("tok", ref, old_url=f"{CDN}/{AID_LOGO}_hero.png",
                                   new_url=f"{CDN}/{AID_NEW}_hero.png",
                                   new_file_id=AID_NEW, apply=True)
        assert out["status"] == "ref-ambiguous"
        assert api.patches == []

    def test_richtext_single_basename_match_still_works(self, monkeypatch):
        items = {"col1": [{"id": "i1", "isDraft": False, "isArchived": False, "fieldData": {
            "slug": "post",
            "post-body": f'<img src="{CDN}/{AID_HERO}_hero.png"><img src="{CDN}/{AID_G2}_other.png">'}}]}
        api = _install_fake(monkeypatch, _FakeApi(
            collections=[{"id": "col1", "slug": "blog"}],
            fields={"col1": [{"slug": "post-body", "type": "RichText"}]}, items=items))
        ref = wc.Reference(kind="richtext", collection_id="col1", collection_slug="blog",
                           item_id="i1", item_slug="post", field_slug="post-body")
        out = wc.repoint_reference("tok", ref, old_url=f"{CDN}/{AID_LOGO}_hero.png",
                                   new_url=f"{CDN}/{AID_NEW}_hero.png",
                                   new_file_id=AID_NEW, apply=True)
        assert out["status"] == "repointed", "an unambiguous basename match must still rescue the join"
        html = api.patches[0]["data"]["fieldData"]["post-body"]
        assert f"{AID_NEW}_hero.png" in html and f"{AID_G2}_other.png" in html

    def test_stale_reference_is_reported_not_patched(self, monkeypatch):
        api = _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        out = wc.repoint_reference("tok", self._ref("image", "main-image"),
                                   old_url=f"{CDN}/gone_other.png", new_url=f"{CDN}/zzz.png",
                                   new_file_id="zzz", apply=True)
        assert out["status"] == "ref-stale"
        assert api.patches == []

    def test_draft_state_is_preserved_on_patch(self, monkeypatch):
        api = _install_fake(monkeypatch, _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS))
        ref = self._ref("image", "headshot", cid="col2", iid="i2")
        ref.is_draft = True
        wc.repoint_reference("tok", ref, old_url=f"{CDN}/{AID_HERO}_hero.png",
                             new_url=f"{CDN}/zzz.png", new_file_id="zzz", apply=True)
        assert api.patches[0]["data"]["isDraft"] is True, "a draft must not be published by a re-point"


# ── live-page index ──────────────────────────────────────────────────────────
class TestLivePageIndex:
    def _serve(self, monkeypatch, pages: dict[str, str]):
        import io as _io

        class _Resp(_io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url not in pages:
                raise wc.urllib.error.HTTPError(url, 404, "nf", {}, None)
            return _Resp(pages[url].encode())

        monkeypatch.setattr(wc.urllib.request, "urlopen", fake_urlopen)

    def test_finds_designer_placed_image(self, monkeypatch):
        base = "https://example.com"
        self._serve(monkeypatch, {
            f"{base}/sitemap.xml": f"<urlset><url><loc>{base}/about</loc></url></urlset>",
            f"{base}/about": f'<img src="{CDN}/{AID_HERO}_hero.png">',
        })
        index, fetched, failed = wc.build_live_page_index(base, progress=False)
        assert fetched == [f"{base}/about"] and failed == []
        assert index[wc._url_key(f"{CDN}/{AID_HERO}_hero.png")] == [f"{base}/about"]

    def test_follows_a_sitemap_index(self, monkeypatch):
        base = "https://example.com"
        self._serve(monkeypatch, {
            f"{base}/sitemap.xml": f"<s><loc>{base}/s1.xml</loc></s>",
            f"{base}/s1.xml": f"<urlset><url><loc>{base}/p</loc></url></urlset>",
            f"{base}/p": f'<img src="{CDN}/bbb_x.png">',
        })
        index, fetched, failed = wc.build_live_page_index(base, progress=False)
        assert fetched == [f"{base}/p"] and failed == []
        assert wc._url_key(f"{CDN}/bbb_x.png") in index

    def test_unreachable_sitemap_returns_empty_and_says_so(self, monkeypatch):
        self._serve(monkeypatch, {})
        index, fetched, failed = wc.build_live_page_index("https://example.com", progress=False)
        assert index == {} and fetched == [] and failed

    def test_non_cdn_images_are_ignored(self, monkeypatch):
        base = "https://example.com"
        self._serve(monkeypatch, {
            f"{base}/sitemap.xml": f"<urlset><url><loc>{base}/p</loc></url></urlset>",
            f"{base}/p": '<img src="https://images.unsplash.com/photo-1.jpg">',
        })
        index, _f, _x = wc.build_live_page_index(base, progress=False)
        assert index == {}


# ── the clean command, end to end ────────────────────────────────────────────
class TestCleanCommand:
    def test_dry_run_does_not_modify_files(self, tmp_path, capsys):
        f = tmp_path / "dirty.png"
        f.write_bytes(DIRTY_PNG)
        assert wc.main(["clean", "--local", str(tmp_path)]) == 0
        assert f.read_bytes() == DIRTY_PNG, "a dry run must not touch the file"
        assert "WOULD" in capsys.readouterr().out

    def test_apply_strips_and_backs_up(self, tmp_path, capsys):
        f = tmp_path / "dirty.png"
        f.write_bytes(DIRTY_PNG)
        backup = tmp_path / "bk"
        rc = wc.main(["clean", "--local", str(tmp_path), "--apply", "--backup-dir", str(backup)])
        assert rc == 0
        assert b"caBX" not in f.read_bytes()
        assert not ip.scan(f.read_bytes()).is_ai_flagged
        backups = list(backup.rglob("dirty.png"))
        assert backups and backups[0].read_bytes() == DIRTY_PNG

    def test_out_dir_leaves_the_original_alone(self, tmp_path):
        f = tmp_path / "dirty.png"
        f.write_bytes(DIRTY_PNG)
        out = tmp_path / "out"
        wc.main(["clean", "--local", str(f), "--apply", "--out", str(out),
                 "--backup-dir", str(tmp_path / "bk")])
        assert f.read_bytes() == DIRTY_PNG
        assert b"caBX" not in (out / "dirty.png").read_bytes()

    def test_already_clean_file_is_untouched(self, tmp_path):
        f = tmp_path / "clean.png"
        f.write_bytes(CLEAN_PNG)
        wc.main(["clean", "--local", str(f), "--apply", "--backup-dir", str(tmp_path / "bk")])
        assert f.read_bytes() == CLEAN_PNG

    def test_keep_c2pa_policy_is_honoured(self, tmp_path):
        f = tmp_path / "dirty.png"
        f.write_bytes(DIRTY_PNG)
        wc.main(["clean", "--local", str(f), "--apply", "--keep-c2pa",
                 "--backup-dir", str(tmp_path / "bk")])
        assert b"caBX" in f.read_bytes(), "--keep-c2pa must leave the manifest alone"
        assert b"hf-job-id" not in f.read_bytes(), "…but still drop the generator tag"

    def test_log_jsonl_is_written(self, tmp_path):
        f = tmp_path / "dirty.png"
        f.write_bytes(DIRTY_PNG)
        log = tmp_path / "log.jsonl"
        wc.main(["clean", "--local", str(f), "--log-jsonl", str(log)])
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert rows and rows[0]["mode"] == "clean" and rows[0]["applied"] is False

    def test_unreadable_container_is_UNKNOWN_not_clean(self, tmp_path, capsys):
        """This test previously asserted rc==0 and a "SKIP" label.

        That encoded the defect: `cmd_clean` folded unparseable files into
        n_skipped and printed them in `already clean N`. "Could not read it" is
        not "already clean", and a run that could not read part of its input
        must not exit 0.
        """
        (tmp_path / "broken.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\xff" * 40)
        rc = wc.main(["clean", "--local", str(tmp_path)])
        out = capsys.readouterr().out
        assert "UNKNOWN" in out
        assert "UNREADABLE" in out and "NOT clean" in out
        assert rc == 2, "an unreadable input must not exit 0"

    def test_a_genuinely_clean_directory_still_exits_zero(self, tmp_path):
        (tmp_path / "ok.png").write_bytes(CLEAN_PNG)
        assert wc.main(["clean", "--local", str(tmp_path)]) == 0

    def test_publish_failure_is_counted_as_an_error(self, monkeypatch, tmp_path, capsys):
        """A publish failure left items re-pointed but NOT live, and exited 0.

        The live page keeps serving the un-stripped image in that state, so it
        is exactly as consequential as a failed re-point.
        """
        h = _ReplaceHarness(monkeypatch, upload_id=AID_HERO,
                            assets=[_asset(AID_HERO, "hero.png")], live_index={})
        def boom(token, cid, ids):
            raise wc.APIError(500, '{"message":"simulated"}', "https://api.webflow.com/v2/x")
        monkeypatch.setattr(wc, "publish_items", boom)
        rc = wc.cmd_replace(_replace_args(apply=True, auto_publish=True,
                                          backup_dir=str(tmp_path),
                                          log_jsonl=str(tmp_path / "l.jsonl")))
        out = capsys.readouterr().out
        assert "PUBLISH FAILED" in out
        assert "still serves the un-stripped image" in out
        assert rc == 2, "a publish failure must move the exit code"


# ── CI surfaces ──────────────────────────────────────────────────────────────
class TestKnownCleanCache:
    def test_reads_ids_proven_clean(self, tmp_path):
        log = tmp_path / "log.jsonl"
        log.write_text("\n".join([
            json.dumps({"asset_id": "a1", "mode": "replace", "action": "already_clean"}),
            json.dumps({"asset_id": "a3", "mode": "scan-asset", "signals": []}),
        ]) + "\n")
        assert wc.load_known_clean(log) == {"a1", "a3"}

    def test_a_replaced_row_proves_the_NEW_asset_clean_not_the_old(self, tmp_path):
        """Regression — and this test previously asserted the bug.

        `replace` never touches the original; it uploads a stripped COPY. Marking
        the ORIGINAL's id known-clean made every later scan skip the still-dirty
        source forever. The CEL cron passes --skip-known-clean over exactly this
        file, so the poisoning was permanent and committed to the repo.
        """
        log = tmp_path / "log.jsonl"
        log.write_text(json.dumps({
            "asset_id": "OLD_dirty", "new_asset_id": "NEW_clean",
            "mode": "replace", "action": "replaced", "verify": {"clean": True},
        }) + "\n")
        known = wc.load_known_clean(log)
        assert "OLD_dirty" not in known, "the original is still dirty — it was never touched"
        assert "NEW_clean" in known

    def test_a_failed_verify_proves_nothing(self, tmp_path):
        log = tmp_path / "log.jsonl"
        log.write_text(json.dumps({
            "asset_id": "OLD", "new_asset_id": "NEW", "mode": "replace",
            "action": "replaced", "verify": {"clean": False},
        }) + "\n")
        assert wc.load_known_clean(log) == set()

    @pytest.mark.parametrize("action", ["incomplete_repoint", "verify_failed",
                                        "refused_id_change", "upload_error", "error"])
    def test_unsuccessful_actions_never_mark_anything_clean(self, tmp_path, action):
        log = tmp_path / "log.jsonl"
        log.write_text(json.dumps({"asset_id": "x", "new_asset_id": "y",
                                   "mode": "replace", "action": action}) + "\n")
        assert wc.load_known_clean(log) == set(), f"{action} must prove nothing"

    def test_does_not_mark_dirty_assets_clean(self, tmp_path):
        log = tmp_path / "log.jsonl"
        log.write_text("\n".join([
            json.dumps({"asset_id": "d1", "mode": "scan-asset",
                        "signals": [{"kind": "c2pa", "where": "PNG:caBX",
                                     "offset": 0, "length": 10, "removable": True, "detail": ""}]}),
            json.dumps({"asset_id": "d2", "mode": "replace", "action": "refused_id_change"}),
            json.dumps({"asset_id": "d3", "mode": "replace", "action": "error"}),
        ]) + "\n")
        assert wc.load_known_clean(log) == set()

    def test_corrupt_lines_cost_time_not_correctness(self, tmp_path):
        log = tmp_path / "log.jsonl"
        log.write_text('{"asset_id": "ok", "mode": "scan-asset", "signals": []}\n'
                       "not json at all\n"
                       '{"truncated": \n')
        assert wc.load_known_clean(log) == {"ok"}

    def test_missing_file_is_empty_not_an_error(self, tmp_path):
        assert wc.load_known_clean(tmp_path / "nope.jsonl") == set()


class TestMarkdownSummary:
    def test_renders_a_clean_result(self):
        md = wc.render_markdown_summary({
            "ts": "2026-08-22T00:00:00Z", "scanned": 10, "with_metadata": 3,
            "ai_flagged": 0, "removable_bytes": 1234, "pixel_watermark_declared": 0,
            "flagged_names": [],
        })
        assert "## AI-provenance scan" in md
        assert "No image carries a C2PA manifest" in md
        assert "|---|" in md, "must be a valid markdown table"

    def test_lists_flagged_images_and_the_next_step(self):
        md = wc.render_markdown_summary({
            "ts": "t", "scanned": 2, "with_metadata": 2, "ai_flagged": 2,
            "removable_bytes": 40, "pixel_watermark_declared": 0,
            "flagged_names": ["a.png", "b.png"],
        })
        assert "`a.png`" in md and "`b.png`" in md
        assert "scrub_confirm = REPLACE" in md

    def test_always_states_the_unremovable_watermark(self):
        md = wc.render_markdown_summary({
            "ts": "t", "scanned": 1, "with_metadata": 1, "ai_flagged": 1,
            "removable_bytes": 10, "pixel_watermark_declared": 1, "flagged_names": ["x.png"],
        })
        assert "removed by this tool" in md          # rendered as "**not** removed by this tool"
        assert "cannot be removed by any lossless operation" in md
        assert "watermark-free" in md, "must warn against the claim explicitly"

    def test_empty_summary_reports_unknown_not_clean(self):
        """A missing scan must never render as a green result."""
        md = wc.render_markdown_summary({})
        assert "UNKNOWN" in md
        assert "not the same as clean" in md

    def test_scan_writes_both_summary_files(self, tmp_path):
        f = tmp_path / "dirty.png"
        f.write_bytes(DIRTY_PNG)
        js, md = tmp_path / "s.json", tmp_path / "s.md"
        wc.main(["scan", "--local", str(f), "--summary-out", str(js), "--markdown-out", str(md)])
        assert json.loads(js.read_text())["ai_flagged"] == 1
        assert "AI-provenance scan" in md.read_text()

    def test_fail_on_flagged_exit_code(self, tmp_path):
        dirty, clean = tmp_path / "d.png", tmp_path / "c.png"
        dirty.write_bytes(DIRTY_PNG)
        clean.write_bytes(CLEAN_PNG)
        assert wc.main(["scan", "--local", str(dirty), "--fail-on-flagged"]) == 1
        assert wc.main(["scan", "--local", str(clean), "--fail-on-flagged"]) == 0


# ── safety gates ─────────────────────────────────────────────────────────────
class TestSafetyGates:
    def test_replace_apply_refused_without_env_confirmation(self, monkeypatch, capsys):
        monkeypatch.delenv("WATERMARK_CLEANER_CONFIRM", raising=False)
        called = []
        monkeypatch.setattr(wc, "cmd_replace", lambda a: (called.append(1), 0)[1])
        rc = wc.main(["replace", "--site", "cel", "--apply"])
        assert rc == 3
        assert not called, "cmd_replace must not run without the env confirmation"

    def test_replace_dry_run_needs_no_confirmation(self, monkeypatch):
        monkeypatch.delenv("WATERMARK_CLEANER_CONFIRM", raising=False)
        seen = {}
        monkeypatch.setattr(wc, "cmd_replace", lambda a: (seen.__setitem__("apply", a.apply), 0)[1])
        assert wc.main(["replace", "--site", "cel"]) == 0
        assert seen["apply"] is False

    def test_scan_requires_a_target(self, capsys):
        assert wc.main(["scan"]) == 2

    def test_apply_proceeds_once_confirmed(self, monkeypatch):
        monkeypatch.setenv("WATERMARK_CLEANER_CONFIRM", "1")
        seen = {}
        monkeypatch.setattr(wc, "cmd_replace", lambda a: (seen.__setitem__("apply", a.apply), 0)[1])
        assert wc.main(["replace", "--site", "cel", "--apply"]) == 0
        assert seen["apply"] is True


# ── the replace command ──────────────────────────────────────────────────────
class _ReplaceHarness:
    """Wires cmd_replace against fakes and records every write attempt."""

    def __init__(self, monkeypatch, *, upload_id, assets, bytes_by_url=None,
                 live_index=None, repoint_status=None):
        # `repoint_status` forces the outcome of every repoint. Without it the
        # fake always answered "repointed", so no test could construct a run
        # that ends in incomplete_repoint — a whole branch of cmd_replace was
        # unreachable from the suite, and a test asserting on that branch passed
        # vacuously.
        self.repoint_status = repoint_status
        self.uploads: list[tuple[str, int]] = []
        self.repoints: list[dict] = []
        self.published: list[tuple[str, list[str]]] = []
        self.upload_id = upload_id
        api = _FakeApi(collections=COLLECTIONS, fields=FIELDS, items=ITEMS, assets=assets)
        _install_fake(monkeypatch, api)
        self.api = api
        blobs = bytes_by_url or {}

        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "get_api_token", lambda t=None: "tok")
        monkeypatch.setattr(wc, "download_image", lambda u, timeout=30: blobs.get(u, DIRTY_PNG))
        monkeypatch.setattr(wc, "build_live_page_index",
                            lambda url, **kw: (live_index or {}, ["p"] if live_index is not None else [], []))

        def fake_upload(data, name, site_id, token):
            self.uploads.append((name, len(data)))
            return {"asset_id": upload_id, "hostedUrl": f"{CDN}/{upload_id}_{name}",
                    "md5": "x", "size": len(data)}

        monkeypatch.setattr(wc, "upload_bytes", fake_upload)

        def fake_repoint(token, ref, *, old_url, new_url, new_file_id, apply):
            self.repoints.append({"ref": ref, "new_url": new_url, "apply": apply})
            if self.repoint_status:
                return {"status": self.repoint_status, "candidates": ["a", "b"]}
            return {"status": "repointed" if apply else "would-repoint"}

        monkeypatch.setattr(wc, "repoint_reference", fake_repoint)
        monkeypatch.setattr(wc, "publish_items",
                            lambda t, cid, ids: self.published.append((cid, ids)) or {})
        monkeypatch.setattr(wc, "verify_live", lambda url, **kw: {"url": url, "clean": True})


def _replace_args(**over):
    """Build cmd_replace's args THROUGH the real parser, then override.

    A hand-rolled argparse.Namespace silently drifts from the CLI: adding
    --skip-known-clean to the parser left every replace test raising
    AttributeError, and only the vendored CEL run surfaced it. Parsing real
    argv means a new flag arrives here with its real default automatically.
    """
    args = wc.build_parser().parse_args(
        ["replace", "--site", "cel", "--quiet", "--site-url", "https://example.com"])
    for k, v in over.items():
        assert hasattr(args, k), f"unknown arg {k!r} — did the CLI flag get renamed?"
        setattr(args, k, v)
    return args


class TestReplaceCommand:
    def test_dry_run_performs_no_upload_and_no_repoint(self, monkeypatch, tmp_path, capsys):
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                            assets=[_asset(AID_HERO, "hero.png")], live_index={})
        rc = wc.cmd_replace(_replace_args(backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert rc == 0
        assert h.uploads == [] and h.repoints == []
        assert "WOULD" in capsys.readouterr().out

    def test_same_asset_id_replaces_without_needing_repoints(self, monkeypatch, tmp_path, capsys):
        h = _ReplaceHarness(monkeypatch, upload_id=AID_HERO,       # id preserved
                            assets=[_asset(AID_HERO, "hero.png")], live_index={})
        rc = wc.cmd_replace(_replace_args(apply=True, backup_dir=str(tmp_path),
                                          log_jsonl=str(tmp_path / "l.jsonl")))
        assert rc == 0
        assert h.uploads and h.uploads[0][0] == "hero.png", "the filename must be preserved exactly"
        assert "REFUSED" not in capsys.readouterr().out

    def test_new_asset_id_with_live_page_reference_is_refused(self, monkeypatch, tmp_path, capsys):
        live = {wc._url_key(f"{CDN}/{AID_HERO}_hero.png"): ["https://example.com/about"]}
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                            assets=[_asset(AID_HERO, "hero.png")], live_index=live)
        wc.cmd_replace(_replace_args(apply=True, backup_dir=str(tmp_path),
                                     log_jsonl=str(tmp_path / "l.jsonl")))
        out = capsys.readouterr().out
        assert "REFUSED" in out and "published page" in out
        assert h.repoints == [], "a refused asset must not have its references rewritten"

    def test_refusal_is_overridable_with_the_explicit_flag(self, monkeypatch, tmp_path, capsys):
        live = {wc._url_key(f"{CDN}/{AID_HERO}_hero.png"): ["https://example.com/about"]}
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                            assets=[_asset(AID_HERO, "hero.png")], live_index=live)
        wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                     backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        out = capsys.readouterr().out
        assert "REFUSED" not in out
        assert h.repoints, "with the override, CMS references should still be rewritten"

    def test_already_clean_asset_is_skipped(self, monkeypatch, tmp_path):
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW, assets=[_asset(AID_HERO, "hero.png")],
                            bytes_by_url={f"{CDN}/{AID_HERO}_hero.png": CLEAN_PNG}, live_index={})
        wc.cmd_replace(_replace_args(apply=True, backup_dir=str(tmp_path),
                                     log_jsonl=str(tmp_path / "l.jsonl")))
        assert h.uploads == [], "a clean asset must not be re-uploaded"

    def test_backup_written_before_upload(self, monkeypatch, tmp_path):
        _ReplaceHarness(monkeypatch, upload_id=AID_HERO, assets=[_asset(AID_HERO, "hero.png")], live_index={})
        wc.cmd_replace(_replace_args(apply=True, backup_dir=str(tmp_path / "bk"),
                                     log_jsonl=str(tmp_path / "l.jsonl")))
        assert (tmp_path / "bk" / f"{AID_HERO}_hero.png").read_bytes() == DIRTY_PNG

    def test_pattern_filter(self, monkeypatch, tmp_path):
        h = _ReplaceHarness(monkeypatch, upload_id=AID_HERO,
                            assets=[_asset(AID_HERO, "hero.png"), _asset(AID_LOGO, "logo.svg")],
                            live_index={})
        wc.cmd_replace(_replace_args(apply=True, pattern="*.png", backup_dir=str(tmp_path),
                                     log_jsonl=str(tmp_path / "l.jsonl")))
        assert [n for n, _ in h.uploads] == ["hero.png"]

    def test_log_records_the_undetectable_watermark(self, monkeypatch, tmp_path):
        _ReplaceHarness(monkeypatch, upload_id=AID_HERO, assets=[_asset(AID_HERO, "hero.png")], live_index={})
        log = tmp_path / "l.jsonl"
        wc.cmd_replace(_replace_args(backup_dir=str(tmp_path), log_jsonl=str(log)))
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert any(r.get("undetectable_watermarks") for r in rows), \
            "the log must record what could NOT be removed, not just what could"


class TestPolicyAwareVerdict:
    """VPE-5 — a policy-blind verdict turned a fully correct run all-red.

    Every assertion here checks that the DECISION flips, not that a dict has
    the right keys: the audit-154 mutation pass showed shape-assertions let
    real defects through.
    """

    EXIF = b"II*\x00 camera exif payload"

    def _kept_exif_result(self) -> tuple[bytes, wc.Policy]:
        src = _png([(b"eXIf", self.EXIF), (b"caBX", C2PA_BLOB)])
        pol = ip.Policy(strip_exif=False)
        res = ip.strip(src, policy=pol)
        assert b"eXIf" in res.data and b"caBX" not in res.data   # policy honoured
        return res.data, pol

    def test_keep_exif_run_is_clean_under_its_own_policy(self):
        data, pol = self._kept_exif_result()
        assert wc.verdict(data, policy=pol)[0] == "CLEAN"

    def test_same_bytes_are_dirty_under_the_strict_question(self):
        """The policy-free call must NOT inherit the exemption — otherwise the
        fix would have widened into "verify can never fail"."""
        data, _pol = self._kept_exif_result()
        assert wc.verdict(data)[0] == "DIRTY"

    def test_policy_exemption_does_not_excuse_what_the_policy_wanted(self):
        """--keep-exif must not make a surviving C2PA manifest read clean."""
        src = _png([(b"eXIf", self.EXIF), (b"caBX", C2PA_BLOB)])
        assert wc.verdict(src, policy=ip.Policy(strip_exif=False))[0] == "DIRTY-AI"

    def test_residue_is_filtered_by_policy_too(self):
        """The byte-level backstop was the other half of the all-red: an XMP
        packet kept on purpose still tripped it."""
        xmp = b'<x:xmpmeta xmlns:x="adobe:ns:meta/">kept</x:xmpmeta>'
        src = _png([(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + xmp)])
        keep_xmp = ip.Policy(strip_xmp=False, strip_iptc=False)
        assert wc.verdict(src, policy=keep_xmp)[0] == "CLEAN"
        assert wc.verdict(src)[0] == "DIRTY"          # strict question unchanged

    def test_result_clean_tracks_the_policy_not_the_absolute(self):
        src = _png([(b"eXIf", self.EXIF), (b"caBX", C2PA_BLOB)])
        res = ip.strip(src, policy=ip.Policy(strip_exif=False))
        assert res.clean is True            # the policy's intent was achieved
        assert res.fully_stripped is False  # ...and the strict question still says no

    def test_result_clean_is_still_false_when_a_wanted_signal_survives(self):
        """Guard the guard: if `clean` could not go False the property is theatre.

        `strip()` raises before returning such a Result, so assert on the
        property directly against a Report that still carries the signal.
        """
        src = _png([(b"caBX", C2PA_BLOB)])
        rep = ip.scan(src)
        fake = ip.Result(data=src, container="png", before=rep, after=rep,
                         policy=ip.Policy())
        assert fake.clean is False
        assert ip.Result(data=src, container="png", before=rep, after=rep,
                         policy=ip.Policy(strip_c2pa=False)).clean is True

    def test_verify_live_passes_the_policy_through(self, monkeypatch):
        """The end-to-end path: replace/cms call verify_live, which must ask
        the policy-aware question or the whole fix is unreachable."""
        data, pol = self._kept_exif_result()
        monkeypatch.setattr(wc, "download_image", lambda _u: data)
        assert wc.verify_live("https://x/y.png", tries=1, policy=pol)["clean"] is True
        assert wc.verify_live("https://x/y.png", tries=1)["clean"] is False


class TestReplaceIdempotence:
    """LOG-1 — `replace --apply` minted a fresh orphan on every run.

    A Webflow asset is immutable: a successful replace uploads a COPY and the
    dirty original stays in the asset list. Nothing recorded that it had been
    handled, so the next night found it, still dirty, and replaced it again.
    """

    ROW = {"action": "replaced", "asset_id": AID_HERO, "new_asset_id": AID_NEW,
           "verify": {"clean": True}}

    def _log(self, tmp_path: Path, *rows: dict) -> Path:
        p = tmp_path / "log.jsonl"
        p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return p

    def test_successful_replace_marks_the_original_superseded(self, tmp_path):
        assert wc.load_superseded(self._log(tmp_path, self.ROW)) == {AID_HERO: AID_NEW}

    def test_the_two_sets_stay_separate(self, tmp_path):
        """The whole point. The original is superseded but NOT clean — its bytes
        are untouched and still served. Merging the sets would make `scan`
        report a site clean while a dirty orphan is public."""
        log = self._log(tmp_path, self.ROW)
        assert AID_HERO in wc.load_superseded(log)
        assert AID_HERO not in wc.load_known_clean(log)
        assert AID_NEW in wc.load_known_clean(log)
        assert AID_NEW not in wc.load_superseded(log)

    @pytest.mark.parametrize("action", ["incomplete_repoint", "verify_failed",
                                        "would_replace", "error", "already_clean"])
    def test_only_a_fully_successful_replace_supersedes(self, tmp_path, action):
        """An incomplete re-point leaves the CMS pointing at the original, and a
        failed verify never proved the copy. Both still need work."""
        row = dict(self.ROW, action=action)
        assert wc.load_superseded(self._log(tmp_path, row)) == {}

    def test_same_asset_id_is_not_a_supersession(self, tmp_path):
        """When Webflow reuses the id the bytes were replaced IN PLACE — there is
        no orphan, and the clean set already covers it. Recording it here would
        skip an asset that may genuinely still need replacing."""
        row = dict(self.ROW, new_asset_id=AID_HERO)
        assert wc.load_superseded(self._log(tmp_path, row)) == {}

    def test_last_successful_replace_wins(self, tmp_path):
        log = self._log(tmp_path,
                        dict(self.ROW, new_asset_id=AID_G1),
                        dict(self.ROW, new_asset_id=AID_G2))
        assert wc.load_superseded(log) == {AID_HERO: AID_G2}

    def test_corrupt_log_costs_time_never_correctness(self, tmp_path):
        p = tmp_path / "log.jsonl"
        p.write_text("not json\n" + json.dumps(self.ROW) + "\n{trunc", encoding="utf-8")
        assert wc.load_superseded(p) == {AID_HERO: AID_NEW}

    def test_second_run_uploads_nothing(self, monkeypatch, tmp_path, capsys):
        """The decision that matters, driven through cmd_replace twice.

        Run 1 replaces and writes the log. Run 2 reads that log and must upload
        NOTHING — before the fix it uploaded a second clean copy, and every
        night after that another one.
        """
        log = tmp_path / "l.jsonl"
        h1 = _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                             assets=[_asset(AID_HERO, "hero.png")], live_index={})
        wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                     backup_dir=str(tmp_path), log_jsonl=str(log)))
        assert len(h1.uploads) == 1, "run 1 should replace the dirty asset"
        assert json.loads(log.read_text().splitlines()[-1])["superseded_by"] == AID_NEW

        # Run 2: the original is STILL on the site (immutable asset, now orphaned)
        # and still dirty. Only the log distinguishes it from unfinished work.
        h2 = _ReplaceHarness(monkeypatch, upload_id=AID_G1,
                             assets=[_asset(AID_HERO, "hero.png")], live_index={})
        wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                     backup_dir=str(tmp_path), log_jsonl=str(log),
                                     skip_known_clean=str(log)))
        assert h2.uploads == [], "run 2 re-replaced an already-replaced asset"
        assert "already replaced" in capsys.readouterr().out

    def test_the_escape_hatch_actually_re_replaces(self, monkeypatch, tmp_path):
        """Guard the guard: if the skip could not be turned off, the previous
        test would pass on a `replace` that had simply stopped working."""
        log = tmp_path / "l.jsonl"
        log.write_text(json.dumps(self.ROW) + "\n", encoding="utf-8")
        h = _ReplaceHarness(monkeypatch, upload_id=AID_G1,
                            assets=[_asset(AID_HERO, "hero.png")], live_index={})
        wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                     backup_dir=str(tmp_path), log_jsonl=str(log),
                                     skip_known_clean=str(log), no_skip_superseded=True))
        assert len(h.uploads) == 1

    def test_a_failed_row_does_not_claim_a_supersession(self, monkeypatch, tmp_path):
        """`load_superseded` filters on the action independently, so writing the
        field on a failed row changes no decision — but the log is a
        verification surface other runs and humans read as evidence. A row
        saying `incomplete_repoint` + `superseded_by: X` asserts a handover that
        did not happen.
        """
        log = tmp_path / "l.jsonl"
        _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                        assets=[_asset(AID_HERO, "hero.png")], live_index={},
                        repoint_status="ref-ambiguous")
        wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                     backup_dir=str(tmp_path), log_jsonl=str(log)))
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert any(r.get("action") == "incomplete_repoint" for r in rows), \
            "fixture did not actually produce a failed row — the assertion below is vacuous"
        for r in rows:
            if r.get("action") != "replaced":
                assert "superseded_by" not in r, \
                    f"{r['action']} row claims superseded_by — the log must not overstate"

    def test_an_unfinished_replace_is_retried_not_skipped(self, monkeypatch, tmp_path):
        """The failure mode on the other side: if `incomplete_repoint` counted
        as handled, an asset whose CMS references were never rewritten would be
        abandoned silently."""
        log = tmp_path / "l.jsonl"
        log.write_text(json.dumps(dict(self.ROW, action="incomplete_repoint")) + "\n",
                       encoding="utf-8")
        h = _ReplaceHarness(monkeypatch, upload_id=AID_G1,
                            assets=[_asset(AID_HERO, "hero.png")], live_index={})
        wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                     backup_dir=str(tmp_path), log_jsonl=str(log),
                                     skip_known_clean=str(log)))
        assert len(h.uploads) == 1, "an incomplete replace must be retried"

    def test_escape_hatch_reaches_the_filter(self):
        """A flag that changes nothing is worse than no flag. Assert BOTH that
        the parser accepts it and that the filter reads it — checking only the
        parser would pass on a flag wired to nothing."""
        pr = wc.build_parser()
        assert pr.parse_args(["replace", "--site", "brightvalley"]).no_skip_superseded is False
        assert pr.parse_args(["replace", "--site", "brightvalley",
                              "--no-skip-superseded"]).no_skip_superseded is True
        src = inspect.getsource(wc.cmd_replace)
        assert "args.no_skip_superseded" in src, "flag parsed but never consulted"
        assert "load_superseded" in src, "cmd_replace never builds the superseded set"


class TestNoOrphanOnRefusal:
    """OR-1 — the id-change refusal ran AFTER upload_bytes.

    Both reasons for refusing depend only on live_index / live_known, which are
    fixed for the whole run. Deciding after the upload therefore paid a
    permanent unreferenced asset on the client's site for information the tool
    already had.
    """

    LIVE = {wc._url_key(f"{CDN}/{AID_HERO}_hero.png"): ["https://example.com/about"]}

    def test_a_refused_asset_is_never_uploaded(self, monkeypatch, tmp_path, capsys):
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                            assets=[_asset(AID_HERO, "hero.png")], live_index=self.LIVE)
        wc.cmd_replace(_replace_args(apply=True, backup_dir=str(tmp_path),
                                     log_jsonl=str(tmp_path / "l.jsonl")))
        assert h.uploads == [], "refusal happened after the upload — orphan created"
        assert h.repoints == []
        out = capsys.readouterr().out
        assert "REFUSED before upload" in out

    def test_unprovable_live_index_also_refuses_before_uploading(self, monkeypatch, tmp_path):
        """The second reason: a crawl that could not complete cannot prove the
        image is unreferenced. Same rule, same ordering."""
        monkeypatch.setattr(wc, "build_live_page_index",
                            lambda url, **kw: ({}, ["p"], ["https://example.com/x"]))
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                            assets=[_asset(AID_HERO, "hero.png")], live_index={})
        monkeypatch.setattr(wc, "build_live_page_index",
                            lambda url, **kw: ({}, ["p"], ["https://example.com/x"]))
        wc.cmd_replace(_replace_args(apply=True, backup_dir=str(tmp_path),
                                     log_jsonl=str(tmp_path / "l.jsonl")))
        assert h.uploads == []

    def test_the_refusal_row_records_that_no_orphan_exists(self, monkeypatch, tmp_path):
        """The log is the evidence surface an operator uses to decide whether a
        cleanup is owed. Silence there reads as 'nothing to clean'."""
        _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                        assets=[_asset(AID_HERO, "hero.png")], live_index=self.LIVE)
        log = tmp_path / "l.jsonl"
        wc.cmd_replace(_replace_args(apply=True, backup_dir=str(tmp_path), log_jsonl=str(log)))
        row = [json.loads(x) for x in log.read_text().splitlines()][-1]
        assert row["action"] == "refused_id_change"
        assert row["orphan_created"] is False

    def test_the_override_still_uploads(self, monkeypatch, tmp_path):
        """Guard the guard: if the pre-check refused unconditionally, the tests
        above would pass on a `replace` that had simply stopped working."""
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                            assets=[_asset(AID_HERO, "hero.png")], live_index=self.LIVE)
        wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                     backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert len(h.uploads) == 1

    def test_a_clean_evidence_run_still_uploads(self, monkeypatch, tmp_path):
        """And the ordinary case — no page refs, crawl complete — must proceed."""
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                            assets=[_asset(AID_HERO, "hero.png")], live_index={})
        wc.cmd_replace(_replace_args(apply=True, backup_dir=str(tmp_path),
                                     log_jsonl=str(tmp_path / "l.jsonl")))
        assert len(h.uploads) == 1


class TestLivePageIndexRetry:
    """OR-1, second half — one transient blip voided a whole run's evidence.

    Every fetch failure poisons `live_known`, which gates an irreversible delete
    and `replace`'s refusal. A single dropped connection out of 200 pages made
    the tool refuse work it could have done correctly.
    """

    def _urlopen(self, script: list):
        """script: one entry per call — an Exception to raise or bytes to return."""
        calls = {"n": 0}

        class _Resp:
            def __init__(self, body): self.body = body
            def read(self): return self.body
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake(req, timeout=None):
            i = calls["n"]; calls["n"] += 1
            item = script[min(i, len(script) - 1)]
            if isinstance(item, Exception):
                raise item
            return _Resp(item)
        return fake, calls

    def test_a_transient_blip_is_retried(self, monkeypatch):
        sitemap = b"<urlset><url><loc>https://example.com/a</loc></url></urlset>"
        page = b'<img src="https://cdn.prod.website-files.com/x/y.png">'
        fake, calls = self._urlopen([sitemap,
                                     urllib.error.URLError("connection reset"),
                                     page])
        monkeypatch.setattr(wc.urllib.request, "urlopen", fake)
        monkeypatch.setattr(wc.time, "sleep", lambda _s: None)
        index, fetched, failures = wc.build_live_page_index("https://example.com", progress=False)
        assert failures == [], "a retryable blip must not poison live_known"
        assert fetched == ["https://example.com/a"]
        assert calls["n"] == 3, "the page must actually have been retried"

    def test_a_404_is_not_retried(self, monkeypatch):
        """A missing page is a fact, not a flake. Retrying it wastes time and
        would let a genuinely absent page look transient."""
        sitemap = b"<urlset><url><loc>https://example.com/gone</loc></url></urlset>"
        err = urllib.error.HTTPError("https://example.com/gone", 404, "Not Found", {}, None)
        fake, calls = self._urlopen([sitemap, err])
        monkeypatch.setattr(wc.urllib.request, "urlopen", fake)
        monkeypatch.setattr(wc.time, "sleep", lambda _s: None)
        _index, _fetched, failures = wc.build_live_page_index("https://example.com", progress=False)
        assert failures, "a 404 page is still a coverage failure"
        assert calls["n"] == 2, f"404 was retried {calls['n'] - 1} time(s)"

    def test_a_persistent_failure_still_fails(self, monkeypatch):
        """Guard the guard: retry must not become 'never reports a failure'."""
        sitemap = b"<urlset><url><loc>https://example.com/a</loc></url></urlset>"
        fake, calls = self._urlopen([sitemap, urllib.error.URLError("down")])
        monkeypatch.setattr(wc.urllib.request, "urlopen", fake)
        monkeypatch.setattr(wc.time, "sleep", lambda _s: None)
        _i, _f, failures = wc.build_live_page_index("https://example.com", progress=False)
        assert failures == ["https://example.com/a"]
        assert calls["n"] == 4, "expected 1 sitemap + 3 attempts"

    def test_the_post_upload_backstop_reports_the_orphan_it_leaves(self, monkeypatch, tmp_path, capsys):
        """The pre-check makes this branch unreachable today — `live_index` is a
        snapshot, so the two lookups cannot disagree. It stays as a guard for a
        future reordering, and is tested by forcing that disagreement: an
        untested safety net is one that will not work when it is finally needed.

        What it must do is name the orphan. A refusal that hides its own side
        effect is how an asset list silently grows.
        """
        real = wc.lookup_refs
        seen = {"n": 0}

        def flaky(index, url):
            # cmd_replace consults the live index three times per asset: the
            # preview line, the pre-upload gate, then this backstop. Answer
            # honestly for the first two and disagree on the third.
            if index:                      # the CMS index — always honest
                return real(index, url)
            seen["n"] += 1
            if seen["n"] >= 3:
                return (["https://example.com/late"], "exact")
            return real(index, url)

        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                            assets=[_asset(AID_HERO, "hero.png")], live_index={})
        monkeypatch.setattr(wc, "lookup_refs", flaky)
        log = tmp_path / "l.jsonl"
        wc.cmd_replace(_replace_args(apply=True, backup_dir=str(tmp_path), log_jsonl=str(log)))
        out = capsys.readouterr().out
        assert len(h.uploads) == 1, "fixture must reach the post-upload branch"
        assert "REFUSED after upload" in out
        assert AID_NEW in out and "purge" in out, "the orphan's id and the cleanup must be named"
        row = [json.loads(x) for x in log.read_text().splitlines()][-1]
        assert row["orphan_created"] is True and row["orphan_asset_id"] == AID_NEW


class TestEverySubcommandCanRunItsHandler:
    """A flag added to one subparser and read by a shared code path raises
    AttributeError only when that subcommand is actually invoked.

    That happened twice: `--skip-known-clean` broke every replace test until a
    vendored CEL run surfaced it, and `--no-skip-superseded` was read by
    `cmd_cms` before its parser defined it. Neither is reachable by a unit test
    of the function — the parser and the handler have to be checked together.
    """

    CASES = {
        "cmd_scan":    ["scan", "--site", "cel"],
        "cmd_clean":   ["clean", "--local", "x.png"],
        "cmd_replace": ["replace", "--site", "cel"],
        "cmd_cms":     ["cms", "--site", "cel"],
        "cmd_purge":   ["purge", "--site", "cel"],
        "cmd_verify":  ["verify", "--url", "https://example.com/a.png"],
        "cmd_lineage": ["lineage", "--site", "cel"],
    }

    @pytest.mark.parametrize("fn_name,argv", sorted(CASES.items()))
    def test_handler_reads_only_args_its_parser_provides(self, fn_name, argv):
        fn = getattr(wc, fn_name)
        ns = wc.build_parser().parse_args(argv)
        tree = ast.parse(inspect.getsource(fn))
        reads = {n.attr for n in ast.walk(tree)
                 if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                 and n.value.id == "args"}
        guarded = {n.args[1].value for n in ast.walk(tree)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == "getattr" and len(n.args) >= 3
                   and isinstance(n.args[1], ast.Constant)}
        missing = sorted(r for r in reads if not hasattr(ns, r) and r not in guarded)
        assert not missing, (
            f"{fn_name} reads args.{{{', '.join(missing)}}} which `{' '.join(argv)}` "
            f"does not define — this raises AttributeError at runtime, not in review")

    def test_the_check_can_fail(self):
        """Guard the guard: an AST walk that found nothing would pass silently
        on every handler forever."""
        tree = ast.parse(inspect.getsource(wc.cmd_replace))
        reads = {n.attr for n in ast.walk(tree)
                 if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                 and n.value.id == "args"}
        assert "apply" in reads and len(reads) > 5, \
            f"the AST walk found only {sorted(reads)} — it is not seeing arg reads"
        ns = wc.build_parser().parse_args(["scan", "--site", "cel"])
        assert not hasattr(ns, "allow_new_asset_id"), \
            "scan gained the flag; pick another replace-only arg for this canary"


# ── the cms command ──────────────────────────────────────────────────────────
# `cmd_cms` had NO harness and NO tests before this — audit 154's auditor died
# on a connection error before reaching it, and it is the command that did the
# actual brightvalley work. Everything below exists because of that gap.
CMS_ONE_ITEM = {"col2": [{
    "id": "i2", "isDraft": False, "isArchived": False, "lastPublished": "2026-01-01",
    "fieldData": {"slug": "jane",
                  "headshot": {"url": f"{CDN}/{AID_HERO}_hero.png", "fileId": AID_HERO}},
}]}


class _CmsHarness:
    """Wires cmd_cms against fakes and records every write attempt."""

    def __init__(self, monkeypatch, *, upload_id, items=None, bytes_by_url=None,
                 repoint_status=None, upload_error=None):
        self.uploads: list[tuple[str, int]] = []
        self.repoints: list[dict] = []
        self.published: list[tuple[str, list[str]]] = []
        self.repoint_status = repoint_status
        blobs = bytes_by_url or {}
        api = _FakeApi(collections=[{"id": "col2", "slug": "team"}],
                       fields={"col2": [{"slug": "headshot", "type": "Image"}]},
                       items=items or CMS_ONE_ITEM, assets=[])
        _install_fake(monkeypatch, api)
        self.api = api

        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "download_image", lambda u, timeout=30: blobs.get(u, DIRTY_PNG))

        def fake_upload(data, name, site_id, token):
            if upload_error:
                raise upload_error
            self.uploads.append((name, len(data)))
            return {"asset_id": upload_id, "hostedUrl": f"{CDN}/{upload_id}_{name}",
                    "md5": "x", "size": len(data)}

        monkeypatch.setattr(wc, "upload_bytes", fake_upload)

        def fake_repoint(token, ref, *, old_url, new_url, new_file_id, apply):
            self.repoints.append({"ref": ref, "new_url": new_url, "apply": apply})
            if self.repoint_status:
                return {"status": self.repoint_status, "candidates": ["a", "b"]}
            return {"status": "repointed"}

        monkeypatch.setattr(wc, "repoint_reference", fake_repoint)
        monkeypatch.setattr(wc, "publish_items",
                            lambda t, cid, ids: self.published.append((cid, ids)) or {})
        monkeypatch.setattr(wc, "verify_live", lambda url, **kw: {"url": url, "clean": True})
        # Default to "crawled nothing, cleanly". Without this the suite reaches
        # the real network the moment cmd_cms gains a live-page crawl — which is
        # exactly what happened. Tests that care override it.
        monkeypatch.setattr(wc, "build_live_page_index", lambda url, **kw: ({}, [], []))


def _cms_args(**over):
    """cmd_cms's args THROUGH the real parser — see _replace_args."""
    args = wc.build_parser().parse_args(["cms", "--site", "cel", "--quiet"])
    for k, v in over.items():
        assert hasattr(args, k), f"unknown arg {k!r} — did the CLI flag get renamed?"
        setattr(args, k, v)
    return args


class TestCmsSkipCacheActuallySkips:
    """CMS-1 — `--skip-known-clean` was a silent no-op in `cmd_cms`.

    `cmd_cms` works from URL keys (`{asset_id}_{name}`); both caches are keyed
    by the bare asset id. It compared the two namespaces directly, so no entry
    could ever match: the flag was accepted, printed nothing, reported
    `skipped 0`, and re-downloaded every image on the site on every run. The
    command that did the actual brightvalley work had no working cache at all.
    """

    KEY = f"{AID_HERO}_hero.png"

    def test_the_id_is_recoverable_from_a_url_key(self):
        assert wc.asset_id_from_url_key(self.KEY) == AID_HERO
        assert wc.asset_id_from_url_key(wc._url_key(f"{CDN}/{self.KEY}")) == AID_HERO

    def test_a_stacked_prefix_yields_the_OUTERMOST_id(self):
        """Re-uploading a prefixed file stacks another id; the outer one is the
        current asset, the inner one names what it superseded."""
        assert wc.asset_id_from_url_key(f"{AID_NEW}_{AID_HERO}_team.webp") == AID_NEW

    @pytest.mark.parametrize("key", ["hero.png", "", "notanid_hero.png",
                                     "6a7dad834766eebcddd96d9_hero.png",   # 23 chars
                                     "6a7dad834766eebcddd96d9fx_hero.png"])  # 25
    def test_a_key_with_no_id_yields_empty(self, key):
        assert wc.asset_id_from_url_key(key) == ""

    def test_the_namespaces_no_longer_disagree(self):
        """The defect in one line: the cache stores this, the loop tested that."""
        assert wc._url_key(f"{CDN}/{self.KEY}") != AID_HERO      # why it never matched
        assert wc.asset_id_from_url_key(wc._url_key(f"{CDN}/{self.KEY}")) == AID_HERO

    def test_cms_actually_skips_a_known_clean_image(self, monkeypatch, tmp_path, capsys):
        log = tmp_path / "l.jsonl"
        log.write_text(json.dumps({"mode": "scan-asset", "action": "scanned",
                                   "asset_id": AID_HERO, "signals": []}) + "\n",
                       encoding="utf-8")
        h = _CmsHarness(monkeypatch, upload_id=AID_NEW)
        rc = wc.cmd_cms(_cms_args(apply=True, backup_dir=str(tmp_path),
                                  log_jsonl=str(tmp_path / "out.jsonl"),
                                  skip_known_clean=str(log)))
        out = capsys.readouterr().out
        assert h.uploads == [], "a known-clean image was re-downloaded and re-uploaded"
        assert "skipped (known clean)  1" in out
        assert rc == 0

    def test_cms_skips_an_already_replaced_image(self, monkeypatch, tmp_path, capsys):
        log = tmp_path / "l.jsonl"
        log.write_text(json.dumps({"action": "replaced", "asset_id": AID_HERO,
                                   "new_asset_id": AID_NEW}) + "\n", encoding="utf-8")
        h = _CmsHarness(monkeypatch, upload_id=AID_G1)
        wc.cmd_cms(_cms_args(apply=True, backup_dir=str(tmp_path),
                             log_jsonl=str(tmp_path / "out.jsonl"),
                             skip_known_clean=str(log)))
        assert h.uploads == [], "cmd_cms re-replaced an already-replaced image"
        assert "already replaced" in capsys.readouterr().out

    def test_without_the_cache_it_still_does_the_work(self, monkeypatch, tmp_path):
        """Guard the guard: the two tests above would also pass on a `cms` that
        had simply stopped uploading anything."""
        h = _CmsHarness(monkeypatch, upload_id=AID_NEW)
        wc.cmd_cms(_cms_args(apply=True, backup_dir=str(tmp_path),
                             log_jsonl=str(tmp_path / "out.jsonl")))
        assert len(h.uploads) == 1

    def test_a_successful_cms_replace_records_the_original_id(self, monkeypatch, tmp_path):
        """`load_superseded` keys on the ORIGINAL asset id. cmd_cms works from
        URLs, so without recovering it the row records a supersession that
        nothing can ever look up — the skip would stay broken."""
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        log = tmp_path / "out.jsonl"
        wc.cmd_cms(_cms_args(apply=True, backup_dir=str(tmp_path), log_jsonl=str(log)))
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        done = [r for r in rows if r.get("action") == "replaced"]
        assert done, "fixture produced no successful replace"
        assert done[0]["asset_id"] == AID_HERO and done[0]["superseded_by"] == AID_NEW
        assert wc.load_superseded(log) == {AID_HERO: AID_NEW}, \
            "the row it writes must be readable by the loader that consumes it"


class TestNoPublishWithoutVerification:
    """CMS-2 — a failed verify still published the item.

    Publishing is the irreversible half of these commands: it puts the new
    bytes on the live site. Queuing it inside the re-point loop meant the
    decision happened BEFORE the verify that was supposed to gate it, so a run
    that printed `VERIFY FAILED` and exited 2 had already gone live. Honest
    reporting after an irreversible act is not a substitute for ordering.
    """

    def test_cms_withholds_publish_when_verification_fails(self, monkeypatch, tmp_path, capsys):
        h = _CmsHarness(monkeypatch, upload_id=AID_NEW)
        monkeypatch.setattr(wc, "verify_live",
                            lambda url, **kw: {"url": url, "clean": False, "verdict": "DIRTY"})
        rc = wc.cmd_cms(_cms_args(apply=True, verify=True, auto_publish=True,
                                  backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert h.published == [], "published bytes that failed verification"
        assert rc == 2
        assert "not queuing" in capsys.readouterr().out

    def test_cms_publishes_when_verification_passes(self, monkeypatch, tmp_path):
        """Guard the guard: withholding always would look identical."""
        h = _CmsHarness(monkeypatch, upload_id=AID_NEW)
        wc.cmd_cms(_cms_args(apply=True, verify=True, auto_publish=True,
                             backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert h.published == [("col2", ["i2"])]

    def test_replace_withholds_publish_when_verification_fails(self, monkeypatch, tmp_path):
        h = _ReplaceHarness(monkeypatch, upload_id=AID_HERO,
                            assets=[_asset(AID_HERO, "hero.png")], live_index={})
        monkeypatch.setattr(wc, "verify_live",
                            lambda url, **kw: {"url": url, "clean": False, "verdict": "DIRTY"})
        rc = wc.cmd_replace(_replace_args(apply=True, verify=True, auto_publish=True,
                                          backup_dir=str(tmp_path),
                                          log_jsonl=str(tmp_path / "l.jsonl")))
        assert h.published == [], "the same defect existed in cmd_replace"
        assert rc == 2

    def test_replace_publishes_when_verification_passes(self, monkeypatch, tmp_path):
        h = _ReplaceHarness(monkeypatch, upload_id=AID_HERO,
                            assets=[_asset(AID_HERO, "hero.png")], live_index={})
        wc.cmd_replace(_replace_args(apply=True, verify=True, auto_publish=True,
                                     backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert h.published, "a verified run must still publish"


class TestCmsReportsDesignerReferences:
    """CMS-3 — `cmd_cms` never looked at published pages at all.

    An image can be in a CMS field AND placed on a page in the Designer.
    `cmd_cms` rewrites the CMS reference and mints a new asset id, which leaves
    the Designer reference on the ORIGINAL, still serving un-stripped bytes —
    and the run printed `repointed 1/1` and exited 0.

    Unlike `replace` this does not refuse: the CMS half is genuinely fixable and
    refusing would leave everything dirty. It must, however, be impossible to
    exit 0 while a dirty image is still published.
    """

    LIVE = {wc._url_key(f"{CDN}/{AID_HERO}_hero.png"): ["https://example.com/about"]}

    def _live(self, monkeypatch, index, failures=()):
        monkeypatch.setattr(wc, "build_live_page_index",
                            lambda url, **kw: (index, ["https://example.com/about"], list(failures)))

    def test_a_designer_reference_makes_the_run_incomplete(self, monkeypatch, tmp_path, capsys):
        h = _CmsHarness(monkeypatch, upload_id=AID_NEW)
        self._live(monkeypatch, self.LIVE)
        rc = wc.cmd_cms(_cms_args(apply=True, check_live_pages=True, site_url="https://example.com",
                                  backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        out = capsys.readouterr().out
        assert len(h.uploads) == 1, "the CMS half must still be done"
        assert h.repoints, "the CMS reference must still be rewritten"
        assert "STILL DIRTY on 1 published page" in out
        assert "webflow-implement" in out
        assert "1 Designer-set reference(s) still point at un-stripped" in out, \
            "the summary must carry the count too — the per-image line scrolls away"
        assert "This run is NOT complete" in out
        assert rc == 2, "a run that leaves a dirty published image must not exit 0"

    def test_no_designer_reference_still_exits_zero(self, monkeypatch, tmp_path, capsys):
        """Guard the guard: an unconditional error would look identical."""
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        self._live(monkeypatch, {})
        rc = wc.cmd_cms(_cms_args(apply=True, check_live_pages=True, site_url="https://example.com",
                                  backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert rc == 0
        assert "STILL DIRTY" not in capsys.readouterr().out

    def test_the_reference_is_recorded_in_the_log(self, monkeypatch, tmp_path):
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        self._live(monkeypatch, self.LIVE)
        log = tmp_path / "l.jsonl"
        wc.cmd_cms(_cms_args(apply=True, check_live_pages=True, site_url="https://example.com",
                             backup_dir=str(tmp_path), log_jsonl=str(log)))
        row = [json.loads(x) for x in log.read_text().splitlines()][-1]
        assert row["designer_page_refs"] == ["https://example.com/about"]

    def test_skipping_the_check_says_so_rather_than_implying_completeness(
            self, monkeypatch, tmp_path, capsys):
        """Silence on an unchecked surface reads as 'checked, nothing found'."""
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        wc.cmd_cms(_cms_args(apply=True, check_live_pages=False,
                             backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert "Published pages were NOT fully checked" in capsys.readouterr().out

    def test_the_flag_without_any_domain_still_warns(self, monkeypatch, tmp_path, capsys):
        """Found on the first live brightvalley run: the summary keyed on the
        FLAG, so `--check-live-pages` with no domain crawled nothing and said
        nothing — the most confident-looking output of the three."""
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        monkeypatch.setattr(wc, "evidence_domains", lambda site, cfg, override: [])
        wc.cmd_cms(_cms_args(apply=True, check_live_pages=True, site_url="",
                             backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        out = capsys.readouterr().out
        assert "Published pages were NOT fully checked" in out
        assert "no domain is on record" in out

    def test_staging_only_sites_are_crawled_too(self, monkeypatch, tmp_path, capsys):
        """brightvalley's Webflow build lives on `staging_url` while its
        production domain still runs WordPress. `replace` and `cms` each looked
        only at `live_url`, so on the site this tool was written for both found
        nothing to crawl and said so in a line nobody reads. All three commands
        now share `evidence_domains`.
        """
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        monkeypatch.setattr(wc, "load_site_config",
                            lambda s: {"webflow_site_id": SITE_ID,
                                       "staging_url": "https://bv.webflow.io"})
        monkeypatch.setattr(wc, "_registry_production_url", lambda s: "")
        crawled = []
        monkeypatch.setattr(wc, "build_live_page_index",
                            lambda url, **kw: (crawled.append(url), ({}, ["p"], []))[1])
        wc.cmd_cms(_cms_args(apply=True, check_live_pages=True,
                             backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert crawled == ["https://bv.webflow.io"], \
            f"staging-only site was not crawled: {crawled}"
        assert "Published pages were NOT fully checked" not in capsys.readouterr().out

    def test_replace_crawls_staging_too(self, monkeypatch, tmp_path):
        """The same defect existed in cmd_replace."""
        _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                        assets=[_asset(AID_HERO, "hero.png")], live_index={})
        monkeypatch.setattr(wc, "load_site_config",
                            lambda s: {"webflow_site_id": SITE_ID,
                                       "staging_url": "https://bv.webflow.io"})
        monkeypatch.setattr(wc, "_registry_production_url", lambda s: "")
        crawled = []
        monkeypatch.setattr(wc, "build_live_page_index",
                            lambda url, **kw: (crawled.append(url), ({}, ["p"], []))[1])
        wc.cmd_replace(_replace_args(apply=False, site_url="", check_live_pages=True,
                                     backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert crawled == ["https://bv.webflow.io"]

    def test_a_half_finished_crawl_also_warns(self, monkeypatch, tmp_path, capsys):
        """A crawl that returned some pages but recorded failures has not proven
        absence either — live_known is the only honest gate."""
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        self._live(monkeypatch, {}, failures=["https://example.com/x"])
        wc.cmd_cms(_cms_args(apply=True, check_live_pages=True, site_url="https://example.com",
                             backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        out = capsys.readouterr().out
        assert "Published pages were NOT fully checked" in out
        assert "did not complete" in out

    def test_an_incomplete_crawl_is_recorded_as_unknown(self, monkeypatch, tmp_path):
        """A crawl that could not finish proves nothing about absence."""
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        self._live(monkeypatch, {}, failures=["https://example.com/x"])
        log = tmp_path / "l.jsonl"
        wc.cmd_cms(_cms_args(apply=True, check_live_pages=True, site_url="https://example.com",
                             backup_dir=str(tmp_path), log_jsonl=str(log)))
        row = [json.loads(x) for x in log.read_text().splitlines()][-1]
        assert row.get("designer_refs_unknown") is True
