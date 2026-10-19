"""Read Borderlands 2 gun part meshes and their textures straight out of the cooked packages ("native" method).

The exact byte layout of UE3 meshes differs between games and engine builds, and this code has to work on files nobody
can look at from here. So it does not walk the mesh structure; it finds the data by what it must look like:

* vertex buffers are bulk arrays: [int32 element size][int32 count][count * size bytes]. A buffer whose elements hold
  a float triple inside the mesh's own bounding box (the FBoxSphereBounds that follows a mesh's properties) is a
  position buffer, wherever the triple sits inside the element;
* index buffers are bulk arrays of 2 or 4 byte values, a multiple of three long, every index below the vertex count;
* UVs are the half or float pairs, in a buffer with the same vertex count, that stay within a few texture repeats;
* materials are object references in the mesh data whose class is a material; their texture parameters name the
  diffuse and normal textures; textures are DXT1/DXT5 mips, inline or in a texture file cache.

Everything returns None (and a reason through `say`) rather than raising, so one odd part never stops a build.
"""

from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass

from .. import meshes as M
from . import upk

MESH_CLASSES = ("StaticMesh", "SkeletalMesh")
MATERIAL_CLASSES = ("MaterialInstanceConstant", "Material", "MaterialInstanceTimeVarying")
# the usual vertex element sizes first (a wrong, smaller size can pass the bounds test on padded data), odd sizes last
PLAIN_SIZES = (40, 32, 36, 44, 48, 33, 37, 52, 56, 60, 64, 28, 24, 41, 45, 49, 68, 72, 76, 80, 84, 88, 92, 96, 20, 16, 12,
               *[s for s in range(13, 97) if s % 4])
ELEMENT_SIZES = tuple(range(12, 97))  # vertex element sizes (a rigid vertex is not always a multiple of 4)
MAX_VERTS = 65535


@dataclass
class RawMesh:
    mesh: M.Mesh
    note: str
    materials: list[str]


def _finite(v: float) -> bool:
    return v == v and abs(v) < 1e7


def read_bounds(data: bytes, pos: int) -> tuple[M.Vec, M.Vec] | None:
    """The FBoxSphereBounds after a mesh's properties: origin, box extent, radius. Returns (min, max) or None."""
    try:
        ox, oy, oz, ex, ey, ez, radius = struct.unpack_from("<7f", data, pos)
    except struct.error:
        return None
    if not all(_finite(v) for v in (ox, oy, oz, ex, ey, ez, radius)):
        return None
    if min(ex, ey, ez) < 0 or max(ex, ey, ez) > 20000 or max(ex, ey, ez) <= 0:
        return None
    return (ox - ex, oy - ey, oz - ez), (ox + ex, oy + ey, oz + ez)


def _bulk_arrays(data: bytes, start: int, sizes: tuple[int, ...] | None, min_count: int = 3):
    """Every [elemSize][count] header at a 4-byte boundary whose payload fits in the data."""
    n = len(data)
    # every byte offset: the headers of the real files are not 4-byte aligned (a 2-byte property earlier shifts them)
    for p in range(start, n - 8):
        size, count = struct.unpack_from("<ii", data, p)
        if count < min_count or count > 400000 or size <= 0 or size > 128:
            continue
        if sizes is not None and size not in sizes:
            continue
        if p + 8 + size * count > n:
            continue
        yield p + 8, size, count


def find_positions(data: bytes, start: int, bounds: tuple[M.Vec, M.Vec] | None) -> tuple[list[M.Vec], int, int] | None:
    """The biggest buffer with a float triple that stays inside the bounds. Returns (positions, data offset, count)."""
    best = None
    for off, size, count in _bulk_arrays(data, start, ELEMENT_SIZES):
        if count > MAX_VERTS or count < 4:
            continue
        sample = range(0, count, max(1, count // 64))
        for o in range(0, size - 11, 4):
            if _positions_ok(data, off, size, count, o, bounds, sample):
                pts = [struct.unpack_from("<3f", data, off + i * size + o) for i in range(count)]
                if _spread_ok(pts, bounds):
                    if best is None or count > best[2]:
                        best = (pts, off, count, size, o)
                    break
    if best is None:
        return None
    return best[0], best[1], best[2]


def _positions_ok(data, off, size, count, o, bounds, sample) -> bool:
    if bounds is None:
        lo = (-3000.0,) * 3
        hi = (3000.0,) * 3
        pad = 0.0
    else:
        lo, hi = bounds
        pad = 0.05 * max(hi[i] - lo[i] for i in range(3)) + 0.5
    for i in sample:
        x, y, z = struct.unpack_from("<3f", data, off + i * size + o)
        if not (_finite(x) and _finite(y) and _finite(z)):
            return False
        if any(0 < abs(v) < 1e-20 for v in (x, y, z)):
            return False  # packed bytes read as floats come out as tiny denormals: this is not a position
        if not (lo[0] - pad <= x <= hi[0] + pad and lo[1] - pad <= y <= hi[1] + pad and lo[2] - pad <= z <= hi[2] + pad):
            return False
    return True


def _spread_ok(pts, bounds) -> bool:
    """Reject buffers that are mostly zeros (a padding field that happens to sit inside the bounds)."""
    if len({p for p in pts[:256]}) < min(8, len(pts)):
        return False
    xs, ys, zs = zip(*pts)
    ext = [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]
    if bounds is None:
        return max(ext) > 1e-3
    want = [bounds[1][i] - bounds[0][i] for i in range(3)]
    return max(ext) >= 0.04 * max(want) and len(set(pts)) >= 0.2 * len(pts)  # a chunk may cover only part of the mesh


def find_indices(data: bytes, start: int, vertex_count: int) -> list[tuple[int, int, int]] | None:
    """The index buffer: a bulk array of 2 or 4 byte values, a multiple of 3 long, all below the vertex count."""
    best = None
    for off, size, count in _bulk_arrays(data, start, (2, 4), min_count=3):
        if count % 3 or count > 3 * 400000:
            continue
        fmt = "<%dH" if size == 2 else "<%dI"
        step = max(1, count // 4096)
        vals = struct.unpack_from(fmt % count, data, off)
        if max(vals) >= vertex_count:
            continue
        if max(vals) < 0.9 * (vertex_count - 1):
            continue  # an index buffer uses (nearly) all the vertices
        tris = [(vals[i], vals[i + 1], vals[i + 2]) for i in range(0, count, 3)]
        degenerate = sum(1 for a, b, c in tris[::step] if a == b or b == c or a == c)
        if degenerate > 0.2 * len(tris[::step]):
            continue
        if best is None or count > best[0]:
            best = (count, tris)
    return best[1] if best else None


def find_uvs(data: bytes, start: int, vertex_count: int, skip_off: int) -> list[tuple[float, float]] | None:
    """UV pairs in a buffer with one element per vertex (float or half), values within a few texture repeats."""
    for off, size, count in _bulk_arrays(data, start, None):
        if count != vertex_count or off == skip_off:
            continue
        if size < 4:
            continue
        for o in range(0, size - 3, 2):
            for fmt, width in (("<2f", 8), ("<2e", 4)):
                if o + width > size or (width == 8 and o % 4):
                    continue
                uv = _uv_try(data, off, size, count, o, fmt)
                if uv:
                    return uv
    return None


def _uv_try(data, off, size, count, o, fmt):
    out = []
    spread_u = set()
    for i in range(count):
        u, v = struct.unpack_from(fmt, data, off + i * size + o)
        if not (_finite(u) and _finite(v)) or not (-4 <= u <= 8 and -8 <= v <= 8):
            return None
        out.append((u, v))
        if i < 64:
            spread_u.add(round(u, 3))
    if len(spread_u) < max(2, min(count, 64) // 16):
        return None
    return out


def index_candidates(data: bytes, start: int) -> list[tuple[int, int, list[tuple[int, int, int]]]]:
    """Every plausible index buffer: (offset, element size, triangles). A bulk array of 2 or 4 byte values, a multiple of 3 long."""
    out = []
    for off, size, count in _bulk_arrays(data, start, (2, 4), min_count=3):
        if count % 3 or count > 3 * 400000:
            continue
        vals = struct.unpack_from(("<%dH" if size == 2 else "<%dI") % count, data, off)
        tris = [(vals[i], vals[i + 1], vals[i + 2]) for i in range(0, count, 3)]
        step = max(1, len(tris) // 4096)
        degenerate = sum(1 for a, b, c in tris[::step] if a == b or b == c or a == c)
        if degenerate > 0.2 * len(tris[::step]) or max(vals) >= 65536 * 8:
            continue
        out.append((off, size, tris))
    return out


def find_plain_arrays(data: bytes, start: int, bounds: tuple[M.Vec, M.Vec] | None, vmax: int) -> list[tuple[int, int, list[M.Vec]]]:
    """Vertex arrays stored as [int32 count][count elements] with no element size in front (what this engine build writes for
    the chunk vertex arrays). The element size is unknown, so the usual sizes are tried in turn, with the position (three
    floats inside the mesh bounds, no denormal garbage) at the start of the element. Returns (data offset, element size,
    positions), in file order, without overlaps."""
    n = len(data)
    found: list[tuple[int, int, list[M.Vec]]] = []
    taken_until = 0
    p = start - start % 4
    while p < n - 16:
        if p < taken_until:
            p = taken_until
            continue
        # right after an array the next count need not be 4-byte aligned (an element size of 33 or 37)
        step = 1 if found and p < taken_until + 16 else 4
        (count,) = struct.unpack_from("<i", data, p)
        here = p
        p += step
        if count < 3 or count > vmax:
            continue
        for size in PLAIN_SIZES:
            if here + 4 + count * size > n:
                continue
            if not _positions_ok(data, here + 4, size, count, 0, bounds, range(0, count, max(1, count // 48))):
                continue
            pts = [struct.unpack_from("<3f", data, here + 4 + i * size) for i in range(count)]
            if _positions_ok(data, here + 4, size, count, 0, bounds, range(count)) and _spread_ok(pts, bounds):
                found.append((here + 4, size, pts))
                taken_until = here + 4 + count * size
                break
    return found


def read_plain_mesh(data: bytes, props_end: int, label: str) -> RawMesh | None:
    """Geometry when the vertices are plain count-prefixed arrays: find the index buffer first (it says how many vertices are
    needed), then the vertex arrays, then the UVs inside the vertex elements."""
    bounds = read_bounds(data, props_end)
    start = props_end + (28 if bounds else 0)
    best = None
    for off, size, tris in index_candidates(data, start):
        need = max(max(t) for t in tris) + 1
        if need < 4:
            continue
        arrays = find_plain_arrays(data, start, bounds, max(need, 8))
        total = sum(len(a[2]) for a in arrays)
        if total < need:
            continue
        if best is None or len(tris) > len(best[2]):
            best = (arrays, off, tris, need)
    if best is None:
        return None
    arrays, _off, tris, need = best
    pts: list[M.Vec] = []
    uvs: list[tuple[float, float]] = []
    have_uv = True
    for off, size, pos in arrays:
        pts += pos
        uv = _element_uvs(data, off, size, len(pos))
        if uv is None:
            have_uv = False
        else:
            uvs += uv
    pts = pts[:need]
    uvs = uvs[:need] if have_uv and len(uvs) >= need else []
    m = M.Mesh(positions=[(p[0], p[1], p[2]) for p in pts], uvs=uvs, tris=tris)
    sizes = [a[1] for a in arrays]
    return RawMesh(m, f"{label}: {len(pts)} vertices, {len(tris)} triangles, uvs {'yes' if uvs else 'no'}, "
                      f"plain arrays {len(arrays)} (element sizes {sizes}), bounds {'yes' if bounds else 'no'}", [])


def _element_uvs(data: bytes, off: int, size: int, count: int):
    """A float pair inside the element (after the position) that behaves like UVs."""
    for o in range(12, size - 7, 4):
        uv = _uv_try(data, off, size, count, o, "<2f")
        if uv:
            return uv
    return None


def read_mesh_blob(data: bytes, props_end: int, label: str) -> RawMesh | None:
    """Positions, triangles and UVs of the first LOD found in an export's data (after its tagged properties).
    Bulk-array layout first (element size written in front), then plain count-prefixed arrays."""
    raw = _read_bulk_mesh(data, props_end, label)
    return raw or read_plain_mesh(data, props_end, label)


def vertex_arrays(data: bytes, start: int, bounds: tuple[M.Vec, M.Vec] | None) -> list[tuple[int, int, int, int, list[M.Vec]]]:
    """Bulk arrays whose elements hold a position (three floats inside the bounds) somewhere inside the element, in file order and
    without overlaps: (data offset, element size, count, position offset, positions)."""
    out = []
    taken = 0
    for off, size, count in _bulk_arrays(data, start, ELEMENT_SIZES):
        if off < taken or count > MAX_VERTS or count < 4:
            continue
        sample = range(0, count, max(1, count // 64))
        for o in range(0, size - 11, 4):
            if _positions_ok(data, off, size, count, o, bounds, sample):
                pts = [struct.unpack_from("<3f", data, off + i * size + o) for i in range(count)]
                if _spread_ok(pts, bounds):
                    out.append((off, size, count, o, pts))
                    taken = off + size * count
                    break
    return out


def element_uvs(data: bytes, off: int, size: int, count: int, pos_offset: int):
    """UVs inside a vertex element: a half-float pair (the usual) or a float pair that is not the position."""
    for o in range(0, size - 3, 2):
        if pos_offset - 4 < o < pos_offset + 12:
            continue
        for fmt, width in (("<2e", 4), ("<2f", 8)):
            if o + width > size or (width == 8 and o % 4):
                continue
            uv = _uv_try(data, off, size, count, o, fmt)
            if uv:
                return uv
    return None


def _read_bulk_mesh(data: bytes, props_end: int, label: str) -> RawMesh | None:
    bounds = read_bounds(data, props_end)
    start = props_end + (28 if bounds else 0)
    arrays = vertex_arrays(data, start, bounds)
    if not arrays:
        return None
    best = None
    for _off, _size, tris in index_candidates(data, start):
        need = max(max(t) for t in tris) + 1
        use, total = [], 0
        for arr in arrays:  # the first arrays in the file, enough to cover the highest index
            use.append(arr)
            total += arr[2]
            if total >= need:
                break
        if total < need:
            continue
        if best is None or len(tris) > len(best[1]):
            best = (use, tris, need)
    if best is None:
        return None
    use, tris, need = best
    pts: list[M.Vec] = []
    uvs: list[tuple[float, float]] = []
    have_uv = True
    for off, size, count, o, pos in use:
        pts += pos
        uv = element_uvs(data, off, size, count, o)
        if uv is None:
            have_uv = False
        else:
            uvs += uv
    pts = pts[:need]
    uvs = uvs[:need] if have_uv and len(uvs) >= need else []
    if not uvs:  # UVs in a buffer of their own, one element per vertex
        uvs = find_uvs(data, start, len(pts), use[0][0]) or []
    m = M.Mesh(positions=[(q[0], q[1], q[2]) for q in pts], uvs=uvs, tris=tris)
    sizes = [(u[1], u[3]) for u in use]
    return RawMesh(m, f"{label}: {len(pts)} vertices, {len(tris)} triangles, uvs {'yes' if uvs else 'no'}, "
                      f"bulk arrays {len(use)} (element size, position offset: {sizes}), bounds {'yes' if bounds else 'no'}", [])


def material_refs(pkg: upk.Package, data: bytes, start: int) -> list[str]:
    """Object references in the data that point at materials (imports and exports), in order of first appearance."""
    seen: list[str] = []
    n_imp, n_exp = len(pkg.imports), len(pkg.exports)
    for p in range(start - start % 4, len(data) - 3, 4):
        (v,) = struct.unpack_from("<i", data, p)
        if v == 0 or v < -n_imp or v > n_exp:
            continue
        try:
            cls = pkg.obj_class(v)
        except (IndexError, upk.UPKError):
            continue
        if cls in MATERIAL_CLASSES:
            path = pkg.path_of(v)
            if path not in seen:
                seen.append(path)
        if len(seen) >= 8:
            break
    return seen


# ---- textures -------------------------------------------------------------------------------------------------------

def texture_parameters(ix, material: str, depth: int = 0) -> dict[str, str]:
    """{parameter name lower-case: texture path} of a material instance and its parents."""
    out: dict[str, str] = {}
    if depth > 4 or not material:
        return out
    props = ix.props(material) or {}
    values = props.get("TextureParameterValues")
    items = values.get("items") if isinstance(values, dict) else None
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict) and isinstance(it.get("ParameterValue"), str):
                out.setdefault(str(it.get("ParameterName", "")).lower(), it["ParameterValue"])
    parent = props.get("Parent")
    if isinstance(parent, str):
        for k, v in texture_parameters(ix, parent, depth + 1).items():
            out.setdefault(k, v)
    if not out:  # a plain material: its texture sample expressions
        try:
            for child in ix.children(material):
                cp = ix.props(child) or {}
                tex = cp.get("Texture")
                if isinstance(tex, str):
                    out.setdefault(str(cp.get("ParameterName") or child).lower(), tex)
        except Exception:  # noqa: BLE001
            pass
    return out


def pick_textures(params: dict[str, str]) -> tuple[str | None, str | None]:
    diffuse = normal = None
    for name, path in params.items():
        low = (name + " " + path).lower()
        if normal is None and ("norm" in low or low.endswith("_n") or "_nrm" in low):
            normal = path
        elif diffuse is None and any(k in low for k in ("diff", "albedo", "base", "color", "_d", "diffuse")):
            diffuse = path
    if diffuse is None:
        diffuse = next((p for p in params.values() if p != normal), None)
    return diffuse, normal


def dds_header(width: int, height: int, fourcc: bytes, size: int) -> bytes:
    return struct.pack("<4sIIIIIII44sIIIIIIIIIIIII", b"DDS ", 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, height, width, size, 0, 1,
                       b"\0" * 44, 32, 0x4, struct.unpack("<I", fourcc)[0], 0, 0, 0, 0, 0, 0x1000, 0, 0, 0, 0)


def read_texture(ix, path: str, tfc_dir, say, max_dim: int = 1024) -> bytes | None:
    """A Texture2D as a DDS file (DXT1 or DXT5) at most max_dim wide, taken from the mip chain, or None."""
    found = ix.get(path)
    if not found:
        say(f"texture {path}: not found")
        return None
    pkg, idx = found
    props = ix.props(path) or {}
    w, h = props.get("SizeX"), props.get("SizeY")
    fmt = str(props.get("Format", ""))
    if not isinstance(w, int) or not isinstance(h, int) or w < 4 or h < 4:
        say(f"texture {path}: no size")
        return None
    if "DXT1" in fmt:
        fourcc, per = b"DXT1", 8
    elif "DXT5" in fmt:
        fourcc, per = b"DXT5", 16
    else:
        say(f"texture {path}: unsupported format {fmt or '?'}")
        return None
    data = pkg.export_data(idx)
    mips = parse_mips(data, w, h, per)
    if not mips:
        say(f"texture {path}: no mip table found ({w}x{h} {fmt}, {len(data)} bytes)")
        return None
    usable = sorted((m for m in mips if m["w"] <= max_dim and m["h"] <= max_dim), key=lambda m: -m["w"] * m["h"]) or mips[-1:]
    for mip in usable:  # the biggest first; a smaller one stands in when it cannot be read (the resident mips are inside the package)
        pixels = _mip_pixels(mip, tfc_dir, props.get("TextureFileCacheName"), say, path)
        if pixels is not None:
            return dds_header(mip["w"], mip["h"], fourcc, len(pixels)) + pixels
    return None


def parse_mips(data: bytes, w: int, h: int, per: int) -> list[dict]:
    """The mip chain of a Texture2D export: entries [flags][element count][size on disk][offset] then, when the data is inline
    (flags 0), the data, then [width][height]. The top mip's entry is found by its element count, at any byte offset."""
    want = (w // 4) * (h // 4) * per
    n = len(data)
    needle = struct.pack("<i", want)
    hits = []
    at = data.find(needle, 4)
    while at >= 0:
        hits.append(at - 4)
        at = data.find(needle, at + 1)
    for p0 in hits:
        if p0 < 0 or p0 + 16 > n:
            continue
        flags, count, disk, off = struct.unpack_from("<Iiii", data, p0)
        if count != want or not 0 < disk <= want + want // 8 + 4096:  # compressed data can be a little bigger than the raw size
            continue
        mips: list[dict] = []
        p = p0
        cw, ch = w, h
        while p + 24 <= n and cw >= 1 and ch >= 1:
            flags, count, disk, off = struct.unpack_from("<Iiii", data, p)
            need = max(1, (cw + 3) // 4) * max(1, (ch + 3) // 4) * per
            if count != need or not 0 < disk <= need + need // 8 + 4096:
                break
            q = p + 16
            inline = None
            if not flags & 1:
                inline = data[q:q + disk]
                q += disk
            if q + 8 > n or struct.unpack_from("<ii", data, q) != (cw, ch):
                break
            mips.append({"w": cw, "h": ch, "flags": flags, "count": count, "disk": disk, "offset": off, "inline": inline})
            p = q + 8
            if cw == 1 and ch == 1:
                break
            cw, ch = max(1, cw // 2), max(1, ch // 2)
        if len(mips) >= 2:
            return mips
    return []


def _mip_pixels(mip: dict, tfc_dir, tfc_name, say, label: str) -> bytes | None:
    if mip["inline"] is not None:
        raw = mip["inline"]
    else:
        if not tfc_dir or not tfc_name:
            say(f"texture {label}: mip {mip['w']}x{mip['h']} is in a texture file cache but none is named")
            return None
        path = _tfc_path(tfc_dir, str(tfc_name))
        if path is None:
            say(f"texture {label}: cache file {tfc_name}.tfc not found")
            return None
        with open(path, "rb") as f:
            f.seek(mip["offset"])
            raw = f.read(mip["disk"])
    out = _unpack(raw, mip["flags"], mip["count"])
    if out is None:
        say(f"texture {label}: mip {mip['w']}x{mip['h']} could not be unpacked (flags {mip['flags']:#x}, {len(raw)} bytes read)")
    return out


_TFC_FILES: dict[str, dict] = {}


def _tfc_path(root, name: str):
    from pathlib import Path

    key = str(root)
    if key not in _TFC_FILES:  # one walk of the game folder, not one per texture
        _TFC_FILES[key] = {f.stem.lower(): f for f in Path(root).rglob("*.tfc")}
    return _TFC_FILES[key].get(name.lower())


def _unpack(raw: bytes, flags: int, want: int) -> bytes | None:
    if len(raw) == want and not flags & 0x32:
        return raw
    if flags & 0x2:  # zlib
        try:
            out = zlib.decompress(raw)
            return out if len(out) == want else None
        except zlib.error:
            return None
    if flags & 0x10 or flags & 0x20 or raw[:4] == struct.pack("<I", upk.TAG):  # a compressed chunk, like the package's own
        try:
            out = upk._decompress_chunk(raw, 0)  # noqa: SLF001
            return out[:want] if len(out) >= want else None
        except Exception:  # noqa: BLE001
            return None
    return raw if len(raw) == want else None
