"""Borderlands 2 voices for the Pandora bandits (docs/badass-roadmap.md, the voice stage).

The Skyrim bandits the installer renames (sheets/enemies.json: Marauder, Nomad, Psycho, Bruiser, Goliath, Badass Marauder, Badass Nomad) speak with the
battle dialog of the Borderlands 2 enemy of that name (the sheet's `voices` column names the BL2 speakers; a bandit keeps one of them for its life).
  install:  extract()  every line group of every speaker, decoded to mono WAV files in work\\audio\\voice (the gun sounds' decoder)
            build()    one sound descriptor (SNDR) per speaker and line group in SkylandsGunModels.esp (the files go to Data\\Sound\\FX\\Skylands\\VO),
                       a silent voice type, overrides of the renamed bandits that use it (so Skyrim's own bandit lines are gone, the user's choice),
                       and Data\\SKSE\\Plugins\\SkylandsVoices.txt, the table the plugin reads (written fresh by every install, never merged)
  in game:  the SKSE plugin (native/skse/src/voices.h) speaks: entering combat, getting hurt, dying, taunts during the fight, a gloat when the player dies.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from .skyrim import esp

# line groups the plugin knows (the order of the columns in SkylandsVoices.txt) -> the BL2 line names that fill them, best first
GROUPS: dict[str, tuple[str, ...]] = {
    "aggro": ("hum_start_aggro", "hum_start_taunt"),
    "taunt": ("hum_start_taunt", "hum_confirm_focus", "hum_confirm_charge", "command_charge", "hum_react_unprovoked", "hum_react_injured"),
    "pain": ("gen_react_pain", "gen_react_pain_dot"),
    "crit": ("gen_react_pain_crit",),
    "death": ("gen_react_death",),
    "death_fire": ("gen_react_death_fire",),
    "death_shock": ("gen_react_death_shock",),
    "gloat": ("hum_react_pl_death", "hum_react_pl_down"),
}
PER_GROUP = 6  # audio files kept per speaker and group (the sound descriptor picks one at random)
TABLE = "SkylandsVoices.txt"
SILENT_VOICE = "SkylandsSilentVoice"


def speakers_of(sheet) -> dict[str, list[str]]:
    """{Pandora row id: [BL2 speakers]} from the enemies sheet."""
    return {row.id: [s for s in row.voices.split(";") if s] for row in sheet.values() if getattr(row, "voices", "-") not in ("", "-")}


def extract(bl2: Path, work: Path, speakers: set[str], say, download: bool = True) -> dict[tuple[str, str], list[Path]]:
    """{(speaker, group): [WAV files]} of the base game's English voices. Never raises: a failure is logged and gives fewer lines."""
    out: dict[tuple[str, str], list[Path]] = {}
    try:
        return _extract(Path(bl2), Path(work), speakers, say, download, out)
    except Exception as e:  # noqa: BLE001 - voices must never stop the install
        say(f"  voices: stopped by {type(e).__name__}: {str(e)[:200]}")
        return out


def _extract(bl2: Path, work: Path, speakers: set[str], say, download: bool, out: dict) -> dict:
    from .bl2 import audio, wwise
    from .bl2.voice import VoiceSet

    banks = bl2 / "WillowGame" / "CookedPCConsole" / "English(US)" / "Audio_Banks.pck"
    if not banks.is_file():
        say(f"  voices: {banks} not found (the English voices are needed); the bandits keep Skyrim's voices")
        return out
    vs = VoiceSet(banks)
    vs.load()
    say(f"  voices: loaded {vs.files}")
    wav_dir = work / "audio" / "voice"
    wav_dir.mkdir(parents=True, exist_ok=True)
    decoder: list = [None, download]
    for speaker in sorted(speakers):
        for group, lines in GROUPS.items():
            files: list[Path] = []
            for line in lines:
                if len(files) >= PER_GROUP:
                    break
                name = f"Ak_Play_VOBD_{speaker}_{line}"
                ident = next((i for _n, i in wwise.event_ids(name) if vs.snd.first(i, (wwise.HIRC_EVENT,)) is not None), None)
                if ident is None:
                    continue
                media = list(dict.fromkeys(m for m in (vs.snd.media_of(s) for s in vs.snd.event_sounds(ident)) if m))
                for m in media:
                    if len(files) >= PER_GROUP:
                        break
                    path = wav_dir / f"{speaker}_{group}_{m:08X}.wav"
                    if not path.is_file():
                        blob = vs.audio(m)
                        if not blob:
                            continue
                        if decoder[0] is None and decoder[1]:
                            decoder[0] = audio.find_decoder(work) or audio.download_decoder(work, say)
                            decoder[1] = False
                        wav = audio.decode(blob, work, f"vo_{speaker}_{m:08X}", decoder[0], say)
                        if not wav:
                            continue
                        path.write_bytes(wav)
                    files.append(path)
            if files:
                out[(speaker, group)] = files
        got = [g for g in GROUPS if (speaker, g) in out]
        say(f"  voices: {speaker}: {sum(len(out[(speaker, g)]) for g in got)} lines in {len(got)} of {len(GROUPS)} groups ({', '.join(got) or 'none'})")
    return out


def _template(m):
    """A vanilla standard sound descriptor to copy: a creature or person's voice-like one first, else any standard one with a category and output model."""
    best = None
    for r in m.by_type.get("SNDR", {}).values():
        cnam = r.first("CNAM")
        if not cnam or struct.unpack("<I", cnam[:4])[0] != 0x1EEF540A or not r.first("ANAM") or not (r.first("GNAM") and r.first("ONAM")):
            continue
        edid = r.edid or ""
        key = (0 if re.search(r"(npc|human).*(vox|voice|pain|death|grunt|attack)|vox", edid, re.I) else 1, len(edid), edid)
        if best is None or key < best[0]:
            best = (key, r)
    return best[1] if best else None


def build(view: esp.Plugin, m, out_data: Path, lines: dict[tuple[str, str], list[Path]], renamed: dict[str, list], names: dict[str, str],
          speakers: dict[str, list[str]], report: dict, log) -> int:
    """Records and the plugin's table. renamed: {Pandora row id: [the bandit NPC overrides of Skylands.esp]}; names: {row id: its name in game}.
    Everything is added at the END of the second plugin so the form ids of what is already there do not move. Returns the number of sound descriptors."""
    from .generate import sndr_prefix

    template = _template(m)
    if not lines or template is None:
        log(f"voices: nothing built ({'no lines were extracted' if not lines else 'no vanilla sound descriptor to copy'}); the bandits keep Skyrim's voices")
        return 0
    style = template.first("ANAM").rstrip(b"\0").decode("latin-1", errors="replace")
    prefix = sndr_prefix(style)
    sound_dir = Path(out_data) / "Sound" / "FX" / "Skylands" / "VO"
    sound_dir.mkdir(parents=True, exist_ok=True)
    ids: dict[tuple[str, str], int] = {}
    for (speaker, group), files in sorted(lines.items()):
        paths = []
        for f in files:
            (sound_dir / Path(f).name).write_bytes(Path(f).read_bytes())
            paths.append(f"{prefix}FX\\Skylands\\VO\\{Path(f).name}")
        edid = f"SkylandsVO_{speaker}_{group}"
        subs, placed = [], False
        for sig, d in template.subrecords:
            if sig == "EDID":
                subs.append(("EDID", esp.zstr(edid)))
            elif sig == "ANAM":
                if not placed:
                    subs += [("ANAM", esp.zstr(p)) for p in paths]
                    placed = True
            else:
                subs.append((sig, d))
        rec = esp.Rec("SNDR", view.new_id(f"SNDR:{edid}"), subs)
        view.override(rec)
        ids[(speaker, group)] = rec.form_id
    log(f"voices: {len(ids)} sound descriptors (copied from {template.edid}, files like {prefix}FX\\Skylands\\VO\\...)")
    # Skyrim's own lines: the renamed bandits get a voice type that no dialogue uses
    silent = view.new("VTYP", SILENT_VOICE)
    silent.add("DNAM", b"\x00")
    silenced = without = 0
    for row_id, recs in renamed.items():
        if row_id not in speakers:
            continue
        for o in recs:
            if o.get("VTCK") is None:
                without += 1  # takes its voice from a template: left alone (the log of the game shows whether it still speaks Skyrim's lines)
                continue
            q = esp.Rec(o.type, o.form_id, [(s, esp.u32(silent.form_id) if s == "VTCK" else d) for s, d in o.subs], o.flags)
            view.override(q)
            silenced += 1
    log(f"voices: {silenced} bandit records silenced (voice type {SILENT_VOICE}); {without} take their voice from a template and keep it")
    # the plugin's table: one speaker per line (its sound descriptors by group, ids without the file), one Pandora name per line (its speakers)
    order = list(GROUPS)
    table = ["# Skylands voices (written by the installer; read by SkylandsNative.dll at data load). Ids are SkylandsGunModels.esp's, without the file.",
             "# speaker <name> " + " ".join(order)]
    used = sorted({s for (s, _g) in ids})
    for s in used:
        table.append(f"speaker {s} " + " ".join(f"{ids.get((s, g), 0) & 0xFFFFFF:06X}" for g in order))
    for row_id, spk in speakers.items():
        have = [s for s in spk if s in used]
        if have and names.get(row_id):
            table.append(f"name {names[row_id]}|{','.join(have)}")
    dest = Path(out_data) / "SKSE" / "Plugins"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / TABLE).write_text("\n".join(table) + "\n", encoding="utf-8")
    report["voices"] = {"descriptors": len(ids), "speakers": used, "silenced": silenced, "names": {names.get(k, k): v for k, v in speakers.items()}}
    log(f"voices: table {TABLE}: {len(used)} speakers, names {[names.get(k) for k in speakers if names.get(k)]}")
    return len(ids)
