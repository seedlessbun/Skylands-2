"""voices.extract: the Pandora bandits' Borderlands 2 lines, read from the English voice pack, the sound pack and the streamed audio, into WAV files by line group."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_wwise as fw  # noqa: E402

from skylands_setup import skse, voices  # noqa: E402
from skylands_setup.bl2 import wwise  # noqa: E402
from skylands_setup.sheet_data import ENEMIES  # noqa: E402


def install(root: Path) -> Path:
    cooked = root / "WillowGame" / "CookedPCConsole"
    eng = cooked / "English(US)"
    eng.mkdir(parents=True)
    events, sfx, streamed = [], [], []
    for n, line in enumerate(("gen_react_death", "gen_react_pain", "hum_start_aggro", "hum_start_taunt")):
        ev, act, snd, media = wwise.fnv1(f"Play_VOBD_Nomad_{line}"), 100 + n, 200 + n, 300 + n
        events += [fw.event(ev, [act]), fw.play_action(act, snd)]
        sfx.append(fw.sound(snd, media, streamed=True))
        streamed.append((media, fw.pcm_wem()))
    (cooked / "Audio_Banks.pck").write_bytes(fw.pck([(1, fw.bank(1, sfx))], []))
    (eng / "Audio_Banks.pck").write_bytes(fw.pck([(2, fw.bank(2, events))], []))
    (eng / "Audio_Streaming.pck").write_bytes(fw.pck([], streamed))
    return root


def test_lines_are_sorted_into_groups_and_decoded(tmp_path):
    bl2 = install(tmp_path / "bl2")
    said: list[str] = []
    out = voices.extract(bl2, tmp_path / "work", {"nomad", "psycho1"}, said.append, download=False)
    assert set(out) == {("nomad", "death"), ("nomad", "pain"), ("nomad", "aggro"), ("nomad", "taunt")}
    assert len(out[("nomad", "aggro")]) == 2  # its own line and, second best, the taunt
    for files in out.values():
        for f in files:
            assert f.read_bytes()[:4] == b"RIFF"  # PCM decodes without the decoder tool
    assert any("nomad: " in s and "in 4 of 8 groups" in s for s in said) and any("psycho1: 0 lines" in s for s in said)


def test_no_english_voice_pack_means_no_lines_and_no_error(tmp_path):
    said: list[str] = []
    assert voices.extract(tmp_path / "empty", tmp_path / "work", {"nomad"}, said.append, download=False) == {}
    assert any("not found" in s for s in said)


def test_every_pandora_name_has_borderlands_speakers():
    spk = voices.speakers_of(ENEMIES)
    assert spk["tier0"] == ["maraudkiller", "maraudrip", "marauddh", "maraudscatshot"] and spk["tier3"] == ["psycho1", "psycho2"]
    assert spk["tier4"] == ["banditheavy"] and spk["boss"] == ["nomad"] and set(spk) == set(ENEMIES)


def test_the_plugin_reads_the_table_and_speaks_on_combat_hits_deaths_and_taunts():
    root = HERE.parent / "native" / "skse" / "src"
    main = (root / "main.cpp").read_text(encoding="utf-8")
    # 1.22.0: the Pandora bandits' voices: the table the installer writes, the three listeners, the taunts, the settings
    voices_h = (root / "voices.h").read_text(encoding="utf-8")
    for text in ("SkylandsVoices.txt", "LookupFormID(s.raw[i], \"SkylandsGunModels.esp\")", "RE::TESCombatEvent", "RE::TESHitEvent", "RE::TESDeathEvent", "SetObjectToFollow",
                 "VoiceGap", "VoiceTauntMin", "kDeathFire", "kGloat", "SpeakerOfLocked"):
        assert text in voices_h, text
    assert "voices::Load();" in main and "voices::Start(holder);" in main and "voices::Config(" in main and "voices::g_elementOf" in main
    assert "kVersion = 392" in main and "{ 1, 27, 0, 0 }" in main
    assert voices.TABLE in (root / "voices.h").read_text(encoding="utf-8")  # the installer and the plugin agree on the file name
    order = list(voices.GROUPS)
    header = (root / "voices.h").read_text(encoding="utf-8")
    assert all(f'"{g}"' in header for g in order)
    assert header.index('"aggro", "taunt", "pain", "crit", "death", "death_fire", "death_shock", "gloat"') > 0 and order == ["aggro", "taunt", "pain", "crit", "death", "death_fire", "death_shock", "gloat"]


def test_despawn_by_distance_and_rarity_and_the_beam_cap():
    root = HERE.parent / "native" / "skse" / "src"
    main = (root / "main.cpp").read_text(encoding="utf-8")
    despawn = (root / "despawn.h").read_text(encoding="utf-8")
    shield = (root / "shield.h").read_text(encoding="utf-8")
    # 1.23.0: loose Skylands items go by distance, commoner ones sooner; the player's own drops stay; the marks survive a save in the co-save
    for text in ("ForEachReference", "SkylandsRarity_", "DespawnCommon", "DespawnLegendary", "oldContainer == 0x14", "0x4E505344", "SetDelete(true)", "BeamCap"):
        assert text in despawn, text
    assert "fn(a_intfc, type, version)" in shield and "for (const auto fn : g_extraSave)" in shield and "for (const auto fn : g_extraRevert)" in shield
    assert '#include "despawn.h"' in main and "despawn::Start(holder);" in main and "despawn::g_onRemoved = &DropBeamOf;" in main and "despawn::Config(" in main
    # the beam cap: rarity read before the beam lock is taken (RarityOf takes despawn's own lock), the lowest rarity loses its beam
    track = main.split("bool TrackBeam(")[1].split("\n\t}\n")[0]
    assert track.index("despawn::RarityOf") < track.index("std::lock_guard guard(g_beamLock)") and "it->rarity < lowest->rarity" in track
    ini = skse.default_ini()
    for key in ("Despawn=1", "DespawnCommon=3000", "DespawnLegendary=16000", "BeamCap=24"):
        assert key in ini, key


def test_the_voice_diagnostics_name_each_bandits_voice_type():
    voices_h = (HERE.parent / "native" / "skse" / "src" / "voices.h").read_text(encoding="utf-8")
    assert "voice look:" in voices_h and "templateUseFlags" in voices_h and 'line.rfind("silent ", 0) == 0' in voices_h
    say = voices_h.split("inline bool Say(")[1]
    assert say.index("Diagnose(a_actor, looked);") < say.index("PlayAt(")


def test_the_lines_are_made_louder_without_wrapping():
    import struct as st
    pcm = st.pack("<4h", 1000, -1000, 30000, -30000)
    wav = b"RIFF" + st.pack("<I", 36 + len(pcm)) + b"WAVE" + b"fmt " + st.pack("<IHHIIHH", 16, 1, 1, 44100, 88200, 2, 16) + b"data" + st.pack("<I", len(pcm)) + pcm
    out = voices.louder(wav, 1.35)
    assert st.unpack_from("<4h", out, 44) == (1350, -1350, 32767, -32768) and out[:44] == wav[:44]
    assert voices.louder(b"not a wav", 1.35) == b"not a wav" and voices.GAIN == 1.35


def test_the_plugin_silences_a_pandora_bandit_that_kept_a_skyrim_voice():
    voices_h = (HERE.parent / "native" / "skse" / "src" / "voices.h").read_text(encoding="utf-8")
    diagnose = voices_h.split("inline void Diagnose(")[1].split("\n\t}\n")[0]
    assert "base->voiceType = silent;" in diagnose and "LookupByID<RE::BGSVoiceType>(g_silent)" in diagnose
    taunts = voices_h.split("inline void Taunts()")[1]
    assert taunts.index("Diagnose(actor, looked);") < taunts.index("currentCombatTarget")  # looked at before it fights


def test_crashes_are_caught_first_and_death_lines_do_not_follow_the_body():
    root = HERE.parent / "native" / "skse" / "src"
    main = (root / "main.cpp").read_text(encoding="utf-8")
    # 0.48.0 crashed with no CRASH line: a vectored handler logs the first fatal exceptions before anyone else, and the unhandled filter is claimed again later
    assert "AddVectoredExceptionHandler(1, FirstChance);" in main and 'ClaimCrashFilter("after data load");' in main and 'ClaimCrashFilter("after a game load");' in main
    first = main.split("LONG WINAPI FirstChance(")[1].split("\n\t}\n")[0]
    assert "return EXCEPTION_CONTINUE_SEARCH;" in first and "EXCEPTION_ACCESS_VIOLATION" in first and "g_firstChance.fetch_add(1) >= 4" in first
    voices_h = (root / "voices.h").read_text(encoding="utf-8")
    assert "PlayAt(sound, a_actor, used != kDeath && used != kDeathFire && used != kDeathShock);" in voices_h and "a_follow && !a_actor->IsDead()" in voices_h


def test_respawn_range_check_never_asks_an_unloaded_cell_if_it_is_inside():
    from skylands_setup.skyrim import scripts
    import inspect
    src = inspect.getsource(scripts)
    in_range = src.split('"InRange",')[1].split("remove = Function(")[0]
    assert in_range.count('"IsInterior"') == 1 and '("id", "IsInterior"), ("id", "cell")' in in_range  # only the player's own (loaded) cell


def test_both_hud_displays_draw_from_ui_tasks_inside_a_guard():
    main = (HERE.parent / "native" / "skse" / "src" / "main.cpp").read_text(encoding="utf-8")
    # 0.48.1 log: the crash was inside Scaleform while the plugin drew its HUD from an ordinary task
    tick = main.split("\tvoid Tick()")[1].split("\n\t}\n")[0]
    assert "QueueHud();" in tick and "HudFrame(" not in tick
    assert main.count("task->AddUITask(") == 2 and "Guarded(&HudFrameNow)" in main and "Guarded(&ShieldHudNow)" in main
    assert "QueueShieldHud();" in main and "shieldhud::Frame();" not in main.split("shield::g_afterUpdate = []() {")[1].split("};")[0]
    guarded = main.split("int Guarded(GuardedFn a_fn)")[1].split("\n\t}\n")[0]
    assert "__try" in guarded and "__except (EXCEPTION_EXECUTE_HANDLER)" in guarded
