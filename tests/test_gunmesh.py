"""The mesh scavenger finds geometry by what it looks like; these blobs have the shapes real exports are expected to have."""

import struct
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))

from skylands_setup import meshes as M  # noqa: E402
from skylands_setup.bl2 import gunmesh, gunparts  # noqa: E402


def blob(mesh, elem_size=32, pos_offset=16, uv_buffer=True, index_size=2, junk=40):
    n = len(mesh.positions)
    lo, hi = mesh.bounds()
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    ext = [(b - a) / 2 for a, b in zip(lo, hi)]
    out = bytearray(b"\x07" * junk)  # stands in for the tagged properties
    props_end = len(out)
    out += struct.pack("<7f", *centre, *ext, 1.0)
    out += struct.pack("<4i", 1, 2, 3, 4)
    out += struct.pack("<ii", elem_size, n)
    for i in range(n):
        v = bytearray(elem_size)
        struct.pack_into("<I", v, 0, 0x80808080)  # packed tangents
        struct.pack_into("<3f", v, pos_offset, *mesh.positions[i])
        out += v
    out += struct.pack("<ii", 4, n)
    for u, vv in mesh.uvs:
        out += struct.pack("<2e", u, vv)
    out += struct.pack("<i", 99)
    flat = [i for t in mesh.tris for i in t]
    out += struct.pack("<ii", index_size, len(flat))
    out += struct.pack(f"<{len(flat)}{'H' if index_size == 2 else 'I'}", *flat)
    return bytes(out), props_end


def test_scavenger_finds_positions_uvs_and_indices():
    box = M.box(0, 0, 0, 40, 10, 6)
    data, end = blob(box)
    raw = gunmesh.read_mesh_blob(data, end, "box")
    assert raw is not None
    assert len(raw.mesh.positions) == 24 and len(raw.mesh.tris) == 12 and len(raw.mesh.uvs) == 24
    assert raw.mesh.positions[3] == box.positions[3] and raw.mesh.tris == box.tris
    assert abs(raw.mesh.uvs[2][0] - box.uvs[2][0]) < 1e-3


def test_scavenger_with_32_bit_indices_and_other_position_offset():
    cyl = M.cylinder(0, 0, 0, 3, 20, sides=8)
    data, end = blob(cyl, elem_size=40, pos_offset=8, index_size=4)
    raw = gunmesh.read_mesh_blob(data, end, "cyl")
    assert raw is not None and len(raw.mesh.positions) == len(cyl.positions) and raw.mesh.tris == cyl.tris


def test_scavenger_rejects_noise():
    assert gunmesh.read_mesh_blob(bytes(range(256)) * 40, 10, "noise") is None


def test_orientation_points_barrel_up_the_y_axis():
    # a game mesh with the barrel along +x, up +z: body at the origin, barrel further along +x, magazine below
    body = M.box(0, 0, 0, 40, 10, 14)
    barrel = M.box(45, 0, 3, 50, 4, 4)
    mag = M.box(5, 0, -12, 8, 6, 14)
    matrix = gunparts.orientation({"Body": body, "Barrel": barrel, "Magazine": mag})
    out = M.transformed(barrel, matrix)
    cx = sum(p[0] for p in out.positions) / len(out.positions)
    cy = sum(p[1] for p in out.positions) / len(out.positions)
    assert cy > 30 and abs(cx) < 1  # the barrel now lies along +y
    mout = M.transformed(mag, matrix)
    assert sum(p[2] for p in mout.positions) < 0  # the magazine is still below
    assert M.det3(matrix) < 0  # left-handed source: the winding flips


def test_pick_textures():
    d, n = gunmesh.pick_textures({"diffuse": "A.Tex_D", "normal": "A.Tex_N"})
    assert d == "A.Tex_D" and n == "A.Tex_N"
    d, n = gunmesh.pick_textures({"misc": "B.Tex"})
    assert d == "B.Tex" and n is None


def plain_blob(mesh, size=40, uv_offset=24, junk=40):
    """Vertices as [count][elements] with no element size in front, like the real Borderlands 2 skeletal meshes."""
    lo, hi = mesh.bounds()
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    ext = [(b - a) / 2 for a, b in zip(lo, hi)]
    out = bytearray(b"\x07" * junk)
    end = len(out)
    out += struct.pack("<7f", *centre, *ext, 1.0) + struct.pack("<ii", 1, 0)
    out += struct.pack("<i", len(mesh.positions))
    for i, p in enumerate(mesh.positions):
        v = bytearray(size)
        struct.pack_into("<3f", v, 0, *p)
        struct.pack_into("<I", v, 12, 0x80808080)
        struct.pack_into("<2f", v, uv_offset, *mesh.uvs[i])
        out += v
    flat = [i for t in mesh.tris for i in t]
    out += struct.pack("<ii", 2, len(flat)) + struct.pack(f"<{len(flat)}H", *flat)
    return bytes(out), end


def test_plain_array_vertices():
    box = M.box(0, 28, 3, 8, 75, 33)
    for size, uv in ((40, 24), (36, 24), (33, 24), (32, 20)):
        data, end = plain_blob(box, size, uv)
        raw = gunmesh.read_mesh_blob(data, end, "stock")
        assert raw is not None, size
        assert len(raw.mesh.positions) == 24 and raw.mesh.tris == box.tris and raw.mesh.positions[5] == box.positions[5], (size, raw.note)
        assert f"element sizes [{size}]" in raw.note and len(raw.mesh.uvs) == 24


def test_two_plain_chunks_are_joined_in_order():
    a = M.box(0, 0, 0, 8, 20, 8)
    b = M.box(0, 40, 0, 8, 20, 8)
    both = M.merged([a, b])
    lo, hi = both.bounds()
    centre = [(x + y) / 2 for x, y in zip(lo, hi)]
    ext = [(y - x) / 2 for x, y in zip(lo, hi)]
    out = bytearray(b"\x07" * 40)
    end = len(out)
    out += struct.pack("<7f", *centre, *ext, 1.0) + struct.pack("<ii", 1, 0)
    for chunk, size in ((a, 33), (b, 40)):  # a rigid chunk, then a soft chunk
        out += struct.pack("<i", len(chunk.positions))
        for i, p in enumerate(chunk.positions):
            v = bytearray(size)
            struct.pack_into("<3f", v, 0, *p)
            struct.pack_into("<I", v, 12, 0x80808080)
            struct.pack_into("<2f", v, 24 if size > 33 else 16, *chunk.uvs[i])
            out += v
        out += b"\x00" * 4
    flat = [i for t in both.tris for i in t]
    out += struct.pack("<ii", 2, len(flat)) + struct.pack(f"<{len(flat)}H", *flat)
    raw = gunmesh.read_mesh_blob(bytes(out), end, "two")
    assert raw is not None and len(raw.mesh.positions) == 48 and raw.mesh.positions[30] == both.positions[30], raw and raw.note


def real_layout_blob(mesh, junk=41):
    """The layout seen in a real Borderlands 2 SkeletalMesh: the vertex bulk array header is not 4-byte aligned, elements are 36 bytes
    (tangents, bone indices and weights, the position at +16, half-float UVs at +28), the index buffer is a bulk array of 16-bit values."""
    lo, hi = mesh.bounds()
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    ext = [(b - a) / 2 for a, b in zip(lo, hi)]
    out = bytearray(b"\\x07" * junk)
    end = len(out)
    out += struct.pack("<7f", *centre, *ext, 1.0) + struct.pack("<i", 1) + b"\\0" * 28 + b"\\x02\\x00"  # materials, origin, a 2-byte field
    flat = [i for t in mesh.tris for i in t]
    out += struct.pack("<ii", 2, len(flat)) + struct.pack(f"<{len(flat)}H", *flat)
    out += b"\\x00\\x00\\x00"
    out += struct.pack("<ii", 36, len(mesh.positions))
    for i, p in enumerate(mesh.positions):
        v = bytearray(36)
        struct.pack_into("<4B", v, 0, 127, 251, 99, 128)
        struct.pack_into("<4B", v, 4, 5, 134, 162, 255)
        struct.pack_into("<3f", v, 16, *p)
        struct.pack_into("<2e", v, 28, *mesh.uvs[i])
        out += v
    return bytes(out), end


def test_real_layout_with_unaligned_bulk_headers():
    mesh = M.cylinder(0, 28, 3, 3, 40, sides=12)
    mesh.uvs = [(min(0.99, u), min(0.99, v)) for u, v in mesh.uvs]
    data, end = real_layout_blob(mesh)
    raw = gunmesh.read_mesh_blob(data, end, "stock")
    assert raw is not None, "not found"
    assert len(raw.mesh.positions) == len(mesh.positions) and raw.mesh.tris == mesh.tris
    assert raw.mesh.positions[10] == pytest.approx(mesh.positions[10], abs=1e-5) and len(raw.mesh.uvs) == len(mesh.uvs)
    assert "(36, 16)" in raw.note


def test_mip_chain_with_compressed_cache_mips_and_inline_tail():
    w = 64
    out = b"\\x01\\x02\\x03\\x04"
    # the big mips live in a texture file cache (flags 0x11, size on disk a little more than the raw size), the small ones are inline
    for size in (64, 32):
        raw = (size // 4) * (size // 4) * 8
        out += struct.pack("<Iiii", 0x11, raw, raw + 121, 0x1000 + size) + struct.pack("<ii", size, size)
    for size in (16, 8, 4):
        raw = (size // 4) * (size // 4) * 8
        out += struct.pack("<Iiii", 0, raw, raw, 0x2000) + bytes([size]) * raw + struct.pack("<ii", size, size)
    mips = gunmesh.parse_mips(out, w, w, 8)
    assert [m["w"] for m in mips] == [64, 32, 16, 8, 4]
    assert mips[0]["inline"] is None and mips[0]["disk"] == 64 * 64 // 2 + 121 and mips[3]["inline"] == bytes([8]) * 32
