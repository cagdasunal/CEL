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
import http.client
import inspect
import io
import json
import random
import re
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

try:  # Pillow drives the lineage-boundary fixtures only
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


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

    def test_a_24_char_NON_HEX_head_is_not_an_id_prefix(self):
        """The length check alone is not the rule — the head must be hex too.

        'my_photo_2026.png' only exercises the length clause (head 'my'), so
        dropping the hex test from `_strip_id_prefixes` changed nothing any test
        could see. A real filename can easily reach 24 characters before its
        first underscore, and eating that head silently renames the image: every
        basename join then compares the WRONG names, which is the fallback the
        whole brightvalley re-point depends on.
        """
        name = "montreal-summer-camp-jan_hero.png"
        assert len(name.partition("_")[0]) == 24, "premise: the head is exactly 24 chars"
        assert wc._strip_id_prefixes(name) == name, \
            "a 24-character non-hex head is part of the filename, not an asset id"
        # Guard the guard: the hex path must still strip, or the assertion above
        # could be satisfied by a function that never strips anything.
        assert wc._strip_id_prefixes(f"{AID_HERO}_hero.png") == "hero.png"

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
        # 600x600, not 200x200. The absolute claim below is a property of the
        # SOURCE RESOLUTION, not of the data domain: a 200x200 source loses
        # so much detail on the way to a 16x16 grid that the trim boundary
        # dominates it. Measured on this exact fixture (Pillow 12.2.0):
        #   200x200 -> paired 41   300x300 -> 11   400x400 -> 31   600x600 -> 19
        # 41 is OVER the threshold of 40, which is why the absolute assertion
        # used to live in a separate test gated on a real photograph. It does
        # not need one — it needs a source big enough to survive the downsample.
        orig = self._img(17, 600, 600)
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
        # A RELATIVE claim: it holds for any fixture, so it cannot be satisfied
        # by tuning the threshold to fit this one.
        assert paired < plain / 2, (
            f"trimming barely helped: {plain} -> {paired}. Expected a large reduction.")
        # And the ABSOLUTE claim, which is the one the tool actually acts on:
        # the derivative must come back UNDER the match threshold, or lineage
        # still reports a padded AI derivative as unrelated. This used to live
        # in a sibling test gated on
        # `sites/brightvalley/assets/office-scenes/A1-gabriela-solo.png`, which
        # is not tracked by git — so it ran on one machine and SKIPPED
        # everywhere else, i.e. the absolute claim was effectively unasserted in
        # CI. A large enough synthetic source carries it portably instead.
        assert paired <= wc.PHASH_MATCH_MAX, (
            f"a padded derivative still misses the threshold ({paired} > {wc.PHASH_MATCH_MAX})")

    def test_the_plain_hash_is_sometimes_the_half_that_carries_the_match(self):
        """The other direction — the reason `perceptual_fingerprint` keeps BOTH.

        Every other fixture here measures the padding case, where the trimmed
        hash is by construction the better half; collapsing
        `fingerprint_distance` to the trimmed leg alone therefore survived all
        of them. Trimming is a heuristic: on an image with a legitimate solid
        border as part of the composition it removes real signal, and it does
        not remove the SAME amount from a lossy re-encode of that image,
        because the compression artefacts smear the border edge. The two
        trimmed crops then disagree while the untrimmed frames still match.
        """
        from PIL import Image
        base = Image.new("RGB", (400, 400), (0, 0, 0))
        base.paste(Image.open(io.BytesIO(self._img(11, 340, 340))).convert("RGB"), (30, 30))
        b1 = io.BytesIO(); base.save(b1, format="PNG")
        original = b1.getvalue()
        b2 = io.BytesIO(); base.resize((300, 300), Image.LANCZOS).save(b2, format="WEBP", quality=30)
        derivative = b2.getvalue()          # resize + lossy re-encode, NO added padding

        fa = wc.perceptual_fingerprint(original)
        fb = wc.perceptual_fingerprint(derivative)
        plain, trimmed = wc.hamming(fa[0], fb[0]), wc.hamming(fa[1], fb[1])

        assert trimmed > wc.PHASH_MATCH_MAX, (
            f"premise: the TRIMMED half must miss here ({trimmed}) or this test proves nothing "
            "about keeping the plain one")
        assert plain < trimmed, f"the plain half must be the better one here ({plain} vs {trimmed})"
        assert plain <= wc.PHASH_MATCH_MAX, f"the plain half must actually match ({plain})"
        assert wc.fingerprint_distance(fa, fb) <= wc.PHASH_MATCH_MAX, (
            "matching must take the BETTER of the two hashes — taking the trimmed one alone "
            f"loses this derivative entirely ({trimmed} > {wc.PHASH_MATCH_MAX})")

    def _padded(self, seed: int, pad: int, colour: tuple[int, int, int]) -> bytes:
        """A 160x160 image centred in a uniform border — the shape _autotrim exists for."""
        from PIL import Image
        im = Image.open(io.BytesIO(self._img(seed, 160, 160))).convert("RGB")
        canvas = Image.new("RGB", (im.width + 2 * pad, im.height + 2 * pad), colour)
        canvas.paste(im, (pad, pad))
        buf = io.BytesIO(); canvas.save(buf, format="PNG"); return buf.getvalue()

    def test_trimming_does_not_make_unrelated_images_collide(self):
        """Trimming pulls two DIFFERENT pictures onto the same canvas size.

        The fixtures must actually be trimmed, or this is a duplicate of
        test_different_images_are_far_apart: full-bleed images are a no-op for
        _autotrim, so fingerprint_distance collapses to the plain-hash
        comparison and the trim-aware leg is never measured. Different border
        widths AND different border colours on purpose — that is the shape in
        which trimming could plausibly normalise two unrelated images into one.
        """
        from PIL import Image
        a = self._padded(5, 60, (255, 255, 255))
        b = self._padded(37, 140, (8, 8, 8))
        assert Image.open(io.BytesIO(a)).size == (280, 280)
        assert Image.open(io.BytesIO(b)).size == (440, 440)
        assert wc._autotrim(Image.open(io.BytesIO(a))).size == (160, 160), \
            "fixture a was not trimmed — the trim-aware leg would go untested"
        assert wc._autotrim(Image.open(io.BytesIO(b))).size == (160, 160), \
            "fixture b was not trimmed — the trim-aware leg would go untested"

        d = wc.fingerprint_distance(wc.perceptual_fingerprint(a), wc.perceptual_fingerprint(b))
        assert d > wc.PHASH_MATCH_MAX * 2, f"trim-aware matching collided unrelated images ({d})"

    def test_a_perfectly_flat_image_has_no_bbox_and_is_left_alone(self):
        """The `getbbox() is None` leg: a uniform field differs from its own
        corner colour nowhere, so there is no box to crop to at all."""
        from PIL import Image, ImageChops
        buf = io.BytesIO()
        Image.new("RGB", (200, 200), (240, 240, 240)).save(buf, format="PNG")
        flat = buf.getvalue()
        g = Image.open(io.BytesIO(flat)).convert("RGB")
        bg = Image.new("RGB", g.size, g.getpixel((0, 0)))
        assert ImageChops.difference(g, bg).convert("L").getbbox() is None, \
            "premise: this fixture reaches the `bb is None` branch, not the 30% floor"
        assert wc._autotrim(Image.open(io.BytesIO(flat))).size == (200, 200)

    def test_near_uniform_image_is_not_trimmed_to_nothing(self):
        """A NEAR-uniform image must not trim away to a sliver — every such
        image would then collide with every other.

        The fixture is deliberately near-uniform rather than perfectly flat: a
        perfectly flat one has no bbox at all, short-circuits on `bb and …`,
        and leaves the two 30%-floor clauses unevaluated — so it locked
        nothing. Here the bbox EXISTS and is tiny, which is the only shape that
        reaches the floor.
        """
        from PIL import Image, ImageChops
        im = Image.new("RGB", (200, 200), (240, 240, 240))
        for x in range(100, 106):
            for y in range(100, 106):
                im.putpixel((x, y), (60, 60, 60))
        buf = io.BytesIO(); im.save(buf, format="PNG")
        near_uniform = buf.getvalue()

        g = Image.open(io.BytesIO(near_uniform)).convert("RGB")
        bg = Image.new("RGB", g.size, g.getpixel((0, 0)))
        raw = ImageChops.difference(g, bg).convert("L").point(
            lambda v: 255 if v > 12 else 0).getbbox()
        assert raw == (100, 100, 106, 106), (
            f"premise: the raw bbox must be a tiny 6x6 box the floor has to reject (got {raw})")
        assert wc._autotrim(Image.open(io.BytesIO(near_uniform))).size == (200, 200), \
            "a 6x6 bbox is under 30% of both dimensions — the crop must be refused"

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

    def test_a_picture_on_a_big_white_canvas_is_not_called_degenerate(self):
        """`max()`, not `min()` — the degeneracy test asks whether EITHER half
        carries signal, and it must, because either half can be the flat one.

        A small photograph centred on a large white canvas — a product shot, a
        logo card, a letterboxed thumbnail — is mostly background, so the
        whole-frame hash really is close to flat. The TRIMMED hash sees the
        actual picture. Taking the minimum of the two popcounts would evict
        exactly these images from the corpus as 'too flat to identify', and
        `lineage` reports what it evicted as `skipped_low_detail` — a confident
        non-answer on an image it could in fact have matched.
        """
        from PIL import Image
        import math
        inner = Image.new("RGB", (104, 104))
        inner.putdata([(int(128 + 100 * math.sin(2.6 * x / 104) * math.cos(2.0 * y / 104)),) * 3
                       for y in range(104) for x in range(104)])
        canvas = Image.new("RGB", (340, 340), (255, 255, 255))
        canvas.paste(inner, (118, 118))
        buf = io.BytesIO(); canvas.save(buf, format="PNG")
        data = buf.getvalue()

        fp = wc.perceptual_fingerprint(data)
        plain_bits = bin(fp[0]).count("1")
        trimmed_bits = bin(fp[1]).count("1")
        assert plain_bits < wc.MIN_FINGERPRINT_BITS, (
            f"premise: the whole-frame hash must be under the floor ({plain_bits}) — "
            "otherwise this fixture never reaches the max/min distinction")
        assert trimmed_bits >= wc.MIN_FINGERPRINT_BITS, (
            f"premise: the trimmed hash must carry real signal ({trimmed_bits})")
        assert not wc.fingerprint_is_degenerate(fp), (
            "one rich half is enough — this image is identifiable and must stay in the corpus")

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

    def test_verify_live_retries_while_the_cdn_still_serves_the_old_bytes(self, monkeypatch):
        """A CDN mid-propagation answers 200 with the PREVIOUS object.

        That response is parseable and DIRTY, not an error — so the retry loop
        is the only thing standing between "we uploaded a clean file" and
        "verify_failed" on a replace that in fact succeeded. Returning the first
        answer whatever it says makes the poll a single fetch with extra steps,
        and the failure it invents is indistinguishable from a real one.
        """
        served = [DIRTY_PNG, CLEAN_PNG]
        fetched = []

        def dl(u, timeout=30):
            fetched.append(u)
            return served[min(len(fetched) - 1, len(served) - 1)]

        monkeypatch.setattr(wc, "download_image", dl)
        r = wc.verify_live("https://x/y.png", tries=2, sleep=0)
        assert len(fetched) == 2, f"a DIRTY first answer must be retried (fetched {len(fetched)})"
        assert r["clean"] is True and r["verdict"] == "CLEAN"

    def test_verify_live_stops_at_the_last_try_rather_than_looping(self, monkeypatch):
        """Guard the guard: retrying forever would hang the nightly run."""
        fetched = []
        monkeypatch.setattr(wc, "download_image",
                            lambda u, timeout=30: (fetched.append(u), DIRTY_PNG)[1])
        r = wc.verify_live("https://x/y.png", tries=3, sleep=0)
        assert len(fetched) == 3 and r["clean"] is False

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

    FONT = b"\x00\x01\x00\x00\x00\x0c\x00\x80\x00\x03\x00@"

    def test_the_local_walker_never_even_opens_a_font(self, tmp_path):
        """Why the exemption cannot be tested on `--local`.

        `iter_local_images` filters on IMAGE_EXTS, so a .ttf on disk never
        reaches `_is_concerning_parse_error` at all. Two tests used to claim
        they locked the font exemption from here; they were measuring the
        extension filter. The exemption itself is exercised on `--site`, below,
        where the asset list serves whatever Webflow holds.
        """
        (tmp_path / "f.ttf").write_bytes(self.FONT)
        (tmp_path / "ok.png").write_bytes(CLEAN_PNG)
        assert [p.name for p in wc.iter_local_images([str(tmp_path)])] == ["ok.png"]
        assert ".ttf" not in wc.IMAGE_EXTS
        assert wc.main(["scan", "--local", str(tmp_path)]) == 0

    def test_scan_exits_two_when_a_real_image_could_not_be_read(self, tmp_path, capsys):
        (tmp_path / "broken.png").write_bytes(ip._PNG_MAGIC + b"\x00\x00\x00\x0dIHDR")
        assert wc.main(["scan", "--local", str(tmp_path)]) == 2
        assert "UNKNOWN, not clean" in capsys.readouterr().err

    def _site(self, monkeypatch, blobs: list[tuple[str, str, bytes]]):
        """`scan --site` over `(asset_id, name, bytes)` — the surface where a
        font really does get downloaded and handed to the scanner."""
        assets = [{"id": aid, "originalFileName": f"{aid}_{name}", "displayName": name,
                   "hostedUrl": f"{CDN}/{aid}_{name}", "contentType": "application/octet-stream"}
                  for aid, name, _ in blobs]
        by_url = {f"{CDN}/{aid}_{name}": data for aid, name, data in blobs}
        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets", lambda t, s, limit=None: assets)
        monkeypatch.setattr(wc, "build_reference_index", lambda *a, **k: ({}, []))
        monkeypatch.setattr(wc, "download_image", lambda u, timeout=30: by_url[u])
        return wc.cmd_scan(wc.build_parser().parse_args(["scan", "--site", "cel", "--quiet"]))

    def test_a_site_whose_assets_include_a_font_still_exits_zero(self, monkeypatch, capsys):
        """The exemption, on the path that has it. Every Webflow site holds
        fonts and PDFs in the Assets panel; counting them unreadable made the
        nightly exit 2 on a healthy site, every night, forever."""
        rc = self._site(monkeypatch, [(AID_LOGO, "brand.ttf", self.FONT),
                                      (AID_HERO, "hero.png", CLEAN_PNG)])
        out = capsys.readouterr()
        assert rc == 0, f"a font must not redden a clean site\n{out.out}"
        assert "unreadable" not in out.out

    def test_a_font_does_not_mask_an_image_that_really_could_not_be_read(
            self, monkeypatch, capsys):
        """Guard the guard: exempting the font must not exempt the shape a
        manifest hides in — a container we DID recognise whose walk aborted, so
        it reports zero signals and looks exactly like a clean file."""
        rc = self._site(monkeypatch, [
            (AID_LOGO, "brand.ttf", self.FONT),
            (AID_HERO, "hero.png", ip._PNG_MAGIC + b"\x00\x00\x00\x0dIHDR")])
        out = capsys.readouterr()
        assert rc == 2, "an unreadable PNG must still move the exit code"
        assert "1 unreadable" in out.out, f"exactly the PNG, not the font\n{out.out}"
        assert "UNKNOWN, not clean" in out.err


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
        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets", lambda t, s, limit=None: [_asset(AID_HERO, "h.png")])
        monkeypatch.setattr(wc, "download_image", lambda u, timeout=30: DIRTY_PNG)
        monkeypatch.setattr(wc, "evidence_domains", lambda *a, **k: [])
        monkeypatch.setattr(wc, "asset_id_appears_in_cms", lambda *a, **k: {AID_HERO: []})
        # Through the real parser, never a hand-rolled Namespace: this test broke
        # the moment purge gained --superseded, which is exactly the drift the
        # _replace_args docstring warns about.
        args = wc.build_parser().parse_args(["purge", "--site", "bv", "--quiet"])
        args.backup_dir = str(tmp_path)
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


class TestPurgeRequiresAllFourConditions:
    """`cmd_purge` is the only IRREVERSIBLE mode, and one test reached its body.

    Its docstring promises four independent, ALL-required conditions. Nothing
    measured them: `test_no_domain_on_record_is_not_silently_treated_as_proof`
    covers the no-domain path and every other assertion about purge was made
    against `evidence_domains` in isolation. A condition that is never
    individually falsified is a condition nobody has checked is wired up — and
    the failure mode here is a deleted client asset.
    """

    def _purge(self, monkeypatch, tmp_path, *, blob=DIRTY_PNG, cms=(), page_hits=(),
               backup=True, argv=(), delete_raises=None):
        """Drive cmd_purge with exactly one candidate; return (rc, deleted_ids, out)."""
        deleted: list[str] = []
        url = f"{CDN}/{AID_HERO}_hero.png"
        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets",
                            lambda t, s, limit=None: [_asset(AID_HERO, "hero.png")])
        monkeypatch.setattr(wc, "download_image", lambda u, timeout=30: blob)
        monkeypatch.setattr(wc, "asset_id_appears_in_cms",
                            lambda *a, **k: {AID_HERO: list(cms)})
        index = {wc._url_key(url): list(page_hits)} if page_hits else {}
        monkeypatch.setattr(wc, "crawl_evidence_domains",
                            lambda *a, **k: (index, ["https://example.com/"], []))

        def _delete(token, aid):
            if delete_raises is not None:
                raise delete_raises
            deleted.append(aid)
            return {}

        monkeypatch.setattr(wc, "delete_asset", _delete)
        bdir = tmp_path / "backup"
        bdir.mkdir()
        if backup:
            (bdir / f"{AID_HERO}_hero.png").write_bytes(blob)
        args = wc.build_parser().parse_args(
            ["purge", "--site", "bv", "--quiet", "--backup-dir", str(bdir),
             "--log-jsonl", str(tmp_path / "purge.jsonl"), *argv])
        rc = wc.cmd_purge(args)
        return rc, deleted

    def test_all_four_satisfied_deletes_exactly_once(self, monkeypatch, tmp_path, capsys):
        """The positive control. Without it every negative below could be
        satisfied by a purge that deletes nothing, ever."""
        rc, deleted = self._purge(monkeypatch, tmp_path, argv=["--apply"])
        assert rc == 0 and deleted == [AID_HERO]
        assert "DELETED" in capsys.readouterr().out

    @pytest.mark.parametrize("label,kw,reason", [
        ("2 — referenced in the CMS", {"cms": ["blog/post"]}, "referenced by CMS"),
        ("3 — on a published page", {"page_hits": ["https://example.com/about"]},
         "on published page"),
        ("4 — no byte-identical backup", {"backup": False}, "no byte-identical backup"),
        ("3 — the proof was switched off", {"argv": ["--apply", "--no-check-live-pages"]},
         "--no-check-live-pages"),
    ])
    def test_any_single_unmet_condition_holds_and_deletes_nothing(
            self, monkeypatch, tmp_path, capsys, label, kw, reason):
        argv = kw.pop("argv", ["--apply"])
        rc, deleted = self._purge(monkeypatch, tmp_path, argv=argv, **kw)
        out = capsys.readouterr().out
        assert deleted == [], f"condition {label} was unmet and the asset was DELETED anyway"
        assert "HOLD" in out and reason in out, f"the hold reason must name condition {label}"
        assert rc == 0, "a safety hold is the tool working, not a failure"

    def test_condition_1_an_asset_with_no_reason_is_never_a_candidate(
            self, monkeypatch, tmp_path, capsys):
        """Condition 1 is enforced earlier than the others — at candidate
        selection — so a clean asset must not even be considered."""
        rc, deleted = self._purge(monkeypatch, tmp_path, blob=CLEAN_PNG, argv=["--apply"])
        assert deleted == [] and rc == 0
        assert "Nothing to purge" in capsys.readouterr().out

    def test_a_dry_run_deletes_nothing_even_with_every_condition_met(
            self, monkeypatch, tmp_path, capsys):
        rc, deleted = self._purge(monkeypatch, tmp_path)
        assert deleted == [] and rc == 0
        assert "WOULD" in capsys.readouterr().out

    def test_a_delete_the_api_refuses_moves_the_exit_code(self, monkeypatch, tmp_path, capsys):
        """A run in which every delete failed must not exit 0. Folding the
        failure into `held` printed "held 1" — indistinguishable from the tool
        correctly refusing — and the cron read a green exit."""
        err = wc.APIError(500, "boom", "https://api.webflow.com/v2/assets/x")
        rc, deleted = self._purge(monkeypatch, tmp_path, argv=["--apply"], delete_raises=err)
        out = capsys.readouterr().out
        assert rc == 2, "a refused delete is the tool not working"
        assert deleted == []
        assert "FAILED" in out and "held 1" not in out, \
            "a failed delete must not be reported as a safety hold"

    def test_the_hold_reason_reaches_the_log(self, monkeypatch, tmp_path):
        """The irreversible mode wrote no log at all while still accepting
        --log-jsonl, so nothing recorded WHY an asset survived a purge."""
        self._purge(monkeypatch, tmp_path, cms=["blog/post"], argv=["--apply"])
        rows = [json.loads(x) for x in (tmp_path / "purge.jsonl").read_text().splitlines()]
        assert [r["action"] for r in rows] == ["held"]
        assert rows[0]["asset_id"] == AID_HERO and rows[0]["cms_hits"] == ["blog/post"]


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

    def test_the_index_decides_when_no_entry_matches_the_url_EXACTLY(self, monkeypatch):
        """The index path, isolated from the exact-match fallback.

        test_multiimage_rewrites_only_the_indexed_entry passes an old_url whose
        id is arr[0]'s own, so the `else` branch would find the same entry by
        exact key and produce an identical result — the index was never what
        decided anything. Here the old_url carries a THIRD id (the
        WordPress-import shape: the CMS URL's id is not the site-asset id), so
        `_exact` matches nothing and `_same` matches BOTH siblings by basename.
        Without `Reference.index` the only honest answer is ref-ambiguous, and
        the re-point that the index makes possible does not happen.
        """
        items = {"col1": [{"id": "i1", "isDraft": False, "isArchived": False, "fieldData": {
            "slug": "post", "gallery": [
                {"url": f"{CDN}/{AID_HERO}_hero.png", "fileId": AID_HERO},
                {"url": f"{CDN}/{AID_G1}_hero.png", "fileId": AID_G1}]}}]}
        api = _install_fake(monkeypatch, _FakeApi(
            collections=[{"id": "col1", "slug": "blog"}],
            fields={"col1": [{"slug": "gallery", "type": "MultiImage"}]}, items=items))
        ref = wc.Reference(kind="multi", collection_id="col1", collection_slug="blog",
                           item_id="i1", item_slug="post", field_slug="gallery", index=0,
                           source_url=f"{CDN}/{AID_LOGO}_hero.png")
        out = wc.repoint_reference("tok", ref, old_url=f"{CDN}/{AID_LOGO}_hero.png",
                                   new_url=f"{CDN}/{AID_NEW}_hero.png",
                                   new_file_id=AID_NEW, apply=True)
        assert out["status"] == "repointed", (
            "the recorded index says WHICH entry this reference is — ignoring it leaves "
            f"two basename matches and no way to choose (got {out['status']})")
        arr = api.patches[0]["data"]["fieldData"]["gallery"]
        assert arr[0]["fileId"] == AID_NEW
        assert arr[1] == {"url": f"{CDN}/{AID_G1}_hero.png", "fileId": AID_G1}, \
            "the sibling is a DIFFERENT image and must be byte-identical afterwards"

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
                       '{"truncated": \n'
                       # Valid JSON, shapes the reader never declared: a non-dict
                       # `verify`, and a cms-shaped row that carries no asset_id
                       # at all. Neither may raise and neither may stop the read.
                       + json.dumps({"asset_id": "A", "new_asset_id": "B",
                                     "mode": "replace", "action": "replaced",
                                     "verify": ["clean"]}) + "\n"
                       + json.dumps({"mode": "cms", "action": "replaced",
                                     "url_key": f"{AID_HERO}_x.png",
                                     "item": "blog/post"}) + "\n"
                       + json.dumps({"asset_id": "ok2", "mode": "scan-asset", "signals": []})
                       + "\n")
        assert wc.load_known_clean(log) == {"ok", "ok2"}, \
            "a malformed row must be skipped, never raise, and never stop the read"

    def test_missing_file_is_empty_not_an_error(self, tmp_path):
        assert wc.load_known_clean(tmp_path / "nope.jsonl") == set()


class TestKnownCleanRoundTripsThroughItsProducers:
    """Every case above hand-writes the JSONL, which tests the READER against a
    shape a human BELIEVED the writer emits.

    Reader and writer are separately mutable. Renaming the key `cmd_scan`
    stamps on a scan-asset row (`asset_id`) silently disables
    ``--skip-known-clean`` for the whole CEL nightly path without moving one
    hand-written assertion, because nothing connected a log a real command
    WROTE to the reader that consumes it. These drive the producers and then
    read back exactly what they produced.
    """

    def _scan_log(self, monkeypatch, tmp_path, blobs: list[tuple[str, str, bytes]]) -> Path:
        """Run `scan --site` over `(asset_id, name, bytes)` and return its log."""
        assets = [{"id": aid, "originalFileName": f"{aid}_{name}", "displayName": name,
                   "hostedUrl": f"{CDN}/{aid}_{name}", "contentType": "image/png"}
                  for aid, name, _ in blobs]
        by_url = {f"{CDN}/{aid}_{name}": data for aid, name, data in blobs}
        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets", lambda t, s, limit=None: assets)
        monkeypatch.setattr(wc, "build_reference_index", lambda *a, **k: ({}, []))
        monkeypatch.setattr(wc, "download_image", lambda u, timeout=30: by_url[u])
        log = tmp_path / "scan.jsonl"
        wc.cmd_scan(wc.build_parser().parse_args(
            ["scan", "--site", "cel", "--quiet", "--log-jsonl", str(log)]))
        assert log.is_file(), "cmd_scan wrote no log at all"
        return log

    # ── the scan producer ────────────────────────────────────────────────
    def test_a_clean_asset_scan_credits_exactly_that_asset(self, monkeypatch, tmp_path):
        """The join itself: the id `cmd_scan` writes is the id the cache reads."""
        log = self._scan_log(monkeypatch, tmp_path, [(AID_HERO, "hero.png", CLEAN_PNG)])
        assert wc.load_known_clean(log) == {AID_HERO}

    def test_a_dirty_asset_scan_credits_nothing(self, monkeypatch, tmp_path):
        log = self._scan_log(monkeypatch, tmp_path, [(AID_HERO, "hero.png", DIRTY_PNG)])
        assert wc.load_known_clean(log) == set()

    def test_an_asset_the_walk_could_not_finish_is_not_credited(self, monkeypatch, tmp_path):
        """LOG-2, end to end. A truncated PNG yields ZERO signals — the same
        shape a clean file yields — and the walk aborted before it could reach
        the manifest. Crediting it makes the alarm self-clearing: night 1 exits
        2 with the UNKNOWN warning, night 2 filters the asset out before the
        fetch, so `unreadable` is 0, the warning vanishes and the manifest is
        still there.
        """
        broken = ip._PNG_MAGIC + b"\x00\x00\x00\x0dIHDR"
        log = self._scan_log(monkeypatch, tmp_path,
                             [(AID_HERO, "hero.png", broken), (AID_G1, "ok.png", CLEAN_PNG)])
        row = [json.loads(x) for x in log.read_text().splitlines()
               if json.loads(x).get("asset_id") == AID_HERO][0]
        assert row["container"] == "png" and row["parse_error"] and not row["signals"], (
            "premise: the producer really does emit a zero-signal row with a "
            "parse_error on a container it recognised")
        known = wc.load_known_clean(log)
        assert AID_HERO not in known, \
            "an aborted walk proves nothing — 'no signals found' is not 'no signals'"
        assert AID_G1 in known, "and the asset that WAS read must still be cached"

    def test_a_font_is_still_credited_because_its_type_is_not_a_failure(
            self, monkeypatch, tmp_path):
        """Guard the guard for the clause above. A Webflow site holds fonts and
        PDFs; those report `unsupported container`, which is a statement about
        the file TYPE. Excluding them too would evict every font from the cache
        and re-download the lot every night forever.
        """
        font = b"\x00\x01\x00\x00\x00\x0c\x00\x80\x00\x03\x00@"
        log = self._scan_log(monkeypatch, tmp_path, [(AID_LOGO, "brand.ttf", font)])
        row = [json.loads(x) for x in log.read_text().splitlines()][0]
        assert row["container"] == "unknown" and row["parse_error"], "premise"
        assert wc.load_known_clean(log) == {AID_LOGO}

    # ── the replace producer ─────────────────────────────────────────────
    def test_a_verified_replace_credits_the_NEW_id_and_only_that(
            self, monkeypatch, tmp_path):
        _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                        assets=[_asset(AID_HERO, "hero.png")], live_index={})
        log = tmp_path / "replace.jsonl"
        wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                     backup_dir=str(tmp_path), log_jsonl=str(log)))
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert [r["action"] for r in rows] == ["replaced"], "premise: the run succeeded"
        assert wc.load_known_clean(log) == {AID_NEW}, (
            "replace never touches the original — the id it proves clean is the "
            "COPY it uploaded")

    def test_a_no_verify_replace_credits_nothing(self, monkeypatch, tmp_path):
        """`--no-verify` means nobody fetched the uploaded bytes. The next scan
        confirms them for the price of one request; caching them on the word of
        the uploader is the claim this tool exists not to make."""
        _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                        assets=[_asset(AID_HERO, "hero.png")], live_index={})
        log = tmp_path / "replace.jsonl"
        wc.cmd_replace(_replace_args(apply=True, verify=False, allow_new_asset_id=True,
                                     backup_dir=str(tmp_path), log_jsonl=str(log)))
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert [r["action"] for r in rows] == ["replaced"] and rows[0]["verify"] == {}, "premise"
        assert wc.load_known_clean(log) == set()


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
        # 64 = usage error. It used to be 2, which is also "the run partially
        # failed" — so a caller could not tell a typo from a real problem.
        assert wc.main(["scan"]) == 64

    def test_verify_requires_a_target(self, capsys):
        """`verify` with nothing to verify printed nothing and exited 0 — the
        one input shape that mapped 'checked nothing' onto 'clean'."""
        assert wc.main(["verify"]) == 64
        assert "verify needs" in capsys.readouterr().err

    def test_a_usage_error_is_distinguishable_from_a_failed_run(self, tmp_path, capsys):
        """The DECISION: these three outcomes must not share a code.

        argparse's usage error, a run that found nothing to do, and a run that
        read something it could not parse are three different things for the
        cron to do, and all three answered 2 / 1 / 2.
        """
        bad = wc.main(["clean", "--local", str(tmp_path), "--nonexistent-flag"])
        empty = wc.main(["clean", "--local", str(tmp_path)])
        (tmp_path / "broken.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\xff" * 40)
        unreadable = wc.main(["clean", "--local", str(tmp_path)])
        assert len({bad, empty, unreadable}) == 3, \
            f"usage={bad} nothing-matched={empty} unreadable={unreadable} — collided"
        assert (bad, empty, unreadable) == (64, 4, 2)

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
        self.upload_folders: list[str | None] = []
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

        def fake_upload(data, name, site_id, token, parent_folder=None):
            self.uploads.append((name, len(data)))
            self.upload_folders.append(parent_folder)
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
        self.upload_folders: list[str | None] = []
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

        def fake_upload(data, name, site_id, token, parent_folder=None):
            if upload_error:
                raise upload_error
            self.uploads.append((name, len(data)))
            self.upload_folders.append(parent_folder)
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

    def test_the_log_records_which_items_were_edited(self, monkeypatch, tmp_path):
        """Without this a failed publish cannot be retried from the log. The CEL
        run re-pointed 242 items, the publish died on Webflow's 100-id cap, and
        rebuilding the list afterwards meant re-crawling the CMS and matching an
        asset id buried in a stacked URL key — because Webflow re-hosts the file
        on write and the URL we PATCH in is never the URL it stores.
        """
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        log = tmp_path / "l.jsonl"
        wc.cmd_cms(_cms_args(apply=True, check_live_pages=False,
                             backup_dir=str(tmp_path), log_jsonl=str(log)))
        done = [json.loads(x) for x in log.read_text().splitlines()]
        done = [r for r in done if r.get("action") == "replaced"]
        assert done, "fixture produced no replace"
        touched = done[0].get("touched_items")
        assert touched, "the log does not say which items were edited"
        assert all(":" in t for t in touched), "expected collection_id:item_id pairs"
        assert "col2:i2" in touched

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


class TestCmsAlsoRespectsTheDefaultLogPath:
    """The `cms` half of the same rule `TestTheDefaultLogPath` pins for `replace`.

    `DEFAULT_LOG_PATH` is `data/watermark-clean-log.jsonl` — committed, and the
    file the CEL nightly hands to `--skip-known-clean`. A dry run that appended
    to it seeded the cache from a run that uploaded nothing, so the next REAL
    run skipped assets it had never processed. `cmd_cms` carries its own copy of
    the `if args.apply or args.log_jsonl:` guard, and every other cms test
    passes an explicit `--log-jsonl` — which satisfies the second operand and
    leaves the fallback unexercised.
    """

    def test_a_cms_dry_run_writes_nothing(self, monkeypatch, tmp_path,
                                          _never_write_the_committed_log):
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        wc.cmd_cms(_cms_args(apply=False, log_jsonl="", backup_dir=str(tmp_path)))
        assert not _never_write_the_committed_log.exists(), \
            "a preview seeded the known-clean cache the next real run reads"

    def test_a_cms_apply_does_write_the_default_log(self, monkeypatch, tmp_path,
                                                    _never_write_the_committed_log):
        """Guard the guard: never writing it would satisfy the test above and
        lose the run record the whole idempotence layer is built on."""
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        wc.cmd_cms(_cms_args(apply=True, log_jsonl="", backup_dir=str(tmp_path)))
        assert [json.loads(x) for x
                in _never_write_the_committed_log.read_text().splitlines()], \
            "an --apply run must leave a record"


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

    def _page_html(self, monkeypatch, html: bytes):
        """Control what the post-write re-check sees on the live page."""
        class _R:
            def read(self): return html
            def __enter__(self): return self
            def __exit__(self, *a): return False
        monkeypatch.setattr(wc.urllib.request, "urlopen", lambda *a, **k: _R())

    def test_a_reference_still_on_the_page_after_the_write_is_reported(
            self, monkeypatch, tmp_path, capsys):
        h = _CmsHarness(monkeypatch, upload_id=AID_NEW)
        self._live(monkeypatch, self.LIVE)
        # the live page STILL shows the old filename after the write
        self._page_html(monkeypatch, f'<img src="{CDN}/{AID_HERO}_hero.png">'.encode())
        rc = wc.cmd_cms(_cms_args(apply=True, check_live_pages=True, site_url="https://example.com",
                                  backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        out = capsys.readouterr().out
        assert len(h.uploads) == 1, "the CMS half must still be done"
        assert h.repoints, "the CMS reference must still be rewritten"
        assert "STILL DIRTY" in out
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

    def test_a_cms_driven_page_is_NOT_reported_once_the_write_lands(
            self, monkeypatch, tmp_path, capsys):
        """The false positive this deferral exists to kill. `live_index` is a
        PRE-WRITE snapshot, so a page whose image comes from the CMS field this
        run just re-pointed still shows the old URL in it. Reporting from the
        snapshot flagged 18 references on a real brightvalley run that the very
        same run had already fixed, counted each as an error, and sent the
        operator to the Designer to repair nothing.
        """
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        self._live(monkeypatch, self.LIVE)
        # the live page now shows the NEW filename — the run fixed it
        self._page_html(monkeypatch, f'<img src="{CDN}/{AID_NEW}_hero.png">'.encode())
        rc = wc.cmd_cms(_cms_args(apply=True, check_live_pages=True, site_url="https://example.com",
                                  backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        out = capsys.readouterr().out
        assert "STILL DIRTY" not in out
        assert "already fixed by this run" in out
        assert rc == 0, "a run that fixed everything must not exit non-zero"

    def test_a_dry_run_still_warns_that_the_image_is_on_a_page(
            self, monkeypatch, tmp_path, capsys):
        """Deferring the check to a post-write re-fetch is correct under --apply
        and WRONG in a preview: nothing has been written, so the snapshot is the
        truth. The first version of the deferral silently removed the preview's
        most useful warning — that replacing this image will leave a
        Designer-placed copy serving the un-stripped file.
        """
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        self._live(monkeypatch, self.LIVE)
        wc.cmd_cms(_cms_args(apply=False, check_live_pages=True,
                             site_url="https://example.com",
                             backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        out = capsys.readouterr().out
        assert "ALSO on 1 published page" in out
        assert "also appear on a published page" in out, "the summary must carry it too"
        assert "This run is NOT complete" not in out, \
            "a preview has not failed at anything — that wording is for --apply"

    def test_a_dry_run_records_the_pages_in_the_log(self, monkeypatch, tmp_path):
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        self._live(monkeypatch, self.LIVE)
        log = tmp_path / "l.jsonl"
        wc.cmd_cms(_cms_args(apply=False, check_live_pages=True,
                             site_url="https://example.com",
                             backup_dir=str(tmp_path), log_jsonl=str(log)))
        row = [json.loads(x) for x in log.read_text().splitlines()][-1]
        assert row["designer_page_refs"] == ["https://example.com/about"]

    def test_a_dry_run_with_no_page_refs_says_nothing(self, monkeypatch, tmp_path, capsys):
        """Guard the guard: warning unconditionally would be the same as never."""
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        self._live(monkeypatch, {})
        wc.cmd_cms(_cms_args(apply=False, check_live_pages=True,
                             site_url="https://example.com",
                             backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert "ALSO on" not in capsys.readouterr().out

    def test_an_unreadable_page_keeps_the_flag(self, monkeypatch, tmp_path, capsys):
        """Unreadable proves nothing either way, so it must not clear the flag —
        that would turn a network blip into a clean bill of health."""
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        self._live(monkeypatch, self.LIVE)
        def boom(*a, **k):
            raise urllib.error.URLError("down")
        monkeypatch.setattr(wc.urllib.request, "urlopen", boom)
        rc = wc.cmd_cms(_cms_args(apply=True, check_live_pages=True, site_url="https://example.com",
                                  backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert "STILL DIRTY" in capsys.readouterr().out and rc == 2

    def test_the_reference_is_recorded_in_the_log(self, monkeypatch, tmp_path):
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        self._live(monkeypatch, self.LIVE)
        self._page_html(monkeypatch, f'<img src="{CDN}/{AID_HERO}_hero.png">'.encode())
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


class TestScanSummaryIsQualifiedByCoverage:
    """153 `scan-green-when-every-fetch-fails`, remainder.

    The exit code and the WARNING were fixed; the SUMMARY was not. "AI-flagged
    0" is a clean bill of health, and it was printed after reading 0 of 5
    assets — as the last thing on screen, below a warning that had scrolled.
    """

    def _run(self, monkeypatch, n_ok: int, n_fail: int, capsys):
        assets = [_asset(f"{i:024x}", f"a{i}.png") for i in range(n_ok + n_fail)]
        ok_urls = {a["hostedUrl"] for a in assets[:n_ok]}
        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets", lambda t, s, limit=None: assets)
        # cmd_scan now also walks the CMS surface; without this the test reaches
        # the real API. Empty = "this site has no CMS-only images", which keeps
        # these tests about the coverage-qualification they were written for.
        monkeypatch.setattr(wc, "build_reference_index", lambda *a, **k: ({}, []))

        def fetch(u, timeout=30):
            if u in ok_urls:
                return DIRTY_PNG
            raise urllib.error.HTTPError(u, 403, "Forbidden", {}, None)

        monkeypatch.setattr(wc, "download_image", fetch)
        rc = wc.cmd_scan(wc.build_parser().parse_args(["scan", "--site", "cel"]))
        return rc, capsys.readouterr().out

    def test_a_run_that_read_nothing_prints_no_count_at_all(self, monkeypatch, capsys):
        rc, out = self._run(monkeypatch, n_ok=0, n_fail=5, capsys=capsys)
        assert rc == 2
        assert "AI-flagged (C2PA/IPTC)  n/a" in out
        assert "this is not a clean result" in out
        assert "AI-flagged (C2PA/IPTC)   0" not in out, \
            "a clean bill of health was printed for assets that were never read"

    def test_a_partial_run_qualifies_its_count(self, monkeypatch, capsys):
        rc, out = self._run(monkeypatch, n_ok=3, n_fail=2, capsys=capsys)
        assert rc == 2
        assert "of 3 read, 2 NOT read" in out, \
            "the count must state the coverage it was measured over"

    def test_a_complete_run_reads_normally(self, monkeypatch, capsys):
        """Guard the guard: qualifying everything would be the same as
        qualifying nothing."""
        rc, out = self._run(monkeypatch, n_ok=4, n_fail=0, capsys=capsys)
        assert rc == 0
        assert "NOT read" not in out and "n/a" not in out
        assert "unreadable" not in out


@pytest.mark.skipif(Image is None, reason="Pillow not installed")
class TestLineageMatchBoundary:
    """153 `crop-defeats-hash-no-caveat`.

    The threshold comment documented only the two transforms the hash handles
    well, and the printed report asserted flatly that the command answers
    "which are AI?". Neither mentioned cropping — which defeats the match at
    1% off each edge, because a row/column difference hash over a fixed 16x16
    grid of the whole frame shifts every cell when the frame moves.

    These tests exist so the caveat cannot silently go stale: change the
    descriptor and they go red until the documented boundary is updated too.
    They assert BANDS, not exact distances — an exact number would be a
    brittle re-statement of the implementation.
    """

    @staticmethod
    def _img(seed: int = 1, w: int = 512, h: int = 512):
        rnd = random.Random(seed)
        im = Image.new("RGB", (w, h))
        px = im.load()
        for y in range(h):
            for x in range(w):
                px[x, y] = ((x * 7 + y * 3) % 256, (y * 5) % 256, (x * 11 + y * 13) % 256)
        for _ in range(40):
            cx, cy, r = rnd.randrange(w), rnd.randrange(h), rnd.randrange(10, 60)
            c = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
            for y in range(max(0, cy - r), min(h, cy + r)):
                for x in range(max(0, cx - r), min(w, cx + r)):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                        px[x, y] = c
        return im

    @staticmethod
    def _enc(im, fmt="PNG", **kw) -> bytes:
        b = io.BytesIO()
        im.save(b, fmt, **kw)
        return b.getvalue()

    def _d(self, a, b) -> int:
        return wc.fingerprint_distance(wc.perceptual_fingerprint(a), wc.perceptual_fingerprint(b))

    # ── what the caveat promises it SURVIVES ────────────────────────────────
    @pytest.mark.parametrize("label,tf", [
        ("resize 50%", lambda im: im.resize((im.width // 2, im.height // 2))),
        ("resize 200%", lambda im: im.resize((im.width * 2, im.height * 2))),
        ("aspect squash", lambda im: im.resize((im.width // 2, im.height))),
    ])
    def test_survives(self, label, tf):
        im = self._img()
        d = self._d(self._enc(im), self._enc(tf(im)))
        assert d <= wc.PHASH_MATCH_MAX, f"{label} no longer matches (d={d}); the report claims it does"

    def test_survives_lossy_re_encode(self):
        im = self._img()
        d = self._d(self._enc(im), self._enc(im, "JPEG", quality=70))
        assert d <= wc.PHASH_MATCH_MAX, f"JPEG q70 no longer matches (d={d})"

    # ── what the caveat admits it does NOT survive ──────────────────────────
    @pytest.mark.parametrize("pct", [1, 2, 5, 10])
    def test_does_not_survive_cropping(self, pct):
        """If this ever starts passing, the descriptor gained crop tolerance and
        the printed caveat is now a lie — update both together."""
        im = self._img()
        m = int(im.width * pct / 100)
        cropped = im.crop((m, m, im.width - m, im.height - m))
        d = self._d(self._enc(im), self._enc(cropped))
        assert d > wc.PHASH_MATCH_MAX, (
            f"a {pct}% crop now matches (d={d}) — the report says it does not")

    @pytest.mark.parametrize("label,tf", [
        ("mirror", lambda im: im.transpose(Image.FLIP_LEFT_RIGHT)),
        ("rotate 90", lambda im: im.transpose(Image.ROTATE_90)),
        ("rotate 2deg", lambda im: im.rotate(2)),
    ])
    def test_does_not_survive_reorientation(self, label, tf):
        im = self._img()
        d = self._d(self._enc(im), self._enc(tf(im)))
        assert d > wc.PHASH_MATCH_MAX, f"{label} now matches (d={d}) — the report says it does not"

    # ── and the separation the threshold depends on ─────────────────────────
    def test_unrelated_images_stay_far_apart(self):
        """The reason the threshold cannot simply be raised to buy crop
        tolerance: there is no gap to raise it into."""
        d = self._d(self._enc(self._img(seed=1)), self._enc(self._img(seed=99)))
        assert d >= wc.PHASH_BITS_UNRELATED_FLOOR, (
            f"unrelated images are only {d} apart; the documented separation is gone")

    def test_the_report_states_the_boundary(self, monkeypatch, capsys):
        """A caveat that lives only in a code comment protects nobody. It has to
        be in what the operator reads."""
        src = inspect.getsource(wc.cmd_lineage)
        assert "LOWER BOUND" in src and "cropping" in src
        assert "NOT evidence of human origin" in src

    def test_the_threshold_was_not_quietly_raised(self):
        """The finding's explicit instruction. A bigger number would 'fix' the
        crop misses by matching unrelated content instead."""
        assert wc.PHASH_MATCH_MAX == 40


class TestLineageCoversBothSurfaces:
    """`cmd_lineage` walked `list_assets` only.

    On brightvalley the asset list and the CMS-image set do not overlap at all
    (214 vs 164, zero shared), so "matched an AI original 59" had never included
    a single CMS image — including 13 team photos known to be AI-generated. A
    lineage answer scoped to one surface, printed without saying which, is the
    confident-partial-answer this tool exists to avoid.
    """

    def _harness(self, monkeypatch, *, assets, cms_items):
        seen = {"downloaded": []}
        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets", lambda t, s, limit=None: assets)
        _install_fake(monkeypatch, _FakeApi(
            collections=[{"id": "col2", "slug": "team"}],
            fields={"col2": [{"slug": "headshot", "type": "Image"}]},
            items=cms_items, assets=assets))
        monkeypatch.setattr(wc, "build_lineage_corpus",
                            lambda src, progress=True: ([{"path": "orig/a.png", "fp": (0, 0),
                                                          "generators": ["Higgsfield"]}], []))

        def dl(u, timeout=30):
            seen["downloaded"].append(u)
            return CLEAN_PNG

        monkeypatch.setattr(wc, "download_image", dl)
        return seen

    def test_a_cms_only_image_is_checked(self, monkeypatch, capsys):
        """The defect in one assertion: an image that exists only as a CMS
        reference must reach the matcher."""
        cms_url = f"{CDN}/{AID_BODY}_cms-only.png"
        items = {"col2": [{"id": "i2", "isDraft": False, "isArchived": False,
                           "lastPublished": "2026-01-01",
                           "fieldData": {"slug": "jane",
                                         "headshot": {"url": cms_url, "fileId": AID_BODY}}}]}
        seen = self._harness(monkeypatch, assets=[_asset(AID_HERO, "hero.png")], cms_items=items)
        wc.cmd_lineage(wc.build_parser().parse_args(["lineage", "--site", "cel", "--quiet"]))
        assert cms_url in seen["downloaded"], "the CMS-only image was never fetched"
        out = capsys.readouterr().out
        assert "1 site asset(s) + 1 CMS-only image(s)" in out

    def test_the_summary_names_which_surfaces_it_measured(self, monkeypatch, capsys):
        """A coverage number without its surface is how 59 was read as
        'the whole site' for a week."""
        self._harness(monkeypatch, assets=[_asset(AID_HERO, "hero.png")],
                      cms_items={"col2": []})
        wc.cmd_lineage(wc.build_parser().parse_args(["lineage", "--site", "cel", "--quiet"]))
        out = capsys.readouterr().out
        # The SUMMARY line specifically, not the progress line above it — the
        # summary is what gets quoted, and the first version of this test passed
        # on a mutant that stripped the surfaces from exactly that line.
        summary = [ln for ln in out.splitlines() if "images checked" in ln]
        assert summary, "no summary line at all"
        assert "site asset(s) +" in summary[0] and "CMS-only" in summary[0], \
            f"the summary does not name its surfaces: {summary[0]!r}"

    def test_an_image_in_both_surfaces_is_counted_once(self, monkeypatch):
        """Most sites DO overlap. Double-fetching would double every count."""
        url = f"{CDN}/{AID_HERO}_hero.png"
        items = {"col2": [{"id": "i2", "isDraft": False, "isArchived": False,
                           "lastPublished": "2026-01-01",
                           "fieldData": {"slug": "jane",
                                         "headshot": {"url": url, "fileId": AID_HERO}}}]}
        seen = self._harness(monkeypatch, assets=[_asset(AID_HERO, "hero.png")], cms_items=items)
        wc.cmd_lineage(wc.build_parser().parse_args(["lineage", "--site", "cel", "--quiet"]))
        assert seen["downloaded"].count(url) == 1, "the same image was fetched twice"

    def test_no_cms_says_so_rather_than_quietly_narrowing(self, monkeypatch, capsys):
        """Opting out is allowed; doing it silently is not."""
        cms_url = f"{CDN}/{AID_BODY}_cms-only.png"
        items = {"col2": [{"id": "i2", "isDraft": False, "isArchived": False,
                           "lastPublished": "2026-01-01",
                           "fieldData": {"slug": "jane",
                                         "headshot": {"url": cms_url, "fileId": AID_BODY}}}]}
        seen = self._harness(monkeypatch, assets=[_asset(AID_HERO, "hero.png")], cms_items=items)
        wc.cmd_lineage(wc.build_parser().parse_args(
            ["lineage", "--site", "cel", "--quiet", "--no-cms"]))
        assert cms_url not in seen["downloaded"]
        assert "CMS images were NOT checked" in capsys.readouterr().out

    def test_a_run_that_could_read_nothing_exits_two_and_says_so(
            self, monkeypatch, tmp_path, capsys):
        """`matched an AI original 0` on a run that fetched zero bytes is
        indistinguishable from a site with no AI in it.

        The corpus is fine, the credentials are fine, every fetch failed — and
        the summary still prints a confident zero. Only the exit code and the
        stderr warning separate 'we looked and found nothing' from 'we could
        not look'; the CEL cron reads the exit code.
        """
        self._harness(monkeypatch, assets=[_asset(AID_HERO, "hero.png"),
                                           _asset(AID_G1, "two.png")],
                      cms_items={"col2": []})

        def boom(u, timeout=30):
            raise urllib.error.HTTPError(u, 403, "Forbidden", {}, None)

        monkeypatch.setattr(wc, "download_image", boom)
        log = tmp_path / "l.jsonl"
        rc = wc.cmd_lineage(wc.build_parser().parse_args(
            ["lineage", "--site", "cel", "--quiet", "--log-jsonl", str(log)]))

        assert rc == 2, "a lineage run that read nothing must not exit 0"
        assert "UNKNOWN, not 'not AI'" in capsys.readouterr().err
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert [r["action"] for r in rows] == ["error", "error"], \
            "each unreadable asset must be named in the log, not just counted"

    def test_a_run_that_read_everything_still_exits_zero(self, monkeypatch):
        """Guard the guard: exiting 2 unconditionally would be the same as
        never exiting 2."""
        self._harness(monkeypatch, assets=[_asset(AID_HERO, "hero.png")],
                      cms_items={"col2": []})
        assert wc.cmd_lineage(wc.build_parser().parse_args(
            ["lineage", "--site", "cel", "--quiet"])) == 0

    def test_rows_record_which_surface_each_image_came_from(self, monkeypatch, tmp_path):
        cms_url = f"{CDN}/{AID_BODY}_cms-only.png"
        items = {"col2": [{"id": "i2", "isDraft": False, "isArchived": False,
                           "lastPublished": "2026-01-01",
                           "fieldData": {"slug": "jane",
                                         "headshot": {"url": cms_url, "fileId": AID_BODY}}}]}
        self._harness(monkeypatch, assets=[_asset(AID_HERO, "hero.png")], cms_items=items)
        log = tmp_path / "l.jsonl"
        wc.cmd_lineage(wc.build_parser().parse_args(
            ["lineage", "--site", "cel", "--quiet", "--log-jsonl", str(log)]))
        if log.exists():
            surfaces = {json.loads(x).get("surface") for x in log.read_text().splitlines()}
            assert surfaces <= {"asset", "cms", None}


class TestLineageCorpusProvenance:
    """`data/watermark-backup` is a FLAT shared root, so the default corpus
    silently mixes every site the tool has ever touched.

    `lineage --site cel` built a 77-image corpus of which 76 were
    brightvalley's and ZERO were CEL's. "matched an AI original 0" therefore
    meant "nothing of CEL's was available to compare against" — and read as a
    clean bill of health. It is why known AI-generated CEL blog thumbnails came
    back unflagged.
    """

    def _run(self, monkeypatch, capsys, site, corpus_paths):
        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets", lambda t, s, limit=None: [])
        monkeypatch.setattr(wc, "build_reference_index", lambda *a, **k: ({}, []))
        monkeypatch.setattr(wc, "build_lineage_corpus", lambda src, progress=True: (
            [{"path": p, "fp": (1, 1), "generators": ["Higgsfield"]} for p in corpus_paths], []))
        wc.cmd_lineage(wc.build_parser().parse_args(["lineage", "--site", site, "--quiet"]))
        return capsys.readouterr().out

    def test_a_corpus_with_none_of_this_site_says_so(self, monkeypatch, capsys):
        out = self._run(monkeypatch, capsys, "cel",
                        ["data/watermark-backup/sites/brightvalley/a.png",
                         "data/watermark-backup/sites/brightvalley/b.png"])
        assert "NONE of these originals are cel's" in out
        assert "NOT 'not AI'" in out, "the warning must name the wrong conclusion it prevents"

    def test_it_names_which_sites_did_contribute(self, monkeypatch, capsys):
        out = self._run(monkeypatch, capsys, "cel",
                        ["data/watermark-backup/sites/brightvalley/a.png"])
        assert "brightvalley=1" in out

    def test_an_own_site_corpus_does_not_warn(self, monkeypatch, capsys):
        """Guard the guard: warning always would be the same as never."""
        out = self._run(monkeypatch, capsys, "cel",
                        ["sites/cel/assets/a.png", "sites/cel/assets/b.png"])
        assert "NONE of these originals" not in out

    def test_a_mixed_corpus_still_reports_composition(self, monkeypatch, capsys):
        """Own originals present but diluted — no false alarm, but the operator
        should still see that another client's images are in the comparison."""
        out = self._run(monkeypatch, capsys, "cel",
                        ["sites/cel/a.png", "data/watermark-backup/sites/brightvalley/b.png"])
        assert "NONE of these originals" not in out
        assert "cel=1" in out and "brightvalley=1" in out


class TestReplacementsAreFiledInAFolder:
    """Webflow's Assets panel has an in-place Replace, but the Data API does not
    expose it: `update_asset` changes metadata only, and `compress_assets` — the
    one endpoint that does swap the hosted file — cannot reach a CMS-uploaded
    image at all (`get_asset` on one returns 404).

    So a replace MINTS a new asset for every CMS image, and the panel grows
    whether anyone wants it to. Deleting the new asset is not an option either:
    a deleted asset's CDN URL returns 403, which would break the very reference
    just re-pointed at it. Filing them into one folder is what remains.
    """

    def test_replace_files_uploads_into_the_folder(self, monkeypatch, tmp_path):
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                            assets=[_asset(AID_HERO, "hero.png")], live_index={})
        monkeypatch.setattr(wc, "resolve_or_create_folder", lambda t, s, n: "fold123")
        wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                     asset_folder="Metadata-Stripped",
                                     backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert h.upload_folders == ["fold123"], "the replacement was uploaded to the panel root"

    def test_cms_files_uploads_into_the_folder(self, monkeypatch, tmp_path):
        h = _CmsHarness(monkeypatch, upload_id=AID_NEW)
        monkeypatch.setattr(wc, "resolve_or_create_folder", lambda t, s, n: "fold123")
        wc.cmd_cms(_cms_args(apply=True, asset_folder="Metadata-Stripped",
                             backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert h.upload_folders == ["fold123"]

    def test_an_empty_folder_name_uploads_to_the_root(self, monkeypatch, tmp_path):
        """Opting out must actually opt out — otherwise the flag is decoration."""
        h = _CmsHarness(monkeypatch, upload_id=AID_NEW)
        monkeypatch.setattr(wc, "resolve_or_create_folder",
                            lambda t, s, n: pytest.fail("folder resolved despite empty name"))
        wc.cmd_cms(_cms_args(apply=True, asset_folder="",
                             backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))
        assert h.upload_folders == [None]

    def test_a_dry_run_creates_no_folder(self, monkeypatch, tmp_path):
        """Webflow has no API to DELETE an asset folder, so a preview must not
        leave one behind."""
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        monkeypatch.setattr(wc, "resolve_or_create_folder",
                            lambda t, s, n: pytest.fail("dry run created a folder"))
        wc.cmd_cms(_cms_args(apply=False, asset_folder="Metadata-Stripped",
                             backup_dir=str(tmp_path), log_jsonl=str(tmp_path / "l.jsonl")))

    def test_an_existing_folder_is_reused_not_duplicated(self, monkeypatch):
        calls = {"post": 0}

        def fake_req(method, url, token, data=None):
            if method == "GET" and "asset_folders" in url:
                return {"assetFolders": [{"id": "existing1", "displayName": "Metadata-Stripped"}]}
            calls["post"] += 1
            return {"id": "new1"}

        monkeypatch.setattr(wc, "rate_limited_request", fake_req)
        assert wc.resolve_or_create_folder("t", SITE_ID, "Metadata-Stripped") == "existing1"
        assert calls["post"] == 0, "a duplicate folder was created; folders cannot be deleted"

    def test_the_match_is_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(wc, "rate_limited_request", lambda m, u, t, data=None: (
            {"assetFolders": [{"id": "e1", "displayName": "metadata-stripped"}]}
            if m == "GET" else pytest.fail("created a duplicate differing only in case")))
        assert wc.resolve_or_create_folder("t", SITE_ID, "Metadata-Stripped") == "e1"

    def test_the_folder_actually_reaches_the_register_call(self, monkeypatch):
        """The tests above stub `upload_bytes` wholesale, so the folder could
        stop reaching Webflow and none of them would notice. This drives the
        real `upload_avif` and inspects the registration body it POSTs.
        """
        import avif_optimizer
        seen = {}

        def fake_req(method, url, token, data=None):
            if method == "POST" and url.endswith("/assets"):
                seen.update(data or {})
                return {"id": AID_NEW, "uploadUrl": "https://s3.example/u",
                        "uploadDetails": {}}
            # upload_avif polls GET /assets/{id} until hostedUrl appears
            return {"id": AID_NEW, "hostedUrl": f"{CDN}/{AID_NEW}_x.png"}

        monkeypatch.setattr(avif_optimizer, "rate_limited_request", fake_req)
        monkeypatch.setattr(avif_optimizer, "build_multipart_body",
                            lambda details, path: (b"", "multipart/form-data"))

        class _R:
            status = 204
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(avif_optimizer.urllib.request, "urlopen", lambda *a, **k: _R())
        avif_optimizer.upload_avif(CLEAN_PNG, "x.png", SITE_ID, "tok", parent_folder="fold123")
        assert seen.get("parentFolder") == "fold123", \
            f"the folder never reached Webflow's register call: {seen}"

        seen.clear()
        avif_optimizer.upload_avif(CLEAN_PNG, "x.png", SITE_ID, "tok")
        assert "parentFolder" not in seen, "root uploads must not send an empty parentFolder"


class TestMerchantCenterWarning:
    """Google Search Central requires the exact marker this tool removes, on
    ecommerce product images:

      "AI-generated images must contain metadata using the IPTC
       DigitalSourceType TrainedAlgorithmicMedia metadata."

    The tool cannot tell a product image from a blog image, so it warns rather
    than refuses. Before this, nothing anywhere — tool or docs — mentioned it.
    """

    def test_it_warns_by_default(self, capsys):
        wc.warn_merchant_center({}, ip.Policy(), "cel")
        out = capsys.readouterr().out
        assert "Merchant Center REQUIRES" in out
        assert "TrainedAlgorithmicMedia" in out
        assert "merchant_center" in out, "the warning must name its own off-switch"

    def test_a_site_that_sells_nothing_can_silence_it(self, capsys):
        wc.warn_merchant_center({"merchant_center": False}, ip.Policy(), "cel")
        assert capsys.readouterr().out == ""

    def test_a_policy_that_keeps_the_marker_does_not_warn(self, capsys):
        """No removal, no hazard. Warning anyway would train people to ignore it."""
        keep = ip.Policy(strip_iptc=False, strip_xmp=False)
        assert keep.wants("iptc_ai") is False, "fixture no longer models 'keep the marker'"
        wc.warn_merchant_center({}, keep, "cel")
        assert capsys.readouterr().out == ""

    def test_merchant_center_true_still_warns(self, capsys):
        """Only an explicit False silences it — a site that DOES sell must see it."""
        wc.warn_merchant_center({"merchant_center": True}, ip.Policy(), "cel")
        assert "Merchant Center REQUIRES" in capsys.readouterr().out

    def test_both_writing_commands_call_it(self):
        """A guard wired into one of the two commands that strip is half a guard."""
        for fn in (wc.cmd_replace, wc.cmd_cms):
            assert "warn_merchant_center" in inspect.getsource(fn), \
                f"{fn.__name__} strips metadata without the Merchant Center warning"


class TestPublishBatching:
    """Webflow's CMS publish endpoint caps itemIds at 100 and REJECTS the whole
    request above that — it does not truncate.

    Sending 242 in one call returned HTTP 400 on the live CEL run and left every
    one of them unpublished: the CMS held the correct stripped reference while
    every live page still served the un-stripped image. Brightvalley had passed
    only because its largest batch was 24.
    """

    def _capture(self, monkeypatch):
        sent = []
        monkeypatch.setattr(wc, "rate_limited_request",
                            lambda m, u, t, data=None: (sent.append(data["itemIds"]), {})[1])
        return sent

    def test_a_batch_over_the_cap_is_split(self, monkeypatch):
        sent = self._capture(monkeypatch)
        wc.publish_items("tok", "col1", [f"i{n}" for n in range(242)])
        assert [len(b) for b in sent] == [100, 100, 42]

    def test_no_batch_exceeds_the_cap(self, monkeypatch):
        sent = self._capture(monkeypatch)
        wc.publish_items("tok", "col1", [f"i{n}" for n in range(1000)])
        assert max(len(b) for b in sent) <= wc.PUBLISH_BATCH_MAX

    def test_every_id_is_sent_exactly_once_in_order(self, monkeypatch):
        """Batching must not drop or duplicate — a silently skipped item is an
        unpublished page that reports success."""
        sent = self._capture(monkeypatch)
        ids = [f"i{n}" for n in range(242)]
        wc.publish_items("tok", "col1", ids)
        assert [x for b in sent for x in b] == ids

    def test_a_small_batch_is_a_single_call(self, monkeypatch):
        sent = self._capture(monkeypatch)
        wc.publish_items("tok", "col1", ["a", "b", "c"])
        assert sent == [["a", "b", "c"]]

    def test_empty_makes_no_call_at_all(self, monkeypatch):
        sent = self._capture(monkeypatch)
        assert wc.publish_items("tok", "col1", []) == {}
        assert sent == []

    def test_a_failing_batch_raises_rather_than_reporting_success(self, monkeypatch):
        """Half-published is not published. The caller counts the raise as an
        error, which is what moves the exit code."""
        calls = {"n": 0}

        def flaky(m, u, t, data=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise wc.APIError(400, "too many items", "https://api.webflow.com/x")
            return {}

        monkeypatch.setattr(wc, "rate_limited_request", flaky)
        with pytest.raises(wc.APIError):
            wc.publish_items("tok", "col1", [f"i{n}" for n in range(242)])


class TestVendoredRegistryRoutesToo:
    """The CEL checkout vendors this script byte-for-byte; its registry is a
    separate, hand-maintained file.

    ``resolve_site_token`` reads ``ROOT / "sites" / "registry.json"`` and ``ROOT``
    is ``parents[1]`` of the *running* file — so in the CEL checkout the lookup
    hits the CEL mirror, not the monorepo SSOT. When the mirror carries no
    ``webflow_connection`` the lookup misses and the function falls through to
    the generic grant *silently*: nothing distinguishes "routing resolved" from
    "this site has no routing entry", and that is the checkout the nightly cron
    runs in.

    The expected env-var name is derived from the monorepo registry, never from
    the mirror under test — a check that sources its baseline from its own
    target passes vacuously.
    """

    DEV = Path(__file__).resolve().parents[3]
    CANONICAL = DEV / "webflow" / "sites" / "registry.json"
    MIRROR = DEV / "englishcollege" / "sites" / "registry.json"

    def _both_checkouts(self):
        if not self.CANONICAL.is_file() or not self.MIRROR.is_file():
            pytest.skip("needs both the monorepo and the CEL mirror checked out side by side")
        if self.CANONICAL.resolve() == self.MIRROR.resolve():
            pytest.skip("baseline and target resolved to the same file — the check would be vacuous")
        canonical = json.loads(self.CANONICAL.read_text(encoding="utf-8"))
        conn = ((canonical.get("sites") or {}).get("cel") or {}).get("webflow_connection") or {}
        env_name = (conn.get("rest_token_env") or "").strip()
        assert env_name, "monorepo SSOT lost cel.webflow_connection.rest_token_env — fix that first"
        return env_name, conn

    def test_mirror_routes_cel_instead_of_falling_through(self, monkeypatch):
        """The decision under test: routed token vs. silent generic fallback.

        Both branches return a usable string in production (CEL's routed env var
        IS the generic one), so the fallback is invisible by value. The sentinels
        make the branch observable.
        """
        env_name, _ = self._both_checkouts()
        monkeypatch.setattr(wc, "ROOT", self.MIRROR.parent.parent)
        monkeypatch.setenv(env_name, "ROUTED-BY-REGISTRY")
        monkeypatch.setattr(wc, "get_api_token", lambda *a, **k: "SILENT-FALLBACK")
        assert wc.resolve_site_token("cel") == "ROUTED-BY-REGISTRY"

    def test_mirror_names_the_same_site_id_as_the_monorepo(self):
        """A routing entry that resolves to the wrong site is worse than none."""
        _, conn = self._both_checkouts()
        mirror_conn = ((json.loads(self.MIRROR.read_text(encoding="utf-8")).get("sites") or {})
                       .get("cel") or {}).get("webflow_connection") or {}
        assert mirror_conn.get("webflow_site_id") == conn.get("webflow_site_id")


# ── the CI scrub's backups ───────────────────────────────────────────────────
_STEP_HEAD_RE = re.compile(r"^\s+-\s+(?:name|uses|run|id|if|with|env):")


def _workflow_steps(text: str):
    """Yield each GitHub Actions step as one block of text.

    A step runs from its leading ``- <key>:`` to the next one, so the block
    carries the step's ``if:``, ``with:`` and ``run:`` together — the guard and
    the body have to be read against each other here.
    """
    cur: list[str] | None = None
    for ln in text.split("\n"):
        if _STEP_HEAD_RE.match(ln):
            if cur is not None:
                yield "\n".join(cur)
            cur = [ln]
        elif cur is not None:
            cur.append(ln)
    if cur is not None:
        yield "\n".join(cur)


class TestCiScrubBackupsOutliveTheRunner:
    """`replace --apply` writes the pre-strip original of every asset it is about
    to overwrite into ``--backup-dir``. On a GitHub runner that directory is
    ephemeral: unless a step commits it or uploads it, the only copy of the bytes
    as they were before an irreversible outward write is deleted with the VM.

    The consequence is not abstract. ``cmd_purge`` requires four conditions and
    the fourth is "a byte-identical backup exists on disk" — so every asset the
    CI scrub touched is held by purge forever, and a scrub that went wrong has
    nothing to roll back to.

    The decision under test is *"do the backups leave the runner?"*, not *"is
    there an upload-artifact step?"* — committing the directory satisfies it
    equally well, and either fix must make these pass.
    """

    WORKFLOW = (Path(__file__).resolve().parents[3] / "englishcollege"
                / ".github" / "workflows" / "blog-image-optimization.yml")

    def _steps(self) -> list[str]:
        if not self.WORKFLOW.is_file():
            pytest.skip(f"the CEL workflow is not checked out at {self.WORKFLOW}")
        return list(_workflow_steps(self.WORKFLOW.read_text(encoding="utf-8")))

    def _backup_dir(self, steps: list[str]) -> str:
        """Read the directory OUT of the workflow rather than pinning a literal.

        A hard-coded ``data/watermark-backup`` would keep passing if someone
        repointed ``--backup-dir`` somewhere nothing persists.
        """
        found = [m.group(1).rstrip("/")
                 for s in steps if "watermark_cleaner.py replace" in s
                 for m in [re.search(r"--backup-dir\s+(\S+)", s)] if m]
        assert len(found) == 1, (
            f"expected exactly one scrub step naming --backup-dir, found {found!r} — "
            f"the rest of this class cannot know which directory to follow")
        return found[0]

    @staticmethod
    def _guard(step: str) -> str:
        """The step's ``if:`` expression, including a folded continuation."""
        m = re.search(r"^(\s*)if:(.*)$", step, re.M)
        if not m:
            return ""
        indent, out = m.group(1), [m.group(2)]
        for ln in step[m.end():].split("\n")[1:]:
            if ln.strip() and not ln.startswith(indent + " "):
                break               # next key at the step's own indent
            out.append(ln)
        return "\n".join(out)

    @staticmethod
    def _persists(step: str, backup: str) -> bool:
        """True only if THIS step moves `backup` off the runner — uploaded as an
        artifact or staged for the commit. Writing into it does not count."""
        here = re.compile(rf"(?:^|[\s'\"]){re.escape(backup)}/?(?:$|[\s'\"\\])", re.M)
        if "actions/upload-artifact" in step:
            m = re.search(r"^(\s*)path:(.*)$", step, re.M)
            if m:
                scalar, tail = m.group(2), []
                if scalar.strip() in ("|", ">", "|-", ">-", "|+", ">+"):
                    for ln in step[m.end():].split("\n")[1:]:
                        if ln.strip() and not ln.startswith(m.group(1) + " "):
                            break
                        tail.append(ln)
                if here.search(scalar + "\n" + "\n".join(tail)):
                    return True
        add = re.search(r"git\s+add\b((?:[^\n]*\\\n)*[^\n]*)", step)
        if add and here.search(add.group(1)):
            return True
        return False

    def test_the_scrub_backup_leaves_the_runner(self):
        steps = self._steps()
        backup = self._backup_dir(steps)
        assert [s for s in steps if self._persists(s, backup)], (
            f"nothing in blog-image-optimization.yml persists {backup}/ — the "
            f"pre-strip originals die with the runner, purge's fourth condition "
            f"(a byte-identical backup on disk) can never be met for a CI-scrubbed "
            f"asset, and a bad scrub is unrollbackable. Add it to the `git add` "
            f"list or upload it as an artifact.")

    def test_the_backups_survive_a_half_finished_scrub(self):
        """A scrub that dies part-way through has already overwritten some
        assets; those originals are precisely the ones that must be kept. A
        persistence step that only runs on success loses them exactly when they
        matter (rules/remote-write-discipline.md)."""
        steps = self._steps()
        backup = self._backup_dir(steps)
        persisting = [s for s in steps if self._persists(s, backup)]
        assert persisting, "no persistence step at all — see the test above"
        assert any("always()" in self._guard(s) for s in persisting), (
            f"every step that persists {backup}/ is conditional on the scrub "
            f"succeeding, so a partial scrub discards the originals it just "
            f"superseded. Guard it with always().")

    def test_writing_the_backups_does_not_count_as_persisting_them(self):
        """Guard the guard: if merely naming the directory satisfied `_persists`,
        the scrub step itself would pass and the two tests above would be
        vacuous — the defect they exist to catch is that the *only* step naming
        the directory is the one that writes it."""
        steps = self._steps()
        backup = self._backup_dir(steps)
        scrub = [s for s in steps if "watermark_cleaner.py replace" in s]
        assert scrub, "the scrub step disappeared from the workflow"
        assert not any(self._persists(s, backup) for s in scrub), (
            "the step that WRITES the backups is being counted as persisting "
            "them; the check is vacuous")


# ── audit 155: the known-clean cache must require POSITIVE proof ─────────────
class TestKnownCleanRequiresPositiveProof:
    """`is not False` credited two rows that prove nothing.

    A `--no-verify` replace writes ``verify: {}``, so ``{}.get("clean")`` is
    None — "not False" — and the new asset was cached as proven-clean without
    anyone ever fetching it. A shape-corrupt row crashed the reader outright,
    contradicting load_known_clean's own "costs time, never correctness".
    """

    def _row(self, tmp_path, **over):
        log = tmp_path / "log.jsonl"
        row = {"asset_id": "OLD", "new_asset_id": "NEW", "mode": "replace",
               "action": "replaced"}
        row.update(over)
        log.write_text(json.dumps(row) + "\n")
        return log

    def test_an_unverified_replace_is_not_proof(self, tmp_path):
        assert wc.load_known_clean(self._row(tmp_path, verify={})) == set(), \
            "--no-verify means nobody looked; that is not proof the upload is clean"

    def test_a_verified_replace_still_counts(self, tmp_path):
        assert wc.load_known_clean(self._row(tmp_path, verify={"clean": True})) == {"NEW"}

    def test_a_shape_corrupt_verify_costs_time_not_correctness(self, tmp_path):
        # Valid JSON, wrong shape — the one corruption the old reader did NOT
        # survive: `"clean".get` is an AttributeError, not a JSONDecodeError.
        log = tmp_path / "log.jsonl"
        log.write_text(json.dumps({"action": "replaced", "asset_id": "A",
                                   "new_asset_id": "B", "verify": "clean"}) + "\n"
                       + json.dumps({"asset_id": "ok", "mode": "scan-asset",
                                     "signals": []}) + "\n")
        assert wc.load_known_clean(log) == {"ok"}, \
            "a malformed row must be skipped, not raise, and must not stop the read"

    def test_a_keep_flag_run_does_not_seed_the_cache(self, tmp_path):
        log = tmp_path / "log.jsonl"
        log.write_text(json.dumps({"asset_id": "A", "mode": "replace",
                                   "action": "already_clean",
                                   "policy_narrowed": True}) + "\n")
        assert wc.load_known_clean(log) == set(), (
            "'carries nothing THIS policy wanted' is not 'carries nothing' — "
            "crediting it evicts a genuinely C2PA-bearing asset forever")


class TestRepointProvesTheBytesMoved:
    def _api(self, monkeypatch, items):
        return _install_fake(monkeypatch, _FakeApi(
            collections=[{"id": "col1", "slug": "blog"}],
            fields={"col1": [{"slug": "post-body", "type": "RichText"}]}, items=items))

    def _ref(self):
        return wc.Reference(kind="richtext", collection_id="col1", collection_slug="blog",
                            item_id="i1", item_slug="post", field_slug="post-body")

    def test_an_entity_encoded_src_is_actually_rewritten(self, monkeypatch):
        """`&amp;` in a rich-text src used to make the rewrite a silent no-op.

        HTMLParser hands back the DECODED src, so `str.replace` found nothing —
        but `changed` came from the MATCH, so a byte-identical PATCH went out
        and the status said "repointed".
        """
        body = f'<p>x</p><img src="{CDN}/{AID_HERO}_hero.png?w=800&amp;q=80" alt="h">'
        api = self._api(monkeypatch, {"col1": [{"id": "i1", "isDraft": False,
                                                "isArchived": False,
                                                "fieldData": {"slug": "post", "post-body": body}}]})
        out = wc.repoint_reference("tok", self._ref(), old_url=f"{CDN}/{AID_HERO}_hero.png",
                                   new_url=f"{CDN}/{AID_NEW}_hero.png",
                                   new_file_id=AID_NEW, apply=True)
        assert out["status"] == "repointed"
        patched = api.patches[0]["data"]["fieldData"]["post-body"]
        assert f"{AID_NEW}_hero.png" in patched, "the field must actually point at the new asset"
        assert patched != body, "a PATCH that changes no bytes is not a re-point"

    def test_a_field_that_would_not_change_is_not_reported_as_repointed(self, monkeypatch):
        """The image field already holds the new URL: nothing to do, and saying
        'repointed' would count it toward n_ok and hide a half-finished run."""
        items = {"col1": [{"id": "i1", "isDraft": False, "isArchived": False, "fieldData": {
            "slug": "post", "main-image": {"url": f"{CDN}/{AID_NEW}_hero.png",
                                           "fileId": AID_NEW}}}]}
        api = _install_fake(monkeypatch, _FakeApi(
            collections=[{"id": "col1", "slug": "blog"}],
            fields={"col1": [{"slug": "main-image", "type": "Image"}]}, items=items))
        ref = wc.Reference(kind="image", collection_id="col1", collection_slug="blog",
                           item_id="i1", item_slug="post", field_slug="main-image")
        out = wc.repoint_reference("tok", ref, old_url=f"{CDN}/{AID_NEW}_hero.png",
                                   new_url=f"{CDN}/{AID_NEW}_hero.png",
                                   new_file_id=AID_NEW, apply=True)
        assert out["status"] == "no-op"
        assert api.patches == [], "no bytes changed — there is nothing to PATCH"


class TestRepointReadsLiveDraftState:
    def test_the_live_value_wins_over_a_stale_index_value(self, monkeypatch):
        """The Reference is a snapshot from index-build time. Echoing its flags
        back un-archives an item somebody archived mid-run."""
        items = {"col1": [{"id": "i1", "isDraft": True, "isArchived": True, "fieldData": {
            "slug": "post", "main-image": {"url": f"{CDN}/{AID_HERO}_hero.png",
                                           "fileId": AID_HERO}}}]}
        api = _install_fake(monkeypatch, _FakeApi(
            collections=[{"id": "col1", "slug": "blog"}],
            fields={"col1": [{"slug": "main-image", "type": "Image"}]}, items=items))
        ref = wc.Reference(kind="image", collection_id="col1", collection_slug="blog",
                           item_id="i1", item_slug="post", field_slug="main-image",
                           is_draft=False, is_archived=False)   # stale: says "live"
        out = wc.repoint_reference("tok", ref, old_url=f"{CDN}/{AID_HERO}_hero.png",
                                   new_url=f"{CDN}/{AID_NEW}_hero.png",
                                   new_file_id=AID_NEW, apply=True)
        body = api.patches[0]["data"]
        assert body["isArchived"] is True, "a re-point must not un-archive an item"
        assert body["isDraft"] is True, "a re-point must not publish a draft"
        assert out["is_archived"] is True and out["is_draft"] is True, \
            "the caller's publish gate reads these — they must be the live values"


class TestMalformedSiteUrlDegradesInsteadOfCrashing:
    def test_a_scheme_less_site_url_returns_no_evidence(self):
        """`urllib.request.Request` raises ValueError, which was in none of the
        caught types — so purge died with a traceback AFTER downloading and
        scanning every asset. Degrading to 'no evidence' makes purge hold."""
        index, fetched, failed = wc.build_live_page_index("englishcollege.com", progress=False)
        assert (index, fetched, failed) == ({}, [], ["<sitemap>"])


class TestCleanOutDirKeepsFilesApart:
    def test_two_same_named_inputs_do_not_collapse(self, tmp_path):
        """`out_dir / p.name` flattened the tree: coll/a/hero.png and
        coll/b/hero.png both wrote to out/hero.png, the second silently
        overwriting the first, while the summary counted two."""
        src = tmp_path / "coll"
        (src / "a").mkdir(parents=True)
        (src / "b").mkdir(parents=True)
        a = src / "a" / "hero.png"
        b = src / "b" / "hero.png"
        # Deliberately DIFFERENT pixel data: two images that strip to identical
        # bytes could not detect an overwrite at all.
        a.write_bytes(DIRTY_PNG)
        b.write_bytes(_png([(b"caBX", C2PA_BLOB)], w=8, h=8))
        out = tmp_path / "out"
        # --backup-dir is NOT optional in a test: without it `cmd_clean` mirrors
        # into DEFAULT_BACKUP_DIR = data/watermark-backup/, the PRODUCTION tree.
        # This test alone deposited 192 files / 5.5 MB of pytest tmpdir paths
        # there and tripped the production-write ratchet on every full-suite run.
        wc.main(["clean", "--local", str(src), "--apply", "--out", str(out),
                 "--backup-dir", str(tmp_path / "bk")])
        written = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.png"))
        assert len(written) == 2, f"inputs collapsed onto one another: {written}"
        assert len({p.read_bytes() for p in out.rglob("*.png")}) == 2, \
            "two distinct images must survive as two distinct files"
        assert a.read_bytes() == DIRTY_PNG, "--out must leave the originals alone"


class TestScanAndCleanAgreeUnderTheSameFlags:
    def test_keep_c2pa_is_honoured_by_scan_too(self, tmp_path, capsys):
        """`scan` accepted the policy flags through common() and ignored them,
        so `scan --keep-c2pa` reported bytes removable that `clean --keep-c2pa`
        would never touch. Two commands, same flags, opposite conclusions."""
        f = tmp_path / "a.png"
        f.write_bytes(_png([(b"caBX", C2PA_BLOB)]))
        wc.main(["scan", "--local", str(f), "--keep-c2pa"])
        scan_out = capsys.readouterr().out
        wc.main(["clean", "--local", str(f), "--keep-c2pa"])
        clean_out = capsys.readouterr().out
        assert "already clean 1" in clean_out, "fixture broke — clean must skip it"
        assert "carry metadata       0" in scan_out, (
            "scan says the file carries removable metadata while clean, under the "
            "same flag, says it is already clean")

    def test_the_default_policy_still_sees_it(self, tmp_path, capsys):
        """Guard the guard: if scan reported 0 unconditionally the test above
        would pass on a scanner that had simply stopped working."""
        f = tmp_path / "a.png"
        f.write_bytes(_png([(b"caBX", C2PA_BLOB)]))
        wc.main(["scan", "--local", str(f)])
        assert "carry metadata       1" in capsys.readouterr().out


class TestScanLimitBoundsTheUncheckedWork:
    def test_a_second_incremental_run_advances(self, monkeypatch, tmp_path, capsys):
        """--limit went into list_assets BEFORE the known-clean filter, so an
        incremental sweep re-fetched the same first N every night and, once they
        were proven clean, scanned ZERO assets and still exited 0 green."""
        assets = [_asset(f"6a7dad834766eebcddd96d{i:02d}", f"a{i}.png") for i in range(10)]
        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets",
                            lambda t, s, limit=None: assets[:limit] if limit else assets)
        monkeypatch.setattr(wc, "download_image", lambda u, timeout=30: CLEAN_PNG)
        log = tmp_path / "l.jsonl"
        argv = ["scan", "--site", "bv", "--limit", "3", "--no-cms", "--quiet",
                "--log-jsonl", str(log), "--skip-known-clean", str(log)]
        wc.main(argv)
        first = {json.loads(x)["asset_id"] for x in log.read_text().splitlines()}
        capsys.readouterr()
        wc.main(argv)
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        second = {r["asset_id"] for r in rows} - first
        assert len(first) == 3, f"run 1 should scan 3 assets, scanned {len(first)}"
        assert len(second) == 3, (
            f"run 2 scanned {len(second)} NEW asset(s) — the limit is bounding the "
            "whole site instead of the unchecked part, so the sweep never advances")


class TestScopedCollectionsIsScopedEvidence:
    def test_a_scoped_index_refuses_rather_than_repointing_nothing(
            self, monkeypatch, tmp_path, capsys):
        """--collections narrows the reference index, which IS the evidence the
        id-change refusal decides on. Scoped to one collection, an asset
        referenced by another looked unreferenced, so the run replaced it and
        re-pointed nothing."""
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                            assets=[_asset(AID_LOGO, "nowhere.png")], live_index={})
        rc = wc.cmd_replace(_replace_args(apply=True, collections="blog",
                                          backup_dir=str(tmp_path),
                                          log_jsonl=str(tmp_path / "l.jsonl")))
        assert h.uploads == [], "a scoped run must not replace an asset it cannot vouch for"
        assert "REFUSED before upload" in capsys.readouterr().out
        assert rc == 2

    def test_an_unscoped_run_still_proceeds(self, monkeypatch, tmp_path):
        """Guard the guard: refusing always would be the same as never running."""
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                            assets=[_asset(AID_LOGO, "nowhere.png")], live_index={})
        wc.cmd_replace(_replace_args(apply=True, backup_dir=str(tmp_path),
                                     log_jsonl=str(tmp_path / "l.jsonl")))
        assert len(h.uploads) == 1


class TestRefusalReachesTheExitCode:
    def test_a_run_that_refused_everything_does_not_exit_zero(self, monkeypatch, tmp_path):
        """REFUSED was printed in the summary and appeared in no return
        expression, so a run that re-pointed nothing read as a success."""
        live = {wc._url_key(f"{CDN}/{AID_HERO}_hero.png"): ["https://example.com/about"]}
        _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                        assets=[_asset(AID_HERO, "hero.png")], live_index=live)
        rc = wc.cmd_replace(_replace_args(apply=True, backup_dir=str(tmp_path),
                                          log_jsonl=str(tmp_path / "l.jsonl")))
        assert rc == 2, "the cron reads this — a refusal is not a success"


class TestIncompleteRepointReachesTheExitCode:
    """TQ-2 — the action was asserted, the resulting exit code was not, so the
    `stats["errors"] += 1` on the incomplete branch survived mutation."""

    def test_replace_exits_non_zero_on_an_incomplete_repoint(self, monkeypatch, tmp_path):
        _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                        assets=[_asset(AID_HERO, "hero.png")], live_index={},
                        repoint_status="ref-ambiguous")
        rc = wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                          backup_dir=str(tmp_path),
                                          log_jsonl=str(tmp_path / "l.jsonl")))
        assert rc == 2, "the CMS still points at the un-stripped file — that is not success"

    def test_cms_exits_non_zero_on_an_incomplete_repoint(self, monkeypatch, tmp_path):
        _CmsHarness(monkeypatch, upload_id=AID_NEW, repoint_status="ref-ambiguous")
        rc = wc.cmd_cms(_cms_args(apply=True, backup_dir=str(tmp_path),
                                  log_jsonl=str(tmp_path / "l.jsonl")))
        assert rc == 2


class TestTheLogSurvivesAnInterrupt:
    def test_rows_for_writes_that_landed_are_already_on_disk(self, monkeypatch, tmp_path):
        """Every row was buffered and flushed once after the loop, so Ctrl-C
        after real uploads and CMS PATCHes left NO log at all — the old->new
        mapping of what had already landed was simply gone."""
        assets = [_asset(AID_HERO, "hero.png"), _asset(AID_LOGO, "other.png")]
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW, assets=assets, live_index={})
        seen: list[str] = []
        real = wc.download_image

        def boom(u, timeout=30):
            seen.append(u)
            if len(seen) > 1:
                raise KeyboardInterrupt
            return real(u, timeout=timeout)

        monkeypatch.setattr(wc, "download_image", boom)
        log = tmp_path / "l.jsonl"
        with pytest.raises(KeyboardInterrupt):
            wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                         backup_dir=str(tmp_path), log_jsonl=str(log)))
        assert len(h.uploads) == 1, "fixture did not actually land a write before the interrupt"
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert [r["action"] for r in rows] == ["replaced"], \
            "the upload that LANDED left no record of where it went"
        assert rows[0]["new_asset_id"] == AID_NEW


class TestPurgeLeavesARecord:
    """LOG-6 / PL-7 / PL-5 — purge accepted --log-jsonl, wrote nothing, folded a
    failed DELETE into `held`, and returned 0 when every delete had failed."""

    def _wire(self, monkeypatch, tmp_path, *, delete_raises=None, pages=True):
        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets", lambda t, s, limit=None: [_asset(AID_HERO, "h.png")])
        monkeypatch.setattr(wc, "download_image", lambda u, timeout=30: DIRTY_PNG)
        monkeypatch.setattr(wc, "asset_id_appears_in_cms", lambda *a, **k: {AID_HERO: []})
        monkeypatch.setattr(wc, "evidence_domains", lambda *a, **k: ["https://example.com"])
        monkeypatch.setattr(
            wc, "crawl_evidence_domains",
            lambda *a, **k: ({}, ["https://example.com/x"] if pages else [], []))

        def _del(token, aid):
            if delete_raises:
                raise delete_raises
            return {}

        monkeypatch.setattr(wc, "delete_asset", _del)
        # A byte-identical backup, so condition 4 is satisfied.
        (tmp_path / "bk").mkdir()
        (tmp_path / "bk" / f"{AID_HERO}_h.png").write_bytes(DIRTY_PNG)

    def _args(self, tmp_path, log, **over):
        a = wc.build_parser().parse_args(["purge", "--site", "bv", "--quiet"])
        a.backup_dir = str(tmp_path / "bk")
        a.log_jsonl = str(log)
        for k, v in over.items():
            assert hasattr(a, k), k
            setattr(a, k, v)
        return a

    def test_a_delete_is_recorded(self, monkeypatch, tmp_path):
        log = tmp_path / "purge.jsonl"
        self._wire(monkeypatch, tmp_path)
        rc = wc.cmd_purge(self._args(tmp_path, log, apply=True))
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert rc == 0
        assert [r["action"] for r in rows] == ["deleted"], \
            "the only irreversible mode must leave a durable record of what it removed"
        assert rows[0]["asset_id"] == AID_HERO and rows[0]["mode"] == "purge"

    def test_a_failed_delete_is_not_a_hold_and_does_not_exit_zero(self, monkeypatch, tmp_path,
                                                                  capsys):
        log = tmp_path / "purge.jsonl"
        self._wire(monkeypatch, tmp_path, delete_raises=wc.APIError(403, "forbidden", "https://x"))
        rc = wc.cmd_purge(self._args(tmp_path, log, apply=True))
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert rc == 2, "every delete failed and the run reported success"
        assert [r["action"] for r in rows] == ["delete_failed"]
        assert "DELETE FAILED        1" in capsys.readouterr().out, \
            "a failed delete counted as a safety hold — the tool not working read as it working"

    def test_disabling_the_page_check_holds_instead_of_deleting(self, monkeypatch, tmp_path,
                                                               capsys):
        """--no-check-live-pages DELETED precondition 3 rather than relaxing it:
        both hold reasons were gated on the flag, so the asset went with zero
        page evidence and nothing was printed about it."""
        log = tmp_path / "purge.jsonl"
        self._wire(monkeypatch, tmp_path)
        rc = wc.cmd_purge(self._args(tmp_path, log, apply=True, check_live_pages=False))
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert [r["action"] for r in rows] == ["held"]
        assert rc == 0
        out = capsys.readouterr().out
        assert "condition 3" in out and "unproven" in out
        assert "DELETED" not in out

    def test_a_name_matched_backup_is_still_consulted(self, monkeypatch, tmp_path, capsys):
        """PL-9 — `rglob(f"*{id}*") or rglob(name)` short-circuited: one file
        whose NAME merely contains the id suppressed the name lookup entirely,
        so a correct byte-identical backup sitting right there was never read."""
        log = tmp_path / "purge.jsonl"
        self._wire(monkeypatch, tmp_path)
        # Remove the id-named backup; leave a name-only one plus a decoy whose
        # filename contains the id but whose bytes differ.
        (tmp_path / "bk" / f"{AID_HERO}_h.png").unlink()
        (tmp_path / "bk" / "h.png").write_bytes(DIRTY_PNG)
        (tmp_path / "bk" / f"{AID_NEW}_{AID_HERO}_h.png").write_bytes(CLEAN_PNG)
        rc = wc.cmd_purge(self._args(tmp_path, log, apply=True))
        assert rc == 0
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert [r["action"] for r in rows] == ["deleted"], (
            "the decoy suppressed the name lookup and the asset was held as "
            "un-backed-up despite a byte-identical backup on disk")

    def test_the_pixel_watermark_caveat_is_in_the_summary(self, monkeypatch, tmp_path, capsys):
        log = tmp_path / "purge.jsonl"
        self._wire(monkeypatch, tmp_path)
        wc.cmd_purge(self._args(tmp_path, log))
        assert "watermark-free" in capsys.readouterr().out


class TestVerifyStatesTheClaimBoundary:
    def test_a_clean_verdict_carries_the_caveat(self, tmp_path, capsys):
        """CLEAN was the tool's last word on the file, with no mention of pixel
        watermarks — and the caveat was driven by `undetectable_watermarks`,
        which is empty after a successful strip, i.e. exactly when it matters."""
        f = tmp_path / "clean.png"
        f.write_bytes(CLEAN_PNG)
        assert wc.main(["verify", "--file", str(f)]) == 0
        out = capsys.readouterr().out
        assert "CLEAN" in out
        assert "SynthID" in out and "watermark-free" in out, \
            "a bare CLEAN reads as 'watermark-free' to anyone quoting it back"


class TestCmsSeedsTheCacheForImagesItProvedClean:
    def test_a_second_run_skips_what_the_first_proved_clean(self, monkeypatch, tmp_path):
        """cms `already_clean` rows carried no asset_id, and load_known_clean
        requires one — so the images this command proved clean (the majority on
        brightvalley) were re-downloaded on every run forever."""
        log = tmp_path / "l.jsonl"
        h1 = _CmsHarness(monkeypatch, upload_id=AID_NEW)
        monkeypatch.setattr(wc, "download_image", lambda u, timeout=30: CLEAN_PNG)
        downloads: list[str] = []
        real = wc.download_image
        monkeypatch.setattr(wc, "download_image",
                            lambda u, timeout=30: (downloads.append(u), real(u))[1])
        wc.cmd_cms(_cms_args(apply=True, backup_dir=str(tmp_path), log_jsonl=str(log)))
        assert h1.uploads == [] and downloads, "fixture: run 1 must prove the image clean"
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert rows[-1]["action"] == "already_clean"

        n_first = len(downloads)
        _CmsHarness(monkeypatch, upload_id=AID_NEW)
        monkeypatch.setattr(wc, "download_image",
                            lambda u, timeout=30: (downloads.append(u), CLEAN_PNG)[1])
        wc.cmd_cms(_cms_args(apply=True, backup_dir=str(tmp_path), log_jsonl=str(log),
                             skip_known_clean=str(log)))
        assert len(downloads) == n_first, \
            "run 2 re-downloaded an image run 1 had already proved clean"


class TestAutoPublishDoesNotShipSomeoneElsesEdits:
    ITEM_WITH_PENDING_EDITS = {"col2": [{
        "id": "i2", "isDraft": False, "isArchived": False,
        "lastPublished": "2026-01-01T00:00:00Z", "lastUpdated": "2026-02-02T00:00:00Z",
        "fieldData": {"slug": "jane",
                      "headshot": {"url": f"{CDN}/{AID_HERO}_hero.png", "fileId": AID_HERO}},
    }]}

    def test_an_item_with_unpublished_edits_is_not_queued(self, monkeypatch, tmp_path, capsys):
        """--auto-publish publishes the whole ITEM. The gate was 'has it ever
        been published?', so an item carrying somebody's unfinished Editor work
        was pushed live wholesale."""
        h = _CmsHarness(monkeypatch, upload_id=AID_NEW, items=self.ITEM_WITH_PENDING_EDITS)
        wc.cmd_cms(_cms_args(apply=True, auto_publish=True, backup_dir=str(tmp_path),
                             log_jsonl=str(tmp_path / "l.jsonl")))
        assert h.uploads, "fixture: the image must actually have been replaced"
        assert h.published == [], "an item with pending edits was published wholesale"
        assert "unpublished edits" in capsys.readouterr().out

    def test_a_fully_published_item_is_still_queued(self, monkeypatch, tmp_path):
        """Guard the guard: holding always would be the same as no --auto-publish."""
        h = _CmsHarness(monkeypatch, upload_id=AID_NEW)
        wc.cmd_cms(_cms_args(apply=True, auto_publish=True, backup_dir=str(tmp_path),
                             log_jsonl=str(tmp_path / "l.jsonl")))
        assert h.published, "nothing is ever published any more"

    def test_a_run_with_errors_publishes_nothing(self, monkeypatch, tmp_path, capsys):
        """Publishing is the irreversible half. A mixed run must not be made live."""
        # One asset succeeds (so something IS queued), a second one errors.
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW, live_index={},
                            assets=[_asset(AID_HERO, "hero.png"),
                                    _asset(AID_LOGO, "boom.png")])

        def _dl(u, timeout=30):
            if AID_LOGO in u:
                raise OSError("connection reset")
            return DIRTY_PNG

        monkeypatch.setattr(wc, "download_image", _dl)
        rc = wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                          auto_publish=True, backup_dir=str(tmp_path),
                                          log_jsonl=str(tmp_path / "l.jsonl")))
        assert rc == 2
        assert len(h.uploads) == 1, "fixture: one asset must have been replaced successfully"
        assert h.published == [], "a run that recorded errors published anyway"
        assert "NOT publishing" in capsys.readouterr().out


class TestFingerprintDescribesTheRenderedImage:
    """The hash opened the file and read it as stored, so three things that
    change nothing a viewer sees moved it right past PHASH_MATCH_MAX."""

    @pytest.fixture(autouse=True)
    def _need_pillow(self):
        pytest.importorskip("PIL")

    def _photo(self, seed: int = 3, w: int = 160, h: int = 120):
        """Smooth like a photograph, but with enough structure to clear
        MIN_FINGERPRINT_BITS — a near-flat fixture is DEGENERATE, and every
        assertion below would then be about the degeneracy guard instead."""
        from PIL import Image
        import math
        im = Image.new("RGB", (w, h))
        im.putdata([(int(128 + 110 * math.sin((x / w) * 6.0 + seed)),
                     int(128 + 110 * math.sin((y / h) * 4.8 + seed * 0.7)),
                     int(128 + 110 * math.sin(((x + y) / (w + h)) * 7.8 + seed * 1.3)))
                    for y in range(h) for x in range(w)])
        return im

    def _png(self, im, **save):
        buf = io.BytesIO()
        im.save(buf, format="PNG", **save)
        return buf.getvalue()

    def test_a_baked_in_exif_orientation_still_matches(self):
        """A derivative whose stored Orientation was applied downstream missed
        its own original by 265 bits — measured on a real repo photo with
        Orientation=5 — against a threshold of 40."""
        from PIL import Image
        im = self._photo()
        exif = Image.Exif()
        exif[0x0112] = 6                       # rotate 90 CW on display
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=92, exif=exif)
        stored = buf.getvalue()
        # What a downstream tool produces: the SAME rendered picture, with the
        # rotation baked into the pixels and no orientation tag left.
        baked = io.BytesIO()
        im.rotate(-90, expand=True).save(baked, format="JPEG", quality=92)
        d = wc.fingerprint_distance(wc.perceptual_fingerprint(stored),
                                    wc.perceptual_fingerprint(baked.getvalue()))
        assert d <= wc.PHASH_MATCH_MAX, (
            f"the same rendered image hashed {d} bits apart — the hash is reading "
            "storage order rather than what anyone sees")

    def test_the_guard_can_fail(self):
        """Guard the guard: an unrelated image must still be far away, or the
        assertion above would pass on a hash that had stopped discriminating."""
        d = wc.fingerprint_distance(wc.perceptual_fingerprint(self._png(self._photo(3))),
                                    wc.perceptual_fingerprint(self._png(self._photo(31))))
        assert d > wc.PHASH_MATCH_MAX

    def test_colour_under_full_transparency_does_not_change_the_hash(self):
        """Three PNGs with an IDENTICAL visible circle and white / black / noise
        under the alpha hashed 153-208 bits apart: two files that render
        identically were reported unrelated."""
        from PIL import Image, ImageDraw
        import random
        variants = []
        for fill in ("white", "black", "noise"):
            base = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
            if fill == "white":
                under = Image.new("RGB", (120, 120), (255, 255, 255))
            elif fill == "black":
                under = Image.new("RGB", (120, 120), (0, 0, 0))
            else:
                rnd = random.Random(7)
                under = Image.new("RGB", (120, 120))
                under.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                               for _ in range(120 * 120)])
            base.paste(under, (0, 0))
            base.putalpha(0)                       # everything invisible…
            d = ImageDraw.Draw(base)
            d.ellipse((25, 25, 95, 95), fill=(20, 90, 200, 255))   # …except this
            variants.append(self._png(base))
        fps = [wc.perceptual_fingerprint(v) for v in variants]
        worst = max(wc.fingerprint_distance(fps[i], fps[j])
                    for i in range(3) for j in range(i + 1, 3))
        assert worst <= wc.PHASH_MATCH_MAX, (
            f"identical visible content hashed {worst} bits apart — the hash is "
            "reading RGB nobody renders")
        # The PLAIN leg specifically: _autotrim flattens too, so a missing
        # composite in perceptual_hash itself hides behind the trimmed hash.
        plain = [wc.perceptual_hash(v) for v in variants]
        worst_plain = max(wc.hamming(plain[i], plain[j])
                          for i in range(3) for j in range(i + 1, 3))
        assert worst_plain <= wc.PHASH_MATCH_MAX, (
            f"the untrimmed hash alone is {worst_plain} bits apart on identical "
            "visible content")

    def test_two_animations_with_the_same_intro_frame_stay_distinct(self):
        """Frame 0 was hashed by accident of where the decoder was parked, so a
        fade-in fingerprinted its black intro: two different GIFs both hashed
        to 0 and matched at distance 0."""
        from PIL import Image
        gifs = []
        for seed in (3, 31):
            body = self._photo(seed).convert("P", palette=Image.ADAPTIVE)
            # The intro must share the body's palette, or PIL quantises every
            # later frame to the first frame's (all-black) one and the fixture
            # tests nothing but its own encoding bug.
            intro = Image.new("P", body.size, 0)
            intro.putpalette(body.getpalette())
            buf = io.BytesIO()
            intro.save(buf, format="GIF", save_all=True, append_images=[body, body])
            gifs.append(buf.getvalue())
        fps = [wc.perceptual_fingerprint(g) for g in gifs]
        assert not any(wc.fingerprint_is_degenerate(f) for f in fps), \
            "the fingerprint still describes the flat intro frame"
        assert wc.fingerprint_distance(*fps) > wc.PHASH_MATCH_MAX, \
            "two different animations fingerprint to the same thing"


class TestAutotrimPicksTheLeastDestructiveCrop:
    @pytest.fixture(autouse=True)
    def _need_pillow(self):
        pytest.importorskip("PIL")

    def test_the_largest_passing_bbox_wins_not_the_first(self):
        """`return g.crop(bb)` inside the loop took the FIRST corner past the
        30% floor. When that corner sits on CONTENT — a near-uniform tone
        reaching the frame edge — a content-driven crop beat the pad-driven one
        and cut real picture away."""
        from PIL import Image
        im = Image.new("RGB", (200, 200), (250, 250, 250))
        # A large, near-white block anchored at the top-left corner: sampling
        # (0,0) yields a bbox that excludes it, i.e. a CONTENT crop that still
        # clears the 30% floor.
        for x in range(0, 120):
            for y in range(0, 120):
                im.putpixel((x, y), (252, 252, 252))
        for x in range(60, 200):
            for y in range(60, 200):
                im.putpixel((x, y), (10, 10, 200))
        buf = io.BytesIO(); im.save(buf, format="PNG")
        first = _first_passing_bbox(im)
        largest = _largest_passing_bbox(im)
        assert first is not None and largest is not None
        assert first != largest, (
            "premise: this fixture must actually offer two different passing "
            "bboxes, or the assertion below is vacuous")
        got = wc._autotrim(Image.open(io.BytesIO(buf.getvalue()))).size
        want = (largest[2] - largest[0], largest[3] - largest[1])
        assert got == want, (
            f"_autotrim returned {got}, the FIRST passing corner's crop "
            f"{(first[2] - first[0], first[3] - first[1])} — it must take the "
            f"largest, which removes a border without ever removing content")


def _passing_bboxes(im, tol: int = 12):
    """Every corner-derived bbox that clears _autotrim's 30% floor, in order."""
    from PIL import Image, ImageChops
    g = im.convert("RGB")
    out = []
    for corner in ((0, 0), (g.width - 1, 0), (0, g.height - 1), (g.width - 1, g.height - 1)):
        bg = Image.new("RGB", g.size, g.getpixel(corner))
        mask = ImageChops.difference(g, bg).convert("L").point(lambda v: 255 if v > tol else 0)
        bb = mask.getbbox()
        if bb and (bb[2] - bb[0]) > g.width * 0.3 and (bb[3] - bb[1]) > g.height * 0.3:
            out.append(bb)
    return out


def _first_passing_bbox(im):
    got = _passing_bboxes(im)
    return got[0] if got else None


def _largest_passing_bbox(im):
    got = _passing_bboxes(im)
    return max(got, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])) if got else None


class TestPhashBitsIsDerivedAndUsed:
    @pytest.fixture(autouse=True)
    def _need_pillow(self):
        pytest.importorskip("PIL")

    def test_the_constant_describes_the_hash_it_names(self):
        """PHASH_BITS was a bare 512 with one store and zero loads, while the
        width was implied by `size=16` somewhere else — free to drift away from
        the comment block that quotes distances on a 512-bit scale."""
        from PIL import Image
        import math
        im = Image.new("RGB", (64, 64))
        im.putdata([(int(128 + 120 * math.sin(x / 5)), (x * 3) % 256, (y * 7) % 256)
                    for y in range(64) for x in range(64)])
        buf = io.BytesIO(); im.save(buf, format="PNG")
        h = wc.perceptual_hash(buf.getvalue())
        assert 0 < h.bit_length() <= wc.PHASH_BITS, \
            f"a {h.bit_length()}-bit hash under a constant claiming {wc.PHASH_BITS}"
        # …and the constant must not merely be an upper bound it never
        # approaches: a detailed image sets bits across the whole width, so a
        # PHASH_BITS that drifted away from the real hash size fails here.
        assert h.bit_length() > wc.PHASH_BITS - wc.PHASH_SIZE * 2, \
            f"a {h.bit_length()}-bit hash under a constant claiming {wc.PHASH_BITS} — " \
            "the constant no longer describes the hash it names"
        other = wc.perceptual_hash(CLEAN_PNG)
        assert wc.hamming(h, other) <= wc.PHASH_BITS
        assert wc.PHASH_BITS == 2 * wc.PHASH_SIZE * wc.PHASH_SIZE


# ── the default log path was reachable from the suite ────────────────────────
@pytest.fixture(autouse=True)
def _never_write_the_committed_log(monkeypatch, tmp_path_factory):
    """No test may append to data/watermark-clean-log.jsonl.

    `DEFAULT_LOG_PATH` had zero test coverage and zero isolation: any `--apply`
    run without an explicit --log-jsonl wrote into the repo's own committed log,
    which `--skip-known-clean` then reads. A test could seed the production
    known-clean cache.
    """
    p = tmp_path_factory.mktemp("wclog") / "default-log.jsonl"
    monkeypatch.setattr(wc, "DEFAULT_LOG_PATH", p)
    return p


class TestTheDefaultLogPath:
    def test_apply_without_an_explicit_log_still_records(
            self, monkeypatch, tmp_path, _never_write_the_committed_log):
        _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                        assets=[_asset(AID_HERO, "hero.png")], live_index={})
        wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                     backup_dir=str(tmp_path), log_jsonl=""))
        rows = [json.loads(x) for x in
                _never_write_the_committed_log.read_text().splitlines()]
        assert [r["action"] for r in rows] == ["replaced"]

    def test_a_dry_run_without_an_explicit_log_writes_nothing(
            self, monkeypatch, tmp_path, _never_write_the_committed_log):
        """load_known_clean reads that file — a preview must never seed it."""
        _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                        assets=[_asset(AID_HERO, "hero.png")], live_index={})
        wc.cmd_replace(_replace_args(backup_dir=str(tmp_path), log_jsonl=""))
        assert not _never_write_the_committed_log.exists()


class TestLineageRowsShareOneEnvelope:
    def _wire(self, monkeypatch, tmp_path, *, corpus_ok=True):
        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets", lambda t, s, limit=None: [_asset(AID_HERO, "h.png")])
        monkeypatch.setattr(wc, "build_reference_index", lambda *a, **k: ({}, []))
        monkeypatch.setattr(
            wc, "build_lineage_corpus",
            lambda srcs, progress=True: ([{"path": f"sites/cel/x.png", "fp": (1, 1),
                                           "generators": ["gpt-image"]}], []))

        def boom(u, timeout=30):
            raise OSError("connection reset")

        monkeypatch.setattr(wc, "download_image", boom)

    def test_the_fetch_error_row_carries_ts_and_mode_like_every_other(
            self, monkeypatch, tmp_path):
        """The error row omitted ts, mode and site while carrying an asset_id —
        the only lineage row that could not be filtered by mode, and one key
        away from being read as proof of cleanliness."""
        self._wire(monkeypatch, tmp_path)
        log = tmp_path / "l.jsonl"
        a = wc.build_parser().parse_args(["lineage", "--site", "cel", "--quiet",
                                          "--log-jsonl", str(log)])
        wc.cmd_lineage(a)
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert rows, "fixture produced no rows"
        for r in rows:
            assert "ts" in r and r.get("mode") == "lineage", \
                f"row off-schema: {sorted(r)}"
        assert wc.load_known_clean(log) == set(), \
            "an error row must never be read as proof of anything"


class TestLineageDoesNotCallAnUnreadableFileClean:
    @pytest.fixture(autouse=True)
    def _need_pillow(self):
        pytest.importorskip("PIL")

    def test_an_unparseable_match_is_reported_as_unknown(self, monkeypatch, tmp_path, capsys):
        """`has_meta = any(s.removable …)` is a two-way split: a file Pillow can
        decode but ip.scan cannot read has no signals AND no proof of
        cleanliness, and was printed 'already clean'."""
        from PIL import Image
        import math
        im = Image.new("RGB", (160, 120))
        im.putdata([(int(128 + 110 * math.sin((x / 160) * 6.0)),
                     int(128 + 110 * math.sin((y / 120) * 4.8)),
                     int(128 + 110 * math.sin(((x + y) / 280) * 7.8)))
                    for y in range(120) for x in range(160)])
        buf = io.BytesIO(); im.save(buf, format="PNG")
        good = buf.getvalue()
        # Same pixels, but the PNG chunk walk aborts: ip.scan reports a
        # parse_error with zero signals.
        broken = good[:-12] + b"\xff" * 12

        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets", lambda t, s, limit=None: [_asset(AID_HERO, "h.png")])
        monkeypatch.setattr(wc, "build_reference_index", lambda *a, **k: ({}, []))
        monkeypatch.setattr(wc, "download_image", lambda u, timeout=30: broken)
        monkeypatch.setattr(
            wc, "build_lineage_corpus",
            lambda srcs, progress=True: ([{"path": "sites/cel/orig.png",
                                           "fp": wc.perceptual_fingerprint(good),
                                           "generators": ["gpt-image"]}], []))
        assert ip.scan(broken).parse_error, "fixture: the walk must actually abort"

        a = wc.build_parser().parse_args(["lineage", "--site", "cel", "--quiet"])
        wc.cmd_lineage(a)
        out = capsys.readouterr().out
        assert "AI-DERIVED" in out, "fixture: the match must actually happen"
        assert "already clean" not in out, \
            "a file whose structure could not be read was reported metadata-clean"
        assert "COULD NOT BE READ" in out

    def test_a_residue_only_match_is_not_reported_clean(self, monkeypatch, capsys):
        """The other half of the same defect: `any(s.removable …)` reads
        STRUCTURAL signals only, so a `trainedAlgorithmicMedia` string the byte
        backstop finds outside any declared record scored zero signals and was
        printed 'already clean' — on a file `verify` calls DIRTY-AI."""
        from PIL import Image
        import math
        im = Image.new("RGB", (160, 120))
        im.putdata([(int(128 + 110 * math.sin((x / 160) * 6.0)),
                     int(128 + 110 * math.sin((y / 120) * 4.8)),
                     int(128 + 110 * math.sin(((x + y) / 280) * 7.8)))
                    for y in range(120) for x in range(160)])
        buf = io.BytesIO(); im.save(buf, format="PNG")
        good = buf.getvalue()
        residue_only = good + (b"http://cv.iptc.org/newscodes/digitalsourcetype/"
                               b"trainedAlgorithmicMedia")
        rep = ip.scan(residue_only)
        assert not rep.parse_error and not rep.signals, \
            "fixture: the structural walk must find NOTHING, which is the whole point"
        assert wc.verdict(residue_only)[0] == "DIRTY-AI"

        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets", lambda t, s, limit=None: [_asset(AID_HERO, "h.png")])
        monkeypatch.setattr(wc, "build_reference_index", lambda *a, **k: ({}, []))
        monkeypatch.setattr(wc, "download_image", lambda u, timeout=30: residue_only)
        monkeypatch.setattr(
            wc, "build_lineage_corpus",
            lambda srcs, progress=True: ([{"path": "sites/cel/orig.png",
                                           "fp": wc.perceptual_fingerprint(good),
                                           "generators": ["gpt-image"]}], []))
        wc.cmd_lineage(wc.build_parser().parse_args(["lineage", "--site", "cel", "--quiet"]))
        out = capsys.readouterr().out
        assert "AI-DERIVED" in out, "fixture: the match must actually happen"
        assert "HAS METADATA" in out and "already clean" not in out, \
            "an AI marker the byte backstop found was reported as metadata-clean"


class TestUnreachablePagesAreNamed:
    def test_the_failing_urls_are_printed_not_just_counted(self, monkeypatch, capsys):
        """purge's own remedy — 'resolve the reason and re-run' — is not
        actionable when the reason is a bare count."""
        import io as _io
        base = "https://example.com"
        pages = {f"{base}/sitemap.xml":
                 f"<urlset><url><loc>{base}/ok</loc></url>"
                 f"<url><loc>{base}/gone</loc></url></urlset>",
                 f"{base}/ok": "<html></html>"}

        def fake_open(req, timeout=None):
            u = req.full_url if hasattr(req, "full_url") else req
            if u not in pages:
                raise urllib.error.HTTPError(u, 404, "nope", {}, None)
            return _io.BytesIO(pages[u].encode())

        monkeypatch.setattr(wc.urllib.request, "urlopen", fake_open)
        _index, fetched, failed = wc.build_live_page_index(base, progress=False)
        assert fetched == [f"{base}/ok"] and failed == [f"{base}/gone"]
        assert f"{base}/gone" in capsys.readouterr().out, \
            "the operator was told a COUNT of unreadable pages, never which ones"


class TestPaginateAnnotationIsAType:
    def test_url_for_resolves_to_a_type_not_the_builtin(self):
        """`url_for: "callable"` resolved to the builtin FUNCTION under
        typing.get_type_hints, so any typing pass reads the contract wrong."""
        import typing
        hints = typing.get_type_hints(wc._paginate)
        assert hints["url_for"] is not callable, \
            "the annotation is the builtin `callable`, not a type"


class TestReplaceAutoPublishAlsoRespectsPendingEdits:
    """The same gate exists in `replace`; without its own test the cms one
    locked only half the behaviour."""

    def _ref(self, **over):
        base = dict(kind="image", collection_id="col1", collection_slug="blog",
                    item_id="i1", item_slug="post", field_slug="main-image",
                    source_url=f"{CDN}/{AID_HERO}_hero.png", was_published=True,
                    last_published="2026-01-01T00:00:00Z")
        base.update(over)
        return wc.Reference(**base)

    def _run(self, monkeypatch, tmp_path, ref):
        h = _ReplaceHarness(monkeypatch, upload_id=AID_NEW,
                            assets=[_asset(AID_HERO, "hero.png")], live_index={})
        monkeypatch.setattr(wc, "build_reference_index",
                            lambda *a, **k: ({wc._url_key(ref.source_url): [ref]}, []))
        wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True,
                                     auto_publish=True, backup_dir=str(tmp_path),
                                     log_jsonl=str(tmp_path / "l.jsonl")))
        return h

    def test_pending_edits_are_not_published(self, monkeypatch, tmp_path, capsys):
        h = self._run(monkeypatch, tmp_path,
                      self._ref(last_updated="2026-02-02T00:00:00Z"))
        assert len(h.uploads) == 1, "fixture: the replace itself must have happened"
        assert h.published == [], "an item with unpublished edits was pushed live wholesale"
        assert "unpublished edits" in capsys.readouterr().out

    def test_a_settled_item_is_still_published(self, monkeypatch, tmp_path):
        """Guard the guard: holding always is the same as no --auto-publish."""
        h = self._run(monkeypatch, tmp_path,
                      self._ref(last_updated="2025-12-01T00:00:00Z"))
        assert h.published, "nothing is ever published any more"


class TestCmsDoesNotPublishAMixedRun:
    ITEMS = {"col2": [
        {"id": "i2", "isDraft": False, "isArchived": False, "lastPublished": "2026-01-01",
         "fieldData": {"slug": "jane",
                       "headshot": {"url": f"{CDN}/{AID_HERO}_hero.png", "fileId": AID_HERO}}},
        {"id": "i3", "isDraft": False, "isArchived": False, "lastPublished": "2026-01-01",
         "fieldData": {"slug": "bob",
                       "headshot": {"url": f"{CDN}/{AID_LOGO}_boom.png", "fileId": AID_LOGO}}},
    ]}

    def test_an_errored_run_publishes_nothing(self, monkeypatch, tmp_path, capsys):
        """Publishing is the irreversible half of the command. A run in which
        one image failed must not push the other half live and exit having
        made a partial state permanent."""
        h = _CmsHarness(monkeypatch, upload_id=AID_NEW, items=self.ITEMS)

        def _dl(u, timeout=30):
            if AID_LOGO in u:
                raise OSError("connection reset")
            return DIRTY_PNG

        monkeypatch.setattr(wc, "download_image", _dl)
        rc = wc.cmd_cms(_cms_args(apply=True, auto_publish=True, backup_dir=str(tmp_path),
                                  log_jsonl=str(tmp_path / "l.jsonl")))
        assert rc == 2
        assert len(h.uploads) == 1, "fixture: one image must have been replaced successfully"
        assert h.published == [], "a run that recorded errors published anyway"
        assert "NOT publishing" in capsys.readouterr().out


class TestATruncatedBodyIsOneAssetNotTheWholeRun:
    def test_an_incomplete_read_is_logged_not_fatal(self, monkeypatch, tmp_path, capsys):
        """`http.client.IncompleteRead`'s MRO is HTTPException -> Exception, NOT
        OSError, so it was in none of the caught types: one CDN truncating one
        body aborted the entire nightly sweep with a traceback."""
        monkeypatch.setattr(wc, "load_site_config", lambda s: {"webflow_site_id": SITE_ID})
        monkeypatch.setattr(wc, "resolve_site_token", lambda s, t=None: "tok")
        monkeypatch.setattr(wc, "list_assets", lambda t, s, limit=None: [_asset(AID_HERO, "h.png")])

        def _boom(url, timeout=30):
            raise http.client.IncompleteRead(b"half")

        monkeypatch.setattr(wc, "fetch_and_scan", _boom)
        rc = wc.main(["scan", "--site", "bv", "--no-cms", "--quiet"])
        out = capsys.readouterr()
        assert rc == 2, "an unreadable asset must not exit 0"
        assert "ERROR" in out.out and "IncompleteRead" in out.out
        assert "UNKNOWN, not clean" in out.err


class TestTheGenericTokenFallbackIsLoud:
    @pytest.fixture
    def fake_repo(self, tmp_path, monkeypatch):
        (tmp_path / "sites").mkdir()
        (tmp_path / "sites" / "registry.json").write_text(json.dumps({
            "sites": {"cel": {"webflow_connection": {"rest_token_env": "WEBFLOW_API_TOKEN"}},
                      "altus": {}}}))
        monkeypatch.setattr(wc, "ROOT", tmp_path)
        monkeypatch.setattr(wc, "get_api_token", lambda *a, **k: "generic")
        return tmp_path

    def test_a_site_with_no_token_of_its_own_says_so(self, fake_repo, capsys):
        """The CEL grant has no authority on another site, so the run 404s on
        every asset. Silently handing it back turned a named config error into
        an unexplained stack trace."""
        assert wc.resolve_site_token("altus") == "generic"
        err = capsys.readouterr().err
        assert "altus" in err and "rest_token_env" in err

    def test_cel_itself_is_not_warned_about(self, fake_repo, capsys):
        """Guard the guard: warning always would be the same as never."""
        wc.resolve_site_token("cel")
        assert capsys.readouterr().err == ""


class TestReplaceLimitBoundsTheUncheckedWork:
    def test_a_second_incremental_run_advances(self, monkeypatch, tmp_path):
        """Same ordering defect as `scan`: --limit went into list_assets before
        the known-clean / superseded filters, so once the first N were handled
        an incremental run examined zero assets and exited 0."""
        assets = [_asset(f"6a7dad834766eebcddd96d{i:02d}", f"a{i}.png") for i in range(6)]
        log = tmp_path / "l.jsonl"
        h1 = _ReplaceHarness(monkeypatch, upload_id=AID_NEW, assets=assets, live_index={})
        wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True, limit=2,
                                     backup_dir=str(tmp_path), log_jsonl=str(log)))
        first = {r["asset_id"] for r in
                 (json.loads(x) for x in log.read_text().splitlines())}
        assert len(h1.uploads) == 2 and len(first) == 2

        h2 = _ReplaceHarness(monkeypatch, upload_id=AID_G1, assets=assets, live_index={})
        wc.cmd_replace(_replace_args(apply=True, allow_new_asset_id=True, limit=2,
                                     backup_dir=str(tmp_path), log_jsonl=str(log),
                                     skip_known_clean=str(log)))
        assert len(h2.uploads) == 2, (
            f"run 2 replaced {len(h2.uploads)} asset(s) — the limit is bounding the "
            "whole site instead of the unchecked part, so the sweep never advances")
        second = {r["asset_id"] for r in
                  (json.loads(x) for x in log.read_text().splitlines())} - first
        assert len(second) == 2 and not (second & first)
