"""Beam meshes are checked with nifly (set NIFCHECK to tools' nifly checker binary, see MODLOG)."""

import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))

from skylands_setup.skyrim import nif  # noqa: E402

NIFCHECK = os.environ.get("NIFCHECK", "")


def test_dds_gradient():
    d = nif.dds_gradient(64)
    assert d[:4] == b"DDS " and struct.unpack_from("<I", d, 4)[0] == 124 and len(d) == 128 + 64 * 4 * 4
    assert d[128 + 3] == 0 and d[-1] == 255  # transparent top row, opaque bottom row


def test_beam_header():
    b = nif.beam((61, 210, 11), "textures\\skylands\\beam.dds")
    assert b.startswith(b"Gamebryo File Format, Version 20.2.0.7\n")


@pytest.mark.skipif(not NIFCHECK, reason="set NIFCHECK to the nifly checker")
def test_beam_resaves_identically_in_nifly(tmp_path):
    src, out = tmp_path / "beam.nif", tmp_path / "resaved.nif"
    src.write_bytes(nif.beam((61, 210, 11), "textures\\skylands\\beam.dds"))
    r = subprocess.run([NIFCHECK, str(src), str(out)], capture_output=True, text=True, check=True)
    assert "shape LootBeam0 verts=4 tris=2" in r.stdout and "emissive 0.24 0.82 0.04" in r.stdout
    assert src.read_bytes() == out.read_bytes()


def _gun_parts():
    from skylands_setup import meshes as M

    return [(M.box(0, 0, 0, 0.2, 1.0, 0.3), "textures\\skylands\\guns\\t.dds", "textures\\skylands\\guns\\t_n.dds"),
            (M.cylinder(0, 0.8, 0.1, 0.05, 0.6), None, None)]


def test_gun_nif_blocks():
    data = nif.gun(_gun_parts())
    assert data.startswith(b"Gamebryo File Format, Version 20.2.0.7\n")
    for t in (b"BSLightingShaderProperty", b"BSShaderTextureSet", b"bhkRigidBodyT", b"bhkCollisionObject", b"BSXFlags"):
        assert t in data


def test_gun_nif_rejects_empty_and_huge_meshes():
    from skylands_setup import meshes as M

    with pytest.raises(ValueError):
        nif.gun([(M.Mesh(), None, None)])


@pytest.mark.skipif(not NIFCHECK, reason="set NIFCHECK to the nifly checker")
def test_gun_nif_loads_in_nifly(tmp_path):
    src, out = tmp_path / "gun.nif", tmp_path / "resaved.nif"
    src.write_bytes(nif.gun(_gun_parts()))
    r = subprocess.run([NIFCHECK, str(src), str(out)], capture_output=True, text=True, check=True)
    assert "shape SkylandsGun0 verts=24 tris=12" in r.stdout and "shape SkylandsGun1" in r.stdout and "resaved" in r.stdout


def test_skin_partition_vertices_are_read():
    import struct

    from skylands_setup.skyrim import nifread

    desc = (0x1 | 0x400) << 44 | (4 << 0)  # positions, full precision, 16-byte vertices, position at offset 0
    verts = b"".join(struct.pack("<3ff", x, 2.0 * x, 3.0, 0.0) for x in (1.0, 2.0, 3.0))
    block = struct.pack("<IIIQ", 0, len(verts), 16, desc) + verts
    s = nifread.read_partition(block)
    assert s.positions == [(1.0, 2.0, 3.0), (2.0, 4.0, 3.0), (3.0, 6.0, 3.0)]


def test_gun_carries_the_vanilla_attach_point():
    from skylands_setup import meshes as M
    from skylands_setup.skyrim import nifread

    data = nif.gun([(M.box(0, 0, 0, 1, 1, 1), None, None)], extra=[("NiStringExtraData", "Prn", "WeaponBack", 0)])
    assert ("NiStringExtraData", "Prn", "WeaponBack", 0) in nifread.extra_data(data)
