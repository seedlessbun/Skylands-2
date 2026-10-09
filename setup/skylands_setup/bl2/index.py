"""Find which Borderlands 2 package holds an object, across the base game and every DLC folder.

Speed matters here (about 900 packages, over a gigabyte): names are read with a tight loop, opened
packages are kept in a generous cache, lookups use per-package dictionaries, and property reads are
remembered, because gun balances share base definitions and part lists.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from pathlib import Path

from . import upk

OPEN_PACKAGES = 24  # kept open at once (a big package is a few hundred MB of Python objects at worst)


INDEX_VERSION = 2


class Index:
    def __init__(self, bl2_root: Path, cache: Path | None = None, progress: Callable[[str], None] | None = None) -> None:
        self.root = Path(bl2_root)
        self.say = progress or (lambda _m: None)
        self.deadline: float | None = None  # time.process_time() (CPU time, so sleep does not count) after which property reads raise TimeoutError
        self.files = sorted(p for p in self.root.rglob("*.upk") if p.is_file())
        self.errors: dict[str, str] = {}
        self.top: dict[str, list[int]] = {}  # lowercased top-level export -> file indices
        self.groups: dict[str, list[tuple[int, int]]] = {}  # "top.group" -> (file index, objects in it), biggest first
        self.slow: list[dict] = []
        self._open: dict[Path, upk.Package] = {}
        self._props: dict[str, dict | None] = {}
        total = len(self.files)
        key = hashlib.sha1(json.dumps([INDEX_VERSION, [(str(f.relative_to(self.root)), f.stat().st_size) for f in self.files]]).encode()).hexdigest()
        if cache is not None and self._load(cache, key):
            self.say(f"Using the saved index of {total} Borderlands 2 packages.")
            return
        t0 = time.time()
        self.say(f"Indexing {total} Borderlands 2 packages ...")
        step = max(1, total // 20)
        for i, f in enumerate(self.files):
            try:
                top, groups = upk.index_info(f)
                for n in top:
                    self.top.setdefault(n, []).append(i)
                for g, count in groups.items():
                    self.groups.setdefault(g, []).append((i, count))
            except Exception as e:  # noqa: BLE001 - some files (shader caches) are not object packages
                self.errors[str(f.relative_to(self.root))] = str(e)[:120]
            if (i + 1) % step == 0 or i + 1 == total:
                self.say(f"  indexed {i + 1}/{total} packages ({time.time() - t0:.0f} s)")
        for entries in self.groups.values():
            entries.sort(key=lambda e: -e[1])
        if cache is not None:
            self._save(cache, key)

    def _load(self, cache: Path, key: str) -> bool:
        try:
            c = json.loads(cache.read_text(encoding="utf-8"))
            if c.get("key") != key:
                return False
            self.top = {k: v for k, v in c["top"].items()}
            self.groups = {k: [tuple(e) for e in v] for k, v in c["groups"].items()}
            self.errors = c.get("errors", {})
            return True
        except (OSError, ValueError, KeyError):
            return False

    def _save(self, cache: Path, key: str) -> None:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"key": key, "top": self.top, "groups": self.groups, "errors": self.errors}), encoding="utf-8")
        except OSError:
            pass

    def candidates(self, path: str, definers_only: bool = False) -> list[Path]:
        """Packages that can hold the object, the one with the most objects in its group first."""
        parts = [p.lower() for p in re.split(r"[.:]", path) if p]
        if not parts:
            return []
        if len(parts) >= 2 and f"{parts[0]}.{parts[1]}" in self.groups:
            entries = self.groups[f"{parts[0]}.{parts[1]}"]
            if definers_only:
                entries = [e for e in entries if e[1] * 2 >= entries[0][1]]
            return [self.files[i] for i, _ in entries]
        return [self.files[i] for i in sorted(self.top.get(parts[0], ()))]

    def package(self, f: Path) -> upk.Package:
        if f in self._open:
            self._open[f] = self._open.pop(f)  # most recently used goes last
            return self._open[f]
        if len(self._open) >= OPEN_PACKAGES:
            self._open.pop(next(iter(self._open)))
        pkg = self._open[f] = upk.open_package(f)
        return pkg

    def get(self, path: str) -> tuple[upk.Package, int] | None:
        t0 = time.time()
        found = None
        cands = self.candidates(path)
        for f in cands:
            try:
                pkg = self.package(f)
            except Exception:  # noqa: BLE001
                continue
            idx = pkg.find(path)
            if idx:
                found = (pkg, idx)
                break
        took = time.time() - t0
        if took > 2.0 and len(self.slow) < 40:
            self.slow.append({"path": path, "seconds": round(took, 1), "candidates": len(cands)})
        return found

    def props(self, path: str) -> dict | None:
        if path in self._props:
            return self._props[path]
        if self.deadline is not None and time.process_time() > self.deadline:
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
        for f in self.candidates(path, definers_only=True):
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
