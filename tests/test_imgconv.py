import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))

from skylands_setup import imgconv  # noqa: E402


def tga(w, h, rle=False):
    px = b"".join(bytes((7, y * 10 % 256, x * 10 % 256, 255)) for y in range(h) for x in range(w))  # B G R A
    head = bytes((0, 0, 10 if rle else 2)) + b"\0" * 9 + struct.pack("<HH", w, h) + bytes((32, 0x20))
    if rle:
        body = b"".join(bytes((0x80,)) + px[i:i + 4] for i in range(0, len(px), 4))  # one-pixel runs of 1
        return head + body
    return head + px


def png(w, h, ctype=6, filt=4):
    n = 4 if ctype == 6 else 3
    rows = []
    prev = bytearray(w * n)
    for y in range(h):
        line = bytearray()
        for x in range(w):
            line += bytes((x * 10 % 256, y * 10 % 256, 7, 255)[:n])
        # filter all rows with the chosen type
        out = bytearray()
        for i in range(len(line)):
            a = line[i - n] if i >= n else 0
            b = prev[i]
            c = prev[i - n] if i >= n else 0
            if filt == 1:
                pr = a
            elif filt == 2:
                pr = b
            elif filt == 3:
                pr = (a + b) >> 1
            elif filt == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            else:
                pr = 0
            out.append((line[i] - pr) & 255)
        rows.append(bytes((filt,)) + bytes(out))
        prev = line
    def chunk(k, d):
        return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def test_tga_and_png_agree_and_make_a_dds(tmp_path):
    t, p = tmp_path / "a.tga", tmp_path / "a.png"
    t.write_bytes(tga(8, 8))
    p.write_bytes(png(8, 8))
    assert imgconv.load_rgba(t) == imgconv.load_rgba(p)
    dds = imgconv.to_dds(t)
    assert dds[:4] == b"DDS " and len(dds) == 128 + 8 * 8 * 4
    w, h, rgba = imgconv.load_rgba(t)
    assert rgba[:4] == bytes((0, 0, 7, 255))  # r g b a of the first pixel


def test_png_filters_and_rle_tga_and_downscale(tmp_path):
    for f in (0, 1, 2, 3, 4):
        (tmp_path / f"f{f}.png").write_bytes(png(8, 8, filt=f))
        assert imgconv.load_rgba(tmp_path / f"f{f}.png") == imgconv.load_rgba(tmp_path / "f0.png")
    (tmp_path / "r.tga").write_bytes(tga(8, 8, rle=True))
    assert imgconv.load_rgba(tmp_path / "r.tga")[2] == imgconv.load_rgba(tmp_path / "f0.png")[2]
    (tmp_path / "big.tga").write_bytes(tga(512, 512))
    w, h, _ = imgconv.load_rgba(tmp_path / "big.tga", 128)
    assert (w, h) == (128, 128)
