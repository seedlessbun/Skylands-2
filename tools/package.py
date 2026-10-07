"""Build the release: dist/Skylands-<version>.zip, dist/entries.json and dist/melty.json.

The zip holds only Skylands' own setup program plus the runtimes it needs (CPython from
python-build-standalone, PSF license; lzokay, MIT). On the player's PC Melty unpacks it to
{managed}/Skylands and runs its setup once; the setup reads the player's Borderlands 2 and Skyrim
SE and builds the Skyrim files there. No file of either game is in the release.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_survey import SKIP, python_tar  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "setup"))
from skylands_setup.build import VERSION  # noqa: E402

README = f"""Skylands {VERSION}: Skyrim, played as a Borderlands vault hunter.

Melty installs this and runs its setup once before the first Play. The setup reads your own
Borderlands 2 and Skyrim Special Edition installs and builds Skylands.esp, its scripts and its loot-beam
meshes into Skyrim's Data folder, then enables Skylands.esp in plugins.txt.

Log: skylands-setup.log next to this file. Installed files: installed-files.json.
Credits and licenses: CREDITS.md, LICENSE-lzokay, python/LICENSE.txt.
"""


def recipe(file_name: str) -> dict:
    return {
        "schemaVersion": 1,
        "mode": "installed",
        "games": [{"slug": "skyrim-se", "role": "primary"}, {"slug": "borderlands-2", "role": "companion"}],
        "components": [{"id": "main", "fileName": file_name, "label": "Skylands setup", "kind": "main", "required": True}],
        "requirements": [],
        "mappings": [{"component": "main", "from": "Skylands/", "to": "{managed}/Skylands"}],
        "setup": {
            "label": "Skylands from your Borderlands 2",
            "launch": {"kind": "exe", "path": "{managed}/Skylands/python/python.exe",
                       "args": ["-X", "utf8", "{managed}/Skylands/app/run_setup.py", "build",
                                "--bl2", "{game:borderlands-2}", "--skyrim", "{game}",
                                "--done", f"{{managed}}/Skylands/setup-done-{VERSION}.txt"]},
            "done": {"file": f"{{managed}}/Skylands/setup-done-{VERSION}.txt", "contains": "ok"},
            "stopWhenDone": True,
        },
        "launch": {"kind": "exe", "path": "{game}/SkyrimSE.exe"},
    }


def main() -> int:
    DIST.mkdir(exist_ok=True)
    name = f"Skylands-{VERSION}.zip"
    out = DIST / name
    entries: list[dict] = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        def add(arc: str, data: bytes) -> None:
            info = zipfile.ZipInfo(arc, date_time=(2026, 10, 7, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
            entries.append({"path": arc, "size": len(data)})

        with tarfile.open(fileobj=io.BytesIO(python_tar()), mode="r:gz") as t:
            for m in t.getmembers():
                if m.isfile() and not any(s in "/" + m.name for s in SKIP):
                    add("Skylands/" + m.name, t.extractfile(m).read())
        app = ROOT / "setup"
        for f in sorted(app.rglob("*")):
            if f.is_file() and f.suffix not in (".so", ".pyc") and "__pycache__" not in f.parts:
                add("Skylands/app/" + f.relative_to(app).as_posix(), f.read_bytes())
        add("Skylands/CREDITS.md", (ROOT / "CREDITS.md").read_bytes())
        add("Skylands/LICENSE-lzokay", (ROOT / "native" / "lzo" / "LICENSE-lzokay").read_bytes())
        add("Skylands/README.txt", README.replace("\n", "\r\n").encode())
    (DIST / "entries.json").write_text(json.dumps(entries), encoding="utf-8")
    (DIST / "melty.json").write_text(json.dumps(recipe(name), indent=2), encoding="utf-8")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"{out.relative_to(ROOT)} {out.stat().st_size} bytes sha256 {digest} {len(entries)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
