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


# ---- shooting: splash and element effects, retuned bolts (all in the optional second plugin) ----------------------------
# (radius in Skyrim units, fraction of the gun's damage the blast does). Launchers explode big; elemental guns splash a little.
SPLASH = {"pistol": (90.0, 0.35), "smg": (80.0, 0.30), "assault_rifle": (80.0, 0.30), "shotgun": (70.0, 0.30), "sniper": (60.0, 0.25),
          "launcher": (420.0, 1.0)}
EXPL_DONOR = {"fire": r"fire", "shock": r"shock|lightning", "corrosive": r"poison|acid", "slag": r"frost|ice", None: r"explosion|bomb|grenade"}
EXPL_ORDER = ["EDID", "OBND", "FULL", "MODL", "MODT", "MODS", "EITM", "MNAM", "DATA"]
EXPL_FORCE_AT, EXPL_DAMAGE_AT, EXPL_RADIUS_AT = 24, 28, 32  # in EXPL DATA (52 bytes)
MGEF_EXPLOSION_AT = 76
BOLT_SPEED, BOLT_GRAVITY = 9000.0, 0.02  # PROJ DATA offsets 8 (speed) and 4 (gravity): a fast, nearly flat shot


KINDS = ["pistol", "smg", "assault_rifle", "shotgun", "sniper", "launcher"]  # index = kind keyword number
ELEMENT_NAMES = ["Fire", "Shock", "Corrosive", "Slag"]  # element keyword number = index + 1 (0 = none)
KIND_AT, ELEM_AT = 0x81E - 0x800, 0x824 - 0x800  # the script finds the kind/element keywords at these local ids (SkylandsGunModels.esp)
ROUND_NAMES = {"pistol": "Pistol Rounds", "smg": "SMG Rounds", "assault_rifle": "Rifle Rounds", "shotgun": "Shells",
               "sniper": "Sniper Rounds", "launcher": "Rockets"}
PROJ_FLAGS_AT, PROJ_GRAVITY_AT, PROJ_SPEED_AT, PROJ_RANGE_AT, PROJ_EXPLOSION_AT = 0, 4, 8, 12, 36
BL2_TO_SKYRIM_SPEED = 1 / 3.0  # Borderlands units per second to Skyrim's: a bullet at 21500 becomes ~7000, an arrow flies at ~4000


class Rounds:
    """Borderlands-style rounds: one AMMO (with its own projectile and, for launchers and elemental guns, its own explosion)
    for every gun type x element. The numbers (projectile speed, splash) come from sheets/shooting.json, read from Borderlands 2.
    Everything is in the optional second plugin. Ids are reserved first, in a fixed order, so the watcher script can find them
    by number with Game.GetFormFromFile: ammo 0x800+kind*5+element, kind keywords 0x81E+kind, element keywords 0x824+element."""

    def __init__(self, view: esp.Plugin, m: Masters, bolts: Record, base_enchant: dict, log: list[str]) -> None:
        self.view, self.m, self.bolts, self.enchants, self.log = view, m, bolts, base_enchant, log
        self.ammo_ids = [[view.new_id(f"AMMO:SkylandsRound_{t}_{e}") for e in range(5)] for t in KINDS]
        self.kind_kw = [view.new_id(f"KYWD:SkylandsKind_{t}") for t in KINDS]
        self.elem_kw = [view.new_id(f"KYWD:SkylandsElement_{e}") for e in ELEMENT_NAMES]
        assert self.ammo_ids[0][0] & 0xFFFFFF == 0x800 and self.kind_kw[0] & 0xFFFFFF == 0x800 + KIND_AT
        for kid, name in [*zip(self.kind_kw, KINDS), *zip(self.elem_kw, ELEMENT_NAMES)]:
            view.override(esp.Rec("KYWD", kid, [("EDID", esp.zstr(f"SkylandsShot_{name}"))]))
        data = bolts.first("DATA")
        self.bolt_proj = self.m.by_type.get("PROJ", {}).get(struct.unpack_from("<I", data)[0]) if data and len(data) >= 4 else None
        if self.bolt_proj is None or len(self.bolt_proj.first("DATA") or b"") < 40:
            log.append("Shooting: the steel bolt's projectile was not found; Borderlands rounds need it")
            self.bolt_proj = None
        self.donors: dict[object, Record | None] = {}
        self.blasts: dict[tuple, int] = {}
        self.made = 0

    def donor(self, element: str | None) -> Record | None:
        if element not in self.donors:
            rx = re.compile(EXPL_DONOR.get(element.lower() if element else None, EXPL_DONOR[None]), re.I)
            found = [r for r in sorted(self.m.by_type.get("EXPL", {}).values(), key=lambda r: r.edid)
                     if rx.search(r.edid) and len(r.first("DATA") or b"") >= 52]
            found.sort(key=lambda r: (0 if r.first("MODL") else 1, 0 if "bolt" in r.edid.lower() else 1))
            self.donors[element] = found[0] if found else None
            self.log.append(f"Shooting: explosion art for {element or 'plain'}: " + (found[0].edid if found else "no vanilla explosion found (no art)"))
        return self.donors[element]

    def expl(self, kind: str, element: str | None, base_damage: float, radius: float | None = None) -> int:
        if (kind, element) in self.blasts:  # one blast per gun type and element, whoever asks (the crossbow rounds, the staff guns)
            return self.blasts[(kind, element)]
        default_radius, frac = SPLASH.get(kind, (80.0, 0.3))
        radius = float(radius or default_radius)
        dmg = max(5, round(base_damage * frac / 5) * 5)
        edid = f"SkylandsBlast_{kind}_{element or 'plain'}"
        donor = self.donor(element)
        r = esp.Rec("EXPL", self.view.new_id(f"EXPL:{edid}"), [])
        if donor is not None:
            r.subs = [(sig, d) for sig, d in donor.subrecords if sig not in ("EDID", "EITM")]
            r.subs.insert(0, ("EDID", esp.zstr(edid)))
            data = bytearray(donor.first("DATA"))
        else:
            r.add("EDID", esp.zstr(edid)).add("OBND", struct.pack("<6h", 0, 0, 0, 0, 0, 0))
            data = bytearray(52)
            struct.pack_into("<I", data, 48, 1)
        struct.pack_into("<fff", data, EXPL_FORCE_AT, 120.0 if kind == "launcher" else 30.0, float(dmg), radius)
        r.set("DATA", bytes(data))
        if element is not None and self.enchants.get(element) is not None:
            insert_ordered(r, "EITM", esp.u32(self.enchants[element].form_id), EXPL_ORDER)
        self.view.override(r)
        self.blasts[(kind, element)] = r.form_id
        return r.form_id

    def build(self, kind: str, element: str | None, base_damage: float, shot) -> None:
        """The projectile and ammo for one gun type x element (ids were reserved in __init__)."""
        t, e = KINDS.index(kind), 0 if element not in ELEMENT_NAMES else ELEMENT_NAMES.index(element) + 1
        explode = element is not None or kind == "launcher"
        edid = f"SkylandsRound_{kind}_{element or 'plain'}"
        proj_id = self.view.new_id(f"PROJ:{edid}")
        if self.bolt_proj is not None:
            pr = esp.Rec("PROJ", proj_id, [(sig, d) for sig, d in self.bolt_proj.subrecords])
            pr.set("EDID", esp.zstr(edid))
            pd = bytearray(self.bolt_proj.first("DATA"))
            speed = float(shot.speed_bl2 if shot else 20000) * BL2_TO_SKYRIM_SPEED
            struct.pack_into("<ff", pd, PROJ_GRAVITY_AT, 0.0 if kind != "launcher" else 0.02, speed)
            struct.pack_into("<f", pd, PROJ_RANGE_AT, 30000.0)
            if explode:
                flags = struct.unpack_from("<H", pd, PROJ_FLAGS_AT)[0] | 0x2
                struct.pack_into("<H", pd, PROJ_FLAGS_AT, flags)
                struct.pack_into("<I", pd, PROJ_EXPLOSION_AT, self.expl(kind, element, base_damage, shot.explosion_radius if shot else None))
            pr.set("DATA", bytes(pd))
            self.view.override(pr)
        data = self.bolts.first("DATA")
        # built from scratch (a copy of the vanilla record, with its other subrecords, was never accepted into the player's pack)
        keep = ("OBND", "MODL", "YNAM", "ZNAM")
        am = esp.Rec("AMMO", self.ammo_ids[t][e], [("EDID", esp.zstr(edid))] + [(s, d) for s, d in self.bolts.subrecords if s in keep])
        am.add("FULL", esp.zstr(ROUND_NAMES[kind] + (f" ({element})" if element else "")))
        am.subs.sort(key=lambda sd: ["EDID", "OBND", "FULL", "MODL", "YNAM", "ZNAM"].index(sd[0]))
        if data and len(data) >= 16 and self.bolt_proj is not None:
            am.add("DATA", struct.pack("<I", proj_id) + data[4:16])
        else:
            am.add("DATA", struct.pack("<IIfI", 0, 0, 8.0, 1))
        self.view.override(am)
        self.made += 1

    def lab_items(self) -> list[int]:
        """Items for the in-game "item test" (what the game will hold): an old-style copy of the vanilla bolt, and a plain
        miscellaneous item. Returned with the first round and the vanilla bolt by make_gunner."""
        out = []
        clone = esp.Rec("AMMO", self.view.new_id("AMMO:SkylandsLabClone"), [(s, d) for s, d in self.bolts.subrecords])
        clone.set("EDID", esp.zstr("SkylandsLabClone")).set("FULL", esp.zstr("Lab bolt"))
        clone.drop("DESC", "ONAM")
        self.view.override(clone)
        out.append(clone.form_id)
        misc = esp.Rec("MISC", self.view.new_id("MISC:SkylandsLabMisc"), [("EDID", esp.zstr("SkylandsLabMisc")),
                       ("OBND", struct.pack("<6h", 0, 0, 0, 0, 0, 0)), ("FULL", esp.zstr("Lab item")), ("DATA", struct.pack("<If", 1, 0.0))])
        self.view.override(misc)
        out.append(misc.form_id)
        return out

    def keywords(self, kind: str, element: str | None) -> list[int]:
        return [self.kind_kw[KINDS.index(kind)], *([self.elem_kw[ELEMENT_NAMES.index(element)]] if element in ELEMENT_NAMES else [])]


class Gunner:
    """Per-gun shooting numbers for the SkylandsGunner script. A profile is one Borderlands weapon type (gun type x
    manufacturer: its own fire rate, spread, reload, pellets and burst, read from the game by extract.shooting_of); profiles
    0-5 are the gun types' defaults from sheets/shooting.json. A gun carries its profile's keyword and two keywords for its
    own magazine size (tens and units)."""

    def __init__(self, view: esp.Plugin, shots: dict, guns: list[dict]) -> None:
        self.rows: list[dict] = []
        self.keywords: list[int] = []
        self.index: dict[tuple, int] = {}
        for kind in KINDS:
            row = shots.get(kind)
            self._add(view, f"SkylandsProfile_{kind}", {
                "clip": int(row.clip) if row else 20, "reload": float(row.reload) if row else 3.0,
                "burst": int(row.burst) if row else 1, "pellets": int(row.pellets) if row else 1,
                "spread": float(row.spread_deg) if row else 2.0, "interval": float(row.fire_interval) if row else 0.2})
        for g in sorted(guns, key=lambda g: (g["type"], g.get("manufacturer", ""))):
            key = (g["type"], g.get("manufacturer", ""))
            if key in self.index or g["type"] not in KINDS:
                continue
            base = self.rows[KINDS.index(g["type"])]
            sh = g.get("shooting") or {}
            # Borderlands: a weapon type with AutomaticBurstCount = 1 is semi-automatic (one shot per pull); SMGs and assault rifles
            # without it are fully automatic (here a burst per pull, since Skyrim cannot see a held trigger); other types are semi.
            burst = 1 if "auto_burst" in sh else base["burst"]
            self.index[key] = len(self.rows)
            self._add(view, f"SkylandsProfile_{key[0]}_{key[1]}", {
                "clip": int(g.get("clip") or base["clip"]), "reload": float(sh.get("reload", base["reload"])),
                "burst": burst, "pellets": int(g.get("pellets") or base["pellets"]),
                "spread": float(sh.get("spread", base["spread"])), "interval": float(sh.get("fire_interval", base["interval"]))})
        self.tens = [self._kw(view, f"SkylandsClipTens_{i}") for i in range(10)]
        self.units = [self._kw(view, f"SkylandsClipUnits_{i}") for i in range(10)]

    @staticmethod
    def _kw(view: esp.Plugin, edid: str) -> int:
        return view.new("KYWD", edid).form_id

    def _add(self, view: esp.Plugin, edid: str, row: dict) -> None:
        self.rows.append(row)
        self.keywords.append(self._kw(view, edid))

    def for_gun(self, g: dict, clip: int | None) -> list[int]:
        out = []
        key = (g["type"], g.get("manufacturer", ""))
        if key in self.index:
            out.append(self.keywords[self.index[key]])
        if clip:
            clip = max(1, min(99, clip))
            out += [self.tens[clip // 10], self.units[clip % 10]]
        return out


AIM_POINT_MESH = "Skylands\\AimPoint.nif"


def make_gunner(view: esp.Plugin, m: Masters, rounds: "Rounds", gunner: Gunner, bolts_id: int) -> None:
    """The player's Borderlands shooting (script SkylandsGunner, see scripts.gunner): an ability with the rounds, keywords and
    the per-profile numbers as properties, and a start-game-enabled quest that gives the player that ability. All in the
    second plugin, so the forms it needs are properties (no Game.GetFormFromFile)."""
    # an invisible object with 3D, placed once in front of the player and turned for every extra round (Weapon.Fire source)
    aim = view.new("ACTI", "SkylandsAimPoint")
    aim.add("OBND", struct.pack("<6h", 0, 0, 0, 0, 0, 0)).add("MODL", esp.zstr(AIM_POINT_MESH))
    rows = gunner.rows
    props = [
        ("Rounds", esp.P_OBJECT_ARRAY, [i for per_kind in rounds.ammo_ids for i in per_kind]),
        ("KindKeywords", esp.P_OBJECT_ARRAY, rounds.kind_kw), ("ElementKeywords", esp.P_OBJECT_ARRAY, rounds.elem_kw),
        ("ProfileKeywords", esp.P_OBJECT_ARRAY, gunner.keywords),
        ("ClipTens", esp.P_OBJECT_ARRAY, gunner.tens), ("ClipUnits", esp.P_OBJECT_ARRAY, gunner.units),
        ("Clip", esp.P_INT_ARRAY, [r["clip"] for r in rows]),
        ("ReloadTime", esp.P_FLOAT_ARRAY, [r["reload"] for r in rows]),
        ("Burst", esp.P_INT_ARRAY, [r["burst"] for r in rows]),
        ("Pellets", esp.P_INT_ARRAY, [r["pellets"] for r in rows]),
        ("Spread", esp.P_FLOAT_ARRAY, [r["spread"] for r in rows]),
        ("Interval", esp.P_FLOAT_ARRAY, [r["interval"] for r in rows]),
        ("Marker", esp.P_OBJECT, aim.form_id), ("Verbose", esp.P_BOOL, True), ("Bolts", esp.P_OBJECT, bolts_id),
        ("LabItems", esp.P_OBJECT_ARRAY, [rounds.ammo_ids[0][0], *rounds.lab_items(), bolts_id]),
    ]
    template = m.need("MGEF", "AbWeaknessFireConstant")
    effect = script_effect(view, template, "SkylandsGunnerFx", "Skylands Gunner", "SkylandsGunner", props)
    ability = spell(view, "SkylandsGunnerAbility", "", "",
                    struct.pack("<IIIfIIffI", 0, 0, SPELL_ABILITY, 0, CAST_CONSTANT, DELIVERY_SELF, 0, 0, 0), [(effect, 0.0, 0, 0)])
    quest = view.new("QUST", "SkylandsGunnerQuest")
    quest.add("VMAD", esp.vmad([("SkylandsGunnerQuest", [("Ability", esp.P_OBJECT, ability.form_id)])], quest=True))
    quest.add("FULL", esp.zstr("Skylands Gunner")).add("DNAM", struct.pack("<HBBII", QUEST_START_GAME_ENABLED, 50, 0, 0, 0))
    quest.add("ANAM", esp.u32(0))


def tune_bolts(view: esp.Plugin, m: Masters, bolts: Record, log: list[str]) -> bool:
    """Make the steel bolt (what every Skylands gun fires) a fast, nearly flat shot: an override of its projectile."""
    data = bolts.first("DATA")
    proj = m.by_type.get("PROJ", {}).get(struct.unpack_from("<I", data)[0]) if data and len(data) >= 4 else None
    if proj is None or len(proj.first("DATA") or b"") < 16:
        log.append("Shooting: the steel bolt's projectile was not found; bolts left as they are")
        return False
    r = copy(proj)
    pd = bytearray(proj.first("DATA"))
    old = struct.unpack_from("<ff", pd, 4)
    struct.pack_into("<ff", pd, 4, BOLT_GRAVITY, BOLT_SPEED)
    r.set("DATA", bytes(pd))
    view.override(r)
    log.append(f"Shooting: steel bolt projectile {proj.edid}: gravity {old[0]:g} -> {BOLT_GRAVITY:g}, speed {old[1]:g} -> {BOLT_SPEED:g}")
    return True


# ---- the staff-type automatic gun prototype -------------------------------------------------------------------------------
STAFF_ANIMATION = 8  # WEAP DNAM byte 0: the animation type (8 staff, 9 crossbow)
STAFF_DONOR = {"fire": r"fire", "shock": r"lightning|spark|shock", "corrosive": r"poison|acid", "slag": r"ice|frost", None: r"ice|frost|fire"}
MGEF_PROJECTILE_AT, MGEF_COST_AT = 72, 4
ENIT_COST_AT, ENIT_FLAGS_AT = 0, 4
STAFF_REV = "0.15.0"
STAFF_SCRIPT = "SkylandsStaffGun20"  # the script class has its own name per revision: a saved game keeps old script objects of the same class running as ghosts with empty properties
STAFF_ID_SHIFT = 380  # ids skipped before the staff gun's records: the second plugin numbers its forms by position, so a saved game would otherwise match the old staff and script effect to the new records and keep their old data  # in the names of the ability, effect and quest: a saved game keeps the script values it was given, so a new revision must be new forms
STAFF_TRACER_RGB = {"fire": (255, 140, 40), "shock": (120, 190, 255), "corrosive": (120, 255, 80), "slag": (190, 90, 255), None: (255, 235, 150)}
PROJ_FLAG_MUZZLE_FLASH = 0x8
PROJ_LIGHT_AT, PROJ_SOUND_AT, PROJ_SOUND_COUNTDOWN_AT = 16, 40, 56
MGEF_HOSTILE, MGEF_DETRIMENTAL, MGEF_HIT_SHADER_AT = 0x1, 0x4, 32
MGEF_NO_HIT_EFFECT, MGEF_NO_HIT_EVENT, MGEF_IMPACT_DATA_AT, MGEF_EXPLOSION_AT = 0x08000000, 0x10, 100, 76
STAFF_CHARGE_PER_SHOT = 100.0  # enchantment charge of one round: the staff's charge gauge is the magazine (weapon charge = magazine * this)
MGEF_LIGHT_AT, MGEF_ENCHANT_SHADER_AT = 24, 36
MGEF_CASTING_ART_AT, MGEF_HIT_ART_AT, MGEF_DUAL_ART_AT, MGEF_ENCHANT_ART_AT = 92, 96, 108, 116
STAFF_OFFSET = (0.0, 0.0, 12.0)  # where the bullet starts, from the hand's magic node: right, up, forward (game units)
STAFF_SCALE, STAFF_FORWARD, STAFF_LIFT = 1.25, 0.10, 0.10  # the model in the hand: size, and how far (of its length) it is moved forward and up
ENIT_CAST_AT, ENIT_CHARGE_AT, MGEF_CASTING_AT = 8, 24, 80
STAFF_SPEED_MULT = 3.0  # the player's weapon speed while the staff gun is in the hand (a guess: it may or may not speed up a cast)


def staff_donor(m: "Masters", element: str | None, log: list[str], strict: bool = False):
    """A vanilla staff whose spell flies a projectile: (weapon, enchantment, effect record, projectile record). Only plain
    ones: a damaging value-modifier effect that is fired and forgotten at an aim, with no script anywhere in the chain (the
    quest artifacts such as the Wabbajack are scripted and are never copied). Preferred by the element's art, else any
    fire, frost or lightning staff; none found means no staff gun (and says so)."""
    rx = re.compile(STAFF_DONOR.get(element.lower() if element else None, STAFF_DONOR[None]), re.I)
    generic = re.compile(r"fire|frost|ice|lightning|spark", re.I)
    found = []
    for w in sorted(m.by_type["WEAP"].values(), key=lambda r: r.edid):
        dn, eitm = w.first("DNAM"), w.first("EITM")
        if not dn or dn[0] != STAFF_ANIMATION or not eitm or not w.first("MODL") or w.first("VMAD"):
            continue
        ench = m.by_type["ENCH"].get(struct.unpack_from("<I", eitm)[0])
        efid = ench.first("EFID") if ench else None
        mg = m.by_type["MGEF"].get(struct.unpack_from("<I", efid)[0]) if efid else None
        md = mg.first("DATA") if mg else None
        if not md or len(md) < 88 or mg.first("VMAD") or ench.first("VMAD"):
            continue
        archetype, casting, delivery = struct.unpack_from("<I", md, 64)[0], struct.unpack_from("<I", md, 80)[0], struct.unpack_from("<I", md, 84)[0]
        if archetype != 0 or casting != 1 or delivery != 2:  # value modifier, fire and forget, aimed
            continue
        pj = m.by_type["PROJ"].get(struct.unpack_from("<I", md, MGEF_PROJECTILE_AT)[0])
        if pj is None or len(pj.first("DATA") or b"") < 40 or pj.first("VMAD"):
            continue
        name = w.edid + " " + mg.edid
        rank = 0 if rx.search(name) else 1 if generic.search(name) else 9
        if rank < 9:
            found.append((rank, w.edid, w, ench, mg, pj))
    if not found:
        log.append("Staff gun: no plain vanilla staff with a projectile spell was found; the staff gun is not built")
        return None
    found.sort(key=lambda t: t[:2])
    if strict and found[0][0] != 0:  # only a staff of the element itself will do (its hit art is the element's)
        log.append(f"Staff gun: no plain vanilla {element} staff with a projectile spell was found; the {element} bullets get no hit art")
        return None
    _, _, w, ench, mg, pj = found[0]
    log.append(f"Staff gun: donor staff {w.edid} (animation type {w.first('DNAM')[0]}), enchantment {ench.edid}, effect {mg.edid}, projectile {pj.edid}"
               f" (of {len(found)} plain staffs)")
    return w, ench, mg, pj


STAFF_SOUND_WORDS = {  # per gun type: a vanilla sound that stands in for the Borderlands one until those are extracted (docs/gun-feel.md)
    "smg": (r"crossbow", r"fire|shoot|attack|release|loose"),
    "assault_rifle": (r"(?<!cross)bow", r"fire|shoot|attack|release|loose"),
}


def staff_shot_sound(m: "Masters", log: list[str], kind: str = "smg"):
    """The sound of a gun shot for a staff gun type: a vanilla firing sound from the masters (the nearest thing Skyrim has; the
    Borderlands sounds come later). (form id, editor id), or None when none is found."""
    what, fire = STAFF_SOUND_WORDS.get(kind, STAFF_SOUND_WORDS["smg"])
    rx_what, rx_fire = re.compile(what, re.I), re.compile(fire, re.I)
    pool = list(m.by_type.get("SNDR", {}).values())
    found = sorted(((0 if rx_fire.search(r.edid or "") else 1, len(r.edid or ""), r.edid, r.form_id) for r in pool
                    if rx_what.search(r.edid or "") and (kind != "assault_rifle" or "crossbow" not in (r.edid or "").lower())))
    if not found and kind != "smg":
        return staff_shot_sound(m, log, "smg")
    if not found:
        log.append(f"Staff gun: no {kind} firing sound was found in the masters; those staff guns are silent")
        return None
    log.append(f"Staff gun: {kind} shot sound {found[0][2]} (of {len(found)} candidates)")
    return found[0][3], found[0][2]


STAFF_EQUIP_SLOT = 0x00013F42  # Skyrim.esm EQUP RightHand: a staff gun goes in the right hand whatever the hands hold (a vanilla staff is "either hand", and went to the left with a gun in the right)
STAFF_BULLET_SPEED = 1.25  # the bullets fly this much faster than the Borderlands speed / 3 (the user asked for +25%)
STAFF_TRACER_LENGTH, STAFF_TRACER_WIDTH = 45.0, 0.8  # half the size of the first tracer (90 long, 1.6 wide)
MGEF_RESIST_AT = 16
PROJ_MUZZLE_LIGHT_AT, PROJ_MUZZLE_DURATION_AT = 20, 44
STAFF_FLASH_LENGTH, STAFF_FLASH_WIDTH, STAFF_FLASH_SECONDS = 26.0, 6.0, 0.05  # the muzzle flash: a short glowing burst ahead of the barrel
STAFF_FLASH_PERCENT = {"smg": 75, "assault_rifle": 90}  # the muzzle flash's size by gun type, in percent of the first flash (the user asked for 25% and 10% smaller)
RELOAD_PARTS = ("out", "in", "end")  # the magazine comes out, a new one goes in, the gun is made ready (bl2/audio.py RELOAD_PARTS)
STAFF_FLASH_LIGHT_RADIUS = 260
STAFF_MUZZLE_FLASH = False  # 0.17.0 turned the projectile's muzzle flash on and the game crashed on the first shot the plugin launched: off until a safer way is tested
STAFF_KINDS = ("smg", "assault_rifle")  # the gun types that are staff guns (the other types stay crossbows)
STAFF_NPC_BURST_MAX = 6


def muzzle_light(view: esp.Plugin, m: "Masters", edid: str, rgb: tuple[int, int, int], radius: int) -> int:
    """A point light for a muzzle flash, copied from a plain vanilla light (radius and colour changed, so nothing flickers, pulses or
    casts shadows), else written from scratch. Returns its form id."""
    best = None
    for r in sorted(m.by_type["LIGH"].values(), key=lambda r: r.edid):
        d = r.first("DATA")
        if not d or len(d) < 48 or r.first("MODL"):
            continue
        _, rad, _color, flags = struct.unpack_from("<iI4sI", d)
        score = (0 if flags & 1 else 1, 0 if not flags & LIGHT_BAD_FLAGS else 1, abs(rad - radius))
        if best is None or score < best[0]:
            best = (score, r)
    if best is not None:
        lt = esp.Rec("LIGH", view.new_id(f"LIGH:{edid}"), [(sig, d) for sig, d in best[1].subrecords if sig in LIGHT_KEEP])
        data = bytearray(lt.get("DATA"))
    else:
        lt = esp.Rec("LIGH", view.new_id(f"LIGH:{edid}"), [("OBND", obnd()), ("FNAM", struct.pack("<f", 1.0))])
        data = bytearray(struct.pack("<iI4sIffffffIf", -1, radius, bytes(4), 1, 1.0, 90.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0))
        lt.subs.insert(0, ("EDID", b""))
    lt.set("EDID", esp.zstr(edid))
    struct.pack_into("<I", data, 4, radius)
    data[8:12] = bytes([*rgb, 0])
    struct.pack_into("<I", data, 12, 0x1)  # dynamic only: no flicker, pulse, spot or shadows
    lt.set("DATA", bytes(data))
    order = ["EDID", "OBND", "DATA", "FNAM"]
    lt.subs.sort(key=lambda sd: order.index(sd[0]) if sd[0] in order else 99)
    view.override(lt)
    return lt.form_id


def sndr_prefix(style: str) -> str:
    """What comes before FX\\... in the file names of the vanilla sound descriptor we copy (this install's read "Data\\Sound\\FX\\WPN\\...", others
    "Sound\\FX\\...", others "FX\\..."): our files are named the same way."""
    at = style.lower().find("fx\\")
    return style[:at] if at > 0 else ""


STAFF_INFO_BUILD = "0.19.3"  # the build named in the staff gun's first message box (STAFF_REV names the id block and must not change)


class Armory:
    """The staff guns: every submachine gun and assault rifle variant of the crossbow set is turned into one IN PLACE (the same form id, so
    the loot lists, the form list of the beams, and every copy already lying in a saved game or carried by an enemy become staff guns;
    same parts, rarity, element, stats and name), each a vanilla staff weapon whose enchantment IS the bullet: one aimed fire-and-forget effect whose projectile
    is the Borderlands bullet of the gun type and element (speed, tracer colour, explosion from the rounds data).

    The player's gun is fired by the SKSE plugin from the attack button (script scripts.staff_gun, plugin FireGun), which keeps the
    game's own staff cast away. An enemy that holds one casts the enchantment as it would any staff and the plugin adds the rest of
    its burst (docs/enemy-ai.md). Each gun carries one keyword whose editor id holds its numbers (magazine, interval, reload, spread,
    burst), SkylandsGun_c<clip>_i<ms>_r<ms>_s<tenths of a degree>_b<burst>, which the plugin reads (GunClip, GunIntervalMs, GunReloadMs).
    Everything is in the second plugin."""

    def __init__(self, view: esp.Plugin, m: "Masters", rounds: "Rounds", gunner: "Gunner", models, data_dir: Path, hold_turn, report: dict,
                 shot_sounds: dict | None = None, sound_dir: Path | None = None) -> None:
        self.view, self.m, self.rounds, self.gunner, self.models, self.report = view, m, rounds, gunner, models, report
        self.shot_sounds = shot_sounds or {}  # {(gun type, manufacturer): [WAV files]} extracted from Borderlands 2
        self.sound_dir = sound_dir
        self.sndr: dict[tuple[str, str], int] = {}
        self.log = report["model_log"]
        self.ok = False
        self.by_rarity: dict[int, list[int]] = {}
        self.gifts: dict[str, int] = {}
        self.first_of: dict[str, int] = {}
        self.keywords: dict[str, int] = {}
        self.bullets: dict[tuple, tuple] = {}
        self.donors: dict[object, tuple | None] = {}
        self.strict: dict[object, tuple | None] = {}
        self.blasts: dict[tuple, int] = {}
        self.tracers: dict[str, bytes] = {}
        self.count = 0
        self.kinds: set[str] = set()
        for i in range(STAFF_ID_SHIFT):
            view.new_id(f"SHIFT:SkylandsStaffGun_{STAFF_REV}_{i}")
        # the ids of the records the player's script lives in, reserved now so they do not move when the number of guns does
        self.fx_id = view.new_id("MGEF:SkylandsStaffGunFx")
        self.ability_id = view.new_id("SPEL:SkylandsStaffGunAbility")
        self.quest_id = view.new_id("QUST:SkylandsStaffGunQuest")
        self.base = staff_donor(m, None, self.log)  # the weapon every staff gun is a copy of
        if self.base is None:
            return
        self.ok = True
        self.hold = None
        if models is not None:
            self.hold = models_mod.staff_hold(models_mod.find_vanilla_mesh(data_dir, self.base[0].first("MODL"), self.log.append, "staff"), hold_turn,
                                              self.log.append, STAFF_SCALE, STAFF_FORWARD, STAFF_LIFT)
            self.log.append(f"Staff guns: fit {self.hold.note}; turn {hold_turn}; extra data {self.hold.extra}")

    def _donor(self, element: str | None):
        if element not in self.donors:
            self.donors[element] = staff_donor(self.m, element, self.log)
        return self.donors[element]

    def _sound_template(self):
        """A vanilla standard sound descriptor with a category and an output model, to copy (weapon sounds first)."""
        if getattr(self, "_template", None) is None:
            best = None
            for r in self.m.by_type.get("SNDR", {}).values():
                cnam = r.first("CNAM")
                if not cnam or struct.unpack("<I", cnam[:4])[0] != 0x1EEF540A or not r.first("ANAM") or not (r.first("GNAM") and r.first("ONAM")):
                    continue
                key = (0 if re.search(r"wpn|crossbow|bow", r.edid or "", re.I) else 1, len(r.edid or ""), r.edid or "")
                if best is None or key < best[0]:
                    best = (key, r)
            self._template = best[1] if best else False
            if best:
                self.log.append(f"Staff guns: sound descriptors copied from {best[1].edid} (file name style {best[1].first('ANAM')[:40]!r})")
            else:
                self.log.append("Staff guns: no standard vanilla sound descriptor to copy; the Borderlands shot sounds cannot be attached")
        return self._template or None

    def _shot_sndr(self, kind: str, manufacturer: str, part: str = "shot") -> int | None:
        """The sound descriptor for the Borderlands shot of one gun type and manufacturer, or (part out, in or end) one part of its reload
        (its WAV files are copied to Data\\Sound\\FX\\Skylands)."""
        key = (kind, manufacturer) if part == "shot" else (kind, manufacturer, part)
        if key in self.sndr:
            return self.sndr[key]
        files = self.shot_sounds.get(key)
        template = self._sound_template() if files and self.sound_dir is not None else None
        if not files or template is None:
            return None
        style = template.first("ANAM").rstrip(b"\0").decode("latin-1", errors="replace")
        prefix = sndr_prefix(style)
        self.sound_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for f in files:
            (self.sound_dir / Path(f).name).write_bytes(Path(f).read_bytes())
            paths.append(f"{prefix}FX\\Skylands\\{Path(f).name}")
        edid = f"Skylands{'Shot' if part == 'shot' else 'Reload' + part.capitalize()}_{kind}_{re.sub('[^A-Za-z0-9]+', '_', manufacturer)}"
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
        rec = esp.Rec("SNDR", self.view.new_id(f"SNDR:{edid}"), subs)
        self.view.override(rec)
        self.sndr[key] = rec.form_id
        self.log.append(f"Staff guns: {kind} {manufacturer} {part} sound {edid}: {len(paths)} files, e.g. {paths[0]}")
        return rec.form_id

    def _element_donor(self, element: str | None):
        """A vanilla staff of the element itself (None for a plain gun, or when the game has none)."""
        if element is None:
            return None
        if element not in self.strict:
            self.strict[element] = staff_donor(self.m, element, self.log, strict=True)
        return self.strict[element]

    def _blast(self, kind: str, element: str, gt, shot) -> int:
        """The element's hit on whoever a bullet strikes: an explosion with NO art, sound or light (nothing is seen to explode), that carries
        the element's status effect and a little splash damage."""
        if (kind, element) in self.blasts:
            return self.blasts[(kind, element)]
        default_radius, frac = SPLASH.get(kind, (80.0, 0.3))
        radius = float(shot.explosion_radius) if shot and getattr(shot, "explosion_radius", None) else default_radius
        dmg = max(5, round(float(gt.base_damage) * frac / 5) * 5)
        edid = f"SkylandsStaffBlast_{kind}_{element}"
        donor = self.rounds.donor(element)
        r = esp.Rec("EXPL", self.view.new_id(f"EXPL:{edid}"), [])
        if donor is not None:
            r.subs = [(sig, d) for sig, d in donor.subrecords if sig not in ("EDID", "EITM", "MODL", "MODT", "MODS", "MNAM")]
            r.subs.insert(0, ("EDID", esp.zstr(edid)))
            data = bytearray(donor.first("DATA"))
        else:
            r.add("EDID", esp.zstr(edid)).add("OBND", struct.pack("<6h", 0, 0, 0, 0, 0, 0))
            data = bytearray(52)
            struct.pack_into("<I", data, 48, 1)
        struct.pack_into("<5I", data, 0, 0, 0, 0, 0, 0)  # light, two sounds, impact data set, placed object: none
        struct.pack_into("<fff", data, EXPL_FORCE_AT, 30.0, float(dmg), radius)
        struct.pack_into("<f", data, 36, 0.0)  # image space radius
        r.set("DATA", bytes(data))
        if self.rounds.enchants.get(element) is not None:
            insert_ordered(r, "EITM", esp.u32(self.rounds.enchants[element].form_id), EXPL_ORDER)
        self.view.override(r)
        self.blasts[(kind, element)] = r.form_id
        return r.form_id

    def _keyword(self, edid: str) -> int:
        if edid not in self.keywords:
            self.keywords[edid] = self.view.new("KYWD", edid).form_id
        return self.keywords[edid]

    def _bullet(self, kind: str, element: str | None, gt, shot):
        """The projectile and effect of one gun type x element, shared by its guns: (projectile id, the effect record's parts).
        A plain gun's bullet carries no element at all (no hit art, shader, impact, sound, keyword or resist: the donor staff's fire is stripped);
        an elemental gun's bullet is made from a staff of that element and carries only that one element's hit; nothing explodes visibly."""
        key = (kind, element)
        if key in self.bullets:
            return self.bullets[key]
        elem_donor = self._element_donor(element)
        plain = elem_donor is None
        donor = elem_donor or self._donor(None)
        _, _, d_mgef, d_proj = donor
        edid = f"SkylandsStaffBullet_{kind}_{(element or 'plain').lower()}"
        mesh = f"Skylands\\Tracer_Staff_{(element or 'plain').lower()}.nif"
        if mesh not in self.tracers:
            self.tracers[mesh] = nif.tracer(STAFF_TRACER_RGB.get(element.lower() if element else None, STAFF_TRACER_RGB[None]), BEAM_TEXTURE,
                                            STAFF_TRACER_LENGTH, STAFF_TRACER_WIDTH)
        pr = esp.Rec("PROJ", self.view.new_id(f"PROJ:{edid}"), [(sig, d) for sig, d in d_proj.subrecords if sig not in ("VMAD", "MODT", "NAM1", "NAM2")])
        pr.set("EDID", esp.zstr(edid))
        pr.set("MODL", esp.zstr(mesh))  # the glowing tracer (nif.tracer) instead of the donor's fireball
        pd = bytearray(d_proj.first("DATA"))
        speed = float(shot.speed_bl2 if shot else 20000) * BL2_TO_SKYRIM_SPEED * STAFF_BULLET_SPEED
        struct.pack_into("<ff", pd, PROJ_GRAVITY_AT, 0.0, speed)
        struct.pack_into("<f", pd, PROJ_RANGE_AT, 30000.0)
        struct.pack_into("<II", pd, PROJ_LIGHT_AT, 0, 0)  # the donor's firelight and muzzle light
        struct.pack_into("<I", pd, PROJ_SOUND_AT, 0)  # the donor's flight sound
        flags = struct.unpack_from("<H", pd, PROJ_FLAGS_AT)[0] & ~PROJ_FLAG_MUZZLE_FLASH
        flash = None
        if STAFF_MUZZLE_FLASH:  # our own glowing burst and a short light, shown for a moment where the bullet leaves
            rgb = STAFF_TRACER_RGB.get(element.lower() if element else None, STAFF_TRACER_RGB[None])
            flash = f"Skylands\\Flash_Staff_{(element or 'plain').lower()}.nif"
            if flash not in self.tracers:
                self.tracers[flash] = nif.tracer(rgb, BEAM_TEXTURE, STAFF_FLASH_LENGTH, STAFF_FLASH_WIDTH, forward=True)
            struct.pack_into("<I", pd, PROJ_MUZZLE_LIGHT_AT, muzzle_light(self.view, self.m, f"SkylandsMuzzleLight_{(element or 'plain').lower()}", rgb, STAFF_FLASH_LIGHT_RADIUS))
            struct.pack_into("<f", pd, PROJ_MUZZLE_DURATION_AT, STAFF_FLASH_SECONDS)
            flags |= PROJ_FLAG_MUZZLE_FLASH
        explosion = 0
        if element is not None:  # the element's status effect, delivered by a silent explosion
            explosion = self._blast(kind, element, gt, shot)
            flags |= 0x2
        else:
            flags &= ~0x2
        struct.pack_into("<H", pd, PROJ_FLAGS_AT, flags)
        struct.pack_into("<I", pd, PROJ_EXPLOSION_AT, explosion)
        pr.set("DATA", bytes(pd))
        at = next(i for i, (sig, _) in enumerate(pr.subs) if sig == "DATA")
        if flash:
            pr.subs.insert(at + 1, ("NAM1", esp.zstr(flash)))  # the muzzle flash model follows the data
        order = ["EDID", "VMAD", "OBND", "FULL", "MODL", "MODT", "MODC", "MODS", "DEST", "DSTD", "DSTF", "DATA", "NAM1", "NAM2", "VNAM"]
        pr.subs.sort(key=lambda sd: order.index(sd[0]) if sd[0] in order else 98)  # the order the game reads them in
        self.view.override(pr)
        md = bytearray(d_mgef.first("DATA"))
        struct.pack_into("<f", md, MGEF_COST_AT, 0.0)
        struct.pack_into("<II", md, MGEF_PROJECTILE_AT, pr.form_id, 0)  # projectile, explosion (the projectile carries its own)
        quiet_art(md, hit=False)
        drop = ("DNAM", "VMAD", "DATA", "EDID")
        if plain:  # no element: nothing of the donor's fire stays on the hit
            quiet_art(md, hit=True)
            struct.pack_into("<I", md, MGEF_IMPACT_DATA_AT, 0)
            struct.pack_into("<I", md, MGEF_RESIST_AT, 0xFFFFFFFF)  # no resistance applies
            drop += ("SNDD", "KSIZ", "KWDA")
        parts = ([(sig, d) for sig, d in d_mgef.subrecords if sig not in drop], bytes(md))
        self.bullets[key] = (pr.form_id, parts)
        return self.bullets[key]

    def add(self, g: dict, k: int, form_id: int, edid: str, gt, rr, built: dict, element: str | None, st: dict, damage: int, value: int, name: str, text: str,
            clip: int | None, rarity_kw: int, gun_kw: int, color, first_person: dict) -> int | None:
        """Turns one crossbow gun variant into a staff gun (an override in the second plugin with the crossbow's own form id)."""
        if not self.ok:
            return None
        kind = g["type"]
        shot = S.SHOOTING.get(kind)
        donor = self._donor(element) or self._donor(None)
        _, d_ench, d_mgef, _ = donor
        proj_id, (mparts, mdata) = self._bullet(kind, element, gt, shot)
        row = self.gunner.rows[self.gunner.index[(kind, g.get("manufacturer", ""))]] if (kind, g.get("manufacturer", "")) in self.gunner.index \
            else self.gunner.rows[KINDS.index(kind)]
        magazine = int(clip or row["clip"])
        # the gun's own rolled stats set its rate of fire, its reload and its accuracy (they are the numbers its description tells)
        interval = max(0.05, 1.0 / max(1.0, float(st["fire_rate"])))
        reload_s = max(0.3, float(st["reload"]))
        spread = float(row["spread"]) * float(st.get("spread_mult", 1.0))
        burst = max(1, min(STAFF_NPC_BURST_MAX, int(row["burst"])))
        text = f"{text} Accuracy: shots spread {spread:.1f} degrees."
        # the effect: this gun's own copy of the bullet effect, which carries its stats text (the crossbow guns show theirs the same way)
        mg = esp.Rec("MGEF", self.view.new_id(f"MGEF:Staff_{edid}"), [("EDID", esp.zstr(f"Staff_{edid}"))])
        mg.subs += [(sig, d) for sig, d in mparts]
        mg.set("FULL", esp.zstr("Gun stats"))
        at = next(i for i, (sig, _) in enumerate(mg.subs) if sig == "FULL")
        mg.subs.insert(at + 1, ("DNAM", esp.zstr(text)))
        mg.add("DATA", mdata)
        mg.subs.sort(key=lambda sd: ["EDID", "VMAD", "FULL", "MDOB", "KSIZ", "KWDA", "DNAM", "DATA"].index(sd[0]) if sd[0] in
                     ["EDID", "VMAD", "FULL", "MDOB", "KSIZ", "KWDA", "DNAM", "DATA"] else 7)
        self.view.override(mg)
        # the enchantment: that effect, no cost, no charge time
        en = esp.Rec("ENCH", self.view.new_id(f"ENCH:Staff_{edid}"), [(sig, d) for sig, d in d_ench.subrecords if sig not in ("EFID", "EFIT", "CTDA", "VMAD")])
        en.set("EDID", esp.zstr(edid))
        if en.get("FULL") is not None:
            en.set("FULL", esp.zstr("Gun stats"))
        enit = bytearray(d_ench.first("ENIT"))
        struct.pack_into("<i", enit, ENIT_COST_AT, 0)
        struct.pack_into("<I", enit, ENIT_FLAGS_AT, struct.unpack_from("<I", enit, ENIT_FLAGS_AT)[0] | 1)  # not auto-calculated: cost stays 0
        struct.pack_into("<f", enit, ENIT_CHARGE_AT, 0.0)  # no charge time
        en.set("ENIT", bytes(enit))
        en.add("EFID", esp.u32(mg.form_id)).add("EFIT", struct.pack("<fII", float(damage), 0, 0))
        self.view.override(en)
        # the weapon: a copy of the base staff, with this gun's name, numbers, keywords and model
        base = self.base[0]
        w = esp.Rec("WEAP", form_id, [(sig, d) for sig, d in base.subrecords if sig not in ("VMAD", "DESC", "EITM", "EAMT", "CNAM")],
                    flags=base.flags & esp.REC_COMPRESSED)  # CNAM: the template weapon (its model and stats win over this record's)
        w.set("EDID", esp.zstr(edid))
        insert_ordered(w, "FULL", esp.zstr(name), WEAP_ORDER)
        insert_ordered(w, "EITM", esp.u32(en.form_id), WEAP_ORDER)
        w.set("ETYP", esp.u32(STAFF_EQUIP_SLOT)) if w.get("ETYP") is not None else insert_ordered(w, "ETYP", esp.u32(STAFF_EQUIP_SLOT), WEAP_ORDER)
        insert_ordered(w, "EAMT", u16(min(65535, round(magazine * STAFF_CHARGE_PER_SHOT))), WEAP_ORDER)  # the charge gauge is the magazine
        dd = w.get("DATA") or b"\0" * 10
        insert_ordered(w, "DATA", struct.pack("<IfH", value, float(gt.weight), damage) + dd[10:], WEAP_ORDER)
        kwda = w.get("KWDA") or b""
        numbers = f"SkylandsGun_c{magazine}_i{round(interval * 1000)}_r{round(reload_s * 1000)}_s{round(spread * 10)}_b{burst}_e{ELEMENT_NAMES.index(element) + 1 if element in ELEMENT_NAMES else 0}_f{STAFF_FLASH_PERCENT.get(kind, 100)}"
        self.kinds.add(kind)
        ids = [*struct.unpack(f"<{len(kwda) // 4}I", kwda), gun_kw, rarity_kw, self._keyword(numbers), self._keyword(f"SkylandsSnd_{kind}")]
        mfr = g.get("manufacturer", "")
        own = [self._shot_sndr(kind, mfr), *(self._shot_sndr(kind, mfr, part) for part in RELOAD_PARTS)]
        if any(x is not None for x in own):  # this gun type from this manufacturer has its own Borderlands shot or reload sounds
            ids.append(self._keyword(f"SkylandsSnd_{kind}_{re.sub('[^A-Za-z0-9]+', '_', mfr)}"))
        insert_ordered(w, "KSIZ", struct.pack("<I", len(ids)), WEAP_ORDER)
        insert_ordered(w, "KWDA", struct.pack(f"<{len(ids)}I", *ids), WEAP_ORDER)
        mesh = self.models.model_for(g, built, rr.id, color, edid, self.hold) if self.models is not None else None
        if mesh:
            w.set("MODL", esp.zstr(mesh))
            w.drop("MODT", "MODS", "MO2T", "MO2S")
            if mesh not in first_person:
                fp = self.view.new("STAT", "SkylandsGunView_" + mesh.rsplit("\\", 1)[-1].removesuffix(".nif"))
                fp.add("OBND", struct.pack("<6h", -40, -40, -40, 40, 40, 40)).add("MODL", esp.zstr(mesh)).add("DNAM", struct.pack("<fI", 30.0, 0))
                first_person[mesh] = fp.form_id
            insert_ordered(w, "WNAM", esp.u32(first_person[mesh]), WEAP_ORDER)
        self.view.override(w)
        self.by_rarity.setdefault(rr.level, []).append(w.form_id)
        self.count += 1
        self.first_of.setdefault(kind, w.form_id)
        if kind not in self.gifts and rr.level >= 3:  # the first good one of each type goes to the player at the start, to try them
            self.gifts[kind] = w.form_id
        self.report.setdefault("staff_guns", {})[edid] = {"name": name, "element": element, "damage": damage, "magazine": magazine,
                                                          "interval": interval, "burst": burst, "mesh": mesh}
        return w.form_id

    def finish(self, m: "Masters") -> None:
        """The player's script: an ability (run by a start-game-enabled quest) with the few numbers that are not the gun's own."""
        if not self.ok:
            return
        sound = staff_shot_sound(m, self.log, "smg")
        snd_kw, snd_ids = [], []
        reload_ids: dict[str, list[int]] = {part: [] for part in RELOAD_PARTS}  # parallel to snd_ids: the three parts of the reload (0: silent)
        stand_in = {kind: staff_shot_sound(m, self.log, kind) for kind in sorted(self.kinds)}
        for kind, mfr in sorted({k[:2] for k in self.sndr}):  # the Borderlands sounds of a gun type and manufacturer, tried before the stand-ins
            snd_kw.append(self._keyword(f"SkylandsSnd_{kind}_{re.sub('[^A-Za-z0-9]+', '_', mfr)}"))
            snd_ids.append(self.sndr.get((kind, mfr)) or (stand_in[kind][0] if stand_in.get(kind) else 0))
            for part in RELOAD_PARTS:
                reload_ids[part].append(self.sndr.get((kind, mfr, part), 0))
        for kind in sorted(self.kinds):  # one shot sound per gun type, found by the gun's SkylandsSnd_<type> keyword
            found = stand_in[kind]
            if found:
                snd_kw.append(self._keyword(f"SkylandsSnd_{kind}"))
                snd_ids.append(found[0])
                for part in RELOAD_PARTS:
                    reload_ids[part].append(0)
        gifts = [self.gifts.get(kind) or self.first_of.get(kind) or next(iter(self.first_of.values())) for kind in STAFF_KINDS]
        info = (f"Build {STAFF_INFO_BUILD}. {self.count} staff guns (submachine guns and assault rifles) from the vanilla staff {self.base[0].edid}; "
                f"each one's numbers are in its SkylandsGun_ keyword; tracers {len(self.tracers)}; shot sound {sound[1] if sound else 'none found'}; "
                f"the SKSE plugin launches a bullet from the gun's muzzle when the attack button goes down, then one every interval while it is held.")
        props = [("ChargePerShot", esp.P_FLOAT, STAFF_CHARGE_PER_SHOT),
                 ("OffsetRight", esp.P_FLOAT, STAFF_OFFSET[0]), ("OffsetUp", esp.P_FLOAT, STAFF_OFFSET[1]), ("OffsetForward", esp.P_FLOAT, STAFF_OFFSET[2]),
                 ("ShotSound", esp.P_OBJECT, sound[0] if sound else 0), ("SoundKeywords", esp.P_OBJECT_ARRAY, snd_kw), ("Sounds", esp.P_OBJECT_ARRAY, snd_ids),
                 ("ReloadOut", esp.P_OBJECT_ARRAY, reload_ids["out"]), ("ReloadIn", esp.P_OBJECT_ARRAY, reload_ids["in"]), ("ReloadEnd", esp.P_OBJECT_ARRAY, reload_ids["end"]), ("GiftA", esp.P_OBJECT, gifts[0]), ("GiftB", esp.P_OBJECT, gifts[1]),
                 ("SpeedMult", esp.P_FLOAT, STAFF_SPEED_MULT), ("Info", esp.P_STRING, info), ("Verbose", esp.P_BOOL, True)]
        fx = script_effect(self.view, m.need("MGEF", "AbWeaknessFireConstant"), "SkylandsStaffGunFx", "Skylands Staff Gun", STAFF_SCRIPT, props)
        assert fx == self.fx_id
        ability = spell(self.view, "SkylandsStaffGunAbility", "", "",
                        struct.pack("<IIIfIIffI", 0, 0, SPELL_ABILITY, 0, CAST_CONSTANT, DELIVERY_SELF, 0, 0, 0), [(fx, 0.0, 0, 0)])
        assert ability.form_id == self.ability_id
        q = self.view.new("QUST", "SkylandsStaffGunQuest")
        assert q.form_id == self.quest_id
        q.add("VMAD", esp.vmad([("SkylandsGunnerQuest", [("Ability", esp.P_OBJECT, ability.form_id)])], quest=True))
        q.add("FULL", esp.zstr("Skylands Staff Gun")).add("DNAM", struct.pack("<HBBII", QUEST_START_GAME_ENABLED, 50, 0, 0, 0))
        q.add("ANAM", esp.u32(0))
        for percent in sorted(set(STAFF_FLASH_PERCENT.values())):
            for word, rgb in (("plain", STAFF_TRACER_RGB[None]), *((n.lower(), STAFF_TRACER_RGB[n.lower()]) for n in ELEMENT_NAMES)):
                # the muzzle flash meshes the plugin spawns at the barrel (one in each element's colour and each size); they are not a projectile feature
                self.tracers[f"Skylands\\Flash_Staff_{word}_{percent}.nif"] = nif.tracer(rgb, BEAM_TEXTURE, STAFF_FLASH_LENGTH * percent / 100, STAFF_FLASH_WIDTH * percent / 100,
                                                                                        forward=True)
        self.report["staff_tracer"] = list(self.tracers.items())
        self.report["staff_gun"] = {"guns": self.count, "tracers": len(self.tracers)}
        self.log.append(f"Staff guns: {self.count} built; gifts {[hex(g) for g in gifts]}; {info}")


def quiet_art(md: bytearray, hit: bool) -> None:
    """Strips the donor effect's art from an effect record's DATA: the casting light and casting art (the fireball that floated
    above the staff gun), the enchant shader and enchant art, the dual casting art, and for a trigger also the hit art."""
    if len(md) < MGEF_ENCHANT_ART_AT + 4:
        return
    struct.pack_into("<I", md, MGEF_LIGHT_AT, 0)
    struct.pack_into("<I", md, MGEF_ENCHANT_SHADER_AT, 0)
    struct.pack_into("<I", md, MGEF_CASTING_ART_AT, 0)
    struct.pack_into("<I", md, MGEF_DUAL_ART_AT, 0)
    struct.pack_into("<I", md, MGEF_ENCHANT_ART_AT, 0)
    if hit:
        struct.pack_into("<I", md, MGEF_HIT_SHADER_AT, 0)
        struct.pack_into("<I", md, MGEF_HIT_ART_AT, 0)


def d_ench_cast(ench: Record) -> int:
    """The cast type (1 fire and forget, 2 concentration) the donor staff's enchantment uses, from its ENIT."""
    enit = ench.first("ENIT") or b""
    return struct.unpack_from("<I", enit, 8)[0] if len(enit) >= 12 else 1


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
             gun_models: str = "off", model_sources: dict | None = None, model_spin: float = 0.0, model_pitch: float = 0.0, model_calibrate: bool = False,
             model_scale: float = 1.0, shooting: str = "off",
             staff_turn: tuple[float, float, float] = (0.0, 0.0, 0.0), shot_sounds: dict | None = None) -> dict:
    """formids: the form ids of earlier builds (updated in place with any new ones); see esp.Plugin.
    gun_models: how the guns get their own meshes (models.METHODS); model_sources: readers of Borderlands 2 meshes by method."""
    data_dir = Path(skyrim_dir) / "Data"
    m = Masters.load(data_dir, {"WEAP", "AMMO", "NPC_", "LVLI", "MGEF", "ENCH", "EQUP", "SHOU", "WOOP", "SPEL", "LIGH", "RACE", "PROJ", "EXPL", "SNDR"})
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
                                  model_log.append, model_sources, model_spin, model_scale, model_pitch, model_calibrate) if gun_models != "off" else None
    bolts = m.need("AMMO", S.SKYRIM_BASE["bolts"].edid)
    base_enchant = {e.bl2_part: m.need("ENCH", e.skyrim_enchantment) for e in S.ELEMENTS.values()}
    any_enchant = next(iter(base_enchant.values()))
    stats_mgef = stats_template(m, any_enchant)
    armory: Armory | None = None
    rounds = Rounds(view, m, bolts, base_enchant, report["model_log"]) if shooting in ("bl2", "both", "staff") else None
    if rounds is not None:
        shots = S.SHOOTING
        for kind in KINDS:
            gtype = next(g for g in S.GUN_TYPES.values() if g.id == kind)
            for element in (None, *ELEMENT_NAMES):
                rounds.build(kind, element, float(gtype.base_damage), shots.get(kind))
        gunner = Gunner(view, shots, bl2["weapons"]["guns"])
        make_gunner(view, m, rounds, gunner, bolts.form_id)
        if shooting == "staff":  # submachine guns and assault rifles are staff guns (the other types stay crossbows)
            armory = Armory(view, m, rounds, gunner, models, data_dir, staff_turn, report, shot_sounds, out_data / "Sound" / "FX" / "Skylands")
    if shooting in ("bullets", "both"):
        tune_bolts(view, m, bolts, report["model_log"])

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
            twin = armory is not None and armory.ok and g["type"] in STAFF_KINDS
            mesh = models.model_for(g, built, rr.id, rarity_color(bl2["rarities"], rr.level), edid) if models is not None and not twin else None
            if twin:  # this gun is a staff gun: the same form id, overridden in the second plugin
                clip_n = max(1, round(g["clip"] * st.get("clip_mult", 1.0))) if g.get("clip") else None
                armory.add(g, k, w.form_id, edid, gt, rr, built, element, st, damage, value, name, text, clip_n, rarity_keywords[rr.level], gun_keyword,
                           rarity_color(bl2["rarities"], rr.level), first_person)
            elif mesh or rounds is not None:
                # What changes about a gun with models or Borderlands rounds goes in a second plugin, as an override of the
                # whole record, so Skylands.esp never changes (it must stay light or every save made with it loses its
                # powers and guns).
                w2 = esp.Rec(w.type, w.form_id, list(w.subs), flags=w.flags)
                if mesh:
                    w2.set("MODL", esp.zstr(mesh))
                    w2.drop("MODT", "MODS", "MO2T", "MO2S")
                    if mesh not in first_person:  # the model Skyrim shows in first person (and, it seems, in the inventory)
                        fp = view.new("STAT", "SkylandsGunView_" + mesh.rsplit("\\", 1)[-1].removesuffix(".nif"))
                        fp.add("OBND", struct.pack("<6h", -40, -40, -40, 40, 40, 40)).add("MODL", esp.zstr(mesh))
                        fp.add("DNAM", struct.pack("<fI", 30.0, 0))
                        first_person[mesh] = fp.form_id
                    insert_ordered(w2, "WNAM", esp.u32(first_person[mesh]), WEAP_ORDER)
                if rounds is not None:  # keywords that tell the gunner script which rounds and numbers this gun uses
                    kw2 = w2.get("KWDA") or b""
                    clip = max(1, round(g["clip"] * st.get("clip_mult", 1.0))) if g.get("clip") else None
                    ids = [*struct.unpack(f"<{len(kw2) // 4}I", kw2), *rounds.keywords(g["type"], element), *gunner.for_gun(g, clip)]
                    insert_ordered(w2, "KSIZ", struct.pack("<I", len(ids)), WEAP_ORDER)
                    insert_ordered(w2, "KWDA", struct.pack(f"<{len(ids)}I", *ids), WEAP_ORDER)
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
    if rounds is not None:
        report["rounds"] = {"ammo": rounds.made}
        report["model_log"].append(f"Shooting: {rounds.made} Borderlands round types built")
    if models is not None:
        models.flush_textures()
        report["gun_models"] = {"method": gun_models, **models.stats, "by_method": models.by_method, "textures": len(models.textures)}
        report["model_log"].append(models.summary())

    tier_lists = {lvl: leveled_list(p, f"SkylandsGuns_{rarity_row(lvl).id}", [(f, 1) for f in ids]).form_id
                  for lvl, ids in sorted(by_rarity.items())}
    if armory is not None and armory.ok and armory.count:
        armory.finish(m)  # the loot lists and the beams' form list are untouched: they hold these very form ids
        report["staff_converted"] = armory.count
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
    if rounds is not None:
        (out_data / "Meshes" / "Skylands" / "AimPoint.nif").write_bytes(nif.empty())
        (out_data / "Scripts" / "SkylandsGunner.pex").write_bytes(pex.write(scripts.gunner()))
        (out_data / "Scripts" / "SkylandsGunnerQuest.pex").write_bytes(pex.write(scripts.gunner_quest()))
        if shooting == "staff":
            (out_data / "Scripts" / f"{STAFF_SCRIPT}.pex").write_bytes(pex.write(scripts.staff_gun(STAFF_SCRIPT)))
            (out_data / "Scripts" / "SkylandsStaffGun.pex").write_bytes(pex.write(scripts.retired("SkylandsStaffGun")))  # earlier revisions' name
            (out_data / "Scripts" / "SkylandsNative.pex").write_bytes(pex.write(scripts.native_stub()))  # the declarations of the SKSE plugin's functions
            for old_name in ("SkylandsStaffGun19", "SkylandsStaffGun18", "SkylandsStaffGun17", "SkylandsStaffGun11", "SkylandsStaffGun12", "SkylandsStaffGun13", "SkylandsStaffGun14", "SkylandsStaffGun15", "SkylandsStaffGun16"):
                (out_data / "Scripts" / f"{old_name}.pex").write_bytes(pex.write(scripts.retired(old_name)))
    for mesh_path, mesh_bytes in report.pop("staff_tracer", []):  # the mesh bytes are not part of the report
        (out_data / "Meshes" / Path(*mesh_path.split("\\"))).write_bytes(mesh_bytes)
    report["records"] = len(p.records)
    return report
