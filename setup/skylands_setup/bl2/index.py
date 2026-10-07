"""Find which Borderlands 2 package holds an object, across the base game and every DLC folder.

Speed matters here (about 900 packages, over a gigabyte): names are read with a tight loop, opened
packages are kept in a generous cache, lookups use per-package dictionaries, and property reads are
remembered, because gun balances share base definitions and part lists.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path

from . import upk

OPEN_PACKAGES = 24  # kept open at once (a big package is a few hundred MB of Python objects at worst)


class Index:
    def __init__(self, bl2_root: Path, cache: Path | None = None, progress: Callable[[str], None] | None = None) -> None:
        self.root = Path(bl2_root)
        self.say = progress or (lambda _m: None)
        self.deadline: float | None = None  # time.time() after which property reads raise TimeoutError
        self.files = sorted(p for p in self.root.rglob("*.upk") if p.is_file())
        self.errors: dict[str, str] = {}
        self.names: dict[str, list[int]] = {}  # lowercased name -> file indices
        self._open: dict[Path, upk.Package] = {}
        self._props: dict[str, dict | None] = {}
        total = len(self.files)
        t0 = time.time()
        self.say(f"Indexing {total} Borderlands 2 packages ...")
        step = max(1, total // 20)
        for i, f in enumerate(self.files):
            try:
                for n in upk.read_name_set(f):
                    self.names.setdefault(n, []).append(i)
            except Exception as e:  # noqa: BLE001 - some files (shader caches) are not object packages
                self.errors[str(f.relative_to(self.root))] = str(e)[:120]
            if (i + 1) % step == 0 or i + 1 == total:
                self.say(f"  indexed {i + 1}/{total} packages ({time.time() - t0:.0f} s)")

    def candidates(self, path: str) -> list[Path]:
        """Packages whose name table holds every part of the object path."""
        parts = [p.lower() for p in re.split(r"[.:]", path) if p]
        sets = [set(self.names.get(p, [])) for p in parts]
        common = set.intersection(*sets) if sets else set()
        return [self.files[i] for i in sorted(common)]

    def package(self, f: Path) -> upk.Package:
        if f in self._open:
            self._open[f] = self._open.pop(f)  # most recently used goes last
            return self._open[f]
        if len(self._open) >= OPEN_PACKAGES:
            self._open.pop(next(iter(self._open)))
        pkg = self._open[f] = upk.open_package(f)
        return pkg

    def get(self, path: str) -> tuple[upk.Package, int] | None:
        for f in self.candidates(path):
            try:
                pkg = self.package(f)
            except Exception:  # noqa: BLE001
                continue
            idx = pkg.find(path)
            if idx:
                return pkg, idx
        return None

    def props(self, path: str) -> dict | None:
        if path in self._props:
            return self._props[path]
        if self.deadline is not None and time.time() > self.deadline:
            raise TimeoutError("the time budget for reading Borderlands 2 ran out")
        found = self.get(path)
        result = None
        if found is not None:
            pkg, idx = found
            try:
                result = upk.object_properties(pkg, idx)
            except Exception:  # noqa: BLE001 - reported by callers as "not found"
                result = None
        if len(self._props) > 200_000:
            self._props.clear()
        self._props[path] = result
        return result

    def children(self, path: str, class_name: str | None = None) -> list[str]:
        """Exports directly inside an object or package group (e.g. every balance in A_Weapons)."""
        out: list[str] = []
        for f in self.candidates(path):
            try:
                pkg = self.package(f)
            except Exception:  # noqa: BLE001
                continue
            for i in pkg.children_of(path):
                if class_name is None or pkg.obj_class(i) == class_name:
                    p = pkg.path_of(i)
                    if p not in out:
                        out.append(p)
        return out
