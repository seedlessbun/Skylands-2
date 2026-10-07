"""Find which Borderlands 2 package holds an object, across the base game and every DLC folder."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import upk

INDEX_VERSION = 1


class Index:
    def __init__(self, bl2_root: Path, cache: Path | None = None) -> None:
        self.root = Path(bl2_root)
        self.files = sorted(p for p in self.root.rglob("*.upk") if p.is_file())
        self.errors: dict[str, str] = {}
        self.names: dict[str, list[int]] = {}  # lowercased name -> file indices
        key = [INDEX_VERSION, len(self.files), sum(p.stat().st_size for p in self.files)]
        if cache is not None and cache.is_file():
            try:
                c = json.loads(cache.read_text(encoding="utf-8"))
                if c.get("key") == key:
                    self.names = c["names"]
                    self.errors = c.get("errors", {})
                    return
            except (OSError, ValueError):
                pass
        for i, f in enumerate(self.files):
            try:
                for n in {x.lower() for x in upk.read_names_only(f)}:
                    self.names.setdefault(n, []).append(i)
            except Exception as e:  # noqa: BLE001 - some files (shader caches) are not object packages
                self.errors[str(f.relative_to(self.root))] = str(e)[:120]
        if cache is not None:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps({"key": key, "names": self.names, "errors": self.errors}), encoding="utf-8")
            except OSError:
                pass
        self._open: dict[Path, upk.Package] = {}

    def candidates(self, path: str) -> list[Path]:
        """Packages whose name table holds every part of the object path."""
        parts = [p.lower() for p in re.split(r"[.:]", path) if p]
        sets = [set(self.names.get(p, [])) for p in parts]
        common = set.intersection(*sets) if sets else set()
        return [self.files[i] for i in sorted(common)]

    def package(self, f: Path) -> upk.Package:
        if not hasattr(self, "_open"):
            self._open = {}
        if f not in self._open:
            if len(self._open) > 6:
                self._open.pop(next(iter(self._open)))
            self._open[f] = upk.open_package(f)
        return self._open[f]

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
        found = self.get(path)
        if found is None:
            return None
        pkg, idx = found
        return upk.object_properties(pkg, idx)

    def children(self, path: str, class_name: str | None = None) -> list[str]:
        """Exports directly inside an object or package group (e.g. every balance in A_Weapons)."""
        out: list[str] = []
        for f in self.candidates(path):
            try:
                pkg = self.package(f)
            except Exception:  # noqa: BLE001
                continue
            for e in pkg.exports:
                if pkg.outer(e.index) and pkg.path_of(pkg.outer(e.index)).lower() == path.lower():
                    if class_name is None or pkg.obj_class(e.index) == class_name:
                        p = pkg.path_of(e.index)
                        if p not in out:
                            out.append(p)
        return out
