"""Pull what Skylands uses out of the player's Borderlands 2 install (sheet: bl2_reads, gun_types).

Every value comes from the player's own files. Anything that cannot be read is listed under
"errors" so the setup can say what is missing instead of guessing.
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import sheet_data as S
from .index import Index

RARITY_SUFFIX = {"": 1, "2_Uncommon": 2, "3_Rare": 3, "4_VeryRare": 4, "5_Alien": 6}
ELEMENT_WORDS = {"Fire": "Incendiary", "Corrosive": "Corrosive", "Shock": "Shock", "Slag": "Slag"}


def clean_text(s: str) -> str:
    s = re.sub(r"\[-?[a-zA-Z]+\]", "", s or "")
    s = re.sub(r"<StringAliasMap:Action\.ActionSkill>", "your shout key", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _first(v):
    if isinstance(v, dict) and v.get("type") == "Array":
        items = v.get("items") or []
        return items[0] if isinstance(items, list) and items else None
    return v


def _attr_value(ix: Index, init: dict | None, errors: list[str], what: str) -> float | None:
    """AttributeInitializationData: a constant, or an attribute whose first resolver is a constant."""
    if not isinstance(init, dict):
        return None
    attr = init.get("BaseValueAttribute")
    if not attr:
        return round(float(init.get("BaseValueConstant", 0.0)) * float(init.get("BaseValueScaleConstant", 1.0)), 3)
    props = ix.props(attr) or {}
    resolver = _first(props.get("ValueResolverChain"))
    if not resolver:
        errors.append(f"{what}: {attr} has no value resolver")
        return None
    rp = ix.props(resolver) or {}
    if "ConstantValue" not in rp:
        errors.append(f"{what}: {resolver} is not a constant")
        return None
    return round(float(rp["ConstantValue"]) * float(init.get("BaseValueScaleConstant", 1.0)), 3)


def rarities(ix: Index, errors: list[str]) -> list[dict]:
    g = ix.props(S.BL2_READS["b_globals"].object) or {}
    rows = _first_list(g.get("RarityLevelColors"))
    out = []
    for r in rows:
        color = r.get("Color")
        if not isinstance(color, list) or len(color) != 4:
            continue
        b, gr, red, a = color
        out.append({"min": r.get("MinLevel"), "max": r.get("MaxLevel"), "rating": r.get("RarityRating"), "rgb": [red, gr, b], "alpha": a})
    if not out:
        errors.append("rarity colours not found in GD_Globals")
    return out


def _first_list(v) -> list:
    if isinstance(v, dict) and v.get("type") == "Array" and isinstance(v.get("items"), list):
        return [x for x in v["items"] if isinstance(x, dict)]
    return []


def classes(ix: Index, errors: list[str]) -> list[dict]:
    out = []
    for row in S.CLASSES.values():
        c = {"id": row.id}
        cls = ix.props(S.BL2_READS[row.class_read].object)
        skill = ix.props(S.BL2_READS[row.skill_read].object)
        if cls is None or skill is None:
            errors.append(f"class {row.id}: class or skill object not found")
            continue
        name_id = cls.get("CharacterNameId")
        names = ix.props(name_id) if name_id else None
        c["character"] = (names or {}).get("LocalizedCharacterName") or row.id
        c["skill_name"] = skill.get("SkillName", "")
        c["skill_desc"] = clean_text(skill.get("SkillDescription", ""))
        c["duration"] = round(float(skill.get("InitialDuration", 0.0)), 3)
        pool = cls.get("SkillCooldownPoolDefinition")
        pp = ix.props(pool) if pool else None
        c["cooldown"] = _attr_value(ix, (pp or {}).get("BaseMaxValue"), errors, f"class {row.id} cooldown") if pp else None
        if not c["skill_name"]:
            errors.append(f"class {row.id}: no skill name")
        out.append(c)
    return out


def _balance_chain(ix: Index, balance: str) -> list[dict]:
    chain, seen = [], set()
    b = balance
    while b and b not in seen and len(chain) < 8:
        seen.add(b)
        p = ix.props(b) or {}
        chain.append({"path": b, **p})
        b = p.get("BaseDefinition")
    return chain


def _parts(ix: Index, chain: list[dict], slot: str) -> list[str]:
    for link in chain:
        plist = link.get("WeaponPartListCollection") or link.get("RuntimePartListCollection")
        pl = ix.props(plist) if plist else None
        data = (pl or {}).get(slot)
        if isinstance(data, dict) and data.get("bEnabled"):
            parts = [w.get("Part") for w in _first_list(data.get("WeightedParts")) if w.get("Part")]
            if parts:
                return parts
    return []


def _weapon_type(ix: Index, chain: list[dict]) -> str | None:
    for link in chain:
        plist = link.get("WeaponPartListCollection")
        pl = ix.props(plist) if plist else None
        if pl and pl.get("AssociatedWeaponType"):
            return pl["AssociatedWeaponType"]
    return None


def _part_name(ix: Index, name_part: str | None) -> str:
    return ((ix.props(name_part) or {}).get("PartName") or "") if name_part else ""


def guns(ix: Index, errors: list[str]) -> dict:
    out: dict = {"guns": [], "manufacturers": {}}
    for gt in S.GUN_TYPES.values():
        groups = [(f"{gt.package}.A_Weapons", False), (f"{gt.package}.A_Weapons_Legendary", True)]
        prefixes = {e: _part_name(ix, f"{gt.package}.Name.Prefix.Prefix_Elemental_{w}") for e, w in ELEMENT_WORDS.items()}
        for group, legendary in groups:
            for bal in ix.children(group, "WeaponBalanceDefinition"):
                leaf = bal.rsplit(".", 1)[1]
                m = re.match(rf"{gt.balance_prefix}_([A-Za-z]+)(?:_(\d_[A-Za-z]+))?$", leaf)
                if not m:
                    continue
                mfr, suffix = m.group(1), m.group(2) or ""
                if legendary:
                    rarity = 5
                elif suffix in RARITY_SUFFIX:
                    rarity = RARITY_SUFFIX[suffix]
                else:
                    continue
                chain = _balance_chain(ix, bal)
                wt = _weapon_type(ix, chain)
                wtp = ix.props(wt) if wt else None
                if not wtp:
                    errors.append(f"{bal}: weapon type not found")
                    continue
                title = _part_name(ix, _first(wtp.get("TitleList")))
                unique = ""
                if legendary:
                    for slot in ("BarrelPartData", "BodyPartData", "Accessory1PartData", "GripPartData"):
                        for part in _parts(ix, chain[:1], slot):
                            pp = ix.props(part) or {}
                            for key in ("TitleList", "PrefixList"):
                                n = _part_name(ix, _first(pp.get(key)))
                                if n:
                                    unique = unique or n
                    unique = unique or re.sub(r"(?<!^)(?=[A-Z])", " ", leaf.split("_")[-1])
                elements = []
                for part in _parts(ix, chain, "ElementalPartData"):
                    e = part.rsplit("_", 1)[-1]
                    if e in ELEMENT_WORDS and e not in elements:
                        elements.append(e)
                if mfr not in out["manufacturers"]:
                    mp = ix.props(f"GD_Manufacturers.Manufacturers.{mfr}") or {}
                    grade = _first_list(mp.get("Grades"))
                    out["manufacturers"][mfr] = grade[0].get("DisplayName", mfr) if grade else mfr
                dmg = wtp.get("InstantHitDamage") or {}
                out["guns"].append({
                    "balance": bal, "type": gt.id, "manufacturer": mfr, "rarity": rarity, "title": title,
                    "unique_name": unique, "elements": elements,
                    "element_prefixes": {e: prefixes[e] for e in elements if prefixes.get(e)},
                    "damage_scale": round(float(dmg.get("BaseValueScaleConstant", 1.0)), 4) if isinstance(dmg, dict) else 1.0,
                    "pellets": int(wtp.get("ProjectilesPerShot", 1) or 1),
                    "clip": int(wtp.get("ClipSize", 0) or 0),
                })
        if not any(g["type"] == gt.id for g in out["guns"]):
            errors.append(f"no {gt.id} balances found in {gt.package}")
    return out


def enemies(ix: Index, errors: list[str]) -> dict:
    out = {}
    for row in S.BL2_READS.values():
        if not row.id.startswith("b_enemy_"):
            continue
        p = ix.props(row.object)
        plays = _first_list((p or {}).get("PlayThroughs"))
        name = plays[0].get("DisplayName") if plays else None
        if not name:
            errors.append(f"{row.id}: display name not found")
            continue
        out[row.id] = name
    return out


def extract(bl2_root: Path, cache_dir: Path | None = None) -> dict:
    errors: list[str] = []
    ix = Index(bl2_root, cache_dir / "bl2_index.json" if cache_dir else None)
    data: dict = {"packages": len(ix.files), "index_errors": len(ix.errors)}
    for key, fn in (("rarities", rarities), ("classes", classes), ("weapons", guns), ("enemies", enemies)):
        try:
            data[key] = fn(ix, errors)
        except Exception as e:  # noqa: BLE001 - keep going, report it
            errors.append(f"{key}: {type(e).__name__}: {e}")
    data["errors"] = errors
    return data
