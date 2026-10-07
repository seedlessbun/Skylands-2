"""Read the records Skylands needs from a Skyrim SE plugin (Skyrim.esm).

Only the top-level groups asked for are read; everything else is skipped by seeking,
so a 250 MB master is scanned in well under a second of I/O.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

FLAG_LOCALIZED = 0x80  # TES4 header flag
FLAG_COMPRESSED = 0x00040000  # record flag


class ESMError(ValueError):
    pass


@dataclass
class Record:
    type: str
    form_id: int
    flags: int
    subrecords: list[tuple[str, bytes]] = field(default_factory=list)

    def first(self, sig: str) -> bytes | None:
        for s, d in self.subrecords:
            if s == sig:
                return d
        return None

    def all(self, sig: str) -> list[bytes]:
        return [d for s, d in self.subrecords if s == sig]

    @property
    def edid(self) -> str:
        d = self.first("EDID")
        return d.rstrip(b"\0").decode("cp1252") if d else ""


def parse_subrecords(data: bytes) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    pos = 0
    big = None
    while pos + 6 <= len(data):
        sig = data[pos : pos + 4].decode("ascii", errors="replace")
        (size,) = struct.unpack_from("<H", data, pos + 4)
        pos += 6
        if sig == "XXXX":
            (big,) = struct.unpack_from("<I", data, pos)
            pos += size
            continue
        if big is not None:
            size, big = big, None
        out.append((sig, data[pos : pos + size]))
        pos += size
    return out


def _parse_record(header: bytes, body: bytes) -> Record:
    rtype = header[:4].decode("ascii")
    _size, flags, form_id = struct.unpack_from("<III", header, 4)
    if flags & FLAG_COMPRESSED:
        (_orig,) = struct.unpack_from("<I", body, 0)
        body = zlib.decompress(body[4:])
    return Record(rtype, form_id, flags, parse_subrecords(body))


def _walk_group(data: bytes, wanted: set[str], out: dict[str, list[Record]]) -> None:
    pos = 0
    while pos + 24 <= len(data):
        head = data[pos : pos + 24]
        if head[:4] == b"GRUP":
            (gsize,) = struct.unpack_from("<I", head, 4)
            _walk_group(data[pos + 24 : pos + gsize], wanted, out)
            pos += gsize
            continue
        (size,) = struct.unpack_from("<I", head, 4)
        rtype = head[:4].decode("ascii", errors="replace")
        if rtype in wanted:
            out[rtype].append(_parse_record(head, data[pos + 24 : pos + 24 + size]))
        pos += 24 + size


def read_plugin(path: Path, wanted: set[str]) -> tuple[Record, dict[str, list[Record]]]:
    """Return the TES4 header and every record of the wanted types."""
    out: dict[str, list[Record]] = {t: [] for t in wanted}
    with open(path, "rb") as f:
        head = f.read(24)
        if head[:4] != b"TES4":
            raise ESMError(f"{Path(path).name}: not a Skyrim plugin")
        (size,) = struct.unpack_from("<I", head, 4)
        tes4 = _parse_record(head, f.read(size))
        while True:
            ghead = f.read(24)
            if len(ghead) < 24:
                break
            if ghead[:4] != b"GRUP":
                raise ESMError("expected a top-level group")
            (gsize,) = struct.unpack_from("<I", ghead, 4)
            label = ghead[8:12].decode("ascii", errors="replace")
            if label in wanted:
                _walk_group(f.read(gsize - 24), wanted, out)
            else:
                f.seek(gsize - 24, 1)
    return tes4, out


def is_localized(tes4: Record) -> bool:
    return bool(tes4.flags & FLAG_LOCALIZED)
