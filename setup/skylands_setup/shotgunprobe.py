"""python -m skylands_setup bl2shotguns [--bl2 DIR] [--out FILE]: where Borderlands 2 keeps its shotgun data (changes nothing).

The installer found the names of the 26 shotgun meshes (sg_body_bandit ...) in the part definitions but no package that exports a mesh of
that name. This survey looks at everything in the install that could be a shotgun: files by name, every package's name table, then (in the
packages that mention shotguns) every export and import whose name looks like one, with its class, full path and size, and where an import
points (an import names the package the game loads the object from, so a missing file shows up here). It also lists the weapon meshes
that DO exist for the other gun types, for comparison.
"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter
from pathlib import Path

from . import steam
from .bl2 import upk

SHOT = re.compile(r"(?i)(shotgun|^sg_|_sg_|_sg$|^sg\d|scatter|pellet|buckshot|blunderbuss)")
FILE_WORDS = re.compile(r"(?i)(shotgun|weap|gun|sg_|startup|common|global)")
MESH = ("SkeletalMesh", "StaticMesh")
TYPE_PART = re.compile(r"(?i)^(ar|smg|pistol|sg|sr|l|shotgun|sniper|launcher|rifle)s?_(body|barrel|grip|stock|mag|magazine|sight|accessory|receiver|pump)")


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="skylands bl2shotguns")
    ap.add_argument("--bl2")
    ap.add_argument("--out", default="BL2-Shotgun-Report.txt")
    ap.add_argument("--minutes", type=float, default=12.0, help="time allowed for opening packages")
    a = ap.parse_args(argv)
    bl2 = Path(a.bl2) if a.bl2 else steam.find("bl2")
    out_path = Path(a.out)
    lines = [f"skylands bl2shotguns 1  {time.strftime('%Y-%m-%d %H:%M:%S')}"]

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

    # 1. the files
    ext: Counter = Counter()
    named: list[tuple[int, Path]] = []
    upks: list[Path] = []
    for p in bl2.rglob("*"):
        if not p.is_file():
            continue
        ext[p.suffix.lower()] += 1
        if p.suffix.lower() == ".upk":
            upks.append(p)
        if FILE_WORDS.search(p.stem) and p.suffix.lower() != ".upk":
            named.append((p.stat().st_size, p))
    upks.sort()
    say(f"File types: {dict(ext.most_common(20))}")
    say(f"{len(upks)} packages. Other files whose names look weapon-related ({len(named)}):")
    for size, p in sorted(named, reverse=True)[:40]:
        say(f"  {size / 1e6:9.2f} MB  {p.relative_to(bl2)}")
    say("Packages whose file name looks weapon-related:")
    for p in upks:
        if re.search(r"(?i)(shotgun|weap|gun|_sg)", p.stem):
            say(f"  {p.stat().st_size / 1e6:9.2f} MB  {p.relative_to(bl2)}")
    stems = {p.stem.lower(): p for p in upks}

    # 2. every package's name table
    say("")
    say("Name tables:")
    t0 = time.time()
    hits: dict[Path, set[str]] = {}
    unreadable: list[str] = []
    for i, p in enumerate(upks):
        try:
            names = upk.read_name_set(p)
        except Exception as e:  # noqa: BLE001
            unreadable.append(f"{p.name}: {type(e).__name__}: {str(e)[:80]}")
            continue
        found = {n for n in names if SHOT.search(n)}
        if found:
            hits[p] = found
        if i % 300 == 0:
            print(f"  {i}/{len(upks)} name tables", flush=True)
    say(f"{len(hits)} of {len(upks)} packages have a shotgun-looking name ({time.time() - t0:.0f} s); {len(unreadable)} could not be read: {unreadable[:10]}")
    allnames: Counter = Counter()
    for found in hits.values():
        allnames.update(found)
    say(f"{len(allnames)} different shotgun-looking names; the most common:")
    for n, c in allnames.most_common(120):
        say(f"  {c:4} packages  {n}")
    save()

    # 3. open the packages that mention shotguns (plus the weapon-named ones)
    say("")
    say("Inside the packages:")
    todo = sorted(set(hits) | {p for p in upks if re.search(r"(?i)(shotgun|weap)", p.stem)}, key=lambda p: (p.stat().st_size, p.name))
    t1 = time.time()
    classes: Counter = Counter()
    meshes_seen: list[str] = []
    missing_outer: Counter = Counter()
    opened = 0
    for p in todo:
        if time.time() - t1 > a.minutes * 60:
            say(f"(time is up after {opened} of {len(todo)} packages; run again with --minutes {a.minutes * 2:g} for the rest)")
            break
        try:
            pkg = upk.open_package(p)
        except Exception as e:  # noqa: BLE001
            say(f"{p.name}: could not be opened ({type(e).__name__}: {str(e)[:100]})")
            continue
        opened += 1
        rows: list[str] = []
        for i, e in enumerate(pkg.exports, 1):
            if SHOT.search(e.name):
                cls = pkg.obj_class(i)
                classes[cls] += 1
                rows.append(f"    export {cls:22} {pkg.path_of(i)}  ({e.serial_size} bytes)")
            elif pkg.obj_class(i) in MESH and TYPE_PART.search(e.name):
                meshes_seen.append(f"{p.stem}: {pkg.path_of(i)}")
        for k, imp in enumerate(pkg.imports):
            if SHOT.search(imp.name):
                path = pkg.path_of(-(k + 1))
                top = path.split(".")[0].split(":")[0].lower()
                where = "in this install" if top in stems else "NOT in this install"
                if top not in stems:
                    missing_outer[top] += 1
                rows.append(f"    import {imp.class_name:22} {path}  -> package {top}: {where}")
        if rows:
            say(f"{p.name} ({p.stat().st_size / 1e6:.1f} MB): {len(rows)} shotgun-looking objects")
            for r in rows[:60]:
                say(r)
            if len(rows) > 60:
                say(f"    ... {len(rows) - 60} more")
    say(f"opened {opened} packages in {time.time() - t1:.0f} s; classes of the shotgun-looking exports: {dict(classes)}")
    say(f"imports pointing into packages that are not in this install: {dict(missing_outer.most_common(30))}")
    save()

    # 4. what weapon meshes exist for every gun type (for comparison)
    say("")
    say(f"Weapon part meshes found in those packages ({len(meshes_seen)}):")
    by_type: Counter = Counter(re.split(r"[_.]", m.split(": ")[1].split(".")[-1].lower())[0] for m in meshes_seen)
    say(f"  by gun type: {dict(by_type)}")
    for m in sorted(set(meshes_seen))[:400]:
        say(f"  {m}")
    say("")
    say(f"Report written to {out_path}. Send it to Claude.")
    save()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
