"""Pull what Skylands uses out of the player's Borderlands 2 install (sheet: bl2_reads, gun_types).

Every value comes from the player's own files. Anything that cannot be read is listed under
"errors" so the setup can say what is missing instead of guessing.
"""

from __future__ import annotations

import re
import time
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
    base = props.get("BaseValue")  # DesignerAttributeDefinition: the number lives on the attribute itself
    if isinstance(base, dict) and "BaseValueConstant" in base:
        return round(float(base["BaseValueConstant"]) * float(base.get("BaseValueScaleConstant", 1.0))
                     * float(init.get("BaseValueScaleConstant", 1.0)), 3)
    resolver = _first(props.get("ValueResolverChain"))
    if resolver and "ManufacturerAttributeValueResolver" in str(resolver):
        return None  # "this gun is made by X" markers: no number to read, nothing to report
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


SLOTS = ("BodyPartData", "BarrelPartData", "GripPartData", "StockPartData", "SightPartData",
         "Accessory1PartData", "Accessory2PartData", "MaterialPartData", "ElementalPartData")
MODIFIER_TYPES = (("scale", "scale"), ("preadd", "preadd"), ("postadd", "postadd"))


def _leaf(path: str) -> str:
    return re.split(r"[.:]", path)[-1]


def _modifier_type(value) -> str:
    text = str(value).lower()
    for needle, name in MODIFIER_TYPES:
        if needle in text:
            return name
    return ""


def parse_effect(ix: Index, item, errors: list[str], what: str, samples: list) -> dict | None:
    """One attribute effect of a part: which attribute, how it combines, by how much."""
    if not isinstance(item, dict):
        return None
    attr = next((v for k, v in item.items() if "AttributeToModify" in k and isinstance(v, str)), None)
    if attr is None:
        attr = next((v for v in item.values() if isinstance(v, str) and "Attributes." in v), None)
    if attr is None:
        if len(samples) < 12:
            samples.append({"where": what, "unparsed": {k: (v if not isinstance(v, dict) else "{...}") for k, v in item.items()}})
        return None
    kind = next((_modifier_type(v) for k, v in item.items() if "ModifierType" in k), "")
    init = next((v for k, v in item.items() if "ModifierValue" in k and isinstance(v, dict)), None)
    value = _attr_value(ix, init, errors, what) if init else None
    if value is None:
        return None
    if len(samples) < 12:
        samples.append({"where": what, "attr": _leaf(attr), "type": kind, "value": value})
    return {"attr": _leaf(attr), "type": kind, "value": value}


def _effects_of(ix: Index, props: dict, keys: tuple[str, ...], errors: list[str], what: str, samples: list) -> list[dict]:
    out = []
    for key in keys:
        value = props.get(key)
        items = _first_list(value) if isinstance(value, dict) and value.get("type") == "Array" else ([value] if isinstance(value, dict) else [])
        for item in items:
            e = parse_effect(ix, item, errors, what, samples)
            if e:
                out.append(e)
    return out


def part_info(ix: Index, path: str, cache: dict, errors: list[str], samples: list) -> dict:
    """What one gun part is called and which stats it changes (memoised)."""
    if path in cache:
        return cache[path]
    p = ix.props(path) or {}
    info = {"prefix": _part_name(ix, _first(p.get("PrefixList"))), "title": _part_name(ix, _first(p.get("TitleList"))), "effects": []}
    info["effects"] += _effects_of(ix, p, ("WeaponAttributeEffects", "ExternalAttributeEffects"), errors, path, samples)
    provider = p.get("BehaviorProviderDefinition")
    if isinstance(provider, str):
        for child in ix.children(provider):
            cp = ix.props(child) or {}
            info["effects"] += _effects_of(ix, cp, ("AttributeEffect", "AttributeEffects"), errors, child, samples)
    cache[path] = info
    return info


def slot_parts(ix: Index, chain: list[dict]) -> dict[str, list[str]]:
    """Every enabled slot of a balance and its candidate parts (the first balance in the chain that defines a slot wins)."""
    out: dict[str, list[str]] = {}
    for slot in SLOTS:
        parts = _parts(ix, chain, slot)
        if parts:
            out[slot.removesuffix("PartData")] = parts
    return out


def type_base(ix: Index, errors: list[str]) -> dict:
    """The player's own base numbers for each gun type, for the record (and to tune the sheets from)."""
    out = {}
    for gt in S.GUN_TYPES.values():
        found = ix.children(f"{gt.package}.A_Weapons", "WeaponTypeDefinition")
        types = {}
        for path in found[:6]:
            p = ix.props(path) or {}
            row = {k: (float(p[k]) if isinstance(p.get(k), (int, float)) else _attr_value(ix, p.get(k), errors, f"{path} {k}"))
                   for k in ("FireRate", "ReloadTime", "ClipSize", "Spread")}
            row["pellets"] = p.get("ProjectilesPerShot")
            types[_leaf(path)] = row
        out[gt.id] = types
    return out


def guns(ix: Index, errors: list[str], say=None) -> dict:
    out: dict = {"guns": [], "manufacturers": {}, "parts": {}, "effect_samples": []}
    try:
        _guns_into(ix, errors, say, out)
    except TimeoutError as e:  # keep what was read so far
        errors.append(f"weapons stopped early after {len(out['guns'])} guns: {e}")
    return out


def _guns_into(ix: Index, errors: list[str], say, out: dict) -> None:
    for gt in S.GUN_TYPES.values():
        groups = [(f"{gt.package}.A_Weapons", False), (f"{gt.package}.A_Weapons_Legendary", True)]
        prefixes = {e: _part_name(ix, f"{gt.package}.Name.Prefix.Prefix_Elemental_{w}") or w for e, w in ELEMENT_WORDS.items()}
        for group, legendary in groups:
            found = ix.children(group, "WeaponBalanceDefinition")
            if say:
                say(f"  {gt.id}: {len(found)} balances in {group}")
            for n_done, bal in enumerate(found):
                if say and n_done and n_done % 25 == 0:
                    say(f"    {gt.id}: {n_done}/{len(found)}")
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
                    title_n = prefix_n = ""
                    for slot in ("BarrelPartData", "BodyPartData", "Accessory1PartData", "GripPartData"):
                        for part in _parts(ix, chain[:1], slot):
                            pp = ix.props(part) or {}
                            title_n = title_n or _part_name(ix, _first(pp.get("TitleList")))
                            prefix_n = prefix_n or _part_name(ix, _first(pp.get("PrefixList")))
                    unique = " ".join(x for x in (prefix_n, title_n) if x) or re.sub(r"(?<!^)(?=[A-Z])", " ", leaf.split("_")[-1])
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
                slots = slot_parts(ix, chain)
                for plist in slots.values():
                    for part in plist:
                        part_info(ix, part, out["parts"], errors, out["effect_samples"])
                out["guns"].append({
                    "slots": slots,
                    "balance": bal, "type": gt.id, "manufacturer": mfr, "rarity": rarity, "title": title,
                    "unique_name": unique, "elements": elements,
                    "element_prefixes": {e: prefixes[e] for e in elements if prefixes.get(e)},
                    "damage_scale": round(float(dmg.get("BaseValueScaleConstant", 1.0)), 4) if isinstance(dmg, dict) else 1.0,
                    "pellets": int(wtp.get("ProjectilesPerShot", 1) or 1),
                    "clip": int(wtp.get("ClipSize", 0) or 0),
                })
        if not any(g["type"] == gt.id for g in out["guns"]):
            errors.append(f"no {gt.id} balances found in {gt.package}")
        if say:
            say(f"  {gt.id}: {sum(1 for g in out['guns'] if g['type'] == gt.id)} gun balances")


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


def extract(bl2_root: Path, cache_dir: Path | None = None, progress=None, budget_minutes: float | None = None) -> dict:
    log: list[str] = []

    def say(m: str) -> None:
        log.append(f"[{time.time() - t0:6.0f} s] {m}")
        if progress:
            progress(m)

    errors: list[str] = []
    t0 = time.time()
    ix = Index(bl2_root, cache_dir / "bl2_index.json" if cache_dir else None, say)
    if budget_minutes:
        ix.deadline = time.process_time() + budget_minutes * 60
    data: dict = {"packages": len(ix.files), "index_errors": len(ix.errors)}
    for key, fn in (("rarities", rarities), ("classes", classes), ("weapons", guns), ("enemies", enemies), ("type_base", type_base)):
        t = time.time()
        say(f"Reading {key} ...")
        try:
            data[key] = fn(ix, errors, say) if fn is guns else fn(ix, errors)
        except Exception as e:  # noqa: BLE001 - keep going, report it
            errors.append(f"{key}: {type(e).__name__}: {e}")
        say(f"  {key} done in {time.time() - t:.0f} s")
    data["errors"] = errors
    data["seconds"] = round(time.time() - t0, 1)
    data["log"] = log
    data["slow_lookups"] = ix.slow
    return data


def summarize_parts(weapons: dict) -> dict:
    """A small digest of the gun parts read: how many, what they change, and what the sheets do not cover yet."""
    from .. import assemble

    parts = weapons.get("parts", {})
    attrs: dict[str, int] = {}
    for info in parts.values():
        for eff in info.get("effects", []):
            attrs[eff["attr"]] = attrs.get(eff["attr"], 0) + 1
    mapped = {a: n for a, n in attrs.items() if assemble.rule_for(a)}
    unmapped = {a: n for a, n in sorted(attrs.items(), key=lambda kv: -kv[1]) if not assemble.rule_for(a)}
    pools: dict[str, list[int]] = {}
    for g in weapons.get("guns", []):
        for slot, plist in (g.get("slots") or {}).items():
            pools.setdefault(slot, []).append(len(plist))
    return {
        "parts": len(parts), "parts_with_effects": sum(1 for i in parts.values() if i.get("effects")),
        "balances": len(weapons.get("guns", [])), "balances_with_parts": sum(1 for g in weapons.get("guns", []) if g.get("slots")),
        "attributes_mapped": mapped, "attributes_not_mapped": dict(list(unmapped.items())[:40]),
        "pool_sizes": {slot: {"balances": len(v), "max": max(v), "avg": round(sum(v) / len(v), 1)} for slot, v in pools.items()},
        "effect_samples": weapons.get("effect_samples", []),
    }
