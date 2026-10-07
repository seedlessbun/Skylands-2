"""Find games in the player's Steam libraries (used when Melty has not passed the folders)."""

from __future__ import annotations

import os
import re
from pathlib import Path

GAMES = {"bl2": ("49520", "Borderlands 2"), "skyrim": ("489830", "Skyrim Special Edition")}


def steam_root() -> Path | None:
    try:
        import winreg

        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for key, val in ((r"Software\Valve\Steam", "SteamPath"), (r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        p = Path(winreg.QueryValueEx(k, val)[0])
                        if p.is_dir():
                            return p
                except OSError:
                    continue
    except ImportError:
        pass
    for p in (Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Steam", Path.home() / ".steam" / "steam"):
        if p.is_dir():
            return p
    return None


def libraries() -> list[Path]:
    root = steam_root()
    if root is None:
        return []
    libs = [root]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    try:
        for m in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore")):
            p = Path(m.replace("\\\\", "\\"))
            if p not in libs:
                libs.append(p)
    except OSError:
        pass
    return libs


def find(game: str) -> Path | None:
    appid, folder = GAMES[game]
    for lib in libraries():
        manifest = lib / "steamapps" / f"appmanifest_{appid}.acf"
        install = None
        try:
            m = re.search(r'"installdir"\s+"([^"]+)"', manifest.read_text(encoding="utf-8", errors="ignore"))
            install = m.group(1) if m else None
        except OSError:
            pass
        for name in filter(None, (install, folder)):
            p = lib / "steamapps" / "common" / name
            if p.is_dir():
                return p
    return None
