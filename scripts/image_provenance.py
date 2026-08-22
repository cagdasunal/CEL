#!/usr/bin/env python3
"""
image_provenance.py — detect and losslessly remove AI-provenance metadata
=========================================================================

The engine behind ``watermark_cleaner.py``. Two jobs, both pure-stdlib:

  scan(data)  -> Report   what provenance signals a byte string carries
  strip(data) -> Result   the same image with those signals surgically removed

**Lossless by construction.** Nothing here decodes or re-encodes pixels. Each
container is parsed at the chunk/segment/box level and rewritten without the
metadata records. The compressed image payload (PNG ``IDAT``, JPEG entropy
stream, WebP ``VP8``/``VP8L``, AVIF AV1 OBUs) is copied byte-for-byte, so the
decoded pixels are bit-identical. ``verify_lossless()`` proves it.

Why not exiftool
----------------
Three reasons, all load-bearing:
  1. The pinned local exiftool is 10.62 (2017) — it predates JUMBF/C2PA and
     mis-identifies AVIF as ``video/mp4``. It cannot see, let alone remove,
     the manifests we actually care about.
  2. A GitHub Actions step should not need ``apt-get install libimage-exiftool-perl``
     when 400 lines of stdlib do the job deterministically.
  3. ``exiftool -all=`` on a JPEG rewrites the file through its own writer. We
     want provable byte-level provenance over what changed.

What this module refuses to claim
---------------------------------
It removes **metadata**. It does **not** remove pixel-domain watermarks
(Google SynthID, OpenAI's declared ``c2pa.watermarked.*``, Meta Stable
Signature). Those live in the image samples themselves and survive any lossless
operation by design. ``scan()`` reports them under
``Report.undetectable_watermarks`` precisely so callers stop short of claiming
otherwise — see ``rules/ai-provenance.md``.

Container coverage
------------------
  PNG   — ancillary chunk removal (``caBX`` is the C2PA store), CRC recomputed
  JPEG  — APPn/COM segment removal, entropy-coded scan copied verbatim
  WebP  — RIFF chunk removal + ``VP8X`` feature-flag fixup + RIFF size fixup
  AVIF  — ISOBMFF ``meta`` remux: item dropped from iinf/iloc/iref/ipma and
          its bytes evicted from ``mdat``, all iloc offsets rewritten
  HEIC  — same code path as AVIF
  GIF   — Comment/Application extension removal (NETSCAPE loop preserved)

Public API
----------
  sniff(data)                    -> str            container id or "unknown"
  scan(data)                     -> Report
  strip(data, *, policy=...)     -> Result
  verify_lossless(before, after) -> tuple[bool, str]
  Policy                                          what to remove / keep

Called by
---------
  scripts/watermark_cleaner.py                     CLI + Webflow replace
  scripts/optimize_blog_richtext_images.py         nightly CEL CMS sweep
  scripts/tests/test_image_provenance.py           unit + stress
"""
from __future__ import annotations

import binascii
import dataclasses
import hashlib
import re
import struct
from typing import Iterable

__all__ = [
    "Policy",
    "Report",
    "Result",
    "Signal",
    "ProvenanceError",
    "sniff",
    "scan",
    "strip",
    "verify_lossless",
    "SIGNAL_KINDS",
]


class ProvenanceError(Exception):
    """Raised when a container is malformed beyond safe rewriting."""


# ── signal taxonomy ──────────────────────────────────────────────────────────
# Ordered most- to least- consequential. `watermark_declared` is deliberately
# last-but-one and carries removable=False: it is the honest "there is a pixel
# watermark here and this module cannot touch it" flag.
SIGNAL_KINDS = (
    "c2pa",                 # signed Content Credentials manifest (JUMBF store)
    "iptc_ai",              # IPTC digitalSourceType => trainedAlgorithmicMedia
    "generator_tag",        # vendor breadcrumb: hf-job-id, Software, parameters…
    "xmp",                  # XMP packet (may carry either of the two above)
    "exif",                 # EXIF IFD — camera/software/GPS
    "iptc_iim",             # legacy Photoshop IRB / IPTC-IIM block
    "comment",              # free-text container comment
    "watermark_declared",   # manifest SAYS a pixel watermark was applied
    "other_metadata",       # anything else non-pixel we chose to drop
)


@dataclasses.dataclass(frozen=True)
class Signal:
    """One provenance finding inside an image."""

    kind: str               # one of SIGNAL_KINDS
    where: str              # container-native locus, e.g. "PNG:caBX" "JPEG:APP11"
    offset: int             # byte offset of the record's start
    length: int             # byte length of the whole record
    removable: bool         # can strip() actually get rid of it?
    detail: str = ""        # human-readable specifics

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Report:
    """What scan() found."""

    container: str
    size: int
    signals: list[Signal] = dataclasses.field(default_factory=list)
    generators: list[str] = dataclasses.field(default_factory=list)
    undetectable_watermarks: list[str] = dataclasses.field(default_factory=list)
    parse_error: str = ""

    # -- convenience -------------------------------------------------------
    @property
    def ai_generators(self) -> list[str]:
        """The generators found that imply synthesis, not merely editing."""
        return [g for g in self.generators if g in _AI_GENERATORS]

    @property
    def is_ai_flagged(self) -> bool:
        """True when a signal a third party could read as 'AI-generated' is present.

        Three sources, not two. A signed C2PA manifest and an IPTC
        ``digitalSourceType`` are the standardised ones — but a bare vendor
        breadcrumb is just as legible, and sometimes worse: Higgsfield's
        ``hf-job-id`` is a live job identifier tied to the account that
        generated the image. Counting only the standardised signals reported 9
        Higgsfield images as ordinary "metadata".
        """
        return (any(s.kind in ("c2pa", "iptc_ai") for s in self.signals)
                or bool(self.ai_generators))

    @property
    def removable_bytes(self) -> int:
        return sum(s.length for s in self.signals if s.removable)

    @property
    def kinds(self) -> list[str]:
        seen: dict[str, None] = {}
        for s in self.signals:
            seen.setdefault(s.kind, None)
        return list(seen)

    def as_dict(self) -> dict:
        return {
            "container": self.container,
            "size": self.size,
            "is_ai_flagged": self.is_ai_flagged,
            "kinds": self.kinds,
            "removable_bytes": self.removable_bytes,
            "generators": list(self.generators),
            "ai_generators": list(self.ai_generators),
            "undetectable_watermarks": list(self.undetectable_watermarks),
            "signals": [s.as_dict() for s in self.signals],
            "parse_error": self.parse_error,
        }


@dataclasses.dataclass
class Result:
    """What strip() produced."""

    data: bytes
    container: str
    before: Report
    after: Report
    removed: list[Signal] = dataclasses.field(default_factory=list)
    kept: list[Signal] = dataclasses.field(default_factory=list)
    bytes_removed: int = 0
    lossless: bool = True
    note: str = ""
    policy: "Policy | None" = None

    @property
    def changed(self) -> bool:
        return self.bytes_removed > 0 or bool(self.removed)

    @property
    def clean(self) -> bool:
        """Did the POLICY's intent get achieved?

        Not "no removable signal survived" — under ``--keep-exif`` the EXIF is
        supposed to survive, and reporting that run as unclean made a fully
        correct strip look like a failure (and, downstream, turned it into
        verify_failed -> errors++ -> exit 2).
        """
        pol = self.policy or DEFAULT_POLICY
        return not any(s.removable and pol.wants(s.kind) for s in self.after.signals)

    @property
    def fully_stripped(self) -> bool:
        """No removable signal at all, regardless of policy — the strict question."""
        return not any(s.removable for s in self.after.signals)

    def as_dict(self) -> dict:
        return {
            "container": self.container,
            "changed": self.changed,
            "clean": self.clean,
            "fully_stripped": self.fully_stripped,
            "lossless": self.lossless,
            "bytes_removed": self.bytes_removed,
            "removed": [s.as_dict() for s in self.removed],
            "kept": [s.as_dict() for s in self.kept],
            "before": self.before.as_dict(),
            "after": self.after.as_dict(),
            "note": self.note,
        }


@dataclasses.dataclass(frozen=True)
class Policy:
    """What to remove. Defaults strip every provenance signal but keep colour.

    ``keep_icc`` defaults True on purpose: an ICC profile is colour-management
    data, not provenance, and dropping it visibly shifts colours in wide-gamut
    images. ``keep_orientation`` re-emits a minimal EXIF IFD holding only
    ``Orientation`` when the original had a non-default value — otherwise
    stripping EXIF silently rotates photographs.
    """

    strip_c2pa: bool = True
    strip_exif: bool = True
    strip_xmp: bool = True
    strip_iptc: bool = True
    strip_comments: bool = True
    strip_generator_tags: bool = True
    keep_icc: bool = True
    keep_orientation: bool = True
    keep_animation: bool = True      # APNG / animated WebP / GIF loop control

    def wants(self, kind: str) -> bool:
        return {
            "c2pa": self.strip_c2pa,
            "iptc_ai": self.strip_xmp or self.strip_iptc,
            "generator_tag": self.strip_generator_tags,
            "xmp": self.strip_xmp,
            "exif": self.strip_exif,
            "iptc_iim": self.strip_iptc,
            "comment": self.strip_comments,
            "other_metadata": True,
            "watermark_declared": False,   # never claimable
        }.get(kind, True)


DEFAULT_POLICY = Policy()


# ── container sniffing ───────────────────────────────────────────────────────
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_GIF_MAGICS = (b"GIF87a", b"GIF89a")


def sniff(data: bytes) -> str:
    """Identify the container from magic bytes. Returns a lowercase id."""
    if len(data) < 12:
        return "unknown"
    if data.startswith(_PNG_MAGIC):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(_GIF_MAGICS):
        return "gif"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"avif", b"avis"):
            return "avif"
        if brand in (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"):
            return "heif"
        # Compatible-brand fallback: some encoders put a generic major brand.
        compat = data[16:64]
        if b"avif" in compat:
            return "avif"
        if b"heic" in compat or b"mif1" in compat:
            return "heif"
        return "isobmff"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    # lstrip() removes whitespace but NOT a UTF-8 BOM, so a BOM-prefixed SVG
    # sniffed as "unknown" and its <c2pa:manifest> was never parsed.
    head = data[:1024].lstrip(b"\xef\xbb\xbf").lstrip()
    if head[:5].lower() == b"<?xml" or head[:4].lower() == b"<svg":
        if b"<svg" in data[:4096].lower():
            return "svg"
    return "unknown"


# ── shared string-level provenance mining ────────────────────────────────────
# These patterns run over the *metadata records only* (never the pixel payload),
# so a false positive cannot be triggered by compressed image entropy.
# Generators that mean "this image was SYNTHESISED", as opposed to editors that
# merely mean "this image was opened in a tool". A Higgsfield `hf-job-id` is a
# live job identifier that resolves inside the account that made it — a stronger
# link back to the creator than an anonymous C2PA manifest — so it must count
# toward is_ai_flagged. Photoshop/Canva/Lightroom deliberately do NOT: a scanned
# photograph retouched in Photoshop is not AI-generated, and flagging it would
# make the signal useless.
_AI_GENERATORS: frozenset[str] = frozenset({
    "OpenAI", "OpenAI gpt-image", "OpenAI DALL-E", "Midjourney", "Adobe Firefly",
    "Google DeepMind", "Google Imagen", "Google Gemini", "Google", "Stability AI",
    "Black Forest Labs FLUX", "Ideogram", "Recraft", "Leonardo AI", "Higgsfield",
    "Amazon Titan", "xAI Grok", "Alibaba Qwen", "ByteDance Seedream",
})

_GENERATOR_PATTERNS: tuple[tuple[bytes, str], ...] = (
    (b"gpt-image", "OpenAI gpt-image"),
    (b"OpenAI", "OpenAI"),
    (b"DALL-E", "OpenAI DALL-E"),
    (b"DALL\xc2\xb7E", "OpenAI DALL-E"),
    (b"Midjourney", "Midjourney"),
    (b"midjourney", "Midjourney"),
    (b"Firefly", "Adobe Firefly"),
    (b"Adobe Photoshop", "Adobe Photoshop"),
    (b"Google DeepMind", "Google DeepMind"),
    (b"Imagen", "Google Imagen"),
    (b"Gemini", "Google Gemini"),
    (b"Made with Google AI", "Google"),
    (b"Stable Diffusion", "Stability AI"),
    (b"stable-diffusion", "Stability AI"),
    (b"StabilityAI", "Stability AI"),
    (b"black-forest-labs", "Black Forest Labs FLUX"),
    (b"FLUX.1", "Black Forest Labs FLUX"),
    (b"Ideogram", "Ideogram"),
    (b"Recraft", "Recraft"),
    (b"Leonardo.Ai", "Leonardo AI"),
    (b"hf-job-id", "Higgsfield"),
    (b"Higgsfield", "Higgsfield"),
    (b"higgsfield", "Higgsfield"),
    (b"Canva", "Canva"),
    (b"Titan Image Generator", "Amazon Titan"),
    (b"Grok", "xAI Grok"),
    (b"Qwen-Image", "Alibaba Qwen"),
    (b"Seedream", "ByteDance Seedream"),
)

# C2PA action assertions that declare an *unremovable* pixel watermark.
_WATERMARK_ACTIONS: tuple[tuple[bytes, str], ...] = (
    (b"c2pa.watermarked", "C2PA c2pa.watermarked action — issuer applied a pixel watermark"),
    (b"synthid", "Google SynthID"),
    (b"SynthID", "Google SynthID"),
    (b"soft_binding", "C2PA soft binding (perceptual hash / watermark)"),
    (b"softBinding", "C2PA soft binding (perceptual hash / watermark)"),
    (b"c2pa.soft-binding", "C2PA soft binding (perceptual hash / watermark)"),
)

_IPTC_AI_TOKENS: tuple[bytes, ...] = (
    b"trainedAlgorithmicMedia",
    b"compositeWithTrainedAlgorithmicMedia",
    b"algorithmicMedia",
    b"digitalSourceType",
)


def _mine_generators(blob: bytes) -> list[str]:
    out: list[str] = []
    for needle, label in _GENERATOR_PATTERNS:
        if needle in blob and label not in out:
            out.append(label)
    return out


def _mine_watermark_declarations(blob: bytes) -> list[str]:
    out: list[str] = []
    for needle, label in _WATERMARK_ACTIONS:
        if needle in blob and label not in out:
            out.append(label)
    return out


def _looks_iptc_ai(blob: bytes) -> str:
    for tok in _IPTC_AI_TOKENS:
        if tok in blob:
            # Report the strongest token present, not merely the first match.
            if b"trainedAlgorithmicMedia" in blob:
                return "digitalSourceType=trainedAlgorithmicMedia"
            return tok.decode("ascii", "replace")
    return ""


def _classify_blob(blob: bytes, base_kind: str) -> tuple[str, str]:
    """Refine a metadata record's kind by looking at its content.

    A generic XMP packet that turns out to carry ``trainedAlgorithmicMedia``
    is far more consequential than "some XMP", and the report should say so.

    ``c2pa`` is never downgraded: a signed manifest is the strongest signal in
    the taxonomy and the IPTC assertion inside it is a *property* of it, not a
    replacement for it. Reporting a ``caBX`` chunk as merely ``iptc_ai`` would
    hide the fact that a cryptographically signed manifest was present.
    """
    ai = _looks_iptc_ai(blob)
    if ai:
        return (base_kind if base_kind == "c2pa" else "iptc_ai"), ai
    gens = _mine_generators(blob)
    if gens:
        return ("generator_tag" if base_kind in ("comment", "other_metadata") else base_kind,
                "generator: " + ", ".join(gens))
    return base_kind, ""


# =============================================================================
# PNG
# =============================================================================
# Chunk layout: [len:4][type:4][data:len][crc:4]. Everything except the critical
# chunks is ancillary and safe to drop — with two exceptions we must protect:
# colour chunks (dropping them shifts rendering) and APNG control chunks
# (dropping them turns an animation into a still).
_PNG_CRITICAL = {b"IHDR", b"PLTE", b"IDAT", b"IEND"}
_PNG_RENDER_ESSENTIAL = {b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"sBIT", b"bKGD", b"pHYs", b"cICP", b"mDCv", b"cLLi"}
_PNG_ANIMATION = {b"acTL", b"fcTL", b"fdAT"}
_PNG_ICC = {b"iCCP"}

# Ancillary chunks that carry provenance, mapped to their signal kind.
_PNG_META_KINDS: dict[bytes, str] = {
    b"caBX": "c2pa",        # C2PA JUMBF store  (C2PA spec §PNG)
    b"eXIf": "exif",
    b"tEXt": "comment",
    b"zTXt": "comment",
    b"iTXt": "xmp",         # XMP lives in an iTXt whose keyword is XML:com.adobe.xmp
    b"tIME": "other_metadata",
    b"dSIG": "other_metadata",
}


def _png_chunks(data: bytes) -> Iterable[tuple[int, bytes, bytes, int]]:
    """Yield (offset, type, payload, total_len) for every chunk."""
    if not data.startswith(_PNG_MAGIC):
        raise ProvenanceError("not a PNG")
    off = len(_PNG_MAGIC)
    n = len(data)
    while off + 8 <= n:
        (ln,) = struct.unpack(">I", data[off:off + 4])
        ctype = data[off + 4:off + 8]
        end = off + 12 + ln
        if ln > n or end > n:
            raise ProvenanceError(f"PNG chunk {ctype!r} at {off} overruns file")
        yield off, ctype, data[off + 8:off + 8 + ln], 12 + ln
        off = end
        if ctype == b"IEND":
            return                       # trailing bytes after IEND are ignored
    # Falling out of the loop means IEND was never reached. Requiring it is what
    # makes truncation detectable: a file cut at a chunk boundary otherwise walks
    # cleanly to `off == n` and looks intact, and a corrupted tail can decay into
    # a zero-length chunk that lands exactly on the end. Both were reported as
    # healthy until the fuzz suite hit them.
    raise ProvenanceError("PNG ended without IEND")


def _png_text_payload(ctype: bytes, payload: bytes) -> tuple[str, bytes]:
    """Return (keyword, decoded-ish body) for tEXt/zTXt/iTXt."""
    if ctype == b"tEXt":
        kw, _, body = payload.partition(b"\x00")
        return kw.decode("latin1", "replace"), body
    if ctype == b"zTXt":
        kw, _, rest = payload.partition(b"\x00")
        body = rest[1:] if rest else b""
        try:
            import zlib
            body = zlib.decompress(body)
        except Exception:
            pass
        return kw.decode("latin1", "replace"), body
    if ctype == b"iTXt":
        parts = payload.split(b"\x00", 3)
        kw = parts[0].decode("utf-8", "replace") if parts else ""
        body = parts[3] if len(parts) > 3 else b""
        # parts[1] is the 1-byte compression flag + method, folded into the split
        if len(parts) > 1 and parts[1][:1] == b"\x01":
            try:
                import zlib
                body = zlib.decompress(body)
            except Exception:
                pass
        return kw, body
    return "", payload


def _scan_png(data: bytes, rep: Report) -> None:
    for off, ctype, payload, total in _png_chunks(data):
        kind = _PNG_META_KINDS.get(ctype)
        if kind is None:
            continue
        detail = ""
        blob = payload
        if ctype in (b"tEXt", b"zTXt", b"iTXt"):
            kw, body = _png_text_payload(ctype, payload)
            blob = kw.encode("utf-8", "replace") + b"\x00" + body
            detail = f"keyword={kw!r}"
            if "xmp" in kw.lower() or b"<x:xmpmeta" in body:
                kind = "xmp"
        refined, extra = _classify_blob(blob, kind)
        kind = refined
        if extra:
            detail = f"{detail} {extra}".strip()
        if ctype == b"caBX":
            detail = (detail + " C2PA JUMBF store").strip()
        rep.signals.append(Signal(
            kind=kind, where=f"PNG:{ctype.decode('latin1')}",
            offset=off, length=total, removable=True, detail=detail,
        ))
        rep.generators.extend(g for g in _mine_generators(blob) if g not in rep.generators)
        for w in _mine_watermark_declarations(blob):
            if w not in rep.undetectable_watermarks:
                rep.undetectable_watermarks.append(w)
                rep.signals.append(Signal(
                    kind="watermark_declared", where=f"PNG:{ctype.decode('latin1')}",
                    offset=off, length=0, removable=False, detail=w,
                ))


def _strip_png(data: bytes, policy: Policy, rep: Report) -> tuple[bytes, list[Signal]]:
    out = bytearray(_PNG_MAGIC)
    removed: list[Signal] = []
    by_offset = {s.offset: s for s in rep.signals if s.length > 0}
    for off, ctype, payload, total in _png_chunks(data):
        if ctype in _PNG_CRITICAL or ctype in _PNG_RENDER_ESSENTIAL:
            out += data[off:off + total]
            continue
        if ctype in _PNG_ANIMATION and policy.keep_animation:
            out += data[off:off + total]
            continue
        if ctype in _PNG_ICC and policy.keep_icc:
            out += data[off:off + total]
            continue
        sig = by_offset.get(off)
        if sig is not None and not policy.wants(sig.kind):
            out += data[off:off + total]
            continue
        if sig is None and ctype not in _PNG_META_KINDS:
            # Unknown ancillary chunk. Anything unrecognised and non-rendering is
            # exactly where a novel provenance marker would hide, so drop it —
            # but only when the caller asked for a full scrub.
            if not policy.strip_generator_tags:
                out += data[off:off + total]
                continue
            removed.append(Signal(
                kind="other_metadata", where=f"PNG:{ctype.decode('latin1', 'replace')}",
                offset=off, length=total, removable=True, detail="unrecognised ancillary chunk",
            ))
            continue
        if sig is not None:
            removed.append(sig)
    return bytes(out), removed


def _png_rebuild_chunk(ctype: bytes, payload: bytes) -> bytes:
    body = ctype + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)


# =============================================================================
# JPEG
# =============================================================================
# Segment layout: 0xFF <marker> <len:2 incl. itself> <payload>. Markers without
# a length: SOI/EOI/TEM/RSTn. After SOS the stream is entropy-coded and must be
# copied verbatim to EOI.
_JPEG_APP_SIGNATURES: tuple[tuple[int, bytes, str, str], ...] = (
    # (marker, payload prefix, kind, label)
    (0xE1, b"Exif\x00\x00", "exif", "EXIF"),
    (0xE1, b"http://ns.adobe.com/xap/1.0/\x00", "xmp", "XMP"),
    (0xE1, b"http://ns.adobe.com/xmp/extension/\x00", "xmp", "XMP extension"),
    (0xE2, b"ICC_PROFILE\x00", "icc", "ICC profile"),
    (0xE2, b"MPF\x00", "other_metadata", "MPF"),
    (0xE2, b"urn:iso:std:iso:ts:21496:-1", "other_metadata", "ISO 21496 gainmap"),
    (0xEB, b"JP\x00\x00", "c2pa", "JUMBF (C2PA)"),
    (0xED, b"Photoshop 3.0\x00", "iptc_iim", "Photoshop IRB / IPTC-IIM"),
    # APP14 "Adobe" is NOT metadata: its transform byte tells the decoder whether
    # the components are YCbCr, YCCK or CMYK. Dropping it inverts colours on
    # 4-component JPEGs and can shift 3-component ones. Classified alongside JFIF
    # and ICC as render-essential, never stripped.
    (0xEE, b"Adobe", "colour", "Adobe APP14 (colour transform)"),
    (0xEC, b"Ducky", "other_metadata", "Ducky APP12"),
)
_JPEG_STANDALONE = {0xD8, 0xD9, 0x01} | set(range(0xD0, 0xD8))


def _jpeg_segments(data: bytes) -> Iterable[tuple[int, int, bytes, int]]:
    """Yield (offset, marker, payload, total_len). Stops at SOS; caller copies the tail."""
    if not data.startswith(b"\xff\xd8"):
        raise ProvenanceError("not a JPEG")
    off, n = 2, len(data)
    while off < n:
        if data[off] != 0xFF:
            raise ProvenanceError(f"JPEG desync at {off}: expected 0xFF, got {data[off]:#04x}")
        # Fill bytes: 0xFF may repeat before the marker id.
        m = off + 1
        while m < n and data[m] == 0xFF:
            m += 1
        if m >= n:
            raise ProvenanceError("JPEG truncated in marker")
        marker = data[m]
        if marker in _JPEG_STANDALONE:
            yield off, marker, b"", m + 1 - off
            off = m + 1
            continue
        if m + 3 > n:
            raise ProvenanceError("JPEG truncated in segment length")
        (seglen,) = struct.unpack(">H", data[m + 1:m + 3])
        if seglen < 2 or m + 1 + seglen > n:
            raise ProvenanceError(f"JPEG segment {marker:#04x} at {off} has bad length {seglen}")
        payload = data[m + 3:m + 1 + seglen]
        total = (m + 1 + seglen) - off
        yield off, marker, payload, total
        off += total
        if marker == 0xDA:      # SOS — entropy-coded data follows
            return


def _jpeg_identify(marker: int, payload: bytes) -> tuple[str, str]:
    for mk, prefix, kind, label in _JPEG_APP_SIGNATURES:
        if marker == mk and payload.startswith(prefix):
            return kind, label
    if marker == 0xFE:
        return "comment", "COM comment"
    if 0xE0 <= marker <= 0xEF:
        if marker == 0xE0 and payload.startswith(b"JFIF\x00"):
            return "jfif", "JFIF"
        if marker == 0xE0 and payload.startswith(b"JFXX\x00"):
            return "jfif", "JFXX"
        return "other_metadata", f"APP{marker - 0xE0} (unrecognised)"
    return "", ""


def _exif_orientation(payload: bytes) -> int:
    """Read tag 0x0112 out of an ``Exif\\0\\0`` APP1 payload. 0 when absent."""
    tiff = payload[6:]
    if len(tiff) < 8:
        return 0
    if tiff[:2] == b"II":
        endian = "<"
    elif tiff[:2] == b"MM":
        endian = ">"
    else:
        return 0
    try:
        (ifd_off,) = struct.unpack(endian + "I", tiff[4:8])
        if ifd_off + 2 > len(tiff):
            return 0
        (count,) = struct.unpack(endian + "H", tiff[ifd_off:ifd_off + 2])
        for i in range(count):
            e = ifd_off + 2 + i * 12
            if e + 12 > len(tiff):
                break
            tag, typ, cnt = struct.unpack(endian + "HHI", tiff[e:e + 8])
            if tag == 0x0112 and typ == 3 and cnt == 1:
                (val,) = struct.unpack(endian + "H", tiff[e + 8:e + 10])
                return val if 1 <= val <= 8 else 0
    except struct.error:
        return 0
    return 0


def _minimal_exif_orientation(orientation: int) -> bytes:
    """Build the smallest valid ``Exif\\0\\0`` APP1 payload carrying Orientation."""
    tiff = b"MM\x00*" + struct.pack(">I", 8)
    tiff += struct.pack(">H", 1)                              # 1 IFD entry
    tiff += struct.pack(">HHI", 0x0112, 3, 1) + struct.pack(">HH", orientation, 0)
    tiff += struct.pack(">I", 0)                              # next IFD = none
    return b"Exif\x00\x00" + tiff


# The eight payloads _strip_jpeg may legitimately re-emit. A surviving EXIF
# segment is a strip failure *unless* it is byte-identical to one of these:
# they carry a single Orientation tag and nothing else — no camera, no software,
# no GPS, no provenance. Without this exemption the post-strip assertion in
# strip() fires on the module's own output, which is how it was first caught.
_ORIENTATION_ONLY_EXIF = frozenset(_minimal_exif_orientation(n) for n in range(1, 9))
# All eight are the same length by construction; raw_residue slices exactly this
# many bytes, so deriving it here keeps the two in lockstep. Hard-coding a guess
# is what made the exemption silently miss on the first run.
_ORIENTATION_EXIF_LEN = len(next(iter(_ORIENTATION_ONLY_EXIF)))


def _is_orientation_only_exif(payload: bytes) -> bool:
    return payload in _ORIENTATION_ONLY_EXIF


def _scan_jpeg(data: bytes, rep: Report) -> None:
    for off, marker, payload, total in _jpeg_segments(data):
        kind, label = _jpeg_identify(marker, payload)
        if kind in ("", "jfif", "icc", "colour"):
            continue
        if kind == "exif" and _is_orientation_only_exif(payload):
            continue                      # our own re-emitted orientation block
        refined, extra = _classify_blob(payload, kind)
        detail = label if not extra else f"{label} — {extra}"
        rep.signals.append(Signal(
            kind=refined, where=f"JPEG:APP{marker - 0xE0}" if 0xE0 <= marker <= 0xEF else f"JPEG:{marker:#04x}",
            offset=off, length=total, removable=True, detail=detail,
        ))
        rep.generators.extend(g for g in _mine_generators(payload) if g not in rep.generators)
        for w in _mine_watermark_declarations(payload):
            if w not in rep.undetectable_watermarks:
                rep.undetectable_watermarks.append(w)
                rep.signals.append(Signal(
                    kind="watermark_declared", where=f"JPEG:APP{marker - 0xE0}",
                    offset=off, length=0, removable=False, detail=w,
                ))


def _strip_jpeg(data: bytes, policy: Policy, rep: Report) -> tuple[bytes, list[Signal]]:
    out = bytearray(b"\xff\xd8")
    removed: list[Signal] = []
    by_offset = {s.offset: s for s in rep.signals if s.length > 0}
    orientation = 0
    tail_from = len(data)
    for off, marker, payload, total in _jpeg_segments(data):
        if marker == 0xD8:
            continue
        if marker == 0xDA:
            tail_from = off
            break
        kind, _label = _jpeg_identify(marker, payload)
        if kind in ("jfif", "colour") or (kind == "icc" and policy.keep_icc):
            out += data[off:off + total]
            continue
        if kind == "exif" and policy.keep_orientation:
            orientation = _exif_orientation(payload) or orientation
        sig = by_offset.get(off)
        if sig is not None and not policy.wants(sig.kind):
            out += data[off:off + total]
            continue
        if sig is not None:
            removed.append(sig)
            continue
        if kind == "icc" and not policy.keep_icc:
            removed.append(Signal(kind="other_metadata", where=f"JPEG:APP{marker - 0xE0}",
                                  offset=off, length=total, removable=True, detail="ICC profile"))
            continue
        out += data[off:off + total]

    # Re-emit orientation so stripping EXIF cannot silently rotate a photo.
    if policy.keep_orientation and orientation not in (0, 1):
        payload = _minimal_exif_orientation(orientation)
        out[2:2] = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload

    out += data[tail_from:]
    return bytes(out), removed


# =============================================================================
# WebP
# =============================================================================
# RIFF: "RIFF"<size:4 LE>"WEBP" then chunks <fourcc:4><size:4 LE><data><pad>.
# VP8X carries feature flags; clearing the EXIF/XMP bits when their chunks go is
# mandatory, otherwise strict decoders report a malformed file.
_WEBP_META_KINDS: dict[bytes, str] = {
    b"EXIF": "exif",
    b"XMP ": "xmp",
    b"C2PA": "c2pa",
}
_WEBP_VP8X_ICC = 0x20
_WEBP_VP8X_ALPHA = 0x10
_WEBP_VP8X_EXIF = 0x08
_WEBP_VP8X_XMP = 0x04
_WEBP_VP8X_ANIM = 0x02


def _webp_chunks(data: bytes) -> Iterable[tuple[int, bytes, bytes, int]]:
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ProvenanceError("not a WebP")
    (riff_size,) = struct.unpack("<I", data[4:8])
    end = min(len(data), 8 + riff_size)
    off = 12
    while off + 8 <= end:
        fourcc = data[off:off + 4]
        (size,) = struct.unpack("<I", data[off + 4:off + 8])
        padded = size + (size & 1)
        if off + 8 + size > end:
            raise ProvenanceError(f"WebP chunk {fourcc!r} at {off} overruns file")
        yield off, fourcc, data[off + 8:off + 8 + size], 8 + padded
        off += 8 + padded


def _scan_webp(data: bytes, rep: Report) -> None:
    for off, fourcc, payload, total in _webp_chunks(data):
        kind = _WEBP_META_KINDS.get(fourcc)
        if kind is None:
            continue
        refined, extra = _classify_blob(payload, kind)
        rep.signals.append(Signal(
            kind=refined, where=f"WEBP:{fourcc.decode('latin1').strip()}",
            offset=off, length=total, removable=True, detail=extra,
        ))
        rep.generators.extend(g for g in _mine_generators(payload) if g not in rep.generators)
        for w in _mine_watermark_declarations(payload):
            if w not in rep.undetectable_watermarks:
                rep.undetectable_watermarks.append(w)
                rep.signals.append(Signal(
                    kind="watermark_declared", where=f"WEBP:{fourcc.decode('latin1').strip()}",
                    offset=off, length=0, removable=False, detail=w,
                ))


def _strip_webp(data: bytes, policy: Policy, rep: Report) -> tuple[bytes, list[Signal]]:
    removed: list[Signal] = []
    by_offset = {s.offset: s for s in rep.signals if s.length > 0}
    body = bytearray()
    dropped_flags = 0
    for off, fourcc, payload, total in _webp_chunks(data):
        if fourcc == b"ICCP" and not policy.keep_icc:
            removed.append(Signal(kind="other_metadata", where="WEBP:ICCP", offset=off,
                                  length=total, removable=True, detail="ICC profile"))
            dropped_flags |= _WEBP_VP8X_ICC
            continue
        sig = by_offset.get(off)
        if sig is not None and policy.wants(sig.kind):
            removed.append(sig)
            dropped_flags |= {b"EXIF": _WEBP_VP8X_EXIF, b"XMP ": _WEBP_VP8X_XMP}.get(fourcc, 0)
            continue
        body += data[off:off + total]

    # Fix the VP8X feature flags for the chunks we just dropped.
    if dropped_flags:
        i = 0
        while i + 8 <= len(body):
            fourcc = bytes(body[i:i + 4])
            (size,) = struct.unpack("<I", body[i + 4:i + 8])
            if fourcc == b"VP8X" and size >= 4:
                body[i + 8] &= ~dropped_flags & 0xFF
                break
            i += 8 + size + (size & 1)

    out = b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + bytes(body)
    return out, removed


# =============================================================================
# GIF
# =============================================================================
def _gif_blocks(data: bytes) -> Iterable[tuple[int, str, int, bytes]]:
    """Yield (offset, kind, total_len, payload) for GIF blocks after the header."""
    if not data.startswith(_GIF_MAGICS):
        raise ProvenanceError("not a GIF")
    n = len(data)
    off = 6
    if off + 7 > n:
        raise ProvenanceError("GIF truncated in logical screen descriptor")
    packed = data[off + 4]
    off += 7
    if packed & 0x80:                                     # global colour table
        off += 3 * (2 ** ((packed & 0x07) + 1))

    def sub_blocks(p: int) -> int:
        while p < n and data[p] != 0:
            p += 1 + data[p]
        return p + 1

    while off < n:
        b = data[off]
        if b == 0x3B:                                     # trailer
            yield off, "trailer", 1, b""
            return
        if b == 0x21:                                     # extension introducer
            if off + 2 > n:
                raise ProvenanceError("GIF truncated in extension")
            label = data[off + 1]
            start = off + 2
            end = sub_blocks(start)
            kind = {0xFE: "comment", 0xFF: "application", 0xF9: "gce", 0x01: "plaintext"}.get(label, "ext")
            yield off, kind, end - off, data[start:end]
            off = end
            continue
        if b == 0x2C:                                     # image descriptor
            if off + 10 > n:
                raise ProvenanceError("GIF truncated in image descriptor")
            lp = data[off + 9]
            p = off + 10
            if lp & 0x80:
                p += 3 * (2 ** ((lp & 0x07) + 1))
            p += 1                                        # LZW minimum code size
            p = sub_blocks(p)
            yield off, "image", p - off, b""
            off = p
            continue
        raise ProvenanceError(f"GIF unknown block {b:#04x} at {off}")


def _scan_gif(data: bytes, rep: Report) -> None:
    for off, kind, total, payload in _gif_blocks(data):
        if kind == "comment":
            refined, extra = _classify_blob(payload, "comment")
            rep.signals.append(Signal(kind=refined, where="GIF:comment", offset=off,
                                      length=total, removable=True, detail=extra))
            rep.generators.extend(g for g in _mine_generators(payload) if g not in rep.generators)
        elif kind == "application":
            app = bytes(payload[1:12]) if len(payload) > 12 else b""
            if app.startswith(b"NETSCAPE") or app.startswith(b"ANIMEXTS"):
                continue                                   # loop control — keep
            refined, extra = _classify_blob(payload, "other_metadata")
            rep.signals.append(Signal(kind=refined, where=f"GIF:app:{app.decode('latin1', 'replace').strip()}",
                                      offset=off, length=total, removable=True, detail=extra))
            rep.generators.extend(g for g in _mine_generators(payload) if g not in rep.generators)


def _strip_gif(data: bytes, policy: Policy, rep: Report) -> tuple[bytes, list[Signal]]:
    removed: list[Signal] = []
    by_offset = {s.offset: s for s in rep.signals if s.length > 0}
    # Header + logical screen descriptor + global colour table are copied whole.
    # `next(iter(...))` on an empty generator raises StopIteration, which is NOT
    # a ProvenanceError and so escaped strip()'s contract entirely — a mutated
    # GIF whose first block is unreadable crashed the caller instead of being
    # refused. Convert it at the boundary.
    try:
        first = next(iter(_gif_blocks(data)))[0]
    except StopIteration:
        raise ProvenanceError("GIF has no parseable blocks") from None
    out = bytearray(data[:first])
    for off, _kind, total, _payload in _gif_blocks(data):
        sig = by_offset.get(off)
        if sig is not None and policy.wants(sig.kind):
            removed.append(sig)
            continue
        out += data[off:off + total]
    return bytes(out), removed


# =============================================================================
# SVG
# =============================================================================
# C2PA in SVG lives in a <c2pa:manifest> element inside <metadata>; Illustrator,
# Figma and Inkscape each leave their own <metadata>/RDF blocks. Removing a
# <metadata> element cannot change rendering — SVG 1.1 §5.10 defines it as
# non-rendered — so this is lossless in exactly the sense the rest of the module
# means it. Editor namespace attributes (inkscape:*, sodipodi:*) are left alone:
# they are attributes on rendered elements, and rewriting those is a different
# and riskier job than deleting a self-contained element.
_SVG_META_ELEMENTS = ("metadata", "c2pa:manifest")


def _svg_elements(data: bytes, tag: str) -> list[tuple[int, int, bytes]]:
    """Find complete <tag …>…</tag> spans. Returns (start, end, inner)."""
    out: list[tuple[int, int, bytes]] = []
    lower = data.lower()
    open_pat = re.compile(rb"<" + re.escape(tag.encode()) + rb"(\s[^>]*)?/?>", re.I)
    close = b"</" + tag.encode().lower() + b">"
    for m in open_pat.finditer(lower):
        if m.group(0).rstrip().endswith(b"/>"):
            out.append((m.start(), m.end(), b""))
            continue
        end = lower.find(close, m.end())
        if end == -1:
            continue
        out.append((m.start(), end + len(close), data[m.end():end]))
    return out


def _scan_svg(data: bytes, rep: Report) -> None:
    if b"<svg" not in data[:4096].lower():
        raise ProvenanceError("not an SVG")
    for tag in _SVG_META_ELEMENTS:
        for start, end, inner in _svg_elements(data, tag):
            blob = data[start:end]
            base = "c2pa" if (tag == "c2pa:manifest" or b"c2pa" in blob.lower()) else "other_metadata"
            refined, extra = _classify_blob(blob, base)
            rep.signals.append(Signal(
                kind=refined, where=f"SVG:<{tag}>", offset=start, length=end - start,
                removable=True, detail=extra or f"{len(inner)} B of {tag}",
            ))
            rep.generators.extend(g for g in _mine_generators(blob) if g not in rep.generators)
            for w in _mine_watermark_declarations(blob):
                if w not in rep.undetectable_watermarks:
                    rep.undetectable_watermarks.append(w)


def _svg_outermost(signals: list[Signal]) -> list[Signal]:
    """Collapse nested SVG spans to their outermost enclosing element.

    A <c2pa:manifest> normally sits INSIDE <metadata>, so scan reports two
    overlapping spans covering the same bytes. Deleting both cuts a second,
    unrelated slice out of the document — the first version ate the <rect>.
    Both the stripper and the losslessness digest must elide exactly the same
    spans, so they share this one function rather than each having a copy.
    """
    outermost: list[Signal] = []
    reach = -1
    for s in sorted(signals, key=lambda s: (s.offset, -s.length)):
        if s.offset < reach:
            continue                       # fully inside the span already taken
        outermost.append(s)
        reach = s.offset + s.length
    return outermost


def _svg_delete_spans(data: bytes, spans: list[Signal]) -> bytes:
    out = bytearray(data)
    for s in sorted(spans, key=lambda x: x.offset, reverse=True):
        del out[s.offset:s.offset + s.length]
    return bytes(out)


def _strip_svg(data: bytes, policy: Policy, rep: Report) -> tuple[bytes, list[Signal]]:
    candidates = [s for s in rep.signals
                  if s.length > 0 and s.removable and policy.wants(s.kind)
                  and s.where.startswith("SVG:")]
    if not candidates:
        return data, []
    outermost = _svg_outermost(candidates)
    return _svg_delete_spans(data, outermost), outermost


def _svg_pixel_digest(data: bytes) -> str:
    """Digest the SVG with every metadata element elided.

    There are no pixels to compare, so 'lossless' here means: nothing outside a
    non-rendered <metadata> element changed.
    """
    rep = Report(container="svg", size=len(data))
    try:
        _scan_svg(data, rep)
    except ProvenanceError:
        return hashlib.sha256(data).hexdigest()
    spans = _svg_outermost([s for s in rep.signals if s.length > 0])
    return hashlib.sha256(_svg_delete_spans(data, spans)).hexdigest()


# =============================================================================
# ISOBMFF (AVIF / HEIF)
# =============================================================================
# The hard case. Exif and XMP are *items*: declared in `iinf` (an `infe` entry),
# located by `iloc` (absolute file offsets into `mdat`), tied to the picture by
# `iref`/`cdsc`, and possibly listed in `ipma`. Removing one means rewriting all
# five structures and re-laying `mdat` — every surviving iloc offset moves.
_ISO_CONTAINER_BOXES = {b"meta", b"iprp", b"ipco", b"moov", b"trak", b"mdia",
                        b"minf", b"stbl", b"dinf", b"iinf", b"grpl"}
_ISO_FULLBOX_CONTAINERS = {b"meta", b"iinf"}
# C2PA in BMFF sits in a top-level `uuid` box carrying this extended type.
# Spec value: D8FEC3D6-1B0E-483C-9297-5828877EC481 (C2PA 2.x, "Embedding manifests
# into BMFF-based formats"). Derived from the hyphenated spec string rather than a
# hand-copied hex run: the first two attempts at this constant were both mistyped,
# and a wrong UUID here fails SILENTLY — every C2PA-bearing AVIF/HEIF simply scans
# clean. test_c2pa_bmff_uuid_matches_the_spec pins it.
_C2PA_BMFF_UUID_STR = "D8FEC3D6-1B0E-483C-9297-5828877EC481"
_C2PA_UUID = bytes.fromhex(_C2PA_BMFF_UUID_STR.replace("-", ""))
# Older writers emitted the JUMBF box type as the extended type instead.
_C2PA_UUID_ALT = bytes.fromhex("6332706100110010800000AA00389B71")


@dataclasses.dataclass
class _Box:
    typ: bytes
    offset: int
    size: int
    hdr: int            # header length: 8, 16 (largesize) or +16 for uuid
    uuid: bytes = b""

    @property
    def end(self) -> int:
        return self.offset + self.size

    @property
    def body(self) -> slice:
        return slice(self.offset + self.hdr, self.end)


def _iso_boxes(data: bytes, start: int, end: int) -> list[_Box]:
    out: list[_Box] = []
    off = start
    while off + 8 <= end:
        (size,) = struct.unpack(">I", data[off:off + 4])
        typ = data[off + 4:off + 8]
        hdr = 8
        if size == 1:
            if off + 16 > end:
                raise ProvenanceError(f"ISOBMFF largesize overruns at {off}")
            (size,) = struct.unpack(">Q", data[off + 8:off + 16])
            hdr = 16
        elif size == 0:
            size = end - off
        uuid = b""
        if typ == b"uuid":
            uuid = data[off + hdr:off + hdr + 16]
            hdr += 16
        if size < hdr or off + size > end:
            raise ProvenanceError(f"ISOBMFF box {typ!r} at {off} has bad size {size}")
        out.append(_Box(typ, off, size, hdr, uuid))
        off += size
    return out


def _iso_find(data: bytes, boxes: list[_Box], path: tuple[bytes, ...]) -> _Box | None:
    """Walk a box path, e.g. (b"meta", b"iinf")."""
    cur = boxes
    box: _Box | None = None
    for want in path:
        box = next((b for b in cur if b.typ == want), None)
        if box is None:
            return None
        inner = box.offset + box.hdr + (4 if box.typ in _ISO_FULLBOX_CONTAINERS else 0)
        if box.typ == b"iinf":
            # iinf FullBox: version 0 has a 2-byte count, version >=1 a 4-byte one.
            ver = data[box.offset + box.hdr]
            inner = box.offset + box.hdr + 4 + (2 if ver == 0 else 4)
        cur = _iso_boxes(data, inner, box.end) if want in _ISO_CONTAINER_BOXES else []
    return box


def _parse_iinf(data: bytes, iinf: _Box) -> list[tuple[int, bytes, _Box]]:
    """Return (item_id, item_type, infe_box) for every entry."""
    ver = data[iinf.offset + iinf.hdr]
    p = iinf.offset + iinf.hdr + 4
    p += 2 if ver == 0 else 4
    out = []
    for infe in _iso_boxes(data, p, iinf.end):
        if infe.typ != b"infe":
            continue
        b = infe.offset + infe.hdr
        iver = data[b]
        q = b + 4
        if iver in (2, 3):
            if iver == 2:
                item_id = struct.unpack(">H", data[q:q + 2])[0]
                q += 2
            else:
                item_id = struct.unpack(">I", data[q:q + 4])[0]
                q += 4
            q += 2                                        # protection_index
            item_type = data[q:q + 4]
            out.append((item_id, item_type, infe))
        else:
            out.append((-1, b"", infe))
    return out


# ISO/IEC 14496-12 §8.11.6: for a version 2/3 `infe` whose item_type is 'mime',
# the null-terminated item_name is followed by a null-terminated content_type.
# It is the ONLY authoritative statement of what an item holds — and it was
# parsed nowhere, so `mime` items were classified by grepping their payload for
# the literal bytes "xmpmeta". That missed two things: XMP serialised without
# the optional <x:xmpmeta> wrapper (XMP part 1 permits a bare rdf:RDF root, and
# Adobe's toolkit has kXMP_OmitXMPMetaElement for exactly this), and any
# non-XMP vendor sidecar. The second is the dangerous one: no Signal meant
# _strip_iso's drop set stayed empty, strip() returned the file unchanged, and
# a rescan by the same blind parser reported clean=True — while a payload like
# {"generator":"Higgsfield"} sat in the file, invisible to raw_residue() too.
_ISO_XMP_CONTENT_TYPES = frozenset({
    b"application/rdf+xml", b"application/xml", b"text/xml",
})
_ISO_C2PA_CONTENT_TYPES = frozenset({
    b"application/x-c2pa-manifest-store", b"application/c2pa",
})


def _infe_content_type(data: bytes, infe: _Box) -> bytes:
    """The declared content_type of a 'mime' item, or b"" if absent/unparseable."""
    b = infe.offset + infe.hdr
    if b >= len(data):
        return b""
    iver = data[b]
    if iver not in (2, 3):
        return b""
    q = b + 4
    q += 2 if iver == 2 else 4          # item_ID
    q += 2                              # item_protection_index
    if data[q:q + 4] != b"mime":
        return b""
    q += 4
    end = min(infe.end, len(data))
    nul = data.find(b"\x00", q, end)   # item_name
    if nul < 0:
        return b""
    q = nul + 1
    nul = data.find(b"\x00", q, end)   # content_type
    return (data[q:nul] if nul >= 0 else data[q:end]).strip().lower()


def _parse_iloc(data: bytes, iloc: _Box) -> tuple[dict, list[dict]]:
    """Parse an iloc box into (header-info, entries)."""
    b = iloc.offset + iloc.hdr
    ver = data[b]
    p = b + 4
    sizes = data[p]
    offset_size, length_size = sizes >> 4, sizes & 0xF
    sizes2 = data[p + 1]
    base_offset_size = sizes2 >> 4
    index_size = sizes2 & 0xF
    p += 2
    if ver < 2:
        item_count = struct.unpack(">H", data[p:p + 2])[0]
        p += 2
    else:
        item_count = struct.unpack(">I", data[p:p + 4])[0]
        p += 4

    def rd(n: int, at: int) -> int:
        if n == 0:
            return 0
        return int.from_bytes(data[at:at + n], "big")

    entries = []
    for _ in range(item_count):
        if ver < 2:
            item_id = struct.unpack(">H", data[p:p + 2])[0]; p += 2
        else:
            item_id = struct.unpack(">I", data[p:p + 4])[0]; p += 4
        construction = 0
        if ver in (1, 2):
            construction = struct.unpack(">H", data[p:p + 2])[0] & 0xF
            p += 2
        data_ref_index = struct.unpack(">H", data[p:p + 2])[0]; p += 2
        base_offset = rd(base_offset_size, p); p += base_offset_size
        extent_count = struct.unpack(">H", data[p:p + 2])[0]; p += 2
        extents = []
        for _e in range(extent_count):
            idx = rd(index_size, p) if ver in (1, 2) else 0
            p += index_size if ver in (1, 2) else 0
            eoff = rd(offset_size, p); p += offset_size
            elen = rd(length_size, p); p += length_size
            extents.append({"index": idx, "offset": eoff, "length": elen})
        entries.append({
            "item_id": item_id, "construction": construction,
            "data_ref_index": data_ref_index, "base_offset": base_offset,
            "extents": extents,
        })
    info = {
        "version": ver, "offset_size": offset_size, "length_size": length_size,
        "base_offset_size": base_offset_size, "index_size": index_size,
        "flags": int.from_bytes(data[b + 1:b + 4], "big"),
    }
    return info, entries


def _build_iloc(info: dict, entries: list[dict]) -> bytes:
    """Re-emit an iloc box with 8-byte offsets so its size is stable across passes."""
    ver = info["version"]
    offset_size, length_size = 8, 8
    base_offset_size, index_size = 0, (info["index_size"] if ver in (1, 2) else 0)
    body = bytearray()
    body.append(ver)
    body += info["flags"].to_bytes(3, "big")
    body.append((offset_size << 4) | length_size)
    body.append((base_offset_size << 4) | index_size)
    if ver < 2:
        body += struct.pack(">H", len(entries))
    else:
        body += struct.pack(">I", len(entries))
    for e in entries:
        if ver < 2:
            body += struct.pack(">H", e["item_id"])
        else:
            body += struct.pack(">I", e["item_id"])
        if ver in (1, 2):
            body += struct.pack(">H", e["construction"] & 0xF)
        body += struct.pack(">H", e["data_ref_index"])
        body += struct.pack(">H", len(e["extents"]))
        for ex in e["extents"]:
            if index_size:
                body += ex["index"].to_bytes(index_size, "big")
            body += ex["offset"].to_bytes(8, "big")
            body += ex["length"].to_bytes(8, "big")
    return struct.pack(">I", len(body) + 8) + b"iloc" + bytes(body)


def _scan_iso(data: bytes, rep: Report) -> None:
    top = _iso_boxes(data, 0, len(data))
    for b in top:
        if b.typ == b"uuid" and b.uuid in (_C2PA_UUID, _C2PA_UUID_ALT):
            blob = data[b.body]
            rep.signals.append(Signal(kind="c2pa", where="ISOBMFF:uuid", offset=b.offset,
                                      length=b.size, removable=True, detail="C2PA JUMBF store"))
            rep.generators.extend(g for g in _mine_generators(blob) if g not in rep.generators)
            for w in _mine_watermark_declarations(blob):
                if w not in rep.undetectable_watermarks:
                    rep.undetectable_watermarks.append(w)

    meta = next((b for b in top if b.typ == b"meta"), None)
    if meta is None:
        return
    inner = _iso_boxes(data, meta.offset + meta.hdr + 4, meta.end)
    iinf = next((b for b in inner if b.typ == b"iinf"), None)
    iloc = next((b for b in inner if b.typ == b"iloc"), None)
    if iinf is None or iloc is None:
        return
    items = _parse_iinf(data, iinf)
    _info, entries = _parse_iloc(data, iloc)
    by_id = {e["item_id"]: e for e in entries}
    for item_id, item_type, infe in items:
        kind = {b"Exif": "exif", b"mime": "xmp", b"c2pa": "c2pa"}.get(item_type)
        if kind is None:
            continue
        ent = by_id.get(item_id)
        blob = b""
        length = infe.size
        if ent:
            for ex in ent["extents"]:
                s = ent["base_offset"] + ex["offset"]
                blob += data[s:s + ex["length"]]
                length += ex["length"]
        detail_extra = ""
        if item_type == b"mime":
            # Decide from the DECLARED content_type, falling back to the payload
            # sniff only when the infe is malformed enough not to carry one.
            ctype = _infe_content_type(data, infe)
            if ctype in _ISO_C2PA_CONTENT_TYPES:
                kind = "c2pa"
            elif ctype in _ISO_XMP_CONTENT_TYPES:
                kind = "xmp"
            elif ctype:
                # A vendor sidecar. It is ancillary metadata by construction —
                # a `meta` item is not the picture, and render-essential parts
                # of an AVIF/HEIF are coded item types (av01/hvc1) or `Exif`,
                # never `mime`. Report it, name what it declared itself to be,
                # and let the policy decide.
                kind = "other_metadata"
                detail_extra = f"content_type={ctype.decode('latin1', 'replace')}"
            elif b"xmpmeta" in blob or b"rdf:RDF" in blob:
                kind = "xmp"
            elif b"c2pa" in blob or b"jumb" in blob:
                kind = "c2pa"
            else:
                continue                              # no type, no payload signal
        refined, extra = _classify_blob(blob, kind)
        extra = f"{extra} {detail_extra}".strip()
        rep.signals.append(Signal(
            kind=refined, where=f"ISOBMFF:item:{item_type.decode('latin1', 'replace')}",
            offset=infe.offset, length=length, removable=True,
            detail=f"item_id={item_id} {extra}".strip(),
        ))
        rep.generators.extend(g for g in _mine_generators(blob) if g not in rep.generators)
        for w in _mine_watermark_declarations(blob):
            if w not in rep.undetectable_watermarks:
                rep.undetectable_watermarks.append(w)
                rep.signals.append(Signal(kind="watermark_declared",
                                          where=f"ISOBMFF:item:{item_type.decode('latin1', 'replace')}",
                                          offset=infe.offset, length=0, removable=False, detail=w))


def _strip_iso(data: bytes, policy: Policy, rep: Report) -> tuple[bytes, list[Signal]]:
    """Remux an AVIF/HEIF without its metadata items.

    Strategy: keep every box verbatim except ``meta`` (rebuilt without the
    dropped items) and ``mdat`` (re-laid to hold only surviving item bytes).
    ``iloc`` is re-emitted with fixed 8-byte offsets so its length does not
    change between the two layout passes, which makes the offset fixpoint exact
    rather than iterative.
    """
    removed: list[Signal] = []
    top = _iso_boxes(data, 0, len(data))
    meta = next((b for b in top if b.typ == b"meta"), None)

    drop_kinds = {s.kind for s in rep.signals if s.removable and policy.wants(s.kind)}
    if not drop_kinds:
        return data, removed
    # A movie box means track samples live in mdat, addressed by moov/stco
    # offsets this code neither reads nor rewrites. Checked FIRST: the two early
    # returns below excise a top-level uuid box, which shifts every byte after
    # it and invalidates those offsets just as thoroughly as a full remux — and
    # _iso_pixel_digest hashes mdat bodies, so verify_lossless cannot see it.
    if any(b.typ in (b"moov", b"moof", b"mvex") for b in top):
        raise ProvenanceError(
            "ISOBMFF carries a movie box (animated AVIF / HEIF sequence); rewriting it "
            "would invalidate the track sample offsets. Refusing to rewrite.")



    # 1. Top-level C2PA uuid boxes: a straight excision, no reflow needed beyond mdat.
    drop_uuid = [b for b in top
                 if b.typ == b"uuid" and b.uuid in (_C2PA_UUID, _C2PA_UUID_ALT) and policy.strip_c2pa]
    for b in drop_uuid:
        removed.append(Signal(kind="c2pa", where="ISOBMFF:uuid", offset=b.offset,
                              length=b.size, removable=True, detail="C2PA JUMBF store"))

    if meta is None:
        out = b"".join(data[b.offset:b.end] for b in top if b not in drop_uuid)
        return out, removed

    inner = _iso_boxes(data, meta.offset + meta.hdr + 4, meta.end)
    iinf = next((b for b in inner if b.typ == b"iinf"), None)
    iloc_box = next((b for b in inner if b.typ == b"iloc"), None)
    if iinf is None or iloc_box is None:
        out = b"".join(data[b.offset:b.end] for b in top if b not in drop_uuid)
        return out, removed

    # ── refuse to remux a file whose mdat we do not fully account for ──────
    # The remux rebuilds mdat from meta-level iloc items ONLY. That is exact for
    # a still image (measured: iloc covers 100% of mdat), but an animated AVIF
    # (`avis`) or a HEIF sequence also stores TRACK samples in mdat, addressed by
    # moov/stco offsets this code neither reads nor rewrites. Remuxing such a
    # file deletes the track data and leaves moov pointing at nothing — and
    # _iso_pixel_digest only hashes meta-level picture items, so verify_lossless
    # would report lossless=True on a file that no longer decodes.
    #
    # Rather than teach the remux about tracks, refuse: a container we cannot
    # fully account for is one we must not rewrite. Excising a top-level C2PA
    # uuid box stays safe and is handled above, because it does not touch mdat.
    _info_pre, entries_pre = _parse_iloc(data, iloc_box)
    covered = 0
    for e in entries_pre:
        if e["construction"] != 0:
            continue
        for ex in e["extents"]:
            covered += ex["length"]
    mdat_payload = sum(b.size - b.hdr for b in top if b.typ == b"mdat")
    if mdat_payload and covered < mdat_payload:
        raise ProvenanceError(
            f"ISOBMFF mdat holds {mdat_payload - covered} byte(s) no iloc extent accounts for; "
            "rebuilding it would silently drop them. Refusing to rewrite.")

    items = _parse_iinf(data, iinf)
    info, entries = _parse_iloc(data, iloc_box)
    by_id = {e["item_id"]: e for e in entries}

    sig_by_offset = {s.offset: s for s in rep.signals if s.length > 0}
    by_id_pre = {e["item_id"]: e for e in entries}
    drop_ids: set[int] = set()
    for item_id, item_type, infe in items:
        sig = sig_by_offset.get(infe.offset)
        if sig is not None and sig.removable and policy.wants(sig.kind):
            ent = by_id_pre.get(item_id)
            if ent is not None and ent["construction"] != 0:
                # construction_method 1/2 put the payload in `idat` or another
                # item, neither of which the mdat rebuild touches. De-registering
                # the item while copying its bytes verbatim reported
                # removed=['exif'], lossless=True with the data still in the file.
                raise ProvenanceError(
                    f"ISOBMFF item {item_id} uses construction_method "
                    f"{ent['construction']}; its payload is not in mdat and cannot be "
                    "evicted by this remux. Refusing to rewrite.")
            drop_ids.add(item_id)
            removed.append(sig)
    if not drop_ids and not drop_uuid:
        return data, removed

    # 2. Rebuild iinf without the dropped infe entries.
    ver = data[iinf.offset + iinf.hdr]
    kept_infe = [infe for (iid, _t, infe) in items if iid not in drop_ids]
    iinf_body = bytearray(data[iinf.offset + iinf.hdr:iinf.offset + iinf.hdr + 4])
    iinf_body += (struct.pack(">H", len(kept_infe)) if ver == 0 else struct.pack(">I", len(kept_infe)))
    for infe in kept_infe:
        iinf_body += data[infe.offset:infe.end]
    new_iinf = struct.pack(">I", len(iinf_body) + 8) + b"iinf" + bytes(iinf_body)

    # 3. Rebuild iref, dropping references to and from dropped items.
    iref_box = next((b for b in inner if b.typ == b"iref"), None)
    new_iref = b""
    if iref_box is not None:
        iref_ver = data[iref_box.offset + iref_box.hdr]
        idsz = 2 if iref_ver == 0 else 4
        body = bytearray(data[iref_box.offset + iref_box.hdr:iref_box.offset + iref_box.hdr + 4])
        for ref in _iso_boxes(data, iref_box.offset + iref_box.hdr + 4, iref_box.end):
            p = ref.offset + ref.hdr
            from_id = int.from_bytes(data[p:p + idsz], "big")
            cnt = struct.unpack(">H", data[p + idsz:p + idsz + 2])[0]
            q = p + idsz + 2
            to_ids = [int.from_bytes(data[q + i * idsz:q + (i + 1) * idsz], "big") for i in range(cnt)]
            if from_id in drop_ids:
                continue
            to_ids = [t for t in to_ids if t not in drop_ids]
            if not to_ids:
                continue
            rb = from_id.to_bytes(idsz, "big") + struct.pack(">H", len(to_ids))
            rb += b"".join(t.to_bytes(idsz, "big") for t in to_ids)
            body += struct.pack(">I", len(rb) + 8) + ref.typ + rb
        if len(body) > 4:
            new_iref = struct.pack(">I", len(body) + 8) + b"iref" + bytes(body)

    # 4. Rebuild ipma, dropping property associations for dropped items.
    ipma_box = None
    iprp_box = next((b for b in inner if b.typ == b"iprp"), None)
    new_iprp = b""
    if iprp_box is not None:
        iprp_inner = _iso_boxes(data, iprp_box.offset + iprp_box.hdr, iprp_box.end)
        ipma_box = next((b for b in iprp_inner if b.typ == b"ipma"), None)
        if ipma_box is None:
            new_iprp = data[iprp_box.offset:iprp_box.end]
        else:
            ip = ipma_box.offset + ipma_box.hdr
            ipver = data[ip]
            ipflags = int.from_bytes(data[ip + 1:ip + 4], "big")
            idsz = 2 if ipver < 1 else 4
            propsz = 2 if (ipflags & 1) else 1
            cnt = struct.unpack(">I", data[ip + 4:ip + 8])[0]
            q = ip + 8
            body = bytearray(data[ip:ip + 4])
            kept = []
            for _ in range(cnt):
                iid = int.from_bytes(data[q:q + idsz], "big"); q += idsz
                n_assoc = data[q]; q += 1
                assoc = data[q:q + n_assoc * propsz]; q += n_assoc * propsz
                if iid in drop_ids:
                    continue
                kept.append(iid.to_bytes(idsz, "big") + bytes([n_assoc]) + assoc)
            body += struct.pack(">I", len(kept))
            for k in kept:
                body += k
            new_ipma = struct.pack(">I", len(body) + 8) + b"ipma" + bytes(body)
            iprp_body = b"".join(
                (new_ipma if b is ipma_box else data[b.offset:b.end]) for b in iprp_inner
            )
            new_iprp = struct.pack(">I", len(iprp_body) + 8) + b"iprp" + iprp_body

    # 5. Collect surviving item payloads in a stable order; they become the new mdat.
    kept_entries = [e for e in entries if e["item_id"] not in drop_ids]
    payloads: list[bytes] = []
    for e in kept_entries:
        if e["construction"] != 0:
            # construction_method 1 = idat-relative, 2 = item-relative. Neither
            # points into mdat, so those extents are left exactly as they are.
            payloads.append(b"")
            continue
        blob = b"".join(
            data[e["base_offset"] + ex["offset"]: e["base_offset"] + ex["offset"] + ex["length"]]
            for ex in e["extents"]
        )
        payloads.append(blob)

    # 6. Two-pass layout. Pass 1 lays the boxes out with placeholder offsets to
    #    learn the final mdat start; pass 2 writes the real offsets. Because
    #    _build_iloc always emits 8-byte offsets, the iloc length is identical in
    #    both passes, so pass 2 needs no further correction.
    def assemble(mdat_start: int) -> bytes:
        cursor = mdat_start + 8
        new_entries = []
        for e, blob in zip(kept_entries, payloads):
            if e["construction"] != 0 or not blob:
                new_entries.append(e)
                continue
            new_entries.append({**e, "base_offset": 0,
                                "extents": [{"index": 0, "offset": cursor, "length": len(blob)}]})
            cursor += len(blob)
        new_iloc = _build_iloc(info, new_entries)
        meta_body = bytearray(data[meta.offset + meta.hdr:meta.offset + meta.hdr + 4])
        for b in inner:
            if b is iinf:
                meta_body += new_iinf
            elif b is iloc_box:
                meta_body += new_iloc
            elif iref_box is not None and b is iref_box:
                meta_body += new_iref
            elif iprp_box is not None and b is iprp_box:
                meta_body += new_iprp
            else:
                meta_body += data[b.offset:b.end]
        new_meta = struct.pack(">I", len(meta_body) + 8) + b"meta" + bytes(meta_body)

        head = bytearray()
        for b in top:
            if b is meta:
                head += new_meta
            elif b.typ == b"mdat" or b in drop_uuid:
                continue
            else:
                head += data[b.offset:b.end]
        mdat_payload = b"".join(p for p in payloads if p)
        return bytes(head), mdat_payload

    head, _ = assemble(0)
    head, mdat_payload = assemble(len(head))
    out = head + struct.pack(">I", len(mdat_payload) + 8) + b"mdat" + mdat_payload
    return out, removed


# =============================================================================
# public entry points
# =============================================================================
_SCANNERS = {
    "png": _scan_png, "jpeg": _scan_jpeg, "webp": _scan_webp, "svg": _scan_svg,
    "gif": _scan_gif, "avif": _scan_iso, "heif": _scan_iso, "isobmff": _scan_iso,
}
_STRIPPERS = {
    "png": _strip_png, "jpeg": _strip_jpeg, "webp": _strip_webp, "svg": _strip_svg,
    "gif": _strip_gif, "avif": _strip_iso, "heif": _strip_iso, "isobmff": _strip_iso,
}


def scan(data: bytes) -> Report:
    """Inventory every provenance signal in ``data``. Never raises on bad input."""
    container = sniff(data)
    rep = Report(container=container, size=len(data))
    fn = _SCANNERS.get(container)
    if fn is None:
        rep.parse_error = f"unsupported container: {container}"
        return rep
    try:
        fn(data, rep)
    except ProvenanceError as e:
        rep.parse_error = str(e)
    except (struct.error, IndexError, ValueError) as e:
        rep.parse_error = f"{type(e).__name__}: {e}"
    return rep


def strip(data: bytes, *, policy: Policy = DEFAULT_POLICY, verify: bool = True) -> Result:
    """Remove provenance metadata losslessly.

    Raises ``ProvenanceError`` when the container cannot be parsed safely, or
    when ``verify`` is on and the rewritten file fails the lossless check. It
    never returns a file it could not prove.
    """
    container = sniff(data)
    before = scan(data)
    if before.parse_error:
        raise ProvenanceError(f"cannot rewrite: {before.parse_error}")
    fn = _STRIPPERS.get(container)
    if fn is None:
        raise ProvenanceError(f"unsupported container: {container}")

    # The contract is "returns a proven-clean file, or raises ProvenanceError".
    # A struct.error / IndexError / StopIteration escaping from a container
    # handler would violate it and reach the caller as an unexpected crash — the
    # fuzz suite caught exactly that on mutated GIFs. Convert at the boundary so
    # there is genuinely no third outcome.
    try:
        out, removed = fn(data, policy, before)
    except ProvenanceError:
        raise
    except (struct.error, IndexError, ValueError, StopIteration, MemoryError, OverflowError) as e:
        raise ProvenanceError(f"rewrite failed: {type(e).__name__}: {e}") from e
    after = scan(out)
    if after.parse_error:
        raise ProvenanceError(f"rewritten file does not parse: {after.parse_error}")

    result = Result(
        data=out, container=container, before=before, after=after,
        removed=removed,
        kept=[s for s in before.signals if s not in removed],
        bytes_removed=len(data) - len(out),
        policy=policy,
    )

    surviving = [s for s in after.signals if s.removable and policy.wants(s.kind)]
    if surviving:
        raise ProvenanceError(
            "strip did not remove everything it claimed: "
            + ", ".join(f"{s.kind}@{s.where}" for s in surviving)
        )

    if verify:
        ok, note = verify_lossless(data, out)
        result.lossless = ok
        result.note = note
        if not ok:
            raise ProvenanceError(f"lossless verification failed: {note}")
    return result


# ── lossless verification ────────────────────────────────────────────────────
def _png_pixel_digest(data: bytes) -> str:
    h = hashlib.sha256()
    for _off, ctype, payload, _t in _png_chunks(data):
        if ctype in (b"IHDR", b"PLTE", b"IDAT", b"tRNS", b"acTL", b"fcTL", b"fdAT"):
            h.update(ctype); h.update(payload)
    return h.hexdigest()


def _jpeg_pixel_digest(data: bytes) -> str:
    h = hashlib.sha256()
    tail = len(data)
    for off, marker, payload, _t in _jpeg_segments(data):
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC9,
                      0xCA, 0xCB, 0xCD, 0xCE, 0xCF, 0xDB, 0xDD):
            h.update(bytes([marker])); h.update(payload)
        if marker == 0xDA:
            h.update(b"SOS"); h.update(payload)
            tail = off
            break
    h.update(data[tail:])
    return h.hexdigest()


def _webp_pixel_digest(data: bytes) -> str:
    h = hashlib.sha256()
    for _off, fourcc, payload, _t in _webp_chunks(data):
        if fourcc in (b"VP8 ", b"VP8L", b"ALPH", b"ANIM", b"ANMF"):
            h.update(fourcc); h.update(payload)
    return h.hexdigest()


def _gif_pixel_digest(data: bytes) -> str:
    h = hashlib.sha256()
    try:
        first = next(iter(_gif_blocks(data)))[0]
    except StopIteration:
        raise ProvenanceError("GIF has no parseable blocks") from None
    h.update(data[:first])
    for off, kind, total, _p in _gif_blocks(data):
        if kind in ("image", "gce", "plaintext"):
            h.update(data[off:off + total])
    return h.hexdigest()


def _iso_pixel_digest(data: bytes) -> str:
    """Digest the *primary item's* coded bytes, resolved through iloc."""
    h = hashlib.sha256()
    top = _iso_boxes(data, 0, len(data))
    meta = next((b for b in top if b.typ == b"meta"), None)
    if meta is None:
        for b in top:
            if b.typ == b"mdat":
                h.update(data[b.body])
        return h.hexdigest()
    inner = _iso_boxes(data, meta.offset + meta.hdr + 4, meta.end)
    iinf = next((b for b in inner if b.typ == b"iinf"), None)
    iloc = next((b for b in inner if b.typ == b"iloc"), None)
    if iinf is None or iloc is None:
        return h.hexdigest()
    meta_types = {b"Exif", b"mime", b"c2pa"}
    picture_ids = [iid for iid, ityp, _b in _parse_iinf(data, iinf) if ityp not in meta_types]
    _info, entries = _parse_iloc(data, iloc)
    for e in sorted(entries, key=lambda x: x["item_id"]):
        if e["item_id"] not in picture_ids or e["construction"] != 0:
            continue
        for ex in e["extents"]:
            s = e["base_offset"] + ex["offset"]
            h.update(data[s:s + ex["length"]])
    return h.hexdigest()


_DIGESTS = {
    "png": _png_pixel_digest, "jpeg": _jpeg_pixel_digest, "webp": _webp_pixel_digest,
    "gif": _gif_pixel_digest, "avif": _iso_pixel_digest, "heif": _iso_pixel_digest,
    "isobmff": _iso_pixel_digest, "svg": _svg_pixel_digest,
}


def verify_lossless(before: bytes, after: bytes) -> tuple[bool, str]:
    """Prove the pixel payload is byte-identical across a strip.

    This is a *container-level* proof: it hashes the coded image data and the
    parameters needed to decode it (PNG IHDR/PLTE/IDAT, JPEG SOF/DHT/DQT/SOS,
    WebP VP8/VP8L/ALPH, ISOBMFF primary-item extents) while ignoring metadata.
    It does not decode, so it needs no codec and cannot be fooled by an encoder
    that happens to produce similar-looking output.
    """
    cb, ca = sniff(before), sniff(after)
    if cb != ca:
        return False, f"container changed: {cb} -> {ca}"
    fn = _DIGESTS.get(cb)
    if fn is None:
        return False, f"no digest for container {cb}"
    try:
        db, da = fn(before), fn(after)
    except ProvenanceError as e:
        return False, f"digest failed: {e}"
    if db != da:
        return False, f"pixel payload changed ({db[:12]} -> {da[:12]})"
    return True, f"pixel payload identical (sha256 {db[:16]}…)"


# ── raw fallback sweep ───────────────────────────────────────────────────────
_RAW_MARKERS: tuple[tuple[bytes, str], ...] = (
    (b"c2pa", "c2pa"),
    (b"jumb", "c2pa"),
    (b"trainedAlgorithmicMedia", "iptc_ai"),
    (b"digitalSourceType", "iptc_ai"),
    (b"<x:xmpmeta", "xmp"),
    (b"Exif\x00\x00", "exif"),
    (b"dcterms:provenance", "c2pa"),     # URI pointing at an off-file manifest
    (b"C2PA_GIF", "c2pa"),               # GIF application-extension identifier
    (b"c2pa:manifest", "c2pa"),          # SVG embedding
)


# Needles long and specific enough that finding them in compressed pixel data is
# implausible. The 4-byte ones (`c2pa`, `jumb`) are excellent for a post-strip
# assertion — where a false positive costs a re-check — but useless as evidence
# on an arbitrary file: a metadata-free PNG whose IDAT bytes happen to spell
# "c2pa" was being reported DIRTY with nothing to strip, which in replace/cms
# became verify_failed -> exit 2 -> reprocessed forever.
_HIGH_CONFIDENCE_MARKERS = frozenset({
    b"trainedAlgorithmicMedia", b"digitalSourceType", b"<x:xmpmeta",
    b"dcterms:provenance", b"C2PA_GIF", b"c2pa:manifest",
})


def raw_residue(data: bytes, *, strict: bool = False,
                high_confidence_only: bool = False) -> list[tuple[str, str, int]]:
    """Byte-level backstop: find provenance strings anywhere in the file.

    ``scan()`` is structure-aware and only looks where metadata is *supposed* to
    live. This finds it wherever it actually is — including places a malformed
    or novel container hid it. Used by the test suite and by ``--paranoid`` to
    assert that a stripped file contains no residue at all.

    By default the orientation-only EXIF block that ``_strip_jpeg`` re-emits is
    not reported: it is 36 bytes holding a single Orientation tag, and flagging
    its ``Exif\\0\\0`` marker would make every rotated photograph look dirty.
    Pass ``strict=True`` to see literally every match.
    """
    out = []
    for needle, kind in _RAW_MARKERS:
        if high_confidence_only and needle not in _HIGH_CONFIDENCE_MARKERS:
            continue
        for m in re.finditer(re.escape(needle), data):
            at = m.start()
            if (not strict and needle == b"Exif\x00\x00"
                    and _is_orientation_only_exif(data[at:at + _ORIENTATION_EXIF_LEN])):
                continue
            out.append((kind, needle.decode("latin1"), at))
    return out
