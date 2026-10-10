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
5. To undo everything: Uninstall-Skylands.bat (removes only the files Skylands installed and its plugin line;
   plugins.txt.skylands-backup next to your plugins.txt is a copy from before the first install).

Includes Python 3.13 (python-build-standalone, PSF license) and lzokay (MIT, LICENSE-lzokay).
Nothing from Borderlands 2 or Skyrim is included; it is all built on your PC from your own copies.
"""


def main() -> int:
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / "Skylands-TestBuild-2.zip"
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
        z.writestr("Uninstall-Skylands.bat", UNINSTALL.replace("\n", "\r\n"))
        z.writestr("README.txt", README.replace("\n", "\r\n"))
    print(f"{out.relative_to(ROOT)} {out.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
