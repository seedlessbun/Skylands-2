"""The fuzzy mesh search must only map names of the same gun type (0.33.0 put a pistol's magazine on a shotgun)."""
from pathlib import Path
from types import SimpleNamespace as N

from skylands_setup.bl2 import gunparts, upk


class _Pkg:
    def __init__(self, names):
        self._by_name = {n: [i + 1] for i, n in enumerate(names)}
        self._names = list(names)

    def _indexes(self):
        pass

    def obj_class(self, i):
        return "SkeletalMesh"

    def path_of(self, i):
        return f"Weap.X.{self._names[i - 1]}"


def _run(monkeypatch, tmp_path, names, left):
    f = tmp_path / "a.upk"
    f.write_bytes(b"x")
    monkeypatch.setattr(upk, "read_name_set", lambda p: set(names))
    src = gunparts.Bl2Source.__new__(gunparts.Bl2Source)
    src.log = lambda m, force=False: None
    src.ix = N(files=[f], groups={}, errors={}, package=lambda p: _Pkg(names))
    src.mesh_index = {}
    src._fuzzy_meshes(left)
    return src.mesh_index


def test_same_type_other_prefix_is_found(monkeypatch, tmp_path):
    got = _run(monkeypatch, tmp_path, ["shotgun_body_bandit"], {"sg_body_bandit"})
    assert set(got) == {"sg_body_bandit"}


def test_other_gun_types_are_never_mapped(monkeypatch, tmp_path):
    got = _run(monkeypatch, tmp_path, ["pistol_body_bandit", "ar_body_bandit", "smg_body_bandit", "launcher_body_bandit"],
               {"sg_body_bandit", "sr_body_bandit"})
    assert got == {}


def test_shotgun_survey_runs_on_a_fake_install(tmp_path):
    import fake_bl2
    from skylands_setup import shotgunprobe

    bl2 = tmp_path / "bl2"
    fake_bl2.pandora_install(bl2)
    cooked = bl2 / "WillowGame" / "CookedPCConsole"
    fake_bl2.level_package_importing(cooked / "Weap_Shotgun_Test.upk", ["SG_Body_Bandit", "shotgun_body_x"])
    out = tmp_path / "report.txt"
    assert shotgunprobe.main(["--bl2", str(bl2), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "Weap_Shotgun_Test.upk" in text and "sg_body_bandit" in text and "Report written" in text


def test_gestalt_survey_runs_on_a_fake_install(tmp_path):
    import fake_bl2
    from skylands_setup import gestaltprobe

    bl2 = tmp_path / "bl2"
    fake_bl2.pandora_install(bl2)
    fake_bl2.level_package_importing(bl2 / "WillowGame" / "CookedPCConsole" / "G_Test.upk", ["GestaltDef_Shotgun"])
    out = tmp_path / "report.txt"
    assert gestaltprobe.main(["--bl2", str(bl2), "--out", str(out)]) == 0
    assert "gestalt" in out.read_text(encoding="utf-8").lower()


def test_a_gestalt_part_is_a_run_of_triangles_of_the_combined_mesh():
    from skylands_setup import meshes as M

    src = gunparts.Bl2Source.__new__(gunparts.Bl2Source)
    src.log = lambda m, force=False: None
    src.stats = {"meshes": 0}
    # a combined mesh of two quads (4 triangles); part "a" is triangles 0-1, part "b" triangles 2-3
    pos = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (5, 0, 0), (6, 0, 0), (6, 1, 0), (5, 1, 0)]
    full = M.Mesh(positions=pos, uvs=[(i / 8, 0.0) for i in range(8)], tris=[(0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7)])
    src._gestalt_mesh = lambda key: full
    src.gestalt_table = {"a": ("k", 0, 2), "b": ("k", 6, 2)}
    b = src._read_gestalt_part("sg_x", "b")
    assert b["placed"] and len(b["mesh"].tris) == 2 and len(b["mesh"].positions) == 4
    assert min(p[0] for p in b["mesh"].positions) == 5 and len(b["mesh"].uvs) == 4
    assert max(max(t) for t in b["mesh"].tris) == 3


def test_gestalt_definition_parts_are_registered_by_fragment_name(tmp_path):
    src = gunparts.Bl2Source.__new__(gunparts.Bl2Source)
    src.log = lambda m, force=False: None
    items = {"type": "Array", "count": 2, "items": [
        {"SkeletalMeshFragmentName": "SG_Body_Bandit", "MaterialIndex": 0, "FirstIndex": 0, "NumPrimitives": 10},
        {"SkeletalMeshFragmentName": "SG_Barrel_Bandit", "MaterialIndex": 0, "FirstIndex": 30, "NumPrimitives": 5}]}
    assert len(src._items(items)) == 2 and src._items([1, 2]) == [1, 2] and src._items(None) == []
