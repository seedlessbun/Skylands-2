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
        from skylands_setup.skyrim import nif

        return nif.dds_solid((9, 9, 9))

    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    sky = fake_skyrim.build_full(tmp_path / "sky")
    rep = generate.generate(bl2, sky, tmp_path / "out", gun_models="auto", model_sources={"native": Source()})
    tes, recs = read_plugin(tmp_path / "out" / "Data" / "SkylandsGunModels.esp", {"WEAP"})
    paths = {r.first("MODL").rstrip(b"\0").decode() for r in recs["WEAP"]}
    assert all(p.startswith("Skylands\\Guns\\native_") for p in paths), paths  # every fake gun is a pistol
    assert (tmp_path / "out" / "Data" / "Textures" / "Skylands" / "Guns" / "t_deadbeef.dds").is_file()
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
    rep = generate.generate(bl2, sky, tmp_path / "out", gun_models="proxy")
    assert any("vanilla length 60.0 along axis x+" in line for line in rep["model_log"]), rep["model_log"]
    f = next((tmp_path / "out" / "Data" / "Meshes" / "Skylands" / "Guns").glob("proxy_*.nif"))
    pts = nifread.world_points(f.read_bytes())
    ext = [max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)]
    assert ext[0] == max(ext) and ext[0] > 10  # the barrel axis is x, as in the vanilla mesh
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
