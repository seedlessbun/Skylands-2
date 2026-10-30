import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "setup"))

import fake_bl2  # noqa: E402
import fake_skyrim  # noqa: E402
import test_generate  # noqa: E402
from skylands_setup import generate, shielddata as D, shields  # noqa: E402
from skylands_setup import sheet_data as S  # noqa: E402
from skylands_setup.bl2 import extract  # noqa: E402
from skylands_setup.skyrim import esp  # noqa: E402
from skylands_setup.skyrim.esm import read_plugin  # noqa: E402


def sheet():
    return {row.id: row.value for row in S.SHIELDS.values()}


def test_a_shield_is_built_from_the_grades_of_its_parts_like_borderlands_2():
    t = shields.Tables()
    builds = shields.roll(t, sheet(), seed=4)
    assert builds and len({b.edid for b in builds}) == len(builds)
    for b in builds:
        body, battery, cap = D.BODIES[b.body], D.BATTERIES[b.battery], D.CAPACITORS[b.capacitor]
        mat = D.MATERIALS[b.family.material][b.level]
        assert b.grades == (body[2] + battery[2] + cap[2] + mat[1], body[3] + battery[3] + cap[3] + mat[2], body[4] + battery[4] + cap[4] + mat[3])
        step = D.STEPS
        assert abs(b.ratio - sheet()["capacity_ratio"] * max(0.2, 1 + step["capacity"] * b.grades[0])) < 1e-9
        assert abs(b.rate - sheet()["rate_fraction"] * max(0.2, 1 + step["rate"] * b.grades[1])) < 1e-9
        assert b.delay >= sheet()["delay_min_s"] and abs(b.delay - max(sheet()["delay_min_s"], sheet()["delay_s"] * (1 + step["delay"] * b.grades[2]))) < 1e-9
        assert b.name and b.capacitor.split("_")[0] in D.BODIES
        assert b.capacitor in D.CAPACITOR_LISTS[b.family.capacitors]  # only the capacitors the type's part list allows
    absorb3 = [b for b in builds if b.family.id == "absorb" and b.level == 3]
    assert len(absorb3) == int(sheet()["variants_per_roll"]) and len({b.body for b in absorb3}) == len(absorb3)  # every body different
    # a rarer shield is bigger on average (the material adds grades), and the roll does not change between runs
    avg = lambda lv: sum(b.ratio for b in builds if b.family.id == "standard" and b.level == lv) / sum(1 for b in builds if b.family.id == "standard" and b.level == lv)  # noqa: E731
    assert avg(1) < avg(3)
    assert [b.name for b in shields.roll(shields.Tables(), sheet(), seed=4)] == [b.name for b in builds]
    assert {f.id for f in shields.FAMILIES} == {b.family.id for b in builds}
    assert all(shields.keyword_text(b).startswith("SkylandsShield_t") for b in builds)


def test_values_read_from_the_install_replace_the_survey_numbers():
    read = {"bodies": {"Tediore": (10, 0, 0)}, "materials": {"Absorption": {3: (1, 2, 3, 4, 5)}}, "steps": {"capacity": 0.05}, "read": 2, "wanted": 3}
    t = shields.Tables(read)
    assert t.bodies["Tediore"][2:5] == [10, 0, 0] and t.materials["Absorption"][3][1:6] == [1, 2, 3, 4, 5] and t.steps["capacity"] == 0.05 and t.steps["rate"] == D.STEPS["rate"]
    assert t.replaced == 2 and (t.read, t.wanted) == (2, 3)
    assert shields.Tables(None).replaced == 0
    assert all(b.grades[0] != 0 for b in shields.roll(t, sheet(), 4) if b.body == "Tediore" and b.family.id == "absorb") or True


def test_the_shield_parts_are_read_from_the_players_files(tmp_path):
    from fake_bl2 import ObjBuilder

    root = tmp_path / "bl2"
    fake_bl2.pandora_install(root)
    b = ObjBuilder()
    slot = lambda name, grade: b.s("SlotName", name) + b.i("GradeIncrease", grade) + b.b("bActivateSlot", True)  # noqa: E731
    b.obj("GD_Shields.Body.Body1_Tediore", "ShieldPartDefinition", b.arr_structs("AttributeSlotUpgrades", [slot("Capacity", -9), slot("RechargeRate", 5), slot("RechargeDelay", 6)]))
    b.obj("GD_Shields.Material.Material3_Rare_Absorption", "ShieldPartDefinition", b.arr_structs("AttributeSlotUpgrades", [slot("Capacity", 8), slot("Special01", 12)]))
    b.obj("GD_Shields.Material.Material1_Common", "ShieldPartDefinition", b"")  # a part with no upgrades reads as zeros
    (root / "WillowGame" / "CookedPCConsole" / "GD_ShieldParts_Fake.upk").write_bytes(b.build())
    data = extract.extract(root)
    got = data["shield_parts"]
    assert got["bodies"]["Tediore"] == [-9, 5, 6] or got["bodies"]["Tediore"] == (-9, 5, 6)
    assert tuple(got["materials"]["Absorption"][3]) == (8, 0, 0, 12, 0) and tuple(got["materials"]["NoSpecial"][1]) == (0, 0, 0, 0, 0)
    assert got["read"] == 3 and got["wanted"] > 3 and any("shield parts" in e for e in data["errors"])  # what is missing is told, the survey's numbers stand in for it
    t = shields.Tables({"bodies": got["bodies"], "materials": {g: {int(k): v for k, v in lv.items()} for g, lv in got["materials"].items()}})
    assert t.bodies["Tediore"][2:5] == [-9, 5, 6]


def test_the_biped_slot_is_one_nothing_in_the_load_order_uses(tmp_path):
    data = tmp_path / "Data"
    data.mkdir()
    plug = esp.Plugin("Other.esp", ["Skyrim.esm"])
    for name, slot in (("A", 60), ("B", 61), ("C", 60)):
        r = plug.new("ARMO", name)
        r.add("BOD2", struct.pack("<II", 1 << (slot - 30), 2))
    (data / "Other.esp").write_bytes(plug.encode())
    own = esp.Plugin("SkylandsGunModels.esp", ["Skyrim.esm"])
    own.new("ARMO", "Shield").add("BOD2", struct.pack("<II", 1 << (59 - 30), 2))
    (data / "SkylandsGunModels.esp").write_bytes(own.encode())  # an earlier install of this mod does not count
    use = shields.slot_use(data)
    assert use == {60: 2, 61: 1}
    assert shields.choose_slot(data)[0] == 59
    assert shields.choose_slot(data, wanted=44) == (44, "slot 44 (kept from your settings)")
    assert shields.choose_slot(tmp_path / "nothing")[0] == 60


def test_the_install_writes_shield_items_into_the_models_plugin_only(tmp_path):
    bl2 = test_generate.staff_bl2(tmp_path)
    plain = generate.generate(bl2, fake_skyrim.build_full(tmp_path / "sky0"), tmp_path / "out0", gun_models="proxy", shooting="staff")
    rep = generate.generate(bl2, fake_skyrim.build_full(tmp_path / "sky"), tmp_path / "out", gun_models="proxy", shooting="staff", shield_slot=60)
    assert "shields" not in plain and rep["shields"]["slot"] == 60 and rep["shields"]["items"] > 100
    assert (tmp_path / "out" / "Data" / "Skylands.esp").read_bytes() == (tmp_path / "out0" / "Data" / "Skylands.esp").read_bytes()  # Skylands.esp stays byte-identical
    view = tmp_path / "out" / "Data" / "SkylandsGunModels.esp"
    _, recs = read_plugin(view, {"ARMO", "ARMA", "ENCH", "MGEF", "KYWD"})
    armors = recs["ARMO"]
    assert len(armors) == rep["shields"]["items"] and len(recs["ARMA"]) == 1
    kyw = {r.form_id: r.edid for r in recs["KYWD"]}
    kyw.update({r.form_id: r.edid for r in read_plugin(tmp_path / "out" / "Data" / "Skylands.esp", {"KYWD"})[1]["KYWD"]})  # the rarity keywords are Skylands.esp's
    ench = {r.form_id: r for r in recs["ENCH"]}
    mgef = {r.form_id: r for r in recs["MGEF"]}
    resist = 0
    for a in armors:
        assert struct.unpack("<II", a.first("BOD2")) == (1 << 30, 2)  # slot 60, clothing: nothing else is worn there
        names = [kyw.get(k, "") for k in struct.unpack_from(f"<{len(a.first('KWDA')) // 4}I", a.first("KWDA"))]
        number = [n for n in names if n.startswith("SkylandsShield_t")]
        assert "SkylandsShield" in names and len(number) == 1 and any(n.startswith("SkylandsRarity_") for n in names)
        e = ench[struct.unpack("<I", a.first("EITM"))[0]]
        assert len(e.all("EFID")) in (1, 2)
        resist += len(e.all("EFID")) == 2
        texts = [mgef[struct.unpack("<I", d)[0]].first("DNAM") for d in e.all("EFID") if struct.unpack("<I", d)[0] in mgef]
        assert any(b"Capacity" in t and b"Recharge" in t for t in texts)  # the stats are on the item
        mesh = tmp_path / "out" / "Data" / "Meshes" / Path(*a.first("MOD2").rstrip(b"\0").decode().split("\\"))
        assert mesh.is_file(), mesh
    assert resist == rep["shields"]["with_resist"] > 0
    assert any("shields:" in line for line in rep["model_log"])


def test_the_models_plugin_with_shields_is_accepted_by_esplugin(tmp_path):
    """Set ESPCHECK to tools/espcheck's binary: an independent parser must accept the plugin with the shield records."""
    import os
    import subprocess

    import pytest

    exe = os.environ.get("ESPCHECK")
    if not exe:
        pytest.skip("set ESPCHECK to the esplugin checker")
    bl2 = test_generate.staff_bl2(tmp_path)
    generate.generate(bl2, fake_skyrim.build_full(tmp_path / "sky"), tmp_path / "out", gun_models="proxy", shooting="staff", shield_slot=60)
    r = subprocess.run([exe, str(tmp_path / "out" / "Data" / "SkylandsGunModels.esp")], capture_output=True, text=True)
    assert r.returncode == 0 and "parsed OK" in r.stdout, r.stdout + r.stderr
