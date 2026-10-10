"""Per-gun stat rolls (sheets: gun_types, rarities).

Every gun rolls fire rate and reload inside its gun type's Borderlands 2-like range, the range
widening toward the top as rarity rises, plus elemental and critical strength. A gun can also
roll a rare "boost": one of fire rate, element or crit damage multiplied by a large factor, like
Borderlands' unique guns with absurd fire rate or elemental damage. Rolls are seeded by the gun's
editor id, so rebuilding gives the same guns.
"""

from __future__ import annotations

import math
import random

SPEED_MIN, SPEED_MAX = 0.5, 3.0  # Skyrim weapon speed the animations stay sane within


def roll(edid: str, gt, rr, has_element: bool) -> dict:
    rnd = random.Random(f"skylands:{edid}")
    rate = gt.rate_min + rnd.uniform(rr.stat_lo, rr.stat_hi) * (gt.rate_max - gt.rate_min)
    reload = gt.reload_max - rnd.uniform(rr.stat_lo, rr.stat_hi) * (gt.reload_max - gt.reload_min)
    element = rr.element_mult * rnd.uniform(1 - rr.spread, 1 + rr.spread)
    crit = gt.crit_damage * rr.crit_mult * rnd.uniform(1 - rr.spread, 1 + rr.spread)
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
    mid_rate, mid_reload = (gt.rate_min + gt.rate_max) / 2, (gt.reload_min + gt.reload_max) / 2
    speed = gt.speed * math.sqrt(rate / mid_rate) * math.sqrt(mid_reload / reload)
    return {
        "fire_rate": round(rate, 2), "reload": round(reload, 2),
        "speed": round(min(SPEED_MAX, max(SPEED_MIN, speed)), 3),
        "crit_damage": max(1, round(crit)), "element_mult": round(element, 3),
        "boosted": boosted, "boost": round(boost, 2) if boosted else None,
    }


def describe(s: dict, element_word: str | None) -> str:
    """The text shown on the gun's enchantment."""
    bits = [f"Fire rate {s['fire_rate']:.1f}/s", f"Reload {s['reload']:.1f}s", f"Crit damage +{s['crit_damage']}"]
    if element_word:
        bits.append(f"{element_word} damage x{s['element_mult']:.1f}")
    text = ", ".join(bits) + "."
    if s["boosted"]:
        text += f" Boosted {s['boosted'].replace('_', ' ')} x{s['boost']:.1f}!"
    return text
