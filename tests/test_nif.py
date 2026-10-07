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
