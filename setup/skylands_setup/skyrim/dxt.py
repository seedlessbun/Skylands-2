"""Read and write DXT1/DXT5 DDS images (enough for gun textures): decode to RGB, re-encode as opaque DXT1.

Borderlands 2's weapon "Comp" textures turned out to be packed channels, not a colour picture; the gun builder reads one,
keeps its structure as brightness and tints it with the manufacturer's colour (`shade`).
"""

from __future__ import annotations

import struct


def parse_dds(data: bytes) -> tuple[int, int, bytes, bytes]:
    if data[:4] != b"DDS ":
        raise ValueError("not a DDS file")
    h, w = struct.unpack_from("<II", data, 12)
    return w, h, data[84:88], data[128:]


def _rgb565(v: int) -> tuple[int, int, int]:
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return (r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31


def decode(data: bytes, step: int = 1) -> tuple[int, int, bytearray]:
    """(width, height, RGB bytes) of a DXT1/DXT5 DDS, keeping every `step`-th pixel in each direction."""
    w, h, fourcc, pixels = parse_dds(data)
    if fourcc not in (b"DXT1", b"DXT5"):
        raise ValueError(f"unsupported format {fourcc!r}")
    per = 8 if fourcc == b"DXT1" else 16
    bw = (w + 3) // 4
    ow, oh = w // step, h // step
    out = bytearray(ow * oh * 3)
    for by in range((h + 3) // 4):
        for bx in range(bw):
            o = (by * bw + bx) * per + (per - 8)
            c0, c1, bits = struct.unpack_from("<HHI", pixels, o)
            p0, p1 = _rgb565(c0), _rgb565(c1)
            if c0 > c1 or per == 16:
                pal = [p0, p1, tuple((2 * a + b) // 3 for a, b in zip(p0, p1)), tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))]
            else:
                pal = [p0, p1, tuple((a + b) // 2 for a, b in zip(p0, p1)), (0, 0, 0)]
            for j in range(4):
                y = by * 4 + j
                if y % step or y // step >= oh:
                    continue
                for i in range(4):
                    x = bx * 4 + i
                    if x % step or x // step >= ow:
                        continue
                    q = ((y // step) * ow + x // step) * 3
                    out[q:q + 3] = bytes(pal[(bits >> (2 * (4 * j + i))) & 3])
    return ow, oh, out


def _565(r: int, g: int, b: int) -> int:
    return ((r * 31 + 127) // 255 << 11) | ((g * 63 + 127) // 255 << 5) | ((b * 31 + 127) // 255)


def encode(w: int, h: int, rgb: bytes) -> bytes:
    """An opaque DXT1 DDS (width and height multiples of 4) from RGB bytes; endpoints are the darkest and brightest pixel of each block."""
    out = bytearray()
    for by in range(h // 4):
        for bx in range(w // 4):
            px = [tuple(rgb[((by * 4 + j) * w + bx * 4 + i) * 3:((by * 4 + j) * w + bx * 4 + i) * 3 + 3]) for j in range(4) for i in range(4)]
            lum = [3 * p[0] + 6 * p[1] + p[2] for p in px]
            lo, hi = px[lum.index(min(lum))], px[lum.index(max(lum))]
            a, b = _565(*hi), _565(*lo)
            if a == b:
                out += struct.pack("<HHI", a, b, 0)
                continue
            if a < b:
                a, b = b, a
                lo, hi = hi, lo
            e0, e1 = _rgb565(a), _rgb565(b)
            pal = [e0, e1, tuple((2 * x + y) // 3 for x, y in zip(e0, e1)), tuple((x + 2 * y) // 3 for x, y in zip(e0, e1))]
            bits = 0
            for k, p in enumerate(px):
                best = min(range(4), key=lambda n: (p[0] - pal[n][0]) ** 2 + (p[1] - pal[n][1]) ** 2 + (p[2] - pal[n][2]) ** 2)
                bits |= best << (2 * k)
            out += struct.pack("<HHI", a, b, bits)
    header = b"DDS " + struct.pack("<7I", 124, 0x1007 | 0x80000, h, w, len(out), 0, 1) + b"\0" * 44
    header += struct.pack("<II4s5I", 32, 4, b"DXT1", 0, 0, 0, 0, 0) + struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    return header + bytes(out)


def mean_saturation(rgb: bytes, samples: int = 4000) -> float:
    n = len(rgb) // 3
    step = max(1, n // samples)
    total = count = 0
    for i in range(0, n, step):
        r, g, b = rgb[3 * i:3 * i + 3]
        m = max(r, g, b)
        if m > 16:
            total += (m - min(r, g, b)) / m
            count += 1
    return total / count if count else 0.0


def prepare(data: bytes, max_side: int = 512) -> tuple[int, int, bytes, float]:
    """The image reduced to at most max_side pixels across, as (width, height, RGB, mean saturation)."""
    w, h, _, _ = parse_dds(data)
    step = max(1, max(w, h) // max_side)
    ow, oh, rgb = decode(data, step)
    cw, ch = ow - ow % 4, oh - oh % 4
    if (cw, ch) != (ow, oh):
        rgb = bytearray(b"".join(bytes(rgb[y * ow * 3:(y * ow + cw) * 3]) for y in range(ch)))
    return cw, ch, bytes(rgb), mean_saturation(bytes(rgb))


def shade(prepared: tuple[int, int, bytes, float], tint: tuple[int, int, int]) -> tuple[bytes, str]:
    """A gun texture in the manufacturer's colour. A texture that is already a plain colour picture is kept; a packed one
    (very saturated everywhere: its channels are separate maps) keeps only its brightness, tinted with `tint`."""
    w, h, rgb, sat = prepared
    if sat < 0.45:
        return encode(w, h, rgb), f"kept the picture (saturation {sat:.2f})"
    out = bytearray(len(rgb))
    for i in range(0, len(rgb), 3):
        lum = (299 * rgb[i] + 587 * rgb[i + 1] + 114 * rgb[i + 2]) / 255000
        k = 0.4 + 0.9 * lum
        out[i], out[i + 1], out[i + 2] = (min(255, int(t * k)) for t in tint)
    return encode(w, h, bytes(out)), f"packed channels (saturation {sat:.2f}): brightness tinted"
