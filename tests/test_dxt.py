import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "setup"))

from skylands_setup.skyrim import dxt  # noqa: E402


def gradient(w=16, h=16):
    return bytes(v for y in range(h) for x in range(w) for v in (x * 16, y * 16, 128))


def test_encode_then_decode_is_close():
    w, h, rgb = dxt.decode(dxt.encode(16, 16, gradient()))
    assert (w, h) == (16, 16)
    src = gradient()
    err = sum(abs(a - b) for a, b in zip(rgb, src)) / len(src)
    assert err < 12


def test_decode_can_skip_pixels():
    w, h, rgb = dxt.decode(dxt.encode(16, 16, gradient()), step=2)
    assert (w, h) == (8, 8) and len(rgb) == 8 * 8 * 3


def test_packed_texture_is_tinted_and_a_plain_one_kept():
    noisy = bytes(v for y in range(16) for x in range(16) for v in ((255, 0, 0), (0, 255, 0), (0, 0, 255))[(x + y) % 3])
    out, note = dxt.shade(dxt.prepare(dxt.encode(16, 16, noisy)), (200, 100, 50))
    assert "packed" in note
    _w, _h, rgb = dxt.decode(out)
    assert max(rgb[0::3]) > max(rgb[1::3]) > max(rgb[2::3])  # red-dominant like the tint, not rainbow
    grey = bytes([120, 120, 120] * 256)
    _out, note2 = dxt.shade(dxt.prepare(dxt.encode(16, 16, grey)), (200, 100, 50))
    assert "kept" in note2
