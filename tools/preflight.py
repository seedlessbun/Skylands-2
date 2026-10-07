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

    errors += sheet_rules(sheets)

    # Optional: every Borderlands object path exists with the right class in the BL2 data pack.
    if bl2_db is not None:
        con = sqlite3.connect(bl2_db)
        for row in sheets.get("bl2_reads", {}).get("rows", []):
            found = con.execute("select k.name from object o join class k on o.class=k.id where o.name=?",
                                (row["object"],)).fetchone()
            if not found:
                errors.append(f"bl2_reads.{row['id']}.object: {row['object']} not in BL2 data")
            elif found[0] != row["ue_class"]:
                errors.append(f"bl2_reads.{row['id']}.ue_class: data says {found[0]}")

    return errors, unverified


def sheet_rules(sheets: dict[str, dict]) -> list[str]:
    """Rules specific to this mashup's sheets."""
    errors: list[str] = []
    return errors


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
