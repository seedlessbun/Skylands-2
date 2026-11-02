"""Read the Badass survey (work\\bl2-badass-report.txt, `Check-BL2-Badass.bat`) and derive the numbers of sheets/badass_tiers.json and sheets/enemy_drops.json.

Usage: python tools/badass_report.py REPORT

What Borderlands 2 does (read from the user's report of 0.45.3, see docs/badass-roadmap.md section 1):
  - a Badass is its own AI class with start values `Attribute_HealthMultiplier` and `Attribute_EnemyNonWeaponDamageMultiplier` (melee, bites, slams: not guns)
    and a `Champion=True` balance; every champion's damage is also scaled by `Enemy_Damage_PerPlayerPerPlaythroughByChampion` (single player: 0.74 against 0.65)
  - the loot lists BadassEnemyGunsAndGear / SuperBadassEnemyGunsAndGear / UltimateBadassEnemyGunsAndGear hold pools with probability 1.0: guaranteed drops
The pairs below (a regular class and its tier variant in the same family) are the reading of the class names; the NUMBERS come from the report.
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

# (family, regular AI class, tier AI class, tier); the pairing is mine, the values are the report's
PAIRS = [
    ("Varkid", "CharClass_BugMorph", "CharClass_Bugmorph_Badass", "badass"),
    ("Varkid", "CharClass_BugMorph", "CharClass_Bugmorph_SuperBadass", "super"),
    ("Varkid", "CharClass_BugMorph", "CharClass_BugMoprhUltimate", "ultimate"),
    ("Loader", "CharClass_LoaderBUL", "CharClass_LoaderBadass", "badass"),
    ("Loader", "CharClass_LoaderBUL", "CharClass_LoaderSuperBadass", "super"),
    ("Constructor", "CharClass_Constructor", "CharClass_ConstructorBadass", "badass"),
    ("Creeper", "CharClass_Creeper", "CharClass_CreeperBadass", "badass"),
    ("Goliath", "CharClass_Goliath", "CharClass_GoliathTurret", "badass"),
    ("Buzzard", "CharClass_Gyrocopter", "CharClass_GyrocopterBadass", "badass"),
    ("Nomad", "CharClass_Nomad", "CharClass_NomadBadass", "badass"),
    ("Bullymong", "CharClass_PrimalBeast", "CharClass_PrimalBeastBadass", "badass"),
    ("Surveyor", "CharClass_Probes", "CharClass_ProbeBadass", "badass"),
    ("Psycho", "CharClass_Psycho", "CharClass_PsychoBadass", "badass"),
    ("Rakk", "CharClass_RakkDrone", "CharClass_RakkBadass", "badass"),
]
LISTS = {"badass": "BadassEnemyGunsAndGear", "super": "SuperBadassEnemyGunsAndGear", "ultimate": "UltimateBadassEnemyGunsAndGear"}
RARITY_OF_POOL = {"Pool_GunsAndGear_02_Uncommon": 2, "Pool_GunsAndGear_04_Rare": 3, "Pool_GunsAndGear_05_VeryRare": 4}  # BL2 pool -> Skylands rarity (1 common ... 4 epic)


def blocks(lines: list[str]) -> dict[str, list[str]]:
    """'--- <path> [class] ...' blocks by the last part of the path (the first block of each name wins)."""
    out: dict[str, list[str]] = {}
    cur: list[str] | None = None
    for ln in lines:
        m = re.match(r"--- (\S+) \[", ln)
        if m:
            leaf = m.group(1).rsplit(".", 1)[-1]
            cur = None if leaf in out else out.setdefault(leaf, [])
            continue
        if ln.startswith("========"):
            cur = None
        if cur is not None:
            cur.append(ln.strip())
    return out


def start_values(body: list[str]) -> dict[str, float]:
    """Attribute start values of an AI class: {attribute leaf: BaseValueConstant}."""
    out: dict[str, float] = {}
    attr = None
    for s in body:
        m = re.match(r"Attribute: \S+\.(\w+)$", s)
        if m:
            attr = m.group(1)
        elif attr and s.startswith("BaseValueConstant:"):
            out.setdefault(attr, float(s.split()[-1]))
            attr = None
    return out


def conditional(body: list[str]) -> list[tuple[float, dict[str, float]]]:
    """(value, {condition attribute: constant}) of a conditional initialisation."""
    rows: list[tuple[float, dict[str, float]]] = []
    val, conds, attr = None, {}, None
    for s in body:
        if s.startswith("BaseValueIfTrue:"):
            if val is not None:
                rows.append((val, conds))
            val, conds = None, {}
        elif s.startswith("BaseValueConstant:") and val is None:
            val = float(s.split()[-1])
        elif s.startswith("AttributeOperand1:"):
            attr = s.split()[-1].rsplit(".", 1)[-1]
        elif s.startswith("ConstantOperand2:") and attr:
            conds[attr] = float(s.split()[-1])
    if val is not None:
        rows.append((val, conds))
    return rows


def guaranteed(body: list[str]) -> list[str]:
    """Pools a loot list drops with probability 1.0 and no per-player scaling (the guaranteed drops)."""
    out: list[str] = []
    pool, const, scaled = None, None, False
    for s in body + ["ItemPool: END.END"]:
        if s.startswith("ItemPool:"):
            if pool and const == 1.0 and not scaled:
                out.append(pool)
            pool, const, scaled = s.split()[-1].rsplit(".", 1)[-1], None, False
        elif s.startswith("BaseValueConstant:") and const is None:
            const = float(s.split()[-1])
        elif (s.startswith("BaseValueAttribute:") or s.startswith("InitializationDefinition:")) and not s.endswith("None"):
            scaled = True
    return out


def derive(text: str) -> dict:
    b = blocks(text.split("\n"))
    rows = []
    for fam, reg, tier_cls, tier in PAIRS:
        if reg not in b or tier_cls not in b:
            continue
        r, t = start_values(b[reg]), start_values(b[tier_cls])
        h0, h1 = r.get("Attribute_HealthMultiplier"), t.get("Attribute_HealthMultiplier")
        d0, d1 = r.get("Attribute_EnemyNonWeaponDamageMultiplier"), t.get("Attribute_EnemyNonWeaponDamageMultiplier")
        s0, s1 = r.get("Attribute_EnemyShieldMaxValueMultiplier"), t.get("Attribute_EnemyShieldMaxValueMultiplier")
        rows.append({"family": fam, "tier": tier, "health": h1 / h0 if h0 and h1 else None, "damage": d1 / d0 if d0 and d1 else None,
                     "shield": s1 / s0 if s0 and s1 else None, "raw": (reg, h0, d0, tier_cls, h1, d1)})
    champ = {}
    if "Enemy_Damage_PerPlayerPerPlaythroughByChampion" in b:
        for v, c in conditional(b["Enemy_Damage_PerPlayerPerPlaythroughByChampion"]):
            if c.get("NumberOfPlayers") == 1.0 and c.get("PlayThroughCount", 1.0) == 1.0:
                champ[int(c.get("Targetable_Is_Champion", -1))] = v
    odds = None
    if "DropODDS_GunsAndGear:ConditionalAttributeValueResolver_0" in b:
        for v, c in conditional(b["DropODDS_GunsAndGear:ConditionalAttributeValueResolver_0"]):
            if c.get("NumberOfPlayers") == 1.0:
                odds = v
    loot = {tier: guaranteed(b[name]) for tier, name in LISTS.items() if name in b}

    def med(tier: str, key: str) -> float | None:
        vals = [r[key] for r in rows if r["tier"] == tier and r[key]]
        return statistics.median(vals) if vals else None

    out = {"rows": rows, "champion": champ, "gear_odds": odds, "loot": loot}
    badass_h, badass_d = med("badass", "health"), med("badass", "damage")
    # a Super / Ultimate against the Badass of the same family
    step = {}
    for tier in ("super", "ultimate"):
        hs, ds = [], []
        for r in rows:
            if r["tier"] != tier:
                continue
            base = next((x for x in rows if x["family"] == r["family"] and x["tier"] == "badass"), None)
            if base and base["health"] and r["health"]:
                hs.append(r["health"] / base["health"])
            if base and base["damage"] and r["damage"]:
                ds.append(r["damage"] / base["damage"])
        step[tier] = (statistics.mean(hs) if hs else None, statistics.mean(ds) if ds else None, len(hs))
    champ_factor = champ[1] / champ[0] if 0 in champ and 1 in champ and champ[0] else 1.0
    out["derived"] = {"badass_health": badass_h, "badass_melee": badass_d * champ_factor if badass_d else None, "gun": champ_factor, "step": step,
                      "shield": med("badass", "shield")}
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    d = derive(Path(argv[0]).read_text(encoding="utf-8", errors="replace"))
    print("regular class -> tier class: health x, non-weapon damage x, shield x")
    for r in d["rows"]:
        f = lambda v: f"{v:.2f}" if v else "-"  # noqa: E731
        print(f"  {r['family']:12} {r['tier']:8} health {f(r['health']):>6}  damage {f(r['damage']):>6}  shield {f(r['shield']):>5}   {r['raw']}")
    print(f"champion damage, single player, first playthrough: {d['champion']}")
    print(f"a regular enemy's chance of a gun or gear drop (single player): {d['gear_odds']}")
    for tier, pools in d["loot"].items():
        gear = [p for p in pools if p in RARITY_OF_POOL]
        print(f"guaranteed drops of a {tier}: {len(gear)} gun/gear item(s) {gear}, the best of Skylands rarity {max((RARITY_OF_POOL[p] for p in gear), default='-')} "
              f"(and {[p for p in pools if p not in RARITY_OF_POOL]})")
    x = d["derived"]
    print(f"DERIVED: Badass health x{x['badass_health']:.2f} (median of the pairs); melee/creature damage x{x['badass_melee']:.2f} (median non-weapon x champion factor); "
          f"gun damage x{x['gun']:.3f} (champion factor); shield x{x['shield']}")
    for tier, (h, dm, n) in x["step"].items():
        print(f"  {tier}: health x{h} and damage x{dm} of the same family's Badass ({n} famil{'y' if n == 1 else 'ies'})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
