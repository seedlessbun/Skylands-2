"""Turn a Borderlands 2 gun (its picked parts) into meshes: the "native" source for `models.GunModels`.

For each part of a built gun: find its mesh object, read the geometry (gunmesh), place it on the body at the socket the
part names, work out which way the barrel points, and pick the diffuse texture of its material.
Everything is best effort and logged; a part that cannot be read is skipped, a gun with no readable part returns None.
"""

from __future__ import annotations

import hashlib
import time

from .. import meshes as M
from . import gunmesh, upk

MESH_KEYS = ("GestaltModeSkeletalMeshName", "Mesh", "SkeletalMesh", "StaticMesh", "GearModel", "Model", "WeaponMesh")
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
    def __init__(self, ix, say, tfc_dir=None) -> None:
        self.ix = ix
        self.say = say
        self.tfc_dir = tfc_dir or ix.root
        self.cache: dict[str, dict | None] = {}
        self.textures: dict[str, bytes] = {}
        self.stats = {"parts": 0, "meshes": 0, "no_mesh": 0, "no_geometry": 0, "textured": 0}
        self.logged = 0
        self.deadline = time.time() + 30 * 60  # then the remaining guns fall back to the next method

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
        seen = []
        for c in cands:
            if "." in c and " " not in c and c not in seen and len(c) < 200:
                seen.append(c)
        for c in seen[:14]:
            found = self.ix.get(c)
            if found and found[0].obj_class(found[1]) in gunmesh.MESH_CLASSES:
                return c
        return None

    def part_data(self, part: str) -> dict | None:
        if part in self.cache:
            return self.cache[part]
        if time.time() > self.deadline:
            self.log("time budget for reading meshes used up", force=self.logged < 41)
            return None
        self.stats["parts"] += 1
        result = None
        try:
            result = self._read_part(part)
        except Exception as e:  # noqa: BLE001
            self.log(f"{part}: {type(e).__name__}: {e}")
        self.cache[part] = result
        return result

    def _read_part(self, part: str) -> dict | None:
        path = self.mesh_path(part)
        if not path:
            self.stats["no_mesh"] += 1
            self.log(f"{part}: no mesh object found in its properties")
            return None
        pkg, idx = self.ix.get(path)
        data = pkg.export_data(idx)
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
        mats = gunmesh.material_refs(pkg, data, props_end)
        diffuse = None
        for mat in mats:
            d, _n = gunmesh.pick_textures(gunmesh.texture_parameters(self.ix, mat))
            if d:
                diffuse = d
                break
        key = self._texture(diffuse) if diffuse else None
        raw.mesh.texture = key
        raw.mesh.normal_map = "flat_n"
        return {"mesh": raw.mesh, "sockets": sockets, "path": path, "texture": key}

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
        dds = gunmesh.read_texture(self.ix, path, self.tfc_dir, self.log)
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
        body = slots.get("Body") or next(iter(slots.values()))
        placed: dict[str, M.Mesh] = {}
        for slot, d in slots.items():
            offset = (0.0, 0.0, 0.0)
            if d is not body:
                offset = self._attach_offset(body, slot, picked.get(slot))
            placed[slot] = M.transformed(d["mesh"], None, 1.0, offset)
        matrix = orientation(placed)
        parts = [M.transformed(m, matrix, 1.0) for m in placed.values()]
        return parts

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
        return (f"native: {s['parts']} parts looked at, {s['meshes']} meshes read, {s['no_mesh']} without a mesh object, "
                f"{s['no_geometry']} whose geometry could not be found, {s['textured']} textures decoded")


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
