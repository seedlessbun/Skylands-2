"""Build a tiny fake Skyrim SE install (Skyrim.esm + Strings in a v105 BSA) for tests.

The records follow Skyrim's real layouts but every value here is made up by the test;
no Skyrim data is in this repository.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import lz4.frame


def sub(sig: str, data: bytes) -> bytes:
    if len(data) > 0xFFFF:
        return b"XXXX" + struct.pack("<HI", 4, len(data)) + sig.encode() + struct.pack("<H", 0) + data
    return sig.encode() + struct.pack("<H", len(data)) + data


def record(rtype: str, form_id: int, subs: list[bytes], compress: bool = False) -> bytes:
    body = b"".join(subs)
    flags = 0
    if compress:
        body = struct.pack("<I", len(body)) + zlib.compress(body)
        flags |= 0x00040000
    return rtype.encode() + struct.pack("<IIIIHH", len(body), flags, form_id, 0, 44, 0) + body


def group(label: str, records: list[bytes]) -> bytes:
    body = b"".join(records)
    return b"GRUP" + struct.pack("<I", 24 + len(body)) + label.encode() + struct.pack("<iHHI", 0, 0, 0, 0) + body


def z(s: str) -> bytes:
    return s.encode("cp1252") + b"\0"


def sid(n: int) -> bytes:
    return struct.pack("<I", n)


def strings_table(entries: dict[int, str], length_prefixed: bool) -> bytes:
    directory, blob = b"", b""
    for k, v in entries.items():
        directory += struct.pack("<II", k, len(blob))
        raw = v.encode("utf-8") + b"\0"
        blob += (struct.pack("<I", len(raw)) + raw) if length_prefixed else raw
    return struct.pack("<II", len(entries), len(blob)) + directory + blob


def bsa105(files: dict[str, bytes]) -> bytes:
    """files: 'folder\\name' -> content. Every file LZ4-compressed (archive flag 0x4)."""
    folders: dict[str, list[tuple[str, bytes]]] = {}
    for path, content in files.items():
        d, n = path.rsplit("\\", 1)
        folders.setdefault(d, []).append((n, content))
    flags = 0x1 | 0x2 | 0x4
    names_blob = b"".join(z(n) for fl in folders.values() for n, _ in fl)
    header_len = 36
    folder_recs_len = 24 * len(folders)
    file_blocks_len = sum(1 + len(d) + 1 + 16 * len(fl) for d, fl in folders.items())
    data_start = header_len + folder_recs_len + file_blocks_len + len(names_blob)
    payloads, offsets = [], []
    pos = data_start
    for fl in folders.values():
        for _n, content in fl:
            comp = struct.pack("<I", len(content)) + lz4.frame.compress(content)
            payloads.append(comp)
            offsets.append((pos, len(comp)))
            pos += len(comp)
    out = b"BSA\0" + struct.pack(
        "<IIIIIIIHH", 105, 36, flags, len(folders), len(files),
        sum(len(d) + 1 for d in folders), len(names_blob), 0, 0,
    )
    for fl in folders.values():
        out += struct.pack("<QIIQ", 0, len(fl), 0, 0)
    k = 0
    for d, fl in folders.items():
        out += bytes([len(d) + 1]) + z(d)
        for _n, _c in fl:
            off, size = offsets[k]
            k += 1
            out += struct.pack("<QII", 0, size, off)
    out += names_blob
    assert len(out) == data_start
    return out + b"".join(payloads)


def ctda_skill_at_least(av_index: int, level: int) -> bytes:
    op = 3 << 5  # >=
    return struct.pack("<B3sfHHIIIIi", op, b"\0\0\0", float(level), 277, 0, av_index, 0, 0, 0, 0)


def build(root: Path) -> Path:
    """Write a fake install under root and return the Skyrim folder."""
    data = root / "Data"
    data.mkdir(parents=True)
    S = {1: "One-Handed", 2: "Armsman", 3: "Nord", 4: "Unrelenting Force", 5: "Fus", 6: "Force",
         7: "Ro", 8: "Balance", 9: "Dah", 10: "Push", 11: "Fighting Stance", 12: "Archery", 13: "Breton"}
    DL = {101: "The art of fighting with one-handed weapons.", 102: "One-handed weapons do 20% more damage.",
          103: "Citizens of Skyrim, tall and fair-haired.", 104: "Your Voice is raw power.",
          105: "Power attacks cost 25% less stamina.", 106: "Breton description."}
    OTHER_NAMES = ["Two-Handed", "Block", "Smithing", "Heavy Armor", "Light Armor", "Pickpocket", "Lockpicking", "Sneak",
                   "Alchemy", "Speech", "Alteration", "Conjuration", "Destruction", "Illusion", "Restoration", "Enchanting"]
    S.update({300 + i: n for i, n in enumerate(OTHER_NAMES)})
    IL = {201: "Hey, you. You're finally awake. You were trying to cross the border, right?", 202: "Other line."}

    armsman1 = record("PERK", 0x000BABE4, [sub("EDID", z("Armsman")), sub("FULL", sid(2)), sub("DESC", sid(102)),
        sub("CTDA", ctda_skill_at_least(6, 0)), sub("DATA", bytes([0, 0, 1, 1, 0])), sub("NNAM", struct.pack("<I", 0x00079342))])
    armsman2 = record("PERK", 0x00079342, [sub("EDID", z("Armsman20")), sub("FULL", sid(2)), sub("DESC", sid(102)),
        sub("CTDA", ctda_skill_at_least(6, 20)), sub("DATA", bytes([0, 0, 1, 1, 0]))])
    stance = record("PERK", 0x00052D52, [sub("EDID", z("FightingStance")), sub("FULL", sid(11)), sub("DESC", sid(105)),
        sub("CTDA", ctda_skill_at_least(6, 20)), sub("DATA", bytes([0, 0, 1, 1, 0]))], compress=True)

    def node(perk: int, index: int, children: list[int]) -> list[bytes]:
        out = [sub("PNAM", struct.pack("<I", perk)), sub("FNAM", struct.pack("<I", 1)), sub("XNAM", struct.pack("<I", index)),
               sub("YNAM", struct.pack("<I", index)), sub("HNAM", struct.pack("<f", 0.5)), sub("VNAM", struct.pack("<f", 0.25)),
               sub("SNAM", struct.pack("<I", 0x44C))]
        out += [sub("CNAM", struct.pack("<I", c)) for c in children]
        return out + [sub("INAM", struct.pack("<I", index))]

    one_handed = record("AVIF", 0x44C, [sub("EDID", z("AVOneHanded")), sub("FULL", sid(1)), sub("DESC", sid(101)),
        sub("CNAM", struct.pack("<I", 0)), sub("AVSK", struct.pack("<4f", 6.3, 0.0, 0.25, 0.0))]
        + node(0, 0, [1]) + node(0x000BABE4, 1, [2]) + node(0x00052D52, 2, []))
    archery = record("AVIF", 0x44E, [sub("EDID", z("AVMarksman")), sub("FULL", sid(12)), sub("DESC", sid(101)),
        sub("AVSK", struct.pack("<4f", 9.3, 0.0, 0.25, 0.0))] + node(0, 0, []))
    health = record("AVIF", 0x3E8, [sub("EDID", z("AVHealth"))])
    others = [record("AVIF", 0x450 + i, [sub("EDID", z(e)), sub("FULL", sid(300 + i)), sub("DESC", sid(101)),
        sub("AVSK", struct.pack("<4f", 2.0, 0.0, 0.25, 0.0))] + node(0, 0, []))
        for i, e in enumerate(["AVTwoHanded", "AVBlock", "AVSmithing", "AVHeavyArmor", "AVLightArmor", "AVPickpocket",
                               "AVLockpicking", "AVSneak", "AVAlchemy", "AVSpeechcraft", "AVAlteration", "AVConjuration",
                               "AVDestruction", "AVMysticism", "AVRestoration", "AVEnchanting"])]

    def race_data(boosts: list[tuple[int, int]], playable: bool) -> bytes:
        pairs = b"".join(bytes([a, b]) for a, b in boosts) + b"\xff\x00" * (7 - len(boosts))
        return pairs + b"\0\0" + struct.pack("<4f", 1, 1, 1, 1) + struct.pack("<I", 1 if playable else 0) + b"\0" * 100

    nord = record("RACE", 0x13746, [sub("EDID", z("NordRace")), sub("FULL", sid(3)), sub("DESC", sid(103)),
        sub("DATA", race_data([(7, 10), (6, 5), (9, 5)], True))])
    breton = record("RACE", 0x13741, [sub("EDID", z("BretonRace")), sub("FULL", sid(13)), sub("DESC", sid(106)),
        sub("DATA", race_data([(21, 10)], True))])
    nord_vampire = record("RACE", 0x88794, [sub("EDID", z("NordRaceVampire")), sub("FULL", sid(3)),
        sub("DATA", race_data([(7, 10)], True))])
    dremora = record("RACE", 0x131F0, [sub("EDID", z("DremoraRace")), sub("FULL", sid(3)),
        sub("DATA", race_data([], False))])

    words = [record("WOOP", 0x13E22, [sub("EDID", z("WordFus")), sub("FULL", sid(5)), sub("TNAM", sid(6))]),
             record("WOOP", 0x13E23, [sub("EDID", z("WordRo")), sub("FULL", sid(7)), sub("TNAM", sid(8))]),
             record("WOOP", 0x13E24, [sub("EDID", z("WordDah")), sub("FULL", sid(9)), sub("TNAM", sid(10))])]
    snam = b"".join(struct.pack("<IIf", w, 0x13E07 + i, r) for i, (w, r) in enumerate([(0x13E22, 15.0), (0x13E23, 20.0), (0x13E24, 45.0)]))
    shout = record("SHOU", 0x13E07, [sub("EDID", z("UnrelentingForceShout")), sub("FULL", sid(4)), sub("DESC", sid(104)), sub("SNAM", snam)])

    gmsts = [record("GMST", 0x100 + i, [sub("EDID", z(n)), sub("DATA", d)]) for i, (n, d) in enumerate([
        ("fXPLevelUpBase", struct.pack("<f", 75.0)), ("fXPLevelUpMult", struct.pack("<f", 25.0)),
        ("fXPPerSkillRank", struct.pack("<f", 1.0)), ("fSkillUseCurve", struct.pack("<f", 1.95)),
        ("iAVDSkillStart", struct.pack("<i", 15)), ("sSomethingElse", sid(999))])]

    tes4 = record("TES4", 0, [sub("HEDR", struct.pack("<fII", 1.7, 0, 0))])
    tes4 = tes4[:8] + struct.pack("<I", 0x81) + tes4[12:]  # master + localized
    esm = tes4 + group("GMST", gmsts) + group("NPC_", [record("NPC_", 7, [sub("EDID", z("Player"))])]) \
        + group("RACE", [nord, breton, nord_vampire, dremora]) + group("AVIF", [one_handed, archery, health, *others]) \
        + group("PERK", [armsman1, armsman2, stance]) + group("WOOP", words) + group("SHOU", [shout])
    (data / "Skyrim.esm").write_bytes(esm)
    (data / "Skyrim - Interface.bsa").write_bytes(bsa105({
        "strings\\skyrim_english.strings": strings_table(S, False),
        "strings\\skyrim_english.dlstrings": strings_table(DL, True),
        "strings\\skyrim_english.ilstrings": strings_table(IL, True),
        "interface\\fonts_en.swf": b"not used",
    }))
    return root


def build_full(root: Path) -> Path:
    """build() plus everything the Skylands generator reads: masters, crossbow, bolts, effects, bandits, loot."""
    root = build(root)
    data = root / "Data"
    esm = bytearray((data / "Skyrim.esm").read_bytes())
    extra = []
    mgefs = ["InvisibillityFFSelf", "ParalysisFFAimed", "SummonStormAtronach", "SummonFrostAtronach", "AlchFortifyMarksman",
             "AlchFortifyHealRate", "AlchFortifyOneHanded", "AlchFortifyTwoHanded", "AbWeaknessFireConstant", "AbFortifyHealth"]
    extra.append(group("MGEF", [record("MGEF", 0x5000 + i, [sub("EDID", z(e)), sub("DATA", b"\0" * 152)]) for i, e in enumerate(mgefs)]))
    enchs = ["EnchWeaponFireDamage03", "EnchWeaponShockDamage03", "EnchWeaponAbsorbHealth02", "EnchWeaponMagickaDamage03"]
    extra.append(group("ENCH", [record("ENCH", 0x6000 + i, [sub("EDID", z(e)), sub("FULL", sid(3)), sub("ENIT", b"\0" * 36), sub("EFID", struct.pack("<I", 0x5000)),
                                                       sub("EFIT", struct.pack("<fII", 10.0, 0, 0))]) for i, e in enumerate(enchs)]))
    light = struct.pack("<iI4sIffffffIf", -1, 256, bytes([255, 255, 255, 0]), 1, 1.0, 90.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0)
    extra.append(group("LIGH", [record("LIGH", 0x7100, [sub("EDID", z("FXPlainLight")), sub("OBND", b"\0" * 12), sub("DATA", light),
                                                        sub("FNAM", struct.pack("<f", 1.0))]),
                                record("LIGH", 0x7101, [sub("EDID", z("AAFlickerLight")), sub("MODL", z("x.nif")), sub("DATA", light)])]))
    spit = struct.pack("<IIIfIIffI", 0, 0, 11, 0.0, 1, 2, 0.0, 0.0, 0)
    extra.append(group("SPEL", [record("SPEL", 0x13E07, [sub("EDID", z("VoicePush1")), sub("ETYP", struct.pack("<I", 0x25BEE)), sub("SPIT", spit)])]))
    extra.append(group("EQUP", [record("EQUP", 0x25BEE, [sub("EDID", z("VoiceEquipSlot"))])]))
    npcs = [record("NPC_", 0x7000, [sub("EDID", z("EncBandit02TemplateMelee")), sub("FULL", sid(3)), sub("SHRT", sid(3)),
                                    sub("ACBS", b"\0" * 24), sub("SPCT", struct.pack("<I", 1)), sub("SPLO", struct.pack("<I", 0x5001))]),
            record("NPC_", 0x7001, [sub("EDID", z("EncBandit02Melee1HNordM")), sub("ACBS", b"\0" * 24)]),
            record("NPC_", 0x7002, [sub("EDID", z("EncBandit03Boss1HNordM")), sub("FULL", sid(3)), sub("ACBS", b"\0" * 24)])]
    extra.append(group("NPC_", npcs))
    lv = struct.pack("<HHIHH", 1, 0, 0x1234, 1, 0)
    def sndr(form_id, edid):
        return record("SNDR", form_id, [sub("EDID", z(edid)), sub("CNAM", struct.pack("<I", 0x1EEF540A)), sub("GNAM", struct.pack("<I", 0x3E00)),
                                        sub("ANAM", z("fx\\wpn\\crossbow\\" + edid.lower() + ".wav")), sub("ONAM", struct.pack("<I", 0x3F00))])

    extra.append(group("SNDR", [sndr(0x9100, "WPNCrossbowFire"), sndr(0x9101, "WPNCrossbowReload"), sndr(0x9102, "WPNBowFireShort")]))
    extra.append(group("LVLI", [record("LVLI", 0x8000, [sub("EDID", z("LootBanditChestBossBase")), sub("LVLD", b"\x00"), sub("LVLF", b"\x01"),
                                                        sub("LLCT", b"\x01"), sub("LVLO", lv)])]))
    # a vanilla-style staff: animation type 8, an enchantment whose effect flies a projectile (the staff-type gun copies it)
    bolt_md = bytearray(152)
    struct.pack_into("<I", bolt_md, 0, 0x5)  # hostile and detrimental, as a vanilla damage staff effect is
    struct.pack_into("<f", bolt_md, 4, 25.0)
    for at in (24, 32, 36, 92, 96, 108, 116):  # casting light, hit shader, enchant shader, casting art, hit art, dual casting art, enchant art
        struct.pack_into("<I", bolt_md, at, 0x7800 + at)
    struct.pack_into("<II", bolt_md, 72, 0x7200, 0x7300)
    struct.pack_into("<II", bolt_md, 80, 1, 2)  # fire and forget, aimed
    extra.append(group("MGEF", [record("MGEF", 0x5100, [sub("EDID", z("EnchStaffFireballFFAimed")), sub("FULL", sid(1)),
                                                        sub("DNAM", sid(2)), sub("DATA", bytes(bolt_md))])]))
    extra.append(group("PROJ", [record("PROJ", 0x7200, [sub("EDID", z("StaffFireballProjectile")), sub("OBND", b"\0" * 12),
                                                        sub("DATA", struct.pack("<HHfffIIfffIIfffIIIffffII", 0x2, 0x1, 0.0, 1500.0, 3000.0, 0, 0, 0.0, 0.0, 0.0, 0, 0x7300,
                                                                                0.0, 0.0, 0.0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0, 0))])]))
    staff_enit = struct.pack("<iIIfIIfII", 80, 0, 1, 0.0, 2, 12, 0.0, 0, 0)
    extra.append(group("ENCH", [record("ENCH", 0x6100, [sub("EDID", z("EnchStaffFireball")), sub("FULL", sid(3)), sub("ENIT", staff_enit),
                                                        sub("EFID", struct.pack("<I", 0x5100)), sub("EFIT", struct.pack("<fII", 40.0, 0, 0))])]))
    extra.append(group("WEAP", [record("WEAP", 0x7400, [sub("EDID", z("StaffFireball")), sub("OBND", b"\0" * 12), sub("FULL", sid(1)),
                                                        sub("MODL", z("weapons\\staff\\staff.nif")), sub("EITM", struct.pack("<I", 0x6100)),
                                                        sub("EAMT", struct.pack("<H", 1000)), sub("ETYP", struct.pack("<I", 1)),
                                                        sub("DESC", sid(2)), sub("DATA", struct.pack("<IfH", 100, 8.0, 8)),
                                                        sub("DNAM", struct.pack("<BBHff", 8, 0, 0, 1.0, 1.0) + b"\0" * 92), sub("CRDT", b"\0" * 24),
                                                        sub("CNAM", struct.pack("<I", 0x7401))])]))
    # a vanilla-style concentration effect (Flames): an aimed continuous cast whose projectile is a flame
    conc_md = bytearray(bolt_md)
    struct.pack_into("<I", conc_md, 0, 0x5)  # hostile, detrimental
    struct.pack_into("<II", conc_md, 72, 0x7201, 0)
    struct.pack_into("<II", conc_md, 80, 2, 2)  # concentration, aimed
    struct.pack_into("<II", conc_md, 32, 0x7777, 0x7778)  # hit shader, enchant shader
    extra.append(group("MGEF", [record("MGEF", 0x5102, [sub("EDID", z("FireDamageConcAimed")), sub("FULL", sid(1)),
                                                        sub("DNAM", sid(2)), sub("DATA", bytes(conc_md))])]))
    extra.append(group("PROJ", [record("PROJ", 0x7201, [sub("EDID", z("FlamesProjectile")), sub("OBND", b"\0" * 12),
                                                        sub("MODL", z("effects\\flames.nif")), sub("MODT", b"\0" * 12), sub("NAM1", z("effects\\flash.nif")),
                                                        sub("DATA", struct.pack("<HHfffIIfffIIfffIIIffffII", 0x8, 0x2, 0.0, 800.0, 1000.0, 0x7779, 0x777A, 0.0, 0.0, 0.0, 0, 0x777B,
                                                                                0.0, 0.0, 0.0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0, 0))])]))
    art_md = bytearray(bolt_md)
    struct.pack_into("<I", art_md, 64, 3)  # a script-archetype effect, like the Wabbajack's
    extra.append(group("MGEF", [record("MGEF", 0x5101, [sub("EDID", z("AAWabbajackFF")), sub("VMAD", b"\x05\x00\x02\x00\x00\x00"), sub("DATA", bytes(art_md))])]))
    extra.append(group("ENCH", [record("ENCH", 0x6101, [sub("EDID", z("AAStaffEnchWabbajack")), sub("ENIT", staff_enit),
                                                        sub("EFID", struct.pack("<I", 0x5101)), sub("EFIT", struct.pack("<fII", 1.0, 0, 0))])]))
    extra.append(group("WEAP", [record("WEAP", 0x7401, [sub("EDID", z("AAWabbajack")), sub("OBND", b"\0" * 12), sub("FULL", sid(1)),
                                                        sub("MODL", z("weapons\\staff\\w.nif")), sub("EITM", struct.pack("<I", 0x6101)),
                                                        sub("DATA", struct.pack("<IfH", 100, 8.0, 8)),
                                                        sub("DNAM", struct.pack("<BBHff", 8, 0, 0, 1.0, 1.0) + b"\0" * 92)])]))
    (data / "Skyrim.esm").write_bytes(bytes(esm) + b"".join(extra))
    tes = record("TES4", 0, [sub("HEDR", struct.pack("<fII", 1.7, 0, 0)), sub("MAST", z("Skyrim.esm")), sub("DATA", b"\0" * 8)])
    tes = tes[:8] + struct.pack("<I", 0x81) + tes[12:]
    # Update.esm overrides the loot list (adds an entry); the generator must build on this newer version.
    lv2 = struct.pack("<HHIHH", 1, 0, 0x1235, 1, 0)
    (data / "Update.esm").write_bytes(tes + group("LVLI", [record("LVLI", 0x8000, [
        sub("EDID", z("LootBanditChestBossBase")), sub("LVLD", b"\x00"), sub("LVLF", b"\x01"), sub("LLCT", b"\x02"), sub("LVLO", lv), sub("LVLO", lv2)])]))
    tes_dg = record("TES4", 0, [sub("HEDR", struct.pack("<fII", 1.7, 0, 0)), sub("MAST", z("Skyrim.esm")), sub("DATA", b"\0" * 8),
                                sub("MAST", z("Update.esm")), sub("DATA", b"\0" * 8)])
    tes_dg = tes_dg[:8] + struct.pack("<I", 0x81) + tes_dg[12:]
    weap = record("WEAP", 0x02000800, [sub("EDID", z("DLC1Crossbow")), sub("OBND", b"\0" * 12), sub("FULL", sid(1)),
                                       sub("MODL", z("dlc01\\weapons\\crossbow\\crossbow.nif")), sub("ETYP", struct.pack("<I", 1)),
                                       sub("DESC", sid(2)), sub("DATA", struct.pack("<IfH", 120, 14.0, 19)),
                                       sub("DNAM", struct.pack("<BBHff", 9, 0, 0, 1.0, 1.0) + b"\0" * 92), sub("CRDT", b"\0" * 24)], compress=True)
    proj = record("PROJ", 0x02000802, [sub("EDID", z("DLC1BoltProjectile")), sub("OBND", b"\0" * 12),
                                       sub("DATA", struct.pack("<HHfffIIfffIIfffIIIffffII", 0x40, 0x40, 0.2, 4000.0, 6000.0, 0, 0, 0.0, 0.0, 0.0, 0, 0,
                                                               0.0, 0.0, 0.0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0, 0))])
    ammo = record("AMMO", 0x02000801, [sub("EDID", z("DLC1BoltSteel")), sub("FULL", sid(1)),
                                       sub("DATA", struct.pack("<IIfI", 0x02000802, 0, 8.0, 1))])
    expl = record("EXPL", 0x02000803, [sub("EDID", z("DLC1BoltExplosionFrost02")), sub("OBND", b"\0" * 12), sub("MODL", z("fx\\blast.nif")),
                                       sub("DATA", b"\0" * 52)])
    (data / "Dawnguard.esm").write_bytes(tes_dg + group("WEAP", [weap]) + group("AMMO", [ammo]) + group("PROJ", [proj]) + group("EXPL", [expl]))
    return root
