"""Shield items, the Borderlands 2 way: an armor record for every combination of a shield type, a rarity and a roll of body, battery and capacitor parts.

In Borderlands 2 a shield is built from five parts: a body, a battery and a capacitor (each from one of nine manufacturers, each adding grades to the shield's
capacity, recharge rate and recharge delay), an accessory (the type: nova, spike, absorb ...) and a material (the rarity, which adds more grades). The slot grade is
the sum of the parts' grades; the stat is its base times (1 + grade x step). The tables are in shielddata.py (read from a real install; the installer reads the
same objects from the player's own files and their values replace these, bl2/extract.shield_parts). This module rolls a fixed number of builds for each
type and rarity, works their numbers out and writes the records:

  KYWD  SkylandsShield                    marks a shield item (the plugin lists them when the game has loaded)
  KYWD  SkylandsShield_t.._e.._k.._r.._d.._g..   its numbers, read by the plugin: type, element, capacity (per mille of the wearer's max health), recharge rate
                                          (per mille of the capacity per second), delay (tenths of a second), grade of the rarity
  KYWD  SkylandsRarity_<rarity>           the rarity (shared with the guns)
  MGEF/ENCH  a constant-effect enchantment: shows the stats on the item, and gives a resistance when a resistance capacitor is part of the build
  ARMO  the item: clothing worn in one biped slot that nothing else uses (chosen by the installer, `choose_slot`), the worn model is empty (an ARMA
        with no model), the world and inventory model is the shield's four parts cut from Borderlands 2's combined shield mesh
  ARMA  one armature with no model, in that slot

Nothing here changes Skylands.esp: all records go to the models plugin.
"""

from __future__ import annotations

import hashlib
import random
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from . import meshes as M
from . import shielddata as D
from . import sheet_data as S
from .skyrim import dxt, esp, nif

MESH_DIR = "Skylands\\Shields"  # under Meshes\
TEX_DIR = "textures\\skylands\\shields"
SIZE = 20.0  # the longest side of a shield model in Skyrim units (a hand is about 8)
HAVOK_SCALE = 69.99125
DEFAULT_RACE = 0x00000019  # Skyrim.esm DefaultRace: the armature belongs to it
# slots tried in this order when the installer looks for one nothing in the player's load order uses (the vanilla game uses 30-61 for armor; the high ones the least)
SLOT_ORDER = (60, 61, 59, 58, 57, 56, 55, 54, 53, 52, 51, 50, 48, 49, 47, 46, 45, 44, 43, 42, 41, 40)
RARITY_OF_LEVEL = {1: "common", 2: "uncommon", 3: "rare", 4: "epic", 5: "legendary"}
ELEMENT_WORDS = {0: "", 1: "Fire", 2: "Shock", 3: "Corrosive", 4: "Explosive"}
RESIST_WORD = {"fire": "Fire", "shock": "Shock", "corrosive": "Corrosive", "explosive": "Explosive"}
ELEMENT_NUMBER = {"fire": 1, "shock": 2, "corrosive": 3, "explosive": 4}

# type numbers: the keyword's t (the plugin's effects use them) and what each does in Borderlands 2 (the plugin does not do them yet; the text says so)
TYPES = {0: "Standard", 1: "Nova", 2: "Spike", 3: "Amp", 4: "Roid", 5: "Absorb", 6: "Booster", 7: "Turtle", 8: "Adaptive"}
TYPE_TEXT = {
    0: "",
    1: "Nova: when the shield breaks it bursts, hurting everyone close with its element.",
    2: "Spike: enemies that hit the shield take its element's damage.",
    3: "Amp: the first shot after the shield is full does extra damage, and drains the shield.",
    4: "Roid: bonus melee damage while the shield is up and for a moment after it breaks.",
    5: "Absorb: a chance for a hit to refill the shield instead of hurting it.",
    6: "Booster: faster fire and reload while the shield is up.",
    7: "Turtle: a large shield that recharges slowly and mends the wearer.",
    8: "Adaptive: resists the element it was last hit by.",
}


@dataclass(frozen=True)
class Family:
    id: str
    title: str
    type_no: int
    element: int
    material: str  # shielddata.MATERIALS group
    capacitors: str  # shielddata.CAPACITOR_LISTS key
    accessory: str  # shielddata.ACCESSORIES key
    levels: tuple[int, ...] = (1, 2, 3, 4)
    unique: str | None = None  # the name of a unique shield (no prefix, no manufacturer)


FAMILIES = [
    Family("standard", "Shield", 0, 0, "NoSpecial", "Standard", "Accessory0_None"),
    Family("absorb", "Absorb Shield", 5, 0, "Absorption", "Standard", "Accessory3_Absorption"),
    Family("booster", "Booster Shield", 6, 0, "Booster", "Standard", "Accessory4_Booster"),
    Family("adaptive", "Adaptive Shield", 8, 0, "Chimera", "Chimera", "Accessory5_Chimera"),
    Family("amp", "Amplify Shield", 3, 0, "Impact", "Standard", "Accessory7_Impact"),
    Family("turtle", "Turtle Shield", 7, 0, "Juggernaut", "Standard", "Accessory8_Juggernaut"),
    Family("roid", "Roid Shield", 4, 0, "Roid", "Standard", "Accessory2_Roid"),
    Family("nova_fire", "Fire Nova Shield", 1, 1, "NovaSpike_Maliwan", "Nova_Fire", "Accessory6_Nova_Fire"),
    Family("nova_shock", "Shock Nova Shield", 1, 2, "NovaSpike_Maliwan", "Nova_Shock", "Accessory6_Nova_Shock"),
    Family("nova_corrosive", "Acid Nova Shield", 1, 3, "NovaSpike_Maliwan", "Nova_Corrosive", "Accessory6_Nova_Corrosive"),
    Family("nova_explosive", "Explosive Nova Shield", 1, 4, "NovaSpike_Torgue", "Nova_Explosive", "Accessory6_Nova_Explosive"),
    Family("spike_fire", "Fire Spike Shield", 2, 1, "NovaSpike_Maliwan", "Spike_Fire", "Accessory1_Spike_Fire"),
    Family("spike_shock", "Shock Spike Shield", 2, 2, "NovaSpike_Maliwan", "Spike_Shock", "Accessory1_Spike_Shock"),
    Family("spike_corrosive", "Acid Spike Shield", 2, 3, "NovaSpike_Maliwan", "Spike_Corrosive", "Accessory1_Spike_Corrosive"),
    Family("spike_explosive", "Explosive Spike Shield", 2, 4, "NovaSpike_Torgue", "Spike_Explosion", "Accessory1_Spike_Explosive"),
    # the unique shields: one material each, a fixed rarity, a name of their own
    Family("phoenix", "Phoenix", 1, 1, "Nova_Phoenix", "Nova_Fire", "Accessory6_Nova_Phoenix", (4,), "Phoenix"),
    Family("singularity", "Singularity", 1, 2, "Nova_Singularity", "Nova_Shock", "Accessory6_Nova_Singularity", (5,), "Singularity"),
    Family("deadly_bloom", "Deadly Bloom", 1, 4, "Nova_DeadlyBloom", "Nova_Explosive", "Accessory6_Nova_Explosive_DeadlyBloom", (5,), "Deadly Bloom"),
    Family("acid_spike_legend", "Acid Spike Shield", 2, 3, "Spike", "Spike_Corrosive", "Accessory1_Spike_Corrosive_Legendary", (5,), "Legendary Acid Spike Shield"),
]


# ---- the tables, with what the player's own files say ------------------------------------------------------------------------------------------------

class Tables:
    """shielddata with the values read from the player's files laid over it (bl2/extract.shield_parts: {"bodies": {key: (cap, rate, delay)}, "batteries": ..., "capacitors": ...,
    "materials": {group: {level: (cap, rate, delay, s1, s2)}}, "steps": {"capacity": .., "rate": .., "delay": ..}, "read": n, "wanted": n})."""

    def __init__(self, read: dict | None = None) -> None:
        read = read or {}
        self.steps = dict(D.STEPS)
        self.steps.update({k: v for k, v in (read.get("steps") or {}).items() if k in self.steps})
        self.bodies = {k: list(v) for k, v in D.BODIES.items()}
        self.batteries = {k: list(v) for k, v in D.BATTERIES.items()}
        self.capacitors = {k: list(v) for k, v in D.CAPACITORS.items()}
        self.materials = {g: {lv: list(t) for lv, t in levels.items()} for g, levels in D.MATERIALS.items()}
        self.replaced = 0
        for key, (cap, rate, delay) in (read.get("bodies") or {}).items():
            if key in self.bodies and [cap, rate, delay] != self.bodies[key][2:5]:
                self.bodies[key][2:5] = [cap, rate, delay]
                self.replaced += 1
        for table, src in ((self.batteries, read.get("batteries")), (self.capacitors, read.get("capacitors"))):
            for key, nums in (src or {}).items():
                if key in table and list(nums) != table[key][2:7]:
                    table[key][2:7] = list(nums)
                    self.replaced += 1
        for group, levels in (read.get("materials") or {}).items():
            for level, nums in levels.items():
                if group in self.materials and level in self.materials[group] and list(nums) != self.materials[group][level][1:6]:
                    self.materials[group][level][1:6] = list(nums)
                    self.replaced += 1
        self.read, self.wanted = read.get("read", 0), read.get("wanted", 0)


@dataclass
class Build:
    family: Family
    level: int
    body: str
    battery: str
    capacitor: str
    grades: tuple[int, int, int]  # capacity, rate, delay: the sum of the parts' and the material's
    parts_grades: tuple[int, int, int]  # the parts' only (what the name goes by)
    special: tuple[int, int]
    resist: str | None
    ratio: float = 0.0  # capacity as a share of max health
    rate: float = 0.0  # recharge per second, as a share of the capacity
    delay: float = 0.0  # seconds
    name: str = ""
    edid: str = ""


def prefix_for(t: Tables, body: str, parts: tuple[int, int, int], resist: str | None) -> str:
    """The name part BL2 puts in front: the resistance's word when the capacitor makes one, else the strongest stat's word for the body's manufacturer."""
    if resist:
        return {"fire": "Inflammable", "shock": "Grounded", "corrosive": "Alkaline", "explosive": "Blast proof"}[resist]
    stats = ("Capacity", "Rate", "Delay")
    best = max(range(3), key=lambda i: (parts[i], -i))
    if max(parts) - min(parts) <= 6 and abs(parts[best]) <= 3:
        return D.PREFIXES.get(f"Prefix_Balanced_{body}", "")
    g = parts[best]
    level = 1 if g <= -8 else 2 if g <= -2 else 3 if g <= 5 else 4 if g <= 12 else 5
    return D.PREFIXES.get(f"Prefix_{stats[best]}_{body}0{level}", "")


def roll(t: Tables, S_: dict, seed: int) -> list[Build]:
    """The builds of every family and rarity: `variants` of each, bodies all different, every third one with a matched battery and capacitor."""
    variants = int(S_["variants_per_roll"])
    base_ratio, rate_base, delay_base = S_["capacity_ratio"], S_["rate_fraction"], S_["delay_s"]
    delay_min = S_["delay_min_s"]
    out: list[Build] = []
    mfrs = list(D.BODIES)
    for fam in FAMILIES:
        caps = D.CAPACITOR_LISTS[fam.capacitors]
        for level in fam.levels:
            rnd = random.Random(f"{seed}|{fam.id}|{level}")
            order = rnd.sample(mfrs, len(mfrs))
            for k in range(variants if fam.unique is None else min(variants, 3)):
                body = order[k % len(order)]
                matched = k % 3 == 0
                battery = body if matched else rnd.choice(list(t.batteries))
                pool = [c for c in caps if c in t.capacitors]
                cap_key = next((c for c in pool if c.split("_")[0] == body), None) if matched else None
                if cap_key and "_" in cap_key and fam.element and ELEMENT_NUMBER.get(t.capacitors[cap_key][7] or "", 0) not in (0, fam.element):
                    cap_key = None  # a Maliwan resistance capacitor of another element than the shield's does not belong to a matched set
                capacitor = cap_key or rnd.choice(pool)
                bd, bt, cp = t.bodies[body], t.batteries[battery], t.capacitors[capacitor]
                mat = t.materials[fam.material][level]
                parts = (bd[2] + bt[2] + cp[2], bd[3] + bt[3] + cp[3], bd[4] + bt[4] + cp[4])
                grades = (parts[0] + mat[1], parts[1] + mat[2], parts[2] + mat[3])
                b = Build(fam, level, body, battery, capacitor, grades, parts, (bt[5] + cp[5] + mat[4], bt[6] + cp[6] + mat[5]), cp[7])
                b.ratio = base_ratio * max(0.4, 1.0 + t.steps["capacity"] * grades[0])  # BL2's own lowest is 0.4 (the Tediore very rare: -20 grades)
                b.rate = rate_base * max(0.2, 1.0 + t.steps["rate"] * grades[1])
                b.delay = max(delay_min, delay_base * (1.0 + t.steps["delay"] * grades[2]))
                prefix = "" if fam.unique else prefix_for(t, body, parts, b.resist)
                b.name = fam.unique or " ".join(w for w in (prefix, body, fam.title) if w)
                key = f"{fam.id}_{level}_{k}"
                b.edid = f"SkylandsShieldItem_{key}"
                out.append(b)
    return out


def stats_text(b: Build, rarity_word: str, resist_percent: float) -> str:
    g = b.grades

    def signed(v: int) -> str:
        return f"{v:+d}"

    lines = [f"{rarity_word} {TYPES[b.family.type_no].lower() if b.family.type_no else 'standard'} shield" + (f", {ELEMENT_WORDS[b.family.element].lower()}" if b.family.element else "") + ".",
             f"Capacity {b.ratio * 100:.0f}% of your health (grade {signed(g[0])})",
             f"Recharge {b.rate * 100:.0f}% of the capacity a second (grade {signed(g[1])})",
             f"Starts recharging {b.delay:.1f} s after the last hit (grade {signed(g[2])})"]
    if b.resist:
        lines.append(f"Resists {RESIST_WORD[b.resist].lower()} {resist_percent:.0f}%")
    lines.append(f"Parts: {b.body} body, {b.battery} battery, {b.capacitor.split('_')[0]} capacitor.")
    text = TYPE_TEXT[b.family.type_no]
    if text:
        lines.append(text + " (Not active in this version.)")
    return "\n".join(lines)


def keyword_text(b: Build) -> str:
    return (f"SkylandsShield_t{b.family.type_no}_e{b.family.element}_k{round(b.ratio * 1000)}_r{round(b.rate * 1000)}_d{round(b.delay * 10)}_g{b.level}")


# ---- the biped slot -----------------------------------------------------------------------------------------------------------------------------------

def slot_use(data_dir: Path, say=None, budget_s: float = 25.0) -> dict[int, int]:
    """How many armor and armature records of the plugins in the Data folder use each biped slot (30-61). Only the ARMO and ARMA groups are read."""
    import time

    from .skyrim import esm

    use: dict[int, int] = {}
    t0 = time.time()
    own = {"skylands.esp", "skylandsgunmodels.esp"}  # an earlier install of this mod must not count: its own shields sit in the slot
    plugins = sorted(p for p in Path(data_dir).glob("*") if p.suffix.lower() in (".esm", ".esp", ".esl") and p.name.lower() not in own)
    for path in plugins:
        if time.time() - t0 > budget_s:
            if say:
                say(f"shield slot: the time budget ran out after {len(use)} slots counted; {path.name} and the plugins after it were not read")
            break
        try:
            _tes4, groups = esm.read_plugin(path, {"ARMO", "ARMA"})
        except Exception as e:  # noqa: BLE001 - a plugin that cannot be read must not stop the install
            if say:
                say(f"shield slot: {path.name} not read ({type(e).__name__}: {str(e)[:60]})")
            continue
        for rtype in ("ARMO", "ARMA"):
            for rec in groups.get(rtype, []):
                bod2 = rec.first("BOD2")
                bodt = rec.first("BODT")
                mask = struct.unpack_from("<I", bod2)[0] if bod2 and len(bod2) >= 4 else struct.unpack_from("<I", bodt)[0] if bodt and len(bodt) >= 4 else 0
                for slot in range(30, 62):
                    if mask & (1 << (slot - 30)):
                        use[slot] = use.get(slot, 0) + 1
    return use


def choose_slot(data_dir: Path, say=None, wanted: int | None = None) -> tuple[int, str]:
    """The biped slot the shields are worn in, and why. `wanted` (the settings file's ShieldSlot, when the player set one) is kept."""
    if wanted and 30 <= wanted <= 61:
        return wanted, f"slot {wanted} (kept from your settings)"
    use = slot_use(data_dir, say)
    for slot in SLOT_ORDER:
        if use.get(slot, 0) == 0:
            return slot, f"slot {slot} (no armor or armature in your load order uses it; counted {sum(use.values())} uses of {len(use)} slots)"
    slot = min(SLOT_ORDER, key=lambda s: use.get(s, 0))
    return slot, f"slot {slot} (every candidate is used by something; this one by {use.get(slot, 0)} records)"


# ---- the models ---------------------------------------------------------------------------------------------------------------------------------------

class Models:
    """Shield meshes written under Meshes\\Skylands\\Shields: the four parts cut from the combined shield mesh when Borderlands 2's meshes can be read, else a stylised orb."""

    ATLAS = "Item_Shields.Textures.Shield_Dif"

    def __init__(self, out_data: Path, source, say, tint: dict[str, tuple[int, int, int]]) -> None:
        self.out = Path(out_data)
        self.source = source
        self.say = say
        self.tint = tint
        self.written: dict[str, str] = {}
        self.textures: dict[str, bytes] = {}
        self.stats = {"real": 0, "proxy": 0, "shared": 0}
        self.noted: set[str] = set()
        self._raw: tuple | None | bool = False

    def _atlas(self, mfr: str) -> str | None:
        """The shield texture atlas, shaded for the manufacturer; its path under Data (or None when it cannot be read)."""
        if self._raw is False:
            self._raw = None
            if self.source is not None:
                try:
                    key = self.source._texture(self.ATLAS)
                    raw = self.source.textures.pop(key, None) if key else None
                    self._raw = dxt.prepare(raw) if raw else None
                except Exception as e:  # noqa: BLE001
                    self.say(f"shield models: the atlas texture could not be read ({type(e).__name__}: {str(e)[:80]})")
        if self._raw is None:
            return None
        name = f"atlas_{mfr}"
        if name not in self.textures:
            self.textures[name], note = dxt.shade(self._raw, self.tint.get(mfr, (150, 150, 156)))
            if note not in self.noted:
                self.noted.add(note)
                self.say(f"shield models: atlas texture: {note}")
        return f"{TEX_DIR}\\{name}.dds"

    def _plain(self, rgb: tuple[int, int, int]) -> str:
        name = f"c_{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        self.textures.setdefault(name, nif.dds_solid(rgb))
        return f"{TEX_DIR}\\{name}.dds"

    def _flat(self) -> str:
        self.textures.setdefault("flat_n", nif.dds_flat_normal())
        return f"{TEX_DIR}\\flat_n.dds"

    def _cut(self, fragments: list[str]) -> list[M.Mesh] | None:
        src = self.source
        table = getattr(src, "gestalt_table", None)
        if not table:
            return None
        parts = []
        for frag in fragments:
            name = frag.lower()
            if name not in table:
                return None
            got = src._read_gestalt_part("shield", name)
            if not got:
                return None
            parts.append(got["mesh"])
        return parts

    def _proxy(self, b: Build, accent: tuple[int, int, int]) -> tuple[list[M.Mesh], str]:
        body = self.tint.get(b.body, (150, 150, 156))
        battery = self.tint.get(b.battery, (110, 110, 116))
        parts = [M.cylinder(0, 0, 0, 8.0, 5.0, axis=2, sides=16), M.box(0, 9.5, 0, 4.0, 5.0, 5.0), M.box(0, -9.5, 0, 3.0, 4.0, 4.0), M.cylinder(0, 0, 3.4, 4.0, 2.0, axis=2, sides=12)]
        for part, rgb in zip(parts, (body, battery, battery, accent)):
            part.texture = f"c_{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            part.normal_map = "flat_n"
        return parts, "proxy"

    def mesh_for(self, b: Build, accent: tuple[int, int, int]) -> str:
        """The path of this build's NIF under Meshes\\ (shared by every rarity of the same look)."""
        fam = b.family
        frags = [D.ACCESSORIES[fam.accessory][1], D.BODIES[b.body][1], D.BATTERIES[b.battery][1]]
        cap_frag = D.CAPACITORS[b.capacitor][1]
        if cap_frag:
            frags.append(cap_frag)
        look = "|".join(frags) + f"|{b.body}"
        parts = self._cut(frags)
        method = "real"
        if parts is None:
            look = f"proxy|{b.body}|{b.battery}|{accent}"
            parts, method = self._proxy(b, accent)
        key = hashlib.sha1(look.encode()).hexdigest()[:10]
        if key in self.written:
            self.stats["shared"] += 1
            return self.written[key]
        shapes = []
        if method == "real":
            atlas = self._atlas(b.body)
            merged = M.merged(parts)
            lo, hi = merged.bounds()
            size = max(hi[i] - lo[i] for i in range(3)) or 1.0
            centre = tuple((lo[i] + hi[i]) / 2 for i in range(3))
            merged = M.transformed(merged, None, SIZE / size, tuple(-c * SIZE / size for c in centre))
            tex = atlas or self._plain(self.tint.get(b.body, (150, 150, 156)))
            shapes = [(merged, tex, self._flat())]
        else:
            groups: dict[str, list[M.Mesh]] = {}
            for p in parts:
                groups.setdefault(p.texture or "", []).append(p)
            for tex_key, items in groups.items():
                rgb = (int(tex_key[2:4], 16), int(tex_key[4:6], 16), int(tex_key[6:8], 16))
                shapes.append((M.merged(items), self._plain(rgb), self._flat()))
        allp = M.merged([s[0] for s in shapes])
        lo, hi = allp.bounds()
        half = tuple(max(0.02, (hi[i] - lo[i]) / 2 / HAVOK_SCALE) for i in range(3))
        data = nif.gun(shapes, half, 1.0, "SkylandsShield")  # type: ignore[arg-type]
        rel = f"{MESH_DIR}\\{method}_{key}.nif"
        path = self.out / "Meshes" / Path(*rel.split("\\"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.written[key] = rel
        self.stats[method if method in self.stats else "proxy"] += 1
        return rel

    def flush_textures(self) -> int:
        d = self.out / "Textures" / "Skylands" / "Shields"
        d.mkdir(parents=True, exist_ok=True)
        for name, data in self.textures.items():
            (d / f"{name}.dds").write_bytes(data)
        return len(self.textures)


# ---- the records --------------------------------------------------------------------------------------------------------------------------------------

def find_effects(m, pattern: str):
    """The first vanilla armor enchantment whose editor id matches, with its first magic effect: (ENCH record, MGEF record), or None."""
    rx = re.compile(pattern, re.I)
    for edid, rec in sorted(((r.edid, r) for r in m.by_type["ENCH"].values()), key=lambda t: t[0]):
        if rx.search(edid):
            efid = rec.first("EFID")
            mg = m.by_type["MGEF"].get(struct.unpack_from("<I", efid)[0]) if efid else None
            if mg is not None:
                return rec, mg
    return None


# rarity level -> the player level from which loot lists offer it (the plugin's carriers use the same gates, shielditems.h kLevelFor)
LEVEL_GATE = {1: 1, 2: 3, 3: 8, 4: 15, 5: 30}
VENDOR_CHEST = re.compile(r"vendor", re.I)
VENDOR_KIND = re.compile(r"blacksmith|smith|armou?r|general", re.I)
VENDOR_LIMIT = 40


def gated_list(view: esp.Plugin, edid: str, entries: list[tuple[int, int, int]], chance_none: int = 0) -> esp.Rec:
    """A leveled list whose entries (form id, count, the lowest player level that is offered it) are chosen among by the player's level."""
    from . import generate

    if len(entries) > generate.LIST_LIMIT:
        raise ValueError(f"{edid}: {len(entries)} entries")
    r = view.new("LVLI", edid)
    r.add("OBND", b"\0" * 12).add("LVLD", bytes([chance_none])).add("LVLF", bytes([0x3])).add("LLCT", bytes([len(entries)]))
    for fid, count, level in entries:
        r.add("LVLO", generate.lvlo(fid, count, level))
    return r


def loot(view: esp.Plugin, m, ids_by_level: dict[int, list[int]], sheet: dict, beam_list, chest_list, report: dict, say) -> dict:
    """Where shields turn up besides the people who wear them (the user's choices): boss chests (a share of the chest ammo list), merchants' stock (the vendor chests of smiths,
    armorers and general stores), and the rarity beams (the shields join the form list the quest scans for guns lying loose; Skylands.esp is not touched, these are overrides)."""
    from . import generate

    tiers = {level: generate.leveled_list(view, f"SkylandsShieldTier_{level}", [(fid, 1) for fid in ids]).form_id for level, ids in sorted(ids_by_level.items())}
    copies = {level: S.RARITIES[RARITY_OF_LEVEL[level]].loot_copies for level in tiers}  # the guns' weights: 122 : 50 : 20 : 6 : 1
    anyone = [(tiers[lv], 1, LEVEL_GATE[lv]) for lv in sorted(tiers) for _ in range(copies[lv])]
    good = [(tiers[lv], 1, LEVEL_GATE[lv]) for lv in sorted(tiers) if lv >= 3 for _ in range(copies[lv])]
    drop_any = gated_list(view, "SkylandsShieldsAny", anyone)
    drop_good = gated_list(view, "SkylandsShieldsGood", good)
    stock = gated_list(view, "SkylandsShieldStock", anyone, chance_none=max(0, min(100, 100 - int(sheet["vendor_chance"]))))
    out = {"tiers": len(tiers), "chest_entries": 0, "vendors": []}
    if chest_list is not None:  # the boss chests already hold this list (for the ammo): some of its entries become shields
        share = max(0.0, min(0.9, float(sheet["chest_chance"]) / 100.0))
        have = len(chest_list.all("LVLO")) if hasattr(chest_list, "all") else sum(1 for s, _ in chest_list.subs if s == "LVLO")
        k = max(1, round(have * share / (1.0 - share))) if share > 0 else 0
        for _ in range(k):
            chest_list.add("LVLO", generate.lvlo(drop_good.form_id, 1))
        chest_list.set("LLCT", bytes([have + k]))
        out["chest_entries"] = k
    vendors = []
    containers = sorted(m.by_type.get("CONT", {}).values(), key=lambda r: r.edid)

    def stock_into(rec) -> None:
        lst = generate.copy(rec)
        n = struct.unpack("<I", lst.get("COCT") or struct.pack("<I", 0))[0]
        at = [i for i, (sig, _) in enumerate(lst.subs) if sig in ("COCT", "CNTO", "COED")]
        if at:
            lst.subs.insert(max(at) + 1, ("CNTO", struct.pack("<II", stock.form_id, 1)))
            lst.set("COCT", struct.pack("<I", n + 1))
        else:  # an empty container: the count and the entry go before its data
            where = next((i for i, (sig, _) in enumerate(lst.subs) if sig in ("DATA", "SNAM", "QNAM")), len(lst.subs))
            lst.subs[where:where] = [("COCT", struct.pack("<I", 1)), ("CNTO", struct.pack("<II", stock.form_id, 1))]
        view.override(lst)
        vendors.append(rec.edid)

    for rec in containers:  # smiths, armorers and general stores first
        if len(vendors) < VENDOR_LIMIT and VENDOR_CHEST.search(rec.edid) and VENDOR_KIND.search(rec.edid):
            stock_into(rec)
    if not vendors:  # none by that name: every vendor chest
        for rec in containers:
            if len(vendors) < VENDOR_LIMIT and VENDOR_CHEST.search(rec.edid):
                stock_into(rec)
    if not vendors:  # still none: the log lists what the containers are called, so the pattern can be corrected
        near = [r.edid for r in containers if re.search(r"merchant|store|shop|trader|smith|armou?r|general|vendor", r.edid, re.I)]
        say(f"shield loot: none of the {len(containers)} containers read from Skyrim.esm looks like a merchant's chest by name; those with a shop-like word in it: {near[:80]}")
    out["vendors"] = vendors
    if beam_list is not None:  # the quest finds loose items of the bases in this list and puts a beam of the item's rarity keyword on them
        every = esp.Rec("FLST", beam_list.form_id, list(beam_list.subs))
        for ids in ids_by_level.values():
            for fid in ids:
                every.add("LNAM", esp.u32(fid))
        view.override(every)
        out["beams"] = sum(len(v) for v in ids_by_level.values())
    report["shield_loot"] = out
    say(f"shield loot: {len(tiers)} rarity lists; boss chests get {out['chest_entries']} shield entries among their ammo ones; {len(vendors)} merchant chests stock them ({', '.join(vendors[:6])}{' ...' if len(vendors) > 6 else ''}); "
        f"{out.get('beams', 0)} shields join the beam form list")
    return out


def build(view: esp.Plugin, m, out_data: Path, rarity_keywords: dict[int, int], source, report: dict, say, *, shields_sheet: dict, bl2_parts: dict | None, slot: int,
          stats_effect, tints: dict[str, tuple[int, int, int]], rarity_colors: dict[int, tuple[int, int, int]], seed: int = 4, beam_list=None, chest_list=None) -> dict:
    """Write the shield records into the models plugin `view` and the meshes and textures under out_data. Returns a summary for the report."""
    t = Tables(bl2_parts)
    builds = roll(t, shields_sheet, seed)
    resist_pct = float(shields_sheet["resist_percent"])
    models = Models(out_data, source, say, tints)
    marker = view.new("KYWD", "SkylandsShield").form_id
    numbers: dict[str, int] = {}
    arma = view.new("ARMA", "SkylandsShieldArmature")
    arma.add("BOD2", struct.pack("<II", 1 << (slot - 30), 2)).add("RNAM", esp.u32(DEFAULT_RACE))
    arma.add("DNAM", struct.pack("<BBBBBBBBf", 1, 1, 0, 0, 0, 0, 0, 0, 0.0))
    stats_donor = find_effects(m, r"^EnchArmor.*FortifyHealth|^EnchArmor.*Health") or find_effects(m, r"^EnchArmor")
    resist_donors = {el: find_effects(m, rf"^EnchArmor.*Resist{word}") for el, word in (("fire", "Fire"), ("shock", "Shock"), ("corrosive", "Poison"), ("explosive", "Magic"))}
    if stats_donor is None:
        say("shields: no vanilla armor enchantment was found to copy; the shields get no stats text")
    missing = sorted(el for el, d in resist_donors.items() if d is None)
    if missing:
        say(f"shields: no vanilla resistance enchantment for {missing}; those capacitors give no resistance")
    made = {"items": 0, "with_resist": 0}
    by_family: dict[str, int] = {}
    ids_by_level: dict[int, list[int]] = {}
    vendor_kw = m.find("KYWD", "VendorItemClothing")  # merchants buy items with a vendor keyword: the player can sell the shields too
    for b in builds:
        rarity = S.RARITIES[RARITY_OF_LEVEL[b.level]]
        text = stats_text(b, rarity.word, resist_pct)
        kw_name = keyword_text(b)
        if kw_name not in numbers:
            numbers[kw_name] = view.new("KYWD", kw_name).form_id
        ench_id = 0
        if stats_donor is not None:
            ench_rec, mg = stats_donor
            e = esp.Rec("ENCH", view.new_id(f"ENCH:Skylands_Shield_{b.edid}"), [("EDID", esp.zstr(f"Skylands_Shield_{b.edid}"))])
            for sig, d in ench_rec.subrecords:  # the donor's head (bounds, enchantment data: constant effect on self), without its name, effects and conditions
                if sig in ("EDID", "FULL", "EFID", "EFIT", "CTDA", "CIS1", "CIS2"):
                    continue
                if sig == "ENIT":
                    e.add("FULL", esp.zstr(b.name))
                e.add(sig, d)
            mgef = stats_effect(view, f"Shield_{b.edid}", text, mg, "Shield stats")
            e.add("EFID", esp.u32(mgef)).add("EFIT", struct.pack("<fII", 0.0, 0, 0))
            donor = resist_donors.get(b.resist or "")
            if donor is not None:
                resist_efid = donor[0].first("EFID")
                e.add("EFID", resist_efid).add("EFIT", struct.pack("<fII", resist_pct, 0, 0))
                made["with_resist"] += 1
            view.override(e)
            ench_id = e.form_id
        accent = rarity_colors.get(b.level, (200, 200, 200))
        mesh = models.mesh_for(b, accent)
        a = view.new("ARMO", b.edid)
        a.add("OBND", struct.pack("<6h", -10, -10, -4, 10, 10, 4)).add("FULL", esp.zstr(b.name))
        if ench_id:
            a.add("EITM", esp.u32(ench_id))
        a.add("MOD2", esp.zstr(mesh)).add("BOD2", struct.pack("<II", 1 << (slot - 30), 2)).add("RNAM", esp.u32(DEFAULT_RACE))
        kws = [marker, numbers[kw_name], rarity_keywords[b.level]] + ([vendor_kw.form_id] if vendor_kw is not None else [])
        a.add("KSIZ", esp.u32(len(kws))).add("KWDA", b"".join(esp.u32(k) for k in kws))
        a.add("DESC", esp.zstr(text)).add("MODL", esp.u32(arma.form_id))
        value = max(10, int(60 * rarity.value_mult * (1.0 + 2.0 * b.ratio)))
        a.add("DATA", struct.pack("<If", value, 1.0)).add("DNAM", struct.pack("<i", 0))
        made["items"] += 1
        ids_by_level.setdefault(b.level, []).append(a.form_id)
        by_family[b.family.id] = by_family.get(b.family.id, 0) + 1
    models.flush_textures()
    # the glow around an enemy with a shield (plugin: shieldaura.h): three strengths of a soft blue haze, and the burst when the shield breaks
    fx_dir = Path(out_data) / "Meshes" / "Skylands"
    fx_dir.mkdir(parents=True, exist_ok=True)
    beam_tex = "textures\\skylands\\beam.dds"
    for name, rgb, bright in (("Fx_ShieldAura_0", (70, 150, 255), 2.2), ("Fx_ShieldAura_1", (70, 150, 255), 1.4), ("Fx_ShieldAura_2", (110, 170, 255), 0.8), ("Fx_ShieldBurst", (210, 235, 255), 3.2)):
        length, width = (90.0, 70.0) if name == "Fx_ShieldBurst" else (72.0, 38.0)
        (fx_dir / f"{name}.nif").write_bytes(nif.glow([(rgb, length, width, True, bright), (rgb, length, width, False, bright)], beam_tex, "SkylandsShieldGlow"))
    loot(view, m, ids_by_level, shields_sheet, beam_list, chest_list, report, say)
    summary = {"items": made["items"], "with_resist": made["with_resist"], "slot": slot, "families": by_family, "meshes": dict(models.stats), "textures": len(models.textures),
               "tables_replaced": t.replaced, "tables_read": t.read, "tables_wanted": t.wanted, "keywords": len(numbers)}
    report["shields"] = summary
    say(f"shields: {made['items']} items in {len(by_family)} families, biped slot {slot}, {made['with_resist']} with a resistance; meshes {models.stats}; "
        f"{t.read} of {t.wanted} part tables read from your files ({t.replaced} differ from the survey's)")
    return summary
