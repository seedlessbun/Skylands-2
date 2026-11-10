"""The gun texture survey (0.63.0): material chains with colours, the textures as pictures, the zip to send back."""

import json
import struct
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_bl2  # noqa: E402
from skylands_setup import texprobe  # noqa: E402


def mips(w, h):
    out = b""
    while w >= 4 and h >= 4:
        size = (w // 4) * (h // 4) * 8
        out += struct.pack("<Iiii", 0, size, size, 0x1000) + bytes(range(256)) * (size // 256) + bytes(range(size % 256)) + struct.pack("<ii", w, h)
        w, h = w // 2, h // 2
    return out


def install(root):
    cooked = Path(root) / "WillowGame" / "CookedPCConsole"
    cooked.mkdir(parents=True)
    b = fake_bl2.ObjBuilder()
    b.obj("Weap_SMG.Tex.Weap_SMG_Comp", "Texture2D", b"")
    tex = b.paths["Weap_SMG.Tex.Weap_SMG_Comp"]
    b.exports[tex - 1]["body"] = (struct.pack("<i", -1) + b.i("SizeX", 16) + b.i("SizeY", 16) +
                                  b.prop("Format", "ByteProperty", b.n("PF_DXT1"), enum="EPixelFormat") + b.none() + b"\x01\x02\x03\x04" + mips(16, 16))
    b.obj("Weap_Shared.Mat.Gun_Master", "Material", b.s("PhysMaterial", "x"))
    b.obj("Weap_SMG.Mat.Mati_Bandit_Rare", "MaterialInstanceConstant", b"")
    mic = b.paths["Weap_SMG.Mat.Mati_Bandit_Rare"]
    b.exports[mic - 1]["body"] = (struct.pack("<i", -1) + b.o("Parent", "Weap_Shared.Mat.Gun_Master") +
                                  b.arr_structs("TextureParameterValues", [b.s("ParameterName", "p_Comp") + b.o("ParameterValue", "Weap_SMG.Tex.Weap_SMG_Comp")]) +
                                  b.arr_structs("VectorParameterValues", [b.s("ParameterName", "p_ColorA") + b.prop("ParameterValue", "StructProperty", struct.pack("<4f", 0.8, 0.1, 0.1, 1.0), struct_name="LinearColor")]) +
                                  b.arr_structs("ScalarParameterValues", [b.s("ParameterName", "p_Wear") + b.f("ParameterValue", 0.25)]) + b.none())
    b.obj("GD_Weap_SMG.ManufacturerMaterials.Mat_Bandit_3_Rare", "WeaponPartDefinition", b.o("Material", "Weap_SMG.Mat.Mati_Bandit_Rare"))
    (cooked / "Wpn_Fake.upk").write_bytes(b.build())


def test_the_texture_survey_dumps_the_material_chain_and_the_texture_and_packs_a_zip(tmp_path):
    install(tmp_path / "bl2")
    work = tmp_path / "work"
    work.mkdir()
    (work / "pandora.json").write_text(json.dumps({"weapons": {"guns": [
        {"type": "smg", "manufacturer": "Bandit", "rarity": "rare", "slots": {"Material": ["GD_Weap_SMG.ManufacturerMaterials.Mat_Bandit_3_Rare"]}}]}}))
    assert texprobe.main(["--bl2", str(tmp_path / "bl2"), "--work", str(work), "--minutes", "2"]) == 0
    report = (work / "bl2-gun-texture-report.txt").read_text(encoding="utf-8")
    assert "smg / Bandit / rare" in report and "Material Weap_SMG.Mat.Mati_Bandit_Rare" in report, report
    assert "vector  p_ColorA = [0.800, 0.100, 0.100, 1.000]" in report, report
    assert "scalar  p_Wear = 0.25" in report and "texture p_Comp = Weap_SMG.Tex.Weap_SMG_Comp" in report
    assert "Weap_Shared.Mat.Gun_Master (Material)" in report or "level 1: Weap_Shared.Mat.Gun_Master  class Material" in report
    assert "- Weap_SMG.Tex.Weap_SMG_Comp: 16x16" in report and "read at 16x16" in report, report
    assert "guess_Weap_SMG.Mat.Mati_Bandit_Rare.png" in report
    with zipfile.ZipFile(work / "bl2-gun-textures.zip") as z:
        names = z.namelist()
    assert "bl2-gun-texture-report.txt" in names and any(n.startswith("gun-textures/tex_") for n in names), names
    png = (work / "gun-textures" / "tex_Weap_SMG.Tex.Weap_SMG_Comp.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (80, 16)  # colour + 4 channels side by side


def test_dxt5_alpha_is_decoded():
    # one 4x4 DXT5 block: alpha endpoints 255/0 with index 1 (= 0) for every pixel; colour white
    alpha = bytes((255, 0)) + (int("001" * 16, 2)).to_bytes(6, "little")
    colour = struct.pack("<HHI", 0xFFFF, 0xFFFF, 0)
    dds = bytearray(128)
    dds[:4] = b"DDS "
    struct.pack_into("<II", dds, 12, 4, 4)
    dds[84:88] = b"DXT5"
    w, h, rgba = texprobe.decode_rgba(bytes(dds) + alpha + colour)
    assert (w, h) == (4, 4) and rgba[0:4] == bytes((255, 255, 255, 0)) and len(rgba) == 64
