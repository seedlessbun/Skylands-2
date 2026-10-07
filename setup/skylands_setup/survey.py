"""Survey: read the player's Borderlands 2 and Skyrim SE installs and write a JSON report.

Used for the first test round: it shows whether each object on the bl2_reads sheet can be
found and decoded in the real files, where Borderlands keeps its text, and what Skyrim's
bandit records are called. It only reads; it writes nothing into either game.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

from . import sheet_data as S
from .bl2 import upk
from .skyrim.bsa import BSA
from .skyrim.esm import is_localized, read_plugin
from .skyrim.strings import parse_table

MAX_PACKAGES_PER_TARGET = 60


def _json_safe(v, depth=0):
    if depth > 8:
        return "..."
    if isinstance(v, dict):
        return {str(k): _json_safe(x, depth + 1) for k, x in list(v.items())[:200]}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x, depth + 1) for x in list(v)[:200]]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v if not isinstance(v, str) else v[:2000]
    return repr(v)[:200]


def survey_bl2(bl2: Path, report: dict) -> None:
    cooked = bl2 / "WillowGame" / "CookedPCConsole"
    files = sorted(cooked.glob("*.upk")) if cooked.is_dir() else []
    report["bl2"] = {
        "folder": str(bl2),
        "cooked_exists": cooked.is_dir(),
        "upk_count": len(files),
        "upk_total_mb": round(sum(f.stat().st_size for f in files) / 1e6, 1),
        "other_cooked_ext": sorted({f.suffix for f in cooked.iterdir()} - {".upk"}) if cooked.is_dir() else [],
        "localization": {},
        "targets": {},
    }
    loc = bl2 / "WillowGame" / "Localization"
    if loc.is_dir():
        for lang in sorted(p for p in loc.iterdir() if p.is_dir()):
            names = sorted(p.name for p in lang.iterdir())
            report["bl2"]["localization"][lang.name] = {"count": len(names), "sample": names[:40]}
        hits = []
        for p in (loc / "INT").glob("*") if (loc / "INT").is_dir() else []:
            try:
                text = p.read_bytes()
            except OSError:
                continue
            for needle in (b"Decepti0n", "Decepti0n".encode("utf-16-le")):
                i = text.find(needle)
                if i >= 0:
                    hits.append({"file": p.name, "utf16": needle != b"Decepti0n", "context": text[max(0, i - 200): i + 120].decode("utf-16-le" if needle != b"Decepti0n" else "cp1252", errors="replace")})
        report["bl2"]["localization_hits"] = hits[:20]
    by_stem = {f.stem.lower(): f for f in files}
    report["bl2"]["gd_packages"] = sorted(f.name for f in files if f.stem.lower().startswith(("gd_", "d_")))[:800]
    names_cache: dict[Path, set[str] | str] = {}
    pkg_cache: dict[Path, upk.Package] = {}

    def names_of(f: Path) -> set[str] | str:
        if f not in names_cache:
            try:
                names_cache[f] = {n.lower() for n in upk.read_names_only(f)}
            except Exception as e:  # noqa: BLE001 - report every failure
                names_cache[f] = f"error: {str(e)[:200]}"
        return names_cache[f]

    def package(f: Path) -> upk.Package:
        if f not in pkg_cache:
            if len(pkg_cache) > 4:
                pkg_cache.pop(next(iter(pkg_cache)))
            pkg_cache[f] = upk.open_package(f)
        return pkg_cache[f]

    for row in S.BL2_READS.values():
        t0 = time.time()
        entry: dict = {"object": row.object, "searched": []}
        report["bl2"]["targets"][row.id] = entry
        top = row.object.split(".")[0]
        leaf = re.split(r"[.:]", row.object)[-1]
        prefix = "_".join(top.split("_")[:2]).lower()
        candidates = []
        if top.lower() in by_stem:
            candidates.append(by_stem[top.lower()])
        candidates += [f for s, f in by_stem.items() if s.startswith(prefix) and f not in candidates]
        candidates += [f for s, f in by_stem.items() if s.startswith(top.lower()[:6]) and f not in candidates]
        for f in candidates[:MAX_PACKAGES_PER_TARGET]:
            low = names_of(f)
            if isinstance(low, str):
                entry["searched"].append({"file": f.name, "error": low})
                continue
            entry["searched"].append({"file": f.name, "names": len(low)})
            if leaf.lower() not in low or top.lower() not in low:
                continue
            try:
                pkg = package(f)
                idx = pkg.find(row.object)
                entry["file"] = f.name
                entry["header"] = {k: pkg.header[k] for k in ("version", "licensee", "engine", "cooker", "compression")}
                if not idx:
                    entry["found"] = False
                    entry["similar"] = [pkg.path_of(e.index) for e in pkg.exports if e.name.lower() == leaf.lower()][:10]
                    continue
                entry["found"] = True
                entry["class"] = pkg.obj_class(idx)
                data = pkg.export_data(idx)
                entry["size"] = len(data)
                entry["head_hex"] = data[:160].hex()
                try:
                    entry["properties"] = _json_safe(upk.object_properties(pkg, idx))
                except Exception as e:  # noqa: BLE001
                    entry["properties_error"] = str(e)[:300]
                # one level of referenced subobjects (resolvers, presentations)
                subs = {}
                for e in pkg.exports:
                    if e.outer_index == idx and len(subs) < 12:
                        try:
                            subs[e.name] = {"class": pkg.obj_class(e.index), "properties": _json_safe(upk.object_properties(pkg, e.index))}
                        except Exception as ex:  # noqa: BLE001
                            subs[e.name] = {"class": pkg.obj_class(e.index), "error": str(ex)[:200]}
                entry["subobjects"] = subs
                break
            except Exception as e:  # noqa: BLE001
                entry.setdefault("errors", []).append(f"{f.name}: {traceback.format_exc(limit=3)[-600:]}")
        entry["seconds"] = round(time.time() - t0, 2)


def survey_extract(bl2: Path, report: dict, cache: Path) -> None:
    from .bl2 import extract

    t0 = time.time()
    report["extract"] = extract.extract(bl2, cache)
    report["extract"]["seconds"] = round(time.time() - t0, 1)


def survey_skyrim(sky: Path, report: dict) -> None:
    data = sky / "Data"
    exe = sky / "SkyrimSE.exe"
    out: dict = {"folder": str(sky), "exe_bytes": exe.stat().st_size if exe.is_file() else None}
    report["skyrim"] = out
    esm = data / "Skyrim.esm"
    if not esm.is_file():
        out["error"] = "Skyrim.esm not found"
        return
    tes4, recs = read_plugin(esm, {"NPC_", "LVLN", "LVLI", "MGEF", "QUST", "WEAP", "AMMO", "ENCH", "EQUP"})
    out["localized"] = is_localized(tes4)
    names: dict[int, str] = {}
    try:
        bsa = BSA(data / "Skyrim - Interface.bsa")
        names = parse_table(bsa.read("strings/skyrim_english.strings"), False)
    except Exception as e:  # noqa: BLE001
        out["strings_error"] = str(e)[:200]

    def name(r):
        d = r.first("FULL")
        if d is None:
            return ""
        return names.get(int.from_bytes(d[:4], "little"), "") if out["localized"] else d.rstrip(b"\0").decode("cp1252")

    out["counts"] = {k: len(v) for k, v in recs.items()}
    out["bandit_npcs"] = sorted({(r.edid, name(r)) for r in recs["NPC_"] if "bandit" in r.edid.lower()})[:300]
    out["bandit_lists"] = sorted(r.edid for r in recs["LVLN"] if "bandit" in r.edid.lower())[:200]
    out["loot_lists"] = sorted(r.edid for r in recs["LVLI"] if r.edid.lower().startswith(("loot", "lchest", "lvlweapon")))[:400]
    out["mq101"] = [(r.edid, len(r.all("INDX"))) for r in recs["QUST"] if r.edid == "MQ101"]
    out["crossbow"] = [(r.edid, r.form_id) for r in recs["WEAP"] if "crossbow" in r.edid.lower()][:20]
    out["ench_weapon"] = sorted(r.edid for r in recs["ENCH"] if r.edid.lower().startswith("enchweapon"))[:300]
    out["mgef_damage"] = sorted(r.edid for r in recs["MGEF"] if re.search(r"damage|poison|absorb|summon", r.edid, re.I))[:300]
    out["equip_slots"] = [(r.edid, r.form_id) for r in recs["EQUP"]]
    out["bandit_named"] = sorted({(r.edid, name(r)) for r in recs["NPC_"] if r.edid.startswith("EncBandit") and name(r)})
    dg = data / "Dawnguard.esm"
    if dg.is_file():
        _, drecs = read_plugin(dg, {"WEAP", "AMMO", "PROJ"})
        out["dawnguard_crossbows"] = [(r.edid, r.form_id) for r in drecs["WEAP"] if "crossbow" in r.edid.lower()]
        out["dawnguard_bolts"] = [(r.edid, r.form_id) for r in drecs["AMMO"] if "bolt" in r.edid.lower()]
    out["mgef_samples"] = sorted(r.edid for r in recs["MGEF"] if re.search(r"invis|paraly|summon|fortify|weakness", r.edid, re.I))[:200]
    plugins = Path(os.environ.get("LOCALAPPDATA", "")) / "Skyrim Special Edition" / "plugins.txt"
    out["plugins_txt"] = plugins.read_text(errors="replace")[:4000] if plugins.is_file() else None


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="skylands survey")
    ap.add_argument("--bl2", help="Borderlands 2 folder (default: found through Steam)")
    ap.add_argument("--skyrim", help="Skyrim Special Edition folder (default: found through Steam)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    from .steam import find

    a.bl2 = a.bl2 or (str(find("bl2")) if find("bl2") else None)
    a.skyrim = a.skyrim or (str(find("skyrim")) if find("skyrim") else None)
    if not a.bl2 or not a.skyrim:
        print(f"Could not find the games through Steam (Borderlands 2: {a.bl2}, Skyrim SE: {a.skyrim}).")
        print("Run again with --bl2 \"<folder>\" --skyrim \"<folder>\".")
        return 1
    print(f"Borderlands 2: {a.bl2}\nSkyrim SE: {a.skyrim}\nReading... this can take a few minutes.")
    report: dict = {"tool": "skylands survey 2", "python": sys.version}
    cache = Path(a.out).parent / "skylands-cache"
    for fn, args in ((survey_extract, (Path(a.bl2), report, cache)), (survey_skyrim, (Path(a.skyrim), report))):
        try:
            fn(*args)
        except Exception:  # noqa: BLE001
            report.setdefault("fatal", []).append(traceback.format_exc()[-2000:])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    ex = report.get("extract", {})
    print(f"Skylands survey written to {a.out}")
    print(f"  vault hunters: {len(ex.get('classes', []))}/6, guns: {len(ex.get('weapons', {}).get('guns', []))}, "
          f"enemy types: {len(ex.get('enemies', {}))}, rarity colours: {len(ex.get('rarities', []))}, problems: {len(ex.get('errors', []))}")
    return 0
