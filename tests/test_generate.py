import struct
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_bl2  # noqa: E402
import fake_skyrim  # noqa: E402
from skylands_setup import generate  # noqa: E402
from skylands_setup.bl2 import extract  # noqa: E402
from skylands_setup.skyrim.esm import read_plugin  # noqa: E402


def test_generate_from_both_games(tmp_path):
    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    bl2["enemies"]["b_enemy_nomad"] = "Nomad"
    bl2["enemies"]["b_enemy_nomad_badass"] = "Badass Nomad"
    sky = fake_skyrim.build_full(tmp_path / "sky")
    out = tmp_path / "out"
    rep = generate.generate(bl2, sky, out)
    data = out / "Data"
    assert (data / "Scripts" / "SkylandsClassQuest.pex").is_file() and (data / "Scripts" / "SkylandsLootBeam.pex").is_file()
    assert (data / "Meshes" / "Skylands" / "Beam_legendary.nif").is_file() and (data / "Textures" / "Skylands" / "beam.dds").is_file()
    tes4, recs = read_plugin(data / "Skylands.esp", {"WEAP", "ENCH", "MGEF", "LVLI", "SHOU", "WOOP", "SPEL", "MESG", "QUST", "NPC_", "ACTI"})
    names = {r.edid: r.first("FULL").rstrip(b"\0").decode() for r in recs["WEAP"]}
    assert names["Skylands_Pistol_Jakobs"] == "Jakobs Revolver (Common)"
    assert names["Skylands_Pistol_Jakobs_3_Rare_Fire"] == "Incendiary Revolver (Rare)"
    assert names["Skylands_Pistol_Jakobs_5_Maggie"] == "Sledge's Maggie (Legendary)"
    fire = next(r for r in recs["WEAP"] if r.edid == "Skylands_Pistol_Jakobs_3_Rare_Fire")
    sigs = [s for s, _ in fire.subrecords]
    assert sigs.index("VMAD") < sigs.index("OBND") < sigs.index("FULL") < sigs.index("MODL") < sigs.index("EITM") < sigs.index("ETYP")
    assert "DESC" not in sigs and "EITM" in sigs
    ench = next(r for r in recs["ENCH"] if r.form_id == struct.unpack_from("<I", fire.first("EITM"))[0])
    st = rep["stats"]["Skylands_Pistol_Jakobs_3_Rare_Fire"]
    assert ench.edid == "Skylands_Ench_Skylands_Pistol_Jakobs_3_Rare_Fire" and ench.first("FULL") == b"Gun stats\0"
    efits = [struct.unpack("<fII", d) for d in ench.all("EFIT")]
    assert len(efits) == 2 and efits[0][0] == pytest.approx(10.0 * st["element_mult"], abs=0.01) and efits[1][0] == 0.0
    mg = next(r for r in recs["MGEF"] if r.form_id == struct.unpack_from("<I", ench.all("EFID")[1])[0])
    assert mg.first("DNAM").decode().startswith(f"Fire rate {st['fire_rate']:.1f}/s, Reload {st['reload']:.1f}s")
    assert struct.unpack_from("<i", mg.first("DATA"), 68)[0] == 77
    assert struct.unpack_from("<f", fire.first("DNAM"), 4)[0] == pytest.approx(st["speed"], abs=1e-3)
    assert struct.unpack_from("<H", fire.first("CRDT"))[0] == st["crit_damage"]
    plain = next(r for r in recs["WEAP"] if r.edid == "Skylands_Pistol_Jakobs")
    pe = next(r for r in recs["ENCH"] if r.form_id == struct.unpack_from("<I", plain.first("EITM"))[0])
    assert len(pe.all("EFIT")) == 1  # a non-elemental gun still lists its stats
    value, weight, dmg = struct.unpack_from("<IfH", fire.first("DATA"))
    assert dmg == round(12 * 1.3) and value == 150
    assert fire.form_id >> 24 == 3 and fire.first("MODL").startswith(b"dlc01")
    loot = next(r for r in recs["LVLI"] if r.edid == "LootBanditWeapon15")
    assert loot.form_id == 0x8000 and loot.first("LLCT") == b"\x09" and len(loot.all("LVLO")) == 9  # built on Update.esm's version
    assert len(recs["SHOU"]) == 5 and {r.edid for r in recs["WOOP"]} >= {"SkylandsWord_assassin", "SkylandsWord_mechromancer"}
    zer0 = next(r for r in recs["SHOU"] if r.edid == "SkylandsShout_assassin")
    word, spell_id, recharge = struct.unpack("<IIf", zer0.all("SNAM")[0])
    assert recharge == 15.0
    sp = next(r for r in recs["SPEL"] if r.form_id == spell_id)
    assert struct.unpack_from("<I", sp.first("ETYP"))[0] == 0x25BEE and struct.unpack_from("<I", sp.first("SPIT"), 20)[0] == 0
    assert struct.unpack("<fII", sp.first("EFIT")) == (0.0, 0, 6)
    msg = recs["MESG"][0]
    assert [d.rstrip(b"\0").decode() for d in msg.all("ITXT")][0] == "Zer0: Zer0 skill"
    npcs = {r.edid: r for r in recs["NPC_"]}
    assert npcs["EncBandit02TemplateMelee"].first("FULL") == b"Nomad\0" and "SHRT" not in [s for s, _ in npcs["EncBandit02TemplateMelee"].subrecords]
    assert struct.unpack("<I", npcs["EncBandit02TemplateMelee"].first("SPCT"))[0] == 2
    assert npcs["EncBandit03Boss1HNordM"].first("FULL") == b"Badass Nomad\0"
    assert "EncBandit02Melee1HNordM" not in npcs  # unnamed records keep inheriting from their template
    assert rep["guns"] == 6 and rep["renamed_enemies"] == 2 and rep["missing_classes"] == ["psycho"]


def test_build_installs_and_enables(tmp_path, monkeypatch):
    from skylands_setup import build

    fake_bl2.pandora_install(tmp_path / "bl2")
    sky = fake_skyrim.build_full(tmp_path / "sky")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    plugins = tmp_path / "appdata" / "Skyrim Special Edition" / "plugins.txt"
    plugins.parent.mkdir(parents=True)
    plugins.write_text("# keep me\n*Unofficial Patch.esp\n")
    done = tmp_path / "managed" / "setup-done.txt"
    assert build.main(["--bl2", str(tmp_path / "bl2"), "--skyrim", str(sky), "--done", str(done)]) == 0
    assert done.read_text().startswith(f"ok {build.VERSION}")
    assert (sky / "Data" / "Skylands.esp").is_file() and (sky / "Data" / "Scripts" / "SkylandsLootBeam.pex").is_file()
    assert plugins.read_text().splitlines() == ["# keep me", "*Unofficial Patch.esp", "*Skylands.esp"]
    assert build.main(["--bl2", str(tmp_path / "bl2"), "--skyrim", str(sky), "--done", str(done)]) == 0
    assert plugins.read_text().count("Skylands.esp") == 1
    assert build.main(["--bl2", str(tmp_path / "nope"), "--skyrim", str(sky), "--done", str(done)]) == 2
    assert not done.exists()


def test_uninstall_removes_only_what_was_installed(tmp_path, monkeypatch):
    from skylands_setup import build

    fake_bl2.pandora_install(tmp_path / "bl2")
    sky = fake_skyrim.build_full(tmp_path / "sky")
    (sky / "Data" / "Other.esp").write_bytes(b"keep me")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    plugins = tmp_path / "appdata" / "Skyrim Special Edition" / "plugins.txt"
    plugins.parent.mkdir(parents=True)
    plugins.write_text("*Unofficial Patch.esp\n")
    done = tmp_path / "work" / "setup-done.txt"
    assert build.main(["--bl2", str(tmp_path / "bl2"), "--skyrim", str(sky), "--done", str(done)]) == 0
    assert (plugins.parent / "plugins.txt.skylands-backup").read_text() == "*Unofficial Patch.esp\n"
    assert build.uninstall_main(["--work", str(done.parent)]) == 0
    assert not (sky / "Data" / "Skylands.esp").exists() and not (sky / "Data" / "Scripts" / "SkylandsLootBeam.pex").exists()
    assert not (sky / "Data" / "Meshes" / "Skylands").exists()
    assert (sky / "Data" / "Other.esp").read_bytes() == b"keep me" and (sky / "Data" / "Skyrim.esm").exists()
    assert plugins.read_text().splitlines() == ["*Unofficial Patch.esp"]
    assert not done.exists()
    assert build.uninstall_main(["--work", str(done.parent)]) == 0  # nothing left to do


def test_generated_plugin_is_accepted_by_esplugin(tmp_path):
    """Set ESPCHECK to tools/espcheck's binary: an independent parser must accept the plugin as a valid light plugin."""
    import os
    import subprocess

    import pytest

    exe = os.environ.get("ESPCHECK")
    if not exe:
        pytest.skip("set ESPCHECK to the esplugin checker")
    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", None)
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    bl2["enemies"]["b_enemy_nomad"] = "Nomad"
    bl2["enemies"]["b_enemy_nomad_badass"] = "Badass Nomad"
    sky = fake_skyrim.build_full(tmp_path / "sky")
    generate.generate(bl2, sky, tmp_path / "out")
    r = subprocess.run([exe, str(tmp_path / "out" / "Data" / "Skylands.esp")], capture_output=True, text=True)
    assert r.returncode == 0 and "parsed OK" in r.stdout and "is_valid_as_light_plugin: Ok(true)" in r.stdout, r.stdout + r.stderr
