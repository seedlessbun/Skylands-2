"""Build dist/Skylands-TestBuild-<n>.zip: install Skylands by hand to try it before it goes on Melty.

Install-Skylands.bat runs the same setup Melty will run (reads your Borderlands 2 and Skyrim installs, builds
Skylands.esp + scripts + loot-beam meshes into Skyrim's Data folder, enables the plugin).
Uninstall-Skylands.bat removes exactly what it installed.
"""

from __future__ import annotations

import io
import sys
import tarfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_survey import SKIP, python_tar  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "setup"))
from skylands_setup.build import VERSION  # noqa: E402

INSTALL = r"""@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0app"
echo Skylands %VERSION%: building from your Borderlands 2 and Skyrim installs. This takes a minute or two.
"%~dp0python\python.exe" -X utf8 -m skylands_setup build --done "%~dp0work\setup-done.txt" %*
echo.
echo Log: %~dp0work\skylands-setup.log
pause
""".replace("%VERSION%", VERSION)
MODEL_BATS = {
    "Proxy": ("proxy", "stylised guns made from boxes and cylinders in each manufacturer's colours (always works)"),
    "Native": ("native", "Borderlands 2 gun meshes read straight from the game's packages"),
    "Native-Calibrate": ("native --gun-calibrate", "like Native, but every rarity is held differently (Common to E-tech = six holds) so you can pick the right one by eye"),
    "Shooting-BL2": ("native --gun-shooting bl2", "native gun models and Borderlands shooting: each gun gets its own rounds (equipped for you), a magazine and reload time, shotgun pellets, automatic bursts for SMGs and rifles, spread, and rockets/elemental rounds that explode; messages on screen say what it is doing"),
    "Shooting-Bullets": ("native --gun-shooting bullets", "native gun models, and the steel bolt becomes a fast, nearly flat shot (bullet-like)"),
    "Shooting-Both": ("native --gun-shooting both", "Borderlands rounds and the faster steel bolt together"),
    "Shooting-Staff": ("native --gun-shooting staff", "STAGE 1 TEST: the Shooting-BL2 install plus ONE submachine gun built on a vanilla staff (given to you once; a staff casts a spell that fires the bullet, so no ammo, no magicka, no charge cost). Compare it with the crossbow SMGs"),
    "UModel": ("umodel", "Borderlands 2 gun meshes exported with the free UModel tool (downloaded during setup; if that fails, put umodel.exe from gildor.org in the work folder)"),
    "Auto": ("auto", "native, then UModel, then proxy, for each gun"),
}
MODEL_BAT = INSTALL.replace("%*", "--gun-models %METHOD% %*").replace("%METHOD%", "{method}")
SHOOTING_SURVEY = r"""@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0app"
echo Reading how Borderlands 2 guns shoot: fire modes, projectiles, explosions, elements (changes nothing; several minutes) ...
"%~dp0python\python.exe" -X utf8 -m skylands_setup shootingsurvey --out "%~dp0work\shooting-survey.json" %*
echo.
echo Send work\shooting-survey.json back to Claude.
"""
SURVEY = r"""@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0app"
echo Reading what Borderlands 2 holds for gun meshes and textures (changes nothing; a few minutes) ...
"%~dp0python\python.exe" -X utf8 -m skylands_setup modelsurvey --out "%~dp0work\gun-model-survey.json" %*
echo.
echo Send work\gun-model-survey.json back to Claude.
pause
"""
UNINSTALL = r"""@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0app"
"%~dp0python\python.exe" -X utf8 -m skylands_setup uninstall --work "%~dp0work"
echo.
pause
"""
README = f"""Skylands {VERSION} test build: Skyrim played as a Borderlands vault hunter

1. Quit Skyrim if it is running.
2. Double-click Install-Skylands.bat and wait for "Done". It reads Borderlands 2 and Skyrim SE (through Steam),
   writes Skylands.esp, scripts and loot-beam files into Skyrim's Data folder and turns the plugin on.
   If it cannot find a game, run it from a command prompt with:
     Install-Skylands.bat --bl2 "D:\\path\\Borderlands 2" --skyrim "D:\\path\\Skyrim Special Edition"
3. Start Skyrim from Steam. Load a save (or start a new game).
4. About two seconds after you can move, a "Choose your Vault Hunter" box appears. Pick one. You get that
   vault hunter's action skill, a starter pistol (equipped) and 60 bolts. Use a NEW game or a save from
   before you chose: a save that already chose a vault hunter will not get the starter pistol again.
5. New in 0.8: when you load a save, a box asks whether to respawn enemies (you can say "always" or "never"); the
   lesser power "Pandora Respawn" does it any time and changes the setting. In a dungeon you are taken back to where
   you came in. The lesser power "Pandora Log Enemies" notes the hostile people around you for respawning right
   away (the same thing happens by itself every couple of seconds). It all works on an existing character: loading
   the save gives you both powers. Beams are plain statics now; a message on screen says whether the beam and the light were made.
6. What to look for (no Skyrim script extender is needed): your starter pistol, a "Skylands gun speed" message when you equip a gun, bandits that carry
   guns (a message names them), guns dropping on the ground when they die with a coloured beam and light over
   them, and a stats line on every gun. If something is missing, send work\\skylands-setup.log, work\\parts-summary.json
   and a screenshot.
7. To undo everything: Uninstall-Skylands.bat (removes only the files Skylands installed and its plugin line;
   plugins.txt.skylands-backup next to your plugins.txt is a copy from before the first install).

GUN MODELS (new, being tested): Install-Skylands.bat leaves every gun looking like a crossbow. These install the same
Skylands but put each gun's own mesh in a second plugin, SkylandsGunModels.esp (Skylands.esp itself is never changed, so your saves keep their powers and guns; the plain installer removes the second plugin); try them one at a time (each re-run replaces the last):
""" + "".join(f"  Install-Skylands-GunModels-{n}.bat  - {why}\n" for n, (_m, why) in MODEL_BATS.items()) + """  Check: the gun in your hand, on the ground and in the inventory (size, direction, colours, no crash), then send
  work\\skylands-setup.log: it says how many gun meshes each method built and which guns kept the crossbow.
  If guns face the wrong way or are too big/small, add --gun-spin 180 (any angle) or --gun-scale 1.5 to the same command,
  e.g.  Install-Skylands-GunModels-Proxy.bat --gun-spin 90
  Run-GunModelSurvey.bat reads Borderlands 2 and writes work\\gun-model-survey.json (what the real mesh files look like);
  send it whenever the native or UModel method builds fewer meshes than it should.

Includes Python 3.13 (python-build-standalone, PSF license) and lzokay (MIT, LICENSE-lzokay).
Nothing from Borderlands 2 or Skyrim is included; it is all built on your PC from your own copies.
"""


def main() -> int:
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / "Skylands-TestBuild-75.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        with tarfile.open(fileobj=io.BytesIO(python_tar()), mode="r:gz") as t:
            for m in t.getmembers():
                if m.isfile() and not any(s in "/" + m.name for s in SKIP):
                    z.writestr(m.name, t.extractfile(m).read())
        app = ROOT / "setup"
        for f in sorted(app.rglob("*")):
            if f.is_file() and f.suffix not in (".so", ".pyc") and "__pycache__" not in f.parts:
                z.write(f, "app/" + f.relative_to(app).as_posix())
        z.write(ROOT / "native" / "lzo" / "LICENSE-lzokay", "LICENSE-lzokay")
        z.write(ROOT / "CREDITS.md", "CREDITS.md")
        z.writestr("Install-Skylands.bat", INSTALL.replace("\n", "\r\n"))
        for name, (method, _why) in MODEL_BATS.items():
            z.writestr(f"Install-Skylands-GunModels-{name}.bat", MODEL_BAT.format(method=method).replace("\n", "\r\n"))
        z.writestr("Run-GunModelSurvey.bat", SURVEY.replace("\n", "\r\n"))
        z.writestr("Run-ShootingSurvey.bat", SHOOTING_SURVEY.replace("\n", "\r\n"))
        z.writestr("Uninstall-Skylands.bat", UNINSTALL.replace("\n", "\r\n"))
        z.writestr("README.txt", README.replace("\n", "\r\n"))
    print(f"{out.relative_to(ROOT)} {out.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
