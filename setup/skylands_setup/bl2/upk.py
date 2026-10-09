"""Read Borderlands 2's cooked Unreal Engine 3 packages (.upk).

Layout follows the universal-modder technique note "Reading UE3 Gearbox games offline":
LZO-compressed chunks, a name table of FString + 64-bit flags, 28-byte imports, and BL2's
export entries (class, super, outer, name, archetype, 64-bit flags, serial size/offset,
export flags, net objects, GUID, package flags). Property parsing is best-effort; the survey
tool reports anything it cannot decode so the real files can confirm each rule.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from . import lzo

TAG = 0x9E2A83C1


class UPKError(ValueError):
    pass


class Reader:
    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.d = data
        self.p = pos

    def u8(self) -> int:
        v = self.d[self.p]
        self.p += 1
        return v

    def u16(self) -> int:
        v = struct.unpack_from("<H", self.d, self.p)[0]
        self.p += 2
        return v

    def i32(self) -> int:
        v = struct.unpack_from("<i", self.d, self.p)[0]
        self.p += 4
        return v

    def u32(self) -> int:
        v = struct.unpack_from("<I", self.d, self.p)[0]
        self.p += 4
        return v

    def u64(self) -> int:
        v = struct.unpack_from("<Q", self.d, self.p)[0]
        self.p += 8
        return v

    def f32(self) -> float:
        v = struct.unpack_from("<f", self.d, self.p)[0]
        self.p += 4
        return v

    def raw(self, n: int) -> bytes:
        if n < 0 or self.p + n > len(self.d):
            raise UPKError("read past end")
        v = self.d[self.p : self.p + n]
        self.p += n
        return v

    def fstring(self) -> str:
        n = self.i32()
        if n == 0:
            return ""
        if n > 0:
            if n > 1 << 20:
                raise UPKError("string too long")
            return self.raw(n)[:-1].decode("cp1252", errors="replace")
        n = -n
        if n > 1 << 20:
            raise UPKError("string too long")
        return self.raw(n * 2)[:-2].decode("utf-16-le", errors="replace")


def _decompress_chunk(data: bytes, pos: int) -> bytes:
    """One compressed chunk: tag, block size, totals, block size table, LZO blocks."""
    r = Reader(data, pos)
    if r.u32() != TAG:
        raise UPKError("bad chunk tag")
    block = r.u32()
    r.u32()  # total compressed
    total_u = r.u32()
    sizes = []
    left = total_u
    while left > 0:
        c, u = r.u32(), r.u32()
        sizes.append((c, u))
        left -= u
        if len(sizes) > 1 + total_u // max(block, 1) + 1:
            raise UPKError("bad block table")
    out = bytearray()
    for c, u in sizes:
        out += lzo.decompress(r.raw(c), u)
    if len(out) != total_u:
        raise UPKError("chunk size mismatch")
    return bytes(out)


def decompressed_image(raw: bytes) -> bytes:
    """Return the package as it is laid out uncompressed."""
    if len(raw) < 16 or struct.unpack_from("<I", raw, 0)[0] != TAG:
        raise UPKError("not an Unreal package")
    # Fully compressed files start with a chunk header (block size where the version would be).
    if struct.unpack_from("<I", raw, 4)[0] == 0x20000:
        out = bytearray()
        pos = 0
        while pos + 16 <= len(raw):
            total_c = struct.unpack_from("<I", raw, pos + 8)[0]
            out += _decompress_chunk(raw, pos)
            pos += 16 + _table_len(raw, pos) + total_c
        return bytes(out)
    h = _header(raw)
    if not h["chunks"]:
        return raw
    first = min(c[2] for c in h["chunks"])
    image = bytearray(raw[:first])
    for u_off, u_size, c_off, _c_size in sorted(h["chunks"]):
        data = _decompress_chunk(raw, c_off)
        if len(image) < u_off:
            image += b"\0" * (u_off - len(image))
        image[u_off : u_off + u_size] = data
    return bytes(image)


def _table_len(raw: bytes, pos: int) -> int:
    r = Reader(raw, pos)
    r.u32()
    r.u32()
    r.u32()
    total_u = r.u32()
    n = 0
    left = total_u
    while left > 0:
        r.u32()
        left -= r.u32()
        n += 8
    return n


def _header(data: bytes) -> dict:
    r = Reader(data)
    if r.u32() != TAG:
        raise UPKError("not an Unreal package")
    h = {"version": r.u16(), "licensee": r.u16()}
    h["header_size"] = r.i32()
    h["folder"] = r.fstring()
    h["flags"] = r.u32()
    h["name_count"], h["name_offset"] = r.i32(), r.i32()
    h["export_count"], h["export_offset"] = r.i32(), r.i32()
    h["import_count"], h["import_offset"] = r.i32(), r.i32()
    h["depends_offset"] = r.i32()
    if h["version"] >= 623:
        r.i32()
        r.i32()
        r.i32()
    if h["version"] >= 584:
        r.i32()
    r.raw(16)  # guid
    gens = r.i32()
    if gens < 0 or gens > 1000:
        raise UPKError("bad generation count")
    r.raw(gens * 12)
    h["engine"], h["cooker"] = r.u32(), r.u32()
    h["compression"] = r.u32()
    n = r.i32()
    if n < 0 or n > 100000:
        raise UPKError("bad chunk count")
    h["chunks"] = [tuple(r.i32() for _ in range(4)) for _ in range(n)]
    return h


@dataclass
class Export:
    index: int
    class_index: int
    super_index: int
    outer_index: int
    name: str
    archetype: int
    flags: int
    serial_size: int
    serial_offset: int


@dataclass
class Import:
    class_package: str
    class_name: str
    outer_index: int
    name: str


@dataclass
class Package:
    path: Path
    header: dict
    data: bytes
    names: list[str] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)
    exports: list[Export] = field(default_factory=list)

    # ---- names and paths -----------------------------------------------------------------
    def fname(self, r: Reader) -> str:
        idx, num = r.i32(), r.i32()
        if not 0 <= idx < len(self.names):
            raise UPKError(f"bad name index {idx}")
        base = self.names[idx]
        return base if num == 0 else f"{base}_{num - 1}"

    def obj_name(self, index: int) -> str:
        if index > 0:
            return self.exports[index - 1].name
        if index < 0:
            return self.imports[-index - 1].name
        return "None"

    def obj_class(self, index: int) -> str:
        if index > 0:
            c = self.exports[index - 1].class_index
            return self.obj_name(c) if c else "Class"
        if index < 0:
            return self.imports[-index - 1].class_name
        return "None"

    def outer(self, index: int) -> int:
        if index > 0:
            return self.exports[index - 1].outer_index
        if index < 0:
            return self.imports[-index - 1].outer_index
        return 0

    def path_of(self, index: int) -> str:
        """Full object path as the SDK and OpenBLCMM write it: Pkg.Group.Name, ':' under objects."""
        parts: list[tuple[str, str]] = []
        i = index
        guard = 0
        while i != 0 and guard < 64:
            parts.append((self.obj_name(i), self.obj_class(i)))
            i = self.outer(i)
            guard += 1
        parts.reverse()
        out = parts[0][0] if parts else "None"
        for k in range(1, len(parts)):
            parent_class = parts[k - 1][1]
            sep = "." if parent_class == "Package" else ":"
            out += sep + parts[k][0]
        return out

    def _indexes(self) -> None:
        if getattr(self, "_by_name", None) is None:
            by_name: dict[str, list[int]] = {}
            by_outer: dict[int, list[int]] = {}
            for e in self.exports:
                by_name.setdefault(e.name.lower(), []).append(e.index)
                by_outer.setdefault(e.outer_index, []).append(e.index)
            self._by_name, self._by_outer = by_name, by_outer

    def find(self, path: str) -> int:
        self._indexes()
        leaf = re.split(r"[.:]", path)[-1].lower()
        want = path.lower()
        for i in self._by_name.get(leaf, ()):
            if self.path_of(i).lower() == want:
                return i
        return 0

    def children_of(self, path: str) -> list[int]:
        """Exports directly inside the object or package group at path."""
        idx = self.find(path)
        if not idx:
            return []
        self._indexes()
        return list(self._by_outer.get(idx, ()))

    def export_data(self, index: int) -> bytes:
        e = self.exports[index - 1]
        return self.data[e.serial_offset : e.serial_offset + e.serial_size]


def open_package(path: Path) -> Package:
    raw = Path(path).read_bytes()
    data = decompressed_image(raw)
    h = _header(data)
    pkg = Package(Path(path), h, data)
    r = Reader(data, h["name_offset"])
    for _ in range(h["name_count"]):
        pkg.names.append(r.fstring())
        r.u64()
    r.p = h["import_offset"]
    for _ in range(h["import_count"]):
        cp, cn = pkg.fname(r), pkg.fname(r)
        outer = r.i32()
        pkg.imports.append(Import(cp, cn, outer, pkg.fname(r)))
    r.p = h["export_offset"]
    for i in range(h["export_count"]):
        cls, sup, outer = r.i32(), r.i32(), r.i32()
        name = pkg.fname(r)
        arch = r.i32()
        flags = r.u64()
        size, off = r.i32(), r.i32()
        r.u32()  # export flags
        nets = r.i32()
        if nets < 0 or nets > 100000:
            raise UPKError("bad export table")
        r.raw(nets * 4)
        r.raw(16)  # guid
        r.u32()  # package flags
        pkg.exports.append(Export(i + 1, cls, sup, outer, name, arch, flags, size, off))
    return pkg


def _name_table(data: bytes, offset: int, count: int) -> list[bytes]:
    """Names as raw bytes (FString + 8 bytes of flags each). A tight loop: this runs for every package."""
    unpack = struct.Struct("<i").unpack_from
    names: list[bytes] = []
    append = names.append
    pos = offset
    for _ in range(count):
        n = unpack(data, pos)[0]
        pos += 4
        if n > 0:
            append(data[pos : pos + n - 1])
            pos += n
        elif n < 0:
            append(data[pos : pos - n * 2 - 2].decode("utf-16-le", errors="replace").encode("cp1252", errors="replace"))
            pos += -n * 2
        else:
            append(b"")
        pos += 8
    return names


def _names_image(raw: bytes) -> tuple[bytes, dict]:
    """Decompress just enough of a package to read its name table."""
    if len(raw) < 16 or struct.unpack_from("<I", raw, 0)[0] != TAG:
        raise UPKError("not an Unreal package")
    if struct.unpack_from("<I", raw, 4)[0] == 0x20000:
        data = decompressed_image(raw)
    else:
        h = _header(raw)
        if not h["chunks"]:
            data = raw
        else:
            lo, hi = h["name_offset"], max(h["import_offset"], h["name_offset"] + 1)
            first = min(c[2] for c in h["chunks"])
            image = bytearray(raw[:first])
            for u_off, u_size, c_off, _c in sorted(h["chunks"]):
                if u_off < hi and u_off + u_size > lo:
                    chunk = _decompress_chunk(raw, c_off)
                    if len(image) < u_off:
                        image += b"\0" * (u_off - len(image))
                    image[u_off : u_off + u_size] = chunk
            data = bytes(image)
    return data, _header(data)


def read_names_only(path: Path) -> list[str]:
    """Name table only, decompressing just the chunks that hold it."""
    data, h = _names_image(Path(path).read_bytes())
    return [n.decode("cp1252", errors="replace") for n in _name_table(data, h["name_offset"], h["name_count"])]


def index_info(path: Path) -> tuple[set[str], set[str]]:
    """(lower-cased names, lower-cased names of the package's top-level exports).

    Name tables also hold the names of everything a package merely imports, so only the top-level
    exports say which file actually defines an object.
    """
    data, h = _names_image(Path(path).read_bytes())
    names = _name_table(data, h["name_offset"], h["name_count"])
    top: set[str] = set()
    pos = h["export_offset"]
    head = struct.Struct("<iii")
    nm = struct.Struct("<ii")
    for _ in range(h["export_count"]):
        _cls, _sup, outer = head.unpack_from(data, pos)
        if outer == 0:
            idx, num = nm.unpack_from(data, pos + 12)
            base = names[idx].decode("cp1252", errors="replace")
            top.add((base if num == 0 else f"{base}_{num - 1}").lower())
        nets = struct.unpack_from("<i", data, pos + 44)[0]
        pos += 48 + nets * 4 + 20
    return {n.lower().decode("cp1252", errors="replace") for n in names}, top


def read_name_set(path: Path) -> set[str]:
    """Lower-cased names of a package, for the object index."""
    data, h = _names_image(Path(path).read_bytes())
    return {n.lower().decode("cp1252", errors="replace") for n in _name_table(data, h["name_offset"], h["name_count"])}


# ---- tagged properties ------------------------------------------------------------------------
BINARY_STRUCTS = {
    "Vector": "<3f", "Rotator": "<3i", "Color": "<4B", "LinearColor": "<4f", "Vector2D": "<2f",
    "Guid": "<4I", "IntPoint": "<2i", "Plane": "<4f", "Quat": "<4f",
}


def read_properties(pkg: Package, data: bytes, pos: int, depth: int = 0) -> tuple[dict, int]:
    """Parse UE3 tagged properties until 'None'. Values are python data; undecoded ones keep hex."""
    r = Reader(data, pos)
    out: dict = {}
    for _ in range(4096):
        name = pkg.fname(r)
        if name == "None":
            return out, r.p
        ptype = pkg.fname(r)
        size = r.i32()
        array_index = r.i32()
        key = name if array_index == 0 else f"{name}({array_index})"
        if ptype == "BoolProperty":
            out[key] = bool(r.u8())
            continue
        struct_name = pkg.fname(r) if ptype == "StructProperty" else None
        enum_name = pkg.fname(r) if ptype == "ByteProperty" else None
        start = r.p
        body = data[start : start + size]
        r.p = start + size
        try:
            out[key] = _value(pkg, ptype, body, struct_name, enum_name, depth)
        except (UPKError, struct.error, IndexError):
            out[key] = {"type": ptype, "struct": struct_name, "hex": body[:64].hex()}
    raise UPKError("property list did not end")


def _value(pkg: Package, ptype: str, body: bytes, struct_name: str | None, enum_name: str | None, depth: int):
    r = Reader(body)
    if ptype == "IntProperty":
        return r.i32()
    if ptype == "FloatProperty":
        return r.f32()
    if ptype in ("ObjectProperty", "ClassProperty", "ComponentProperty", "InterfaceProperty"):
        idx = r.i32()
        return pkg.path_of(idx) if idx else None
    if ptype == "NameProperty":
        return pkg.fname(r)
    if ptype == "StrProperty":
        return r.fstring()
    if ptype == "ByteProperty":
        return r.u8() if len(body) == 1 else pkg.fname(r)
    if ptype == "StructProperty":
        if struct_name in BINARY_STRUCTS:
            return list(struct.unpack_from(BINARY_STRUCTS[struct_name], body))
        if depth < 6:
            props, end = read_properties(pkg, body, 0, depth + 1)
            if end == len(body):
                return props
        raise UPKError("struct not tagged")
    if ptype == "ArrayProperty":
        count = r.i32()
        rest = body[4:]
        return {"type": "Array", "count": count, "items": _array_items(pkg, rest, count, depth)}
    raise UPKError(f"unknown type {ptype}")


def _array_items(pkg: Package, body: bytes, count: int, depth: int):
    """Arrays carry no element type: try structs (tagged), then object refs, floats, ints."""
    if count == 0:
        return []
    if depth < 6:
        try:
            items, pos = [], 0
            for _ in range(count):
                props, pos = read_properties(pkg, body, pos, depth + 1)
                items.append(props)
            if pos == len(body):
                return items
        except (UPKError, struct.error, IndexError):
            pass
    if len(body) == 4 * count:
        ints = list(struct.unpack_from(f"<{count}i", body))
        if all(-len(pkg.imports) <= i <= len(pkg.exports) for i in ints):
            return [pkg.path_of(i) if i else None for i in ints]
        return ints
    return {"hex": body[:128].hex(), "size": len(body)}


def object_properties(pkg: Package, index: int) -> dict:
    """Properties of an export (skipping the leading net index)."""
    data = pkg.export_data(index)
    for start in (4, 0, 8):
        try:
            props, _ = read_properties(pkg, data, start)
            return props
        except (UPKError, struct.error, IndexError):
            continue
    raise UPKError("could not parse properties")
