"""Gun models for the Skylands weapons.

Every Skylands gun is a copy of the vanilla crossbow. This module makes each gun its own mesh. There are several ways to
get the geometry (`method`), all ending in the same Skyrim-side steps: fit the mesh to the vanilla crossbow's axes and size,
write the NIF (lit shapes, textures, box collision) and the textures under Meshes/Skylands/Guns and Textures/Skylands/Guns.

  proxy    stylised guns built from boxes and cylinders (colour from the manufacturer; always works)
  native   Borderlands 2 part meshes read straight from the game's packages (bl2/meshes.py)
  umodel   Borderlands 2 part meshes exported by UModel and read back (bl2/umodel.py)
  auto     native, then umodel, then proxy, per gun

Nothing here may stop an install: any failure leaves that gun on the vanilla mesh and says why in the log.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from . import meshes as M
from .skyrim import nif, nifread

METHODS = ("off", "proxy", "native", "umodel", "auto")
MESH_DIR = "Skylands\\Guns"  # under Meshes\
TEX_DIR = "textures\\skylands\\guns"
HAVOK_SCALE = 69.99125  # skyrim units per havok unit

# length of each gun type in Skyrim units (a hand is about 8, a dagger about 35): the in-game test showed a pistol sized
# as a fraction of the crossbow came out far too big next to the player
LENGTH = {"pistol": 16.0, "smg": 24.0, "assault_rifle": 34.0, "shotgun": 34.0, "sniper": 42.0, "launcher": 36.0}

PALETTE = {  # body colour, trim colour per manufacturer
    "Bandit": ((120, 78, 52), (70, 56, 48)),
    "Dahl": ((82, 92, 62), (45, 48, 40)),
    "Hyperion": ((232, 196, 36), (36, 36, 40)),
    "Jakobs": ((98, 62, 36), (150, 150, 156)),
    "Maliwan": ((226, 228, 234), (70, 150, 220)),
    "Tediore": ((196, 188, 168), (60, 90, 140)),
    "Torgue": ((226, 112, 28), (60, 40, 30)),
    "Vladof": ((150, 34, 30), (30, 30, 34)),
}
STEEL = (88, 90, 96)


@dataclass
class Fit:
    matrix: tuple[M.Vec, M.Vec, M.Vec]  # canonical gun (barrel +y, up +z, right +x) -> the vanilla weapon's axes
    length: float  # the vanilla weapon's length (skyrim units)
    note: str


IDENTITY: tuple[M.Vec, M.Vec, M.Vec] = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def fit_from_points(points: list[M.Vec]) -> Fit:
    """Work out the vanilla weapon's barrel axis (longest extent, pointing away from the origin/grip), its up axis (the
    thinnest of the others) and its length."""
    if len(points) < 4:
        return Fit(IDENTITY, 50.0, "no vanilla mesh: assuming barrel +y, up +z, 50 long")
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    ext = [hi[i] - lo[i] for i in range(3)]
    fwd = max(range(3), key=lambda i: ext[i])
    others = [i for i in range(3) if i != fwd]
    up = min(others, key=lambda i: ext[i])
    centre = (lo[fwd] + hi[fwd]) / 2
    sign = 1.0 if centre >= 0 else -1.0
    f = [0.0, 0.0, 0.0]
    f[fwd] = sign
    u = [0.0, 0.0, 0.0]
    u[up] = 1.0
    r = M.cross(tuple(f), tuple(u))  # type: ignore[arg-type]
    # p' = x * right + y * forward + z * up, so those are the columns
    rows = tuple(tuple((r, f, u)[c][i] for c in range(3)) for i in range(3))
    return Fit(rows, ext[fwd], f"vanilla length {ext[fwd]:.1f} along axis {'xyz'[fwd]}{'+' if sign > 0 else '-'}, up axis {'xyz'[up]}")  # type: ignore[arg-type]


def find_vanilla_mesh(data_dir: Path, modl: bytes | None, say=None) -> bytes | None:
    """The vanilla crossbow's NIF: a loose file in Data\\Meshes, or inside one of Skyrim's archives (an exact path first, then
    the nearest thing named like a crossbow). Says what it did, because a miss means the fit falls back to guessed axes."""
    log = say or (lambda _m: None)
    if not modl:
        log("vanilla crossbow mesh: the crossbow record has no model path")
        return None
    rel = modl.split(b"\0")[0].decode("cp1252", "replace").replace("/", "\\").lstrip("\\")
    loose = Path(data_dir) / "Meshes" / Path(*rel.split("\\"))
    if loose.is_file():
        log(f"vanilla crossbow mesh: {rel} (loose file)")
        return loose.read_bytes()
    from .skyrim import bsa

    inner = "meshes\\" + rel.lower()
    opened, failed, near = 0, [], []
    for archive in sorted(Path(data_dir).glob("*.bsa")):
        try:
            a = bsa.BSA(archive)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{archive.name}: {type(e).__name__}")
            continue
        opened += 1
        if inner in a.entries:
            try:
                data = a.read(inner)
                log(f"vanilla crossbow mesh: {rel} (in {archive.name})")
                return data
            except Exception as e:  # noqa: BLE001
                failed.append(f"{archive.name} read: {type(e).__name__}: {e}")
        for name in a.entries:
            if "crossbow" in name and name.endswith(".nif") and not any(k in name for k in ("1stperson", "firstperson", "bolt", "skin", "dlc02", "_fp")):
                near.append((archive, name))
    if near:
        near.sort(key=lambda t: (0 if "weapons" in t[1] else 1, len(t[1])))
        archive, name = near[0]
        try:
            data = bsa.BSA(archive).read(name)
            log(f"vanilla crossbow mesh: {rel} not found; using {name} from {archive.name}")
            return data
        except Exception as e:  # noqa: BLE001
            failed.append(f"{archive.name} read {name}: {type(e).__name__}: {e}")
    log(f"vanilla crossbow mesh: {rel} not found ({opened} archives searched, unreadable: {failed[:4] or 'none'})")
    return None


def describe_nif(data: bytes) -> str:
    """For the log: what is in the vanilla crossbow's NIF and why its shapes could not be measured."""
    try:
        blocks = nifread.blocks(data)
    except Exception as e:  # noqa: BLE001
        return f"unreadable ({type(e).__name__}: {e})"
    kinds: dict[str, int] = {}
    for k, _b in blocks:
        kinds[k] = kinds.get(k, 0) + 1
    errors = []
    for k, b in blocks:
        if k in ("BSTriShape", "BSSubIndexTriShape", "BSMeshLODTriShape", "BSDynamicTriShape"):
            try:
                nifread.read_shape(b)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{k}: {type(e).__name__}: {e}")
    return f"{len(blocks)} blocks {dict(sorted(kinds.items()))}; shape errors {errors[:3] or 'none'}"


def fit_mesh(m: M.Mesh, fit: Fit, scale: float) -> M.Mesh:
    return M.transformed(m, fit.matrix, scale)


# ---- proxy guns -----------------------------------------------------------------------------------------------------

def proxy_parts(gun_type: str, manufacturer: str, accent: tuple[int, int, int]) -> list[M.Mesh]:
    """A stylised gun in the canonical frame (barrel +y, up +z), length 1.0, grip at the origin."""
    body, trim = PALETTE.get(manufacturer, ((120, 120, 124), (60, 60, 64)))
    body_t, trim_t, steel_t, accent_t = (f"c_{c[0]:02x}{c[1]:02x}{c[2]:02x}" for c in (body, trim, STEEL, accent))
    L = 1.0
    out: list[M.Mesh] = []

    def add(m: M.Mesh, key: str) -> None:
        m.texture = key
        m.normal_map = "flat_n"
        out.append(m)

    if gun_type == "pistol":
        add(M.box(0, 0.30 * L, 0.05 * L, 0.10 * L, 0.80 * L, 0.16 * L), body_t)
        add(M.box(0, -0.04 * L, -0.15 * L, 0.09 * L, 0.18 * L, 0.30 * L), trim_t)  # grip
        add(M.cylinder(0, 0.62 * L, 0.05 * L, 0.035 * L, 0.34 * L), steel_t)
        add(M.box(0, 0.36 * L, 0.17 * L, 0.04 * L, 0.34 * L, 0.05 * L), accent_t)  # sight rail
    elif gun_type == "smg":
        add(M.box(0, 0.30 * L, 0.04 * L, 0.10 * L, 0.65 * L, 0.18 * L), body_t)
        add(M.box(0, -0.02 * L, -0.20 * L, 0.08 * L, 0.16 * L, 0.36 * L), trim_t)
        add(M.box(0, 0.30 * L, -0.27 * L, 0.07 * L, 0.12 * L, 0.34 * L), steel_t)  # magazine
        add(M.cylinder(0, 0.78 * L, 0.05 * L, 0.03 * L, 0.34 * L), steel_t)
        add(M.box(0, -0.30 * L, 0.02 * L, 0.06 * L, 0.34 * L, 0.10 * L), trim_t)  # stock
        add(M.box(0, 0.30 * L, 0.17 * L, 0.04 * L, 0.40 * L, 0.04 * L), accent_t)
    elif gun_type == "shotgun":
        add(M.box(0, 0.10 * L, 0.03 * L, 0.11 * L, 0.34 * L, 0.18 * L), body_t)
        add(M.cylinder(0, 0.62 * L, 0.06 * L, 0.035 * L, 0.78 * L), steel_t)  # barrel
        add(M.cylinder(0, 0.52 * L, -0.01 * L, 0.04 * L, 0.46 * L), trim_t)  # pump
        add(M.box(0, -0.30 * L, -0.02 * L, 0.08 * L, 0.46 * L, 0.20 * L), trim_t)  # stock
        add(M.box(0, 0.0, -0.18 * L, 0.08 * L, 0.14 * L, 0.30 * L), trim_t)
        add(M.box(0, 0.62 * L, 0.115 * L, 0.025 * L, 0.70 * L, 0.025 * L), accent_t)
    elif gun_type == "sniper":
        add(M.box(0, 0.18 * L, 0.03 * L, 0.10 * L, 0.52 * L, 0.17 * L), body_t)
        add(M.cylinder(0, 0.70 * L, 0.05 * L, 0.028 * L, 0.80 * L), steel_t)
        add(M.cylinder(0, 0.22 * L, 0.17 * L, 0.04 * L, 0.42 * L), trim_t)  # scope
        add(M.cylinder(0, 0.22 * L, 0.17 * L, 0.048 * L, 0.05 * L), accent_t)
        add(M.box(0, -0.34 * L, 0.0, 0.08 * L, 0.46 * L, 0.20 * L), trim_t)
        add(M.box(0, 0.0, -0.18 * L, 0.07 * L, 0.12 * L, 0.28 * L), trim_t)
    elif gun_type == "launcher":
        add(M.cylinder(0, 0.35 * L, 0.10 * L, 0.10 * L, 0.90 * L), body_t)  # tube
        add(M.cylinder(0, 0.84 * L, 0.10 * L, 0.125 * L, 0.18 * L), accent_t)  # muzzle ring
        add(M.box(0, 0.0, -0.12 * L, 0.08 * L, 0.14 * L, 0.34 * L), trim_t)
        add(M.box(0, 0.22 * L, -0.02 * L, 0.06 * L, 0.20 * L, 0.10 * L), steel_t)
        add(M.box(0, 0.30 * L, 0.24 * L, 0.04 * L, 0.20 * L, 0.06 * L), steel_t)
    else:  # assault rifle and anything else
        add(M.box(0, 0.22 * L, 0.04 * L, 0.10 * L, 0.52 * L, 0.18 * L), body_t)
        add(M.cylinder(0, 0.70 * L, 0.06 * L, 0.03 * L, 0.55 * L), steel_t)
        add(M.box(0, 0.0, -0.18 * L, 0.08 * L, 0.14 * L, 0.32 * L), trim_t)
        add(M.box(0, 0.26 * L, -0.25 * L, 0.07 * L, 0.12 * L, 0.30 * L), steel_t)  # magazine
        add(M.box(0, -0.30 * L, 0.0, 0.08 * L, 0.46 * L, 0.20 * L), trim_t)  # stock
        add(M.box(0, 0.24 * L, 0.18 * L, 0.04 * L, 0.34 * L, 0.05 * L), accent_t)
    return out


# ---- writing --------------------------------------------------------------------------------------------------------

def _hex_rgb(key: str) -> tuple[int, int, int] | None:
    if key.startswith("c_") and len(key) == 8:
        try:
            return int(key[2:4], 16), int(key[4:6], 16), int(key[6:8], 16)
        except ValueError:
            return None
    return None


class GunModels:
    """Builds and writes gun meshes into out_data (Meshes/..., Textures/...), one NIF per distinct look."""

    def __init__(self, method: str, out_data: Path, vanilla_nif: bytes | None, say=print, extra_sources=None,
                 spin: float = 0.0, scale: float = 1.0) -> None:
        if method not in METHODS:
            raise ValueError(f"unknown gun model method {method!r}")
        self.method = method
        self.spin, self.scale = spin, scale  # extra turn about the up axis (degrees) and size multiplier, for correcting the fit by hand
        self.out = Path(out_data)
        self.say = say
        self.sources = extra_sources or {}  # method name -> object with part_meshes(g, built) -> {slot: Mesh|None} and textures
        pts = []
        if vanilla_nif:
            try:
                pts = nifread.world_points(vanilla_nif)
            except (nifread.NifError, ValueError) as e:
                say(f"Gun models: could not measure the vanilla crossbow mesh ({e}); using default axes.")
            if len(pts) < 4:
                say(f"Gun models: the vanilla crossbow mesh gave {len(pts)} points: {describe_nif(vanilla_nif)}")
        self.fit = fit_from_points(pts)
        say(f"Gun models ({method}): {self.fit.note}")
        self.written: dict[str, str] = {}  # look key -> mesh path under Meshes\
        self.textures: dict[str, bytes] = {}
        self.stats = {"built": 0, "shared": 0, "failed": 0}
        self.by_method: dict[str, int] = {}

    # --- textures
    def _texture_path(self, key: str, normal: bool = False) -> str:
        if key not in self.textures:
            rgb = _hex_rgb(key)
            if key == "flat_n":
                self.textures[key] = nif.dds_flat_normal()
            elif rgb is not None:
                self.textures[key] = nif.dds_solid(rgb)
            else:
                raise KeyError(key)
        return f"{TEX_DIR}\\{key}.dds"

    def add_texture(self, key: str, dds: bytes) -> str:
        self.textures[key] = dds
        return f"{TEX_DIR}\\{key}.dds"

    # --- one gun
    def model_for(self, g: dict, built: dict, rarity_id: str, accent: tuple[int, int, int], edid: str) -> str | None:
        """The path (under Meshes\\) of this gun's NIF, or None to keep the vanilla crossbow mesh."""
        if self.method == "off":
            return None
        order = ("native", "umodel", "proxy") if self.method == "auto" else (self.method,)
        for method in order:
            try:
                result = self._build(method, g, built, rarity_id, accent, edid)
            except Exception as e:  # noqa: BLE001 - a bad mesh must never stop the install
                self.say(f"Gun model {edid}: {method} failed ({type(e).__name__}: {e})")
                continue
            if result:
                self.by_method[method] = self.by_method.get(method, 0) + 1
                return result
        self.stats["failed"] += 1
        return None

    def _build(self, method: str, g: dict, built: dict, rarity_id: str, accent, edid: str) -> str | None:
        gun_type = g["type"]
        mfr = g.get("manufacturer", "")
        if method == "proxy":
            parts = proxy_parts(gun_type, mfr, accent)
            look = f"proxy|{gun_type}|{mfr}|{accent}"
        else:
            src = self.sources.get(method)
            if src is None:
                return None
            parts = src.gun_parts(g, built)
            if not parts:
                return None
            for tkey, dds in src.take_textures().items():
                self.add_texture(tkey, dds)
            body = PALETTE.get(mfr, ((120, 120, 124), (60, 60, 64)))[0]
            for part in parts:  # a part whose texture could not be read still gets the manufacturer's colour
                if not part.texture or part.texture not in self.textures:
                    part.texture = f"c_{body[0]:02x}{body[1]:02x}{body[2]:02x}"
                part.normal_map = "flat_n"
            look = f"{method}|" + "|".join(f"{k}={v}" for k, v in sorted(built.get("parts", {}).items()))
        key = hashlib.sha1(look.encode()).hexdigest()[:10]
        if key in self.written:
            self.stats["shared"] += 1
            return self.written[key]
        length = LENGTH.get(gun_type, 24.0) * self.scale
        lo, hi = _bounds_of(parts)
        if method != "proxy":
            _sanity(parts, lo, hi)
        size = hi[1] - lo[1]
        scale = length / size if size > 1e-6 else 1.0
        placed = [M.transformed(p, None, scale, (0.0, 0.0, 0.0)) for p in parts]
        # the grip is the canonical origin for proxies; real meshes are re-centred on the body below the receiver
        if method != "proxy":
            plo, phi = _bounds_of(placed)
            cx, cy, cz = (plo[0] + phi[0]) / 2, plo[1] + (phi[1] - plo[1]) * 0.28, phi[2] - (phi[2] - plo[2]) * 0.62
            placed = [M.transformed(p, None, 1.0, (-cx, -cy, -cz)) for p in placed]
        if method != "proxy":
            placed = [M.ensure_outward(p) for p in placed]
        if self.spin:
            a = math.radians(self.spin)
            turn = ((math.cos(a), -math.sin(a), 0.0), (math.sin(a), math.cos(a), 0.0), (0.0, 0.0, 1.0))
            placed = [M.transformed(p, turn) for p in placed]
        placed = [fit_mesh(p, self.fit, 1.0) for p in placed]
        groups: dict[tuple[str | None, str | None], list[M.Mesh]] = {}
        for p in placed:
            groups.setdefault((p.texture, p.normal_map), []).append(p)
        shapes = []
        for (tex, nrm), items in groups.items():
            m = M.merged(items)
            tex_path = self._texture_path(tex) if tex and (_hex_rgb(tex) or tex in self.textures) else (f"{TEX_DIR}\\{tex}.dds" if tex else None)
            nrm_path = self._texture_path(nrm) if nrm == "flat_n" else (f"{TEX_DIR}\\{nrm}.dds" if nrm else None)
            shapes.append((m, tex_path, nrm_path))
        allp = M.merged([s[0] for s in shapes])
        lo2, hi2 = allp.bounds()
        half = tuple(max(0.02, (hi2[i] - lo2[i]) / 2 / HAVOK_SCALE) for i in range(3))
        data = nif.gun(shapes, half, 2.0, "SkylandsGun")  # type: ignore[arg-type]
        rel = f"{MESH_DIR}\\{method}_{key}.nif"
        path = self.out / "Meshes" / Path(*rel.split("\\"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.written[key] = rel
        self.stats["built"] += 1
        return rel

    def flush_textures(self) -> int:
        d = self.out / "Textures" / "Skylands" / "Guns"
        d.mkdir(parents=True, exist_ok=True)
        for key, data in self.textures.items():
            (d / f"{key}.dds").write_bytes(data)
        return len(self.textures)

    def summary(self) -> str:
        return (f"Gun models: {self.stats['built']} meshes written, {self.stats['shared']} guns share one, "
                f"{self.stats['failed']} kept the crossbow mesh; by method {self.by_method or 'none'}; {len(self.textures)} textures")


def _sanity(parts: list[M.Mesh], lo: M.Vec, hi: M.Vec) -> None:
    """A mesh read from unknown data must look like a gun before it replaces the crossbow: enough triangles and elongated."""
    tris = sum(len(p.tris) for p in parts)
    ext = sorted(hi[i] - lo[i] for i in range(3))
    if tris < 30:
        raise ValueError(f"only {tris} triangles")
    if ext[0] <= 1e-6 or ext[2] / ext[0] > 400 or ext[2] / ext[0] < 1.8:  # a pistol is nearly as tall as it is long, but thin
        raise ValueError(f"extents {ext[0]:.2f} x {ext[1]:.2f} x {ext[2]:.2f} do not look like a gun")


def _bounds_of(parts: list[M.Mesh]) -> tuple[M.Vec, M.Vec]:
    pts = [p for m in parts for p in m.positions]
    if not pts:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    return (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts)), (max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))
