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


GAIN = 1.35  # the lines are this much louder than BL2's files (0.47.0: noticeably quieter than Skyrim's own voices)


def louder(wav: bytes, gain: float) -> bytes:
    """A 16-bit PCM WAV with every sample times gain (clipped); anything else is returned as it is."""
    if len(wav) < 12 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE" or gain == 1.0:
        return wav
    out = bytearray(wav)
    pos, bits = 12, 0
    while pos + 8 <= len(out):
        cid, size = bytes(out[pos:pos + 4]), struct.unpack_from("<I", out, pos + 4)[0]
        body = pos + 8
        if cid == b"fmt " and size >= 16:
            fmt, bits = struct.unpack_from("<H", out, body)[0], struct.unpack_from("<H", out, body + 14)[0]
            if fmt != 1:
                return wav
        elif cid == b"data" and bits == 16:
            n = min(size, len(out) - body) // 2
            samples = struct.unpack_from(f"<{n}h", out, body)
            struct.pack_into(f"<{n}h", out, body, *(max(-32768, min(32767, int(round(v * gain)))) for v in samples))
            return bytes(out)
        pos = body + size + (size & 1)
    return wav


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
            (sound_dir / Path(f).name).write_bytes(louder(Path(f).read_bytes(), GAIN))
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
    # Skyrim's own lines: the renamed bandits get a voice type that no dialogue uses. A record with no voice of its own speaks with its race's default voice
    # (it gets the silent one too); a record that takes its traits from a template (ACBS template flag "traits") speaks with the template's voice, so the
    # template is silenced as well (an NPC, or every NPC of a leveled list, followed a few steps)
    silent = view.new("VTYP", SILENT_VOICE)
    silent.add("DNAM", b"\x00")
    done: set[int] = set()
    count = {"own": 0, "race": 0, "template": 0, "named": 0}

    def silence(rec, why: str) -> None:
        if rec.form_id in done:
            return
        done.add(rec.form_id)
        subs = list(rec.subs if hasattr(rec, "subs") else rec.subrecords)
        if any(sg == "VTCK" for sg, _d in subs):
            subs = [(sg, esp.u32(silent.form_id) if sg == "VTCK" else d) for sg, d in subs]
        else:  # after the fields that come before it in an NPC record
            at = max((i + 1 for i, (sg, _d) in enumerate(subs) if sg in ("EDID", "VMAD", "OBND", "ACBS", "SNAM", "INAM")), default=len(subs))
            subs.insert(at, ("VTCK", esp.u32(silent.form_id)))
        view.override(esp.Rec(rec.type, rec.form_id, subs, rec.flags & esp.REC_COMPRESSED))
        count[why] += 1

    def traits_template(rec) -> int:
        """The form id the record takes its traits (and voice) from, else 0."""
        acbs = rec.get("ACBS") if hasattr(rec, "get") else rec.first("ACBS")
        tplt = rec.get("TPLT") if hasattr(rec, "get") else rec.first("TPLT")
        if not acbs or len(acbs) < 20 or not tplt:
            return 0
        flags = struct.unpack_from("<H", acbs, 18)[0]
        return struct.unpack("<I", tplt[:4])[0] if flags & 1 else 0

    def follow(fid: int, depth: int, seen: set[int]) -> list:
        """The NPC records whose voice a template id stands for."""
        if not fid or depth > 4 or fid in seen:
            return []
        seen.add(fid)
        npc = mine.get(fid) or m.by_type.get("NPC_", {}).get(fid)  # a renamed one as Skylands.esp has it (its name and ability kept)
        if npc is not None:
            inner = traits_template(npc)
            return follow(inner, depth + 1, seen) if inner else [npc]
        lvln = m.by_type.get("LVLN", {}).get(fid)
        out = []
        if lvln is not None:
            for d in lvln.all("LVLO"):
                if len(d) >= 8:
                    out += follow(struct.unpack_from("<I", d, 4)[0], depth + 1, seen)
        return out

    for row_id in speakers:
        if row_id not in renamed:
            log(f"voices: sheet row {row_id} renamed no record (its Borderlands name was not read, or no NPC matched its editor id pattern): it has no voice")
            if row_id == "boss":  # which bandit boss records the game has (to correct the pattern)
                bosses = sorted(r.edid + ("" if r.first("FULL") is None else " (named)") for r in m.by_type.get("NPC_", {}).values() if re.search(r"(?i)bandit.*boss|boss.*bandit", r.edid))
                log(f"voices:   bandit boss records in the game ({len(bosses)}): {', '.join(bosses[:30])}")
    mine = {o.form_id: o for recs in renamed.values() for o in recs}
    looked = 0
    for row_id, recs in renamed.items():
        if row_id not in speakers:
            continue
        for o in recs:
            vtck = o.get("VTCK")
            tid = traits_template(o)
            if looked < 60:
                edid = (o.get("EDID") or b"").rstrip(b"\0").decode("cp1252", "replace")
                own = f"its own voice {struct.unpack('<I', vtck[:4])[0]:08X}" if vtck else "no voice of its own (the race's default)"
                log(f"voices: {edid} {o.form_id:08X}: {own}" + (f", traits from template {tid:08X}" if tid else ""))
                looked += 1
            if tid:
                targets = follow(tid, 0, set())
                if looked <= 60:
                    log(f"voices:   template {tid:08X} -> {len(targets)} record(s) silenced with it")
                for t in targets:
                    silence(t, "template")
                silence(o, "template")  # its own voice does not count, but a mod may turn the flag off
            elif vtck is None:
                silence(o, "race")
            else:
                silence(o, "own")
    # 0.48.0: the bandits that spawn are mostly NOT the renamed records: Skyrim's EncBanditNN... people take their NAME from a renamed template
    # (template flag "base data") through an NPC or a leveled list, but keep their OWN voice (no "traits" flag), so they showed a Pandora name and still
    # spoke Skyrim's lines (0.47.0 log: "Killer Marauder" with voice types 00013ADD, 0009843B, ...). Every NPC whose template chain reaches a renamed record is silenced.
    chains: dict[int, bool] = {}

    def reaches(fid: int, depth: int) -> bool:
        if fid in mine:
            return True
        if not fid or depth > 6:
            return False
        if fid in chains:
            return chains[fid]
        chains[fid] = False  # a loop reaches nothing
        npc = m.by_type.get("NPC_", {}).get(fid)
        got = False
        if npc is not None:
            tplt = npc.first("TPLT")
            got = bool(tplt) and reaches(struct.unpack("<I", tplt[:4])[0], depth + 1)
        else:
            lvln = m.by_type.get("LVLN", {}).get(fid)
            if lvln is not None:
                got = any(len(d) >= 8 and reaches(struct.unpack_from("<I", d, 4)[0], depth + 1) for d in lvln.all("LVLO"))
        chains[fid] = got
        return got

    shown = 0
    for npc in list(m.by_type.get("NPC_", {}).values()):
        if npc.form_id in mine or npc.form_id in done:
            continue
        tplt, acbs = npc.first("TPLT"), npc.first("ACBS")
        if not tplt or not acbs or len(acbs) < 20 or not struct.unpack_from("<H", acbs, 18)[0] & 0x80:  # 0x80: name (base data) from the template
            continue
        if not reaches(struct.unpack("<I", tplt[:4])[0], 0):
            continue
        if shown < 40:
            vt = npc.first("VTCK")
            log(f"voices: {npc.edid} {npc.form_id:08X} takes a Pandora name from template {struct.unpack('<I', tplt[:4])[0]:08X} and spoke with "
                + (f"its own voice {struct.unpack('<I', vt[:4])[0]:08X}" if vt else "its race's voice") + ": silenced")
            shown += 1
        silence(npc, "named")
    silenced = sum(count.values())
    log(f"voices: {silenced} records silenced (voice type {SILENT_VOICE}): {count['own']} with their own voice, {count['race']} that spoke with their race's voice, "
        f"{count['template']} through a template, {count['named']} that take a Pandora name from a template")
    # the plugin's table: one speaker per line (its sound descriptors by group, ids without the file), one Pandora name per line (its speakers)
    order = list(GROUPS)
    table = ["# Skylands voices (written by the installer; read by SkylandsNative.dll at data load). Ids are SkylandsGunModels.esp's, without the file.",
             "# speaker <name> " + " ".join(order),
             f"silent {silent.form_id & 0xFFFFFF:06X}"]
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
