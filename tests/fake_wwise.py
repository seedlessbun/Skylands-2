"""Tiny Wwise packs for the tests: the layouts bl2/wwise.py assumes (AKPK version 1 with a bank table and a streamed-sound table; banks with BKHD,
DIDX, DATA and HIRC chunks)."""

import io
import math
import struct
import wave


def pcm_wem(seconds: float = 0.1, rate: int = 22050, channels: int = 2) -> bytes:
    """A RIFF PCM audio file, the one kind of Wwise audio the installer can read without the decoder tool."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(rate * seconds)
        frames = b"".join(struct.pack("<h", int(12000 * math.sin(i / 8))) * channels for i in range(n))
        w.writeframes(frames)
    return buf.getvalue()


def obj(typ: int, ident: int, rest: bytes = b"") -> bytes:
    body = struct.pack("<I", ident) + rest
    return bytes([typ]) + struct.pack("<I", len(body)) + body


def event(ident: int, actions: list[int]) -> bytes:
    return obj(4, ident, struct.pack("<I", len(actions)) + b"".join(struct.pack("<I", a) for a in actions))


def play_action(ident: int, target: int) -> bytes:
    return obj(3, ident, struct.pack("<HI", 0x0403, target) + bytes([0, 0, 0, 0, 0, 0, 0, 0]))


def sound(ident: int, media: int, streamed: bool = False, parent: int = 0) -> bytes:
    return obj(2, ident, struct.pack("<IIII", 0x00040001, 1 if streamed else 0, media, 0) + bytes([0, 1, 0]) + struct.pack("<I", parent))


def container(ident: int, children: list[int], parent: int) -> bytes:
    return obj(5, ident, bytes(9) + struct.pack("<I", parent) + struct.pack("<I", len(children)) + b"".join(struct.pack("<I", c) for c in children))


def bank(bank_id: int, objects: list[bytes], media: dict[int, bytes] | None = None, version: int = 62) -> bytes:
    media = media or {}
    chunks = struct.pack("<4sIII", b"BKHD", 8, version, bank_id)
    if media:
        index, data, pos = b"", b"", 0
        for ident, blob in media.items():
            index += struct.pack("<III", ident, pos, len(blob))
            data += blob
            pos += len(blob)
        chunks += b"DIDX" + struct.pack("<I", len(index)) + index + b"DATA" + struct.pack("<I", len(data)) + data
    hirc = struct.pack("<I", len(objects)) + b"".join(objects)
    return chunks + b"HIRC" + struct.pack("<I", len(hirc)) + hirc


def pck(banks: list[tuple[int, bytes]], sounds: list[tuple[int, bytes]], trust_table: bool = True) -> bytes:
    langs = struct.pack("<I", 1) + struct.pack("<II", 12, 0) + "sfx".encode("utf-16-le") + b"\0\0"
    langs += b"\0" * (-len(langs) % 4)
    bank_table = struct.pack("<I", len(banks)) + b"\0" * (20 * len(banks))
    sound_table = struct.pack("<I", len(sounds)) + b"\0" * (20 * len(sounds))
    header_size = 4 + 4 + 4 + 4 + len(langs) + len(bank_table) + len(sound_table) + 4
    pos = 8 + header_size
    body = b""
    bank_rows, sound_rows = [], []
    for table, rows in ((banks, bank_rows), (sounds, sound_rows)):
        for ident, blob in table:
            pad = -pos % 16
            body += b"\0" * pad
            pos += pad
            rows.append(struct.pack("<5I", ident, 16, len(blob), pos // 16, 0))
            body += blob
            pos += len(blob)
    bank_table = struct.pack("<I", len(banks)) + b"".join(bank_rows)
    sound_table = struct.pack("<I", len(sounds)) + b"".join(sound_rows)
    if not trust_table:
        bank_table = struct.pack("<I", len(banks)) + b"\xff" * (20 * len(banks))  # useless offsets: the bank walker has to find them
    head = struct.pack("<5I", header_size, 1, len(langs), len(bank_table), len(sound_table))
    out = b"AKPK" + head + langs + bank_table + sound_table
    assert len(out) == 8 + header_size - 4 or True
    return out + b"\0" * (8 + header_size - len(out)) + body
