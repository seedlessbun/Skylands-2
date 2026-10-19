"""Gun model survey: what the real Borderlands 2 files hold for gun meshes and textures, as a JSON report.

Run once (Run-GunModelSurvey.bat); it changes nothing. For a sample of gun parts it records how each part points at its
mesh, what the mesh export looks like, whether the geometry reader found vertices/triangles/UVs, which materials and
textures it found, and a hex head of whatever it could not read, so the next build can be fixed from the real layout.
"""

from __future__ import annotations

import json
import re
import struct
import sys
import time
import traceback
from pathlib import Path

from . import steam
from .bl2 import extract, gunmesh, gunparts, upk
from .bl2.index import Index

PER_SLOT = 5
DUMPS: dict[str, int] = {}


def _bulk_summary(data: bytes, start: int, limit: int = 12) -> list[dict]:
    out = []
    for off, size, count in gunmesh._bulk_arrays(data, start, None, min_count=8):  # noqa: SLF001
        out.append({"offset": off, "element_size": size, "count": count})
        if len(out) >= limit:
            break
    return out


def inspect_part(ix: Index, src: gunparts.Bl2Source, part: str) -> dict:
    rep: dict = {"part": part}
    props = ix.props(part) or {}
    rep["property_keys"] = sorted(props)[:60]
    for key in ("GestaltModeSkeletalMeshName", "AdditionalGestaltModeSkeletalMeshNames", "bIsGestaltMode", "PartType"):
        if key in props:
            rep.setdefault("raw", {})[key] = repr(props[key])[:300]
    rep["gestalt_names"] = src.gestalt_names(part)
    rep["name_table_packages"] = {n: [f.name for f in (src.name_files or {}).get(n, [])][:6] for n in rep["gestalt_names"]}
    cands: list[str] = []
    for v in props.values():
        gunparts._strings(v, cands)  # noqa: SLF001
    rep["string_values"] = [c[:120] for c in cands if "." in c][:20]
    rep["derived_paths"] = src.derived_paths(part)
    mic = props.get("Material")
    if isinstance(mic, str):  # a Material part: the paint job of a whole gun
        info = {"material": mic}
        params = gunmesh.texture_parameters(ix, mic)
        info["parameters"] = dict(list(params.items())[:12])
        diffuse, normal = gunmesh.pick_textures(params)
        info["diffuse"], info["normal"] = diffuse, normal
        if diffuse:
            tp = ix.props(diffuse) or {}
            info["diffuse_props"] = {k: str(v)[:60] for k, v in list(tp.items())[:16]}
            notes: list[str] = []
            dds = gunmesh.read_texture(ix, diffuse, ix.root, notes.append)
            info["diffuse_decoded"] = bool(dds)
            if not dds and DUMPS.get("textures", 0) < 2:
                DUMPS["textures"] = DUMPS.get("textures", 0) + 1
                tf = ix.get(diffuse)
                if tf:
                    tdata = tf[0].export_data(tf[1])
                    info["texture_export_hex"] = tdata[:6000].hex()
                    info["texture_export_total"] = len(tdata)
            info["notes"] = notes[:4]
            found = ix.get(diffuse)
            if found:
                data = found[0].export_data(found[1])
                info["texture_export_bytes"] = len(data)
                info["texture_head_hex"] = data[:96].hex()
        rep["gun_material"] = info
    path = src.mesh_path(part)
    rep["mesh_path"] = path
    if not path:
        return rep
    pkg, idx = ix.get(path)
    data = pkg.export_data(idx)
    rep["mesh_class"] = pkg.obj_class(idx)
    rep["package"] = pkg.path.name
    rep["export_bytes"] = len(data)
    end = None
    for start in (4, 0, 8):
        try:
            p, end = upk.read_properties(pkg, data, start)
            rep["mesh_properties"] = {k: str(v)[:80] for k, v in list(p.items())[:20]}
            break
        except Exception:  # noqa: BLE001
            continue
    rep["properties_end"] = end
    end = end or 4
    rep["bounds"] = gunmesh.read_bounds(data, end)
    rep["bulk_arrays"] = _bulk_summary(data, end + 28)
    raw = gunmesh.read_mesh_blob(data, end, path)
    rep["geometry"] = raw.note if raw else "NOT FOUND"
    if not raw and len(data) <= 40000 and DUMPS.get("meshes", 0) < 3:
        DUMPS["meshes"] = DUMPS.get("meshes", 0) + 1
        rep["export_hex"] = data.hex()  # the whole mesh export: enough to work out its layout offline
    if raw:
        lo, hi = raw.mesh.bounds()
        rep["geometry_bounds"] = {"min": [round(v, 2) for v in lo], "max": [round(v, 2) for v in hi]}  # around the part's own origin, or placed in weapon space?
    if not raw:
        rep["hex_after_properties"] = data[end:end + 160].hex()
    rep["sockets"] = {k: v for k, v in list(src._sockets(pkg, path).items())[:12]}  # noqa: SLF001
    mats = gunmesh.material_refs(pkg, data, end)
    rep["materials"] = mats[:6]
    rep["textures"] = []
    for m in mats[:3]:
        params = gunmesh.texture_parameters(ix, m)
        info = {"material": m, "parameters": dict(list(params.items())[:12])}
        diffuse, normal = gunmesh.pick_textures(params)
        info["diffuse"], info["normal"] = diffuse, normal
        if diffuse:
            tp = ix.props(diffuse) or {}
            info["diffuse_props"] = {k: str(v)[:60] for k, v in list(tp.items())[:16]}
            dds = gunmesh.read_texture(ix, diffuse, ix.root, lambda msg, i=info: i.setdefault("notes", []).append(msg))
            info["diffuse_decoded"] = bool(dds)
        rep["textures"].append(info)
    return rep


CHARACTER_PACKAGES = re.compile(r"(char|pawn|psycho|marauder|nomad|siren|assassin|soldier|mercenary|mechromancer|player|bandit|midget)", re.I)


def character_survey(ix: Index, limit: int = 40) -> list[dict]:
    """Which packages hold character meshes (for the later enemy and player model work): classes and a few names each."""
    out = []
    for f in ix.files:
        if not CHARACTER_PACKAGES.search(f.stem) or len(out) >= limit:
            continue
        try:
            pkg = ix.package(f)
        except Exception as e:  # noqa: BLE001
            out.append({"package": f.name, "error": str(e)[:100]})
            continue
        classes: dict[str, list[str]] = {}
        for i, e in enumerate(pkg.exports, 1):
            cls = pkg.obj_class(i)
            if cls in ("SkeletalMesh", "AnimSet", "PhysicsAsset", "Texture2D", "MaterialInstanceConstant"):
                classes.setdefault(cls, []).append(pkg.path_of(i))
        if classes.get("SkeletalMesh"):
            out.append({"package": f.name, "mb": round(f.stat().st_size / 1e6, 1),
                        **{k: {"count": len(v), "sample": v[:6]} for k, v in classes.items()}})
    return out


def part_name_dump(ix: Index, src: gunparts.Bl2Source, by_slot: dict[str, list[str]], budget: float = 300.0) -> dict:
    """Every part, the mesh name it asks for, the paths that name could live at and where the name turns up. Answers why most
    manufacturers' meshes are not found: which package, if any, holds an object of that name and what class it is."""
    t0 = time.time()
    parts = sorted({p for ps in by_slot.values() for p in ps})
    rows = []
    for part in parts:
        names = src.gestalt_names(part)
        rows.append({"part": part, "mesh_names": names, "derived": src.derived_paths(part)[:4],
                     "files_naming_it": [[f.stem for f in (src.name_files or {}).get(n, [])][:8] for n in names]})
    wanted = sorted({n for r in rows for n in r["mesh_names"]})
    found: dict[str, list] = {}
    opened = 0
    for name in wanted:
        if time.time() - t0 > budget:
            found["_stopped"] = [f"time budget used up after {opened} packages"]
            break
        hits = []
        for f in sorted((src.name_files or {}).get(name, []), key=lambda f: f.stat().st_size)[:6]:
            try:
                pkg = ix.package(f)
                pkg._indexes()  # noqa: SLF001
                opened += 1
                hits += [{"file": f.stem, "kind": "export", "path": pkg.path_of(i), "class": pkg.obj_class(i)} for i in pkg._by_name.get(name, ())][:3]  # noqa: SLF001
                hits += [{"file": f.stem, "kind": "import", "path": pkg.path_of(-(k + 1)), "class": imp.class_name}
                         for k, imp in enumerate(pkg.imports) if imp.name.lower() == name][:2]
            except Exception as e:  # noqa: BLE001
                hits.append({"file": f.stem, "error": f"{type(e).__name__}: {str(e)[:80]}"})
        found[name] = hits
    groups = {k: [ix.files[i].stem for i, _n in v][:6] for k, v in ix.groups.items() if k.startswith(("weap_", "wpn_", "weapon"))}
    return {"parts": rows, "where_found": found, "weapon_groups": groups,
            "mesh_class_counts": {n: sum(1 for h in hs if h.get("class") in ("SkeletalMesh", "StaticMesh")) for n, hs in found.items() if n != "_stopped"}}


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="skylands modelsurvey")
    ap.add_argument("--bl2")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    bl2 = Path(a.bl2) if a.bl2 else steam.find("bl2")
    out = Path(a.out)
    report: dict = {"tool": "skylands modelsurvey 2", "started": time.strftime("%Y-%m-%d %H:%M:%S")}

    def say(msg: str) -> None:
        print(msg, flush=True)

    def save() -> None:
        out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")

    try:
        if not bl2 or not (bl2 / "WillowGame").is_dir():
            say(f"Borderlands 2 not found ({bl2}).")
            return 2
        work = out.parent
        ix = Index(bl2, work / "cache" / "bl2_index.json", say)
        report["tfc_files"] = [str(p.relative_to(bl2)) for p in bl2.rglob("*.tfc")][:20]
        say("Reading the gun balances (this is the slow part) ...")
        weapons = extract.guns(ix, [], say)
        report["guns"] = len(weapons["guns"])
        by_slot: dict[str, list[str]] = {}
        for g in weapons["guns"]:
            for slot, options in g["slots"].items():
                for part in options:
                    if part not in by_slot.setdefault(slot, []):
                        by_slot[slot].append(part)
        report["slots"] = {k: len(v) for k, v in by_slot.items()}
        src = gunparts.Bl2Source(ix, say)
        sample = [part for slot, parts in sorted(by_slot.items()) for part in parts[:PER_SLOT]]
        say("Scanning the package name tables for the meshes the parts name ...")
        src.prepare(sample)
        report["parts"] = []
        for slot, parts in sorted(by_slot.items()):
            for part in parts[:PER_SLOT]:
                say(f"  {slot}: {part}")
                try:
                    report["parts"].append({"slot": slot, **inspect_part(ix, src, part)})
                except Exception:  # noqa: BLE001
                    report["parts"].append({"slot": slot, "part": part, "error": traceback.format_exc()[-800:]})
                save()
        try:
            src._mesh_by_name_build()  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pass
        names = src._meshes_by_name or {}  # noqa: SLF001
        report["weapon_mesh_names"] = {"count": sum(len(v) for v in names.values()),
                                       "sample": [p for v in list(names.values())[:60] for p in v[:1]]}
        report["weapon_groups"] = sorted(k for k in ix.groups if re.search(r"(pistol|smg|shotgun|sniper|launcher|assault|rifle|weap|wpn|gun)", k))[:300]
        report["packages_with_weapon_names"] = [f.name for f in ix.files if re.search(r"(pistol|smg|shotgun|sniper|launcher|assault|rifle|weap|wpn|gun)", f.stem, re.I)][:100]
        say("Writing the part-name dump (which package holds each mesh a part asks for) ...")
        try:
            full = [p for ps in by_slot.values() for p in ps]
            src.prepare(full)
            report["part_name_dump"] = part_name_dump(ix, src, by_slot)
        except Exception:  # noqa: BLE001
            report["part_name_dump"] = traceback.format_exc()[-800:]
        save()
        say("Looking for character meshes ...")
        try:
            report["characters"] = character_survey(ix)
        except Exception:  # noqa: BLE001
            report["characters"] = traceback.format_exc()[-600:]
        report["open_errors"] = dict(list(ix.open_errors.items())[:40])
        report["summary"] = src.summary()
        report["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save()
        say(f"Wrote {out}")
        return 0
    except Exception:  # noqa: BLE001
        report["fatal"] = traceback.format_exc()
        save()
        say("Failed:\n" + report["fatal"])
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
