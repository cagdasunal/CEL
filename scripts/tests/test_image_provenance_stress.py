"""Stress + fuzz suite for scripts/image_provenance.py.

Where test_image_provenance.py asserts that the documented cases behave, this
file attacks the module: random mutation, hostile structure, pathological size,
and repetition at scale. The bar is not "produces the right answer" — it is
**never silently produces a wrong one**.

Three invariants are checked everywhere, on every input:

  I1  ``scan()`` never raises. Malformed input yields a Report with parse_error.
  I2  ``strip()`` either returns a file that passes lossless verification and
      carries no removable signal, or raises ProvenanceError. There is no third
      outcome — in particular it never returns a corrupt file.
  I3  ``strip()`` is idempotent and never inflates a file beyond the small,
      bounded orientation re-emission.

Runtime target: the whole file under ~30s. Fuzz iteration counts are set by
STRESS_ITERATIONS so CI can turn them up without an edit.
"""
from __future__ import annotations

import os
import random
import struct
import sys
import time
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import image_provenance as ip  # noqa: E402
from image_provenance import ProvenanceError  # noqa: E402

ITERATIONS = int(os.environ.get("STRESS_ITERATIONS", "300"))
SEED = int(os.environ.get("STRESS_SEED", "20260822"))


# ── builders ─────────────────────────────────────────────────────────────────
def _png_chunk(t: bytes, p: bytes) -> bytes:
    return struct.pack(">I", len(p)) + t + p + struct.pack(">I", zlib.crc32(t + p) & 0xFFFFFFFF)


def png(chunks=(), w=8, h=8) -> bytes:
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(sum(([x * 7 % 256, y * 11 % 256, 90] for x in range(w)), []))
                   for y in range(h))
    out = ip._PNG_MAGIC + _png_chunk(b"IHDR", ihdr)
    for t, p in chunks:
        out += _png_chunk(t, p)
    return out + _png_chunk(b"IDAT", zlib.compress(raw)) + _png_chunk(b"IEND", b"")


def jpeg(segments=()) -> bytes:
    def seg(m, p):
        return b"\xff" + bytes([m]) + struct.pack(">H", len(p) + 2) + p
    out = b"\xff\xd8" + seg(0xE0, b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00")
    for m, p in segments:
        out += seg(m, p)
    out += seg(0xDB, b"\x00" + bytes(range(1, 65)))
    out += seg(0xC0, b"\x08\x00\x08\x00\x08\x01\x01\x11\x00")
    out += seg(0xC4, b"\x00" + bytes([0] * 16) + b"\x00")
    out += seg(0xDA, b"\x01\x01\x00\x00\x3f\x00")
    return out + b"\xfe\xed\xfa\xce\xde\xad\xbe\xef" + b"\xff\xd9"


def webp(chunks=(), flags=0) -> bytes:
    def ch(f, p):
        return f + struct.pack("<I", len(p)) + p + (b"\x00" if len(p) & 1 else b"")
    body = b""
    if flags or chunks:
        body += ch(b"VP8X", bytes([flags, 0, 0, 0]) + (7).to_bytes(3, "little") + (7).to_bytes(3, "little"))
    body += ch(b"VP8 ", b"\x00" * 24)
    for f, p in chunks:
        body += ch(f, p)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


def gif(comment=None, app=None) -> bytes:
    out = b"GIF89a" + struct.pack("<HH", 4, 4) + bytes([0xF0, 0, 0]) + bytes([0, 0, 0, 255, 255, 255])
    if comment is not None:
        out += b"\x21\xfe" + bytes([len(comment)]) + comment + b"\x00"
    if app is not None:
        out += b"\x21\xff\x0b" + app.ljust(11, b"\x00")[:11] + b"\x03\x01\x00\x00\x00"
    out += b"\x2c" + struct.pack("<HHHH", 0, 0, 4, 4) + b"\x00" + b"\x02\x02\x44\x01\x00" + b"\x3b"
    return out


def svg(meta=b"") -> bytes:
    block = b"<metadata>" + meta + b"</metadata>" if meta else b""
    return (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8">'
            + block + b'<rect width="8" height="8"/></svg>')


C2PA = (b"jumb jumdc2pa c2pa.actions.v2 gpt-image digitalSourceType "
        b"http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia "
        b"c2pa.watermarked.unbound")

SEEDS: list[tuple[str, bytes]] = [
    ("png-clean", png()),
    ("png-c2pa", png([(b"caBX", C2PA)])),
    ("png-many", png([(b"caBX", C2PA), (b"tEXt", b"Software\x00Midjourney"),
                      (b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00<x:xmpmeta/>"),
                      (b"tIME", b"\x07\xe9\x08\x16\x0c\x00\x00"), (b"zZzZ", b"unknown")])),
    ("jpeg-clean", jpeg()),
    ("jpeg-c2pa", jpeg([(0xEB, b"JP\x00\x00" + C2PA)])),
    ("jpeg-many", jpeg([(0xE1, b"Exif\x00\x00MM\x00*\x00\x00\x00\x08" + b"\x00" * 20),
                        (0xE1, b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta/>"),
                        (0xED, b"Photoshop 3.0\x008BIM"), (0xFE, b"a comment"),
                        (0xEB, b"JP\x00\x00" + C2PA)])),
    ("webp-clean", webp()),
    ("webp-meta", webp([(b"EXIF", b"II*\x00abcd"), (b"XMP ", b"<x:xmpmeta/>"),
                        (b"C2PA", C2PA)],
                       flags=ip._WEBP_VP8X_EXIF | ip._WEBP_VP8X_XMP)),
    ("gif-clean", gif()),
    ("gif-meta", gif(comment=b"OpenAI", app=b"C2PA_GIF")),
    ("svg-clean", svg()),
    ("svg-meta", svg(b"<c2pa:manifest>" + C2PA + b"</c2pa:manifest>")),
]


def _assert_invariants(name: str, data: bytes) -> str:
    """I1+I2+I3 on one blob. Returns the outcome for tallying."""
    rep = ip.scan(data)                                   # I1: must not raise
    assert isinstance(rep, ip.Report)

    try:
        res = ip.strip(data)
    except ProvenanceError:
        return "refused"                                  # I2: loud failure is allowed
    except Exception as e:                                # noqa: BLE001 — that's the point
        pytest.fail(f"{name}: strip() raised {type(e).__name__} instead of ProvenanceError: {e}")

    assert res.clean, f"{name}: removable signal survived: {[s.kind for s in res.after.signals]}"
    ok, note = ip.verify_lossless(data, res.data)
    assert ok, f"{name}: {note}"
    assert ip.sniff(res.data) == ip.sniff(data), f"{name}: container changed"
    assert len(res.data) <= len(data) + 64, f"{name}: file grew by {len(res.data) - len(data)}"

    again = ip.strip(res.data).data                       # I3
    assert again == res.data, f"{name}: strip is not idempotent"
    return "stripped" if res.changed else "unchanged"


# ── fuzz: random byte mutation ───────────────────────────────────────────────
class TestByteMutationFuzz:
    """Flip, insert and delete bytes in valid files. Nothing may crash or lie."""

    def test_single_byte_flips(self):
        rng = random.Random(SEED)
        outcomes = {"stripped": 0, "unchanged": 0, "refused": 0}
        for i in range(ITERATIONS):
            name, seed = SEEDS[i % len(SEEDS)]
            b = bytearray(seed)
            for _ in range(rng.randint(1, 4)):
                b[rng.randrange(len(b))] = rng.randrange(256)
            outcomes[_assert_invariants(f"{name}#flip{i}", bytes(b))] += 1
        # A mutation corpus that never once reaches the stripper is not testing it.
        assert outcomes["stripped"] + outcomes["unchanged"] > 0, \
            f"every mutant was refused — the fuzzer is not exercising strip(): {outcomes}"

    def test_truncation_at_every_depth(self):
        for name, seed in SEEDS:
            for cut in range(1, len(seed), max(1, len(seed) // 24)):
                _assert_invariants(f"{name}#trunc{cut}", seed[:cut])

    def test_random_insertions(self):
        rng = random.Random(SEED + 1)
        for i in range(ITERATIONS // 2):
            name, seed = SEEDS[i % len(SEEDS)]
            at = rng.randrange(len(seed))
            junk = bytes(rng.randrange(256) for _ in range(rng.randint(1, 24)))
            _assert_invariants(f"{name}#ins{i}", seed[:at] + junk + seed[at:])

    def test_random_deletions(self):
        rng = random.Random(SEED + 2)
        for i in range(ITERATIONS // 2):
            name, seed = SEEDS[i % len(SEEDS)]
            at = rng.randrange(len(seed))
            n = rng.randint(1, 16)
            _assert_invariants(f"{name}#del{i}", seed[:at] + seed[at + n:])

    def test_pure_random_noise_is_never_mistaken_for_an_image(self):
        rng = random.Random(SEED + 3)
        for _ in range(200):
            blob = bytes(rng.randrange(256) for _ in range(rng.randint(0, 512)))
            rep = ip.scan(blob)
            assert isinstance(rep, ip.Report)
            if rep.container == "unknown":
                with pytest.raises(ProvenanceError):
                    ip.strip(blob)

    def test_magic_prefix_with_garbage_body(self):
        """The worst case: looks like a real container, is not one."""
        rng = random.Random(SEED + 4)
        prefixes = [ip._PNG_MAGIC, b"\xff\xd8\xff", b"RIFF\x10\x00\x00\x00WEBP",
                    b"GIF89a", b"\x00\x00\x00\x20ftypavif"]
        for i in range(ITERATIONS):
            pre = prefixes[i % len(prefixes)]
            body = bytes(rng.randrange(256) for _ in range(rng.randint(8, 256)))
            _assert_invariants(f"magic{i}", pre + body)


# ── hostile structure ────────────────────────────────────────────────────────
class TestHostileStructure:
    def test_declared_length_near_int_max(self):
        for declared in (0x7FFFFFFF, 0xFFFFFFFF, 0x80000000):
            good = png([(b"caBX", C2PA)])
            bad = bytearray(good)
            off = good.index(b"caBX") - 4
            bad[off:off + 4] = struct.pack(">I", declared)
            rep = ip.scan(bytes(bad))
            assert rep.parse_error, f"length {declared:#x} must be refused"

    def test_zero_length_everything(self):
        data = png([(b"caBX", b""), (b"tEXt", b""), (b"iTXt", b""), (b"zTXt", b"")])
        _assert_invariants("zero-len", data)

    def test_thousands_of_metadata_chunks(self):
        """A file whose metadata vastly outnumbers its pixels."""
        chunks = [(b"tEXt", f"k{i}\x00OpenAI".encode()) for i in range(3000)]
        data = png(chunks)
        t0 = time.monotonic()
        res = ip.strip(data)
        assert time.monotonic() - t0 < 10, "3000 chunks should not take 10s"
        assert res.clean and b"OpenAI" not in res.data

    def test_deeply_nested_isobmff_boxes(self):
        """Nested containers must not recurse without bound."""
        inner = b""
        for _ in range(400):
            inner = struct.pack(">I", len(inner) + 8) + b"meta" + inner
        ftyp = struct.pack(">I", 24) + b"ftyp" + b"avif" + struct.pack(">I", 0) + b"avif" + b"mif1"
        rep = ip.scan(ftyp + inner)
        assert isinstance(rep, ip.Report)

    def test_isobmff_box_claiming_zero_size_in_a_loop(self):
        """size==0 means 'to EOF'; a parser that treats it as 'advance 0' hangs."""
        ftyp = struct.pack(">I", 24) + b"ftyp" + b"avif" + struct.pack(">I", 0) + b"avif" + b"mif1"
        data = ftyp + (struct.pack(">I", 0) + b"free") * 50
        t0 = time.monotonic()
        ip.scan(data)
        assert time.monotonic() - t0 < 5, "zero-size boxes must terminate the walk"

    def test_webp_chunk_size_lies_in_both_directions(self):
        for delta in (-4, +4, +1000, -1000):
            good = webp([(b"EXIF", b"q" * 16)], flags=ip._WEBP_VP8X_EXIF)
            bad = bytearray(good)
            i = good.index(b"EXIF")
            size = struct.unpack("<I", bad[i + 4:i + 8])[0]
            bad[i + 4:i + 8] = struct.pack("<I", max(0, size + delta))
            _assert_invariants(f"webp-lie{delta}", bytes(bad))

    def test_jpeg_without_terminating_eoi(self):
        data = jpeg([(0xEB, b"JP\x00\x00" + C2PA)])[:-2]
        _assert_invariants("jpeg-no-eoi", data)

    def test_png_without_iend(self):
        good = png([(b"caBX", C2PA)])
        data = good[:good.rindex(b"IEND") - 4]
        rep = ip.scan(data)
        assert rep.parse_error

    def test_decompression_bomb_in_ztxt_is_bounded(self):
        """A zTXt chunk that expands enormously must not exhaust memory."""
        bomb = zlib.compress(b"\x00" * (40 * 1024 * 1024))
        data = png([(b"zTXt", b"k\x00\x00" + bomb)])
        t0 = time.monotonic()
        res = ip.strip(data)
        assert time.monotonic() - t0 < 15
        assert res.clean and b"zTXt" not in res.data

    def test_gif_subblock_chain_without_terminator(self):
        data = bytearray(gif(comment=b"OpenAI"))
        data[-1] = 0xFF                                   # clobber the trailer
        _assert_invariants("gif-noterm", bytes(data))

    def test_svg_unclosed_metadata_tag(self):
        data = b'<svg xmlns="http://www.w3.org/2000/svg"><metadata>oops<rect/></svg>'
        _assert_invariants("svg-unclosed", data)

    def test_svg_many_metadata_blocks(self):
        meta = b"".join(b"<metadata>OpenAI</metadata>" for _ in range(500))
        data = (b'<svg xmlns="http://www.w3.org/2000/svg">' + meta + b"<rect/></svg>")
        res = ip.strip(data)
        assert b"OpenAI" not in res.data and b"<rect/>" in res.data


# ── scale ────────────────────────────────────────────────────────────────────
class TestScale:
    def test_large_metadata_payload(self):
        """A 12 MB C2PA manifest — bigger than most whole images."""
        big = C2PA + b"\x00" * (12 * 1024 * 1024)
        data = png([(b"caBX", big)])
        t0 = time.monotonic()
        res = ip.strip(data)
        elapsed = time.monotonic() - t0
        assert res.clean
        assert res.bytes_removed > 12 * 1024 * 1024
        assert elapsed < 15, f"12 MB manifest took {elapsed:.1f}s"

    def test_large_pixel_payload_is_not_copied_repeatedly(self):
        """Throughput must stay sane on a big IDAT — the payload is copied once."""
        data = png([(b"caBX", C2PA)], w=900, h=900)
        t0 = time.monotonic()
        res = ip.strip(data)
        elapsed = time.monotonic() - t0
        assert res.clean and res.lossless
        assert elapsed < 15, f"900x900 took {elapsed:.1f}s"

    def test_throughput_over_many_files(self):
        t0 = time.monotonic()
        n = 0
        for i in range(600):
            name, seed = SEEDS[i % len(SEEDS)]
            ip.strip(seed)
            n += 1
        rate = n / max(time.monotonic() - t0, 1e-6)
        assert rate > 50, f"only {rate:.0f} images/sec — too slow for a whole-CMS sweep"

    def test_repeated_strip_does_not_accumulate_state(self):
        """Module-level caches, if any, must not leak between calls."""
        data = png([(b"caBX", C2PA)])
        first = ip.strip(data)
        for _ in range(200):
            r = ip.strip(data)
            assert r.data == first.data
            assert [s.kind for s in r.removed] == [s.kind for s in first.removed]


# ── verifier integrity ───────────────────────────────────────────────────────
class TestVerifierCannotSilentlyPass:
    """A verifier that cannot go red proves nothing. Force it red in every way."""

    # A differing-payload twin for every container, so no case can skip.
    _TWINS = {
        "png": lambda: png(w=16, h=16),
        "jpeg": lambda: jpeg([(0xFE, b"different scan")]).replace(
            b"\xfe\xed\xfa\xce\xde\xad\xbe\xef", b"\x11\x22\x33\x44\x55\x66\x77\x88"),
        "webp": lambda: webp([(b"EXIF", b"x")]).replace(b"\x00" * 24, b"\x77" * 24),
        "gif": lambda: gif(comment=b"z").replace(b"\x02\x02\x44\x01\x00", b"\x02\x02\x21\x01\x00"),
        "svg": lambda: svg().replace(b'width="8"', b'width="9"'),
    }

    @pytest.mark.parametrize("name,data", SEEDS, ids=[n for n, _ in SEEDS])
    def test_digest_changes_when_the_payload_changes(self, name, data):
        """Every container's digest must be able to go red, not just PNG's.

        Nine of these used to pytest.skip, which meant the losslessness proof
        for WebP, GIF, JPEG and SVG rested on nothing.
        """
        container = ip.sniff(data)
        twin = self._TWINS[container]()
        assert twin != data, f"{container}: twin fixture is identical — proves nothing"
        ok, note = ip.verify_lossless(data, twin)
        assert not ok, f"{container}: verifier accepted a different payload ({note})"

    def test_a_truncated_payload_fails_verification(self):
        data = png([(b"caBX", C2PA)])
        res = ip.strip(data)
        mangled = res.data[:-8] + b"\x00" * 8
        ok, _ = ip.verify_lossless(data, mangled)
        assert not ok, "the verifier must notice a damaged tail"

    def test_raw_residue_finds_what_scan_would_miss(self):
        """Provenance hidden outside any declared metadata record."""
        data = png() + b"trailing junk: trainedAlgorithmicMedia"
        assert ip.raw_residue(data), "the byte-level backstop must see it"

    def test_strip_refuses_when_it_cannot_finish(self):
        """A file whose metadata cannot be removed must raise, not return dirty."""
        good = png([(b"caBX", C2PA)])
        bad = bytearray(good)
        off = good.index(b"caBX") - 4
        bad[off:off + 4] = struct.pack(">I", 0x7FFFFFF0)
        with pytest.raises(ProvenanceError):
            ip.strip(bytes(bad))


# ── policy matrix ────────────────────────────────────────────────────────────
class TestPolicyMatrix:
    @pytest.mark.parametrize("name,data", SEEDS, ids=[n for n, _ in SEEDS])
    def test_every_policy_combination_holds_the_invariants(self, name, data):
        from itertools import product
        for c2pa, exif, icc, orient in product((True, False), repeat=4):
            pol = ip.Policy(strip_c2pa=c2pa, strip_exif=exif,
                            keep_icc=icc, keep_orientation=orient)
            try:
                res = ip.strip(data, policy=pol)
            except ProvenanceError:
                continue
            ok, note = ip.verify_lossless(data, res.data)
            assert ok, f"{name} {pol}: {note}"
            surviving = [s for s in res.after.signals if s.removable and pol.wants(s.kind)]
            assert not surviving, f"{name} {pol}: {[s.kind for s in surviving]}"
