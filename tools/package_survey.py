"""Build dist/Skylands-Survey-<n>.zip: the survey tool with its own Python for Windows.

Python comes from python-build-standalone (Astral, CPython under the PSF license), pinned by
SHA-256. Double-click Run-Survey.bat; it writes survey-report.json next to itself.
"""

from __future__ import annotations

import hashlib
import io
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
DIST = ROOT / "dist"
PY_URL = ("https://github.com/astral-sh/python-build-standalone/releases/download/20261003/"
          "cpython-3.13.16+20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz")
PY_SHA256 = "ec43f1a85c29f147d7ae2d13218c52c70b24a983a82ab22d6c607c0593060e10"
SKIP = ("/tcl/", "/Lib/test/", "/Lib/idlelib/", "/Lib/tkinter/", "/Lib/ensurepip/", "/Lib/turtledemo/",
        "/include/", "/Scripts/", "/Lib/site-packages/pip")
BAT = r"""@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0app"
"%~dp0python\python.exe" -X utf8 -m skylands_setup survey --out "%~dp0survey-report.json" %*
echo.
echo Done. Send survey-report.json from this folder back to Claude.
pause
"""
README = """Skylands survey (test round 2)

Double-click Run-Survey.bat. It finds Borderlands 2 and Skyrim Special Edition through Steam,
reads them (it changes nothing in either game) and writes survey-report.json in this folder.
If it cannot find a game, run it from a command prompt with:
  Run-Survey.bat --bl2 "D:\\path\\to\\Borderlands 2" --skyrim "D:\\path\\to\\Skyrim Special Edition"

Includes Python 3.13 (python-build-standalone, PSF license) and lzokay (MIT, LICENSE-lzokay).
"""


def python_tar() -> bytes:
    path = CACHE / PY_URL.rsplit("/", 1)[1]
    if not path.exists():
        CACHE.mkdir(exist_ok=True)
        with urllib.request.urlopen(PY_URL) as r:  # noqa: S310 - fixed official URL
            path.write_bytes(r.read())
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != PY_SHA256:
        path.unlink()
        raise SystemExit("python download checksum mismatch")
    return data


def main() -> int:
    DIST.mkdir(exist_ok=True)
    out = DIST / "Skylands-Survey-2.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        with tarfile.open(fileobj=io.BytesIO(python_tar()), mode="r:gz") as t:
            for m in t.getmembers():
                if not m.isfile() or any(s in "/" + m.name for s in SKIP):
                    continue
                z.writestr(m.name, t.extractfile(m).read())  # python/...
        for f in sorted((ROOT / "setup" / "skylands_setup").rglob("*")):
            if f.is_file() and f.suffix not in (".so", ".pyc") and "__pycache__" not in f.parts:
                z.write(f, "app/" + f.relative_to(ROOT / "setup").as_posix())
        z.write(ROOT / "native" / "lzo" / "LICENSE-lzokay", "LICENSE-lzokay")
        z.writestr("Run-Survey.bat", BAT.replace("\n", "\r\n"))
        z.writestr("README.txt", README.replace("\n", "\r\n"))
    print(f"{out.relative_to(ROOT)} {out.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
