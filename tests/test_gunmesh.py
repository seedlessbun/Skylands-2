"""The mesh scavenger finds geometry by what it looks like; these blobs have the shapes real exports are expected to have."""

import struct
import sys
from pathlib import Path

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
