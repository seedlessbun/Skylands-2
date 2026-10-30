"""Reads the deep shield survey (work/bl2-shield-deep-report.txt, written by Check-BL2-Shields-Deep.bat) into objects, so the shield data can be turned into the sheet.

    python tools/shield_report.py <report.txt> [--summary]

The report is an indented dump: "--- <path> [<Class>] level N via M" opens an object, its properties follow (Name: value, or Name: then a nested block; arrays are
"items:" with "[0]" entries).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HEAD = re.compile(r"^--- (?P<path>\S+) \[(?P<cls>[A-Za-z0-9_]+)\] level (?P<level>\d+)(?: via (?P<via>.*))?$")
ITEM = re.compile(r"^\[(\d+)\](?: (.*))?$")


class Obj:
    def __init__(self, path: str, cls: str, level: int, via: str | None):
        self.path, self.cls, self.level, self.via = path, cls, level, via
        self.props: dict = {}

    @property
    def name(self) -> str:
        return self.path.rsplit(".", 1)[-1]

    def __repr__(self):
        return f"<{self.cls} {self.path}>"


def _parse_block(lines: list[tuple[int, str]], i: int, indent: int):
    """Parse the lines at this indent into a dict (or, when they are [n] entries, a list). Returns (value, next index)."""
    if i < len(lines) and ITEM.match(lines[i][1]) and lines[i][0] == indent:
        out = []
        while i < len(lines) and lines[i][0] == indent and ITEM.match(lines[i][1]):
            m = ITEM.match(lines[i][1])
            i += 1
            if m.group(2) is not None and m.group(2) != "":
                out.append(m.group(2))
            elif i < len(lines) and lines[i][0] > indent:
                val, i = _parse_block(lines, i, lines[i][0])
                out.append(val)
            else:
                out.append(None)
        return out, i
    out = {}
    while i < len(lines) and lines[i][0] == indent:
        text = lines[i][1]
        i += 1
        key, sep, rest = text.partition(":")
        rest = rest.strip()
        if not sep:
            continue
        if rest == "" and i < len(lines) and lines[i][0] > indent:
            val, i = _parse_block(lines, i, lines[i][0])
            out[key] = val
        else:
            out[key] = rest
    return out, i


def parse(text: str) -> list[Obj]:
    objs: list[Obj] = []
    cur: Obj | None = None
    body: list[tuple[int, str]] = []

    def close():
        nonlocal body
        if cur is not None and body:
            base = min(ind for ind, _ in body)
            val, _ = _parse_block(body, 0, base)
            cur.props = val if isinstance(val, dict) else {}
        body = []

    for raw in text.splitlines():
        m = HEAD.match(raw)
        if m:
            close()
            cur = Obj(m["path"], m["cls"], int(m["level"]), m["via"])
            objs.append(cur)
            continue
        if raw.startswith("========"):
            close()
            cur = None
            continue
        if cur is None or not raw.strip() or raw.startswith(("families:", "defaults:", "read ", "asset ")):
            continue
        ind = len(raw) - len(raw.lstrip(" "))
        body.append((ind, raw.strip()))
    close()
    return objs


def by_path(objs: list[Obj]) -> dict[str, Obj]:
    out: dict[str, Obj] = {}
    for o in objs:
        out.setdefault(o.path, o)
    return out


def main(argv):
    path = Path(argv[1])
    objs = parse(path.read_text(encoding="utf-8", errors="replace"))
    idx = by_path(objs)
    print(len(objs), "objects,", len(idx), "distinct")
    return objs, idx




# ---- turning the deep report into setup/skylands_setup/shielddata.py ------------------------------------------------------------------------------------

def _arr(x):
    if isinstance(x, dict) and "items" in x:
        return x["items"] or []
    return x if isinstance(x, list) else []


def _num(v):
    if isinstance(v, dict):
        v = v.get("BaseValueConstant")
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _grades(o: Obj) -> dict[str, int]:
    out = {}
    for u in _arr(o.props.get("AttributeSlotUpgrades")):
        if isinstance(u, dict):
            try:
                out[u["SlotName"]] = int(u["GradeIncrease"])
            except (KeyError, ValueError):
                pass
    return out


def build_tables(idx: dict[str, Obj]) -> dict:
    """The tables shielddata.py holds, from the objects of the report."""
    sd = idx["GD_Shields.A_Item.Shield_Standard"]
    steps = {}
    for e in _arr(sd.props.get("AttributeSlotEffects")):
        steps[e["SlotName"]] = _num(e.get("PerGradeUpgrade"))
    bodies = {}
    for p, o in sorted(idx.items()):
        if o.cls == "ShieldPartDefinition" and p.startswith("GD_Shields.Body.Body"):
            mfr = p.rsplit("_", 1)[-1]
            g = _grades(o)
            bodies[mfr] = {"path": p, "fragment": o.props.get("GestaltModeSkeletalMeshName"), "capacity": g.get("Capacity", 0), "rate": g.get("RechargeRate", 0), "delay": g.get("RechargeDelay", 0)}
    materials = {}
    for p, o in sorted(idx.items()):
        if o.cls == "ShieldPartDefinition" and p.startswith("GD_Shields.Material.Material"):
            leaf = p.rsplit(".", 1)[-1]
            level = int(leaf[8])
            group = leaf.split("_", 2)[2] if leaf.count("_") >= 2 else "NoSpecial"
            g = _grades(o)
            materials[leaf] = {"path": p, "level": level, "group": group, "capacity": g.get("Capacity", 0), "rate": g.get("RechargeRate", 0), "delay": g.get("RechargeDelay", 0),
                               "special1": g.get("Special01", 0), "special2": g.get("Special02", 0)}
    parts = {"battery": {}, "capacitor": {}, "accessory": {}}
    for p, o in sorted(idx.items()):
        if o.cls != "ShieldPartDefinition":
            continue
        kind = {"GD_Shields.Battery.": "battery", "GD_Shields.Capacitor.": "capacitor", "GD_Shields.Accessory.": "accessory"}
        for prefix, key in kind.items():
            if p.startswith(prefix):
                leaf = p.rsplit(".", 1)[-1]
                parts[key][leaf] = {"path": p, "fragment": o.props.get("GestaltModeSkeletalMeshName"), "grades": _grades(o)}
    prefixes = {p.rsplit(".", 1)[-1]: o.props.get("PartName") for p, o in idx.items() if o.cls == "ItemNamePartDefinition" and ".Prefixes." in p}
    titles = {p.rsplit(".", 1)[-1]: o.props.get("PartName") for p, o in idx.items() if o.cls == "ItemNamePartDefinition" and ".Titles." in p}
    return {"steps": steps, "bodies": bodies, "materials": materials, "parts": parts, "prefixes": prefixes, "titles": titles}


if __name__ == "__main__":
    if "--emit" in sys.argv:
        pass
    elif "--tables" in sys.argv:
        import json

        print(json.dumps(build_tables(by_path(parse(Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")))), indent=1))
    else:
        main(sys.argv)


def emit_module(idx: dict[str, Obj]) -> str:
    """The text of setup/skylands_setup/shielddata.py."""
    t = build_tables(idx)
    s = t["steps"]
    out = ['"""Borderlands 2 shield parts, as read from the deep shield survey of a real install (tools/shield_report.py writes this file).',
           "",
           "Every number here is a BL2 value (source: GD_Shields.* objects named in `path`); the installer reads the same objects from the player's own files",
           "(bl2/extract.shield_parts) and the values it reads replace these. A shield's slot grade is the sum of its body, battery and capacitor parts and its material;",
           "capacity and recharge rate scale by (1 + grade x step), the delay by (1 + grade x step) with a negative step (more grade, shorter delay).",
           '"""',
           "",
           f"STEPS = {{'capacity': {s['Capacity']:.2f}, 'rate': {s['RechargeRate']:.2f}, 'delay': {s['RechargeDelay']:.2f}}}  # GD_Shields.A_Item.Shield_Standard AttributeSlotEffects PerGradeUpgrade",
           ""]

    def grades(g):
        return (g.get("Capacity", 0), g.get("RechargeRate", 0), g.get("RechargeDelay", 0), g.get("Special01", 0), g.get("Special02", 0))

    out.append("# manufacturer -> (path, mesh fragment, capacity, rate, delay) grades of its body part")
    out.append("BODIES = {")
    order = ["Tediore", "Bandit", "Vladof", "Dahl", "Anshin", "Maliwan", "Torgue", "Hyperion", "Pangolin"]
    for m in order:
        b = t["bodies"][m]
        out.append(f"    {m!r}: ({b['path']!r}, {b['fragment']!r}, {b['capacity']}, {b['rate']}, {b['delay']}),")
    out.append("}")
    out.append("")
    out.append("# battery / capacitor key -> (path, mesh fragment, capacity, rate, delay, special 1, special 2); the capacitors that make a resistance carry it as the last item")
    out.append("BATTERIES = {")
    for leaf, v in t["parts"]["battery"].items():
        key = leaf.split("_", 1)[1]
        out.append(f"    {key!r}: ({v['path']!r}, {v['fragment']!r}, " + ", ".join(str(x) for x in grades(v["grades"])) + "),")
    out.append("}")
    out.append("CAPACITORS = {")
    resist = {"CorrosiveResist": "corrosive", "FireResist": "fire", "ShockResist": "shock", "ExplosiveDamageResistance": "explosive"}
    for leaf, v in t["parts"]["capacitor"].items():
        key = leaf.split("_", 1)[1]
        res = next((resist[k] for k in v["grades"] if k in resist), None)
        frag = v["fragment"] if not str(v["fragment"]).startswith("Shield_Pickup") else None
        out.append(f"    {key!r}: ({v['path']!r}, {frag!r}, " + ", ".join(str(x) for x in grades(v["grades"])) + f", {res!r}),")
    out.append("}")
    out.append("")
    out.append("# material group -> rarity level (1 common .. 5 legendary) -> (path, capacity, rate, delay, special 1, special 2) grades")
    groups: dict[str, dict] = {}
    for leaf, v in t["materials"].items():
        groups.setdefault(v["group"], {})[v["level"]] = v
    out.append("MATERIALS = {")
    for g in sorted(groups):
        out.append(f"    {g!r}: {{")
        for level in sorted(groups[g]):
            v = groups[g][level]
            out.append(f"        {level}: ({v['path']!r}, {v['capacity']}, {v['rate']}, {v['delay']}, {v['special1']}, {v['special2']}),")
        out.append("    },")
    out.append("}")
    out.append("")
    out.append("# accessory part -> mesh fragment (the fragment names in the survey are crossed: the accessory part names a Shield_Body_* mesh, the body part a Shield_Accessory_* one)")
    out.append("ACCESSORIES = {")
    for leaf, v in t["parts"]["accessory"].items():
        out.append(f"    {leaf!r}: ({v['path']!r}, {v['fragment']!r}),")
    out.append("}")
    out.append("")
    out.append("PREFIXES = {  # item name part -> text (Prefix_<stat>_<manufacturer><level 01-05>, Prefix_Balanced_<manufacturer>, Prefix_Special_..., resist prefixes)")
    for k in sorted(t["prefixes"]):
        out.append(f"    {k!r}: {t['prefixes'][k]!r},")
    out.append("}")
    out.append("TITLES = {")
    for k in sorted(t["titles"]):
        out.append(f"    {k!r}: {t['titles'][k]!r},")
    out.append("}")
    # which capacitors each family may roll
    out.append("")
    out.append("# part list -> the keys of the capacitors it may roll (equal weights)")
    out.append("CAPACITOR_LISTS = {")
    for p, o in sorted(idx.items()):
        if o.cls == "ItemPartListDefinition" and p.startswith("GD_Shields.Capacitor.PartsList"):
            keys = [w["Part"].rsplit(".", 1)[-1].split("_", 1)[1] for w in _arr(o.props.get("WeightedParts"))]
            out.append(f"    {p.rsplit('.', 1)[-1].replace('PartsList_Capacitor_', '')!r}: {keys!r},")
    out.append("}")
    return "\n".join(out) + "\n"


if __name__ == "__main__" and "--emit" in sys.argv:
    print(emit_module(by_path(parse(Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")))), end="")
