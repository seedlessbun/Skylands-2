"""Assemble guns the way Borderlands 2 does, from parts.

A Borderlands balance (e.g. Pistol_Jakobs_3_Rare) lists, per slot (body, barrel, grip, stock, sight,
accessories, material, element), the parts a gun of that make and rarity may be built from. Every
gun is one pick from each pool; each part carries stat changes (damage, fire interval, reload speed,
clip size, spread, ...) that Borderlands combines into the gun's numbers. This does the same pick
and combination, then hands Skylands the resulting multipliers. Nothing is shown of the parts
themselves yet; they only change the stats and the name.

The parts' effects are read from the player's own game files (bl2.extract). Where a part carries no
readable effect it still gets a small, fixed "personality" (derived from its name) so that the same
part always nudges guns the same way, and a manufacturer's character (sheet: manufacturers) is
applied on top.
"""

from __future__ import annotations

import random
import re

from . import sheet_data as S

STATS = ("damage", "fire_rate", "reload", "clip", "accuracy", "crit", "element")
ELEMENTS = ("Fire", "Shock", "Corrosive", "Slag")
NAME_ORDER = ("Elemental", "Accessory1", "Accessory2", "Material", "Barrel", "Body", "Grip", "Stock", "Sight")
# what each kind of part tends to change when it has no readable effect
FLAVOUR = {"Barrel": ("fire_rate", "accuracy"), "Body": ("damage", "clip"), "Grip": ("reload", "accuracy"),
           "Stock": ("accuracy", "reload"), "Sight": ("crit", "accuracy"), "Accessory1": STATS, "Accessory2": STATS,
           "Material": ("element", "damage"), "Elemental": ("element",)}
MULT_MIN, MULT_MAX = 0.4, 2.5


def rule_for(attr: str):
    for row in S.PART_STATS.values():
        if re.search(row.attr, attr, re.I):
            return row
    return None


def effect_multiplier(eff: dict) -> float:
    """A Borderlands attribute effect as a plain multiplier. Scale values are multipliers (1.1 = +10%);
    small values (and additive ones) are read as fractions (0.1 = +10%)."""
    v = float(eff["value"])
    m = v if 0.25 <= v <= 4.0 and eff.get("type") in ("scale", "") else 1.0 + v if abs(v) < 2.0 else 1.0
    return min(MULT_MAX, max(MULT_MIN, m))


def personality(path: str, slot: str) -> dict[str, float]:
    rnd = random.Random(f"part:{path}")
    stats = FLAVOUR.get(slot, STATS)
    chosen = rnd.sample(stats, k=min(2, len(stats)))
    return {s: 1.0 + rnd.uniform(-0.07, 0.10) for s in chosen}


def part_mods(path: str, slot: str, info: dict) -> dict[str, float]:
    mods = dict.fromkeys(STATS, 1.0)
    for eff in info.get("effects", []):
        rule = rule_for(eff["attr"])
        if rule is None:
            continue
        m = effect_multiplier(eff)
        if rule.invert == "yes":
            m = 1.0 / m
        mods[rule.stat] *= m ** float(rule.power)
    for stat, m in personality(path, slot).items():
        mods[stat] *= m
    return mods


def manufacturer_mods(name: str) -> dict[str, float]:
    row = S.MANUFACTURERS.get(name)
    if row is None:
        return dict.fromkeys(STATS, 1.0)
    mods = dict.fromkeys(STATS, 1.0)
    mods.update(damage=row.damage, fire_rate=row.fire_rate, reload=row.reload, crit=row.crit, element=row.element)
    return mods


def clean(path: str) -> str:
    leaf = re.split(r"[.:]", path)[-1]
    return leaf.replace("_", " ").strip()


def pick(g: dict, parts: dict, variant: int, taken: set) -> dict:
    """One variant of a balance: a part from each slot, different from the variants already made."""
    for attempt in range(8):
        rnd = random.Random(f"gun:{g['balance']}:{variant}:{attempt}")
        chosen = {slot: rnd.choice(options) for slot, options in sorted(g["slots"].items()) if options}
        key = tuple(sorted(chosen.items()))
        if key not in taken or attempt == 7:
            break
    taken.add(key)
    mods = manufacturer_mods(g["manufacturer"])
    for slot, path in chosen.items():
        for stat, m in part_mods(path, slot, parts.get(path, {})).items():
            mods[stat] *= m
    element = next((e for e in ELEMENTS if chosen.get("Elemental", "").endswith("_" + e)), None)
    return {"parts": chosen, "mods": mods, "element": element}


def name_of(g: dict, chosen: dict, parts: dict, element: str | None, manufacturers: dict, word: str) -> str:
    if g["unique_name"]:
        base = g["unique_name"]
    else:
        prefix = next((parts[chosen[s]]["prefix"] for s in NAME_ORDER if s in chosen and parts.get(chosen[s], {}).get("prefix")), "")
        if not prefix and element:
            prefix = g["element_prefixes"].get(element, "")
        title = next((parts[chosen[s]]["title"] for s in NAME_ORDER if s in chosen and parts.get(chosen[s], {}).get("title")), "") or g["title"]
        lead = prefix or manufacturers.get(g["manufacturer"], g["manufacturer"])
        base = f"{lead} {title}".strip()
    return f"{base} ({word})"


def parts_line(chosen: dict) -> str:
    shown = [f"{slot} {clean(path).split(' ', 1)[-1]}" for slot, path in sorted(chosen.items()) if slot in ("Barrel", "Body", "Grip", "Stock", "Sight")]
    return ", ".join(shown)
