"""Preflight: lay every sheet's rows and columns over each other before a build.

Lists
- every unfilled cell (missing, empty or null),
- every reference between sheets that does not resolve,
- sheet-specific rules (18 unique skills, known damage types, known hook functions),
- every cell still marked unverified ("no" in a verification column).

Errors stop the build. Unverified cells are reported but do not stop a build:
they are what still has to be checked in the running game before listing.

Usage: python tools/preflight.py [--bl2-db path/to/OpenBLCMM/data.db] [--quiet]
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEETS = ROOT / "sheets"

VERIFY_COLUMNS = {
    "in_game",
    "in_data",
    "parser_tested",
    "real_file_tested",
    "read_verified",
    "balanced_in_game",
}

# WillowDmgSource_* classes present in BL2 (OpenBLCMM BL2 data, 2023-04-20).
KNOWN_DAMAGE_TYPES = {
    "WillowDmgSource_Bullet", "WillowDmgSource_CustomCrate", "WillowDmgSource_Grenade",
    "WillowDmgSource_MachineGun", "WillowDmgSource_Melee", "WillowDmgSource_MeleeWithBlade",
    "WillowDmgSource_Pistol", "WillowDmgSource_Rocket", "WillowDmgSource_Shield",
    "WillowDmgSource_ShieldNova", "WillowDmgSource_ShieldSpike", "WillowDmgSource_Shotgun",
    "WillowDmgSource_Skill", "WillowDmgSource_Skill_IgnoreIOs", "WillowDmgSource_Sniper",
    "WillowDmgSource_StatusEffect", "WillowDmgSource_SubMachineGun",
    "WillowDmgSource_VehicleRanInto", "WillowDmgSource_VehicleRanOver",
}


def load_sheets() -> dict[str, dict]:
    sheets = {}
    for path in sorted(SHEETS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        sheets[data["sheet"]] = data
    return sheets


def is_unfilled(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def preflight(sheets: dict[str, dict], bl2_db: Path | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    unverified: list[str] = []
    ids = {name: {row.get("id") for row in s["rows"]} for name, s in sheets.items()}

    for name, sheet in sheets.items():
        columns = sheet["columns"]
        seen: set[str] = set()
        for i, row in enumerate(sheet["rows"]):
            rid = row.get("id", f"#{i}")
            if rid in seen:
                errors.append(f"{name}.{rid}: duplicate id")
            seen.add(rid)
            for col in columns:
                if col not in row or is_unfilled(row[col]):
                    errors.append(f"{name}.{rid}.{col}: unfilled")
                elif col in VERIFY_COLUMNS and row[col] != "yes":
                    unverified.append(f"{name}.{rid}.{col}")
            for col in row:
                if col not in columns:
                    errors.append(f"{name}.{rid}.{col}: column not declared on the sheet")
            for col, target in sheet.get("refs", {}).items():
                targets = target if isinstance(target, list) else [target]
                value = row.get(col)
                if is_unfilled(value):
                    continue
                for t in targets:
                    if t not in sheets:
                        errors.append(f"{name}.{col}: refers to missing sheet '{t}'")
                if not any(value in ids.get(t, set()) for t in targets):
                    errors.append(f"{name}.{rid}.{col}: '{value}' not found in {'/'.join(targets)}")

    # Damage types must be real BL2 classes.
    for name in ("xp_sources", "effects"):
        for row in sheets.get(name, {}).get("rows", []):
            dt = row.get("damage_types", "")
            if dt in ("-", "*") or is_unfilled(dt):
                continue
            for cls in dt.split(","):
                if cls.strip() not in KNOWN_DAMAGE_TYPES:
                    errors.append(f"{name}.{row['id']}.damage_types: unknown class '{cls}'")

    # Exactly Skyrim's 18 skills, each actor-value index once.
    skills = sheets.get("skills", {}).get("rows", [])
    if len(skills) != 18:
        errors.append(f"skills: {len(skills)} rows, Skyrim has 18")
    indices = [r.get("av_index") for r in skills]
    if sorted(indices) != list(range(6, 24)):
        errors.append(f"skills.av_index: expected 6..23 once each, got {sorted(indices)}")
    for r in skills:
        if not is_unfilled(r.get("per_level")) and r["per_level"] < 0:
            errors.append(f"skills.{r['id']}.per_level: negative")

    # Every skill's xp source and effect is used exactly once.
    for col, sheet in (("xp_source", "xp_sources"), ("effect", "effects")):
        used = [r.get(col) for r in skills]
        for rid in ids.get(sheet, set()):
            if used.count(rid) != 1:
                errors.append(f"{sheet}.{rid}: used by {used.count(rid)} skills (expected 1)")

    # Shout words unlock in order.
    words = sheets.get("shout", {}).get("rows", [])
    levels = [w.get("unlock_level") for w in words]
    if [w.get("words") for w in words] != [1, 2, 3]:
        errors.append("shout: rows must be words 1, 2, 3 in order")
    if levels != sorted(levels):
        errors.append("shout.unlock_level: must not decrease")

    # Optional: hook functions exist in the BL2 object data.
    if bl2_db is not None:
        con = sqlite3.connect(bl2_db)
        for row in sheets.get("hooks", {}).get("rows", []):
            found = con.execute("select 1 from object where name=?", (row["function"],)).fetchone()
            if not found:
                errors.append(f"hooks.{row['id']}.function: {row['function']} not in BL2 data")
            elif row.get("in_data") != "yes":
                errors.append(f"hooks.{row['id']}.in_data: function exists, mark it 'yes'")
        for row in sheets.get("sounds", {}).get("rows", []) + sheets.get("shout", {}).get("rows", []):
            obj = row.get("object") if row.get("source") == "bl2" else row.get("camera_anim")
            if obj and not con.execute("select 1 from object where name=?", (obj,)).fetchone():
                errors.append(f"{row['id']}: BL2 object {obj} not in BL2 data")

    return errors, unverified


def main() -> int:
    args = sys.argv[1:]
    db = None
    if "--bl2-db" in args:
        db = Path(args[args.index("--bl2-db") + 1])
    quiet = "--quiet" in args
    sheets = load_sheets()
    errors, unverified = preflight(sheets, db)
    rows = sum(len(s["rows"]) for s in sheets.values())
    cells = sum(len(s["rows"]) * len(s["columns"]) for s in sheets.values())
    print(f"preflight: {len(sheets)} sheets, {rows} rows, {cells} cells")
    for e in errors:
        print("  ERROR", e)
    print(f"  {len(errors)} errors; {len(unverified)} cells not yet verified")
    if not quiet:
        by_sheet: dict[str, int] = {}
        for u in unverified:
            by_sheet[u.split(".")[0]] = by_sheet.get(u.split(".")[0], 0) + 1
        for name, n in sorted(by_sheet.items()):
            print(f"    unverified in {name}: {n}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
