"""The "umodel" method: let UModel (Konstantin Nosov's UE viewer, which knows Borderlands 2's mesh format) export each gun
part mesh, then read the PSK/PSKX it writes. Sockets (where parts attach) and the part -> mesh lookup still come from our own
package reader, so only the geometry and textures differ from the native method.

UModel is not shipped with Skylands: setup downloads it from its author's site into the work folder when it is missing (or
uses a copy you put there, or the path in SKYLANDS_UMODEL). If it cannot be found the method reports that and the next
method in the chain takes over.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path

from .. import imgconv
from .. import meshes as M
from . import gunparts, psk

DOWNLOADS = ("https://www.gildor.org/down/47/umodel/umodel_win32.zip", "https://www.gildor.org/down/umodel/umodel_win32.zip")
EXE_NAMES = ("umodel_64.exe", "umodel.exe", "umodel_64", "umodel")
IMAGE_EXT = (".tga", ".png", ".dds")


def find_exe(work: Path, say) -> list[str] | None:
    env = os.environ.get("SKYLANDS_UMODEL")
    cands = [Path(env)] if env else []
    for d in (work, work / "tools", work / "umodel"):
        cands += [d / n for n in EXE_NAMES]
    for c in cands:
        if c.is_file():
            return [str(c)]
    return None


def download(work: Path, say) -> list[str] | None:
    dest = work / "tools"
    for url in DOWNLOADS:
        try:
            say(f"  umodel: downloading {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "Skylands-setup"})
            with urllib.request.urlopen(req, timeout=90) as r:
                blob = r.read()
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                dest.mkdir(parents=True, exist_ok=True)
                names = [n for n in z.namelist() if not n.endswith("/")]
                if not any(Path(n).name.lower().startswith("umodel") for n in names):
                    raise zipfile.BadZipFile("no umodel in the archive")
                for n in names:
                    (dest / Path(n).name).write_bytes(z.read(n))
            say(f"  umodel: downloaded ({len(blob) // 1024} KB, sha256 {hashlib.sha256(blob).hexdigest()[:16]}...)")
            return find_exe(work, say)
        except Exception as e:  # noqa: BLE001
            say(f"  umodel: {url} failed ({type(e).__name__}: {str(e)[:100]})")
    return None


def locate(work: Path, say) -> list[str] | None:
    return find_exe(work, say) or download(work, say)


class UModelSource(gunparts.Bl2Source):
    def __init__(self, ix, say, command: list[str], work: Path, game: str = "bl2", minutes: float = 35.0,
                 attach: str = "auto") -> None:
        super().__init__(ix, say, attach=attach)
        self.command = command
        self.out_root = Path(work) / "umodel-export"
        self.game = game
        self.deadline = time.time() + minutes * 60
        self.failures = 0
        self.stats["exported"] = 0
        self.stats["export_failed"] = 0

    def export(self, pkg, idx: int, path: str) -> Path | None:
        name = pkg.obj_name(idx)
        cls = pkg.obj_class(idx)
        out = self.out_root / re.sub(r"[^A-Za-z0-9_.-]", "_", path)[:120]
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True, exist_ok=True)
        cooked = pkg.path.parent
        for game_args in ([f"-game={self.game}"], []):
            cmd = [*self.command, "-export", *game_args, f"-path={cooked}", f"-out={out}", "-nolightmap", str(pkg.path), name, cls]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(out))
            except (subprocess.TimeoutExpired, OSError) as e:
                self._fail(path, f"{type(e).__name__}: {e}")
                return None
            if any(out.rglob("*.psk*")):
                return out
            tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
            last = " | ".join(tail)
        self._fail(path, f"no mesh file written (exit {r.returncode}): {last[:240]}")
        return None

    def _fail(self, path: str, why: str) -> None:
        self.stats["export_failed"] += 1
        self.failures += 1
        self.log(f"umodel export of {path} failed: {why}", force=self.failures <= 6)

    def _read_part(self, part: str) -> dict | None:
        path = self.mesh_path(part)
        if not path:
            self.stats["no_mesh"] += 1
            self.log(f"{part}: no mesh object found in its properties")
            return None
        pkg, idx = self.ix.get(path)
        out = self.export(pkg, idx, path)
        if out is None:
            return None
        self.stats["exported"] += 1
        files = sorted(out.rglob("*.psk*"), key=lambda p: -p.stat().st_size)
        try:
            groups = psk.read_by_material(files[0].read_bytes())
        except psk.PSKError as e:
            self.stats["no_geometry"] += 1
            self.log(f"{path}: {e}")
            return None
        mesh = M.merged([m for m, _ in groups])
        self.stats["meshes"] += 1
        self.log(f"{path}: {len(mesh.positions)} vertices, {len(mesh.tris)} triangles (umodel)")
        key = self._texture_from(out, [name for _, name in groups])
        mesh.texture = key
        mesh.normal_map = "flat_n"
        return {"mesh": mesh, "sockets": self._sockets(pkg, path), "path": path, "texture": key}

    def _texture_from(self, out: Path, materials: list[str]) -> str | None:
        images = [p for p in out.rglob("*") if p.suffix.lower() in IMAGE_EXT]
        if not images:
            return None

        def score(p: Path) -> int:
            n = p.stem.lower()
            if any(k in n for k in ("norm", "_n", "spec", "_s", "mask", "_m", "emis")):
                return 0
            return 2 if any(k in n for k in ("diff", "_d", "albedo", "base", "color")) else 1

        best = max(images, key=lambda p: (score(p), p.stat().st_size))
        if score(best) == 0:
            return None
        key = "t_" + hashlib.sha1(best.stem.lower().encode()).hexdigest()[:8]
        if key in self.textures:
            return key
        try:
            self.textures[key] = imgconv.to_dds(best)
        except Exception as e:  # noqa: BLE001
            self.log(f"{best.name}: {type(e).__name__}: {e}")
            return None
        self.stats["textured"] += 1
        return key

    def summary(self) -> str:
        s = self.stats
        return (f"umodel: {s['parts']} parts looked at, {s['exported']} exported, {s['export_failed']} export failures, "
                f"{s['meshes']} meshes read, {s['textured']} textures converted")
