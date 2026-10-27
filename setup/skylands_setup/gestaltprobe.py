"""python -m skylands_setup bl2gestalt [--bl2 DIR] [--out FILE]: how Borderlands 2 stores its shotgun (and other) gun meshes (changes nothing).

The shotgun survey found one SkeletalMesh, Remaster_Weap_Shotguns.GestaltDef_Shotgun_GestaltSkeletalMesh (1.7 MB, in Mancana_StartupRemaster.upk), and
a GestaltSkeletalMeshDefinition next to it: one combined "gestalt" mesh holding every shotgun part, instead of one mesh per part. The part
definitions name their piece (GestaltModeSkeletalMeshName = SG_Body_Bandit). This survey lists every gestalt object in the install, decodes the
definitions' properties (they probably say which piece is which) and looks inside the combined meshes: the names stored in them (bones, sections,
materials), what the mesh reader finds, and the first bytes after the properties. With --dump the two shotgun objects are also written as raw files.
"""

from __future__ import annotations

import re
import struct
import sys
import time
from pathlib import Path

from . import steam
from .bl2 import gunmesh, upk

GESTALT = re.compile(r"(?i)gestalt")


def show(value, depth: int = 0, limit: list[int] | None = None) -> list[str]:
    """A decoded property value as indented lines, bounded."""
    out: list[str] = []
    pad = "  " * depth
    if limit is None:
        limit = [400]
    if limit[0] <= 0:
        return out
    if isinstance(value, dict):
        for k, v in value.items():
            if limit[0] <= 0:
                out.append(pad + "...")
                break
            if isinstance(v, (dict, list)) and v:
                out.append(f"{pad}{k}:")
                limit[0] -= 1
                out += show(v, depth + 1, limit)
            else:
                out.append(f"{pad}{k}: {str(v)[:160]}")
                limit[0] -= 1
    elif isinstance(value, list):
        for i, v in enumerate(value):
            if limit[0] <= 0:
                out.append(f"{pad}... ({len(value) - i} more)")
                break
            if isinstance(v, (dict, list)) and v:
                out.append(f"{pad}[{i}]")
                limit[0] -= 1
                out += show(v, depth + 1, limit)
            else:
                out.append(f"{pad}[{i}] {str(v)[:160]}")
                limit[0] -= 1
    else:
        out.append(f"{pad}{str(value)[:160]}")
        limit[0] -= 1
    return out


def fname_runs(pkg: upk.Package, data: bytes, start: int, end: int, cap: int = 400) -> list[str]:
    """Names stored in a blob as (name index, number) pairs: bone, section and material names appear this way."""
    out: list[str] = []
    n = len(pkg.names)
    for p in range(start, min(end, len(data) - 8), 4):
        idx, num = struct.unpack_from("<ii", data, p)
        if 0 < idx < n and 0 <= num < 6:
            name = pkg.names[idx]
            if len(name) >= 3 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_ .\-]*", name):
                out.append(f"+{p - start}:{name}{'' if num == 0 else '_' + str(num - 1)}")
                if len(out) >= cap:
                    break
    return out


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="skylands bl2gestalt")
    ap.add_argument("--bl2")
    ap.add_argument("--out", default="BL2-Gestalt-Report.txt")
    ap.add_argument("--no-dump", action="store_true", help="do not write the raw shotgun objects")
    a = ap.parse_args(argv)
    bl2 = Path(a.bl2) if a.bl2 else steam.find("bl2")
    out_path = Path(a.out)
    lines = [f"skylands bl2gestalt 1  {time.strftime('%Y-%m-%d %H:%M:%S')}"]

    def say(msg: str) -> None:
        print(msg, flush=True)
        lines.append(msg)

    def save() -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not bl2 or not bl2.is_dir():
        say(f"Borderlands 2 not found ({bl2}). Run with --bl2 \"D:\\path\\Borderlands 2\".")
        save()
        return 2
    say(f"Borderlands 2 folder: {bl2}")
    upks = sorted(bl2.rglob("*.upk"))
    packages: list[Path] = []
    for i, p in enumerate(upks):
        try:
            names = upk.read_name_set(p)
        except Exception:  # noqa: BLE001
            continue
        if any(n.startswith("gestaltdef_") or n == "gestaltskeletalmeshdefinition" or n.endswith("_gestaltskeletalmesh") for n in names):
            packages.append(p)
        if i % 400 == 0:
            print(f"  {i}/{len(upks)} name tables", flush=True)
    say(f"{len(packages)} packages mention a gestalt definition or mesh: {[p.name for p in packages][:40]}")
    save()

    found: list[tuple[Path, upk.Package, int]] = []
    for p in packages:
        try:
            pkg = upk.open_package(p)
        except Exception as e:  # noqa: BLE001
            say(f"{p.name}: could not be opened ({type(e).__name__}: {str(e)[:80]})")
            continue
        for i, e in enumerate(pkg.exports, 1):
            cls = pkg.obj_class(i)
            if cls.startswith("Gestalt") or (cls in ("SkeletalMesh", "StaticMesh") and GESTALT.search(e.name)):
                found.append((p, pkg, i))
    say("")
    say(f"{len(found)} gestalt objects:")
    for p, pkg, i in found:
        say(f"  {p.stem}: {pkg.obj_class(i):34} {pkg.path_of(i)}  ({pkg.exports[i - 1].serial_size} bytes)")
    save()

    dump_dir = out_path.parent / "gestalt"
    # the shotgun first, then a few others, definitions before meshes
    order = sorted(found, key=lambda t: (0 if "shotgun" in t[1].exports[t[2] - 1].name.lower() else 1, 0 if t[1].obj_class(t[2]).startswith("Gestalt") else 1))
    said_defs = said_meshes = 0
    for p, pkg, i in order:
        cls = pkg.obj_class(i)
        path = pkg.path_of(i)
        shotgun = "shotgun" in path.lower()
        data = pkg.export_data(i)
        if cls.startswith("Gestalt"):
            if said_defs >= (4 if not shotgun else 99) and not shotgun:
                continue
            said_defs += 1
            say("")
            say(f"=== {path} ({cls}, {len(data)} bytes) in {p.name}")
            try:
                props = upk.object_properties(pkg, i)
                say(f"properties: {len(props)} keys: {list(props)[:40]}")
                for line in show(props, 1, [600 if shotgun else 150]):
                    say(line)
            except Exception as e:  # noqa: BLE001
                say(f"properties could not be read: {type(e).__name__}: {e}")
                say(f"first bytes: {data[:128].hex(' ')}")
            if shotgun and not a.no_dump:
                dump_dir.mkdir(parents=True, exist_ok=True)
                (dump_dir / "GestaltDef_Shotgun.bin").write_bytes(data)
        else:
            if said_meshes >= (3 if not shotgun else 99) and not shotgun:
                continue
            said_meshes += 1
            say("")
            say(f"=== {path} ({cls}, {len(data)} bytes) in {p.name}")
            try:
                props, end = upk.read_properties(pkg, data, 4)
            except Exception as e:  # noqa: BLE001
                props, end = {}, 4
                say(f"properties could not be read: {type(e).__name__}: {e}")
            say(f"properties: {list(props)[:40]}; they end at byte {end}")
            for line in show(props, 1, [60]):
                say(line)
            bounds = gunmesh.read_bounds(data, end)
            say(f"bounds after the properties: {bounds}")
            say(f"first 160 bytes after the properties: {data[end:end + 160].hex(' ')}")
            runs = fname_runs(pkg, data, end, min(len(data), end + 40000), 500)
            say(f"names stored in the first 40000 bytes ({len(runs)}): {runs}")
            say(f"material references: {gunmesh.material_refs(pkg, data, end)}")
            try:
                raw = gunmesh.read_mesh_blob(data, end, path)
                say(f"mesh reader: {raw.note if raw else 'found no geometry'}")
                if raw:
                    xs = [v[0] for v in raw.mesh.positions]
                    ys = [v[1] for v in raw.mesh.positions]
                    zs = [v[2] for v in raw.mesh.positions]
                    say(f"  extent x {min(xs):.1f}..{max(xs):.1f} y {min(ys):.1f}..{max(ys):.1f} z {min(zs):.1f}..{max(zs):.1f}")
            except Exception as e:  # noqa: BLE001
                say(f"mesh reader failed: {type(e).__name__}: {e}")
            if shotgun and not a.no_dump:
                dump_dir.mkdir(parents=True, exist_ok=True)
                (dump_dir / "GestaltMesh_Shotgun.bin").write_bytes(data)
        save()
    say("")
    say(f"Report written to {out_path}. Send it to Claude." + ("" if a.no_dump else f" (The raw shotgun objects are in {dump_dir}; only send those if asked.)"))
    save()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
