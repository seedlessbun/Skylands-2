"""Read files out of Skyrim BSA archives (v104 Oldrim/zlib, v105 Special Edition/LZ4)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from .lz4 import decompress_frame

ARCHIVE_DIR_NAMES = 0x1
ARCHIVE_FILE_NAMES = 0x2
ARCHIVE_COMPRESSED = 0x4
ARCHIVE_EMBED_NAMES = 0x100
SIZE_TOGGLE_COMPRESSED = 0x40000000


class BSAError(ValueError):
    pass


class BSA:
    """Index of one archive. Paths are lower-case with backslashes, e.g. 'strings\\skyrim_english.strings'."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.entries: dict[str, tuple[int, int]] = {}  # path -> (offset, raw size field)
        with open(self.path, "rb") as f:
            header = f.read(36)
            if len(header) < 36 or header[:4] != b"BSA\0":
                raise BSAError(f"{self.path.name}: not a BSA")
            (version, _off, self.flags, folders, files, _dlen, _flen, _fflags) = struct.unpack_from(
                "<IIIIIIIH", header, 4
            )
            if version not in (104, 105):
                raise BSAError(f"{self.path.name}: unsupported BSA version {version}")
            self.version = version
            if not (self.flags & ARCHIVE_DIR_NAMES and self.flags & ARCHIVE_FILE_NAMES):
                raise BSAError(f"{self.path.name}: archive has no names")
            rec = 24 if version == 105 else 16
            counts = [struct.unpack_from("<I", f.read(rec), 8)[0] for _ in range(folders)]
            dirs: list[tuple[str, list[tuple[int, int]]]] = []
            for count in counts:
                (nlen,) = f.read(1)
                name = f.read(nlen)[:-1].decode("cp1252").lower()
                recs = []
                for _ in range(count):
                    _h, size, offset = struct.unpack("<QII", f.read(16))
                    recs.append((offset, size))
                dirs.append((name, recs))
            names = f.read(_flen).split(b"\0")
            k = 0
            for dname, recs in dirs:
                for offset, size in recs:
                    fname = names[k].decode("cp1252").lower()
                    k += 1
                    self.entries[f"{dname}\\{fname}" if dname else fname] = (offset, size)

    def read(self, inner_path: str) -> bytes:
        key = inner_path.replace("/", "\\").lower()
        if key not in self.entries:
            raise KeyError(inner_path)
        offset, size = self.entries[key]
        compressed = bool(self.flags & ARCHIVE_COMPRESSED) != bool(size & SIZE_TOGGLE_COMPRESSED)
        size &= ~SIZE_TOGGLE_COMPRESSED & 0xFFFFFFFF
        with open(self.path, "rb") as f:
            f.seek(offset)
            data = f.read(size)
        if self.flags & ARCHIVE_EMBED_NAMES:
            skip = 1 + data[0]
            data = data[skip:]
        if not compressed:
            return data
        (original,) = struct.unpack_from("<I", data, 0)
        payload = data[4:]
        out = decompress_frame(payload) if self.version == 105 else zlib.decompress(payload)
        if len(out) != original:
            raise BSAError(f"{inner_path}: size {len(out)} != {original}")
        return out
