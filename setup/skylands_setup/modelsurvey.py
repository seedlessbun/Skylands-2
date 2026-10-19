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
    cands: list[str] = []
    for v in props.values():
        gunparts._strings(v, cands)  # noqa: SLF001
    rep["string_values"] = [c[:120] for c in cands if "." in c][:20]
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


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="skylands modelsurvey")
    ap.add_argument("--bl2")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    bl2 = Path(a.bl2) if a.bl2 else steam.find("bl2")
    out = Path(a.out)
    report: dict = {"tool": "skylands modelsurvey 1", "started": time.strftime("%Y-%m-%d %H:%M:%S")}

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
        src = gunparts.Bl2Source(ix, lambda m: None)
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
        say("Looking for character meshes ...")
        try:
            report["characters"] = character_survey(ix)
        except Exception:  # noqa: BLE001
            report["characters"] = traceback.format_exc()[-600:]
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
