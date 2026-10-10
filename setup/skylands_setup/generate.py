"""Build Skylands' Skyrim files from the player's two games.

Inputs: the extracted Borderlands 2 data (bl2.extract) and the player's Skyrim install.
Outputs (under out/Data): Skylands.esp, Scripts/*.pex, Meshes/Skylands/*.nif, Textures/Skylands/*.dds.

Records Skylands changes are copied from the player's own Skyrim masters (latest version among
Skyrim.esm, Update.esm, Dawnguard.esm, which is also this plugin's master order, so form ids need
no remapping) and edited: nothing of Skyrim is shipped.
"""

from __future__ import annotations

import random
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from . import sheet_data as S
from . import stats
from .skyrim import esp, nif, pex, scripts
from .skyrim.esm import Record, read_plugin

MASTERS = ["Skyrim.esm", "Update.esm", "Dawnguard.esm"]
PLUGIN = "Skylands.esp"
BEAM_TEXTURE = "textures\\skylands\\beam.dds"
LIST_LIMIT = 200  # entries per leveled list (Skyrim allows 255)

# SPIT spell types / cast types / delivery (Skyrim SE)
SPELL_ABILITY, CAST_CONSTANT, DELIVERY_SELF = 4, 0, 0
DELIVERY = {"self": 0, "aimed": 2}
QUEST_START_GAME_ENABLED = 0x0001

# Subrecord order Skyrim expects (insertions go after the last present signature before them).
WEAP_ORDER = ["EDID", "VMAD", "OBND", "FULL", "MODL", "MODT", "MODS", "EITM", "EAMT", "ETYP", "BIDS", "BAMT",
              "YNAM", "ZNAM", "KSIZ", "KWDA", "DESC", "INAM", "WNAM", "SNAM", "XNAM", "NAM7", "TNAM", "UNAM",
              "NAM9", "NAM8", "DATA", "DNAM", "CRDT", "VNAM", "CNAM"]


class GenerateError(RuntimeError):
    pass


@dataclass
class Masters:
    """Latest version of every record of the wanted types across the three masters."""

    by_type: dict[str, dict[int, Record]] = field(default_factory=dict)

    @classmethod
    def load(cls, data_dir: Path, types: set[str]) -> Masters:
        m = cls({t: {} for t in types})
        for name in MASTERS:
            p = data_dir / name
            if not p.is_file():
                raise GenerateError(f"{name} not found in {data_dir}")
            _, recs = read_plugin(p, types)
            for t, rs in recs.items():
                for r in rs:
                    m.by_type[t][r.form_id] = r
        return m

    def find(self, rtype: str, edid: str) -> Record | None:
        if edid.startswith("^"):
            rx = re.compile(edid, re.I)
            return next((r for r in self.by_type[rtype].values() if rx.search(r.edid)), None)
        return next((r for r in self.by_type[rtype].values() if r.edid.lower() == edid.lower()), None)

    def need(self, rtype: str, edid: str) -> Record:
        r = self.find(rtype, edid)
        if r is None:
            raise GenerateError(f"{rtype} {edid} not found in the player's Skyrim masters")
        return r


def copy(rec: Record, new_type: str | None = None) -> esp.Rec:
    return esp.Rec(new_type or rec.type, rec.form_id, list(rec.subrecords), flags=rec.flags & esp.REC_COMPRESSED)


def insert_ordered(rec: esp.Rec, sig: str, data: bytes, order: list[str]) -> None:
    rec.drop(sig)
    pos = order.index(sig)
    at = 0
    for i, (s, _) in enumerate(rec.subs):
        if s in order and order.index(s) < pos:
            at = i + 1
    rec.subs.insert(at, (sig, data))


def u16(v: int) -> bytes:
    return struct.pack("<H", v)


def obnd() -> bytes:
    return b"\0" * 12


def lvlo(form_id: int, count: int = 1, level: int = 1) -> bytes:
    return struct.pack("<HHIHH", level, 0, form_id, count, 0)


def leveled_list(p: esp.Plugin, edid: str, entries: list[tuple[int, int]], flags: int = 0x3) -> esp.Rec:
    """entries: (form id, count). Lists longer than the limit nest into sub-lists."""
    if len(entries) > LIST_LIMIT:
        subs = [entries[i : i + LIST_LIMIT] for i in range(0, len(entries), LIST_LIMIT)]
        entries = [(leveled_list(p, f"{edid}_{k}", chunk, flags).form_id, 1) for k, chunk in enumerate(subs)]
    r = p.new("LVLI", edid)
    r.add("OBND", obnd()).add("LVLD", bytes([0])).add("LVLF", bytes([flags])).add("LLCT", bytes([len(entries)]))
    for fid, count in entries:
        r.add("LVLO", lvlo(fid, count))
    return r


def spell(p: esp.Plugin, edid: str, name: str, desc: str, spit: bytes, effects: list[tuple[int, float, int, int]],
          etyp: int | None = None) -> esp.Rec:
    r = p.new("SPEL", edid).add("OBND", obnd())
    if name:
        r.add("FULL", esp.zstr(name))
    r.add("MDOB", esp.u32(0))
    if etyp is not None:
        r.add("ETYP", esp.u32(etyp))
    r.add("DESC", esp.zstr(desc)).add("SPIT", spit)
    for mgef, mag, area, dur in effects:
        r.add("EFID", esp.u32(mgef)).add("EFIT", struct.pack("<fII", mag, area, dur))
    return r


def parse_effects(text: str) -> list[tuple[str, float]]:
    out = []
    for part in text.split(";"):
        part = part.strip()
        if part and part != "-":
            edid, _, mag = part.partition(":")
            out.append((edid, float(mag or 0)))
    return out


def scale_efit(data: bytes, mult: float) -> bytes:
    """EFIT = magnitude (f32), area (u32), duration (u32): scale the magnitude."""
    if len(data) < 4:
        return data
    return struct.pack("<f", round(struct.unpack_from("<f", data)[0] * mult, 2)) + data[4:]


def rarity_row(level: int):
    return next((r for r in S.RARITIES.values() if r.level == level), S.RARITIES["legendary"])


def rarity_color(colors: list[dict], level: int) -> tuple[int, int, int]:
    for c in colors:
        if c.get("min") is not None and c["min"] <= level <= (c.get("max") or c["min"]):
            return tuple(c["rgb"])
    raise GenerateError(f"no Borderlands rarity colour for level {level}")


def gun_name(g: dict, element: str | None, manufacturers: dict) -> str:
    if g["rarity"] == 5 and g.get("unique_name"):
        base = g["unique_name"]
    else:
        lead = g["element_prefixes"].get(element) if element else manufacturers.get(g["manufacturer"], g["manufacturer"])
        base = f"{lead} {g['title']}".strip()
    return f"{base} ({rarity_row(g['rarity']).word})"


AV_VARIABLE10 = 77  # an actor value nothing uses: the stats effect only displays numbers
MGEF_AV_AT = 68
MGEF_ART_AT = (24, 32, 36, 72, 76, 92, 96, 100, 108, 116, 128, 132, 136)  # light, shaders, projectile, arts, ability, perk


def stats_template(m: Masters, base_ench: Record) -> Record:
    """The magic effect of a vanilla weapon enchantment, to be stripped into a display-only effect."""
    efid = base_ench.first("EFID")
    mg = m.by_type["MGEF"].get(struct.unpack_from("<I", efid)[0]) if efid else None
    if mg is None:
        raise GenerateError("the effect of the vanilla weapon enchantments was not found")
    return mg


def stats_effect(p: esp.Plugin, edid: str, text: str, template: Record) -> int:
    """A new magic effect that does nothing but show the gun's stats on its enchantment."""
    r = esp.Rec("MGEF", p.new_id(), [])
    r.add("EDID", esp.zstr(f"Skylands_Stats_{edid}")).add("FULL", esp.zstr("Gun stats")).add("DNAM", esp.zstr(text))
    data = bytearray(template.first("DATA") or b"\0" * 152)
    if len(data) >= MGEF_AV_AT + 4:
        struct.pack_into("<i", data, MGEF_AV_AT, AV_VARIABLE10)
        for at in MGEF_ART_AT:
            if len(data) >= at + 4:
                struct.pack_into("<I", data, at, 0)
    r.add("DATA", bytes(data))
    p.override(r)
    return r.form_id


def gun_enchant(p: esp.Plugin, edid: str, st: dict, donor: Record, with_element: bool, element_word: str | None,
                template: Record) -> int:
    """One enchantment per gun: the vanilla element effect scaled by the gun's roll, plus its stats line."""
    head, effects = [], []
    for sig, d in donor.subrecords:
        if sig == "EFID":
            effects.append([(sig, d)])
        elif effects:
            effects[-1].append((sig, d))
        else:
            head.append((sig, d))
    e = esp.Rec("ENCH", p.new_id(), [(sig, d) for sig, d in head if sig not in ("EDID", "FULL")])
    e.subs.insert(0, ("EDID", esp.zstr(f"Skylands_Ench_{edid}")))
    insert_ordered(e, "FULL", esp.zstr("Gun stats"), ["EDID", "VMAD", "OBND", "FULL", "ENIT"])
    if with_element:
        for group in effects:
            e.subs.extend((sig, scale_efit(d, st["element_mult"]) if sig == "EFIT" else d) for sig, d in group)
    mg = stats_effect(p, edid, stats.describe(st, element_word), template)
    e.add("EFID", esp.u32(mg)).add("EFIT", struct.pack("<fII", 0.0, 0, 0))
    p.override(e)
    return e.form_id


def generate(bl2: dict, skyrim_dir: Path, out_dir: Path, seed: int = 4) -> dict:
    data_dir = Path(skyrim_dir) / "Data"
    m = Masters.load(data_dir, {"WEAP", "AMMO", "NPC_", "LVLI", "MGEF", "ENCH", "EQUP", "SHOU", "WOOP", "SPEL"})
    p = esp.Plugin(PLUGIN, MASTERS)
    report: dict = {"guns": 0, "renamed_enemies": 0, "loot_lists": 0, "classes": []}
    rnd = random.Random(seed)

    # ---- loot beams (one activator per rarity level, coloured from Borderlands' table) ------
    out_data = Path(out_dir) / "Data"
    (out_data / "Meshes" / "Skylands").mkdir(parents=True, exist_ok=True)
    (out_data / "Textures" / "Skylands").mkdir(parents=True, exist_ok=True)
    (out_data / "Scripts").mkdir(parents=True, exist_ok=True)
    (out_data / "Textures" / "Skylands" / "beam.dds").write_bytes(nif.dds_gradient())
    beams: dict[int, int] = {}
    for row in S.RARITIES.values():
        color = rarity_color(bl2["rarities"], row.level)
        mesh = f"Skylands\\Beam_{row.id}.nif"
        (out_data / "Meshes" / "Skylands" / f"Beam_{row.id}.nif").write_bytes(nif.beam(color, BEAM_TEXTURE))
        beam = p.new("ACTI", f"SkylandsBeam_{row.id}")
        beam.add("VMAD", esp.vmad([("SkylandsLootBeam", [])])).add("OBND", obnd()).add("MODL", esp.zstr(mesh))
        beams[row.level] = beam.form_id
    # Keywords the scripts look for: one on every Skylands gun, and one per rarity (picks the beam).
    gun_keyword = p.new("KYWD", "SkylandsGun").form_id
    rarity_keywords = {row.level: p.new("KYWD", f"SkylandsRarity_{row.id}").form_id for row in S.RARITIES.values()}

    # ---- guns ---------------------------------------------------------------------------------
    crossbow = m.need("WEAP", S.SKYRIM_BASE["crossbow"].edid)
    bolts = m.need("AMMO", S.SKYRIM_BASE["bolts"].edid)
    base_enchant = {e.bl2_part: m.need("ENCH", e.skyrim_enchantment) for e in S.ELEMENTS.values()}
    any_enchant = next(iter(base_enchant.values()))
    stats_mgef = stats_template(m, any_enchant)

    gun_types = {g.id: g for g in S.GUN_TYPES.values()}
    by_rarity: dict[int, list[int]] = {}
    starters: list[int] = []
    for g in bl2["weapons"]["guns"]:
        gt = gun_types[g["type"]]
        rr = rarity_row(g["rarity"])
        type_scales = [x["damage_scale"] for x in bl2["weapons"]["guns"] if x["type"] == g["type"]] or [1.0]
        scale = g["damage_scale"] / (sum(type_scales) / len(type_scales)) if g["damage_scale"] else 1.0
        damage = max(1, round(gt.base_damage * rr.damage_mult * min(1.5, max(0.7, scale))))
        value = round(gt.base_value * rr.value_mult)
        for element in [None, *g["elements"]]:
            w = copy(crossbow)
            edid = f"Skylands_{g['balance'].rsplit('.', 1)[1]}{'_' + element if element else ''}"
            w.form_id = p.new_id()
            w.drop("DESC", "EITM", "EAMT", "VMAD")
            w.set("EDID", esp.zstr(edid))
            insert_ordered(w, "FULL", esp.zstr(gun_name(g, element, bl2["weapons"]["manufacturers"])), WEAP_ORDER)
            kwda = w.get("KWDA") or b""
            keywords = [*struct.unpack(f"<{len(kwda) // 4}I", kwda), gun_keyword, rarity_keywords[rr.level]]
            insert_ordered(w, "KSIZ", struct.pack("<I", len(keywords)), WEAP_ORDER)
            insert_ordered(w, "KWDA", struct.pack(f"<{len(keywords)}I", *keywords), WEAP_ORDER)
            st = stats.roll(edid, gt, rr, element is not None)
            ench = gun_enchant(p, edid, st, base_enchant.get(element) or any_enchant, element is not None, element, stats_mgef)
            insert_ordered(w, "EITM", esp.u32(ench), WEAP_ORDER)
            insert_ordered(w, "EAMT", u16(65535), WEAP_ORDER)
            d = w.get("DATA") or b"\0" * 10
            insert_ordered(w, "DATA", struct.pack("<IfH", value, float(gt.weight), damage) + d[10:], WEAP_ORDER)
            dn = w.get("DNAM")
            if dn and len(dn) >= 12:  # the rolled animation speed rides in the gun's (otherwise unused) reach
                w.set("DNAM", dn[:8] + struct.pack("<f", st["speed"]) + dn[12:])
            crit = w.get("CRDT")
            if crit and len(crit) >= 2:
                w.set("CRDT", u16(st["crit_damage"]) + crit[2:])
            p.override(w)
            by_rarity.setdefault(rr.level, []).append(w.form_id)
            if g["type"] == "pistol" and rr.level == 1 and element is None:
                starters.append(w.form_id)
            report["guns"] += 1
            report.setdefault("stats", {})[edid] = {k: v for k, v in st.items() if v is not None}
    if not by_rarity:
        raise GenerateError("no Borderlands guns were extracted")

    tier_lists = {lvl: leveled_list(p, f"SkylandsGuns_{rarity_row(lvl).id}", [(f, 1) for f in ids]).form_id
                  for lvl, ids in sorted(by_rarity.items())}
    any_entries = [(tier_lists[lvl], 1) for lvl in tier_lists for _ in range(rarity_row(lvl).loot_copies)]
    good_entries = [(tier_lists[lvl], 1) for lvl in tier_lists if lvl >= 3 for _ in range(rarity_row(lvl).loot_copies)]
    gun_any = leveled_list(p, "SkylandsGunsAny", any_entries)
    gun_good = leveled_list(p, "SkylandsGunsGood", good_entries or any_entries)
    # Drops are plain lists (no "use all"): one gun per roll. Ammo is its own entry in the loot lists.
    drop_any = gun_any
    drop_good = gun_good
    ammo_drop = leveled_list(p, "SkylandsAmmoDrop", [(bolts.form_id, 12)])
    for row in S.LOOT_INJECTION.values():
        target = m.find("LVLI", row.skyrim_lvli)
        if target is None:
            report.setdefault("missing", []).append(row.skyrim_lvli)
            continue
        lst = copy(target)
        add = drop_good.form_id if row.list == "good" else drop_any.form_id
        n = (lst.get("LLCT") or b"\0")[0]
        extra = [add] * row.count + [ammo_drop.form_id]
        if n + len(extra) > 255:
            continue
        for fid in extra:
            last = max(i for i, (s, _) in enumerate(lst.subs) if s in ("LLCT", "LVLO", "COED"))
            lst.subs.insert(last + 1, ("LVLO", lvlo(fid)))
        lst.set("LLCT", bytes([n + len(extra)]))
        p.override(lst)
        report["loot_lists"] += 1
    starter_gun = rnd.choice(starters) if starters else next(iter(by_rarity[min(by_rarity)]))

    # ---- vault hunters ---------------------------------------------------------------------------
    fus = next((w for w in m.by_type["WOOP"].values() if w.edid == "WordFus"), None)
    template_shout = next((s for s in m.by_type["SHOU"].values()
                           if fus and (s.first("SNAM") or b"")[:4] == esp.u32(fus.form_id)), None)
    if template_shout is None:
        raise GenerateError("Unrelenting Force (template for the action-skill shouts) not found")
    template_spell = m.by_type["SPEL"].get(struct.unpack_from("<I", template_shout.first("SNAM"), 4)[0])
    if template_spell is None:
        raise GenerateError("Unrelenting Force's first spell not found")
    spit = bytearray(template_spell.first("SPIT"))
    etyp = template_spell.first("ETYP")
    shouts, words, buttons = [], [], []
    for row in S.CLASSES.values():
        c = next((x for x in bl2["classes"] if x["id"] == row.id), None)
        if c is None:
            report.setdefault("missing_classes", []).append(row.id)
            continue
        duration = int(round(min(c["duration"] or 10, row.max_duration)))
        effects = []
        for edid, mag in parse_effects(row.effects):
            effects.append((m.need("MGEF", edid).form_id, mag, 0, duration))
        sp = bytearray(spit)
        struct.pack_into("<I", sp, 20, DELIVERY[row.delivery])
        spl = spell(p, f"SkylandsSkill_{row.id}", c["skill_name"], c["skill_desc"], bytes(sp), effects,
                    etyp=struct.unpack("<I", etyp)[0] if etyp else None)
        word = p.new("WOOP", f"SkylandsWord_{row.id}").add("FULL", esp.zstr(c["skill_name"])).add("TNAM", esp.zstr(c["character"]))
        sh = p.new("SHOU", f"SkylandsShout_{row.id}").add("FULL", esp.zstr(c["skill_name"])).add("MDOB", esp.u32(0))
        sh.add("DESC", esp.zstr(c["skill_desc"]))
        sh.add("SNAM", struct.pack("<IIf", word.form_id, spl.form_id, float(c["cooldown"] or 30.0)))
        sh.add("SNAM", struct.pack("<IIf", 0, 0, 0.0)).add("SNAM", struct.pack("<IIf", 0, 0, 0.0))
        shouts.append(sh.form_id)
        words.append(word.form_id)
        buttons.append(f"{c['character']}: {c['skill_name']}")
        report["classes"].append({"id": row.id, "character": c["character"], "skill": c["skill_name"],
                                  "duration": duration, "cooldown": c["cooldown"]})
    if not shouts:
        raise GenerateError("no vault hunters were extracted")
    msg = p.new("MESG", "SkylandsClassChoice")
    msg.add("DESC", esp.zstr("Pandora's Vault Hunters have come to Skyrim. Who are you?"))
    msg.add("FULL", esp.zstr("Choose your Vault Hunter")).add("INAM", esp.u32(0))
    msg.add("DNAM", esp.u32(1)).add("TNAM", esp.u32(0))
    for b in buttons:
        msg.add("ITXT", esp.zstr(b))
    quest = p.new("QUST", "SkylandsClassQuest")
    quest.add("VMAD", esp.vmad([("SkylandsClassQuest", [
        ("ClassChoice", esp.P_OBJECT, msg.form_id), ("Shouts", esp.P_OBJECT_ARRAY, shouts),
        ("Words", esp.P_OBJECT_ARRAY, words), ("StarterGun", esp.P_OBJECT, starter_gun), ("StarterAmmo", esp.P_OBJECT, bolts.form_id),
        ("GunKeyword", esp.P_OBJECT, gun_keyword),
        ("RarityKeywords", esp.P_OBJECT_ARRAY, [rarity_keywords[k] for k in sorted(rarity_keywords)]),
        ("Beams", esp.P_OBJECT_ARRAY, [beams[k] for k in sorted(beams)])])], quest=True))
    quest.add("FULL", esp.zstr("Skylands")).add("DNAM", struct.pack("<HBBII", QUEST_START_GAME_ENABLED, 50, 0, 0, 0))
    quest.add("ANAM", esp.u32(0))

    # ---- Pandora's bandits ------------------------------------------------------------------------
    abilities: dict[str, int] = {}
    for row in S.ENEMIES.values():
        name = bl2["enemies"].get(row.bl2_read)
        if not name:
            report.setdefault("missing_enemies", []).append(row.id)
            continue
        if row.abilities != "-" and row.abilities not in abilities:
            effects = [(m.need("MGEF", e).form_id, mag, 0, 0) for e, mag in parse_effects(row.abilities)]
            abilities[row.abilities] = spell(p, f"SkylandsAb_{row.id}", "", "",
                                             struct.pack("<IIIfIIffI", 0, 0, SPELL_ABILITY, 0, CAST_CONSTANT, DELIVERY_SELF, 0, 0, 0),
                                             effects).form_id
        rx = re.compile(row.skyrim_edid_pattern)
        for npc in m.by_type["NPC_"].values():
            if not rx.search(npc.edid) or npc.first("FULL") is None:
                continue
            o = copy(npc)
            o.set("FULL", esp.zstr(name)).drop("SHRT")
            if row.abilities != "-":
                spells = [d for s, d in o.subs if s == "SPLO"] + [esp.u32(abilities[row.abilities])]
                anchor = next((i for i, (s, _) in enumerate(o.subs) if s in ("SPCT", "SPLO")), None)
                o.drop("SPCT", "SPLO")
                if anchor is None:
                    anchor = max((i + 1 for i, (s, _) in enumerate(o.subs) if s in ("ACBS", "SNAM", "INAM", "VTCK", "TPLT", "RNAM", "WNAM", "ANAM", "ATKR")), default=len(o.subs))
                o.subs[anchor:anchor] = [("SPCT", esp.u32(len(spells)))] + [("SPLO", d) for d in spells]
            p.override(o)
            report["renamed_enemies"] += 1

    # ---- files ------------------------------------------------------------------------------------
    (out_data / PLUGIN).write_bytes(p.encode())
    (out_data / "Scripts" / "SkylandsClassQuest.pex").write_bytes(pex.write(scripts.class_choice_quest()))
    (out_data / "Scripts" / "SkylandsLootBeam.pex").write_bytes(pex.write(scripts.loot_beam()))
    report["records"] = len(p.records)
    return report
