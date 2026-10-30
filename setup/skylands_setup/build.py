"""The setup Melty runs once before the first Play: read both games, build Skylands, install it.

  python -m skylands_setup build --bl2 <Borderlands 2> --skyrim <Skyrim SE> --done <marker file>

Writes generated files into <Skyrim>/Data, enables Skylands.esp in the player's plugins.txt,
keeps a list of what it wrote (for a clean uninstall) and a log, then writes the marker Melty
waits for. On any failure it writes the reason to the log and exits non-zero without a marker.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

from . import generate, skse
from .skyrim.esm import read_plugin
from .bl2 import extract
from .steam import find

VERSION = "0.37.0"
OLD_SCRIPTS = ("SkylandsWatcher.pex", "SkylandsClassQuest.pex", "SkylandsRespawn.pex")


RECORD_TYPES = {"STAT", "KYWD", "LIGH", "FLST", "WEAP", "ENCH", "MGEF", "SPEL", "SHOU", "WOOP", "MESG", "QUST", "LVLI", "ACTI"}


def harvest(plugin: Path, ids: dict[str, int]) -> int:
    """Learn the form ids of the Skylands plugin already installed, so rebuilding keeps every record's id (saves
    refer to spells, guns and the quest by id). Ids already known win."""
    if not plugin.is_file():
        return 0
    try:
        _, recs = read_plugin(plugin, RECORD_TYPES)
    except Exception:  # noqa: BLE001 - an unreadable old plugin just means a fresh set of ids
        return 0
    own = len(generate.MASTERS) << 24
    found = 0
    for rtype, rs in recs.items():
        for r in rs:
            key = f"{rtype}:{r.edid}"
            if r.edid and (r.form_id & 0xFF000000) == own and key not in ids:
                ids[key] = r.form_id
                found += 1
    return found


def enable_plugin(plugin: str) -> Path | None:
    """Add '*Skylands.esp' to %LOCALAPPDATA%/Skyrim Special Edition/plugins.txt (keeps every other line)."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    path = Path(base) / "Skyrim Special Edition" / "plugins.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []
    backup = path.with_name("plugins.txt.skylands-backup")
    if path.is_file() and not backup.exists():
        shutil.copyfile(path, backup)
    if not any(line.lstrip("*").strip().lower() == plugin.lower() for line in lines):
        lines.append(f"*{plugin}")
    else:
        lines = [f"*{plugin}" if line.lstrip("*").strip().lower() == plugin.lower() else line for line in lines]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def disable_plugin(plugin: str) -> bool:
    base = os.environ.get("LOCALAPPDATA")
    path = Path(base) / "Skyrim Special Edition" / "plugins.txt" if base else None
    if path is None or not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    kept = [line for line in lines if line.lstrip("*").strip().lower() != plugin.lower()]
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return len(kept) != len(lines)


def prune_empty(sky: Path) -> None:
    """Remove the Skylands folders under Meshes and Textures once nothing is left in them."""
    import os

    for top in (sky / "Data" / "Meshes" / "Skylands", sky / "Data" / "Textures" / "Skylands"):
        for root, _dirs, _files in os.walk(top, topdown=False):
            try:
                Path(root).rmdir()
            except OSError:
                pass


def remove_stale(work: Path, sky: Path, keep: list[str]) -> int:
    """After a new install: delete the files an earlier install put there that this one did not (another gun model method
    leaves different meshes behind). Never touches a file the new install wrote, so the plugin and scripts are never missing."""
    record = work / "installed-files.json"
    if not record.is_file():
        return 0
    try:
        info = json.loads(record.read_text(encoding="utf-8"))
        if Path(info["skyrim"]) != sky:
            return 0
        n = 0
        kept = {k.lower() for k in keep}
        for rel in info["files"]:
            f = sky / rel
            if rel.lower().startswith("data/") and rel.lower() not in kept and f.is_file():
                f.unlink()
                n += 1
        prune_empty(sky)
        return n
    except (OSError, ValueError, KeyError):
        return 0


def verify(sky: Path, plugins: Path | None) -> list[str]:
    """What a player (or support) needs to see after an install: is everything in place and switched on."""
    data = sky / "Data"
    out = []
    esp = data / generate.PLUGIN
    out.append(f"{generate.PLUGIN}: {'present, ' + str(esp.stat().st_size // 1024) + ' KB' if esp.is_file() else 'MISSING'}")
    models = data / generate.MODELS_PLUGIN
    if models.is_file():
        out.append(f"{generate.MODELS_PLUGIN}: present, {models.stat().st_size // 1024} KB")
    for name in ("SkylandsHunter", "SkylandsHunterQuest", "SkylandsHunterPower"):
        pex = data / "Scripts" / f"{name}.pex"
        out.append(f"Scripts\\{name}.pex: {'present' if pex.is_file() else 'MISSING'}")
    st = skse.status(sky)
    out.append(f"SKSE: {'ready' if st.ready else 'NOT READY (see the skse lines above)'}; SkylandsNative.dll: {'present' if st.plugin else 'MISSING'}")
    if plugins and plugins.is_file():
        lines = [x.strip() for x in plugins.read_text(encoding="utf-8", errors="replace").splitlines()]
        entry = [x for x in lines if x.lstrip("*").lower() == generate.PLUGIN.lower()]
        out.append(f"plugins.txt: {entry[0] if entry else 'no Skylands line'} (line {lines.index(entry[0]) + 1 if entry else '-'} of {len(lines)})")
    else:
        out.append("plugins.txt: not found")
    return out


def uninstall_main(argv: list[str]) -> int:
    """Remove exactly the files the setup installed, and the plugin line it added."""
    import argparse

    ap = argparse.ArgumentParser(prog="skylands uninstall")
    ap.add_argument("--work", required=True, help="the folder holding installed-files.json")
    a = ap.parse_args(argv)
    work = Path(a.work)
    record = work / "installed-files.json"
    if not record.is_file():
        print("Nothing to remove: Skylands has not installed anything from this folder.")
        return 0
    info = json.loads(record.read_text(encoding="utf-8"))
    sky = Path(info["skyrim"])
    removed = 0
    for rel in info["files"]:
        f = sky / rel
        if f.is_file():
            f.unlink()
            removed += 1
    prune_empty(sky)
    unplugged = disable_plugin(generate.PLUGIN)
    disable_plugin(generate.MODELS_PLUGIN)
    record.unlink()
    for marker in work.glob("setup-done*.txt"):
        marker.unlink()
    print(f"Removed {removed} Skylands files from {sky / 'Data'}" + ("; plugin disabled." if unplugged else "."))
    return 0


def install(stage: Path, skyrim: Path) -> list[str]:
    written = []
    for f in sorted((stage / "Data").rglob("*")):
        if f.is_file():
            rel = f.relative_to(stage)
            dest = skyrim / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dest)
            written.append(str(rel).replace("\\", "/"))
    return written


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="skylands build")
    ap.add_argument("--bl2")
    ap.add_argument("--skyrim")
    ap.add_argument("--done", required=True, help="marker file written when everything is installed")
    ap.add_argument("--gun-models", default="off", choices=["off", "proxy", "native", "umodel", "auto"],
                    help="where the guns get their own meshes from (default: off, every gun looks like the crossbow)")
    ap.add_argument("--gun-shooting", default="off", choices=["off", "bullets", "bl2", "both", "staff"],
                    help="bl2: Borderlands rounds per gun type and element (fast bullets, rockets and elemental guns explode); bullets: only the steel bolt becomes a fast flat shot; both")
    ap.add_argument("--gun-calibrate", action="store_true", help="give each rarity a different hold (for finding the right one by eye)")
    ap.add_argument("--staff-turn", default="60,0,180", help="staff-type SMG: turn (pitch,yaw,roll degrees) of the model in the staff grip: rolled 180 (0.13.6: it pointed up and was upside down); pitch -45 pointed straight up (0.13.12), 45 faced forward but a little high (0.14.2), so 0.14.4 lowers it 15 degrees: 60 (more pitch lowers the barrel)")
    ap.add_argument("--gun-pitch", type=float, default=0.0, help="raise the barrel this many more degrees (negative lowers it)")
    ap.add_argument("--gun-spin", type=float, default=0.0, help="turn every gun model this many degrees about its up axis (fixes a gun facing the wrong way)")
    ap.add_argument("--gun-scale", type=float, default=1.0, help="make every gun model this many times bigger or smaller")
    ap.add_argument("--gun-attach", default="auto", choices=["auto", "sockets", "none"],
                    help="how Borderlands 2 gun parts are placed on the body (native/umodel methods)")
    ap.add_argument("--bl2-sounds", default="auto", choices=["auto", "off"],
                    help="staff guns: take each gun's shot sound from Borderlands 2's Wwise packs (decoded with vgmstream, downloaded into the work folder); off keeps Skyrim's stand-ins")
    ap.add_argument("--stage-only", action="store_true", help="build into the work folder without installing")
    a = ap.parse_args(argv)
    done = Path(a.done)
    work = done.parent
    work.mkdir(parents=True, exist_ok=True)
    log = work / "skylands-setup.log"
    t0 = time.time()

    def say(msg: str) -> None:
        print(msg, flush=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

    try:
        if done.exists():
            done.unlink()
        bl2 = Path(a.bl2) if a.bl2 else find("bl2")
        sky = Path(a.skyrim) if a.skyrim else find("skyrim")
        if not bl2 or not (bl2 / "WillowGame").is_dir():
            say(f"Borderlands 2 not found ({bl2}). Skylands reads it to build its guns and vault hunters.")
            return 2
        if not sky or not (sky / "Data" / "Skyrim.esm").is_file():
            say(f"Skyrim Special Edition not found ({sky}).")
            return 2
        say(f"Skylands {VERSION} setup. Borderlands 2: {bl2}  Skyrim SE: {sky}")
        data = extract.extract(bl2, work / "cache", say, budget_minutes=40)
        (work / "pandora.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
        digest = extract.summarize_parts(data.get("weapons", {}))
        (work / "parts-summary.json").write_text(json.dumps(digest, indent=1), encoding="utf-8")
        say(f"Gun parts read: {digest['parts']} ({digest['parts_with_effects']} with stat effects) for "
            f"{digest['balances_with_parts']}/{digest['balances']} gun balances.")
        say(f"Read Borderlands 2: {len(data.get('classes', []))} vault hunters, "
            f"{len(data.get('weapons', {}).get('guns', []))} gun balances, {len(data.get('enemies', {}))} enemy types, "
            f"{len(data.get('rarities', []))} rarity colours")
        for e in data.get("errors", []):
            say(f"  note: {e}")
        stage = work / "stage"
        shutil.rmtree(stage, ignore_errors=True)
        registry = work / "formids.json"
        ids: dict[str, int] = {}
        if registry.is_file():
            try:
                ids = {k: int(v) for k, v in json.loads(registry.read_text(encoding="utf-8")).items()}
            except (OSError, ValueError):
                ids = {}
        learned = harvest(sky / "Data" / generate.PLUGIN, ids)
        say(f"Form ids: {len(ids)} from before ({learned} read from the installed plugin).")
        sources = {}
        if a.gun_models in ("native", "umodel", "auto"):
            from .bl2 import gunparts
            from .bl2.index import Index

            ix = Index(bl2, work / "cache" / "bl2_index.json", say)
            sources["native"] = gunparts.Bl2Source(ix, say, attach=a.gun_attach)
            all_parts = sorted({p for g in data.get("weapons", {}).get("guns", []) for opts in g["slots"].values() for p in opts})
            say(f"Finding the meshes of {len(all_parts)} gun parts (one pass over the package name tables) ...")
            sources["native"].prepare(all_parts)
            if a.gun_models in ("umodel", "auto"):
                from .bl2 import umodel

                command = umodel.locate(work, say)
                if command:
                    say(f"UModel: {command[0]}")
                    sources["umodel"] = umodel.UModelSource(ix, say, command, work, attach=a.gun_attach)
                    sources["umodel"].name_files = sources["native"].name_files  # same lookup, one scan
                    sources["umodel"].log = lambda msg, force=False, _s=sources["umodel"]: _s.say(f"  umodel: {msg}")
                else:
                    say("UModel was not found and could not be downloaded. Download it from https://www.gildor.org/en/projects/umodel (the Windows zip), "
                        "unzip it and put umodel.exe (or umodel_64.exe) in the work folder next to this log, then run this installer again.")
        shot_sounds = None
        if a.gun_shooting == "staff" and a.bl2_sounds == "auto":
            from .bl2 import audio

            wanted = sorted({(g["type"], g.get("manufacturer", "")) for g in data.get("weapons", {}).get("guns", [])
                             if g["type"] in generate.STAFF_KINDS and g.get("manufacturer")})
            say(f"Looking for the Borderlands 2 shot sounds of {len(wanted)} gun type x manufacturer pairs ...")
            shot_sounds = audio.extract_shot_sounds(bl2, work, wanted, say)
        report = generate.generate(data, sky, stage, formids=ids, shot_sounds=shot_sounds, gun_models=a.gun_models, model_sources=sources,
                                   model_spin=a.gun_spin, model_pitch=a.gun_pitch, model_calibrate=a.gun_calibrate, shooting=a.gun_shooting, model_scale=a.gun_scale, staff_turn=tuple(float(x) for x in a.staff_turn.split(",")))
        for src in sources.values():
            say(src.summary())
        for line in report.get("model_log", []):
            say(line)
        registry.write_text(json.dumps(ids, indent=0), encoding="utf-8")
        (work / "generate-report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        say(f"Built Skylands.esp: {report['records']} records, {report['guns']} guns, "
            f"{report['renamed_enemies']} bandit records renamed, {report['loot_lists']} loot lists extended, "
            f"{report.get('watched_races', 0)} races carry the Skylands ability"
            + (f" (skipped: {', '.join(report['race_skipped'])})" if report.get("race_skipped") else ""))
        if a.stage_only:
            say(f"Staged only, in {stage}")
            return 0
        bin_dir = Path(__file__).resolve().parent / "bin"
        sk = skse.status(sky)
        for line in skse.describe(sk):
            say(f"  skse: {line}")
        staged = skse.stage_plugin(stage, bin_dir, sky / skse.PLUGIN_REL.rsplit('/', 1)[0] / skse.PLUGIN_INI, data.get("shields"))
        say(f"shields: read from Borderlands 2: {data.get('shields') or 'nothing (the sheet defaults are used)'}")
        say(f"SkylandsNative plugin: {'staged for install' if staged else 'not in this build (bin/SkylandsNative.dll is missing)'}")
        for old in OLD_SCRIPTS:  # scripts of earlier versions: a saved game still running one of them would keep acting on stale values
            (sky / "Data" / "Scripts" / old).unlink(missing_ok=True)
        try:
            written = install(stage, sky)
        except PermissionError as e:
            say(f"Could not write {e.filename}: Skyrim (or a mod manager or antivirus) has it open. Close Skyrim and any mod manager, then run this installer again. "
                "Nothing that was installed before has been removed.")
            return 1
        say(f"Installed {len(written)} files into {sky / 'Data'}")
        gone = remove_stale(work, sky, written)
        (work / "installed-files.json").write_text(json.dumps({"skyrim": str(sky), "files": written}, indent=1), encoding="utf-8")
        if gone:
            say(f"Removed {gone} files of the previous install that this one does not use.")
        plugins = enable_plugin(generate.PLUGIN)
        if generate.MODELS_PLUGIN.lower() in {w.lower().rsplit("/", 1)[-1] for w in written}:
            enable_plugin(generate.MODELS_PLUGIN)  # after Skylands.esp, which it needs
        else:
            disable_plugin(generate.MODELS_PLUGIN)
        say(f"Plugin enabled in {plugins}")
        for line in verify(sky, plugins):
            say(f"  check: {line}")
        done.write_text(f"ok {VERSION} {time.strftime('%Y-%m-%d %H:%M:%S')}\n", encoding="utf-8")
        say(f"Done in {time.time() - t0:.0f} s")
        return 0
    except Exception:  # noqa: BLE001 - everything goes to the log for the player and for support
        say("Setup failed:\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
