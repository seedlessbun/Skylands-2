"""Relics (0.43.0): armor items worn in a biped slot of their own, whose keyword carries the numbers the plugin (native/skse/src/relic.h) applies while the player wears one.

The numbers are Borderlands 2's (docs/relic-roadmap.md, the deep relic survey): an artifact effect is  level x per-level + grade x per-grade  (a fraction) where the level is the
item's level (Skylands: the character's) and the grade comes with the rarity. Only the general kinds are made here (the user's choice): health, shield, resistance, ammo and one
damage relic; the weapon-type, manufacturer and element relics (Aggression A-F, Allegiance A-H, Elemental) come later.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from . import meshes as M
from .skyrim import esp, nif
from .shields import DEFAULT_RACE, HAVOK_SCALE, RARITY_OF_LEVEL, SLOT_ORDER, find_effects, slot_use

MESH = "Skylands\\Relics\\relic.nif"
TEX_DIR = "textures\\skylands\\relics"
GRADE_OF_LEVEL = {1: 0, 2: 1, 3: 3, 4: 6, 5: 9}  # the grade a rarity brings (BL2's maximum is 12); design values
RARITY_WORDS = {1: "Common", 2: "Uncommon", 3: "Rare", 4: "Epic", 5: "Legendary"}
DAMAGE_NOTE = "Borderlands 2's Aggression relic raises the damage of ONE weapon type; this one raises the damage of all guns (design, until the type relics are made)"


@dataclass(frozen=True)
class Effect:
    code: str  # the letter relic.h knows
    text: str
    per_level: float  # a fraction per character level
    per_grade: float  # a fraction per grade
    bl2: str  # where the number comes from


@dataclass(frozen=True)
class Kind:
    id: str
    title: str
    effects: tuple[Effect, ...]
    bl2: str


KINDS = [
    Kind("vitality", "Vitality", (Effect("h", "Health", 0.004, 0.02, "HealthMaxValue_Player"),), "GD_Artifacts.A_Item.Artifact_Vitality"),
    Kind("protection", "Protection", (Effect("s", "Shield capacity", 0.003, 0.01, "ShieldMaxValue"), Effect("r", "Shield recharge rate", 0.003, 0.01, "ShieldOnIdleRegenerationRate")),
         "GD_Artifacts.A_Item.Artifact_Protection"),
    Kind("resistance", "Resistance", (Effect("f", "Fire resistance", 0.0034, 0.0099, "IncendiaryImpactDamageModifier"), Effect("k", "Shock resistance", 0.0040, 0.0120, "ShockImpactDamageModifier"),
                                      Effect("c", "Corrosive resistance", 0.0030, 0.0109, "CorrosiveImpactDamageModifier"), Effect("x", "Explosive resistance", 0.0035, 0.0099, "ExplosiveImpactDamageModifier")),
         "GD_Artifacts.A_Item.Artifact_Resistance"),
    Kind("stockpile", "Stockpile", (Effect("m", "Magazine size", 0.005, 0.03, "Ammo_*_MaxValue (Skylands: the magazine)"),), "GD_Artifacts.A_Item.Artifact_Stockpile"),
    Kind("aggression", "Aggression", (Effect("d", "Damage", 0.003, 0.01, "WeaponDamage"),), "GD_Artifacts.A_Item.Artifact_AggressionA (all guns: " + DAMAGE_NOTE + ")"),
]


def pct(x: float) -> str:
    return f"{x * 100:.1f}".rstrip("0").rstrip(".")


def keyword_text(kind: Kind, level: int, grade: int) -> str:
    parts = [f"SkylandsRelic_l{level}"]
    for e in kind.effects:
        parts.append(f"{e.code}{round(e.per_level * 100000)}x{round(e.per_grade * grade * 100000)}")
    return "_".join(parts)


def stats_text(kind: Kind, level: int, grade: int) -> str:
    lines = [f"{RARITY_WORDS[level]} {kind.title.lower()} relic."]
    for e in kind.effects:
        lines.append(f"{e.text} +{pct(e.per_level)}% per character level, +{pct(e.per_grade * grade)}% on top")
    return "\n".join(lines)


def choose_slot(data_dir: Path, say=None, wanted: int | None = None, taken: int = 0) -> tuple[int, str]:
    """The biped slot the relics are worn in: the first one nothing in the load order uses, other than the shields' (`taken`)."""
    if wanted and 30 <= wanted <= 61 and wanted != taken:
        return wanted, f"slot {wanted} (kept from your settings)"
    use = slot_use(data_dir, say)
    for slot in SLOT_ORDER:
        if slot != taken and use.get(slot, 0) == 0:
            return slot, f"slot {slot} (no armor or armature in your load order uses it)"
    slot = min((s for s in SLOT_ORDER if s != taken), key=lambda s: use.get(s, 0))
    return slot, f"slot {slot} (every candidate is used by something; this one by {use.get(slot, 0)} records)"


def write_assets(out_data: Path, colors: dict[int, tuple[int, int, int]]) -> dict[int, str]:
    """A small ring with a gem, in a colour per rarity: one mesh each. Returns the mesh path (under Meshes\\) by rarity level. (A stand-in until Borderlands 2's artifact mesh is cut from its gestalt.)"""
    mesh_dir = Path(out_data) / "Meshes" / "Skylands" / "Relics"
    tex_dir = Path(out_data) / "Textures" / "Skylands" / "Relics"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    tex_dir.mkdir(parents=True, exist_ok=True)
    (tex_dir / "flat_n.dds").write_bytes(nif.dds_flat_normal())
    (tex_dir / "band.dds").write_bytes(nif.dds_solid((150, 150, 158)))
    paths: dict[int, str] = {}
    for level, rgb in colors.items():
        name = f"gem_{level}"
        (tex_dir / f"{name}.dds").write_bytes(nif.dds_solid(rgb))
        band = M.cylinder(0, 0, 0, 3.4, 1.0, axis=2, sides=18)
        gem = M.box(0, 3.6, 0.3, 1.0, 1.0, 1.0)
        shapes = []
        for part, tex in ((band, "band"), (gem, name)):
            shapes.append((part, f"{TEX_DIR}\\{tex}.dds", f"{TEX_DIR}\\flat_n.dds"))
        allp = M.merged([s[0] for s in shapes])
        lo, hi = allp.bounds()
        half = tuple(max(0.02, (hi[i] - lo[i]) / 2 / HAVOK_SCALE) for i in range(3))
        rel = f"Skylands\\Relics\\relic_{level}.nif"
        (mesh_dir / f"relic_{level}.nif").write_bytes(nif.gun(shapes, half, 0.2, "SkylandsRelic"))  # type: ignore[arg-type]
        paths[level] = rel
    return paths


def make(view: esp.Plugin, m, out_data: Path, rarity_keywords: dict[int, int], report: dict, say, *, slot: int, stats_effect, rarity_colors: dict[int, tuple[int, int, int]]) -> dict[int, list[int]]:
    """Write the relic records into the models plugin `view` and the assets under out_data. Returns the item form ids by rarity level (for the loot lists)."""
    if not slot:
        return {}
    marker = view.new("KYWD", "SkylandsRelic").form_id
    arma = view.new("ARMA", "SkylandsRelicArmature")
    arma.add("BOD2", struct.pack("<II", 1 << (slot - 30), 2)).add("RNAM", esp.u32(DEFAULT_RACE))
    arma.add("DNAM", struct.pack("<BBBBBBBBf", 1, 1, 0, 0, 0, 0, 0, 0, 0.0))
    stats_donor = find_effects(m, r"^EnchArmor.*FortifyHealth|^EnchArmor.*Health") or find_effects(m, r"^EnchArmor")
    if stats_donor is None:
        say("relics: no vanilla armor enchantment was found to copy; the relics get no stats text")
    meshes = write_assets(out_data, {lv: rarity_colors.get(lv, (200, 200, 200)) for lv in RARITY_OF_LEVEL})
    vendor_kw = m.find("KYWD", "VendorItemClothing")
    numbers: dict[str, int] = {}
    ids_by_level: dict[int, list[int]] = {}
    count = 0
    for kind in KINDS:
        for level in sorted(RARITY_OF_LEVEL):
            for variant in (0, 1):  # a second build of each, one grade better
                grade = GRADE_OF_LEVEL[level] + variant
                name = f"{'Prime ' if variant else ''}{kind.title} Relic"
                edid = f"SkylandsRelic_{kind.id}_{level}_{variant}"
                text = stats_text(kind, level, grade)
                kw = keyword_text(kind, level, grade)
                if kw not in numbers:
                    numbers[kw] = view.new("KYWD", kw).form_id
                ench_id = 0
                if stats_donor is not None:
                    ench_rec, mg = stats_donor
                    e = esp.Rec("ENCH", view.new_id(f"ENCH:{edid}"), [("EDID", esp.zstr(edid + "_ench"))])
                    for sig, d in ench_rec.subrecords:
                        if sig in ("EDID", "FULL", "EFID", "EFIT", "CTDA", "CIS1", "CIS2"):
                            continue
                        if sig == "ENIT":
                            e.add("FULL", esp.zstr(name))
                        e.add(sig, d)
                    mgef = stats_effect(view, f"Relic_{kind.id}_{level}_{variant}", text, mg, "Relic stats")
                    e.add("EFID", esp.u32(mgef)).add("EFIT", struct.pack("<fII", 0.0, 0, 0))
                    view.override(e)
                    ench_id = e.form_id
                a = view.new("ARMO", edid)
                a.add("OBND", struct.pack("<6h", -6, -6, -2, 6, 6, 2)).add("FULL", esp.zstr(name))
                if ench_id:
                    a.add("EITM", esp.u32(ench_id))
                a.add("MOD2", esp.zstr(meshes[level])).add("BOD2", struct.pack("<II", 1 << (slot - 30), 2)).add("RNAM", esp.u32(DEFAULT_RACE))
                kws = [marker, numbers[kw], rarity_keywords[level]] + ([vendor_kw.form_id] if vendor_kw is not None else [])
                a.add("KSIZ", esp.u32(len(kws))).add("KWDA", b"".join(esp.u32(k) for k in kws))
                a.add("DESC", esp.zstr(text)).add("MODL", esp.u32(arma.form_id))
                value = 40 + 120 * grade
                a.add("DATA", struct.pack("<If", value, 0.5)).add("DNAM", struct.pack("<i", 0))
                ids_by_level.setdefault(level, []).append(a.form_id)
                count += 1
    report["relics"] = {"items": count, "slot": slot, "kinds": [k.id for k in KINDS]}
    say(f"relics: {count} items in {len(KINDS)} kinds, worn in biped slot {slot}")
    return ids_by_level
