"""Skyrim localized string tables: .strings (zero-terminated) and .dlstrings/.ilstrings (length-prefixed)."""

from __future__ import annotations

import struct


def parse_table(data: bytes, length_prefixed: bool, encoding: str = "utf-8") -> dict[int, str]:
    count, _size = struct.unpack_from("<II", data, 0)
    base = 8 + count * 8
    table: dict[int, str] = {}
    for i in range(count):
        sid, off = struct.unpack_from("<II", data, 8 + i * 8)
        p = base + off
        if length_prefixed:
            (n,) = struct.unpack_from("<I", data, p)
            raw = data[p + 4 : p + 4 + n]
        else:
            raw = data[p : data.index(b"\0", p)]
        raw = raw.rstrip(b"\0")
        try:
            table[sid] = raw.decode(encoding)
        except UnicodeDecodeError:
            table[sid] = raw.decode("cp1252", errors="replace")
    return table
