"""The native source end to end on a fake package: part -> mesh object -> geometry, socket offset, material -> DXT1 texture."""

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_bl2  # noqa: E402
from skylands_setup import meshes as M  # noqa: E402
from skylands_setup.bl2 import gunparts  # noqa: E402
from skylands_setup.bl2.index import Index  # noqa: E402
from test_gunmesh import blob  # noqa: E402


def build_install(root, with_texture=True):
    cooked = Path(root) / "WillowGame" / "CookedPCConsole"
    cooked.mkdir(parents=True)
    b = fake_bl2.ObjBuilder()
    b.obj("Wpn_Pistol.Tex.Pistol_Diffuse", "Texture2D", b"")
    tex = b.paths["Wpn_Pistol.Tex.Pistol_Diffuse"]
    def mips(w, h):  # real layout: [flags][count][size on disk][offset] data [width][height], largest first
        out = b""
        while w >= 4 and h >= 4:
            size = (w // 4) * (h // 4) * 8
            out += struct.pack("<Iiii", 0, size, size, 0x1000) + bytes(range(256)) * (size // 256) + bytes(range(size % 256)) + struct.pack("<ii", w, h)
            w, h = w // 2, h // 2
        return out

    b.exports[tex - 1]["body"] = (struct.pack("<i", -1) + b.i("SizeX", 16) + b.i("SizeY", 16) +
                                  b.prop("Format", "ByteProperty", b.n("PF_DXT1"), enum="EPixelFormat") + b.none() +
                                  b"\x01\x02\x03\x04" + mips(16, 16))
    b.obj("Wpn_Pistol.Mat.Pistol_MIC", "MaterialInstanceConstant", b"")
    mic = b.paths["Wpn_Pistol.Mat.Pistol_MIC"]
    b.exports[mic - 1]["body"] = (struct.pack("<i", -1) + b.arr_structs("TextureParameterValues", [
        b.s("ParameterName", "Diffuse") + b.o("ParameterValue", "Wpn_Pistol.Tex.Pistol_Diffuse")]) + b.none())
    box = M.box(0, 0, 0, 40, 10, 14)
    barrel = M.box(0, 0, 0, 50, 4, 4)

    def mesh_obj(path, mesh, with_mat):
        b.obj(path, "StaticMesh", b"")
        idx = b.paths[path]
        data, end = blob(mesh)
        data = bytearray(data)
        if with_mat:
            data += struct.pack("<i", mic)
        # the properties are empty: just the "None" name, then the blob after it
        props = struct.pack("<i", -1) + b.none()
        b.exports[idx - 1]["body"] = props + bytes(data[end:])
        return idx

    mesh_obj("Wpn_Pistol.Mesh.Pistol_Body", box, True)
    mesh_obj("Wpn_Pistol.Mesh.Pistol_Barrel", barrel, False)
    b.obj("Wpn_Pistol.Mesh.Pistol_Body:Socket_Barrel", "StaticMeshSocket",
          b.s("SocketName", "Barrel") + b.st("RelativeLocation", "Vector", struct.pack("<3f", 45.0, 0.0, 3.0)))
    b.obj("GD_Weap_Pistol.Body.Pistol_Body_A", "WeaponPartDefinition", b.s("GestaltModeSkeletalMeshName", "Wpn_Pistol.Mesh.Pistol_Body"))
    b.obj("GD_Weap_Pistol.Barrel.Pistol_Barrel_A", "WeaponPartDefinition",
          b.s("GestaltModeSkeletalMeshName", "Wpn_Pistol.Mesh.Pistol_Barrel") + b.s("AttachmentPointName", "Barrel"))
    (cooked / "Wpn_Fake.upk").write_bytes(b.build())


def test_native_source_reads_a_gun(tmp_path):
    build_install(tmp_path / "bl2")
    ix = Index(tmp_path / "bl2")
    log = []
    src = gunparts.Bl2Source(ix, log.append)
    built = {"parts": {"Body": "GD_Weap_Pistol.Body.Pistol_Body_A", "Barrel": "GD_Weap_Pistol.Barrel.Pistol_Barrel_A"}}
    parts = src.gun_parts({"type": "pistol"}, built)
    assert parts is not None and len(parts) == 2, log
    assert src.stats["meshes"] == 2 and src.stats["textured"] == 1, (src.stats, log)
    # the barrel sits at the barrel socket (x 45 in the game's axes = y in the gun frame) and the gun is oriented barrel +y
    body, barrel = parts
    by = sum(p[1] for p in barrel.positions) / len(barrel.positions)
    assert by > 30
    assert body.texture and body.texture.startswith("t_")
    tex = src.take_textures()
    assert len(tex) == 1 and next(iter(tex.values()))[:4] == b"DDS " and b"DXT1" in next(iter(tex.values()))[:100]


def test_native_source_reports_a_part_without_a_mesh(tmp_path):
    build_install(tmp_path / "bl2")
    ix = Index(tmp_path / "bl2")
    log = []
    src = gunparts.Bl2Source(ix, log.append)
    assert src.gun_parts({"type": "pistol"}, {"parts": {"Body": "GD_Weap_Pistol.Nothing.Missing"}}) is None
    assert src.stats["no_mesh"] == 1 and any("no mesh object" in m for m in log)


def test_attach_modes(tmp_path):
    build_install(tmp_path / "bl2")
    ix = Index(tmp_path / "bl2")
    built = {"parts": {"Body": "GD_Weap_Pistol.Body.Pistol_Body_A", "Barrel": "GD_Weap_Pistol.Barrel.Pistol_Barrel_A"}}

    def barrel_y(mode):
        src = gunparts.Bl2Source(ix, lambda m: None, attach=mode)
        parts = src.gun_parts({"type": "pistol"}, built)
        return sum(p[1] for p in parts[1].positions) / len(parts[1].positions)

    assert barrel_y("sockets") > 40  # the barrel is moved out to the socket
    assert abs(barrel_y("none")) < 1  # it stays where its own mesh puts it
    assert barrel_y("auto") > 40  # centred on its origin, so the socket applies


def test_missing_mesh_borrows_another_manufacturers_of_the_same_slot(tmp_path):
    build_install(tmp_path / "bl2")
    ix = Index(tmp_path / "bl2")
    src = gunparts.Bl2Source(ix, lambda m: None)
    f = tmp_path / "bl2" / "WillowGame" / "CookedPCConsole" / "Wpn_Fake.upk"
    src.mesh_index = {"pistol_body_hyperion": (f, "Weap_Pistol.Body.Pistol_Body_Hyperion"),
                      "pistol_body_jakobs": (f, "Weap_Pistol.Body.Pistol_Body_Jakobs"),
                      "pistol_grip_jakobs": (f, "Weap_Pistol.Grip.Pistol_Grip_Jakobs")}
    assert src._stand_in("GD_Weap_Pistol.Body.Pistol_Body_Jakobs_2") == "Weap_Pistol.Body.Pistol_Body_Jakobs"  # same manufacturer first
    assert src._stand_in("GD_Weap_Pistol.Body.Pistol_Body_Dahl") == "Weap_Pistol.Body.Pistol_Body_Hyperion"
    assert src._stand_in("GD_Weap_Pistol.Sight.Pistol_Sight_None") is None  # only structural parts are borrowed
    assert src._stand_in("GD_Weap_SMG.Body.SMG_Body_Dahl") is None  # never from another gun type


def test_gestalt_name_found_through_the_name_table(tmp_path):
    cooked = tmp_path / "bl2" / "WillowGame" / "CookedPCConsole"
    cooked.mkdir(parents=True)
    # a part that only carries a plain mesh name (no '.', not an object reference), and a package that holds that mesh
    b = fake_bl2.ObjBuilder()
    b.obj("GD_Weap_Pistol.Barrel.Pistol_Barrel_Z", "WeaponPartDefinition", b.s("GestaltModeSkeletalMeshName", "Pistol_Barrel_Z_Mesh"))
    (cooked / "GD_Parts.upk").write_bytes(b.build())
    m = fake_bl2.ObjBuilder()
    m.obj("Gestalt_Pistols.Meshes.Pistol_Barrel_Z_Mesh", "SkeletalMesh", b"")
    (cooked / "Gestalt_Pistols.upk").write_bytes(m.build())
    ix = Index(tmp_path / "bl2")
    log = []
    src = gunparts.Bl2Source(ix, log.append)
    src.prepare(["GD_Weap_Pistol.Barrel.Pistol_Barrel_Z"])
    assert src.name_files == {"pistol_barrel_z_mesh": [cooked / "Gestalt_Pistols.upk"]}
    assert src.mesh_path("GD_Weap_Pistol.Barrel.Pistol_Barrel_Z") == "Gestalt_Pistols.Meshes.Pistol_Barrel_Z_Mesh", log


def test_mesh_path_derived_from_the_part_path_and_material_texture(tmp_path):
    build_install(tmp_path / "bl2")
    cooked = tmp_path / "bl2" / "WillowGame" / "CookedPCConsole"
    # the real layout: GD_Weap_Pistol.Barrel.X (a part) -> Weap_Pistol.Barrel.X (the mesh); a Material part pointing at a MIC
    b = fake_bl2.ObjBuilder()
    b.obj("Weap_Pistol.Barrel.Pistol_Barrel_A", "SkeletalMesh", b"")
    idx = b.paths["Weap_Pistol.Barrel.Pistol_Barrel_A"]
    data, end = blob(M.box(0, 0, 0, 4, 40, 4))
    b.exports[idx - 1]["body"] = struct.pack("<i", -1) + b.none() + data[end:]
    b.obj("GD_Weap_Pistol.Barrel.Pistol_Barrel_A", "WeaponPartDefinition", b.s("GestaltModeSkeletalMeshName", "Pistol_Barrel_A"))
    b.obj("GD_Weap_Pistol.ManufacturerMaterials.Mat_A", "WeaponPartDefinition", b.s("Material", "Wpn_Pistol.Mat.Pistol_MIC"))
    (cooked / "Weap_Fake.upk").write_bytes(b.build())
    ix = Index(tmp_path / "bl2")
    src = gunparts.Bl2Source(ix, lambda m: None)
    assert src.derived_paths("GD_Weap_Pistol.Barrel.Pistol_Barrel_A")[0] == "Weap_Pistol.Barrel.pistol_barrel_a"
    built = {"parts": {"Barrel": "GD_Weap_Pistol.Barrel.Pistol_Barrel_A", "Material": "GD_Weap_Pistol.ManufacturerMaterials.Mat_A"}}
    assert src.gun_parts({"type": "pistol"}, built) is None  # a barrel alone is not a gun: no body mesh, left to the next method
    assert src.stats["no_body"] == 1
    # with a body (the same mesh stands in for it) the gun is built and carries the Material part's texture
    b = fake_bl2.ObjBuilder()
    b.obj("Weap_Pistol.Body.Pistol_Body_A", "SkeletalMesh", b"")
    data2, end2 = blob(M.box(0, 0, 0, 8, 20, 12))
    b.exports[b.paths["Weap_Pistol.Body.Pistol_Body_A"] - 1]["body"] = struct.pack("<i", -1) + b.none() + data2[end2:]
    b.obj("GD_Weap_Pistol.Body.Pistol_Body_A", "WeaponPartDefinition", b.s("GestaltModeSkeletalMeshName", "Pistol_Body_A"))
    (cooked / "Weap_Fake2.upk").write_bytes(b.build())
    ix = Index(tmp_path / "bl2")
    src = gunparts.Bl2Source(ix, lambda m: None)
    built["parts"]["Body"] = "GD_Weap_Pistol.Body.Pistol_Body_A"
    parts = src.gun_parts({"type": "pistol"}, built)
    assert parts and len(parts) == 2 and all(p.texture and p.texture.startswith("t_") for p in parts), src.stats
