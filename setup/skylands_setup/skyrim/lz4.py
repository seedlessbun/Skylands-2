"""LZ4 frame decoder (pure Python). Skyrim SE's v105 BSA archives compress files as LZ4 frames."""

from __future__ import annotations

import struct

FRAME_MAGIC = 0x184D2204


class LZ4Error(ValueError):
    pass


def _decode_block(src: memoryview, out: bytearray) -> None:
    """Decode one LZ4 block, appending to out (earlier output may be referenced by matches)."""
    i = 0
    n = len(src)
    while i < n:
        token = src[i]
        i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        if lit:
            out += src[i : i + lit]
            i += lit
        if i >= n:
            break  # last sequence has literals only
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        if offset == 0 or offset > len(out):
            raise LZ4Error("bad match offset")
        mlen = token & 15
        if mlen == 15:
            while True:
                b = src[i]
                i += 1
                mlen += b
                if b != 255:
                    break
        mlen += 4
        start = len(out) - offset
        if mlen <= offset:
            out += out[start : start + mlen]
        else:  # overlapping copy repeats the last `offset` bytes
            chunk = bytes(out[start:])
            reps, rest = divmod(mlen, offset)
            out += chunk * reps + chunk[:rest]


def decompress_frame(data: bytes) -> bytes:
    view = memoryview(data)
    if len(view) < 7 or struct.unpack_from("<I", view, 0)[0] != FRAME_MAGIC:
        raise LZ4Error("not an LZ4 frame")
    flg = view[4]
    if (flg >> 6) != 1:
        raise LZ4Error("unsupported LZ4 frame version")
    pos = 6  # magic(4) + FLG + BD
    if flg & 0x08:
        pos += 8  # content size
    if flg & 0x01:
        pos += 4  # dictionary id
    pos += 1  # header checksum
    block_checksum = bool(flg & 0x10)
    out = bytearray()
    while True:
        (size,) = struct.unpack_from("<I", view, pos)
        pos += 4
        if size == 0:
            break
        raw = size & 0x80000000
        size &= 0x7FFFFFFF
        block = view[pos : pos + size]
        pos += size
        if raw:
            out += block
        else:
            _decode_block(block, out)
        if block_checksum:
            pos += 4
    return bytes(out)
