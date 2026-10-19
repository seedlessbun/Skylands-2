"""Read just enough of a Skyrim SE NIF (20.2.0.7, BS version 100) to measure its shapes.

Used to fit a new gun model to the vanilla crossbow it replaces: the extent and direction of the vanilla mesh tell the
fitting code which way the barrel points, how long the weapon is and where the grip is, without guessing.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


class NifError(ValueError):
    pass


@dataclass
class Shape:
    name_index: int
    translation: tuple[float, float, float]
    rotation: tuple[float, ...]
    scale: float
    positions: list[tuple[float, float, float]]


def _half(b: bytes) -> float:
    return struct.unpack("<e", b)[0]


def blocks(data: bytes) -> list[tuple[str, bytes]]:
    nl = data.find(b"\n")
    if nl < 0 or not data.startswith(b"Gamebryo File Format"):
        raise NifError("not a NIF")
    p = nl + 1
    version, endian, user, count = struct.unpack_from("<IBII", data, p)
    p += 13
    if version != 0x14020007 or endian != 1:
        raise NifError(f"unsupported NIF version {version:#x}")
    if user >= 3:
        (bsver,) = struct.unpack_from("<I", data, p)
        p += 4
        for _ in range(3):
            p += 1 + data[p]
        if bsver >= 103:
            p += 1 + data[p]
    (ntypes,) = struct.unpack_from("<H", data, p)
    p += 2
    types = []
    for _ in range(ntypes):
        (ln,) = struct.unpack_from("<I", data, p)
        p += 4
        types.append(data[p:p + ln].decode("ascii", "replace"))
        p += ln
    idx = struct.unpack_from(f"<{count}H", data, p)
    p += 2 * count
    sizes = struct.unpack_from(f"<{count}I", data, p)
    p += 4 * count
    nstr, _maxlen = struct.unpack_from("<II", data, p)
    p += 8
    for _ in range(nstr):
        (ln,) = struct.unpack_from("<I", data, p)
        p += 4 + ln
    (ngroups,) = struct.unpack_from("<I", data, p)
    p += 4 + 4 * ngroups
    out = []
    for i in range(count):
        out.append((types[idx[i]], data[p:p + sizes[i]]))
        p += sizes[i]
    return out


def read_shape(block: bytes) -> Shape:
    p = 0
    (name,) = struct.unpack_from("<i", block, p)
    p += 4
    (nextra,) = struct.unpack_from("<I", block, p)
    p += 4 + 4 * nextra + 4  # extra data refs, controller
    p += 4  # flags
    trans = struct.unpack_from("<3f", block, p)
    p += 12
    rot = struct.unpack_from("<9f", block, p)
    p += 36
    (scale,) = struct.unpack_from("<f", block, p)
    p += 4 + 4  # collision ref
    p += 16 + 4 + 4 + 4  # bounding sphere, skin, shader, alpha
    (desc,) = struct.unpack_from("<Q", block, p)
    p += 8
    ntris, nverts, size = struct.unpack_from("<HHI", block, p)
    p += 8
    unit = (desc & 0xF) * 4
    attrs = desc >> 44
    if not attrs & 0x1 or unit < 8:
        raise NifError("shape has no positions")
    full = True  # Skyrim SE always stores float positions (the flag only matters for Fallout 4)
    pos = []
    for i in range(nverts):
        o = p + i * unit
        if full:
            pos.append(struct.unpack_from("<3f", block, o))
        else:
            pos.append((_half(block[o:o + 2]), _half(block[o + 2:o + 4]), _half(block[o + 4:o + 6])))
    return Shape(name, trans, rot, scale, pos)


def extra_data(data: bytes) -> list[tuple[str, str, str, int]]:
    """The string extra data and behaviour-graph references of a NIF as (type, name, value, flag): the vanilla crossbow's
    'Prn' tells Skyrim where the sheathed weapon hangs and its behaviour graph drives the weapon's own animation."""
    out = []
    strings = _strings(data)
    for kind, blk in blocks(data):
        try:
            if kind == "NiStringExtraData":
                a, b = struct.unpack_from("<ii", blk, 0)
                out.append((kind, strings[a] if a >= 0 else "", strings[b] if b >= 0 else "", 0))
            elif kind == "BSBehaviorGraphExtraData":
                a, b = struct.unpack_from("<ii", blk, 0)
                out.append((kind, strings[a] if a >= 0 else "", strings[b] if b >= 0 else "", blk[8]))
        except (struct.error, IndexError):
            continue
    return out


def _strings(data: bytes) -> list[str]:
    nl = data.find(b"\n")
    p = nl + 1
    version, endian, user, count = struct.unpack_from("<IBII", data, p)
    p += 13
    if user >= 3:
        (bsver,) = struct.unpack_from("<I", data, p)
        p += 4
        for _ in range(3):
            p += 1 + data[p]
        if bsver >= 103:
            p += 1 + data[p]
    (ntypes,) = struct.unpack_from("<H", data, p)
    p += 2
    for _ in range(ntypes):
        (ln,) = struct.unpack_from("<I", data, p)
        p += 4 + ln
    p += 2 * count + 4 * count
    nstr, _maxlen = struct.unpack_from("<II", data, p)
    p += 8
    out = []
    for _ in range(nstr):
        (ln,) = struct.unpack_from("<I", data, p)
        out.append(data[p + 4:p + 4 + ln].decode("ascii", "replace"))
        p += 4 + ln
    return out


def read_partition(block: bytes) -> Shape:
    """The vertices a skinned shape keeps in its NiSkinPartition (Skyrim SE stores them there, not in the shape)."""
    nparts, dsize, vsize = struct.unpack_from("<III", block, 0)
    (desc,) = struct.unpack_from("<Q", block, 12)
    if vsize < 8 or not dsize:
        raise NifError("partition has no vertex data")
    attrs = desc >> 44
    if not attrs & 0x1:
        raise NifError("partition has no positions")
    full = True  # Skyrim SE always stores float positions
    off = (desc >> 4) & 0xF
    pos = []
    for i in range(dsize // vsize):
        o = 20 + i * vsize + off * 4
        if full:
            pos.append(struct.unpack_from("<3f", block, o))
        else:
            pos.append((_half(block[o:o + 2]), _half(block[o + 2:o + 4]), _half(block[o + 4:o + 6])))
    return Shape(-1, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0), 1.0, pos)


def shapes(data: bytes) -> list[Shape]:
    out = []
    for kind, blk in blocks(data):
        if kind == "NiSkinPartition":
            try:
                out.append(read_partition(blk))
            except (NifError, struct.error):
                pass
            continue
        if kind in ("BSTriShape", "BSSubIndexTriShape", "BSMeshLODTriShape", "BSDynamicTriShape"):
            try:
                out.append(read_shape(blk))
            except (NifError, struct.error):
                continue
    return out


def world_points(data: bytes) -> list[tuple[float, float, float]]:
    """Every vertex of every shape with the shape's own transform applied (parent nodes are not walked)."""
    pts: list[tuple[float, float, float]] = []
    for s in shapes(data):
        r = s.rotation
        for x, y, z in s.positions:
            pts.append((
                (r[0] * x + r[1] * y + r[2] * z) * s.scale + s.translation[0],
                (r[3] * x + r[4] * y + r[5] * z) * s.scale + s.translation[1],
                (r[6] * x + r[7] * y + r[8] * z) * s.scale + s.translation[2],
            ))
    return pts
