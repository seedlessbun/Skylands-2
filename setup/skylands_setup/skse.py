"""SKSE (the Skyrim Script Extender) as a dependency of Skylands: what the player's install has, and what Skylands adds.

Skylands guns need three things the player installs once, none of which Skylands may ship:
  * SKSE64, matching the Skyrim runtime (skse64_loader.exe and skse64_<major>_<minor>_<build>.dll next to SkyrimSE.exe);
  * Address Library for SKSE Plugins (Data/SKSE/Plugins/versionlib-*.bin; version-*.bin on 1.5.97), which every
    CommonLibSSE plugin, including SkylandsNative.dll, uses to find the game's functions on any runtime;
  * Skyrim started through skse64_loader.exe (Steam's Play button starts the game without SKSE).
Skylands installs its own plugin, Data/SKSE/Plugins/SkylandsNative.dll (built by .github/workflows/skse-plugin.yml).
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

PLUGIN_DLL = "SkylandsNative.dll"
PLUGIN_INI = "SkylandsNative.ini"
PLUGIN_REL = f"Data/SKSE/Plugins/{PLUGIN_DLL}"
SKSE_DOWNLOAD = "https://skse.silverlock.org/"
ADDRESS_LIBRARY = "https://www.nexusmods.com/skyrimspecialedition/mods/32444"
DEFAULT_INI = """; SkylandsNative settings
[Skylands]
; the version of this file's defaults: an install keeps the values you changed while this number is the same, and writes the new defaults (the old file is kept as .old) when it is not
IniVersion=3
; how far ahead (game units) the bullets are aimed to cross the crosshair
Convergence=3000
; a short glowing flash at the muzzle with every bullet (1 on, 0 off)
MuzzleFlash=1
; aiming down the sights (hold the block button): the share of the spread left when fully aimed (0.1 to 1)
AimSpread=0.5
; the share of the walking speed left when fully aimed (0.1 to 1)
AimWalk=0.7
; how quickly the aim comes up and goes down (whole aims a second, 1 to 30)
AimRate=7
; the gun moves to the middle of the screen while aimed (1 on, 0 off); where its muzzle sits: ahead of the eye, below it, to the right of it (game units)
AimCenter=1
; the aimed gun is placed from the player's position and angles of this frame (1) or the camera's (0)
AimPredict=1
; the reload key as a keyboard scan code (47 is V; 19 is R, which is also Ready Weapon: while a gun is in the hand it no longer puts the weapon away)
ReloadKey=47
; a mouse button as the reload key as well (3, 4, 5 ... are the side buttons; -1 none)
ReloadMouse=-1
; short ammo messages on the screen: reloading, magazine full, low ammo (1 on, 0 off)
AmmoText=1
; ammo: a player with none of a gun's ammo is given this many rounds when the gun is first taken up in a run of the game, and enemies that die with a gun carry some
StartAmmo=300
; the Borderlands-style display at the bottom right (1 on, 0 off: the plain messages come back); where its right edge and bottom line are, in a 1280 x 720 HUD
Hud=1
HudRight=70
HudBottom=80
AmmoDrops=1
AimForward=33
AimDown=6.5
AimRight=0
; recoil: degrees the view kicks up with a shot (0 = none), the most it drifts sideways, the share of the kick given back when the shooting stops, the kick's share while aimed, and how far (units) the aimed gun jerks back
RecoilPitch=0.55
RecoilYaw=0.22
RecoilRecover=0.6
RecoilAim=0.6
RecoilGun=1.0
; the arms are hidden while fully aimed (1 on, 0 off); shell casings out of the gun, smoke at the muzzle, a small burst where an elemental bullet ends (1 on, 0 off)
HideHands=1
Casings=1
Smoke=1
ImpactBursts=1
; the aimed gun's sway (breathing, walking, a lag behind turns): 1 is the default, 0 none, 2 twice as much
Sway=1.0
"""


def exe_version(path: Path) -> tuple[int, int, int, int] | None:
    """The file version of a Windows executable, from the VS_FIXEDFILEINFO block of its version resource."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    sig = struct.pack("<I", 0xFEEF04BD)
    at = data.find(sig)
    while at != -1 and at + 16 <= len(data):
        struc_version, ms, ls = struct.unpack_from("<III", data, at + 4)
        if struc_version == 0x00010000:
            return ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF
        at = data.find(sig, at + 1)
    return None


@dataclass
class SkseStatus:
    runtime: tuple[int, int, int, int] | None = None
    loader: bool = False
    skse_dll: str | None = None  # the skse64_*.dll that matches the runtime
    skse_dlls: list[str] = field(default_factory=list)  # every skse64_*.dll found
    address_library: str | None = None
    plugin: bool = False  # SkylandsNative.dll in place

    @property
    def ready(self) -> bool:
        return self.loader and self.skse_dll is not None and self.address_library is not None


def status(skyrim: Path) -> SkseStatus:
    """What the player's Skyrim folder has of SKSE, Address Library and the Skylands plugin."""
    sky = Path(skyrim)
    st = SkseStatus()
    st.runtime = exe_version(sky / "SkyrimSE.exe")
    st.loader = (sky / "skse64_loader.exe").is_file()
    st.skse_dlls = sorted(f.name for f in sky.glob("skse64_*.dll"))
    if st.runtime:
        want = f"skse64_{st.runtime[0]}_{st.runtime[1]}_{st.runtime[2]}.dll".lower()
        st.skse_dll = next((n for n in st.skse_dlls if n.lower() == want), None)
    plugins = sky / "Data" / "SKSE" / "Plugins"
    if st.runtime:
        a, b, c, d = st.runtime
        names = [f"versionlib-{a}-{b}-{c}-{d}.bin", f"version-{a}-{b}-{c}-{d}.bin"]
        st.address_library = next((n for n in names if (plugins / n).is_file()), None)
    elif plugins.is_dir():  # the runtime could not be read: any Address Library file will do for the report
        st.address_library = next((f.name for f in plugins.glob("version*-*.bin")), None)
    st.plugin = (plugins / PLUGIN_DLL).is_file()
    return st


def describe(st: SkseStatus) -> list[str]:
    """Lines for the setup log: what is there, and exactly what to do about what is not."""
    rt = ".".join(map(str, st.runtime)) if st.runtime else "unknown (SkyrimSE.exe not readable)"
    out = [f"Skyrim runtime: {rt}"]
    out.append(f"SKSE loader (skse64_loader.exe): {'found' if st.loader else 'MISSING'}")
    if st.runtime:
        want = f"skse64_{st.runtime[0]}_{st.runtime[1]}_{st.runtime[2]}.dll"
        out.append(f"SKSE for this runtime ({want}): {'found' if st.skse_dll else 'MISSING' + (' (found for another version: ' + ', '.join(st.skse_dlls) + ')' if st.skse_dlls else '')}")
    out.append(f"Address Library (versionlib-*.bin in Data/SKSE/Plugins): {st.address_library or 'MISSING'}")
    if not st.ready:
        out.append("Skylands needs SKSE and Address Library for its guns (the staff gun does nothing without them). To add them:")
        if not (st.loader and st.skse_dll):
            out.append(f"  1. Download SKSE64 (the 'Current Anniversary Edition build' for Skyrim {rt}, 7z or installer) from {SKSE_DOWNLOAD}")
            out.append("     and copy skse64_loader.exe, the skse64_*.dll and the Data/Scripts folder into your Skyrim folder (next to SkyrimSE.exe).")
        if not st.address_library:
            out.append(f"  2. Download 'Address Library for SKSE Plugins' (All in one, the file for your runtime) from {ADDRESS_LIBRARY}")
            out.append("     and copy its Data/SKSE/Plugins/versionlib-*.bin file into your Skyrim's Data/SKSE/Plugins folder.")
        out.append("  3. Start Skyrim with skse64_loader.exe (not Steam's Play button, which starts it without SKSE).")
    return out


def _ini_values(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith((";", "[")) and "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def merge_ini(default: str, old: str | None) -> tuple[str, bool]:
    """The settings file to install: the defaults, with the values the player changed kept when the old file has the same IniVersion. Returns (text, kept)."""
    if not old:
        return default, False
    before, after = _ini_values(old), _ini_values(default)
    if before.get("IniVersion") != after.get("IniVersion"):
        return default, False
    lines = []
    for line in default.splitlines():
        key = line.partition("=")[0].strip()
        if "=" in line and not line.strip().startswith((";", "[")) and key in before and key != "IniVersion":
            line = f"{key}={before[key]}"
        lines.append(line)
    return "\n".join(lines) + "\n", True


def stage_plugin(stage: Path, bin_dir: Path, existing_ini: Path | None = None) -> str | None:
    """Put the Skylands plugin (if the build has it) and its settings in the stage folder, so they install and uninstall with the rest. The player's values in an
    installed settings file of the same IniVersion are kept; a file of another version is kept next to the new one as .old."""
    dll = Path(bin_dir) / PLUGIN_DLL
    if not dll.is_file():
        return None
    dest = Path(stage) / "Data" / "SKSE" / "Plugins"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / PLUGIN_DLL).write_bytes(dll.read_bytes())
    old = None
    if existing_ini is not None and Path(existing_ini).is_file():
        try:
            old = Path(existing_ini).read_text(encoding="utf-8", errors="replace")
        except OSError:
            old = None
    text, kept = merge_ini(DEFAULT_INI, old)
    (dest / PLUGIN_INI).write_text(text, encoding="utf-8")
    if old and not kept:
        (dest / (PLUGIN_INI + ".old")).write_text(old, encoding="utf-8")
    return f"Data/SKSE/Plugins/{PLUGIN_DLL}"


def parse_version(text: str) -> tuple[int, ...] | None:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?", text)
    return tuple(int(g) for g in m.groups() if g is not None) if m else None
