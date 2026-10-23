"""Per-gun stat rolls (sheets: gun_types, rarities).

Every gun rolls fire rate and reload inside its gun type's Borderlands 2-like range, the range
widening toward the top as rarity rises, plus elemental and critical strength. A gun can also
roll a rare "boost": one of fire rate, element or crit damage multiplied by a large factor, like
Borderlands' unique guns with absurd fire rate or elemental damage. Rolls are seeded by the gun's
editor id, so rebuilding gives the same guns.
"""

from __future__ import annotations

import random

SPEED_MIN, SPEED_MAX = 0.4, 6.0  # player weapon speed multiplier (1.0 = normal); fast guns look frantic on purpose
RATE_REF, RELOAD_REF = 2.0, 2.5  # a gun firing 2/s with a 2.5 s reload runs at normal animation speed


def roll(edid: str, gt, rr, has_element: bool, mods: dict | None = None) -> dict:
    """mods: multipliers from the gun's parts and manufacturer (assemble.py); none means a plain gun."""
    mods = mods or {}
    rnd = random.Random(f"skylands:{edid}")
    rate = (gt.rate_min + rnd.uniform(rr.stat_lo, rr.stat_hi) * (gt.rate_max - gt.rate_min)) * mods.get("fire_rate", 1.0)
    reload = (gt.reload_max - rnd.uniform(rr.stat_lo, rr.stat_hi) * (gt.reload_max - gt.reload_min)) * mods.get("reload", 1.0)
    rate = min(gt.rate_max * 1.15, max(gt.rate_min * 0.8, rate))
    reload = min(gt.reload_max * 1.2, max(gt.reload_min * 0.8, reload))
    element = rr.element_mult * rnd.uniform(1 - rr.spread, 1 + rr.spread) * mods.get("element", 1.0)
    crit = (gt.crit_damage * rr.crit_mult * rnd.uniform(1 - rr.spread, 1 + rr.spread)
            * mods.get("crit", 1.0) * mods.get("accuracy", 1.0) ** 0.5)
    boosted, boost = None, 1.0
    if rnd.random() < rr.roll_chance:
        boosted = rnd.choice(["fire_rate", "crit_damage", *(["element"] if has_element else [])])
        boost = rnd.uniform(rr.boost_min, rr.boost_max)
        if boosted == "fire_rate":
            rate *= boost
        elif boosted == "crit_damage":
            crit *= boost
        else:
            element *= boost
    # Animation speed grows with fire rate (steeply) and falls with reload time (gently).
    speed = (rate / RATE_REF) ** 0.6 * (RELOAD_REF / reload) ** 0.4
    speed = round(min(SPEED_MAX, max(SPEED_MIN, speed)), 3)
    # accuracy (the staff guns' shot spread): a good roll and an accurate part set tighten it. Drawn last so no earlier number moves.
    quality = rnd.uniform(rr.stat_lo, rr.stat_hi)
    spread_mult = min(1.6, max(0.5, (1.3 - 0.6 * quality) / max(0.5, mods.get("accuracy", 1.0))))
    return {
        "fire_rate": round(rate, 2), "reload": round(reload, 2), "speed": speed,
        "crit_damage": max(1, round(crit)), "element_mult": round(element, 3),
        "damage_mult": round(mods.get("damage", 1.0), 3), "clip_mult": round(mods.get("clip", 1.0), 3),
        "boosted": boosted, "boost": round(boost, 2) if boosted else None, "spread_mult": round(spread_mult, 3),
    }


def describe(s: dict, element_word: str | None, manufacturer: str = "", clip: int = 0, parts: str = "") -> str:
    """The text shown on the gun's enchantment."""
    bits = [f"Fire rate {s['fire_rate']:.1f}/s", f"Reload {s['reload']:.1f}s"]
    if clip:
        bits.append(f"Mag {max(1, round(clip * s.get('clip_mult', 1.0)))}")
    bits.append(f"Crit damage +{s['crit_damage']}")
    if element_word:
        bits.append(f"{element_word} damage x{s['element_mult']:.1f}")
    text = (f"{manufacturer}. " if manufacturer else "") + ", ".join(bits) + "."
    if parts:
        text += f" Parts: {parts}."
    if s["boosted"]:
        text += f" Boosted {s['boosted'].replace('_', ' ')} x{s['boost']:.1f}!"
    return text
