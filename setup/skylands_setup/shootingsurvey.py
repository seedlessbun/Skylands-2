"""Shooting survey: where Borderlands 2 keeps how its guns shoot, as a JSON report.

Run once (Run-ShootingSurvey.bat); it changes nothing. For two balances of each gun type it follows the object references
(balance -> weapon type -> projectile/explosion/impact/damage-type definitions ...) a few levels deep and records every
object's class and properties, so the shooting data (fire mode, shots per pull, pellets, spread, projectile speed, splash
radius, element effects) can be read out of what the game actually holds.
"""

from __future__ import annotations

import json
import re
import sys
import time
import traceback
from pathlib import Path

from . import steam
from .bl2 import extract
from .bl2.index import Index

SEEDS_PER_TYPE = 6
MAX_OBJECTS = 1200
BUDGET_S = 600
DEPTH = 3
PATH = re.compile(r"^[A-Za-z_]\w*(\.\w+)+(:\w+)?$")
# classes that cost time and say nothing about shooting
SKIP = re.compile(r"(Texture|Material|SoundCue|SoundNode|ParticleSystem|SkeletalMesh|StaticMesh|AnimSet|AnimTree|PhysicsAsset|"
                  r"Font|Sequence|SwfMovie|Cascade|Distribution|Module|Behavior|Skel|Light|Surface)", re.I)
INTEREST = re.compile(r"(explos|projectile|impact|bullet|damagetype|weapontype|ammo|firetype|firemode|muzzle|recoil)", re.I)
# followed before anything else, so the object cap is spent on what says how guns shoot
FIRST = re.compile(r"(projectile|explo|firingmode|weapontype|\.wt_|damagetype|behavior_explode|elemental)", re.I)


def _short(v, limit: int = 240):
    text = json.dumps(v, default=str)
    return text if len(text) <= limit else text[:limit] + "..."


def _strings(v, out: list[str], depth: int = 0) -> None:
    if depth > 4:
        return
    if isinstance(v, str):
        if PATH.match(v):
            out.append(v)
    elif isinstance(v, dict):
        for x in v.values():
            _strings(x, out, depth + 1)
    elif isinstance(v, (list, tuple)):
        for x in v:
            _strings(x, out, depth + 1)


def crawl(ix: Index, seeds: list[str], say=print) -> dict:
    t0 = time.time()
    seen: dict[str, dict] = {}
    classes: dict[str, int] = {}
    queue = [(s, 0, "") for s in seeds]
    while queue and len(seen) < MAX_OBJECTS and time.time() - t0 < BUDGET_S:
        path, depth, via = queue.pop(0)
        if path in seen:
            continue
        found = ix.get(path)
        if not found:
            continue
        pkg, idx = found
        cls = pkg.obj_class(idx)
        classes[cls] = classes.get(cls, 0) + 1
        if SKIP.search(cls):
            seen[path] = {"class": cls, "skipped": True, "via": via}
            continue
        props = ix.props(path) or {}
        seen[path] = {"class": cls, "depth": depth, "via": via, "props": {k: _short(v) for k, v in list(props.items())[:60]}}
        if len(seen) % 25 == 0:
            say(f"  {len(seen)} objects read ({time.time() - t0:.0f} s)")
        if depth < DEPTH:
            refs: list[str] = []
            for k, v in props.items():
                found_here: list[str] = []
                _strings(v, found_here)
                refs += [r for r in found_here if r != path]
            for r in dict.fromkeys(refs):
                if r not in seen and not r.lower().startswith(("fx_", "ake_", "common_gunmaterials")):
                    if FIRST.search(r):
                        queue.insert(0, (r, depth + 1, f"{path}"))
                    else:
                        queue.append((r, depth + 1, f"{path}"))
    return {"objects": seen, "class_counts": classes, "seconds": round(time.time() - t0)}


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="skylands shootingsurvey")
    ap.add_argument("--bl2")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    bl2 = Path(a.bl2) if a.bl2 else steam.find("bl2")
    out = Path(a.out)
    report: dict = {"tool": "skylands shootingsurvey 2", "started": time.strftime("%Y-%m-%d %H:%M:%S")}

    def say(msg: str) -> None:
        print(msg, flush=True)

    def save() -> None:
        out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")

    try:
        if not bl2 or not (bl2 / "WillowGame").is_dir():
            say(f"Borderlands 2 not found ({bl2}).")
            return 2
        ix = Index(bl2, out.parent / "cache" / "bl2_index.json", say)
        say("Reading the gun balances ...")
        weapons = extract.guns(ix, [], say)
        seeds: list[str] = []
        by_type: dict[str, list[str]] = {}
        for g in weapons["guns"]:
            by_type.setdefault(g["type"], []).append(g["balance"])
        for t, balances in sorted(by_type.items()):
            picked = []  # one balance per manufacturer: their weapon types carry their own clip, spread, fire rate
            for mfr in ("Bandit", "Dahl", "Hyperion", "Jakobs", "Maliwan", "Tediore", "Torgue", "Vladof"):
                hit = next((b for b in balances if mfr.lower() in b.rsplit(".", 1)[-1].lower()), None)
                if hit and hit not in picked:
                    picked.append(hit)
            picked = picked or balances[:SEEDS_PER_TYPE]
            seeds += picked
            say(f"  {t}: {len(balances)} balances; following {picked}")
        seeds += ["GD_Weap_Shared_Effects.Default_Elemental_Explosions", "GD_Weap_Launchers.Projectiles.Projectile_Rocket_Bandit",
                  "GD_Explosions.explosive.Explosion_ExplosiveMaster", "GD_Explosions.corrosive.Explosion_CorrosiveMaster",
                  "GD_Explosions.Incendiary.Explosion_IncendiaryMaster", "GD_Explosions.shock.Explosion_ShockMaster"]
        report["seeds"] = seeds
        report["package_names"] = sorted(k for k in ix.top if INTEREST.search(k))[:300]
        report["group_names"] = sorted(k for k in ix.groups if INTEREST.search(k) and k.startswith(("gd_", "d_")))[:300]
        save()
        say("Following the references from each balance (a few minutes) ...")
        report["crawl"] = crawl(ix, seeds, say)
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
