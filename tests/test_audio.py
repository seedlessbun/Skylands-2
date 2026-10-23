import json
import struct
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_bl2  # noqa: E402
import fake_skyrim  # noqa: E402
import fake_wwise as F  # noqa: E402
from skylands_setup import generate  # noqa: E402
from skylands_setup.bl2 import audio, extract, wwise  # noqa: E402
from skylands_setup.skyrim.esm import read_plugin  # noqa: E402


def make_bl2(root: Path, trust_table: bool = True) -> Path:
    """A Borderlands folder with the two Wwise packs: the SMG Dahl shot event leads (action -> random container) to two sounds, one inside the
    bank and one streamed; the rifle Jakobs shot is a single sound."""
    cooked = root / "WillowGame" / "CookedPCConsole"
    cooked.mkdir(parents=True)
    smg, rifle = wwise.fnv1("Play_Wep_SMG_Dahl_Shot_Short"), wwise.fnv1("Ak_Play_Wep_Rifle_Jakobs_Shot")
    wem = F.pcm_wem()
    objs = [F.event(smg, [0x100]), F.play_action(0x100, 0x200), F.container(0x200, [0x300, 0x301], 0x999),
            F.sound(0x300, 0x5001), F.sound(0x301, 0x5002, streamed=True),
            F.event(rifle, [0x101]), F.play_action(0x101, 0x302), F.sound(0x302, 0x5003)]
    for n, part in enumerate(("Eject", "Insert", "Cock")):  # the SMG Dahl reload: three events, one sound each
        objs += [F.event(wwise.fnv1(f"Ak_Play_Wep_SMG_Dahl_Reload_{part}"), [0x110 + n]), F.play_action(0x110 + n, 0x310 + n), F.sound(0x310 + n, 0x5100 + n)]
    bank = F.bank(0xB1, objs, {0x5001: wem, 0x5003: F.pcm_wem(0.2, 44100, 1), **{0x5100 + n: F.pcm_wem(0.1 + n * 0.05) for n in range(3)}})
    (cooked / "Audio_Banks.pck").write_bytes(F.pck([(0xB1, bank)], [], trust_table))
    (cooked / "Audio_Streaming.pck").write_bytes(F.pck([], [(0x5002, F.pcm_wem(0.15, 48000, 2))]))
    return root


def test_fnv1_is_wwises_name_hash():
    assert wwise.fnv1("") == 2166136261
    assert wwise.fnv1("Play_Wep_SMG_Dahl_Shot_Short") == wwise.fnv1("play_wep_smg_dahl_shot_short")
    assert wwise.fnv1("a") == ((2166136261 * 16777619) & 0xFFFFFFFF) ^ 97


def test_event_names_are_tried_with_and_without_the_unreal_prefix():
    names = [n for n, _ in wwise.event_ids("Ak_Play_Wep_SMG_Dahl_Shot_Short")]
    assert "Ak_Play_Wep_SMG_Dahl_Shot_Short" in names and "Play_Wep_SMG_Dahl_Shot_Short" in names and "Wep_SMG_Dahl_Shot_Short" in names


def test_shot_sounds_are_followed_from_event_to_wav(tmp_path):
    bl2 = make_bl2(tmp_path / "bl2")
    log: list[str] = []
    out = audio.extract_shot_sounds(bl2, tmp_path / "work", [("smg", "Dahl"), ("assault_rifle", "Jakobs"), ("smg", "Torgue")], log.append, download=False)
    assert set(out) == {("smg", "Dahl"), ("assault_rifle", "Jakobs"), ("smg", "Dahl", "out"), ("smg", "Dahl", "in"), ("smg", "Dahl", "end")}, log
    assert len(out[("smg", "Dahl", "in")]) == 1
    assert len(out[("smg", "Dahl")]) == 2  # one from the bank, one streamed
    for f in [*out[("smg", "Dahl")], *out[("assault_rifle", "Jakobs")]]:
        with wave.open(str(f)) as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 44100)  # what Skyrim plays as a sound effect
    assert any("no event found" in l and "smg_Torgue" in l for l in log), log
    assert any("Play_Wep_SMG_Dahl_Shot_Short" in l and "2 sound objects" in l for l in log), log
    assert json.loads((tmp_path / "work" / "audio" / "report.json").read_text())["smg_Torgue"] == "no event"


def test_banks_are_found_by_their_chunks_when_the_pack_table_is_useless(tmp_path):
    bl2 = make_bl2(tmp_path / "bl2", trust_table=False)
    log: list[str] = []
    out = audio.extract_shot_sounds(bl2, tmp_path / "work", [("assault_rifle", "Jakobs")], log.append, download=False)
    assert ("assault_rifle", "Jakobs") in out, log


def test_audio_that_needs_the_decoder_is_skipped_with_a_message(tmp_path):
    root = tmp_path / "bl2" / "WillowGame" / "CookedPCConsole"
    root.mkdir(parents=True)
    vorbis = b"RIFF" + struct.pack("<I", 40) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 0xFFFF, 1, 48000, 0, 0, 0) + bytes(20)
    objs = [F.event(wwise.fnv1("Ak_Play_Wep_Pistol_Dahl_Shot"), [1]), F.play_action(1, 2), F.sound(2, 0x7000)]
    (root / "Audio_Banks.pck").write_bytes(F.pck([(1, F.bank(1, objs, {0x7000: vorbis}))], []))
    log: list[str] = []
    out = audio.extract_shot_sounds(tmp_path / "bl2", tmp_path / "work", [("pistol", "Dahl")], log.append, download=False)
    assert out == {} and any("needs the decoder tool" in l for l in log), log


def test_the_staff_guns_get_the_borderlands_shot_sound(tmp_path):
    fake_bl2.pandora_install(tmp_path / "bl2")
    bl2 = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    bl2["rarities"] = [{"min": lvl, "max": lvl, "rgb": [lvl * 40, 100, 50]} for lvl in range(1, 7)]
    g0 = bl2["weapons"]["guns"][0]
    bl2["weapons"]["guns"].append({**g0, "type": "smg", "manufacturer": "Dahl", "elements": ["Fire"], "balance": g0["balance"] + "_smg"})
    wav = tmp_path / "x.wav"
    wav.write_bytes(audio.to_mono_wav(F.pcm_wem()))
    parts = {}
    for part in ("out", "in", "end"):
        (tmp_path / f"r_{part}.wav").write_bytes(wav.read_bytes())
        parts[("smg", "Dahl", part)] = [tmp_path / f"r_{part}.wav"]
    rep = generate.generate(bl2, fake_skyrim.build_full(tmp_path / "sky"), tmp_path / "out", shooting="staff", shot_sounds={("smg", "Dahl"): [wav], **parts})
    data = tmp_path / "out" / "Data"
    assert (data / "Sound" / "FX" / "Skylands" / "x.wav").is_file()
    _, recs = read_plugin(data / "SkylandsGunModels.esp", {"SNDR", "KYWD", "WEAP", "MGEF"})
    snd = next(r for r in recs["SNDR"] if r.edid == "SkylandsShot_smg_Dahl")
    assert [d for s, d in snd.subrecords if s == "ANAM"] == [b"FX\\Skylands\\x.wav\0"]  # the vanilla record's file name style (no Sound\ prefix)
    assert snd.first("CNAM") == struct.pack("<I", 0x1EEF540A) and snd.first("GNAM") and snd.first("ONAM")  # category and output model kept
    kw = next(r for r in recs["KYWD"] if r.edid == "SkylandsSnd_smg_Dahl")
    smg = [w for w in recs["WEAP"] if w.first("DNAM")[0] == 8 and kw.form_id in struct.unpack(f"<{len(w.first('KWDA')) // 4}I", w.first("KWDA"))]
    assert smg  # the Dahl SMG variants carry the keyword
    vm = next(r for r in recs["MGEF"] if r.edid == "SkylandsStaffGunFx").first("VMAD")
    assert kw.form_id.to_bytes(4, "little") in vm and snd.form_id.to_bytes(4, "little") in vm  # the script's lists name the keyword and the sound
    assert any("smg Dahl shot sound SkylandsShot_smg_Dahl" in l for l in rep["model_log"]), rep["model_log"]
    for part in ("Out", "In", "End"):  # the three parts of the reload have their own descriptors, named by the script's parallel lists
        r = next(r for r in recs["SNDR"] if r.edid == f"SkylandsReload{part}_smg_Dahl")
        assert r.form_id.to_bytes(4, "little") in vm
        assert (data / "Sound" / "FX" / "Skylands" / f"r_{part.lower()}.wav").is_file()
    for prop in (b"ReloadOut", b"ReloadIn", b"ReloadEnd"):
        assert prop in vm


def test_an_action_laid_out_differently_is_still_followed(tmp_path):
    root = tmp_path / "bl2" / "WillowGame" / "CookedPCConsole"
    root.mkdir(parents=True)
    odd_action = F.obj(3, 1, bytes([9, 9]) + bytes(6) + struct.pack("<I", 2))  # the target is not where the strict reading looks
    objs = [F.event(wwise.fnv1("Ak_Play_Wep_Pistol_Dahl_Shot"), [1]), odd_action, F.sound(2, 0x7000)]
    (root / "Audio_Banks.pck").write_bytes(F.pck([(1, F.bank(1, objs, {0x7000: F.pcm_wem()}))], []))
    out = audio.extract_shot_sounds(tmp_path / "bl2", tmp_path / "work", [("pistol", "Dahl")], lambda m: None, download=False)
    assert ("pistol", "Dahl") in out
