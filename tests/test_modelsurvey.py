import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

from skylands_setup import modelsurvey  # noqa: E402
from skylands_setup.bl2 import gunparts  # noqa: E402
from skylands_setup.bl2.index import Index  # noqa: E402
import test_gunparts  # noqa: E402


def test_inspect_part_reports_geometry_and_texture(tmp_path):
    test_gunparts.build_install(tmp_path / "bl2")
    ix = Index(tmp_path / "bl2")
    src = gunparts.Bl2Source(ix, lambda m: None)
    rep = modelsurvey.inspect_part(ix, src, "GD_Weap_Pistol.Body.Pistol_Body_A")
    assert rep["mesh_class"] == "StaticMesh" and "24 vertices" in rep["geometry"] and rep["textures"][0]["diffuse_decoded"] is True
    assert rep["sockets"].get("barrel") == (45.0, 0.0, 3.0) or rep["sockets"].get("barrel") == [45.0, 0.0, 3.0]
    json.dumps(rep, default=str)
    missing = modelsurvey.inspect_part(ix, src, "GD_Weap_Pistol.Nothing.Missing")
    assert missing["mesh_path"] is None


def test_character_survey_lists_skeletal_mesh_packages(tmp_path):
    import fake_bl2

    cooked = tmp_path / "bl2" / "WillowGame" / "CookedPCConsole"
    cooked.mkdir(parents=True)
    b = fake_bl2.ObjBuilder()
    b.obj("Char_Psycho.Mesh.Psycho_Body", "SkeletalMesh", b"")
    b.obj("Char_Psycho.Anim.Psycho_Anims", "AnimSet", b"")
    (cooked / "Char_Psycho.upk").write_bytes(b.build())
    ix = Index(tmp_path / "bl2")
    rows = modelsurvey.character_survey(ix)
    assert rows and rows[0]["SkeletalMesh"]["sample"] == ["Char_Psycho.Mesh.Psycho_Body"] and rows[0]["AnimSet"]["count"] == 1


def test_part_name_dump_lists_where_each_mesh_name_lives(tmp_path):
    test_gunparts.build_install(tmp_path / "bl2")
    ix = Index(tmp_path / "bl2")
    src = gunparts.Bl2Source(ix, lambda m: None)
    by_slot = {"Body": ["GD_Weap_Pistol.Body.Pistol_Body_A"], "Barrel": ["GD_Weap_Pistol.Barrel.Pistol_Barrel_A"]}
    src.prepare([p for ps in by_slot.values() for p in ps])
    dump = modelsurvey.part_name_dump(ix, src, by_slot)
    json.dumps(dump, default=str)
    assert {r["part"] for r in dump["parts"]} == {p for ps in by_slot.values() for p in ps}
    assert any(h.get("class") in ("StaticMesh", "SkeletalMesh") for hs in dump["where_found"].values() for h in hs)


def test_shooting_survey_follows_references_between_objects(tmp_path):
    from skylands_setup import shootingsurvey

    test_gunparts.build_install(tmp_path / "bl2")
    ix = Index(tmp_path / "bl2")
    rep = shootingsurvey.crawl(ix, ["GD_Weap_Pistol.Barrel.Pistol_Barrel_A"], lambda m: None)
    json.dumps(rep, default=str)
    assert "GD_Weap_Pistol.Barrel.Pistol_Barrel_A" in rep["objects"]
    assert rep["class_counts"].get("WeaponPartDefinition", 0) >= 1
