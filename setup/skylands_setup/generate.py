"""Build Skylands' Skyrim files from the player's two games.

Inputs: the extracted Borderlands 2 data (bl2.extract) and the player's Skyrim install.
Outputs (under out/Data): Skylands.esp, Scripts/*.pex, Meshes/Skylands/*.nif, Textures/Skylands/*.dds.

Records Skylands changes are copied from the player's own Skyrim masters (latest version among
Skyrim.esm, Update.esm, Dawnguard.esm, which is also this plugin's master order, so form ids need
no remapping) and edited: nothing of Skyrim is shipped.
"""

from __future__ import annotations

import math
import random
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from . import sheet_data as S
from . import assemble, stats
from . import models as models_mod
from .skyrim import esp, nif, pex, scripts
from .skyrim.bsa import BSA
from .skyrim.esm import Record, is_localized, read_plugin
from .skyrim.strings import parse_table

MASTERS = ["Skyrim.esm", "Update.esm", "Dawnguard.esm"]
PLUGIN = "Skylands.esp"
MODELS_PLUGIN = "SkylandsGunModels.esp"
BEAM_TEXTURE = "textures\\skylands\\beam.dds"
XMARKER = 0x0000003B  # Skyrim.esm: the invisible marker object
ACTOR_TYPE_NPC = 0x00013794  # Skyrim.esm keyword: humanoids
SPEED_BUCKETS, SPEED_BASE, SPEED_STEP = 48, 0.5, 0.05  # SkylandsSpeed_n keywords: speed = base + step * n
RACES = r"^(Nord|Breton|Imperial|Redguard|Orc|DarkElf|HighElf|WoodElf|Khajiit|Argonian)Race(Vampire)?$"
LIGHT_RADIUS = 600  # game units
LIST_LIMIT = 200  # entries per leveled list (Skyrim allows 255)

# SPIT spell types / cast types / delivery (Skyrim SE)
SPELL_ABILITY, CAST_CONSTANT, DELIVERY_SELF = 4, 0, 0
SPELL_LESSER_POWER, CAST_FIRE_FORGET = 3, 1
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
MGEF_ARCHETYPE_SCRIPT = 1
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
    r = esp.Rec("MGEF", p.new_id(f"MGEF:Skylands_Stats_{edid}"), [])
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


def gun_enchant(p: esp.Plugin, edid: str, av_speed: float, text: str, element_mult: float, donor: Record,
                with_element: bool, template: Record) -> int:
    """One enchantment per gun: the vanilla element effect scaled by the gun's roll, plus its stats line.
    The stats effect's magnitude carries the player weapon speed to apply while the gun is equipped."""
    head, effects = [], []
    for sig, d in donor.subrecords:
        if sig == "EFID":
            effects.append([(sig, d)])
        elif effects:
            effects[-1].append((sig, d))
        else:
            head.append((sig, d))
    e = esp.Rec("ENCH", p.new_id(f"ENCH:Skylands_Ench_{edid}"), [(sig, d) for sig, d in head if sig not in ("EDID", "FULL")])
    e.subs.insert(0, ("EDID", esp.zstr(f"Skylands_Ench_{edid}")))
    insert_ordered(e, "FULL", esp.zstr("Gun stats"), ["EDID", "VMAD", "OBND", "FULL", "ENIT"])
    if with_element:
        for group in effects:
            e.subs.extend((sig, scale_efit(d, element_mult) if sig == "EFIT" else d) for sig, d in group)
    mg = stats_effect(p, edid, text, template)
    e.add("EFID", esp.u32(mg)).add("EFIT", struct.pack("<fII", av_speed, 0, 0))
    p.override(e)
    return e.form_id


LIGHT_BAD_FLAGS = 0x8 | 0x20 | 0x40 | 0x80 | 0x200 | 0x400 | 0x800 | 0x1000 | 0x2000 | 0x4000  # flicker, off, pulse, spot, shadows
LIGHT_KEEP = ("EDID", "OBND", "DATA", "FNAM")


def make_lights(p: esp.Plugin, m: Masters, colors: dict[int, tuple[int, int, int]], report: dict) -> dict[int, int]:
    """One coloured point light per rarity. Copied from a plain vanilla light when there is one (radius, colour and
    flags changed, so nothing flickers, pulses or casts shadows), else written from scratch."""
    best = None
    for r in sorted(m.by_type["LIGH"].values(), key=lambda r: r.edid):
        d = r.first("DATA")
        if not d or len(d) < 48 or r.first("MODL"):
            continue
        _, radius, _color, flags = struct.unpack_from("<iI4sI", d)
        score = (0 if flags & 1 else 1, 0 if not flags & LIGHT_BAD_FLAGS else 1, abs(radius - LIGHT_RADIUS))
        if best is None or score < best[0]:
            best = (score, r)
    template = best[1] if best else None
    out = {}
    for level, (red, green, blue) in colors.items():
        row = rarity_row(level)
        if template is not None:
            lt = esp.Rec("LIGH", p.new_id(f"LIGH:SkylandsLight_{row.id}"), [(sig, d) for sig, d in template.subrecords if sig in LIGHT_KEEP])
            data = bytearray(lt.get("DATA"))
        else:
            lt = esp.Rec("LIGH", p.new_id(f"LIGH:SkylandsLight_{row.id}"), [("OBND", obnd()), ("FNAM", struct.pack("<f", 1.0))])
            data = bytearray(struct.pack("<iI4sIffffffIf", -1, LIGHT_RADIUS, bytes(4), 1, 1.0, 90.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0))
            lt.subs.insert(0, ("EDID", b""))
        lt.set("EDID", esp.zstr(f"SkylandsLight_{row.id}"))
        struct.pack_into("<I", data, 4, LIGHT_RADIUS)
        data[8:12] = bytes([red, green, blue, 0])
        struct.pack_into("<I", data, 12, 0x1)  # dynamic only: no flicker, pulse, spot or shadows
        lt.set("DATA", bytes(data))
        order = ["EDID", "OBND", "DATA", "FNAM"]
        lt.subs.sort(key=lambda sd: order.index(sd[0]) if sd[0] in order else 99)
        p.override(lt)
        out[level] = lt.form_id
    report["lights"] = "from a vanilla light" if template is not None else "written from scratch"
    return out


class Texts:
    """Skyrim's own text for string ids (the masters are localized; this plugin is not, so copied names are written out)."""

    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir)
        self.tables: dict[str, dict[int, str]] = {}

    def text(self, kind: str, string_id: int) -> str | None:
        if kind not in self.tables:
            try:
                data = BSA(self.dir / "Skyrim - Interface.bsa").read(f"strings/skyrim_english.{kind}")
                self.tables[kind] = parse_table(data, kind != "strings")
            except Exception:  # noqa: BLE001 - reported by the caller as "not localised"
                self.tables[kind] = {}
        return self.tables[kind].get(string_id)


def script_effect(p: esp.Plugin, template: Record, edid: str, name: str, script: str, props: list, fire_and_forget: bool = False) -> int:
    """A magic effect (copied from a plain vanilla one) whose only job is to run a script."""
    mg = esp.Rec("MGEF", p.new_id(f"MGEF:{edid}"), [])
    mg.add("EDID", esp.zstr(edid)).add("VMAD", esp.vmad([(script, props)])).add("FULL", esp.zstr(name))
    data = bytearray(template.first("DATA") or b"\0" * 152)
    if len(data) >= 92:
        flags = struct.unpack_from("<I", data)[0] & ~0x5  # not hostile, not detrimental
        struct.pack_into("<I", data, 0, flags)
        struct.pack_into("<I", data, 64, MGEF_ARCHETYPE_SCRIPT)
        struct.pack_into("<i", data, MGEF_AV_AT, -1)
        struct.pack_into("<i", data, 88, -1)
        for at in MGEF_ART_AT:
            if len(data) >= at + 4:
                struct.pack_into("<I", data, at, 0)
        if fire_and_forget:
            struct.pack_into("<II", data, 80, 1, 0)  # casting type: fire and forget, delivery: self
    mg.add("DATA", bytes(data))
    p.override(mg)
    return mg.form_id


def make_message(p: esp.Plugin, edid: str, title: str, body: str, buttons: list[str]) -> esp.Rec:
    msg = p.new("MESG", edid)
    msg.add("DESC", esp.zstr(body)).add("FULL", esp.zstr(title)).add("INAM", esp.u32(0))
    msg.add("DNAM", esp.u32(1)).add("TNAM", esp.u32(0))
    for b in buttons:
        msg.add("ITXT", esp.zstr(b))
    return msg


def make_powers(p: esp.Plugin, m: "Masters", quest_id: int) -> tuple[int, int]:
    """The lesser powers "Pandora Respawn" (respawn now / settings) and "Pandora Log Enemies" (note the hostile people
    around you for respawning, for testing). Returns their form ids."""
    template = m.need("MGEF", "AbWeaknessFireConstant")
    spit = struct.pack("<IIIfIIffI", 0, 0, SPELL_LESSER_POWER, 0, CAST_FIRE_FORGET, DELIVERY_SELF, 0, 0, 0)
    out = []
    for edid, name, text, action in (
            ("SkylandsPandoraRespawn", "Pandora Respawn", "Respawn the enemies around you, or choose when enemies respawn.", 0),
            ("SkylandsPandoraLog", "Pandora Log Enemies", "Note the hostile people around you, so they can respawn.", 1)):
        fx = script_effect(p, template, f"{edid}Effect", name, "SkylandsHunterPower",
                           [("Owner", esp.P_OBJECT, quest_id), ("Action", esp.P_INT, action)], fire_and_forget=True)
        out.append(spell(p, f"{edid}Power", name, text, spit, [(fx, 0.0, 0, 0)]).form_id)
    return out[0], out[1]


def make_watcher(p: esp.Plugin, m: Masters, texts: Texts, props: list, report: dict, powers: tuple = ()) -> int:
    """The ability that runs the SkylandsHunter script, given to every humanoid race (so to everybody).
    Returns the ability's form id."""
    template = m.need("MGEF", "AbWeaknessFireConstant")
    effect = script_effect(p, template, "SkylandsWatcherFx", "Skylands", "SkylandsHunter", props)
    ability = spell(p, "SkylandsPandoraAbility", "", "",
                    struct.pack("<IIIfIIffI", 0, 0, SPELL_ABILITY, 0, CAST_CONSTANT, DELIVERY_SELF, 0, 0, 0),
                    [(effect, 0.0, 0, 0)])
    races = 0
    for race in sorted(m.by_type["RACE"].values(), key=lambda r: r.edid):
        if not re.match(RACES, race.edid):
            continue
        rec = copy(race)
        ok = True
        for sig, kind in (("FULL", "strings"), ("DESC", "dlstrings")):
            d = rec.get(sig)
            if d is not None and len(d) == 4:
                text = texts.text(kind, struct.unpack("<I", d)[0])
                if text is None:
                    ok = False
                    break
                rec.set(sig, esp.zstr(text))
        if not ok:
            report.setdefault("race_skipped", []).append(race.edid)
            continue
        spells = [d for sg, d in rec.subs if sg == "SPLO"] + [esp.u32(f) for f in (ability.form_id, *powers)]
        anchor = next((i for i, (sg, _) in enumerate(rec.subs) if sg in ("SPCT", "SPLO")), None)
        if anchor is None:
            anchor = next((i + 1 for i, (sg, _) in reversed(list(enumerate(rec.subs))) if sg in ("DESC", "FULL")), len(rec.subs))
        rec.drop("SPCT", "SPLO")
        rec.subs[anchor:anchor] = [("SPCT", esp.u32(len(spells)))] + [("SPLO", d) for d in spells]
        p.override(rec)
        races += 1
    report["watched_races"] = races
    return ability.form_id


def generate(bl2: dict, skyrim_dir: Path, out_dir: Path, seed: int = 4, formids: dict[str, int] | None = None,
             gun_models: str = "off", model_sources: dict | None = None, model_spin: float = 0.0,
             model_scale: float = 1.0) -> dict:
    """formids: the form ids of earlier builds (updated in place with any new ones); see esp.Plugin.
    gun_models: how the guns get their own meshes (models.METHODS); model_sources: readers of Borderlands 2 meshes by method."""
    data_dir = Path(skyrim_dir) / "Data"
    m = Masters.load(data_dir, {"WEAP", "AMMO", "NPC_", "LVLI", "MGEF", "ENCH", "EQUP", "SHOU", "WOOP", "SPEL", "LIGH", "RACE"})
    for key in [k for k in (formids or {}) if k.startswith("STAT:SkylandsGunView_")]:
        del formids[key]  # left by builds that kept these in Skylands.esp, which made it too big to stay light
    p = esp.Plugin(PLUGIN, MASTERS, ids=formids)
    view = esp.Plugin(MODELS_PLUGIN, MASTERS + [PLUGIN])
    report: dict = {"guns": 0, "renamed_enemies": 0, "loot_lists": 0, "classes": []}
    rnd = random.Random(seed)
    G = S.GENERATION["main"]

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
        beam = p.new("STAT", f"SkylandsBeam_{row.id}")
        beam.add("OBND", struct.pack("<6h", -10, -10, 0, 10, 10, 150)).add("MODL", esp.zstr(mesh)).add("DNAM", struct.pack("<fI", 30.0, 0))
        beams[row.level] = beam.form_id
    # Keywords the scripts look for: one on every Skylands gun, and one per rarity (picks the beam).
    gun_keyword = p.new("KYWD", "SkylandsGun").form_id
    rarity_keywords = {row.level: p.new("KYWD", f"SkylandsRarity_{row.id}").form_id for row in S.RARITIES.values()}
    quest = p.new("QUST", "SkylandsPandoraQuest")
    speed_keywords = [p.new("KYWD", f"SkylandsSpeed_{i}").form_id for i in range(SPEED_BUCKETS)]
    lights = make_lights(p, m, {row.level: rarity_color(bl2["rarities"], row.level) for row in S.RARITIES.values()}, report)

    # ---- guns ---------------------------------------------------------------------------------
    crossbow = m.need("WEAP", S.SKYRIM_BASE["crossbow"].edid)
    first_person: dict[str, int] = {}
    model_log = report.setdefault("model_log", [])
    models = models_mod.GunModels(gun_models, out_data, models_mod.find_vanilla_mesh(data_dir, crossbow.first("MODL"), model_log.append),
                                  model_log.append, model_sources, model_spin, model_scale) if gun_models != "off" else None
    bolts = m.need("AMMO", S.SKYRIM_BASE["bolts"].edid)
    base_enchant = {e.bl2_part: m.need("ENCH", e.skyrim_enchantment) for e in S.ELEMENTS.values()}
    any_enchant = next(iter(base_enchant.values()))
    stats_mgef = stats_template(m, any_enchant)

    gun_types = {g.id: g for g in S.GUN_TYPES.values()}
    by_rarity: dict[int, list[int]] = {}
    starters: list[int] = []
    parts = bl2["weapons"].get("parts", {})
    manufacturers = bl2["weapons"]["manufacturers"]
    for g in bl2["weapons"]["guns"]:
        gt = gun_types[g["type"]]
        rr = rarity_row(g["rarity"])
        value = round(gt.base_value * rr.value_mult)
        taken: set = set()
        for k in range(max(1, int(rr.variants))):
            built = assemble.pick(g, {**parts}, k, taken)
            element = built["element"]
            if element is None and not g.get("slots", {}).get("Elemental") and g["elements"]:
                element = [None, *g["elements"]][k % (len(g["elements"]) + 1)]  # no readable element parts: one variant per element
            edid = f"Skylands_{g['balance'].rsplit('.', 1)[1]}_{k + 1}"
            st = stats.roll(edid, gt, rr, element is not None, built["mods"])
            damage = max(1, round(gt.base_damage * rr.damage_mult * st["damage_mult"]))
            half = round(math.sqrt(st["speed"]), 3)  # half the speed goes into the weapon, half into the player's weapon speed
            name = assemble.name_of(g, built["parts"], parts, element, manufacturers, rr.word)
            w = copy(crossbow)
            w.form_id = p.new_id(f"WEAP:{edid}")
            w.drop("DESC", "EITM", "EAMT", "VMAD")
            w.set("EDID", esp.zstr(edid))
            insert_ordered(w, "FULL", esp.zstr(name), WEAP_ORDER)
            kwda = w.get("KWDA") or b""
            bucket = min(SPEED_BUCKETS - 1, max(0, round((half - SPEED_BASE) / SPEED_STEP)))
            keywords = [*struct.unpack(f"<{len(kwda) // 4}I", kwda), gun_keyword, rarity_keywords[rr.level], speed_keywords[bucket]]
            insert_ordered(w, "KSIZ", struct.pack("<I", len(keywords)), WEAP_ORDER)
            insert_ordered(w, "KWDA", struct.pack(f"<{len(keywords)}I", *keywords), WEAP_ORDER)
            text = stats.describe(st, element, manufacturers.get(g["manufacturer"], g["manufacturer"]),
                                  g.get("clip", 0), assemble.parts_line(built["parts"]))
            ench = gun_enchant(p, edid, 0.0, text, st["element_mult"], base_enchant.get(element) or any_enchant,
                               element is not None, stats_mgef)
            insert_ordered(w, "EITM", esp.u32(ench), WEAP_ORDER)
            insert_ordered(w, "EAMT", u16(65535), WEAP_ORDER)
            d = w.get("DATA") or b"\0" * 10
            insert_ordered(w, "DATA", struct.pack("<IfH", value, float(gt.weight), damage) + d[10:], WEAP_ORDER)
            dn = w.get("DNAM")
            if dn and len(dn) >= 8:
                w.set("DNAM", dn[:4] + struct.pack("<f", half) + dn[8:])
            crit = w.get("CRDT")
            if crit and len(crit) >= 2:
                w.set("CRDT", u16(st["crit_damage"]) + crit[2:])
            if models is not None:
                mesh = models.model_for(g, built, rr.id, rarity_color(bl2["rarities"], rr.level), edid)
                if mesh:
                    # The real model goes in a second plugin so Skylands.esp never changes (it must stay light
                    # or every save made with it loses its powers and guns).
                    w2 = esp.Rec(w.type, w.form_id, list(w.subs), flags=w.flags)
                    w2.set("MODL", esp.zstr(mesh))
                    w2.drop("MODT", "MODS", "MO2T", "MO2S")
                    if mesh not in first_person:  # the model Skyrim shows in first person (and, it seems, in the inventory)
                        fp = view.new("STAT", "SkylandsGunView_" + mesh.rsplit("\\", 1)[-1].removesuffix(".nif"))
                        fp.add("OBND", struct.pack("<6h", -40, -40, -40, 40, 40, 40)).add("MODL", esp.zstr(mesh))
                        fp.add("DNAM", struct.pack("<fI", 30.0, 0))
                        first_person[mesh] = fp.form_id
                    insert_ordered(w2, "WNAM", esp.u32(first_person[mesh]), WEAP_ORDER)
                    view.override(w2)
            p.override(w)
            by_rarity.setdefault(rr.level, []).append(w.form_id)
            if g["type"] == "pistol" and rr.level == 1 and element is None:
                starters.append(w.form_id)
            report["guns"] += 1
            report.setdefault("stats", {})[edid] = {"name": name, "parts": built["parts"], "element": element,
                                                   **{k2: v for k2, v in st.items() if v is not None}}
    if not by_rarity:
        raise GenerateError("no Borderlands guns were extracted")
    if models is not None:
        models.flush_textures()
        report["gun_models"] = {"method": gun_models, **models.stats, "by_method": models.by_method, "textures": len(models.textures)}
        report["model_log"].append(models.summary())

    tier_lists = {lvl: leveled_list(p, f"SkylandsGuns_{rarity_row(lvl).id}", [(f, 1) for f in ids]).form_id
                  for lvl, ids in sorted(by_rarity.items())}
    any_entries = [(tier_lists[lvl], 1) for lvl in tier_lists for _ in range(rarity_row(lvl).loot_copies)]
    good_entries = [(tier_lists[lvl], 1) for lvl in tier_lists if lvl >= 2 for _ in range(rarity_row(lvl).loot_copies)]
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
    gun_list = p.new("FLST", "SkylandsGunList")  # every gun: the player's script finds ones lying nearby with it
    for ids in by_rarity.values():
        for fid in ids:
            gun_list.add("LNAM", esp.u32(fid))
    watcher_props = [
        ("Owner", esp.P_OBJECT, quest.form_id), ("GunKeyword", esp.P_OBJECT, gun_keyword),
        ("SpeedKeywords", esp.P_OBJECT_ARRAY, speed_keywords), ("GunList", esp.P_OBJECT, gun_list.form_id),
        ("GunDrop", esp.P_OBJECT, drop_any.form_id), ("GunDropGood", esp.P_OBJECT, drop_good.form_id),
        ("NpcKeyword", esp.P_OBJECT, ACTOR_TYPE_NPC), ("Bolts", esp.P_OBJECT, bolts.form_id),
        ("ArmChance", esp.P_INT, int(G.arm_chance)), ("DropChance", esp.P_INT, int(G.drop_chance)),
        ("GoodLevel", esp.P_INT, int(G.good_level)), ("ScanRadius", esp.P_FLOAT, float(G.scan_radius)),
        ("Verbose", esp.P_BOOL, bool(G.verbose)),
        # what the quest needs, handed over by the player's copy of this script (a saved game would keep stale values)
        ("RarityKeywords", esp.P_OBJECT_ARRAY, [rarity_keywords[k] for k in sorted(rarity_keywords)]),
        ("Beams", esp.P_OBJECT_ARRAY, [beams[k] for k in sorted(beams)]),
        ("Lights", esp.P_OBJECT_ARRAY, [lights[k] for k in sorted(lights)] if len(lights) == len(beams) else []),
        ("PromptMsg", esp.P_OBJECT, p.new_id("MESG:SkylandsRespawnPrompt")),
        ("SettingsMsg", esp.P_OBJECT, p.new_id("MESG:SkylandsRespawnSettings")), ("MarkerForm", esp.P_OBJECT, XMARKER),
        ("RespawnPower", esp.P_OBJECT, p.new_id("SPEL:SkylandsPandoraRespawnPower")),
        ("LogPower", esp.P_OBJECT, p.new_id("SPEL:SkylandsPandoraLogPower")),
        ("Ability", esp.P_OBJECT, p.new_id("SPEL:SkylandsPandoraAbility"))]
    respawn_power, log_power = make_powers(p, m, quest.form_id)
    watcher_ability = make_watcher(p, m, Texts(data_dir), watcher_props, report)

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
    prompt_msg = make_message(p, "SkylandsRespawnPrompt", "Respawn enemies?",
                              "Pandora's enemies can come back every time you load a save, so you can farm them and the bosses "
                              "for loot. In a dungeon you are taken back to where you came in.",
                              ["Respawn enemies here", "Not this time", "Always respawn when I load", "Never ask again"])
    settings_msg = make_message(p, "SkylandsRespawnSettings", "Pandora Respawn",
                                "Respawn the enemies around you now, or choose what happens when you load a save.",
                                ["Respawn enemies now", "Ask me every time I load", "Always respawn when I load",
                                 "Never respawn when I load", "Cancel"])
    quest.add("VMAD", esp.vmad([("SkylandsHunterQuest", [
        ("ClassChoice", esp.P_OBJECT, msg.form_id), ("Shouts", esp.P_OBJECT_ARRAY, shouts),
        ("Words", esp.P_OBJECT_ARRAY, words), ("StarterGun", esp.P_OBJECT, starter_gun),
        ("StarterAmmo", esp.P_OBJECT, bolts.form_id),
        ("AbilityInit", esp.P_OBJECT, p.new_id("SPEL:SkylandsPandoraAbility"))])], quest=True))
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
    if view.records:
        (out_data / MODELS_PLUGIN).write_bytes(view.encode())
    (out_data / "Scripts" / "SkylandsHunterQuest.pex").write_bytes(pex.write(scripts.class_choice_quest()))
    (out_data / "Scripts" / "SkylandsHunterPower.pex").write_bytes(pex.write(scripts.respawn_power()))
    (out_data / "Scripts" / "SkylandsHunter.pex").write_bytes(pex.write(scripts.watcher()))
    report["records"] = len(p.records)
    return report
