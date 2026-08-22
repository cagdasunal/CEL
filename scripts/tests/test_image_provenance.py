"""Tests for scripts/image_provenance.py — detection + lossless metadata surgery.

Three layers, deliberately:

  1. **Synthetic fixtures** — every container is built in-memory with a known
     metadata record injected, so the suite proves each code path without
     depending on any file in the repo.
  2. **Adversarial input** — truncated, malformed, lying-length, zero-byte and
     wrong-magic data. The engine must fail loudly or cleanly, never silently
     emit a corrupt image.
  3. **Real-corpus regression** — when ``sites/`` is present, every image in it
     is stripped and re-verified. Skipped (not failed) on a bare checkout.

The load-bearing invariant everywhere: ``strip()`` must never return a file it
cannot prove lossless, and must never leave a removable signal behind.
"""
from __future__ import annotations

import io
import struct
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import image_provenance as ip  # noqa: E402
from image_provenance import Policy, ProvenanceError  # noqa: E402


# ── fixture builders (stdlib only — no Pillow needed for most of the suite) ──

def _png(*, chunks: list[tuple[bytes, bytes]] | None = None, w: int = 4, h: int = 4) -> bytes:
    """Build a minimal but genuinely valid PNG, with optional extra chunks."""
    def chunk(t: bytes, p: bytes) -> bytes:
        return struct.pack(">I", len(p)) + t + p + struct.pack(">I", zlib.crc32(t + p) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)          # 8-bit RGB
    # One scanline per row: a leading filter byte, then w RGB triples. The
    # content varies per pixel so a size change is detectable by the digest.
    raw = b"".join(
        b"\x00" + bytes(sum(([x * 7 % 256, y * 11 % 256, 90] for x in range(w)), []))
        for y in range(h)
    )
    out = ip._PNG_MAGIC + chunk(b"IHDR", ihdr)
    for t, p in (chunks or []):
        out += chunk(t, p)
    out += chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    return out


C2PA_BLOB = (
    b"\x00\x00\x00\x1ejumb\x00\x00\x00\x16jumdc2pa\x00\x11\x00\x10\x80\x00\x00\xaa\x008\x9bq\x03"
    b"c2pa.actions.v2 softwareAgent gpt-image "
    b"digitalSourceType http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia "
    b"c2pa.watermarked.unbound OpenAI Media Service API"
)
XMP_BLOB = (
    b'<?xpacket begin="\xef\xbb\xbf"?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
    b'<rdf:RDF><rdf:Description Iptc4xmpExt:digitalSourceType='
    b'"http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"/>'
    b"</rdf:RDF></x:xmpmeta><?xpacket end='w'?>"
)


def _jpeg(*, segments: list[tuple[int, bytes]] | None = None) -> bytes:
    """Build a structurally valid JPEG skeleton with optional APPn segments."""
    def seg(marker: int, payload: bytes) -> bytes:
        return b"\xff" + bytes([marker]) + struct.pack(">H", len(payload) + 2) + payload

    out = b"\xff\xd8"
    out += seg(0xE0, b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00")
    for marker, payload in (segments or []):
        out += seg(marker, payload)
    out += seg(0xDB, b"\x00" + bytes(range(1, 65)))                     # DQT
    out += seg(0xC0, b"\x08\x00\x08\x00\x08\x01\x01\x11\x00")           # SOF0 8x8 grey
    out += seg(0xC4, b"\x00" + bytes([0] * 16) + b"\x00")               # DHT
    out += seg(0xDA, b"\x01\x01\x00\x00\x3f\x00")                       # SOS
    out += b"\xfe\xed\xfa\xce\xde\xad\xbe\xef"                          # entropy data
    out += b"\xff\xd9"
    return out


def _webp(*, chunks: list[tuple[bytes, bytes]] | None = None, vp8x_flags: int = 0) -> bytes:
    """Build a VP8X-extended WebP with optional metadata chunks."""
    def chunk(fourcc: bytes, payload: bytes) -> bytes:
        pad = b"\x00" if len(payload) & 1 else b""
        return fourcc + struct.pack("<I", len(payload)) + payload + pad

    body = b""
    if vp8x_flags or chunks:
        body += chunk(b"VP8X", bytes([vp8x_flags, 0, 0, 0]) + (7).to_bytes(3, "little") + (7).to_bytes(3, "little"))
    body += chunk(b"VP8 ", b"\x00" * 24)                                # opaque payload stand-in
    for fourcc, payload in (chunks or []):
        body += chunk(fourcc, payload)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


def _gif(*, comment: bytes | None = None, app: bytes | None = None) -> bytes:
    out = b"GIF89a" + struct.pack("<HH", 4, 4) + bytes([0xF0, 0, 0])
    out += bytes([0, 0, 0, 255, 255, 255])                               # 2-entry GCT
    if comment is not None:
        out += b"\x21\xfe" + bytes([len(comment)]) + comment + b"\x00"
    if app is not None:
        out += b"\x21\xff\x0b" + app.ljust(11, b"\x00")[:11] + b"\x03\x01\x00\x00\x00"
    out += b"\x2c" + struct.pack("<HHHH", 0, 0, 4, 4) + b"\x00"          # image descriptor
    out += b"\x02\x02\x44\x01\x00"                                       # LZW data + terminator
    out += b"\x3b"
    return out


# =============================================================================
# sniff
# =============================================================================
class TestSniff:
    @pytest.mark.parametrize("data,expected", [
        (_png(), "png"),
        (_jpeg(), "jpeg"),
        (_webp(), "webp"),
        (_gif(), "gif"),
        (b"\x00\x00\x00\x20ftypavif\x00\x00\x00\x00avifmif1miaf" + b"\x00" * 32, "avif"),
        (b"\x00\x00\x00\x20ftypheic\x00\x00\x00\x00heicmif1" + b"\x00" * 32, "heif"),
        (b"II*\x00" + b"\x00" * 32, "tiff"),
        (b"not an image at all, really", "unknown"),
        (b"", "unknown"),
        (b"\x89PNG", "unknown"),          # too short to be anything
    ])
    def test_container_identification(self, data, expected):
        assert ip.sniff(data) == expected

    def test_avif_via_compatible_brand_only(self):
        # Some encoders emit a generic major brand and only list avif in compat.
        data = b"\x00\x00\x00\x20ftypmif1\x00\x00\x00\x00mif1avifmiaf" + b"\x00" * 32
        assert ip.sniff(data) in ("avif", "heif")


# =============================================================================
# PNG
# =============================================================================
class TestPng:
    def test_detects_c2pa_in_cabx(self):
        rep = ip.scan(_png(chunks=[(b"caBX", C2PA_BLOB)]))
        assert rep.container == "png"
        assert rep.is_ai_flagged
        kinds = {s.kind for s in rep.signals}
        assert "c2pa" in kinds, "a caBX chunk must be reported as c2pa, never downgraded"
        assert "OpenAI gpt-image" in rep.generators

    def test_reports_undetectable_watermark_and_marks_it_unremovable(self):
        rep = ip.scan(_png(chunks=[(b"caBX", C2PA_BLOB)]))
        assert rep.undetectable_watermarks, "c2pa.watermarked must surface"
        wm = [s for s in rep.signals if s.kind == "watermark_declared"]
        assert wm and all(not s.removable for s in wm)

    def test_strips_cabx_losslessly(self):
        orig = _png(chunks=[(b"caBX", C2PA_BLOB)])
        res = ip.strip(orig)
        assert res.clean and res.lossless
        assert b"caBX" not in res.data and b"c2pa" not in res.data
        assert not ip.raw_residue(res.data)
        assert len(res.data) < len(orig)

    def test_strips_text_generator_tag(self):
        orig = _png(chunks=[(b"tEXt", b"hf-job-id\x00e57a4c89-d6e3-448a-9ad1")])
        rep = ip.scan(orig)
        assert "Higgsfield" in rep.generators
        res = ip.strip(orig)
        assert b"hf-job-id" not in res.data
        assert res.clean

    def test_detects_xmp_inside_itxt(self):
        payload = b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + XMP_BLOB
        rep = ip.scan(_png(chunks=[(b"iTXt", payload)]))
        assert rep.is_ai_flagged
        res = ip.strip(_png(chunks=[(b"iTXt", payload)]))
        assert b"trainedAlgorithmicMedia" not in res.data

    def test_preserves_icc_by_default(self):
        icc = b"ICCProfileName\x00\x00" + zlib.compress(b"fake icc payload")
        orig = _png(chunks=[(b"iCCP", icc), (b"caBX", C2PA_BLOB)])
        res = ip.strip(orig)
        assert b"iCCP" in res.data, "colour management must survive a provenance strip"
        assert b"caBX" not in res.data

    def test_drops_icc_when_asked(self):
        icc = b"ICCProfileName\x00\x00" + zlib.compress(b"fake icc payload")
        orig = _png(chunks=[(b"iCCP", icc)])
        res = ip.strip(orig, policy=Policy(keep_icc=False))
        assert b"iCCP" not in res.data

    def test_preserves_apng_control_chunks(self):
        actl = struct.pack(">II", 2, 0)
        orig = _png(chunks=[(b"acTL", actl), (b"caBX", C2PA_BLOB)])
        res = ip.strip(orig)
        assert b"acTL" in res.data, "an APNG must not be flattened into a still"
        assert b"caBX" not in res.data

    def test_preserves_render_essential_chunks(self):
        orig = _png(chunks=[(b"gAMA", struct.pack(">I", 45455)),
                            (b"sRGB", b"\x00"),
                            (b"tEXt", b"Software\x00Midjourney v6")])
        res = ip.strip(orig)
        for keep in (b"gAMA", b"sRGB"):
            assert keep in res.data
        assert b"Midjourney" not in res.data

    def test_drops_unrecognised_ancillary_chunk(self):
        # A novel provenance marker would look exactly like this.
        orig = _png(chunks=[(b"zZzZ", b"some future watermark record")])
        res = ip.strip(orig)
        assert b"zZzZ" not in res.data
        assert any(s.where.endswith("zZzZ") for s in res.removed)

    def test_crc_is_recomputed_and_valid(self):
        res = ip.strip(_png(chunks=[(b"caBX", C2PA_BLOB)]))
        # Walking the chunks validates every length; verify CRCs explicitly too.
        for off, ctype, payload, _t in ip._png_chunks(res.data):
            stored = struct.unpack(">I", res.data[off + 8 + len(payload):off + 12 + len(payload)])[0]
            assert stored == zlib.crc32(ctype + payload) & 0xFFFFFFFF


# =============================================================================
# JPEG
# =============================================================================
class TestJpeg:
    def test_detects_and_strips_exif_xmp_iptc_and_jumbf(self):
        orig = _jpeg(segments=[
            (0xE1, b"Exif\x00\x00MM\x00*\x00\x00\x00\x08\x00\x00\x00\x00\x00\x00"),
            (0xE1, b"http://ns.adobe.com/xap/1.0/\x00" + XMP_BLOB),
            (0xED, b"Photoshop 3.0\x008BIM\x04\x04\x00\x00\x00\x00\x00\x00"),
            (0xEB, b"JP\x00\x00" + C2PA_BLOB),
        ])
        rep = ip.scan(orig)
        kinds = {s.kind for s in rep.signals}
        assert {"exif", "iptc_iim", "c2pa"} <= kinds
        assert rep.is_ai_flagged
        res = ip.strip(orig)
        assert res.clean and res.lossless
        for gone in (b"Exif\x00\x00", b"ns.adobe.com/xap", b"Photoshop 3.0", b"c2pa"):
            assert gone not in res.data, f"{gone!r} survived"

    def test_entropy_coded_scan_is_copied_verbatim(self):
        orig = _jpeg(segments=[(0xEB, b"JP\x00\x00" + C2PA_BLOB)])
        res = ip.strip(orig)
        assert res.data.endswith(b"\xfe\xed\xfa\xce\xde\xad\xbe\xef\xff\xd9")

    def test_preserves_icc_and_jfif(self):
        orig = _jpeg(segments=[(0xE2, b"ICC_PROFILE\x00\x01\x01" + b"\x00" * 20),
                               (0xEB, b"JP\x00\x00" + C2PA_BLOB)])
        res = ip.strip(orig)
        assert b"ICC_PROFILE" in res.data
        assert b"JFIF" in res.data
        assert b"c2pa" not in res.data

    def test_reemits_orientation_when_stripping_exif(self):
        exif = ip._minimal_exif_orientation(6) + b"\x00" * 8      # padded => not "minimal"
        orig = _jpeg(segments=[(0xE1, exif)])
        assert ip._exif_orientation(exif) == 6
        res = ip.strip(orig)
        kept = [pl for _o, m, pl, _t in ip._jpeg_segments(res.data) if m == 0xE1]
        assert kept, "orientation must be re-emitted or the photo silently rotates"
        assert ip._exif_orientation(kept[0]) == 6
        assert ip._is_orientation_only_exif(kept[0])

    def test_orientation_reemission_does_not_trip_the_strip_assertion(self):
        # Regression: the post-strip "nothing survived" check used to fire on the
        # module's own orientation block, making every rotated photo unstrippable.
        exif = ip._minimal_exif_orientation(5) + b"junkjunk"
        res = ip.strip(_jpeg(segments=[(0xE1, exif)]))
        assert res.clean
        assert not ip.raw_residue(res.data)
        assert ip.raw_residue(res.data, strict=True), "strict mode must still see it"

    def test_orientation_not_reemitted_when_policy_declines(self):
        exif = ip._minimal_exif_orientation(6) + b"\x00" * 8
        res = ip.strip(_jpeg(segments=[(0xE1, exif)]), policy=Policy(keep_orientation=False))
        assert not [pl for _o, m, pl, _t in ip._jpeg_segments(res.data) if m == 0xE1]

    def test_orientation_1_is_not_reemitted(self):
        exif = ip._minimal_exif_orientation(1) + b"\x00" * 8
        res = ip.strip(_jpeg(segments=[(0xE1, exif)]))
        assert not [pl for _o, m, pl, _t in ip._jpeg_segments(res.data) if m == 0xE1]

    def test_preserves_adobe_app14_colour_transform(self):
        """APP14 carries the YCbCr/YCCK/CMYK transform byte, not metadata.

        Stripping it inverts colours on 4-component JPEGs. It was classified as
        droppable metadata until the tooling survey flagged it.
        """
        app14 = b"Adobe\x00d\x00\x00\x00\x00\x02"          # transform = 2 (YCCK)
        orig = _jpeg(segments=[(0xEE, app14), (0xEB, b"JP\x00\x00" + C2PA_BLOB)])
        rep = ip.scan(orig)
        assert not [s for s in rep.signals if "APP14" in s.where], "APP14 must not be a signal"
        res = ip.strip(orig)
        assert app14 in res.data, "the Adobe colour-transform marker must survive"
        assert b"c2pa" not in res.data

    def test_strips_com_comment(self):
        orig = _jpeg(segments=[(0xFE, b"Generated by Stable Diffusion")])
        rep = ip.scan(orig)
        assert "Stability AI" in rep.generators
        res = ip.strip(orig)
        assert b"Stable Diffusion" not in res.data


# =============================================================================
# WebP
# =============================================================================
class TestWebp:
    def test_strips_exif_and_xmp_chunks(self):
        flags = ip._WEBP_VP8X_EXIF | ip._WEBP_VP8X_XMP
        orig = _webp(vp8x_flags=flags,
                     chunks=[(b"EXIF", b"II*\x00 fake exif payload"),
                             (b"XMP ", XMP_BLOB)])
        rep = ip.scan(orig)
        assert {"exif"} <= {s.kind for s in rep.signals}
        assert rep.is_ai_flagged
        res = ip.strip(orig)
        assert res.clean and res.lossless
        assert b"XMP " not in res.data and b"trainedAlgorithmicMedia" not in res.data

    def test_clears_vp8x_feature_flags_for_removed_chunks(self):
        flags = ip._WEBP_VP8X_EXIF | ip._WEBP_VP8X_XMP | ip._WEBP_VP8X_ALPHA
        orig = _webp(vp8x_flags=flags, chunks=[(b"EXIF", b"x" * 10), (b"XMP ", b"y" * 10)])
        res = ip.strip(orig)
        vp8x = [p for _o, f, p, _t in ip._webp_chunks(res.data) if f == b"VP8X"]
        assert vp8x, "VP8X must survive"
        got = vp8x[0][0]
        assert not got & ip._WEBP_VP8X_EXIF, "EXIF flag must be cleared"
        assert not got & ip._WEBP_VP8X_XMP, "XMP flag must be cleared"
        assert got & ip._WEBP_VP8X_ALPHA, "unrelated flags must be untouched"

    def test_riff_size_header_is_corrected(self):
        orig = _webp(vp8x_flags=ip._WEBP_VP8X_EXIF, chunks=[(b"EXIF", b"z" * 100)])
        res = ip.strip(orig)
        declared = struct.unpack("<I", res.data[4:8])[0]
        assert declared == len(res.data) - 8, "RIFF size must match the rewritten body"

    def test_c2pa_chunk_removed(self):
        orig = _webp(vp8x_flags=0, chunks=[(b"C2PA", C2PA_BLOB)])
        rep = ip.scan(orig)
        assert "c2pa" in {s.kind for s in rep.signals}
        res = ip.strip(orig)
        assert b"c2pa" not in res.data

    def test_odd_length_chunk_padding_handled(self):
        orig = _webp(vp8x_flags=ip._WEBP_VP8X_EXIF, chunks=[(b"EXIF", b"odd")])  # 3 bytes → padded
        res = ip.strip(orig)
        assert res.clean
        assert struct.unpack("<I", res.data[4:8])[0] == len(res.data) - 8


# =============================================================================
# GIF
# =============================================================================
class TestGif:
    def test_strips_comment_extension(self):
        orig = _gif(comment=b"made with Midjourney")
        rep = ip.scan(orig)
        assert "Midjourney" in rep.generators
        res = ip.strip(orig)
        assert b"Midjourney" not in res.data
        assert res.clean and res.lossless

    def test_preserves_netscape_loop_extension(self):
        orig = _gif(app=b"NETSCAPE2.0", comment=b"OpenAI")
        res = ip.strip(orig)
        assert b"NETSCAPE2.0" in res.data, "animation loop control must survive"
        assert b"OpenAI" not in res.data

    def test_strips_foreign_application_extension(self):
        orig = _gif(app=b"XMP DataXMP")
        res = ip.strip(orig)
        assert b"XMP Data" not in res.data


# =============================================================================
# spec-conformance regressions
#
# Each of these pins a value or a structural rule that, when wrong, fails
# SILENTLY — the scan comes back clean on a file that still carries a manifest.
# They exist because two of them were in fact wrong on the first pass.
# =============================================================================
class TestSpecConformance:
    def test_c2pa_bmff_uuid_matches_the_spec(self):
        """A mistyped UUID makes every C2PA-bearing AVIF/HEIF scan clean."""
        assert ip._C2PA_UUID.hex() == "d8fec3d61b0e483c92975828877ec481"
        assert len(ip._C2PA_UUID) == 16
        assert len(ip._C2PA_UUID_ALT) == 16

    def test_c2pa_uuid_is_derived_from_the_hyphenated_spec_string(self):
        assert ip._C2PA_UUID == bytes.fromhex(ip._C2PA_BMFF_UUID_STR.replace("-", ""))

    def test_multi_segment_jpeg_app11_is_fully_removed(self):
        """A C2PA manifest over 64 KB spans several contiguous APP11 segments.

        Removing only the first leaves a live remainder — a partial strip that
        still reads as a manifest to a tolerant parser.
        """
        part = b"JP\x00\x00" + b"M" * 60000
        orig = _jpeg(segments=[(0xEB, part), (0xEB, part), (0xEB, part)])
        rep = ip.scan(orig)
        app11 = [s for s in rep.signals if s.where == "JPEG:APP11"]
        assert len(app11) == 3, "every APP11 segment must be reported, not just the first"
        res = ip.strip(orig)
        assert b"JP\x00\x00" not in res.data
        assert res.clean

    def test_c2pa_gif_application_extension_is_removed(self):
        """exiftool cannot delete this at any version; we must."""
        orig = _gif(app=b"C2PA_GIF")
        rep = ip.scan(orig)
        assert rep.signals, "the C2PA_GIF app extension must be detected"
        res = ip.strip(orig)
        assert b"C2PA_GIF" not in res.data
        assert not ip.raw_residue(res.data)

    def test_webp_c2pa_fourcc_is_the_spec_one(self):
        assert b"C2PA" in ip._WEBP_META_KINDS
        assert ip._WEBP_META_KINDS[b"C2PA"] == "c2pa"

    def test_png_c2pa_chunk_is_cabx(self):
        assert ip._PNG_META_KINDS[b"caBX"] == "c2pa"

    def test_external_manifest_pointer_is_flagged(self):
        """dcterms:provenance points at a manifest hosted off-file."""
        xmp = (b"XML:com.adobe.xmp\x00\x00\x00\x00\x00"
               b'<x:xmpmeta><rdf:Description dcterms:provenance="https://example/c2pa"/></x:xmpmeta>')
        orig = _png(chunks=[(b"iTXt", xmp)])
        assert ip.raw_residue(orig), "the pointer must be visible to the raw backstop"
        res = ip.strip(orig)
        assert b"dcterms:provenance" not in res.data

    def test_detection_is_structural_not_a_byte_grep(self):
        """Compressed pixel data can contain any byte sequence, including 0xFFEB.

        A grep-based detector reports a JPEG C2PA marker inside a PNG's IDAT.
        scan() walks chunk lengths, so it must not.
        """
        # 4096 pseudo-random pixels — the compressed stream will contain 0xFFEB runs.
        w = h = 64
        raw = b"".join(b"\x00" + bytes(((x * 37 + y * 91 + 13) % 256) for x in range(w * 3))
                       for y in range(h))
        def chunk(t, p):
            return struct.pack(">I", len(p)) + t + p + struct.pack(">I", zlib.crc32(t + p) & 0xFFFFFFFF)
        data = (ip._PNG_MAGIC
                + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 0))     # stored: raw bytes pass through
                + chunk(b"IEND", b""))
        rep = ip.scan(data)
        assert not rep.parse_error
        assert not rep.signals, "no metadata declared, so none may be reported"


class TestIsobmffRefusesWhatItCannotAccountFor:
    """The remux rebuilds mdat from meta-level iloc items ONLY.

    Exact for a still image — measured, iloc covers 100% of mdat. But an
    animated AVIF (`avis`) or HEIF sequence also stores TRACK samples there,
    addressed by moov/stco offsets this code neither reads nor rewrites.
    Remuxing one deletes the track data while `_iso_pixel_digest` — which hashes
    only meta-level picture items — still reports lossless=True. A container we
    cannot fully account for must not be rewritten.
    """

    @pytest.fixture(autouse=True)
    def _need_pillow(self):
        pytest.importorskip("PIL")

    def _animated_avif(self) -> bytes:
        from PIL import Image
        try:
            import pillow_avif  # noqa: F401
        except ImportError:
            pytest.skip("no AVIF encoder")
        frames = []
        for i in range(3):
            im = Image.new("RGB", (48, 32))
            im.putdata([((x * 3 + i * 40) % 256, (y * 5 + i * 20) % 256, (i * 60) % 256)
                        for y in range(32) for x in range(48)])
            frames.append(im)
        buf = io.BytesIO()
        try:
            frames[0].save(buf, format="AVIF", save_all=True,
                           append_images=frames[1:], duration=100)
        except (OSError, ValueError) as e:
            pytest.skip(f"cannot build an animated AVIF: {e}")
        return buf.getvalue()

    def _force_remux(self, data: bytes):
        """A signal must be present or _strip_iso early-returns before the guard."""
        rep = ip.scan(data)
        rep.signals.append(ip.Signal(kind="iptc_ai", where="ISOBMFF:item:mime",
                                     offset=0, length=1, removable=True))
        return rep

    def test_a_movie_box_is_refused(self):
        data = self._animated_avif()
        top = ip._iso_boxes(data, 0, len(data))
        assert any(b.typ == b"moov" for b in top), "fixture has no moov — nothing to guard"
        with pytest.raises(ProvenanceError, match="movie box"):
            ip._strip_iso(data, ip.DEFAULT_POLICY, self._force_remux(data))

    def test_unaccounted_mdat_bytes_are_refused(self):
        """Pad mdat with bytes no iloc extent covers; the remux would drop them."""
        from PIL import Image
        try:
            import pillow_avif  # noqa: F401
        except ImportError:
            pytest.skip("no AVIF encoder")
        im = Image.new("RGB", (32, 32), (10, 20, 30))
        buf = io.BytesIO(); im.save(buf, format="AVIF")
        data = bytearray(buf.getvalue())
        top = ip._iso_boxes(bytes(data), 0, len(data))
        mdat = next(b for b in top if b.typ == b"mdat")
        # grow mdat by 64 bytes that nothing points at
        data[mdat.offset:mdat.offset + 4] = struct.pack(">I", mdat.size + 64)
        data[mdat.end:mdat.end] = b"\x00" * 64
        blob = bytes(data)
        with pytest.raises(ProvenanceError, match="no iloc extent accounts for"):
            ip._strip_iso(blob, ip.DEFAULT_POLICY, self._force_remux(blob))

    def test_a_normal_still_avif_is_NOT_refused(self):
        """The guard must not fire on the files this tool actually processes."""
        from PIL import Image
        try:
            import pillow_avif  # noqa: F401
        except ImportError:
            pytest.skip("no AVIF encoder")
        im = Image.new("RGB", (32, 32), (10, 20, 30))
        buf = io.BytesIO()
        im.save(buf, format="AVIF",
                xmp=b'<x:xmpmeta><rdf:Description Iptc4xmpExt:digitalSourceType='
                    b'"http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"'
                    b'/></x:xmpmeta>')
        data = buf.getvalue()
        assert ip.scan(data).is_ai_flagged, "fixture lost its XMP"
        res = ip.strip(data)                      # must not raise
        assert res.clean and res.lossless
        assert Image.open(io.BytesIO(res.data)).size == (32, 32)


class TestRealFormatVariants:
    """Round-trip real encoder output, not just hand-built skeletons.

    The synthetic fixtures elsewhere in this file exercise the parsers, but they
    are all baseline/simple. Real files are progressive, interlaced, palettised,
    1-bit, 16-bit, CMYK, lossless-WebP. Each of those is a different code path
    through the same parser, and CMYK JPEG in particular is where dropping the
    Adobe APP14 marker would invert colour without any test noticing.
    """

    @pytest.fixture(autouse=True)
    def _need_pillow(self):
        pytest.importorskip("PIL")

    def _build(self, mode, fmt, size=(64, 48), **save):
        from PIL import Image
        try:
            import pillow_avif  # noqa: F401
        except ImportError:
            pass
        im = Image.new(mode, size)
        if mode in ("RGB", "RGBA", "CMYK"):
            im.putdata([tuple((x * 3 + y * 5 + c * 7) % 256 for c in range(len(mode)))
                        for y in range(size[1]) for x in range(size[0])])
        buf = io.BytesIO()
        im.save(buf, format=fmt, **save)
        return buf.getvalue()

    def _pixels(self, data):
        from PIL import Image, ImageSequence
        im = Image.open(io.BytesIO(data))
        return b"".join(f.convert("RGBA").tobytes() for f in ImageSequence.Iterator(im))

    @pytest.mark.parametrize("label,mode,fmt,kw", [
        ("jpeg-baseline",    "RGB",  "JPEG", {"quality": 85}),
        ("jpeg-progressive", "RGB",  "JPEG", {"quality": 85, "progressive": True}),
        ("jpeg-optimized",   "RGB",  "JPEG", {"quality": 85, "optimize": True}),
        ("jpeg-444",         "RGB",  "JPEG", {"quality": 95, "subsampling": 0}),
        ("jpeg-grey",        "L",    "JPEG", {"quality": 85}),
        ("jpeg-cmyk",        "CMYK", "JPEG", {"quality": 85}),
        ("png-rgba",         "RGBA", "PNG",  {}),
        ("png-interlaced",   "RGB",  "PNG",  {"interlace": True}),
        ("png-palette",      "P",    "PNG",  {}),
        ("png-1bit",         "1",    "PNG",  {}),
        ("png-16bit",        "I;16", "PNG",  {}),
        ("webp-lossy",       "RGB",  "WEBP", {"quality": 80}),
        ("webp-lossless",    "RGB",  "WEBP", {"lossless": True}),
        ("webp-rgba",        "RGBA", "WEBP", {"quality": 80}),
        ("avif",             "RGB",  "AVIF", {"quality": 60}),
        ("gif",              "P",    "GIF",  {}),
    ])
    def test_round_trips_losslessly(self, label, mode, fmt, kw):
        try:
            data = self._build(mode, fmt, **kw)
        except (OSError, ValueError, KeyError) as e:
            pytest.skip(f"encoder unavailable for {label}: {e}")
        res = ip.strip(data)
        assert res.lossless, f"{label}: container digest says the payload changed"
        assert self._pixels(data) == self._pixels(res.data), f"{label}: decoded pixels differ"

    @pytest.mark.parametrize("label,fmt", [
        ("animated-gif", "GIF"), ("apng", "PNG"), ("animated-webp", "WEBP")])
    def test_animation_survives(self, label, fmt):
        """Dropping an APNG control chunk or a WebP ANMF turns a loop into a still."""
        from PIL import Image, ImageSequence
        frames = []
        for i in range(4):
            im = Image.new("RGB", (48, 32))
            im.putdata([((x * 3 + i * 40) % 256, (y * 5 + i * 20) % 256, (i * 60) % 256)
                        for y in range(32) for x in range(48)])
            frames.append(im)
        buf = io.BytesIO()
        try:
            frames[0].save(buf, format=fmt, save_all=True, append_images=frames[1:],
                           duration=100, loop=0)
        except (OSError, ValueError) as e:
            pytest.skip(f"cannot build {label}: {e}")
        data = buf.getvalue()

        def n_frames(b):
            return sum(1 for _ in ImageSequence.Iterator(Image.open(io.BytesIO(b))))

        if n_frames(data) < 2:
            pytest.skip(f"{label}: encoder produced a single frame")
        res = ip.strip(data)
        assert n_frames(res.data) == n_frames(data), f"{label}: frames were lost"
        assert self._pixels(data) == self._pixels(res.data), f"{label}: frame pixels differ"


class TestAiGeneratorFlag:
    """A vendor breadcrumb naming an AI generator is an AI signal.

    Regression: is_ai_flagged counted only c2pa/iptc_ai, so a PNG whose sole
    marker was Higgsfield's `hf-job-id` — a live job identifier tied to the
    account that generated it, arguably a stronger link than an anonymous C2PA
    manifest — was reported as ordinary "metadata". 9 real images slipped
    through that way.
    """

    def test_higgsfield_job_id_alone_is_an_ai_signal(self):
        rep = ip.scan(_png(chunks=[(b"tEXt", b"hf-job-id\x00e57a4c89-d6e3-448a-9ad1")]))
        assert rep.is_ai_flagged
        assert rep.ai_generators == ["Higgsfield"]

    @pytest.mark.parametrize("blob,expected", [
        (b"Software\x00Midjourney v6", "Midjourney"),
        (b"Software\x00Stable Diffusion", "Stability AI"),
        (b"Comment\x00Made with Google AI", "Google"),
        (b"Software\x00Ideogram", "Ideogram"),
    ])
    def test_other_ai_generators_flag_too(self, blob, expected):
        rep = ip.scan(_png(chunks=[(b"tEXt", blob)]))
        assert rep.is_ai_flagged
        assert expected in rep.ai_generators

    def test_photo_editors_do_NOT_flag(self):
        """A retouched photograph is not AI-generated; flagging it kills the signal."""
        rep = ip.scan(_png(chunks=[(b"tEXt", b"Software\x00Adobe Photoshop 26.0")]))
        assert rep.generators == ["Adobe Photoshop"]
        assert rep.ai_generators == []
        assert not rep.is_ai_flagged

    def test_clean_image_is_not_flagged(self):
        assert not ip.scan(_png()).is_ai_flagged

    def test_c2pa_still_flags_without_a_generator_match(self):
        blob = b"jumb jumdc2pa digitalSourceType trainedAlgorithmicMedia"
        rep = ip.scan(_png(chunks=[(b"caBX", blob)]))
        assert rep.is_ai_flagged and rep.ai_generators == []

    def test_ai_generators_is_in_as_dict(self):
        d = ip.scan(_png(chunks=[(b"tEXt", b"hf-job-id\x00abc")])).as_dict()
        assert d["ai_generators"] == ["Higgsfield"]
        assert d["is_ai_flagged"] is True

    def test_every_ai_generator_label_is_actually_producible(self):
        """Guard the allowlist: a label in _AI_GENERATORS that no pattern emits is dead."""
        emitted = {label for _needle, label in ip._GENERATOR_PATTERNS}
        orphans = ip._AI_GENERATORS - emitted
        assert not orphans, f"_AI_GENERATORS names labels no pattern produces: {sorted(orphans)}"


class TestSvg:
    def _svg(self, metadata: bytes = b"") -> bytes:
        meta = b"<metadata>" + metadata + b"</metadata>" if metadata else b""
        return (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" '
                b'viewBox="0 0 10 10">' + meta + b'<rect width="10" height="10"/></svg>')

    def test_sniffs_svg(self):
        assert ip.sniff(self._svg()) == "svg"
        assert ip.sniff(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>') == "svg"

    def test_strips_c2pa_manifest_element(self):
        orig = self._svg(b"<c2pa:manifest>" + C2PA_BLOB + b"</c2pa:manifest>")
        rep = ip.scan(orig)
        assert "c2pa" in {s.kind for s in rep.signals}
        res = ip.strip(orig)
        assert b"c2pa" not in res.data
        assert b"<rect" in res.data, "rendered content must survive"
        assert res.lossless

    def test_strips_editor_metadata_block(self):
        orig = self._svg(b"<rdf:RDF>Adobe Illustrator 29.0</rdf:RDF>")
        rep = ip.scan(orig)
        assert "Adobe Photoshop" in rep.generators or rep.signals
        res = ip.strip(orig)
        assert b"Illustrator" not in res.data
        assert b"<rect" in res.data

    def test_clean_svg_is_untouched(self):
        orig = self._svg()
        res = ip.strip(orig)
        assert res.data == orig
        assert not res.changed

    def test_self_closing_metadata_tag(self):
        orig = b'<svg xmlns="http://www.w3.org/2000/svg"><metadata/><rect/></svg>'
        res = ip.strip(orig)
        assert b"<rect/>" in res.data


# =============================================================================
# adversarial / malformed input
# =============================================================================
class TestAdversarial:
    @pytest.mark.parametrize("data", [
        b"",
        b"\x00",
        b"\x89PNG\r\n\x1a\n",                                   # header only
        b"\x89PNG\r\n\x1a\n" + b"\xff" * 32,                    # garbage chunks
        b"\xff\xd8\xff",                                        # JPEG header only
        b"RIFF\x04\x00\x00\x00WEBP",                            # empty WebP
        b"GIF89a",                                              # truncated GIF
        b"\x00\x00\x00\x08ftypavif",                            # truncated AVIF
    ])
    def test_scan_never_raises(self, data):
        rep = ip.scan(data)
        assert isinstance(rep, ip.Report)          # a Report, possibly with parse_error

    @pytest.mark.parametrize("data", [
        b"", b"\x00" * 40, b"not an image",
        b"\x89PNG\r\n\x1a\n" + b"\xff" * 32,
        b"\xff\xd8\xff\xe0\xff\xff\xff\xff",
    ])
    def test_strip_raises_rather_than_returning_garbage(self, data):
        with pytest.raises(ProvenanceError):
            ip.strip(data)

    def test_png_lying_chunk_length_is_rejected(self):
        good = _png(chunks=[(b"caBX", C2PA_BLOB)])
        bad = bytearray(good)
        # Overstate the caBX length so it claims to run past EOF.
        off = good.index(b"caBX") - 4
        bad[off:off + 4] = struct.pack(">I", 0x7FFFFFF0)
        rep = ip.scan(bytes(bad))
        assert rep.parse_error, "an overrunning chunk length must be reported"
        with pytest.raises(ProvenanceError):
            ip.strip(bytes(bad))

    def test_jpeg_bad_segment_length_is_rejected(self):
        good = _jpeg(segments=[(0xEB, b"JP\x00\x00" + C2PA_BLOB)])
        bad = bytearray(good)
        i = good.index(b"\xff\xeb")
        bad[i + 2:i + 4] = struct.pack(">H", 1)     # length < 2 is invalid
        assert ip.scan(bytes(bad)).parse_error
        with pytest.raises(ProvenanceError):
            ip.strip(bytes(bad))

    def test_webp_chunk_overrun_is_rejected(self):
        good = _webp(vp8x_flags=ip._WEBP_VP8X_EXIF, chunks=[(b"EXIF", b"q" * 8)])
        bad = bytearray(good)
        i = good.index(b"EXIF")
        bad[i + 4:i + 8] = struct.pack("<I", 0xFFFF)
        assert ip.scan(bytes(bad)).parse_error

    def test_truncated_png_mid_idat(self):
        good = _png(chunks=[(b"caBX", C2PA_BLOB)])
        assert ip.scan(good[:len(good) - 20]).parse_error

    def test_zero_length_chunks_are_survivable(self):
        orig = _png(chunks=[(b"tEXt", b""), (b"caBX", b"")])
        res = ip.strip(orig)
        assert res.clean

    def test_huge_declared_isobmff_box_is_rejected(self):
        # A well-formed 24-byte ftyp, then a meta box claiming 2 GB of body.
        ftyp = struct.pack(">I", 24) + b"ftyp" + b"avif" + struct.pack(">I", 0) + b"avif" + b"mif1"
        assert len(ftyp) == 24
        data = ftyp + struct.pack(">I", 0x7FFFFFFF) + b"meta" + b"\x00" * 8
        rep = ip.scan(data)
        assert rep.parse_error, "a box declaring more bytes than the file holds must be refused"
        with pytest.raises(ProvenanceError):
            ip.strip(data)

    def test_isobmff_zero_size_box_does_not_hang_or_overrun(self):
        # size == 0 means "runs to end of file"; it must terminate, not loop.
        ftyp = struct.pack(">I", 24) + b"ftyp" + b"avif" + struct.pack(">I", 0) + b"avif" + b"mif1"
        data = ftyp + struct.pack(">I", 0) + b"free" + b"\x00" * 8
        rep = ip.scan(data)
        assert isinstance(rep, ip.Report)

    def test_isobmff_largesize_truncated_is_rejected(self):
        ftyp = struct.pack(">I", 24) + b"ftyp" + b"avif" + struct.pack(">I", 0) + b"avif" + b"mif1"
        data = ftyp + struct.pack(">I", 1) + b"meta" + b"\x00\x00\x00"   # largesize cut short
        rep = ip.scan(data)
        assert rep.parse_error

    def test_nul_bytes_in_text_keyword(self):
        orig = _png(chunks=[(b"tEXt", b"\x00\x00\x00OpenAI")])
        res = ip.strip(orig)
        assert b"OpenAI" not in res.data


# =============================================================================
# invariants / property-style
# =============================================================================
def _all_fixtures() -> list[tuple[str, bytes]]:
    return [
        ("png-c2pa", _png(chunks=[(b"caBX", C2PA_BLOB)])),
        ("png-text", _png(chunks=[(b"tEXt", b"hf-job-id\x00abc123")])),
        ("png-clean", _png()),
        ("png-multi", _png(chunks=[(b"caBX", C2PA_BLOB), (b"tEXt", b"Software\x00Midjourney"),
                                   (b"tIME", b"\x07\xe9\x08\x16\x0c\x00\x00")])),
        ("jpeg-c2pa", _jpeg(segments=[(0xEB, b"JP\x00\x00" + C2PA_BLOB)])),
        ("jpeg-exif", _jpeg(segments=[(0xE1, b"Exif\x00\x00MM\x00*\x00\x00\x00\x08\x00\x00" + b"\x00" * 20)])),
        ("jpeg-clean", _jpeg()),
        ("webp-exif", _webp(vp8x_flags=ip._WEBP_VP8X_EXIF, chunks=[(b"EXIF", b"II*\x00abcd")])),
        ("webp-clean", _webp()),
        ("gif-comment", _gif(comment=b"OpenAI DALL-E")),
        ("gif-clean", _gif()),
    ]


class TestInvariants:
    @pytest.mark.parametrize("name,data", _all_fixtures(), ids=lambda v: v if isinstance(v, str) else "")
    def test_strip_is_idempotent(self, name, data):
        once = ip.strip(data).data
        twice = ip.strip(once).data
        assert once == twice, f"{name}: a second strip changed the file"

    @pytest.mark.parametrize("name,data", _all_fixtures(), ids=lambda v: v if isinstance(v, str) else "")
    def test_strip_never_grows_the_payload(self, name, data):
        res = ip.strip(data)
        # Orientation re-emission can add ≤ 44 bytes; nothing else may grow a file.
        assert len(res.data) <= len(data) + 44, f"{name}: grew by {len(res.data) - len(data)}"

    @pytest.mark.parametrize("name,data", _all_fixtures(), ids=lambda v: v if isinstance(v, str) else "")
    def test_strip_is_always_lossless(self, name, data):
        res = ip.strip(data)
        ok, note = ip.verify_lossless(data, res.data)
        assert ok, f"{name}: {note}"
        assert res.lossless

    @pytest.mark.parametrize("name,data", _all_fixtures(), ids=lambda v: v if isinstance(v, str) else "")
    def test_container_is_unchanged(self, name, data):
        assert ip.sniff(ip.strip(data).data) == ip.sniff(data)

    @pytest.mark.parametrize("name,data", _all_fixtures(), ids=lambda v: v if isinstance(v, str) else "")
    def test_no_removable_signal_survives(self, name, data):
        res = ip.strip(data)
        assert res.clean, f"{name}: {[s.kind for s in res.after.signals]}"

    def test_verify_lossless_can_actually_fail(self):
        """The verifier must be able to go red, or it proves nothing."""
        a = _png(chunks=[(b"caBX", C2PA_BLOB)])
        b = _png(chunks=[(b"caBX", C2PA_BLOB)], w=8, h=8)     # different pixels
        ok, note = ip.verify_lossless(a, b)
        assert not ok and "pixel payload changed" in note

    def test_verify_lossless_rejects_container_swap(self):
        ok, note = ip.verify_lossless(_png(), _jpeg())
        assert not ok and "container changed" in note

    def test_policy_can_decline_every_removal(self):
        keep_all = Policy(strip_c2pa=False, strip_exif=False, strip_xmp=False,
                          strip_iptc=False, strip_comments=False, strip_generator_tags=False)
        orig = _png(chunks=[(b"caBX", C2PA_BLOB)])
        res = ip.strip(orig, policy=keep_all)
        assert res.data == orig, "a no-op policy must be byte-preserving"
        assert not res.changed


# =============================================================================
# reporting surface
# =============================================================================
class TestReport:
    def test_as_dict_is_json_serialisable(self):
        import json
        rep = ip.scan(_png(chunks=[(b"caBX", C2PA_BLOB)]))
        json.dumps(rep.as_dict())          # must not raise

    def test_result_as_dict_is_json_serialisable(self):
        import json
        res = ip.strip(_png(chunks=[(b"caBX", C2PA_BLOB)]))
        json.dumps(res.as_dict())

    def test_clean_image_reports_nothing_to_do(self):
        rep = ip.scan(_png())
        assert not rep.is_ai_flagged
        assert rep.removable_bytes == 0
        assert not rep.signals

    def test_undetectable_watermark_never_counted_as_removable(self):
        rep = ip.scan(_png(chunks=[(b"caBX", C2PA_BLOB)]))
        wm = [s for s in rep.signals if s.kind == "watermark_declared"]
        assert wm
        assert rep.removable_bytes == sum(s.length for s in rep.signals if s.removable)
        assert all(s.length == 0 for s in wm), "a declaration has no bytes of its own to remove"


# =============================================================================
# real-corpus regression (skipped on a bare checkout)
# =============================================================================
SITES = ROOT / "sites"
_CORPUS_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif"}


def _corpus(limit: int | None = None) -> list[Path]:
    if not SITES.is_dir():
        return []
    out = [p for p in sorted(SITES.rglob("*"))
           if p.is_file() and p.suffix.lower() in _CORPUS_EXTS]
    return out[:limit] if limit else out


@pytest.mark.skipif(not _corpus(), reason="no sites/ image corpus in this checkout")
class TestRealCorpus:
    def test_every_image_scans_or_reports_why_not(self):
        bad = []
        for p in _corpus():
            rep = ip.scan(p.read_bytes())
            if rep.parse_error and rep.container != "unknown":
                bad.append((p.name, rep.parse_error))
        assert not bad, f"unparseable images: {bad[:5]}"

    def test_every_strippable_image_round_trips_losslessly(self):
        failures = []
        stripped = 0
        for p in _corpus():
            data = p.read_bytes()
            rep = ip.scan(data)
            if rep.parse_error or not any(s.removable for s in rep.signals):
                continue
            try:
                res = ip.strip(data)
                stripped += 1
            except ProvenanceError as e:
                failures.append((p.name, str(e)))
                continue
            if not res.clean:
                failures.append((p.name, "signals survived"))
            if ip.raw_residue(res.data):
                failures.append((p.name, f"residue {ip.raw_residue(res.data)[:2]}"))
        assert not failures, f"{len(failures)} failures: {failures[:5]}"
        # `stripped == 0` is legitimate once the corpus has been cleaned; the
        # synthetic fixtures cover the strip path unconditionally.

    def test_the_repo_corpus_stays_clean(self):
        """Regression guard: no AI-provenance signal may reappear under sites/.

        This replaces an assertion that the corpus *contains* C2PA-bearing
        images — a test that inverted the moment the tool did its job, which is
        exactly backwards. Cleanliness is the invariant worth pinning; the
        machinery's ability to go red is proven by the synthetic fixtures and by
        test_oracle_detects_our_synthetic_fixture_is_not_a_real_manifest.
        """
        flagged = []
        for p in _corpus():
            rep = ip.scan(p.read_bytes())
            if rep.is_ai_flagged:
                flagged.append((str(p.relative_to(ROOT)), rep.ai_generators or rep.kinds))
        assert not flagged, (
            f"{len(flagged)} image(s) under sites/ carry an AI-provenance signal — "
            f"run `watermark_cleaner.py clean --local sites/<site> --apply`: {flagged[:5]}"
        )


# ── independent oracle: the official C2PA SDK ────────────────────────────────
_C2PA_MIME = {"png": "image/png", "jpeg": "image/jpeg",
              "webp": "image/webp", "avif": "image/avif", "heif": "image/heif"}


def _sdk_sees_manifest(data: bytes, mime: str) -> bool:
    """True when c2pa-rs (via c2pa-python) can read a manifest out of these bytes."""
    from c2pa import Reader
    try:
        Reader(mime, io.BytesIO(data))
        return True
    except Exception:
        return False


class TestOfficialSdkOracle:
    """Cross-check our removal against the reference C2PA implementation.

    Our own ``scan()`` deciding a file is clean proves only that our parser
    cannot find anything — a scanner and a stripper sharing one author share
    one blind spot. c2pa-rs is the reference implementation used by Content
    Credentials Verify; if it cannot find a manifest, the manifest is gone as
    far as the ecosystem is concerned. It can read and validate, but has no
    removal API, so it can only ever contradict us — never flatter us.
    """

    def test_oracle_detects_our_synthetic_fixture_is_not_a_real_manifest(self):
        """Guard the guard: our fake C2PA blob must NOT read as a valid manifest.

        Without this, a green oracle run would be meaningless — it could be
        green because the SDK cannot parse anything we build.
        """
        pytest.importorskip("c2pa")
        assert not _sdk_sees_manifest(_png(chunks=[(b"caBX", C2PA_BLOB)]), "image/png")

    @pytest.mark.skipif(not _corpus(), reason="no sites/ image corpus in this checkout")
    def test_real_manifests_are_gone_according_to_the_reference_implementation(self):
        pytest.importorskip("c2pa")
        checked = 0
        survived = []
        for p in _corpus():
            data = p.read_bytes()
            container = ip.sniff(data)
            mime = _C2PA_MIME.get(container)
            if not mime or not _sdk_sees_manifest(data, mime):
                continue
            after = ip.strip(data).data
            if _sdk_sees_manifest(after, mime):
                survived.append(p.name)
            checked += 1
        if checked == 0:
            # A clean corpus is the DESIRED end state, so "found nothing to
            # check" must not fail. The oracle's ability to contradict us is
            # pinned separately by the synthetic-fixture guard above, which does
            # not depend on repo contents at all.
            pytest.skip("no SDK-readable manifests under sites/ — corpus is clean")
        assert not survived, f"reference implementation still reads a manifest in: {survived[:5]}"


@pytest.mark.skipif(not _corpus(), reason="no sites/ image corpus in this checkout")
def test_decoded_pixels_are_identical_after_strip():
    """The strongest check available: decode both files and compare raw pixels.

    ``verify_lossless`` reasons about the container. This reasons about the
    image. They must agree, and both must be green.
    """
    pytest.importorskip("PIL")
    from PIL import Image, ImageSequence

    def pixels(b: bytes) -> bytes:
        im = Image.open(io.BytesIO(b))
        return b"".join(f.convert("RGBA").tobytes() for f in ImageSequence.Iterator(im))

    checked = 0
    for p in _corpus(limit=120):
        data = p.read_bytes()
        rep = ip.scan(data)
        if rep.parse_error or not any(s.removable for s in rep.signals):
            continue
        res = ip.strip(data)
        try:
            before, after = pixels(data), pixels(res.data)
        except Exception:
            continue                                   # codec unavailable (e.g. AVIF)
        assert before == after, f"{p.name}: decoded pixels differ after strip"
        checked += 1
    if checked == 0:
        pytest.skip("nothing under sites/ needed stripping — corpus is clean")
