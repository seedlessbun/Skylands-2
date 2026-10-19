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

from . import generate
from .skyrim.esm import read_plugin
from .bl2 import extract
from .steam import find

VERSION = "0.9.3"


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
    for d in (sky / "Data" / "Meshes" / "Skylands", sky / "Data" / "Textures" / "Skylands"):
        try:
            d.rmdir()
        except OSError:
            pass
    unplugged = disable_plugin(generate.PLUGIN)
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
        report = generate.generate(data, sky, stage, formids=ids)
        registry.write_text(json.dumps(ids, indent=0), encoding="utf-8")
        (work / "generate-report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        say(f"Built Skylands.esp: {report['records']} records, {report['guns']} guns, "
            f"{report['renamed_enemies']} bandit records renamed, {report['loot_lists']} loot lists extended, "
            f"{report.get('watched_races', 0)} races carry the Skylands ability"
            + (f" (skipped: {', '.join(report['race_skipped'])})" if report.get("race_skipped") else ""))
        if a.stage_only:
            say(f"Staged only, in {stage}")
            return 0
        written = install(stage, sky)
        (work / "installed-files.json").write_text(json.dumps({"skyrim": str(sky), "files": written}, indent=1), encoding="utf-8")
        plugins = enable_plugin(generate.PLUGIN)
        say(f"Installed {len(written)} files into {sky / 'Data'}; enabled in {plugins}")
        done.write_text(f"ok {VERSION} {time.strftime('%Y-%m-%d %H:%M:%S')}\n", encoding="utf-8")
        say(f"Done in {time.time() - t0:.0f} s")
        return 0
    except Exception:  # noqa: BLE001 - everything goes to the log for the player and for support
        say("Setup failed:\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
