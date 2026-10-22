import math
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
    assert (data / "Scripts" / "SkylandsHunterQuest.pex").is_file() and (data / "Scripts" / "SkylandsHunter.pex").is_file() and (data / "Scripts" / "SkylandsHunterPower.pex").is_file()
    assert (data / "Meshes" / "Skylands" / "Beam_legendary.nif").is_file() and (data / "Textures" / "Skylands" / "beam.dds").is_file()
    tes4, recs = read_plugin(data / "Skylands.esp", {"WEAP", "KYWD", "ENCH", "MGEF", "LVLI", "SHOU", "WOOP", "SPEL", "MESG", "QUST", "NPC_", "STAT", "LIGH", "RACE", "FLST"})
    names = {r.edid: r.first("FULL").rstrip(b"\0").decode() for r in recs["WEAP"]}
    assert len(names) == rep["guns"] == 9  # 3 common + 4 rare + 2 legendary variants
    assert names["Skylands_Pistol_Jakobs_5_Maggie_1"] == "Sledge's Maggie (Legendary)"
    rare_ids = sorted(e for e in names if e.startswith("Skylands_Pistol_Jakobs_3_Rare_"))
    assert len(rare_ids) == 4 and {names[e] for e in rare_ids} == {"Incendiary Revolver (Rare)"}
    assert {rep["stats"][e]["parts"]["Barrel"].rsplit("_", 1)[-1] for e in rare_ids} == {"Heavy", "Quick"}  # different parts, different guns
    fire = next(r for r in recs["WEAP"] if r.edid == rare_ids[0])
    sigs = [s for s, _ in fire.subrecords]
    assert "VMAD" not in sigs and sigs.index("OBND") < sigs.index("FULL") < sigs.index("MODL") < sigs.index("EITM") < sigs.index("ETYP")
    assert "DESC" not in sigs and "EITM" in sigs
    ench = next(r for r in recs["ENCH"] if r.form_id == struct.unpack_from("<I", fire.first("EITM"))[0])
    st = rep["stats"][rare_ids[0]]
    half = math.sqrt(st["speed"])
    assert ench.edid == f"Skylands_Ench_{rare_ids[0]}" and ench.first("FULL") == b"Gun stats\0"
    efits = [struct.unpack("<fII", d) for d in ench.all("EFIT")]
    assert len(efits) == 2 and efits[0][0] == pytest.approx(10.0 * st["element_mult"], abs=0.01)
    assert efits[1][0] == 0.0  # the stats effect only displays text
    mg = next(r for r in recs["MGEF"] if r.form_id == struct.unpack_from("<I", ench.all("EFID")[1])[0])
    text = mg.first("DNAM").decode()
    assert text.startswith(f"Jakobs. Fire rate {st['fire_rate']:.1f}/s, Reload {st['reload']:.1f}s") and "Parts: Barrel" in text
    assert struct.unpack_from("<i", mg.first("DATA"), 68)[0] == 77
    assert struct.unpack_from("<f", fire.first("DNAM"), 4)[0] == pytest.approx(half, abs=1e-3)  # half of the speed is the gun's own
    kws = struct.unpack(f"<{len(fire.first('KWDA')) // 4}I", fire.first("KWDA"))
    kyw = {r.form_id: r.edid for r in recs["KYWD"]}
    assert struct.unpack("<I", fire.first("KSIZ"))[0] == len(kws) and [kyw[k] for k in kws if k in kyw] == ["SkylandsGun", "SkylandsRarity_rare", f"SkylandsSpeed_{round((half - 0.5) / 0.05)}"]
    beam = next(r for r in recs["STAT"] if r.edid == "SkylandsBeam_rare")  # a plain static: no script that could fail to attach
    assert beam.first("MODL") == b"Skylands\\Beam_rare.nif\0" and "VMAD" not in [sg for sg, _ in beam.subrecords]
    lights = {r.edid: r for r in recs["LIGH"]}
    assert len(lights) == 6 and lights["SkylandsLight_common"].first("DATA")[8:12] == bytes([40, 100, 50, 0])
    assert struct.unpack_from("<I", lights["SkylandsLight_rare"].first("DATA"), 4)[0] == generate.LIGHT_RADIUS and "MODL" not in [s for s, _ in lights["SkylandsLight_rare"].subrecords]
    quest = next(r for r in recs["QUST"] if r.edid == "SkylandsPandoraQuest")
    for prop in (b"ClassChoice", b"Shouts", b"Words", b"StarterGun", b"StarterAmmo"):
        assert prop in quest.first("VMAD")
    for prop in (b"RarityKeywords", b"Beams", b"Lights", b"PromptMsg", b"RespawnPower", b"LogPower", b"NpcKeyword"):
        assert prop not in quest.first("VMAD")  # a saved game would keep stale values; the player's watcher hands these over
    power = next(r for r in recs["SPEL"] if r.edid == "SkylandsPandoraRespawnPower")
    assert struct.unpack_from("<I", power.first("SPIT"), 8)[0] == 3  # a lesser power
    power_fx = next(r for r in recs["MGEF"] if r.edid == "SkylandsPandoraRespawnEffect")
    assert b"SkylandsHunterPower" in power_fx.first("VMAD") and struct.unpack_from("<I", power_fx.first("DATA"), 80)[0] == 1
    logger = next(r for r in recs["SPEL"] if r.edid == "SkylandsPandoraLogPower")
    assert struct.unpack_from("<I", logger.first("SPIT"), 8)[0] == 3
    log_fx = next(r for r in recs["MGEF"] if r.edid == "SkylandsPandoraLogEffect")
    assert b"SkylandsHunterPower" in log_fx.first("VMAD") and b"Action" in log_fx.first("VMAD")
    boxes = {r.edid: [d.rstrip(b"\0").decode() for d in r.all("ITXT")] for r in recs["MESG"]}
    assert boxes["SkylandsRespawnPrompt"][0] == "Respawn enemies here" and len(boxes["SkylandsRespawnSettings"]) == 5
    # the watcher: an ability whose effect runs the script, carried by every humanoid race
    watch_fx = next(r for r in recs["MGEF"] if r.edid == "SkylandsWatcherFx")
    for prop in (b"SkylandsHunter", b"Owner", b"GunKeyword", b"SpeedKeywords", b"GunList", b"GunDrop", b"NpcKeyword", b"Bolts",
                 b"ArmChance", b"DropChance", b"GoodLevel", b"ScanRadius", b"RarityKeywords", b"Beams", b"Lights", b"PromptMsg",
                 b"SettingsMsg", b"MarkerForm", b"RespawnPower", b"LogPower", b"Ability"):
        assert prop in watch_fx.first("VMAD")
    assert struct.unpack_from("<I", watch_fx.first("DATA"), 64)[0] == generate.MGEF_ARCHETYPE_SCRIPT
    ability = next(r for r in recs["SPEL"] if r.edid == "SkylandsPandoraAbility")
    assert struct.unpack_from("<I", ability.first("SPIT"), 8)[0] == 4 and struct.unpack_from("<I", ability.first("EFID"))[0] == watch_fx.form_id
    races = {r.edid: r for r in recs["RACE"]}
    assert set(races) == {"NordRace", "BretonRace", "NordRaceVampire"} and rep["watched_races"] == 3  # not the Dremora
    nord = races["NordRace"]
    assert nord.first("FULL") == b"Nord\0" and nord.first("DESC").endswith(b"\0") and len(nord.first("DESC")) > 4  # names written out, not string ids
    spells = [struct.unpack("<I", d)[0] for d in nord.all("SPLO")]
    assert power.form_id not in spells and logger.form_id not in spells  # the ability script grants the powers, not the race
    assert ability.form_id in spells and struct.unpack("<I", nord.first("SPCT"))[0] == len(spells)
    guns = next(r for r in recs["FLST"] if r.edid == "SkylandsGunList")
    assert len(guns.all("LNAM")) == rep["guns"]
    speeds = [r for r in recs["KYWD"] if r.edid.startswith("SkylandsSpeed_")]
    assert len(speeds) == 48
    assert struct.unpack_from("<H", fire.first("CRDT"))[0] == st["crit_damage"]
    value, weight, dmg = struct.unpack_from("<IfH", fire.first("DATA"))
    assert dmg == round(12 * 1.3 * st["damage_mult"]) and value == 150
    assert fire.form_id >> 24 == 3 and fire.first("MODL").startswith(b"dlc01")
    loot = next(r for r in recs["LVLI"] if r.edid == "LootBanditChestBossBase")
    assert loot.form_id == 0x8000 and loot.first("LLCT") == b"\x06" and len(loot.all("LVLO")) == 6  # 2 (Update.esm's version) + 3 gun lists + ammo
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
    assert rep["renamed_enemies"] == 2 and rep["missing_classes"] == ["psycho"]


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
    assert (sky / "Data" / "Skylands.esp").is_file() and (sky / "Data" / "Scripts" / "SkylandsHunter.pex").is_file()
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
    assert not (sky / "Data" / "Skylands.esp").exists() and not (sky / "Data" / "Scripts" / "SkylandsHunter.pex").exists()
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


def test_form_ids_stay_the_same_between_builds(tmp_path):
    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    sky = fake_skyrim.build_full(tmp_path / "sky")
    ids: dict[str, int] = {}
    generate.generate(bl2, sky, tmp_path / "one", formids=ids)
    first = dict(ids)
    assert len(first) > 100 and len(set(first.values())) == len(first)
    # a different set of guns (the first balance gone): everything that is still there keeps its id
    bl2["weapons"]["guns"] = bl2["weapons"]["guns"][1:]
    generate.generate(bl2, sky, tmp_path / "two", formids=ids)
    for key, fid in first.items():
        assert ids[key] == fid
    # and an unchanged rebuild is byte for byte the same plugin
    again = dict(first)
    generate.generate(bl2, sky, tmp_path / "three", formids=again)
    assert again == ids or all(again[k] == v for k, v in first.items())


def test_build_learns_ids_from_the_installed_plugin(tmp_path, monkeypatch):
    from skylands_setup import build

    fake_bl2.pandora_install(tmp_path / "bl2")
    sky = fake_skyrim.build_full(tmp_path / "sky")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    done = tmp_path / "managed" / "setup-done.txt"
    args = ["--bl2", str(tmp_path / "bl2"), "--skyrim", str(sky), "--done", str(done)]
    assert build.main(args) == 0
    installed = {f"{r.type}:{r.edid}": r.form_id for rs in read_plugin(sky / "Data" / "Skylands.esp", build.RECORD_TYPES)[1].values()
                 for r in rs if r.edid and r.form_id >> 24 == 3}
    # lose the saved registry (a reinstall): the installed plugin still tells the build which ids to keep
    (tmp_path / "managed" / "formids.json").unlink()
    assert build.main(args) == 0
    again = {f"{r.type}:{r.edid}": r.form_id for rs in read_plugin(sky / "Data" / "Skylands.esp", build.RECORD_TYPES)[1].values()
             for r in rs if r.edid and r.form_id >> 24 == 3}
    assert again == installed and len(installed) > 100


def test_proxy_gun_models(tmp_path):
    import os
    import subprocess

    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    sky = fake_skyrim.build_full(tmp_path / "sky")
    out = tmp_path / "out"
    rep = generate.generate(bl2, sky, out, gun_models="proxy")
    data = out / "Data"
    base_bytes = (data / "Skylands.esp").read_bytes()
    plain = tmp_path / "plain"
    generate.generate(bl2, sky, plain)
    assert base_bytes == (plain / "Data" / "Skylands.esp").read_bytes()  # Skylands.esp never changes, so it stays light
    assert int.from_bytes(base_bytes[8:12], "little") & 0x200 and not (plain / "Data" / "SkylandsGunModels.esp").exists()
    tes, recs = read_plugin(data / "SkylandsGunModels.esp", {"WEAP", "STAT"})
    assert b"Skylands.esp" in (data / "SkylandsGunModels.esp").read_bytes()[:400] and recs["STAT"]
    assert all(r.first("WNAM") for r in recs["WEAP"])
    meshes = {r.first("MODL").rstrip(b"\0").decode() for r in recs["WEAP"]}
    assert all(m.startswith("Skylands\\Guns\\proxy_") for m in meshes), meshes
    for m in meshes:
        assert (data / "Meshes" / Path(*m.split("\\"))).is_file()
    assert all("MODT" not in [s for s, _ in r.subrecords] for r in recs["WEAP"])
    assert rep["gun_models"]["built"] >= 1 and rep["gun_models"]["failed"] == 0
    assert any((data / "Textures" / "Skylands" / "Guns").glob("c_*.dds")) and (data / "Textures" / "Skylands" / "Guns" / "flat_n.dds").is_file()
    exe = os.environ.get("NIFCHECK")
    if exe:
        for m in meshes:
            r = subprocess.run([exe, str(data / "Meshes" / Path(*m.split("\\")))], capture_output=True, text=True, check=True)
            assert "shape SkylandsGun0" in r.stdout


def test_gun_models_off_keeps_the_crossbow(tmp_path):
    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    sky = fake_skyrim.build_full(tmp_path / "sky")
    generate.generate(bl2, sky, tmp_path / "out")
    tes, recs = read_plugin(tmp_path / "out" / "Data" / "Skylands.esp", {"WEAP"})
    assert all(r.first("MODL").startswith(b"dlc01") for r in recs["WEAP"])
    assert not (tmp_path / "out" / "Data" / "Meshes" / "Skylands" / "Guns").exists()


def test_native_gun_models_with_a_source_and_fallbacks(tmp_path):
    from skylands_setup import meshes as M

    class Source:
        def gun_parts(self, g, built):
            if g["type"] != "pistol":
                return None
            body = M.box(0, 0, 0, 0.1, 1.0, 0.2)
            body.texture = "t_deadbeef"
            return [body, M.cylinder(0, 0.7, 0, 0.03, 0.5, sides=12)]

        def take_textures(self):
            return {"t_deadbeef": nif_dds()}

    def nif_dds():
        from skylands_setup.skyrim import dxt

        return dxt.encode(16, 16, bytes([90, 90, 90] * 256))

    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    sky = fake_skyrim.build_full(tmp_path / "sky")
    rep = generate.generate(bl2, sky, tmp_path / "out", gun_models="auto", model_sources={"native": Source()})
    tes, recs = read_plugin(tmp_path / "out" / "Data" / "SkylandsGunModels.esp", {"WEAP"})
    paths = {r.first("MODL").rstrip(b"\0").decode() for r in recs["WEAP"]}
    assert all(p.startswith("Skylands\\Guns\\native_") for p in paths), paths  # every fake gun is a pistol
    assert list((tmp_path / "out" / "Data" / "Textures" / "Skylands" / "Guns").glob("t_deadbeef_*.dds"))  # tinted per manufacturer
    assert rep["gun_models"]["by_method"] == {"native": rep["guns"]}


def test_gun_models_spin_and_scale(tmp_path):
    import subprocess

    from skylands_setup.skyrim import nifread

    def bounds(spin, scale):
        d = tmp_path / f"o{spin}_{scale}"
        fake_bl2.pandora_install(d / "bl2")
        bl2 = extract.extract(d / "bl2", d / "cache")
        bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
        sky = fake_skyrim.build_full(d / "sky")
        generate.generate(bl2, sky, d / "out", gun_models="proxy", model_spin=spin, model_scale=scale)
        f = next((d / "out" / "Data" / "Meshes" / "Skylands" / "Guns").glob("proxy_*.nif"))
        pts = nifread.world_points(f.read_bytes())
        return [max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)], pts

    e0, p0 = bounds(0, 1.0)
    e2, p2 = bounds(0, 2.0)
    assert all(abs(b - 2 * a) < 1e-3 * max(1, b) for a, b in zip(e0, e2))
    e90, p90 = bounds(90, 1.0)
    assert len(p90) == len(p0) and p90 != p0  # turned, not changed in size
    assert abs(sum(e90) - sum(e0)) < 1.0


def test_gun_models_follow_the_vanilla_crossbow_axes(tmp_path):
    from skylands_setup import meshes as M
    from skylands_setup.skyrim import nif, nifread

    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    sky = fake_skyrim.build_full(tmp_path / "sky")
    # a vanilla crossbow lying along +x (60 long), thin in z, wider in y, grip at the origin
    vanilla = nif.gun([(M.box(30, 0, 0, 60, 12, 4), None, None)])
    loose = sky / "Data" / "Meshes" / "dlc01" / "weapons" / "crossbow"
    loose.mkdir(parents=True)
    (loose / "crossbow.nif").write_bytes(vanilla)
    from skylands_setup import models as models_mod

    # cancel the built-in hold correction so the barrel axis can be compared with the vanilla one directly
    rep = generate.generate(bl2, sky, tmp_path / "out", gun_models="proxy", model_pitch=-models_mod.HOLD_PITCH, model_spin=-models_mod.HOLD_YAW)
    assert any("vanilla length 60.0 along axis x+" in line for line in rep["model_log"]), rep["model_log"]
    f = next((tmp_path / "out" / "Data" / "Meshes" / "Skylands" / "Guns").glob("proxy_*.nif"))
    pts = nifread.world_points(f.read_bytes())
    ext = [max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)]
    assert ext[0] == max(ext) and ext[0] > 5  # the barrel axis is x, as in the vanilla mesh
    assert sum(p[0] for p in pts) > 0  # and points the same way (forward = +x)


def test_gun_models_set_the_first_person_model_object(tmp_path):
    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    sky = fake_skyrim.build_full(tmp_path / "sky")
    generate.generate(bl2, sky, tmp_path / "out", gun_models="proxy")
    tes, recs = read_plugin(tmp_path / "out" / "Data" / "SkylandsGunModels.esp", {"WEAP", "STAT"})
    views = {r.form_id: r for r in recs["STAT"] if r.edid.startswith("SkylandsGunView_")}
    assert views
    for w in recs["WEAP"]:
        fp = views[struct.unpack("<I", w.first("WNAM"))[0]]
        assert fp.first("MODL") == w.first("MODL")  # first person and world model are the same mesh


def test_calibration_build_holds_each_rarity_differently(tmp_path):
    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    sky = fake_skyrim.build_full(tmp_path / "sky")
    rep = generate.generate(bl2, sky, tmp_path / "out", gun_models="proxy", model_calibrate=True)
    assert any("CALIBRATION" in line for line in rep["model_log"])
    plain = generate.generate(bl2, fake_skyrim.build_full(tmp_path / "sky2"), tmp_path / "out2", gun_models="proxy")
    cal = {f.name: f.read_bytes() for f in (tmp_path / "out" / "Data" / "Meshes" / "Skylands" / "Guns").glob("*.nif")}
    pla = {f.name: f.read_bytes() for f in (tmp_path / "out2" / "Data" / "Meshes" / "Skylands" / "Guns").glob("*.nif")}
    assert cal and set(cal) != set(pla)  # the calibration holds change the mesh files (their names include the hold)


def test_shooting_rounds_go_in_the_second_plugin(tmp_path):
    import struct as st

    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    generate.generate(bl2, fake_skyrim.build_full(tmp_path / "sky0"), tmp_path / "out0")
    rep = generate.generate(bl2, fake_skyrim.build_full(tmp_path / "sky"), tmp_path / "out", shooting="bl2")
    assert (tmp_path / "out" / "Data" / "Skylands.esp").read_bytes() == (tmp_path / "out0" / "Data" / "Skylands.esp").read_bytes()
    tes, recs = read_plugin(tmp_path / "out" / "Data" / "SkylandsGunModels.esp", {"AMMO", "PROJ", "EXPL", "KYWD", "WEAP"})
    ammo = sorted((r for r in recs["AMMO"] if r.edid.startswith("SkylandsRound_")), key=lambda r: r.form_id)
    assert len(ammo) == 30 and ammo[0].form_id & 0xFFFFFF == 0x800 and ammo[0].edid == "SkylandsRound_pistol_plain"
    kw = {r.form_id & 0xFFFFFF: r.edid for r in recs["KYWD"]}
    assert kw[0x81E] == "SkylandsShot_pistol" and kw[0x823] == "SkylandsShot_launcher" and kw[0x824] == "SkylandsShot_Fire" and kw[0x827] == "SkylandsShot_Slag"
    proj = {r.edid: r for r in recs["PROJ"]}
    pd = proj["SkylandsRound_launcher_Fire"].first("DATA")
    assert st.unpack_from("<H", pd)[0] & 0x2 and st.unpack_from("<I", pd, 36)[0] != 0  # explodes
    assert not st.unpack_from("<H", proj["SkylandsRound_pistol_plain"].first("DATA"))[0] & 0x2  # a plain bullet does not
    assert abs(st.unpack_from("<f", pd, 8)[0] - 3000 / 3) < 1
    for w in recs["WEAP"]:  # every gun says which rounds it uses
        ids = st.unpack(f"<{len(w.first('KWDA')) // 4}I", w.first("KWDA"))
        assert any(i & 0xFFFFFF in range(0x81E, 0x824) for i in ids)
    assert rep["rounds"]["ammo"] == 30
    # the player's gunner: quest -> ability -> script effect, all in the second plugin, with the numbers as properties
    tes, recs = read_plugin(tmp_path / "out" / "Data" / "SkylandsGunModels.esp", {"QUST", "SPEL", "MGEF"})
    assert any(r.edid == "SkylandsGunnerQuest" for r in recs["QUST"]) and any(r.edid == "SkylandsGunnerAbility" for r in recs["SPEL"])
    fx = next(r for r in recs["MGEF"] if r.edid == "SkylandsGunnerFx")
    vm = fx.first("VMAD")
    assert b"SkylandsGunner" in vm and b"Pellets" in vm and b"ReloadTime" in vm
    assert b"ProfileKeywords" in vm and b"ClipTens" in vm
    tes, kw = read_plugin(tmp_path / "out" / "Data" / "SkylandsGunModels.esp", {"KYWD", "WEAP"})
    names = {r.form_id: r.edid for r in kw["KYWD"]}
    assert "SkylandsProfile_pistol" in names.values() and "SkylandsClipUnits_9" in names.values()
    for w in kw["WEAP"]:  # each gun: a profile keyword and its magazine size
        mine = [names.get(i) for i in st.unpack(f"<{len(w.first('KWDA')) // 4}I", w.first("KWDA"))]
        assert any(n and n.startswith("SkylandsProfile_") for n in mine)
    assert (tmp_path / "out" / "Data" / "Scripts" / "SkylandsGunner.pex").is_file()
    assert not (tmp_path / "out0" / "Data" / "Scripts" / "SkylandsGunner.pex").exists()


def test_gun_mesh_length_follows_the_size_table(tmp_path):
    from skylands_setup import models as models_mod
    from skylands_setup.skyrim import nifread

    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    sky = fake_skyrim.build_full(tmp_path / "sky")
    for scale in (1.0, 1.5):  # a bigger --gun-scale must give bigger meshes
        out = tmp_path / f"out{scale}"
        generate.generate(bl2, fake_skyrim.build_full(tmp_path / f"sky{scale}"), out, gun_models="proxy", model_scale=scale, model_pitch=-models_mod.HOLD_PITCH)
        f = next((out / "Data" / "Meshes" / "Skylands" / "Guns").glob("proxy_*.nif"))
        pts = nifread.world_points(f.read_bytes())
        longest = max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))
        assert abs(longest - models_mod.LENGTH["pistol"] * scale) < 0.05 * models_mod.LENGTH["pistol"] * scale, (scale, longest)


from skylands_setup import sheet_data as S  # noqa: E402


def test_staff_gun_prototype_is_one_staff_weapon_with_a_bullet_spell(tmp_path):
    import struct as st

    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    bl2["weapons"]["guns"].append({**bl2["weapons"]["guns"][0], "type": "smg", "elements": ["Fire"]})  # the fake game has pistols only
    generate.generate(bl2, fake_skyrim.build_full(tmp_path / "sky0"), tmp_path / "out0")
    rep = generate.generate(bl2, fake_skyrim.build_full(tmp_path / "sky"), tmp_path / "out", gun_models="proxy", shooting="staff")
    assert (tmp_path / "out" / "Data" / "Skylands.esp").read_bytes() == (tmp_path / "out0" / "Data" / "Skylands.esp").read_bytes()
    assert rep["staff_gun"]["edid"] == "SkylandsStaffSMG" and rep["staff_gun"]["mesh"]
    assert any("donor staff StaffFireball " in l for l in rep["model_log"]), rep["model_log"]  # never the scripted artifact (AAWabbajack sorts first)
    _, recs = read_plugin(tmp_path / "out" / "Data" / "SkylandsGunModels.esp", {"WEAP", "ENCH", "MGEF", "PROJ", "SPEL", "QUST"})
    w = next(r for r in recs["WEAP"] if r.edid == "SkylandsStaffSMG")
    assert w.first("DNAM")[0] == 8  # animation type: staff
    assert w.first("CNAM") is None  # no template weapon: it would give the staff gun the vanilla staff's model
    assert w.first("EAMT") and w.first("MODL").rstrip(b"\0").endswith(b".nif") and b"Skylands" in w.first("MODL")
    en = next(r for r in recs["ENCH"] if r.edid == "SkylandsStaffSMG_Ench")
    assert st.unpack_from("<i", en.first("ENIT"))[0] == 0 and st.unpack_from("<I", en.first("ENIT"), 4)[0] & 1  # costs nothing
    assert len([s for s, _ in en.subrecords if s == "EFID"]) == 1
    assert st.unpack_from("<I", en.first("ENIT"), 8)[0] == 2 and st.unpack_from("<f", en.first("ENIT"), 24)[0] == 0.0  # concentration, no charge time
    tg = next(r for r in recs["MGEF"] if r.edid == "SkylandsStaffSMG_Trigger")
    assert st.unpack_from("<I", en.first("EFID"))[0] == tg.form_id  # the staff casts the trigger, not the bullet
    td = tg.first("DATA")
    tproj = next(r for r in recs["PROJ"] if r.edid == "SkylandsStaffSMG_Trigger")
    # a concentration cast needs a projectile of its own (none crashed the game in 0.13.13): the donor's flame with our tracer, quiet
    assert st.unpack_from("<I", td, 80)[0] == 2 and st.unpack_from("<I", td, 72)[0] == tproj.form_id and st.unpack_from("<f", td, 4)[0] == 0.0
    assert not st.unpack_from("<I", td, 0)[0] & 0x5 and st.unpack_from("<II", td, 32) == (0, 0)  # not hostile or detrimental, no hit art
    tpd = tproj.first("DATA")
    assert st.unpack_from("<H", tpd, 2)[0] == 2 and st.unpack_from("<II", tpd, 16) == (0, 0) and st.unpack_from("<I", tpd, 36)[0] == 0 and st.unpack_from("<I", tpd, 40)[0] == 0
    assert tproj.first("MODL").rstrip(b"\0") == b"Skylands\\Tracer_StaffSMG.nif" and tproj.first("NAM1") is None
    assert any("trigger donor effect FireDamageConcAimed" in l for l in rep["model_log"]), rep["model_log"]
    mg = next(r for r in recs["MGEF"] if r.edid == "SkylandsStaffSMG_Bullet")
    proj = next(r for r in recs["PROJ"] if r.edid == "SkylandsStaffSMG_Bullet")
    for rec in (mg, tg):  # no casting light or art, enchant shader or art, dual casting art: the fireball that floated above the gun
        for at in (24, 36, 92, 108, 116):
            assert st.unpack_from("<I", rec.first("DATA"), at)[0] == 0, (rec.edid, at)
    assert st.unpack_from("<I", mg.first("DATA"), 96)[0] == 0x7800 + 96 and st.unpack_from("<I", tg.first("DATA"), 96)[0] == 0  # the bullet keeps its hit art
    assert st.unpack("<H", w.first("EAMT"))[0] == round(S.SHOOTING["smg"].clip * 100)  # the charge gauge is the magazine, 100 a round
    assert st.unpack_from("<I", mg.first("DATA"), 72)[0] == proj.form_id and st.unpack_from("<f", mg.first("DATA"), 4)[0] == 0.0
    assert proj.first("MODL").rstrip(b"\0") == b"Skylands\\Tracer_StaffSMG.nif" and proj.first("NAM1") is None  # our tracer, no fireball or muzzle flash
    assert (tmp_path / "out" / "Data" / "Meshes" / "Skylands" / "Tracer_StaffSMG.nif").read_bytes().startswith(b"Gamebryo File Format")
    pd = proj.first("DATA")
    assert not st.unpack_from("<H", pd, 0)[0] & 0x8  # no muzzle flash
    assert abs(st.unpack_from("<f", pd, 8)[0] - S.SHOOTING["smg"].speed_bl2 / 3) < 1 and st.unpack_from("<f", pd, 4)[0] == 0.0  # the SMG round's speed, flat
    assert any(r.edid == "SkylandsStaffGunQuest" for r in recs["QUST"]) and any(r.edid == "SkylandsStaffGunAbility" for r in recs["SPEL"])
    fx = read_plugin(tmp_path / "out" / "Data" / "SkylandsGunModels.esp", {"MGEF"})[1]["MGEF"]
    vm = next(r for r in fx if r.edid == "SkylandsStaffGunFx").first("VMAD")
    assert b"SkylandsStaffGun15" in vm and b"BulletSpell" in vm and b"Interval" in vm and b"ChargePerShot" in vm and b"AimPoint" in vm
    aimp = next(r for r in read_plugin(tmp_path / "out" / "Data" / "SkylandsGunModels.esp", {"ACTI"})[1]["ACTI"] if r.edid == "SkylandsStaffAim")
    assert aimp.first("MODL").rstrip(b"\0") == b"Skylands\\AimPoint.nif" and b"MagSize" in vm and b"SpeedMult" in vm
    assert (tmp_path / "out" / "Data" / "Scripts" / "SkylandsStaffGun15.pex").is_file()


def test_staff_hold_points_the_barrel_at_the_thicker_end_of_the_staff():
    from skylands_setup import meshes as M, models as models_mod
    from skylands_setup.skyrim import nif

    shaft = M.box(0, 0, 0, 0.02, 0.02, 1.0)  # a thin pole along z, centred on the grip
    head = M.box(0, 0, 0.5, 0.2, 0.2, 0.2)  # a thick head at the +z end
    for sign in (1, -1):
        parts = [M.transformed(m, ((1, 0, 0), (0, sign, 0), (0, 0, sign)), 40.0) for m in (shaft, head)]
        data = nif.gun([(M.merged(parts), None, None)], (0.1, 0.1, 0.5), 2.0, "Staff")
        hold = models_mod.staff_hold(data, (0.0, 0.0, 15.0))
        assert hold.roll == 15.0 and f"head at {'+' if sign > 0 else '-'} (" in hold.note
        barrel = tuple(hold.fit.matrix[i][1] for i in range(3))  # where the gun's +y (barrel) goes in the staff's frame
        assert abs(abs(barrel[2]) - 1.0) < 1e-6 and barrel[2] * sign > 0, (sign, barrel)


def test_staff_model_is_scaled_and_moved_in_the_hand(tmp_path, monkeypatch):
    from skylands_setup.skyrim import nifread

    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    bl2["weapons"]["guns"].append({**bl2["weapons"]["guns"][0], "type": "smg", "elements": ["Fire"]})

    def points(tag, scale, forward, lift):
        monkeypatch.setattr(generate, "STAFF_SCALE", scale)
        monkeypatch.setattr(generate, "STAFF_FORWARD", forward)
        monkeypatch.setattr(generate, "STAFF_LIFT", lift)
        rep = generate.generate(bl2, fake_skyrim.build_full(tmp_path / f"sky{tag}"), tmp_path / f"out{tag}", gun_models="proxy", shooting="staff",
                                staff_turn=(45.0, 0.0, 180.0))
        nifs = [tmp_path / f"out{tag}" / "Data" / "Meshes" / Path(*rep["staff_gun"]["mesh"].split("\\"))]
        return nifread.world_points(nifs[0].read_bytes())

    def size_and_centre(pts):
        lo = [min(p[i] for p in pts) for i in range(3)]
        hi = [max(p[i] for p in pts) for i in range(3)]
        return [h - l for h, l in zip(hi, lo)], [(h + l) / 2 for h, l in zip(hi, lo)]

    base_size, base_centre = size_and_centre(points("a", 1.0, 0.0, 0.0))
    big_size, _ = size_and_centre(points("b", 1.25, 0.0, 0.0))
    _, moved_centre = size_and_centre(points("c", 1.0, 0.10, 0.10))
    assert all(abs(b / a - 1.25) < 0.02 for a, b in zip(base_size, big_size) if a > 1e-3), (base_size, big_size)
    shift = sum((m - c) ** 2 for m, c in zip(moved_centre, base_centre)) ** 0.5
    assert abs(shift - 0.1 * 2 ** 0.5 * 33.8) < 0.5, shift  # 10% of the SMG's length forward and 10% up (at right angles)
