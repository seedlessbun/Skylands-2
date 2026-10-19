"""Read TGA / PNG (what UModel exports) and write a small uncompressed DDS for Skyrim.

Textures are cut down to at most `max_size` pixels a side by picking every n-th pixel: Skylands guns are small on screen
and uncompressed BGRA keeps this free of any encoder.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from .skyrim import nif


class ImageError(ValueError):
    pass


def _stride(w: int, h: int, max_size: int) -> int:
    s = 1
    while w // s > max_size or h // s > max_size:
        s *= 2
    return s


def load_rgba(path: Path, max_size: int = 256) -> tuple[int, int, bytes]:
    data = Path(path).read_bytes()
    ext = Path(path).suffix.lower()
    if ext == ".tga":
        return _tga(data, max_size)
    if ext == ".png":
        return _png(data, max_size)
    raise ImageError(f"unsupported image type {ext}")


def _tga(data: bytes, max_size: int) -> tuple[int, int, bytes]:
    idlen, cmap, itype = data[0], data[1], data[2]
    w, h = struct.unpack_from("<HH", data, 12)
    bpp, desc = data[16], data[17]
    if cmap or itype not in (2, 3, 10, 11) or bpp not in (8, 24, 32) or w == 0 or h == 0:
        raise ImageError(f"unsupported TGA (type {itype}, {bpp} bpp)")
    n = bpp // 8
    p = 18 + idlen
    if itype in (10, 11):
        raw = bytearray()
        total = w * h * n
        while len(raw) < total and p < len(data):
            head = data[p]
            p += 1
            cnt = (head & 0x7F) + 1
            if head & 0x80:
                raw += data[p:p + n] * cnt
                p += n
            else:
                raw += data[p:p + cnt * n]
                p += cnt * n
        pix = bytes(raw)
    else:
        pix = data[p:p + w * h * n]
    if len(pix) < w * h * n:
        raise ImageError("TGA is cut off")
    s = _stride(w, h, max_size)
    ow, oh = w // s, h // s
    out = bytearray()
    top_left = bool(desc & 0x20)
    for y in range(oh):
        sy = y * s if top_left else (h - 1 - y * s)
        row = sy * w * n
        for x in range(ow):
            o = row + x * s * n
            if n == 1:
                g = pix[o]
                out += bytes((g, g, g, 255))
            else:
                b, g, r = pix[o], pix[o + 1], pix[o + 2]
                out += bytes((r, g, b, pix[o + 3] if n == 4 else 255))
    return ow, oh, bytes(out)


def _png(data: bytes, max_size: int) -> tuple[int, int, bytes]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ImageError("not a PNG")
    p = 8
    idat = b""
    w = h = depth = ctype = interlace = 0
    palette = b""
    while p + 8 <= len(data):
        ln, kind = struct.unpack_from(">I4s", data, p)
        body = data[p + 8:p + 8 + ln]
        p += 12 + ln
        if kind == b"IHDR":
            w, h, depth, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = body
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    if depth != 8 or interlace or ctype not in (0, 2, 3, 4, 6):
        raise ImageError(f"unsupported PNG (depth {depth}, type {ctype}, interlace {interlace})")
    if w * h > 2048 * 2048:
        raise ImageError("PNG too large to read here")
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows = []
    prev = bytearray(stride)
    q = 0
    for _ in range(h):
        ft = raw[q]
        line = bytearray(raw[q + 1:q + 1 + stride])
        q += 1 + stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        elif ft != 0:
            raise ImageError(f"bad PNG filter {ft}")
        rows.append(line)
        prev = line
    s = _stride(w, h, max_size)
    ow, oh = w // s, h // s
    out = bytearray()
    for y in range(oh):
        line = rows[y * s]
        for x in range(ow):
            o = x * s * bpp
            if ctype == 6:
                out += bytes(line[o:o + 4])
            elif ctype == 2:
                out += bytes(line[o:o + 3]) + b"\xff"
            elif ctype == 0:
                out += bytes((line[o],) * 3) + b"\xff"
            elif ctype == 4:
                out += bytes((line[o],) * 3) + bytes((line[o + 1],))
            else:
                i = line[o] * 3
                out += bytes(palette[i:i + 3]) + b"\xff"
    return ow, oh, bytes(out)


def to_dds(path: Path, max_size: int = 256) -> bytes:
    """DDS bytes for an exported image: `.dds` is passed through, `.tga` and `.png` are converted."""
    if Path(path).suffix.lower() == ".dds":
        return Path(path).read_bytes()
    w, h, rgba = load_rgba(path, max_size)
    bgra = bytearray(len(rgba))
    bgra[0::4], bgra[1::4], bgra[2::4], bgra[3::4] = rgba[2::4], rgba[1::4], rgba[0::4], rgba[3::4]
    return nif._dds_bgra(w, h, bytes(bgra))  # noqa: SLF001
