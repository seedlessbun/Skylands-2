"""LZO1X decompression for Borderlands 2 packages, through the bundled lzokay helper (MIT)."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

_BIN = Path(__file__).resolve().parent.parent / "bin"
_lib = None


class LZOError(ValueError):
    pass


def _load() -> ctypes.CDLL:
    global _lib
    if _lib is None:
        name = "skylands_lzo.dll" if sys.platform == "win32" else "skylands_lzo.so"
        lib = ctypes.CDLL(str(_BIN / name))
        fn = lib.skylands_lzo_decompress
        fn.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t]
        fn.restype = ctypes.c_longlong
        _lib = lib
    return _lib


def decompress(data: bytes, size: int) -> bytes:
    """Decompress one LZO1X block whose uncompressed size is known."""
    out = ctypes.create_string_buffer(size)
    n = _load().skylands_lzo_decompress(data, len(data), out, size)
    if n < 0:
        raise LZOError(f"LZO error {n}")
    if n != size:
        raise LZOError(f"LZO produced {n} bytes, expected {size}")
    return out.raw
