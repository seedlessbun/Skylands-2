"""The Badass survey (bl2badass) on a fake install with a regular enemy, its badass and super badass variants, a formula and a pool list."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_bl2  # noqa: E402
from fake_bl2 import ObjBuilder  # noqa: E402

from skylands_setup import badassprobe  # noqa: E402


def badass_install(root):
    fake_bl2.pandora_install(root)
    cooked = root / "WillowGame" / "CookedPCConsole"
    b = ObjBuilder()
    b.obj("GD_Balance_HealthAndDamage.AIParameters.Attribute_HealthMultiplier", "AttributeDefinition",
          b.st("BaseValue", "AttributeInitializationData", b.f("BaseValueConstant", 1.0) + b.f("BaseValueScaleConstant", 1.0)))
    b.obj("GD_AI_Marauder.Class.AIClass_Marauder", "WillowAIClassDefinition", b.o("HealthAttribute", "GD_Balance_HealthAndDamage.AIParameters.Attribute_HealthMultiplier"))
    b.obj("GD_Itempools.ListDefs.BadassEnemyGunsAndGear", "ItemPoolListDefinition", b.f("Probability", 1.0))
    for leaf, name, scale in (("PawnBalance_Marauder", "Marauder", 1.0), ("PawnBalance_MarauderBadass", "Badass Marauder", 4.0),
                              ("PawnBalance_SuperBadassMarauder", "Super Badass Marauder", 10.0)):
        b.obj(f"GD_Population_Marauder.Balance.{leaf}", "AIPawnBalanceDefinition",
              b.o("AIClass", "GD_AI_Marauder.Class.AIClass_Marauder") + b.f("HealthScale", scale)
              + b.arr_structs("PlayThroughs", [b.i("PlayThrough", 1) + b.s("DisplayName", name) + b.o("DefaultItemPoolIncludedLists", "GD_Itempools.ListDefs.BadassEnemyGunsAndGear")]))
    b.obj("GD_Population_Skag.Balance.PawnBalance_Skag", "AIPawnBalanceDefinition", b.f("HealthScale", 1.0))
    b.obj("FX_Badass.Particles.Part_BadassAura", "ParticleSystem", b"")
    b.obj("Ake_VO_Marauder.Ak_Play_VO_Marauder_Badass_Taunt", "AkEvent", b"")
    b.obj("Ake_VO_Marauder.Ak_Play_Skag_Death", "AkEvent", b"")
    (cooked / "Startup_Badass_Fake.upk").write_bytes(b.build())


def test_badass_survey_finds_tiers_formulas_pools_and_enemy_sounds(tmp_path):
    bl2 = tmp_path / "bl2"
    badass_install(bl2)
    out = tmp_path / "report.txt"
    assert badassprobe.main(["--bl2", str(bl2), "--out", str(out), "--no-audio", "--minutes", "2"]) == 0
    text = out.read_text(encoding="utf-8")
    for needle in (
        "badass   GD_Population_Marauder.Balance.PawnBalance_MarauderBadass",
        "super    GD_Population_Marauder.Balance.PawnBalance_SuperBadassMarauder",
        "regular  GD_Population_Skag.Balance.PawnBalance_Skag",
        "Marauder: 3 (",
        "HealthScale: 10.0",  # the super variant dumped in full
        "GD_AI_Marauder.Class.AIClass_Marauder",  # followed to the AI class
        "Attribute_HealthMultiplier",  # and the formula
        "BadassEnemyGunsAndGear",  # the pool list
        "Part_BadassAura",  # presentation
        "ak_play_vo_marauder_badass_taunt",  # enemy voice names by family (name tables are lower case)
        "ak_play_skag_death",
        "-- skag",
        "banks not checked",
        "Finished. Report written",
    ):
        assert needle.lower() in text.lower(), needle
    assert "SECTION" not in text


def test_badass_survey_reports_a_missing_install(tmp_path):
    out = tmp_path / "report.txt"
    assert badassprobe.main(["--bl2", str(tmp_path / "nope"), "--out", str(out)]) == 2


def test_tier_and_family_words():
    assert badassprobe.tier_of("PawnBalance_UltimateBadassVarkid") == "ultimate"
    assert badassprobe.tier_of("PawnBalance_SuperBadassSkag") == "super"
    assert badassprobe.tier_of("PawnBalance_BadassMarauder") == "badass"
    assert badassprobe.tier_of("PawnBalance_Nomad") == "regular"
    assert badassprobe.is_sound_name("Ak_Play_VO_Psycho_Taunt") and badassprobe.is_sound_name("Ak_Play_Skag_Bite")
    assert not badassprobe.is_sound_name("Ak_Play_Wep_SMG_Dahl_Shot") and not badassprobe.is_sound_name("PawnBalance_Skag")


def test_balance_groups_copied_into_many_packages_are_read_once_each(tmp_path, monkeypatch):
    # the real game copies GD_Population_<X>.Balance into many level packages; B1 used to reopen them group after group (it looked stuck)
    bl2 = tmp_path / "bl2"
    badass_install(bl2)
    cooked = bl2 / "WillowGame" / "CookedPCConsole"
    for n in range(3):
        b = ObjBuilder()
        b.obj("GD_Population_Marauder.Balance.PawnBalance_MarauderBadass", "AIPawnBalanceDefinition", b.f("HealthScale", 4.0))
        b.obj(f"GD_Population_Rakk{n}.Balance.PawnBalance_Rakk{n}", "AIPawnBalanceDefinition", b.f("HealthScale", 1.0))
        (cooked / f"Level_{n}_P.upk").write_bytes(b.build())
    from skylands_setup.bl2 import upk

    opened: list[str] = []
    real = upk.open_package

    def counting(path):
        opened.append(Path(path).name)
        return real(path)

    monkeypatch.setattr(upk, "open_package", counting)
    out = tmp_path / "report.txt"
    assert badassprobe.main(["--bl2", str(bl2), "--out", str(out), "--no-audio", "--minutes", "2"]) == 0
    text = out.read_text(encoding="utf-8")
    b1 = text.split("B1. Every enemy")[1].split("========")[0]
    assert b1.count("PawnBalance_MarauderBadass [") == 1  # one copy listed, not one per package
    for n in range(3):
        assert f"PawnBalance_Rakk{n}" in b1
    # B1 on its own: every package it opens is opened once
    import time

    from skylands_setup.bl2.index import Index
    from skylands_setup.shieldprobe import Ctx

    ctx = Ctx(Index(bl2), tmp_path / "b1.txt", time.time() + 60)
    opened.clear()
    fams = badassprobe.balances(ctx)
    assert opened and len(opened) == len(set(opened)), opened
    assert sum(len(v) for v in fams.values()) == 8  # the fake install's 5 + the 3 Rakk; the copied MarauderBadass is counted once


def test_voice_search_finds_battle_dialog_in_a_pack_other_than_the_main_pair(tmp_path):
    # the first real report found no ak_play_vobd_* event in Audio_Banks.pck although the packages name a bank akb_vobd_bandits
    import fake_wwise as fw

    from skylands_setup.bl2 import wwise

    bl2 = tmp_path / "bl2"
    badass_install(bl2)
    cooked = bl2 / "WillowGame" / "CookedPCConsole"
    b = ObjBuilder()
    b.obj("Ake_VOBD_Marauder.Ak_Play_VOBD_Marauder_Gen_React_Death", "AkEvent", b"")
    b.obj("Ake_VOBD_Marauder.Ak_Play_VOBD_Marauder_Gen_Start_Taunt", "AkEvent", b"")
    b.obj("Akb_VOBD_Bandits.Akb_VOBD_Bandits", "AkBank", b"")
    (cooked / "Startup_Voice_Fake.upk").write_bytes(b.build())
    (cooked / "Audio_Banks.pck").write_bytes(fw.pck([(wwise.fnv1("akb_other"), fw.bank(wwise.fnv1("akb_other"), []))], []))
    ev = wwise.fnv1("Play_VOBD_Marauder_Gen_React_Death")
    death = fw.bank(wwise.fnv1("akb_vobd_bandits"), [fw.event(ev, [77]), fw.play_action(77, 88), fw.sound(88, 99)], {99: fw.pcm_wem()})
    dlc = bl2 / "DLC" / "Lang" / "English(US)"
    dlc.mkdir(parents=True)
    (dlc / "Audio_Banks_VO.pck").write_bytes(fw.pck([(wwise.fnv1("akb_vobd_bandits"), death)], []))
    out = tmp_path / "voice.txt"
    assert badassprobe.main(["--bl2", str(bl2), "--out", str(out), "--voice-packs", "--minutes", "2"]) == 0
    text = out.read_text(encoding="utf-8")
    assert "B8. Enemy voices" in text and "B1. Every enemy" not in text  # --voice runs only the names and the voices
    assert "-- marauder (2): {'death': 1, 'taunt': 1}" in text
    assert "akb_vobd_bandits" in text  # the bank named by its Wwise id
    vo = text.split("Audio_Banks_VO.pck")[1]
    assert "ak_play_vobd_marauder_gen_react_death: 1 sound(s), 1 audio file(s) found here" in vo
    assert "battle-dialog events found: 1 of 2 names, in 1 packs" in text


def test_spawn_survey_reads_the_badass_share_of_a_spawn_mix(tmp_path):
    bl2 = tmp_path / "bl2"
    badass_install(bl2)  # holds PawnBalance_Marauder and PawnBalance_MarauderBadass
    cooked = bl2 / "WillowGame" / "CookedPCConsole"
    b = ObjBuilder()
    b.obj("GD_Population_Marauder.Balance.PawnBalance_Marauder", "AIPawnBalanceDefinition", b"")
    b.obj("GD_Population_Marauder.Balance.PawnBalance_MarauderBadass", "AIPawnBalanceDefinition", b"")
    b.obj("GD_Population_Marauder.Population.PopDef_MarauderMix", "WillowPopulationDefinition", b"")
    b.obj("GD_Population_Marauder.Population.PopDef_MarauderMix:PopulationFactoryBalancedAIPawn_0", "PopulationFactoryBalancedAIPawn",
          b.o("PawnBalanceDefinition", "GD_Population_Marauder.Balance.PawnBalance_Marauder"))
    b.obj("GD_Population_Marauder.Population.PopDef_MarauderMix:PopulationFactoryBalancedAIPawn_1", "PopulationFactoryBalancedAIPawn",
          b.o("PawnBalanceDefinition", "GD_Population_Marauder.Balance.PawnBalance_MarauderBadass"))
    mix = b.arr_structs("ActorArchetypeList", [
        b.o("SpawnFactory", "GD_Population_Marauder.Population.PopDef_MarauderMix:PopulationFactoryBalancedAIPawn_0")
        + b.st("Probability", "AttributeInitializationData", b.f("BaseValueConstant", 0.9) + b.f("BaseValueScaleConstant", 1.0)) + b.i("MaxActiveAtOneTime", 6),
        b.o("SpawnFactory", "GD_Population_Marauder.Population.PopDef_MarauderMix:PopulationFactoryBalancedAIPawn_1")
        + b.st("Probability", "AttributeInitializationData", b.f("BaseValueConstant", 0.1) + b.f("BaseValueScaleConstant", 1.0)) + b.i("MaxActiveAtOneTime", 1)])
    idx = b.paths["GD_Population_Marauder.Population.PopDef_MarauderMix"]
    b.exports[idx - 1]["body"] = b.exports[idx - 1]["body"][:4] + mix + b.none()
    (cooked / "Startup_Pop_Fake.upk").write_bytes(b.build())
    out = tmp_path / "spawns.txt"
    assert badassprobe.main(["--bl2", str(bl2), "--out", str(out), "--spawns", "--no-audio", "--minutes", "2"]) == 0
    text = out.read_text(encoding="utf-8")
    assert "B9. How often a Badass spawns" in text and "B8." not in text
    assert "PopDef_MarauderMix: badass 10.0%, regular 90.0%" in text
    assert "SHARE badass: median 10.0%" in text
    assert "SECTION" not in text


def test_voice_banks_inside_packages_are_searched(tmp_path):
    import fake_wwise as fw

    from skylands_setup.bl2 import wwise

    bl2 = tmp_path / "bl2"
    badass_install(bl2)
    cooked = bl2 / "WillowGame" / "CookedPCConsole"
    names = ObjBuilder()
    names.obj("Ake_VOBD_Psycho.Ak_Play_VOBD_Psycho_Gen_React_Pain", "AkEvent", b"")
    names.obj("Akb_VOBD_Bandits.Akb_VOBD_Bandits", "AkBank", b"")
    (cooked / "Bandit_Dialog.upk").write_bytes(names.build())
    ev = wwise.fnv1("Play_VOBD_Psycho_Gen_React_Pain")
    bank = fw.bank(wwise.fnv1("akb_vobd_bandits"), [fw.event(ev, [5]), fw.play_action(5, 6), fw.sound(6, 7)], {7: fw.pcm_wem()})
    loc = ObjBuilder()
    i = loc.obj("Akb_VOBD_Bandits.Akb_VOBD_Bandits", "AkBank", b"")
    loc.exports[i - 1]["body"] += bank
    (cooked / "Bandit_Dialog_LOC_INT.upk").write_bytes(loc.build())
    out = tmp_path / "voice.txt"
    assert badassprobe.main(["--bl2", str(bl2), "--out", str(out), "--voice-packs", "--minutes", "2"]) == 0
    text = out.read_text(encoding="utf-8")
    part = text.split("B8b. Voice banks stored inside the packages")[1]
    assert "Bandit_Dialog_LOC_INT.upk: Akb_VOBD_Bandits.Akb_VOBD_Bandits [AkBank]" in part
    assert "ak_play_vobd_psycho_gen_react_pain: 1 sound(s), audio inside the bank 1" in part
    assert "by speaker: {'psycho': 1}" in part


def test_voice_lines_resolve_across_the_language_pack_the_sound_pack_and_the_streamed_audio(tmp_path):
    # the base game's case: the event is in English(US)/Audio_Banks.pck, the sound object it plays is in the language-free Audio_Banks.pck,
    # and the audio file is streamed from English(US)/Audio_Streaming.pck (the first voice survey loaded each pack alone and found 0 sounds)
    import fake_wwise as fw

    from skylands_setup.bl2 import wwise

    bl2 = tmp_path / "bl2"
    badass_install(bl2)
    cooked = bl2 / "WillowGame" / "CookedPCConsole"
    names = ObjBuilder()
    names.obj("Ake_VOBD_Psycho1.Ak_Play_VOBD_Psycho1_Gen_React_Death", "AkEvent", b"")
    names.obj("Ake_VOBD_Psycho1.Ak_Play_VOBD_Psycho1_Hum_Start_Taunt", "AkEvent", b"")
    (cooked / "Psycho_Dialog.upk").write_bytes(names.build())
    death, taunt = wwise.fnv1("Play_VOBD_Psycho1_Gen_React_Death"), wwise.fnv1("Play_VOBD_Psycho1_Hum_Start_Taunt")
    lang = fw.bank(wwise.fnv1("akb_vobd_bandits"), [fw.event(death, [11]), fw.play_action(11, 21), fw.event(taunt, [12]), fw.play_action(12, 99)])
    sfx = fw.bank(wwise.fnv1("akb_vobd_shared"), [fw.sound(21, 31, streamed=True)])
    (cooked / "Audio_Banks.pck").write_bytes(fw.pck([(wwise.fnv1("akb_vobd_shared"), sfx)], []))
    eng = cooked / "English(US)"
    eng.mkdir()
    (eng / "Audio_Banks.pck").write_bytes(fw.pck([(wwise.fnv1("akb_vobd_bandits"), lang)], []))
    (eng / "Audio_Streaming.pck").write_bytes(fw.pck([], [(31, fw.pcm_wem())]))
    out = tmp_path / "work" / "voice.txt"
    assert badassprobe.main(["--bl2", str(bl2), "--out", str(out), "--voice", "--minutes", "2"]) == 0
    text = out.read_text(encoding="utf-8")
    assert "B10. Enemy voice lines" in text and "B8. Enemy voices" not in text
    assert "psycho1 [base game]: 2 / 1 / 1 /" in text and "<- bandit-like" in text  # 2 events, 1 leads to a sound with streamed audio
    assert "1 events lead to no sound" in text and "ak_play_vobd_psycho1_hum_start_taunt event" in text  # its structure is dumped
    wavs = list((tmp_path / "work" / "voice-samples").glob("psycho1_death_*.wav"))
    assert len(wavs) == 1 and wavs[0].read_bytes()[:4] == b"RIFF"  # PCM decodes without the decoder tool
