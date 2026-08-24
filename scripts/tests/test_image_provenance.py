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

    def test_c2pa_alt_uuid_matches_the_jumbf_template(self):
        """`len(...) == 16` accepts any sixteen bytes, so it guarded nothing.

        The legacy form is the four-byte JUMBF type tag `c2pa` followed by the
        ISO/IEC 14496-12 §A.1 extended-type template
        ``XXXXXXXX-0011-0010-8000-00AA00389B71``. Pin both halves: a wrong value
        here fails exactly as silently as a wrong `_C2PA_UUID` — every AVIF/HEIF
        from a legacy JUMBF writer simply scans clean.
        """
        assert ip._C2PA_UUID_ALT == b"c2pa" + bytes.fromhex("00110010800000AA00389B71")

    def test_c2pa_uuid_is_derived_from_the_hyphenated_spec_string(self):
        assert ip._C2PA_UUID == bytes.fromhex(ip._C2PA_BMFF_UUID_STR.replace("-", ""))

    # Spec literals, NOT ip._C2PA_UUID*. Building the fixture from the module
    # constant would make the test self-fulfilling: a mistyped constant would
    # produce a fixture carrying the same typo, scan would match it, and the
    # test would pass on exactly the defect it exists to catch. Verified — the
    # first version of this test did that and survived the 1->2 mutation.
    SPEC_UUIDS = {
        "primary": bytes.fromhex("D8FEC3D61B0E483C92975828877EC481"),
        "legacy-jumbf": b"c2pa" + bytes.fromhex("00110010800000AA00389B71"),
    }

    @pytest.mark.parametrize("spec_name", sorted(SPEC_UUIDS))
    def test_top_level_c2pa_uuid_box_is_detected_and_excised(self, spec_name):
        """Exercise the constants against the spec, do not merely pin them.

        Both spellings are consumed at the same two call sites, so the primary
        UUID's fixture coverage says nothing about the alternate. Build one file
        per spec-literal spelling and require the same outcome: scanned as c2pa,
        mined for generators, and physically removed by strip().
        """
        uuid = self.SPEC_UUIDS[spec_name]
        blob = b"jumb\x00jumdc2pa manifest softwareAgent gpt-image"
        data = _bmff_uuid_only(uuid, blob)

        rep = ip.scan(data)
        assert rep.parse_error == ""
        assert [(s.kind, s.where) for s in rep.signals] == [("c2pa", "ISOBMFF:uuid")], (
            f"a {spec_name} C2PA manifest scanned CLEAN — the module constant does not "
            "match the spec value this fixture was built from")
        assert "OpenAI gpt-image" in rep.generators and rep.is_ai_flagged

        res = ip.strip(data)
        assert res.clean and res.changed
        assert uuid not in res.data, "the uuid box survived the strip"
        assert not ip.scan(res.data).signals

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


def _bmff(items: list[tuple[int, bytes, bytes, bytes]], *, brand: bytes = b"avif") -> bytes:
    """Build a minimal, spec-shaped still AVIF/HEIF carrying the given items.

    ``items`` is (item_id, item_type, content_type, payload); content_type is
    used only for ``mime`` items, per ISO/IEC 14496-12 §8.11.6.

    Written for the `iso-mime-xmpmeta-heuristic` fix. The suite previously had
    no synthetic ISOBMFF at all — every AVIF test went through Pillow, so it
    could only produce files Pillow chooses to write, and a hand-crafted `mime`
    item with a vendor content_type was unreachable.
    """
    def box(typ: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body) + 8) + typ + body

    def full(typ: bytes, ver: int, flags: int, body: bytes) -> bytes:
        return box(typ, bytes([ver]) + flags.to_bytes(3, "big") + body)

    infes = b""
    for iid, ityp, ctype, _payload in items:
        b = struct.pack(">H", iid) + struct.pack(">H", 0) + ityp
        b += b"item\x00"                                   # item_name
        if ityp == b"mime":
            b += ctype + b"\x00"                           # content_type
        infes += full(b"infe", 2, 0, b)
    iinf = full(b"iinf", 0, 0, struct.pack(">H", len(items)) + infes)
    hdlr = full(b"hdlr", 0, 0, b"\x00" * 4 + b"pict" + b"\x00" * 12 + b"h\x00")
    pitm = full(b"pitm", 0, 0, struct.pack(">H", items[0][0]))

    # iloc offsets point into mdat, so lay the file out once with placeholder
    # offsets to learn its size, then again with the real ones.
    def build(offsets: list[int]) -> bytes:
        body = bytes([(4 << 4) | 4, 0]) + struct.pack(">H", len(items))
        for (iid, _t, _c, payload), off in zip(items, offsets):
            body += struct.pack(">H", iid) + struct.pack(">H", 0)
            body += struct.pack(">H", 1)                    # extent_count
            body += struct.pack(">I", off) + struct.pack(">I", len(payload))
        iloc = full(b"iloc", 0, 0, body)
        meta = full(b"meta", 0, 0, hdlr + pitm + iinf + iloc)
        ftyp = box(b"ftyp", brand + b"\x00" * 4 + brand + b"mif1")
        mdat = box(b"mdat", b"".join(p for _i, _t, _c, p in items))
        return ftyp + meta + mdat

    stub = build([0] * len(items))
    mdat_payload_start = len(stub) - sum(len(p) for _i, _t, _c, p in items)
    real, cur = [], mdat_payload_start
    for _i, _t, _c, payload in items:
        real.append(cur)
        cur += len(payload)
    return build(real)


def _bmff_uuid_only(uuid: bytes, blob: bytes, *, brand: bytes = b"avif") -> bytes:
    """An AVIF carrying nothing but a top-level C2PA `uuid` box.

    Deliberately has no `meta`: _strip_iso's uuid excision is a straight
    top-level cut that runs before any item reflow, so this isolates the
    constant-matching decision from the remux machinery.
    """
    ftyp = struct.pack(">I", 24) + b"ftyp" + brand + b"\x00" * 4 + brand + b"mif1"
    assert len(ftyp) == 24
    return ftyp + struct.pack(">I", 8 + 16 + len(blob)) + b"uuid" + uuid + blob


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

    def test_every_emitted_label_is_a_deliberate_ai_or_not_ai_decision(self):
        """The reverse direction — the one that catches a NEW generator.

        The orphan check above only finds dead labels. Adding a pattern without
        a matching _AI_GENERATORS entry — a real generator that silently fails
        to set is_ai_flagged — left the suite green. Every emitted label must
        therefore be classified: AI, or explicitly listed here as not-AI.

        These two are editors, not generators. A scanned photograph retouched in
        Photoshop, or a poster laid out in Canva, is not AI-generated; flagging
        either would make is_ai_flagged useless. Adding a label here is a
        deliberate act, which is the entire point.
        """
        not_ai = {"Adobe Photoshop", "Canva"}
        emitted = {label for _needle, label in ip._GENERATOR_PATTERNS}
        unclassified = emitted - ip._AI_GENERATORS - not_ai
        assert not unclassified, (
            f"pattern(s) emit {sorted(unclassified)}, which is neither in _AI_GENERATORS "
            "nor listed as a non-AI editor here — decide which, then record it")
        # and the not-AI list must not rot into a shadow allowlist
        assert not (not_ai & ip._AI_GENERATORS), "a label cannot be both AI and not-AI"
        assert not_ai <= emitted, f"stale non-AI label(s): {sorted(not_ai - emitted)}"

    def test_a_non_ai_editor_tag_does_not_set_the_ai_flag(self):
        """The behavioural half: the classification above must actually bite."""
        rep = ip.scan(_png(chunks=[(b"tEXt", b"Software\x00Canva")]))
        assert rep.generators == ["Canva"]
        assert rep.ai_generators == [] and not rep.is_ai_flagged


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

    def test_completeness_guard_catches_a_stripper_that_misses_a_record(self):
        """The guard must be able to go red, or `res.clean` proves nothing.

        Every other assertion in this file reads `res.clean` / `res.after`,
        which is the same quantity strip()'s own completeness guard computes —
        so deleting the guard changed no result. This installs a deliberately
        incomplete handler (drops the FIRST removable record, keeps the rest
        verbatim) and requires strip() to refuse the output and name the
        survivor. Without the guard the incomplete file is returned as clean.
        """
        data = _png(chunks=[(b"tEXt", b"Software\x00Midjourney v6"),
                            (b"tEXt", b"Comment\x00made with DALL-E")])
        before = ip.scan(data)
        assert len([s for s in before.signals if s.removable]) == 2, "fixture needs two records"

        def drops_only_the_first(d: bytes, policy, rep) -> tuple[bytes, list]:
            by_off = {s.offset: s for s in rep.signals}
            skip = sorted(s.offset for s in rep.signals
                          if s.removable and policy.wants(s.kind))[:1]
            out, removed = bytearray(ip._PNG_MAGIC), []
            for off, _ctype, _payload, total in ip._png_chunks(d):
                if off in skip:
                    removed.append(by_off[off])
                    continue
                out += d[off:off + total]
            return bytes(out), removed

        real = ip._STRIPPERS["png"]
        ip._STRIPPERS["png"] = drops_only_the_first
        try:
            with pytest.raises(ProvenanceError) as e:
                ip.strip(data)
        finally:
            ip._STRIPPERS["png"] = real
        assert "did not remove everything it claimed" in str(e.value)
        assert "generator_tag@PNG:tEXt" in str(e.value), "the survivor must be named"

        # And the control is honest: the REAL stripper on the same fixture passes.
        assert ip.strip(data).clean

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


def _pixel_identity_sweep(paths, pixels) -> tuple[int, int]:
    """Compare decoded pixels before/after strip over ``paths``.

    Returns ``(checked, undecodable)``. The split is load-bearing: "no file
    needed stripping" and "no file could be decoded" are opposite worlds, and
    collapsing them into one counter let the second report as the first.
    """
    checked = undecodable = 0
    for p in paths:
        data = p.read_bytes()
        rep = ip.scan(data)
        if rep.parse_error or not any(s.removable for s in rep.signals):
            continue
        res = ip.strip(data)
        try:
            before, after = pixels(data), pixels(res.data)
        except Exception:
            undecodable += 1                           # codec unavailable (e.g. AVIF)
            continue
        assert before == after, f"{p.name}: decoded pixels differ after strip"
        checked += 1
    return checked, undecodable


def _pixel_identity_verdict(checked: int, undecodable: int) -> tuple[str, str]:
    """Name the world we are actually in. Never report the reassuring one blind."""
    if checked:
        return "verified", f"{checked} file(s) pixel-identical after strip"
    if undecodable:
        return "xfail", (f"{undecodable} file(s) could not be decoded (codec unavailable) "
                         "— pixel identity NOT verified")
    return "skip", "nothing under sites/ needed stripping — corpus is clean"


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

    verdict, note = _pixel_identity_verdict(*_pixel_identity_sweep(_corpus(limit=120), pixels))
    if verdict == "xfail":
        # xfail, not skip: an AVIF-less environment is visibly NOT covered here.
        pytest.xfail(note)
    if verdict == "skip":
        pytest.skip(note)


class TestPixelIdentitySweepReportsWhichWorldItIsIn:
    """154 `pixel-identity-test-skip-reason-misattributes`.

    With every decode failing, the sweep reported "corpus is clean" — the one
    sentence that means the opposite of what had happened. These pin the
    counting and the verdict separately, because only the pair is falsifiable.
    """

    @staticmethod
    def _real_pixels(b: bytes) -> bytes:
        from PIL import Image, ImageSequence
        im = Image.open(io.BytesIO(b))
        return b"".join(f.convert("RGBA").tobytes() for f in ImageSequence.Iterator(im))

    def _stripworthy_png(self, tmp_path, name="x.png"):
        p = tmp_path / name
        p.write_bytes(_png(chunks=[(b"tEXt", b"Software\x00Midjourney v6")]))
        return p

    def test_a_decodable_file_counts_as_checked(self, tmp_path):
        pytest.importorskip("PIL")
        p = self._stripworthy_png(tmp_path)
        assert _pixel_identity_sweep([p], self._real_pixels) == (1, 0)

    def test_an_undecodable_file_counts_as_undecodable_not_as_clean(self, tmp_path):
        """The exact defect: the same file, the only change being a dead codec."""
        pytest.importorskip("PIL")
        p = self._stripworthy_png(tmp_path)

        def no_codec(_b: bytes) -> bytes:
            raise OSError("cannot identify image file")

        assert _pixel_identity_sweep([p], no_codec) == (0, 1)

    def test_a_clean_file_is_neither_checked_nor_undecodable(self, tmp_path):
        p = tmp_path / "clean.png"
        p.write_bytes(_png())                          # nothing removable
        assert _pixel_identity_sweep([p], self._real_pixels) == (0, 0)

    def test_the_verdict_flips_between_the_two_zero_checked_worlds(self):
        assert _pixel_identity_verdict(0, 3)[0] == "xfail"
        assert "NOT verified" in _pixel_identity_verdict(0, 3)[1]
        assert _pixel_identity_verdict(0, 0)[0] == "skip"
        assert "corpus is clean" in _pixel_identity_verdict(0, 0)[1]
        assert _pixel_identity_verdict(5, 3)[0] == "verified"


class TestIsoMimeItemsAreClassifiedByTheirDeclaredType:
    """153 `iso-mime-xmpmeta-heuristic`.

    `mime` items were classified by grepping their payload for the literal
    bytes "xmpmeta". The infe box's declared content_type — the only
    authoritative statement of what an item holds — was parsed nowhere.

    Two payloads walked straight through. The dangerous one is a vendor
    sidecar: no Signal meant `_strip_iso`'s drop set stayed empty, `strip()`
    returned the file unchanged, and a rescan by the same blind parser reported
    `clean=True` — with the payload still in the file and `raw_residue()`
    carrying no marker for it either.
    """

    PIC = bytes(range(64))
    VENDOR = b'{"hf-job-id":"8812","generator":"Higgsfield"}'
    BARE_RDF = (b'<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
                b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                b'<rdf:Description Iptc4xmpExt:digitalSourceType='
                b'"http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"/>'
                b'</rdf:RDF><?xpacket end="w"?>')

    def _img(self, ctype: bytes, payload: bytes) -> bytes:
        return _bmff([(1, b"av01", b"", self.PIC), (2, b"mime", ctype, payload)])

    def test_the_fixture_builder_produces_a_file_the_parser_accepts(self):
        """Guard the guard: if the synthetic AVIF did not parse, every
        assertion below would be about a rejected file, not about the fix."""
        rep = ip.scan(_bmff([(1, b"av01", b"", self.PIC)]))
        assert rep.container == "avif" and not rep.parse_error
        assert rep.signals == [], "a picture-only file must carry no signal"

    def test_a_vendor_sidecar_is_seen(self):
        rep = ip.scan(self._img(b"application/json", self.VENDOR))
        assert rep.signals, "a mime item with a vendor content_type was invisible"
        assert rep.ai_generators == ["Higgsfield"]
        assert rep.is_ai_flagged is True

    def test_a_vendor_sidecar_is_actually_evicted(self):
        """The half that mattered: before, strip() reported clean=True with
        bytes_removed=0 and the payload still in the file."""
        res = ip.strip(self._img(b"application/json", self.VENDOR))
        assert b"Higgsfield" not in res.data
        assert res.bytes_removed > 0 and res.clean and res.lossless

    def test_the_picture_item_survives_the_remux_byte_exactly(self):
        """Evicting a sibling item must not disturb the one that renders."""
        res = ip.strip(self._img(b"application/json", self.VENDOR))
        assert self.PIC in res.data
        out = res.data
        meta = next(b for b in ip._iso_boxes(out, 0, len(out)) if b.typ == b"meta")
        sub = list(ip._iso_boxes(out, meta.offset + meta.hdr + 4, meta.end))
        iloc = next(b for b in sub if b.typ == b"iloc")
        _info, entries = ip._parse_iloc(out, iloc)
        assert len(entries) == 1, "the dropped item is still registered in iloc"
        e = entries[0]
        blob = b"".join(out[e["base_offset"] + x["offset"]:
                            e["base_offset"] + x["offset"] + x["length"]] for x in e["extents"])
        assert blob == self.PIC, "iloc no longer resolves the picture to its own bytes"

    def test_xmp_without_the_optional_xmpmeta_wrapper_is_seen(self):
        """XMP part 1 permits a bare rdf:RDF root, and Adobe's toolkit has
        kXMP_OmitXMPMetaElement for exactly this."""
        assert b"xmpmeta" not in self.BARE_RDF, "fixture defeats its own purpose"
        rep = ip.scan(self._img(b"application/rdf+xml", self.BARE_RDF))
        assert any(s.kind == "iptc_ai" for s in rep.signals)
        assert rep.is_ai_flagged is True

    @pytest.mark.parametrize("ctype", [b"application/xml", b"text/xml", b"APPLICATION/RDF+XML"])
    def test_every_xml_content_type_routes_to_xmp(self, ctype):
        rep = ip.scan(self._img(ctype, self.BARE_RDF))
        assert any(s.kind == "iptc_ai" for s in rep.signals), f"{ctype!r} was not recognised"

    def test_an_unrecognised_mime_item_is_reported_not_hidden(self):
        """An opaque sidecar carries no AI marker, but it is still metadata and
        the operator is still entitled to know it was there."""
        rep = ip.scan(self._img(b"application/octet-stream", b"opaque bytes"))
        assert [s.kind for s in rep.signals] == ["other_metadata"]
        assert "content_type=application/octet-stream" in rep.signals[0].detail

    def test_a_malformed_infe_falls_back_to_the_payload_sniff(self):
        """Deciding from the declared type must not mean going blind when the
        declaration is missing — that would trade one silent miss for another."""
        img = self._img(b"application/rdf+xml", self.BARE_RDF)
        broken = img.replace(b"application/rdf+xml\x00", b"\x00" * 20, 1)
        assert len(broken) == len(img), "the fixture must stay the same length"
        rep = ip.scan(broken)
        assert any(s.kind == "iptc_ai" for s in rep.signals), \
            "no content_type AND no payload sniff = the original blind spot, restored"

    def test_content_type_is_recorded_so_the_operator_can_see_what_was_dropped(self):
        res = ip.strip(self._img(b"application/json", self.VENDOR))
        assert res.removed, "nothing was removed"
        joined = " ".join(s.detail for s in res.removed)
        assert "content_type=application/json" in joined or "Higgsfield" in joined

    PLAIN_XMP = (b'<?xpacket begin="" id="W5M0Mp"?>'
                 b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                 b'<rdf:Description dc:creator="Jane"/></rdf:RDF><?xpacket end="w"?>')

    def test_a_plain_xml_item_classifies_as_xmp_not_as_other(self):
        """Not cosmetic. `other_metadata` is the catch-all whose Policy.wants()
        returns True unconditionally, so misfiling XMP there makes the policy
        unreachable for ISO items — see the next test."""
        rep = ip.scan(self._img(b"application/rdf+xml", self.PLAIN_XMP))
        assert [s.kind for s in rep.signals] == ["xmp"]

    def test_keep_xmp_actually_keeps_an_iso_xmp_item(self):
        """The consequence. A policy the caller set is honoured only if the
        signal carries the kind that policy names."""
        img = self._img(b"application/rdf+xml", self.PLAIN_XMP)
        keep = ip.Policy(strip_xmp=False, strip_iptc=False)
        res = ip.strip(img, policy=keep)
        assert self.PLAIN_XMP in res.data, "--keep-xmp did not reach an ISOBMFF item"
        assert res.clean, "the policy's intent was achieved; the result must say so"
        assert not res.fully_stripped

    def test_the_default_policy_still_removes_it(self):
        """Guard the guard: a Policy that could never remove anything would
        pass the test above too."""
        res = ip.strip(self._img(b"application/rdf+xml", self.PLAIN_XMP))
        assert self.PLAIN_XMP not in res.data and res.fully_stripped


# =============================================================================
# regressions fixed in the 2026-08 audit (trackers 153/154)
# =============================================================================
class TestJpegOrientationIdempotence:
    """`_strip_jpeg` re-emitted its orientation APP1 unconditionally at out[2:2].

    Consequences, all reachable from `watermark_cleaner.py clean`:
      * a rotated JPEG grew +36 B on EVERY pass, stacking duplicate APP1 blocks
      * JFIF APP0 was displaced out of its mandatory first-segment position
      * bytes_removed went negative, and `Result.changed` (`bytes_removed > 0`)
        then read False on a file that had demonstrably changed
    """

    def _rotated(self) -> bytes:
        # A full Exif (padded, so NOT the orientation-only block) plus a COM, so
        # pass 1 genuinely has something to strip.
        exif = ip._minimal_exif_orientation(6) + b"\x00" * 8
        return _jpeg(segments=[(0xE1, exif), (0xFE, b"a comment worth 27 bytes...")])

    def _app1_count(self, data: bytes) -> int:
        return sum(1 for _o, m, pl, _t in ip._jpeg_segments(data)
                   if m == 0xE1 and ip._is_orientation_only_exif(pl))

    def test_stripping_twice_is_a_fixpoint(self):
        once = ip.strip(self._rotated()).data
        twice = ip.strip(once).data
        assert twice == once, "strip(strip(x)) must equal strip(x)"

    def test_the_orientation_block_is_not_duplicated(self):
        once = ip.strip(self._rotated()).data
        assert self._app1_count(once) == 1
        assert self._app1_count(ip.strip(once).data) == 1, \
            "a second pass appended a second identical orientation APP1"

    def test_orientation_survives_both_passes(self):
        twice = ip.strip(ip.strip(self._rotated()).data).data
        kept = [pl for _o, m, pl, _t in ip._jpeg_segments(twice) if m == 0xE1]
        assert kept and ip._exif_orientation(kept[0]) == 6

    def test_jfif_app0_stays_the_first_segment(self):
        """JFIF requires APP0 immediately after SOI; inserting at out[2:2]
        pushed it to second place on the very first pass."""
        once = ip.strip(self._rotated()).data
        markers = [m for _o, m, _pl, _t in ip._jpeg_segments(once) if 0xE0 <= m <= 0xEF]
        assert markers[0] == 0xE0, f"APP0 is no longer first: {[hex(m) for m in markers]}"

    def test_a_file_that_grew_is_never_reported_unchanged(self):
        """The decision. `changed` drives the CLI's STRIP/already-clean split."""
        res = ip.strip(self._rotated())
        assert len(res.data) != len(self._rotated()), "fixture must actually change size"
        assert res.changed, "a rewritten file reported itself unchanged"

    def test_the_second_pass_reports_no_change(self):
        once = ip.strip(self._rotated()).data
        again = ip.strip(once)
        assert again.data == once
        assert not again.changed, "an untouched file must not report changed"

    def test_keep_exif_does_not_add_a_second_orientation_block(self):
        """Same defect via a different route: when the policy KEEPS the Exif,
        the orientation already ships and re-emitting duplicates it."""
        res = ip.strip(self._rotated(), policy=Policy(strip_exif=False))
        app1 = [pl for _o, m, pl, _t in ip._jpeg_segments(res.data) if m == 0xE1]
        assert len(app1) == 1, "kept the original Exif AND re-emitted an orientation block"

    def test_changed_is_true_for_a_file_that_grew_with_nothing_removed(self):
        """`bytes_removed > 0` is a PROXY for "changed" and it is wrong in one
        direction: a rewrite that makes the file bigger yields a negative
        bytes_removed, which is not > 0, so the Result claimed nothing happened.

        The orientation fixpoint above closes the route that reached this in
        practice; the property itself is asserted here directly so the guard
        cannot rot back to the proxy unnoticed.
        """
        src = _jpeg()
        grown = src + b"\x00" * 16
        res = ip.Result(data=grown, container="jpeg",
                        before=ip.scan(src), after=ip.scan(src),
                        removed=[], bytes_removed=len(src) - len(grown))
        assert res.bytes_removed < 0, "the fixture must model a file that grew"
        assert res.changed, "a file that grew was reported unchanged"

    def test_changed_is_false_for_a_true_no_op(self):
        """Guard the guard: a `changed` that always returned True would pass above."""
        src = _jpeg()
        res = ip.Result(data=src, container="jpeg",
                        before=ip.scan(src), after=ip.scan(src),
                        removed=[], bytes_removed=0)
        assert not res.changed


class TestScanAndStripAgreeOnUnknownPngChunks:
    """`_strip_png` dropped unrecognised ancillary chunks that `_scan_png` never
    reported. Because `cmd_replace`/`cmd_cms` gate on the SCAN result, a PNG
    whose only provenance was an unknown chunk was recorded "already_clean" and
    the stripper written for exactly that case was never reached.
    """

    HIDDEN = b"hf-job-id=8812 trainedAlgorithmicMedia"

    def _img(self) -> bytes:
        return _png(chunks=[(b"hfJB", self.HIDDEN)])

    def test_scan_reports_the_unknown_chunk(self):
        rep = ip.scan(self._img())
        assert [s.where for s in rep.signals if s.length > 0] == ["PNG:hfJB"]

    def test_the_pipeline_no_longer_calls_it_already_clean(self):
        """THE decision: cmd_replace/cmd_cms branch on exactly this."""
        rep = ip.scan(self._img())
        assert rep.is_ai_flagged, "an AI marker in an unknown chunk read as clean"
        assert rep.removable_bytes > 0
        assert "Higgsfield" in rep.ai_generators

    def test_scan_and_strip_agree_offset_for_offset(self):
        """The invariant that makes the two halves impossible to drift apart."""
        d = self._img()
        scanned = {s.offset for s in ip.scan(d).signals if s.length > 0}
        stripped = {s.offset for s in ip.strip(d).removed}
        assert scanned == stripped, f"scan {sorted(scanned)} != strip {sorted(stripped)}"

    def test_the_bytes_really_go(self):
        res = ip.strip(self._img())
        assert self.HIDDEN not in res.data and res.clean and res.lossless

    def test_render_and_animation_chunks_are_not_reported_as_metadata(self):
        """Guard the guard: a scan that reported EVERY chunk would pass above
        and would make every ordinary PNG look dirty."""
        actl = struct.pack(">II", 1, 0)
        clean = _png(chunks=[(b"gAMA", struct.pack(">I", 45455)), (b"acTL", actl),
                             (b"iCCP", b"p\x00\x00" + zlib.compress(b"icc"))])
        rep = ip.scan(clean)
        assert [s for s in rep.signals if s.removable] == []
        assert not ip.strip(clean).removed

    def test_keeping_the_breadcrumbs_still_keeps_an_unknown_chunk(self):
        """scan() now raises a Signal for these; the policy must still win."""
        d = self._img()
        res = ip.strip(d, policy=Policy(strip_generator_tags=False, strip_xmp=False,
                                        strip_iptc=False))
        assert res.data == d, "--keep-generator-tags silently lost an unknown chunk"


APPENDED_XMP = (
    b'<?xpacket begin="" id="W5M0Mp"?><x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF>'
    b'<rdf:Description xmp:CreatorTool="Midjourney" Iptc4xmpExt:digitalSourceType='
    b'"http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"/>'
    b"</rdf:RDF></x:xmpmeta><?xpacket end='w'?>"
)


class TestJpegTrailerAfterEoi:
    """Everything from SOS onward was copied verbatim and inspected by nobody.

    An XMP packet appended after FFD9 therefore survived a strip that reported
    `clean=True, bytes_removed=0` — while `raw_residue()`, the backstop, found
    it easily. The backstop existed; it just was not wired into scan().
    """

    def _with_trailer(self, trailer: bytes) -> bytes:
        return _jpeg() + trailer

    def test_scan_sees_the_appended_packet(self):
        rep = ip.scan(self._with_trailer(APPENDED_XMP))
        assert any(s.where == "JPEG:trailer" for s in rep.signals)

    def test_the_appended_packet_flips_the_ai_verdict(self):
        """THE decision — `--fail-on-flagged` and the crawler both read this."""
        rep = ip.scan(self._with_trailer(APPENDED_XMP))
        assert rep.is_ai_flagged, "an appended AI packet scanned as an ordinary photo"
        assert "Midjourney" in rep.ai_generators

    def test_strip_actually_removes_it(self):
        res = ip.strip(self._with_trailer(APPENDED_XMP))
        assert b"trainedAlgorithmicMedia" not in res.data
        assert b"Midjourney" not in res.data
        assert res.changed and res.bytes_removed > 0 and res.clean

    def test_removing_the_trailer_still_verifies_lossless(self):
        """The digest hashed data[SOS:] including the trailer. Dropping the
        trailer without narrowing the digest would fail EVERY such strip."""
        orig = self._with_trailer(APPENDED_XMP)
        res = ip.strip(orig)
        ok, note = ip.verify_lossless(orig, res.data)
        assert ok, note
        assert res.lossless

    def test_a_plain_jpeg_is_unaffected(self):
        """Guard the guard: no EOI-less or trailer-less file may gain a signal."""
        rep = ip.scan(_jpeg())
        assert not [s for s in rep.signals if s.where == "JPEG:trailer"]
        assert ip.strip(_jpeg()).data == _jpeg()

    def test_the_entropy_stream_is_still_copied_byte_for_byte(self):
        res = ip.strip(self._with_trailer(APPENDED_XMP))
        assert b"\xfe\xed\xfa\xce\xde\xad\xbe\xef" in res.data, "entropy data was cut"
        assert res.data.endswith(b"\xff\xd9")


class TestMultiPictureJpeg:
    """An MPO's secondary image was copied verbatim past the first SOS and never
    scanned, while the APP2 MPF index that addresses it was dropped as
    'other_metadata' — orphaning the secondary AND leaving its provenance intact.
    """

    def _mpo(self) -> bytes:
        primary = _jpeg(segments=[(0xE2, b"MPF\x00" + b"\x00" * 24)])
        secondary = _jpeg(segments=[(0xE1, b"http://ns.adobe.com/xap/1.0/\x00" + APPENDED_XMP)])
        return primary + secondary

    def test_the_secondary_image_is_no_longer_invisible(self):
        rep = ip.scan(self._mpo())
        assert any(s.where.endswith("@secondary") for s in rep.signals), \
            "the secondary image's own APP segments were never walked"

    def test_the_secondarys_provenance_flips_the_verdict(self):
        """THE decision. It scanned as `signals=[('other_metadata','JPEG:APP2')],
        is_ai_flagged=False, generators=[]`."""
        rep = ip.scan(self._mpo())
        assert rep.is_ai_flagged
        assert "Midjourney" in rep.ai_generators

    def test_strip_refuses_rather_than_orphaning_the_secondary(self):
        """The honest short path: dropping the MPF index leaves the secondary
        unreachable and its XMP intact, and the old code called that clean=True."""
        with pytest.raises(ProvenanceError, match="multi-picture"):
            ip.strip(self._mpo())

    def test_the_secondary_is_reported_as_not_removable(self):
        """It is picture data. Claiming it is strippable would be the same lie
        in the other direction."""
        rep = ip.scan(self._mpo())
        trailer = [s for s in rep.signals if s.where == "JPEG:trailer"]
        assert trailer and not trailer[0].removable

    def test_an_ordinary_two_segment_jpeg_is_not_mistaken_for_an_mpo(self):
        assert ip.strip(_jpeg(segments=[(0xFE, b"just a comment")])).clean


def _bmff_idat(exif_payload: bytes, *, pixels: bytes = b"\xa5" * 16) -> bytes:
    """A still HEIF whose Exif item uses ``construction_method=1`` (idat-relative).

    `_bmff` cannot express this: it emits iloc version 0, which has no
    construction_method field at all — which is why no fixture in the suite ever
    exercised the non-zero methods (grep 'construction' returned nothing).
    """
    def box(typ: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body) + 8) + typ + body

    def full(typ: bytes, ver: int, flags: int, body: bytes) -> bytes:
        return box(typ, bytes([ver]) + flags.to_bytes(3, "big") + body)

    infes = (full(b"infe", 2, 0, struct.pack(">HH", 1, 0) + b"Exif" + b"exif\x00")
             + full(b"infe", 2, 0, struct.pack(">HH", 2, 0) + b"av01" + b"pic\x00"))
    iinf = full(b"iinf", 0, 0, struct.pack(">H", 2) + infes)
    hdlr = full(b"hdlr", 0, 0, b"\x00" * 4 + b"pict" + b"\x00" * 12 + b"h\x00")
    pitm = full(b"pitm", 0, 0, struct.pack(">H", 2))
    idat = box(b"idat", exif_payload)

    def build(pic_off: int) -> bytes:
        body = bytes([(4 << 4) | 4, 0]) + struct.pack(">H", 2)
        body += struct.pack(">HHH", 1, 1, 0) + struct.pack(">H", 1)     # item 1, method 1
        body += struct.pack(">II", 0, len(exif_payload))                 # -> idat payload + 0
        body += struct.pack(">HHH", 2, 0, 0) + struct.pack(">H", 1)     # item 2, method 0
        body += struct.pack(">II", pic_off, len(pixels))                 # -> mdat
        iloc = full(b"iloc", 1, 0, body)
        meta = full(b"meta", 0, 0, hdlr + pitm + iinf + iloc + idat)
        ftyp = box(b"ftyp", b"mif1" + b"\x00" * 4 + b"mif1heic")
        return ftyp + meta + box(b"mdat", pixels)

    return build(len(build(0)) - len(pixels))


class TestIsobmffConstructionMethods:
    """`_scan_iso` resolved every extent as ``base_offset + offset``, an absolute
    file offset, with no construction_method check.

    For a method-1 item that address is meaningless: the payload lives in the
    meta-level ``idat`` box. The scanner therefore mined AI markers out of
    whichever unrelated bytes sat at that position — reporting
    ``generators=[], is_ai_flagged=False`` on a file where
    ``b"Midjourney" in data`` was plainly True.
    """

    EXIF = (b"\x00\x00\x00\x06Exif\x00\x00MM\x00*\x00\x00\x00\x08"
            b"Software\x00Midjourney v7 hf-job-id 8812")

    def test_the_fixture_really_is_idat_relative(self):
        """Derive it from the file, never assume the builder did its job."""
        data = _bmff_idat(self.EXIF)
        top = ip._iso_boxes(data, 0, len(data))
        meta = next(b for b in top if b.typ == b"meta")
        inner = ip._iso_boxes(data, meta.offset + meta.hdr + 4, meta.end)
        iloc = next(b for b in inner if b.typ == b"iloc")
        _info, entries = ip._parse_iloc(data, iloc)
        assert {e["item_id"]: e["construction"] for e in entries} == {1: 1, 2: 0}
        assert any(b.typ == b"idat" for b in inner)

    def test_the_marker_is_no_longer_mined_from_the_wrong_bytes(self):
        """THE decision. `b"Midjourney" in data` was True the whole time."""
        data = _bmff_idat(self.EXIF)
        assert b"Midjourney" in data
        rep = ip.scan(data)
        assert rep.parse_error == ""
        assert "Midjourney" in rep.generators, "the idat payload was never read"
        assert rep.is_ai_flagged
        assert "Higgsfield" in rep.generators

    def test_the_item_is_still_reported(self):
        rep = ip.scan(_bmff_idat(self.EXIF))
        assert [s.kind for s in rep.signals] == ["exif"]

    def test_an_unresolvable_method_reads_nothing_rather_than_guessing(self):
        """Method 2 is item-relative. Reading the absolute offset instead would
        put arbitrary bytes into the report; reporting nothing at all would hide
        the item. It must do neither."""
        data = bytearray(_bmff_idat(self.EXIF))
        at = data.find(struct.pack(">HHH", 1, 1, 0) + struct.pack(">H", 1))
        assert at > 0, "fixture layout changed"
        data[at:at + 6] = struct.pack(">HHH", 1, 2, 0)          # method 1 -> 2
        rep = ip.scan(bytes(data))
        assert [s.kind for s in rep.signals] == ["exif"], "the item vanished from the report"
        assert "construction_method 2" in rep.signals[0].detail
        assert rep.generators == [], "bytes were read from an unresolvable extent"

    def test_method_0_still_resolves_exactly_as_before(self):
        """Guard the guard: a resolver that returned b'' for everything would
        satisfy the negative assertions above."""
        rep = ip.scan(_bmff([(1, b"Exif", b"", b"Exif\x00\x00 Software Midjourney"),
                             (2, b"av01", b"", b"\xa5" * 16)]))
        assert "Midjourney" in rep.generators

    def test_strip_still_refuses_the_idat_item(self):
        """The strip half was already fail-safe; keep it that way."""
        with pytest.raises(ProvenanceError, match="construction_method 1"):
            ip.strip(_bmff_idat(self.EXIF))


def _bmff_meta_no_index(mdat: bytes) -> bytes:
    """ftyp + meta(hdlr only) + mdat — a `meta` with no iinf and no iloc.

    Real files look like this when the item index sits in a box this parser does
    not index, and `_iso_pixel_digest` bailed out on exactly this shape.
    """
    def box(typ: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body) + 8) + typ + body

    hdlr = box(b"hdlr", b"\x00" * 4 + b"\x00" * 4 + b"pict" + b"\x00" * 12 + b"h\x00")
    meta = box(b"meta", b"\x00\x00\x00\x00" + hdlr)
    return box(b"ftyp", b"avif" + b"\x00" * 4 + b"avifmif1") + meta + box(b"mdat", mdat)


class TestIsoDigestCannotBeSilentlyNarrow:
    """`_iso_pixel_digest` returned the digest of the EMPTY STRING whenever a
    `meta` existed but iinf/iloc did not — so two files differing in their
    entire mdat verified as pixel-identical. A proof that cannot fail is not a
    proof.
    """

    def test_two_files_differing_only_in_mdat_are_not_identical(self):
        a = _bmff_meta_no_index(b"\x11" * 64)
        b = _bmff_meta_no_index(b"\x22" * 64)
        assert len(a) == len(b), "the fixtures must differ ONLY in mdat content"
        assert ip._iso_pixel_digest(a) != ip._iso_pixel_digest(b)

    def test_verify_lossless_rejects_that_pair(self):
        """THE decision — this is the answer callers actually act on."""
        ok, note = ip.verify_lossless(_bmff_meta_no_index(b"\x11" * 64),
                                      _bmff_meta_no_index(b"\x22" * 64))
        assert not ok, note

    def test_the_digest_is_never_the_empty_sha256(self):
        empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert ip._iso_pixel_digest(_bmff_meta_no_index(b"\x11" * 64)) != empty

    def test_an_identical_pair_still_verifies(self):
        """Guard the guard: a digest that just hashed the whole file would pass
        every assertion above and reject every legitimate strip."""
        d = _bmff_meta_no_index(b"\x11" * 64)
        ok, _note = ip.verify_lossless(d, d)
        assert ok

    def test_mdat_bytes_no_extent_claims_are_still_hashed(self):
        """The other half: with a full item index present, bytes inside mdat
        that no iloc extent accounts for used to fall outside the digest."""
        base = _bmff([(1, b"av01", b"", b"\xa5" * 16)])
        assert base.endswith(b"\xa5" * 16)
        a, b = base + b"\x01" * 8, base + b"\x02" * 8
        # extend the mdat box header so the appended bytes are INSIDE mdat
        def grow(d: bytes) -> bytes:
            top = ip._iso_boxes(d, 0, len(d) - 8)
            mdat = next(x for x in top if x.typ == b"mdat")
            return (d[:mdat.offset] + struct.pack(">I", mdat.size + 8)
                    + d[mdat.offset + 4:])
        a, b = grow(a), grow(b)
        assert ip._iso_pixel_digest(a) != ip._iso_pixel_digest(b)


class TestTrailingC2paUuidIsNotRefusedOverAMovieBox:
    """OR-5. The movie-box guard refused every uuid excision, including one that
    provably shifts nothing: a uuid box beginning at or after the end of the
    last mdat. Track samples live in mdat, and mdat does not move.
    """

    def _with_moov(self, *, trailing: bool) -> bytes:
        def box(typ: bytes, body: bytes) -> bytes:
            return struct.pack(">I", len(body) + 8) + typ + body
        blob = b"jumb\x00jumdc2pa manifest softwareAgent gpt-image"
        uuid = box(b"uuid", ip._C2PA_UUID + blob)
        ftyp = box(b"ftyp", b"avif" + b"\x00" * 4 + b"avifmif1")
        moov = box(b"moov", b"\x00" * 16)
        mdat = box(b"mdat", b"\xa5" * 32)
        return ftyp + moov + mdat + uuid if trailing else ftyp + moov + uuid + mdat

    def test_a_trailing_uuid_is_excised(self):
        data = self._with_moov(trailing=True)
        res = ip.strip(data)
        assert ip._C2PA_UUID not in res.data
        assert res.clean and res.lossless and res.changed

    def test_the_mdat_is_byte_identical_afterwards(self):
        """Why it is safe at all: every byte a stco offset could address stays
        exactly where it was."""
        data = self._with_moov(trailing=True)
        out = ip.strip(data).data
        assert out == data[:data.find(b"uuid") - 4]

    def test_a_uuid_BEFORE_mdat_is_still_refused(self):
        """Guard the guard: cutting there shifts mdat, and the digest hashes
        mdat bodies, so verify_lossless could not see the damage."""
        with pytest.raises(ProvenanceError, match="movie box"):
            ip.strip(self._with_moov(trailing=False))


class TestSvgProvenanceOutsideMetadata:
    """`_SVG_META_ELEMENTS` was ('metadata', 'c2pa:manifest'), so provenance
    written anywhere else was neither reported nor stripped — and strip()
    returned `clean=True, bytes_removed=0` on a file that plainly carried it.
    """

    DIRTY = (b'<!-- Generator: Recraft AI 2026, hf-job-id: 8812 -->\n'
             b'<svg xmlns="http://www.w3.org/2000/svg">'
             b'<title>A blue square</title>'
             b'<desc>Generated with Midjourney v7</desc>'
             b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description '
             b'Iptc4xmpExt:digitalSourceType="http://cv.iptc.org/newscodes/'
             b'digitalsourcetype/trainedAlgorithmicMedia"/></rdf:RDF></x:xmpmeta>'
             b'<rect width="10" height="10"/></svg>')

    def test_the_verdict_flips(self):
        """THE decision: scan reported signals=[], generators=[],
        is_ai_flagged=False on this exact document."""
        rep = ip.scan(self.DIRTY)
        assert rep.is_ai_flagged
        assert "Recraft" in rep.generators and "Higgsfield" in rep.generators
        assert "Midjourney" in rep.generators

    def test_each_hiding_place_is_reported_separately(self):
        wheres = {s.where for s in ip.scan(self.DIRTY).signals}
        assert "SVG:comment" in wheres
        assert "SVG:<desc>" in wheres
        assert "SVG:<x:xmpmeta>" in wheres

    def test_strip_actually_removes_them(self):
        res = ip.strip(self.DIRTY)
        assert res.changed and res.bytes_removed > 0
        assert b"Recraft" not in res.data
        assert b"Midjourney" not in res.data
        assert b"trainedAlgorithmicMedia" not in res.data
        assert res.clean

    def test_the_rendered_tree_survives(self):
        res = ip.strip(self.DIRTY)
        assert b'<rect width="10" height="10"/>' in res.data
        assert b"<svg" in res.data and b"</svg>" in res.data
        assert res.lossless

    def test_the_accessible_name_is_never_deleted(self):
        """<title> is what a screen reader announces. Mining it is right;
        deleting it is an accessibility regression, not a strip."""
        dirty = self.DIRTY.replace(b"<title>A blue square</title>",
                                   b"<title>Made with Midjourney</title>")
        rep = ip.scan(dirty)
        title = [s for s in rep.signals if s.where == "SVG:<title>"]
        assert title and not title[0].removable
        assert b"<title>Made with Midjourney</title>" in ip.strip(dirty).data

    def test_an_ordinary_svg_is_still_left_completely_alone(self):
        """Guard the guard. Reporting EVERY comment/desc/title would make the
        default policy delete licence headers and author descriptions."""
        clean = (b'<!-- Copyright 2026 Acme Corp. All rights reserved. -->\n'
                 b'<svg xmlns="http://www.w3.org/2000/svg">'
                 b'<title>Logo</title><desc>The company logo, in blue.</desc>'
                 b'<rect width="10" height="10"/></svg>')
        rep = ip.scan(clean)
        assert rep.signals == [] and not rep.is_ai_flagged
        assert ip.strip(clean).data == clean

    def test_a_document_level_xpacket_wrapper_is_caught(self):
        doc = (b'<svg xmlns="http://www.w3.org/2000/svg"><rect/>'
               b'<?xpacket begin="" id="W5M0Mp"?><rdf:RDF>CreatorTool Midjourney'
               b"</rdf:RDF><?xpacket end='w'?></svg>")
        rep = ip.scan(doc)
        assert rep.is_ai_flagged
        res = ip.strip(doc)
        assert b"xpacket" not in res.data and b"Midjourney" not in res.data


class TestGenericGeneratorNamesDoNotFlagCaptions:
    """Bare 'Gemini', 'Imagen', 'Grok', 'Recraft', 'Ideogram' matched ANYWHERE
    in a metadata record, free caption text included — so a photograph flipped
    is_ai_flagged, and `--fail-on-flagged` would have failed CI on it.
    """

    CAPTION = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description '
               b'xmp:CreatorTool="Adobe Lightroom 14.2">'
               b'<dc:description>Gemini constellation over Vancouver, shot on a '
               b'Google Pixel</dc:description></rdf:Description></rdf:RDF></x:xmpmeta>')
    TOOL = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description '
            b'xmp:CreatorTool="Gemini"/></rdf:RDF></x:xmpmeta>')

    def _png_xmp(self, xmp: bytes) -> bytes:
        return _png(chunks=[(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + xmp)])

    def test_a_caption_mentioning_gemini_is_not_ai_flagged(self):
        rep = ip.scan(self._png_xmp(self.CAPTION))
        assert not rep.is_ai_flagged, "a photograph was reported AI-generated"
        assert rep.ai_generators == []

    def test_but_the_match_is_still_reported_to_the_operator(self):
        """Suppressing the FLAG must not mean hiding the evidence."""
        rep = ip.scan(self._png_xmp(self.CAPTION))
        assert "Google Gemini" in rep.generators

    def test_the_same_name_in_creatortool_does_flag(self):
        """THE other half. A guard that never flagged would pass the test above."""
        rep = ip.scan(self._png_xmp(self.TOOL))
        assert rep.is_ai_flagged
        assert rep.ai_generators == ["Google Gemini"]

    @pytest.mark.parametrize("needle", [b"Grok", b"Imagen", b"Recraft", b"Ideogram"])
    def test_every_generic_needle_behaves_the_same_way(self, needle):
        caption = b"<dc:description>a photo of a " + needle + b" in the wild</dc:description>"
        field = b'<rdf:Description xmp:CreatorTool="' + needle + b'"/>'
        assert not ip.scan(self._png_xmp(caption)).is_ai_flagged
        assert ip.scan(self._png_xmp(field)).is_ai_flagged

    def test_an_unambiguous_name_flags_from_anywhere(self):
        """Guard the guard: field-scoping must not be applied to needles that
        were never ambiguous, or every non-XMP container stops flagging."""
        rep = ip.scan(self._png_xmp(b"<dc:description>made with Midjourney</dc:description>"))
        assert rep.is_ai_flagged and rep.ai_generators == ["Midjourney"]


class TestGeneratorPatternCoverage:
    """No pattern for the Stable-Diffusion / ComfyUI PNG text conventions or
    most 2026 vendors, and 'Amazon Nova Canvas' resolved to the NON-AI editor
    label 'Canva' — so an AWS-generated image scanned as merely edited.
    """

    @pytest.mark.parametrize("blob,label", [
        (b"Software\x00Amazon Nova Canvas", "Amazon Nova"),
        (b"parameters\x00a cat, Negative prompt: blurry, Steps: 20", "Stability AI"),
        (b"Software\x00Model hash: a1b2c3d4", "Stability AI"),
        (b"Software\x00ComfyUI", "ComfyUI"),
        (b"Software\x00AUTOMATIC1111 webui", "AUTOMATIC1111"),
        (b"Software\x00InvokeAI 5.4", "InvokeAI"),
        (b"Software\x00Fooocus v2", "Fooocus"),
        (b"Software\x00FLUX.2 [dev]", "Black Forest Labs FLUX"),
        (b"Software\x00Runway Gen-4", "Runway"),
        (b"Software\x00Sora", "OpenAI Sora"),
        (b"Software\x00Kling 2.5", "Kuaishou Kling"),
        (b"Software\x00Hunyuan Image", "Tencent Hunyuan"),
        (b"Software\x00Krea", "Krea AI"),
        (b"Software\x00Meta AI", "Meta AI"),
        (b"Software\x00ideogram/2.0", "Ideogram"),
        (b"Software\x00recraft v3", "Recraft"),
    ])
    def test_each_generator_is_recognised_and_flags(self, blob, label):
        rep = ip.scan(_png(chunks=[(b"tEXt", blob)]))
        assert label in rep.generators, f"{blob!r} produced {rep.generators}"
        assert rep.is_ai_flagged, f"{label} did not set the AI flag"

    def test_nova_canvas_is_not_the_canva_editor(self):
        """THE decision. 'Canva' is a substring of 'Amazon Nova Canvas', so the
        AWS generator resolved to the non-AI editor label and did not flag."""
        rep = ip.scan(_png(chunks=[(b"tEXt", b"Software\x00Amazon Nova Canvas")]))
        assert "Canva" not in rep.generators
        assert rep.ai_generators == ["Amazon Nova"] and rep.is_ai_flagged

    def test_the_canva_editor_itself_still_resolves(self):
        """Guard the guard: an anchor that broke 'Canva' outright would pass."""
        rep = ip.scan(_png(chunks=[(b"tEXt", b"Software\x00Canva")]))
        assert rep.generators == ["Canva"] and not rep.is_ai_flagged

    def test_flux_does_not_match_mid_word(self):
        rep = ip.scan(_png(chunks=[(b"tEXt", b"Comment\x00measured the INFLUX. done")]))
        assert "Black Forest Labs FLUX" not in rep.generators


class TestIccProfileIsMined:
    """`keep_icc` defaults True — dropping a profile shifts colours — so a
    vendor name inside one SHIPS and survives every future run. The scanners
    skipped the payload before the miner saw it, producing a confident
    "clean, 0 signals, not AI-flagged".
    """

    DESC = b"desc\x00\x00\x00\x00Adobe Firefly generated profile hf-job-id 42"

    def test_jpeg_icc_is_mined(self):
        rep = ip.scan(_jpeg(segments=[(0xE2, b"ICC_PROFILE\x00\x01\x01" + self.DESC)]))
        assert "Adobe Firefly" in rep.generators and "Higgsfield" in rep.generators

    def test_it_flips_the_verdict(self):
        """THE decision — the miner WOULD have found it; it was never handed
        the payload."""
        rep = ip.scan(_jpeg(segments=[(0xE2, b"ICC_PROFILE\x00\x01\x01" + self.DESC)]))
        assert rep.is_ai_flagged

    def test_the_profile_is_still_byte_identical_after_a_default_strip(self):
        """Non-negotiable: dropping ICC shifts client colours. Reporting it must
        not start removing it."""
        orig = _jpeg(segments=[(0xE2, b"ICC_PROFILE\x00\x01\x01" + self.DESC)])
        res = ip.strip(orig)
        assert self.DESC in res.data
        assert res.data == orig, "the retained profile must not move or change"

    def test_it_is_reported_as_not_removable(self):
        rep = ip.scan(_jpeg(segments=[(0xE2, b"ICC_PROFILE\x00\x01\x01" + self.DESC)]))
        icc = [s for s in rep.signals if "ICC" in s.detail]
        assert icc and not icc[0].removable

    def test_png_iccp_is_decompressed_then_mined(self):
        payload = b"p\x00\x00" + zlib.compress(self.DESC)
        rep = ip.scan(_png(chunks=[(b"iCCP", payload)]))
        assert "Adobe Firefly" in rep.generators and rep.is_ai_flagged

    def test_webp_iccp_is_mined(self):
        rep = ip.scan(_webp(chunks=[(b"ICCP", self.DESC)], vp8x_flags=0x20))
        assert "Adobe Firefly" in rep.generators and rep.is_ai_flagged

    def test_a_plain_profile_produces_no_signal(self):
        """Guard the guard: every image with a colour profile must not become
        'dirty' just because the profile now gets read."""
        rep = ip.scan(_jpeg(segments=[(0xE2, b"ICC_PROFILE\x00\x01\x01desc\x00sRGB IEC61966")]))
        assert rep.signals == [] and not rep.is_ai_flagged


class TestOrientationSalvageIsNotJpegOnly:
    """`keep_orientation` was implemented ONLY inside `_strip_jpeg`, while the
    Policy docstring stated an unqualified contract. The same image stripped as
    a WebP or PNG came out silently rotated — the exact harm the option exists
    to prevent, and the reason it defaults True.
    """

    TIFF6 = staticmethod(lambda: ip._minimal_tiff_orientation(6))

    def _png_rot(self) -> bytes:
        # Padded, so it is NOT the module's own minimal block.
        return _png(chunks=[(b"eXIf", ip._minimal_tiff_orientation(6) + b"\x00" * 8)])

    def _webp_rot(self) -> bytes:
        return _webp(chunks=[(b"EXIF", ip._minimal_tiff_orientation(6) + b"\x00" * 8)],
                     vp8x_flags=ip._WEBP_VP8X_EXIF)

    def _png_orientation(self, data: bytes) -> int:
        for _off, ctype, payload, _t in ip._png_chunks(data):
            if ctype == b"eXIf":
                return ip._tiff_orientation(payload)
        return 0

    def _webp_orientation(self, data: bytes) -> int:
        for _off, fourcc, payload, _t in ip._webp_chunks(data):
            if fourcc == b"EXIF":
                return ip._tiff_orientation(ip._webp_exif_tiff(payload))
        return 0

    def test_the_png_fixture_really_is_rotated(self):
        assert self._png_orientation(self._png_rot()) == 6

    def test_png_orientation_survives_the_strip(self):
        """THE decision: removed=['exif'], clean=True, and the photo on its side."""
        res = ip.strip(self._png_rot())
        assert res.removed, "the fixture must actually have something stripped"
        assert self._png_orientation(res.data) == 6, "the PNG was silently rotated"

    def test_webp_orientation_survives_the_strip(self):
        res = ip.strip(self._webp_rot())
        assert res.removed
        assert self._webp_orientation(res.data) == 6, "the WebP was silently rotated"

    def test_the_webp_exif_feature_bit_stays_set(self):
        """An EXIF chunk still ships, so clearing the VP8X bit makes the file
        malformed to a strict decoder."""
        out = ip.strip(self._webp_rot()).data
        vp8x = next(pl for _o, fc, pl, _t in ip._webp_chunks(out) if fc == b"VP8X")
        assert vp8x[0] & ip._WEBP_VP8X_EXIF

    @pytest.mark.parametrize("kind", ["png", "webp"])
    def test_stripping_twice_is_a_fixpoint(self, kind):
        orig = self._png_rot() if kind == "png" else self._webp_rot()
        once = ip.strip(orig).data
        assert ip.strip(once).data == once

    @pytest.mark.parametrize("kind", ["png", "webp"])
    def test_the_provenance_still_goes(self, kind):
        """Guard the guard: re-emitting must not mean keeping the original."""
        pad = b"Software Midjourney" + ip._minimal_tiff_orientation(6)
        orig = (_png(chunks=[(b"eXIf", pad)]) if kind == "png"
                else _webp(chunks=[(b"EXIF", pad)], vp8x_flags=ip._WEBP_VP8X_EXIF))
        res = ip.strip(orig)
        assert b"Midjourney" not in res.data and res.clean and res.lossless

    @pytest.mark.parametrize("kind", ["png", "webp"])
    def test_orientation_1_is_not_reemitted(self, kind):
        pad = ip._minimal_tiff_orientation(1) + b"\x00" * 8
        orig = (_png(chunks=[(b"eXIf", pad)]) if kind == "png"
                else _webp(chunks=[(b"EXIF", pad)], vp8x_flags=ip._WEBP_VP8X_EXIF))
        got = ip.strip(orig).data
        assert b"eXIf" not in got and b"EXIF" not in got

    @pytest.mark.parametrize("kind", ["png", "webp"])
    def test_the_policy_can_still_decline(self, kind):
        orig = self._png_rot() if kind == "png" else self._webp_rot()
        got = ip.strip(orig, policy=Policy(keep_orientation=False)).data
        assert b"eXIf" not in got and b"EXIF" not in got

    def test_png_pixels_are_untouched(self):
        orig = self._png_rot()
        res = ip.strip(orig)
        assert res.lossless
        ok, note = ip.verify_lossless(orig, res.data)
        assert ok, note


class TestNoDeadPrivateHelpers:
    """`_png_rebuild_chunk` and `_iso_find` sat with zero call sites anywhere —
    definitions only, 0% coverage, and `_iso_find`'s iinf version-1 branch was
    unvalidated guesswork about a 2-vs-4-byte count field that had never
    executed. CLAUDE.md's Script Creation Gate covers new exported functions
    with no callers; nothing enforced it, so this does.
    """

    def _defs_and_refs(self):
        import ast
        src = (ROOT / "scripts" / "image_provenance.py").read_text()
        tree = ast.parse(src)
        defs = [n.name for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name.startswith("_") and not n.name.startswith("__")]
        haystack = "\n".join(
            (ROOT / "scripts" / f).read_text()
            for f in ("image_provenance.py", "watermark_cleaner.py",
                      "tests/test_image_provenance.py",
                      "tests/test_image_provenance_stress.py")
        )
        return defs, haystack

    def test_every_private_helper_has_a_caller(self):
        defs, haystack = self._defs_and_refs()
        assert defs, "found no helpers to check — the AST walk is broken"
        dead = []
        for name in defs:
            # one hit is the `def` itself; anything more is a reference
            if haystack.count(name) <= 1:
                dead.append(name)
        assert not dead, (
            f"defined but never called: {sorted(dead)} — wire it in or delete it "
            "(CLAUDE.md Script Creation Gate)")

    def test_the_predicate_can_actually_fail(self):
        """Verify the verifier. Run the SAME predicate over a haystack holding
        nothing but a definition and require it to call that helper dead —
        otherwise the test above would pass on a module full of dead code.

        (Naming a sentinel string here would not work: this file is part of the
        haystack, so the literal would find itself.)
        """
        name = "_orphan" + "ed_helper"
        haystack = f"def {name}():\n    return 1\n"
        assert haystack.count(name) <= 1, "the dead-code predicate cannot see a definition-only helper"

    def test_a_helper_with_one_caller_is_not_reported_dead(self):
        """The other direction, so the predicate is not merely always-true."""
        name = "_liv" + "e_helper"
        haystack = f"def {name}():\n    return 1\n\nx = {name}()\n"
        assert haystack.count(name) > 1
