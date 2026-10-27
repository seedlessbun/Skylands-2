"""Turn a Borderlands 2 gun (its picked parts) into meshes: the "native" source for `models.GunModels`.

For each part of a built gun: find its mesh object, read the geometry (gunmesh), place it on the body at the socket the
part names, work out which way the barrel points, and pick the diffuse texture of its material.
Everything is best effort and logged; a part that cannot be read is skipped, a gun with no readable part returns None.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from .. import meshes as M
from . import gunmesh, upk

MESH_INDEX_VERSION = 3  # the saved mesh locations are only used when written by this version of the search
MESH_KEYS = ("GestaltModeSkeletalMeshName", "Mesh", "SkeletalMesh", "StaticMesh", "GearModel", "Model", "WeaponMesh")
WEAPON_PACKAGES = re.compile(r"(wpn|weapon|weap_|pistol|smg|shotgun|sniper|launcher|assault|rifle|gun)", re.I)
SLOT_ORDER = ("Body", "Barrel", "Grip", "Stock", "Sight", "Magazine", "Accessory", "Material", "Elemental")


def _strings(value, out: list[str], depth: int = 0) -> None:
    if depth > 4:
        return
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _strings(v, out, depth + 1)
    elif isinstance(value, list):
        for v in value:
            _strings(v, out, depth + 1)


class Bl2Source:
    def __init__(self, ix, say, tfc_dir=None, attach: str = "auto") -> None:
        self.attach = attach  # "sockets": move each part to its socket on the body; "none": parts share the weapon's space; "auto": guess
        self.ix = ix
        self.say = say
        self.tfc_dir = tfc_dir or ix.root
        self.cache: dict[str, dict | None] = {}
        self.textures: dict[str, bytes] = {}
        self.stats = {"parts": 0, "meshes": 0, "no_mesh": 0, "no_geometry": 0, "textured": 0}
        self.logged = 0
        self._beat = time.time()
        self.index_ready = False
        self.part_limit = float("inf")
        self.located: dict[str, Path] = {}  # object path -> the package it was found in
        self.mesh_index: dict[str, tuple[Path, str]] = {}  # wanted mesh name -> (package, object path)
        self.prof: dict[str, float] = {}
        self._meshes_by_name: dict[str, list[str]] | None = None
        self.name_files: dict[str, list] | None = None  # lower-case mesh name -> packages whose name table holds it
        self.by_gestalt: dict[str, str | None] = {}
        self.deadline = time.time() + 10 * 60  # then the remaining guns fall back to the next method

    def log(self, msg: str, force: bool = False) -> None:
        if force or self.logged < 40:
            self.logged += 1
            self.say(f"  native: {msg}")

    # --- one part
    def mesh_path(self, part: str) -> str | None:
        props = self.ix.props(part) or {}
        cands: list[str] = []
        for key in MESH_KEYS:
            if key in props:
                _strings(props[key], cands)
        for key, v in props.items():
            if key not in MESH_KEYS:
                _strings(v, cands)
        for name in self.gestalt_names(part):  # the located real mesh first: no package hunting
            if name in self.mesh_index:
                return self._by_gestalt(part)
        if self.index_ready:  # every package that names a wanted mesh has been opened: nothing more to find by path
            return self._stand_in(part)
        seen = []
        for c in cands:
            if "." in c and " " not in c and c not in seen and len(c) < 200:
                seen.append(c)
        for c in seen[:6]:
            if time.time() > self.part_limit:
                return None
            found = self.ix.get(c)
            if found and found[0].obj_class(found[1]) in gunmesh.MESH_CLASSES:
                return c
        for c in self.derived_paths(part):
            found = self.ix.get(c)
            if found and found[0].obj_class(found[1]) in gunmesh.MESH_CLASSES:
                return c
        t1 = time.time()
        r = self._by_gestalt(part) or self._stand_in(part)
        self.prof["lookup_s"] = self.prof.get("lookup_s", 0) + time.time() - t1
        return r

    def derived_paths(self, part: str) -> list[str]:
        """GD_Weap_Pistol.Barrel.Pistol_Barrel_Bandit -> Weap_Pistol.Barrel.<gestalt name or the part's own name>: this is where
        the game keeps the meshes of its weapon parts (seen in the real files: Weap_SMG.Stock.SMG_Stock_Maliwan)."""
        segs = part.split(".")
        if len(segs) < 3 or not segs[0].lower().startswith("gd_weap"):
            return []
        pkg, group = segs[0][3:], segs[1]
        names = [*self.gestalt_names(part), re.split(r"[.:]", segs[-1])[-1].lower()]
        out = []
        for n in dict.fromkeys(names):
            out.append(f"{pkg}.{group}.{n}")
        return out

    # --- Borderlands 2 "gestalt" parts: the mesh is named by a plain name, not referenced as an object
    def gestalt_names(self, part: str) -> list[str]:
        props = self.ix.props(part) or {}
        out: list[str] = []
        v = props.get("GestaltModeSkeletalMeshName")
        found: list[str] = []
        _strings(v, found)
        for f in found:
            leaf = re.split(r"[.:]", f.strip())[-1].strip().lower()
            if leaf and leaf not in out and leaf != "none":
                out.append(leaf)
        return out

    def prepare(self, parts: list[str]) -> None:
        """One pass over every package's name table to learn which packages hold the meshes the parts name."""
        t0 = time.time()
        wanted: set[str] = set()
        for part in parts:
            wanted.update(self.gestalt_names(part))
        self.name_files = {}
        if not wanted:
            self.log(f"none of the {len(parts)} parts names a mesh (GestaltModeSkeletalMeshName)", force=True)
            return
        n = 0
        for f in self.ix.files:
            try:
                names = upk.read_name_set(f)
            except Exception:  # noqa: BLE001
                continue
            for hit in wanted & names:
                self.name_files.setdefault(hit, []).append(f)
            n += 1
            if n % 400 == 0:
                self.log(f"scanned {n}/{len(self.ix.files)} package name tables ({time.time() - t0:.0f} s)", force=True)
        self.log(f"{len(wanted)} mesh names wanted; {sum(1 for w in wanted if w in self.name_files)} found in a package name table "
                 f"({time.time() - t0:.0f} s); sample {sorted(wanted)[:5]}", force=True)
        self._index_meshes(wanted)
        self.index_ready = True

    def _index_meshes(self, wanted: set[str]) -> None:
        """Each level package holds only the weapon meshes that level uses, so one gun's parts are spread over many packages.
        Open the packages whose name tables mention a wanted mesh (smallest first) once each and note where every wanted mesh
        really is. The result is saved, so the next install skips this."""
        cache = None
        if getattr(self.ix, "cache_path", None):
            cache = Path(self.ix.cache_path).with_name("gun_mesh_index.json")
            try:
                saved = json.loads(cache.read_text(encoding="utf-8"))
                if saved.get("key") == self.ix.key and saved.get("wanted", 0) >= len(wanted) and saved.get("v") == MESH_INDEX_VERSION:
                    for name, (rel, path) in saved["found"].items():
                        f = self.ix.root / rel
                        if f.is_file():
                            self.mesh_index[name] = (f, path)
                    self.log(f"mesh locations: {len(self.mesh_index)} of {len(wanted)} from the saved list", force=True)
                    return
            except (OSError, ValueError, KeyError):
                pass
        t0 = time.time()
        files: dict[Path, int] = {}
        for n in wanted:
            for f in (self.name_files or {}).get(n, []):
                files[f] = files.get(f, 0) + 1
        order = sorted(files, key=lambda f: (f.stat().st_size, f.name))
        self.log(f"looking for the real meshes in {len(order)} packages", force=True)
        left = set(wanted)
        unreadable: list[str] = []
        for k, f in enumerate(order):
            if not left or time.time() - t0 > 480:
                break
            if k % 10 == 0:
                self.log(f"opened {k}/{len(order)} packages, {len(self.mesh_index)} of {len(wanted)} meshes located ({time.time() - t0:.0f} s)", force=True)
            try:
                pkg = self.ix.package(f)
                pkg._indexes()  # noqa: SLF001
            except Exception as e:  # noqa: BLE001
                unreadable.append(f"{f.name}: {type(e).__name__}: {str(e)[:70]}")
                continue
            for name in list(left):
                for i in pkg._by_name.get(name, ()):  # noqa: SLF001
                    if pkg.obj_class(i) in gunmesh.MESH_CLASSES:
                        self.mesh_index[name] = (f, pkg.path_of(i))
                        left.discard(name)
                        break
        self.log(f"{len(self.mesh_index)} of {len(wanted)} meshes located in {time.time() - t0:.0f} s; "
                 f"never found: {sorted(left)[:12]}{'...' if len(left) > 12 else ''}", force=True)
        if unreadable:
            self.log(f"{len(unreadable)} of those packages could not be opened: {unreadable[:6]}", force=True)
        if left:  # every name, so a gun type whose meshes are all missing can be told apart (a type's name appears in its parts)
            by_prefix: dict[str, list[str]] = {}
            for n in sorted(left):
                by_prefix.setdefault(n.split("_")[0], []).append(n)
            self.log("never found, by prefix: " + "; ".join(f"{k} ({len(v)}): {v[:6]}" for k, v in sorted(by_prefix.items())), force=True)
        if left:
            try:
                self._fuzzy_meshes(left)
            except Exception as e:  # noqa: BLE001 - a guess at best: never stop the install
                self.log(f"fuzzy mesh search failed: {type(e).__name__}: {str(e)[:100]}", force=True)
        if cache is not None and (not left or time.time() - t0 <= 480):
            try:
                cache.write_text(json.dumps({"key": self.ix.key, "wanted": len(wanted), "v": MESH_INDEX_VERSION,
                                             "found": {n: [str(f.relative_to(self.ix.root)), p] for n, (f, p) in self.mesh_index.items()}}),
                                 encoding="utf-8")
            except OSError:
                pass

    ALIASES = {"sg": ("shotgun", "shotguns", "sg"), "smg": ("smg", "smgs"), "pistol": ("pistol", "pistols"), "ar": ("assaultrifle", "ar", "rifle"),
               "sr": ("sniper", "sniperrifle", "sr"), "l": ("launcher", "launchers", "rocketlauncher")}

    def _fuzzy_meshes(self, left: set[str]) -> None:
        """Meshes whose exact name was never found: the files may name them differently (Shotgun_Body_Bandit for SG_Body_Bandit). Look through
        every package's name table for names of the same gun type, slot and manufacturer under another prefix, open those packages and take the
        mesh exports. Everything seen is logged, so the next log shows what the files really call these meshes."""
        t0 = time.time()
        # (alias prefix, tail) -> the wanted names of THAT gun type only: a pistol's magazine must never become a shotgun's (0.33.0 mixed the types)
        by_alias: dict[tuple[str, str], list[str]] = {}
        for n in left:
            pre, _, tail = n.partition("_")
            for alias in self.ALIASES.get(pre, ()):
                if alias != pre and tail:
                    by_alias.setdefault((alias, tail), []).append(n)
        if not by_alias:
            return
        aliases = {a for a, _ in by_alias}
        wanted_tail = {t: [] for _, t in by_alias}
        hit_files: dict[Path, set[str]] = {}
        similar: set[str] = set()
        for f in self.ix.files:
            try:
                names = upk.read_name_set(f)
            except Exception:  # noqa: BLE001
                continue
            near = {n for n in names if (n.partition("_")[0], n.partition("_")[2]) in by_alias}
            for n in names:  # what the files call things of these gun types at all, for the log
                if n.partition("_")[0] in aliases and re.search(r"(body|barrel|grip|stock|mag|sight|receiver)", n) and len(similar) < 60:
                    similar.add(n)
            if near:
                hit_files[f] = near
        self.log(f"fuzzy search: {len(hit_files)} packages hold names like a missing mesh's under another prefix "
                 f"({time.time() - t0:.0f} s); sample {[(f.stem, sorted(v)[:3]) for f, v in list(hit_files.items())[:4]]}", force=True)
        self.log(f"fuzzy search: names of these gun types that look like parts: {sorted(similar)[:40]}", force=True)
        weapon_groups = sorted(k for k in self.ix.groups if re.search(r"shotgun|weap_sg|^sg_", k))[:30]
        self.log(f"fuzzy search: package groups named for shotguns: {weapon_groups}; packages the index could not read: {sorted(self.ix.errors)[:12]}", force=True)
        found = 0
        for f in sorted(hit_files, key=lambda f: (f.stat().st_size, f.name))[:80]:
            if time.time() - t0 > 240:
                break
            try:
                pkg = self.ix.package(f)
                pkg._indexes()  # noqa: SLF001
            except Exception as e:  # noqa: BLE001
                self.log(f"fuzzy search: {f.name} cannot be opened: {type(e).__name__}: {str(e)[:60]}", force=True)
                continue
            for nm in hit_files[f]:
                for i in pkg._by_name.get(nm, ()):  # noqa: SLF001
                    if pkg.obj_class(i) not in gunmesh.MESH_CLASSES:
                        continue
                    for w in by_alias.get((nm.partition("_")[0], nm.partition("_")[2]), []):
                        if w in left:
                            self.mesh_index[w] = (f, pkg.path_of(i))
                            left.discard(w)
                            found += 1
        self.log(f"fuzzy search: {found} more meshes located; still missing {len(left)}", force=True)

    def _by_gestalt(self, part: str) -> str | None:
        if part in self.by_gestalt:
            return self.by_gestalt[part]
        result = None
        for name in self.gestalt_names(part):
            if name in self.mesh_index:
                self.located[self.mesh_index[name][1]] = self.mesh_index[name][0]
                result = self.mesh_index[name][1]
                break
        if result is None and self.name_files is not None and not self.index_ready:
            for name in self.gestalt_names(part):
                result = self._find_export(name)
                if result:
                    break
        self.by_gestalt[part] = result
        return result

    def _find_export(self, name: str) -> str | None:
        files = sorted(self.name_files.get(name, []), key=lambda f: (0 if "startup" in f.stem.lower() else 1, f.stat().st_size))
        t0 = time.time()
        for f in files[:30]:
            if time.time() - t0 > 15 or time.time() > self.part_limit:  # some packages are huge: never let one part eat the budget
                self.prof["gave_up"] = self.prof.get("gave_up", 0) + 1
                break
            try:
                pkg = self.ix.package(f)
                pkg._indexes()  # noqa: SLF001
            except Exception:  # noqa: BLE001
                continue
            for i in pkg._by_name.get(name, ()):  # noqa: SLF001
                if pkg.obj_class(i) in gunmesh.MESH_CLASSES:
                    return pkg.path_of(i)
            for k, imp in enumerate(pkg.imports):  # a package that only uses the mesh still names where it lives
                if imp.name.lower() == name and imp.class_name in gunmesh.MESH_CLASSES:
                    path = pkg.path_of(-(k + 1))
                    if self.ix.get(path):
                        return path
        return None

    SLOTS_WITH_STAND_INS = ("body", "barrel", "grip", "stock")

    def _stand_in(self, part: str) -> str | None:
        """Most manufacturers' meshes are not in the game's files at all (a level package holds only the meshes it uses). A part
        whose own mesh is missing borrows the closest real one of the same gun type and slot (same manufacturer first), so every
        gun still gets a real Borderlands 2 body instead of the crossbow."""
        segs = part.split(".")
        if len(segs) < 3 or segs[1].lower() not in self.SLOTS_WITH_STAND_INS or not segs[0].lower().startswith("gd_weap"):
            return None
        kind, slot = segs[0][3:].lower().rstrip("s"), segs[1].lower()
        pool = []
        for name, (f, path) in sorted(self.mesh_index.items()):
            ps = path.split(".")
            if len(ps) >= 3 and ps[0].lower().rstrip("s") == kind and ps[1].lower() == slot:
                pool.append((name, f, path))
        if not pool:
            return None
        token = re.split(r"[_.]", segs[-1].lower())
        mfr = next((t for t in reversed(token) if t in ("bandit", "dahl", "hyperion", "jakobs", "maliwan", "tediore", "torgue", "vladof")), "")
        pick = next((p for p in pool if mfr and mfr in p[0]), pool[0])
        self.located[pick[2]] = pick[1]
        self.stats["stand_ins"] = self.stats.get("stand_ins", 0) + 1
        return pick[2]

    def _mesh_by_name_build(self) -> None:
        if self._meshes_by_name is None:
            t0 = time.time()
            names: dict[str, list[str]] = {}
            n = 0
            for f in self.ix.files:
                if not WEAPON_PACKAGES.search(f.stem) or f.stem.lower().startswith(("gd_", "d_")) or n >= 60:
                    continue
                if time.time() - t0 > 25:  # a guess at best: never hold the install up for it
                    self.log("name fallback: stopped after 25 s", force=True)
                    break
                n += 1
                if n % 10 == 1:
                    self.log(f"name fallback: indexing weapon package {n} ({f.stem}), {time.time() - t0:.0f} s so far", force=True)
                try:
                    pkg = self.ix.package(f)
                except Exception:  # noqa: BLE001
                    continue
                for i in range(1, len(pkg.exports) + 1):
                    if pkg.obj_class(i) in gunmesh.MESH_CLASSES:
                        names.setdefault(pkg.obj_name(i).lower(), []).append(pkg.path_of(i))
            self._meshes_by_name = names
            self.log(f"indexed {sum(len(v) for v in names.values())} meshes in {n} weapon packages by name ({time.time() - t0:.0f} s)", force=True)

    def _mesh_by_name(self, part: str) -> str | None:
        """Fallback: a mesh whose name matches the part's, among the packages that look like weapon assets."""
        self._mesh_by_name_build()
        leaf = part.split(".")[-1].split(":")[-1].lower()
        if leaf in self._meshes_by_name:
            return self._meshes_by_name[leaf][0]
        if len(leaf) >= 8:
            for name, paths in self._meshes_by_name.items():
                if len(name) >= 8 and (leaf in name or name in leaf):
                    return paths[0]
        return None

    def diagnose(self, part: str) -> str:
        """Where the mesh a part names does exist (path and class of every export of that name), for the log."""
        out = []
        for name in self.gestalt_names(part)[:2]:
            files = (self.name_files or {}).get(name, [])
            out.append(f"{name}: in {len(files)} name tables")
            for f in files[:6]:
                try:
                    pkg = self.ix.package(f)
                    pkg._indexes()  # noqa: SLF001
                    hits = [(pkg.path_of(i), pkg.obj_class(i)) for i in pkg._by_name.get(name, ())][:3]  # noqa: SLF001
                    hits += [("import " + pkg.path_of(-(k + 1)), imp.class_name) for k, imp in enumerate(pkg.imports)
                             if imp.name.lower() == name][:3]
                except Exception as e:  # noqa: BLE001
                    hits = [f"{type(e).__name__}: {str(e)[:60]}"]
                out.append(f"{f.stem} ({f.stat().st_size // 1048576} MB): {hits}")
        return "; ".join(out)

    def describe(self, part: str) -> str:
        """What a part's properties hold, for the log when no mesh could be found from them."""
        props = self.ix.props(part)
        if props is None:
            return "properties could not be read"
        vals: list[str] = []
        for key, v in props.items():
            found: list[str] = []
            _strings(v, found)
            vals += [f"{key}={f[:70]}" for f in found[:2]]
        return f"keys {sorted(props)[:30]}; values {vals[:10]}"

    def group_hint(self) -> None:
        """Once: which package groups look like weapon assets (their names tell where the meshes live)."""
        if getattr(self, "_hinted", False):
            return
        self._hinted = True
        keys = [k for k in self.ix.groups if re.search(r"(pistol|smg|shotgun|sniper|launcher|assault|rifle|weap|wpn|gun)", k) and not k.startswith(("gd_", "d_"))]
        self.log(f"{len(keys)} package groups look like weapon assets, e.g. {sorted(keys)[:14]}", force=True)

    def part_data(self, part: str) -> dict | None:
        if part in self.cache:
            return self.cache[part]
        if time.time() > self.deadline:
            self.log("time budget for reading meshes used up", force=self.logged < 41)
            return None
        self.stats["parts"] += 1
        self.group_hint()
        result = None
        t0 = time.time()
        self.part_limit = t0 + 25
        try:
            result = self._read_part(part)
        except Exception as e:  # noqa: BLE001
            self.log(f"{part}: {type(e).__name__}: {e}")
        took = time.time() - t0
        self.prof["parts_s"] = self.prof.get("parts_s", 0) + took
        if took > 5:
            self.log(f"{part}: took {took:.0f} s", force=True)
        if time.time() - self._beat > 10:  # the log goes quiet after the first lines; this shows the install is still working
            self._beat = time.time()
            self.log(f"still working: {self.stats['parts']} parts looked at, {self.stats['meshes']} meshes read, "
                     f"{self.stats['textured']} textures, {self.stats['no_mesh']} without a mesh, "
                     f"{int(self.deadline - time.time())} s of budget left; seconds spent {({k: int(v) for k, v in self.prof.items()})}", force=True)
        self.cache[part] = result
        return result

    def _read_part(self, part: str) -> dict | None:
        path = self.mesh_path(part)
        if not path:
            self.stats["no_mesh"] += 1
            kind = part.split(".")[0].lower()
            seen = self.stats.setdefault("no_mesh_kinds", {})
            seen[kind] = seen.get(kind, 0) + 1
            if seen[kind] <= 2:  # the first two of each gun type, whatever the log's throttle says
                self.log(f"{part}: no mesh ({kind}, number {seen[kind]}); " + self.describe(part) + "; " + self.diagnose(part), force=True)
            self.log(f"{part}: no mesh object found; " + self.describe(part), force=self.stats["no_mesh"] <= 3)
            if self.stats["no_mesh"] <= 10:
                self.log(f"  where the named mesh is: {self.diagnose(part)}", force=True)
            return None
        t1 = time.time()
        if path in self.located:
            pkg = self.ix.package(self.located[path])
            idx = pkg.find(path)
        else:
            pkg, idx = self.ix.get(path)
        data = pkg.export_data(idx)
        self.prof["open_export_s"] = self.prof.get("open_export_s", 0) + time.time() - t1
        props_end = None
        for start in (4, 0, 8):
            try:
                _p, props_end = upk.read_properties(pkg, data, start)
                break
            except (upk.UPKError, Exception):  # noqa: BLE001
                continue
        if props_end is None:
            props_end = 4
        raw = gunmesh.read_mesh_blob(data, props_end, path)
        if raw is None:
            self.stats["no_geometry"] += 1
            self.log(f"{path}: could not find geometry ({len(data)} bytes)")
            return None
        self.stats["meshes"] += 1
        self.log(raw.note)
        sockets = self._sockets(pkg, path)
        mats = gunmesh.material_refs(pkg, data, props_end)  # looked up only if the body needs its own texture (see gun_parts)
        key = None  # the gun's Material part supplies the texture; reading every part's material cost minutes and went unused
        raw.mesh.texture = key
        raw.mesh.normal_map = "flat_n"
        return {"mesh": raw.mesh, "sockets": sockets, "path": path, "texture": key, "mats": mats}

    def _sockets(self, pkg: upk.Package, mesh_path: str) -> dict[str, tuple[float, float, float]]:
        out: dict[str, tuple[float, float, float]] = {}
        for i in pkg.children_of(mesh_path):
            if "Socket" not in pkg.obj_class(i):
                continue
            try:
                p = upk.object_properties(pkg, i)
            except Exception:  # noqa: BLE001
                continue
            loc = p.get("RelativeLocation")
            name = p.get("SocketName") or pkg.obj_name(i)
            if isinstance(loc, list) and len(loc) == 3:
                out[str(name).lower()] = (float(loc[0]), float(loc[1]), float(loc[2]))
        return out

    def _texture(self, path: str) -> str | None:
        key = "t_" + hashlib.sha1(path.lower().encode()).hexdigest()[:8]
        if key in self.textures:
            return key
        if self.prof.get("texture_s", 0) > 150:  # textures are the slow part: past this the rest of the guns get a plain colour
            if not self.prof.get("texture_stop"):
                self.prof["texture_stop"] = 1
                self.log("texture time budget used up; remaining guns are not textured", force=True)
            return None
        t0 = time.time()
        dds = gunmesh.read_texture(self.ix, path, self.tfc_dir, self.log)
        spent = time.time() - t0
        self.prof["texture_s"] = self.prof.get("texture_s", 0) + spent
        if spent > 10:
            self.log(f"texture {path} took {spent:.0f} s", force=True)
        if dds is None:
            return None
        self.textures[key] = dds
        self.stats["textured"] += 1
        return key

    # --- one gun
    def gun_parts(self, g: dict, built: dict) -> list[M.Mesh] | None:
        picked = built.get("parts", {})
        slots = {slot: self.part_data(path) for slot, path in picked.items() if path}
        slots = {k: v for k, v in slots.items() if v}
        if not slots:
            return None
        body_slot = "Body"
        if "Body" not in slots:
            # No body mesh could be read. A gun with at least two readable parts takes its biggest part as the body (a shotgun's receiver may be named
            # otherwise or live where it cannot be read); a lone scope or stock is not a gun: leave it to the next method
            self.stats["no_body"] = self.stats.get("no_body", 0) + 1
            if len(slots) < 2:
                self.log(f"{g.get('balance', '?')}: no body mesh could be read (parts read: {sorted(slots)}); not building this gun")
                return None

            def volume(d):
                lo, hi = d["mesh"].bounds()
                return (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])

            body_slot = max(slots, key=lambda k: volume(slots[k]))
            self.log(f"{g.get('balance', '?')}: no Body part could be read (parts read: {sorted(slots)}); the biggest, {body_slot}, stands in for it")
        body = slots[body_slot]
        placed: dict[str, M.Mesh] = {}
        for slot, d in slots.items():
            offset = (0.0, 0.0, 0.0)
            if d is not body and self._use_sockets(d, body):
                offset = self._attach_offset(body, slot, picked.get(slot))
            placed[slot] = M.transformed(d["mesh"], None, 1.0, offset)
        matrix = orientation(placed)
        parts = [M.transformed(m, matrix, 1.0) for m in placed.values()]
        gun_texture = self._gun_material_texture(picked.get("Material"))
        if not gun_texture:  # no Material part: the body's own material stands in
            for mat in slots[body_slot].get("mats", [])[:3]:
                d, _n = gunmesh.pick_textures(gunmesh.texture_parameters(self.ix, mat))
                if d:
                    gun_texture = self._texture(d)
                    break
        if gun_texture:  # one material (a texture shared by every part, each part's UVs lie on it) covers the whole gun
            for m in parts:
                m.texture = gun_texture
        return parts

    def _gun_material_texture(self, material_part: str | None) -> str | None:
        """The diffuse texture of the gun's Material part (a manufacturer/rarity paint job: Common_GunMaterials...Mati_*)."""
        if not material_part or self.prof.get("material_s", 0) > 120:  # looking materials up is what ate the minutes
            return None
        t0 = time.time()
        try:
            return self._gun_material_texture_inner(material_part)
        finally:
            self.prof["material_s"] = self.prof.get("material_s", 0) + time.time() - t0

    def _gun_material_texture_inner(self, material_part: str) -> str | None:
        props = self.ix.props(material_part) or {}
        mic = props.get("Material")
        if not isinstance(mic, str):
            return None
        params = gunmesh.texture_parameters(self.ix, mic)
        diffuse, _normal = gunmesh.pick_textures(params)
        if not diffuse:
            self.log(f"material {mic}: no texture parameter ({sorted(params)[:6]})", force=self.stats["textured"] == 0 and self.logged < 80)
            return None
        key = self._texture(diffuse)
        if key is None:
            self.log(f"material {mic}: texture {diffuse} could not be decoded", force=self.logged < 80)
        return key

    def _use_sockets(self, part: dict, body: dict) -> bool:
        """Parts modelled around their own attach point need the socket offset; parts already placed in the weapon's space do not.
        In auto mode a part whose centre sits far from its own origin (relative to the body's size) is taken as already placed."""
        if self.attach == "sockets":
            return True
        if self.attach == "none":
            return False
        lo, hi = part["mesh"].bounds()
        blo, bhi = body["mesh"].bounds()
        size = max(bhi[i] - blo[i] for i in range(3)) or 1.0
        centre = [abs((lo[i] + hi[i]) / 2) for i in range(3)]
        return max(centre) <= 0.45 * size

    def _attach_offset(self, body: dict, slot: str, part_path: str | None) -> tuple[float, float, float]:
        props = (self.ix.props(part_path) or {}) if part_path else {}
        name = str(props.get("AttachmentPointName") or props.get("AttachPoint") or slot).lower()
        socks = body["sockets"]
        for key in (name, slot.lower()):
            if key in socks:
                return socks[key]
        return (0.0, 0.0, 0.0)

    def take_textures(self) -> dict[str, bytes]:
        out, self.textures = self.textures, {}
        return out

    def summary(self) -> str:
        s = self.stats
        errs = getattr(self.ix, "open_errors", {})
        extra = f"; {len(errs)} packages could not be opened, e.g. {dict(list(errs.items())[:3])}" if errs else ""
        return (f"native: {s['parts']} parts looked at, {s['meshes']} meshes read, {s['no_mesh']} without a mesh object, "
                f"{s['no_geometry']} whose geometry could not be found, {s['textured']} textures decoded, "
                f"{s.get('no_body', 0)} guns skipped for lacking a body mesh, {s.get('stand_ins', 0)} parts using another manufacturer's mesh; parts without a mesh by package {s.get('no_mesh_kinds', {})}{extra}")


def orientation(placed: dict[str, M.Mesh]) -> tuple[M.Vec, M.Vec, M.Vec]:
    """The matrix from the game's axes to the canonical gun frame (barrel +y, up +z, right +x).

    Barrel axis = the longest extent of the whole gun, pointing from the body towards the barrel part; up = the thinner of
    the other two axes, pointing away from the grip/magazine. UE3 is left-handed, so the right axis is the negated cross
    product, which also makes the winding flip in `meshes.transformed`.
    """
    pts = [p for m in placed.values() for p in m.positions]
    if not pts:
        return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    ext = [hi[i] - lo[i] for i in range(3)]
    fwd = max(range(3), key=lambda i: ext[i])
    centre_body = _centroid(placed.get("Body") or next(iter(placed.values())))
    sign = 1.0
    barrel = placed.get("Barrel")
    if barrel is not None:
        sign = 1.0 if _centroid(barrel)[fwd] >= centre_body[fwd] else -1.0
    else:
        mid = (lo[fwd] + hi[fwd]) / 2
        sign = 1.0 if centre_body[fwd] <= mid else -1.0
    others = [i for i in range(3) if i != fwd]
    up = 2 if 2 in others else min(others, key=lambda i: ext[i])
    usign = 1.0
    low = placed.get("Magazine") or placed.get("Grip")
    if low is not None and _centroid(low)[up] > centre_body[up] + 1e-6:
        usign = -1.0
    f = [0.0, 0.0, 0.0]
    f[fwd] = sign
    u = [0.0, 0.0, 0.0]
    u[up] = usign
    r = M.cross(tuple(f), tuple(u))  # type: ignore[arg-type]
    r = (-r[0], -r[1], -r[2])
    return tuple(tuple((r, f, u)[c][i] for c in range(3)) for i in range(3))  # type: ignore[return-value]


def _centroid(m: M.Mesh) -> M.Vec:
    n = max(1, len(m.positions))
    return (sum(p[0] for p in m.positions) / n, sum(p[1] for p in m.positions) / n, sum(p[2] for p in m.positions) / n)
