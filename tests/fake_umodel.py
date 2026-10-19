"""Stands in for umodel.exe in tests: writes a PSK and a TGA where UModel would."""

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))

from skylands_setup import meshes as M  # noqa: E402
from skylands_setup.bl2 import psk  # noqa: E402

args = sys.argv[1:]
out = next(Path(a.split("=", 1)[1]) for a in args if a.startswith("-out="))
pkg, obj, cls = [a for a in args if not a.startswith("-")][-3:]
if obj == "Pistol_Barrel":
    box = M.box(0, 0, 0, 50, 4, 4)
else:
    box = M.box(0, 0, 0, 40, 10, 14)
d = out / Path(pkg).stem / cls
d.mkdir(parents=True, exist_ok=True)
(d / f"{obj}.pskx").write_bytes(psk.write(box, "Mat_" + obj))
t = out / Path(pkg).stem / "Texture2D"
t.mkdir(parents=True, exist_ok=True)
px = bytes((20, 40, 200, 255)) * 16
(t / f"{obj}_Diffuse.tga").write_bytes(bytes((0, 0, 2)) + b"\0" * 9 + struct.pack("<HH", 4, 4) + bytes((32, 0x20)) + px)
(t / f"{obj}_Normal.tga").write_bytes(bytes((0, 0, 2)) + b"\0" * 9 + struct.pack("<HH", 4, 4) + bytes((32, 0x20)) + px)
print("exported", obj)
