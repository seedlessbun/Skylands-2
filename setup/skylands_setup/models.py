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
import struct
import math
from dataclasses import dataclass
from pathlib import Path

from . import meshes as M
from . import sheet_data as S
from .skyrim import dxt, nif, nifread

METHODS = ("off", "proxy", "native", "umodel", "auto")
MESH_DIR = "Skylands\\Guns"  # under Meshes\
TEX_DIR = "textures\\skylands\\guns"
HAVOK_SCALE = 69.99125  # skyrim units per havok unit

# length of each gun type in Skyrim units (a hand is about 8, a dagger about 35): the in-game test showed a pistol sized
# as a fraction of the crossbow came out far too big next to the player
LENGTH = {"pistol": 23.0, "smg": 33.8, "assault_rifle": 47.3, "shotgun": 47.3, "sniper": 59.4, "launcher": 51.3}
# the first in-hand test showed a gun aimed down and to the right: turn it up and to the left (degrees, about the grip)
# calibration build: each rarity (level 1-6) gets a different turn from the plain fit, so one install shows six holds side by side
# (pitch, yaw, roll about the barrel axis, degrees)
CALIBRATION = {1: (90.0, 0.0, 0.0), 2: (-90.0, 0.0, 0.0), 3: (0.0, 0.0, 90.0), 4: (0.0, 0.0, -90.0), 5: (0.0, 90.0, 0.0), 6: (0.0, -90.0, 0.0)}
# The calibration test: +90 pointed down, -90 straight up, and the plain fit (0) was upside down and backwards. Going round
# from backwards: +90 is down, +180 is forwards and upright, -90 is up, so 180 is the hold.
HOLD_PITCH, HOLD_YAW = 180.0, 0.0
GRIP_DEPTH = 0.395  # how far down the gun's height (0 = top, 1 = bottom) the hand holds it; was 0.62: raising the hold point brings the gun down 15% of its height
GRIP_AT = 0.455  # where along the gun (0 = rear, 1 = muzzle) the hand holds it; was 0.28, raised to move the gun back in the hand

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
    spread = max(max(p[i] for p in points) - min(p[i] for p in points) for i in range(3))
    if not 3.0 < spread < 400.0:  # a crossbow is about 70 units: anything else is a misread, not a measurement
        return Fit(IDENTITY, 50.0, f"the vanilla mesh measured {spread:.0f} units, which is not a crossbow: assuming barrel +y, up +z")
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


@dataclass
class Hold:
    """How to fit a gun to another vanilla weapon than the crossbow (the staff prototype): that weapon's axes (`fit`), its
    extra data (the attach point), the turn (degrees) applied to the gun before the fit, and a tag for the file name."""

    fit: Fit
    extra: list
    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0
    tag: str = "hold"
    note: str = ""
    scale: float = 1.0  # size multiplier on the gun's length
    forward: float = 0.0  # how far (of the gun's length) it is moved along its barrel, after the turn
    lift: float = 0.0  # and along its own up


def staff_hold(vanilla_nif: bytes | None, turn: tuple[float, float, float] = (0.0, 0.0, 0.0), say=None,
               scale: float = 1.0, forward: float = 0.0, lift: float = 0.0) -> Hold:
    """Fit for a vanilla staff. A staff is long and thin, held near the middle with a head at one end; the gun's barrel goes
    towards the head (the end that is thicker). Where the axes cannot be measured the crossbow's assumption is used."""
    log = say or (lambda _m: None)
    pts: list = []
    extra: list = []
    if vanilla_nif:
        try:
            pts = nifread.world_points(vanilla_nif)
            extra = [e for e in nifread.extra_data(vanilla_nif) if e[0] == "NiStringExtraData"]
        except (nifread.NifError, ValueError, struct.error) as e:
            log(f"Staff gun: could not read the vanilla staff mesh ({e})")
    if len(pts) < 4:
        fit = Fit(IDENTITY, 100.0, "no vanilla staff mesh: assuming barrel +y, up +z")
        return Hold(fit, extra, *turn, tag="staff", note=fit.note, scale=scale, forward=forward, lift=lift)
    ext = [max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)]
    fwd = max(range(3), key=lambda i: ext[i])
    others = [i for i in range(3) if i != fwd]
    up = min(others, key=lambda i: ext[i])
    lo, hi = min(p[fwd] for p in pts), max(p[fwd] for p in pts)
    span = hi - lo

    def girth(a: float, b: float) -> float:  # how widely the points of one end of the staff are spread sideways
        side = [p for p in pts if a <= p[fwd] <= b]
        return sum(max(q[i] for q in side) - min(q[i] for q in side) for i in others) if side else 0.0

    top, bottom = girth(hi - span * 0.25, hi), girth(lo, lo + span * 0.25)
    sign = 1.0 if top >= bottom else -1.0
    f, u = [0.0] * 3, [0.0] * 3
    f[fwd], u[up] = sign, 1.0
    r = M.cross(tuple(f), tuple(u))  # type: ignore[arg-type]
    rows = tuple(tuple((r, f, u)[c][i] for c in range(3)) for i in range(3))
    note = (f"vanilla staff {span:.0f} long along axis {'xyz'[fwd]}, head at {'+' if sign > 0 else '-'} (end spread {top:.0f} vs {bottom:.0f}), "
            f"mesh runs {lo:.0f}..{hi:.0f}")
    return Hold(Fit(rows, span, note), extra, *turn, tag="staff", note=note, scale=scale, forward=forward, lift=lift)  # type: ignore[arg-type]


def find_vanilla_mesh(data_dir: Path, modl: bytes | None, say=None, what: str = "crossbow") -> bytes | None:
    """The vanilla crossbow's NIF: a loose file in Data\\Meshes, or inside one of Skyrim's archives (an exact path first, then
    the nearest thing named like a crossbow). Says what it did, because a miss means the fit falls back to guessed axes."""
    log = say or (lambda _m: None)
    if not modl:
        log(f"vanilla {what} mesh: the record has no model path")
        return None
    rel = modl.split(b"\0")[0].decode("cp1252", "replace").replace("/", "\\").lstrip("\\")
    loose = Path(data_dir) / "Meshes" / Path(*rel.split("\\"))
    if loose.is_file():
        log(f"vanilla {what} mesh: {rel} (loose file)")
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
                log(f"vanilla {what} mesh: {rel} (in {archive.name})")
                return data
            except Exception as e:  # noqa: BLE001
                failed.append(f"{archive.name} read: {type(e).__name__}: {e}")
        for name in a.entries:
            if what in name and name.endswith(".nif") and not any(k in name for k in ("1stperson", "firstperson", "bolt", "skin", "dlc02", "_fp")):
                near.append((archive, name))
    if near:
        near.sort(key=lambda t: (0 if "weapons" in t[1] else 1, len(t[1])))
        archive, name = near[0]
        try:
            data = bsa.BSA(archive).read(name)
            log(f"vanilla {what} mesh: {rel} not found; using {name} from {archive.name}")
            return data
        except Exception as e:  # noqa: BLE001
            failed.append(f"{archive.name} read {name}: {type(e).__name__}: {e}")
    log(f"vanilla {what} mesh: {rel} not found ({opened} archives searched, unreadable: {failed[:4] or 'none'})")
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
                 spin: float = 0.0, scale: float = 1.0, pitch: float = 0.0, calibrate: bool = False) -> None:
        if method not in METHODS:
            raise ValueError(f"unknown gun model method {method!r}")
        self.method = method
        self.calibrate = calibrate  # a different hold per rarity, for finding the right one by eye
        self.pitch = pitch  # extra nose-up angle in degrees on top of the built-in hold correction
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
        self.extra: list[tuple[str, str, str, int]] = []
        if vanilla_nif:
            try:
                found = nifread.extra_data(vanilla_nif)
                say(f"Gun models: the vanilla crossbow's extra data: {found}")
                # the "Prn" attach point (where the sheathed weapon hangs): without it a weapon is drawn at the player's feet
                self.extra = [e for e in found if e[0] == "NiStringExtraData"]
            except (nifread.NifError, ValueError, struct.error) as e:
                say(f"Gun models: could not read the vanilla crossbow's extra data ({e})")
        say(f"Gun models ({method}): {self.fit.note}")
        if calibrate:
            say(f"Gun models: CALIBRATION build, hold by rarity (pitch, yaw, roll): {CALIBRATION}")
        say(f"Gun models: hold correction pitch {HOLD_PITCH + pitch:g} deg (built in {HOLD_PITCH:g} + extra {pitch:g}), yaw {HOLD_YAW + spin:g} deg "
            f"(built in {HOLD_YAW:g} + extra {spin:g}), size x{scale:g}")
        self.written: dict[str, str] = {}  # look key -> mesh path under Meshes\
        self.textures: dict[str, bytes] = {}
        self.raw: dict[str, bytes] = {}  # decoded Borderlands 2 textures as read, before they are tinted per manufacturer
        self.sizes: dict[str, list[tuple[float, float]]] = {}  # gun type -> (barrel-axis length, longest side) of every mesh written, in Skyrim units
        self.shade_notes: dict[str, int] = {}
        self.prepared: dict[str, tuple] = {}  # texture key -> reduced RGB image (decoded once, tinted per manufacturer)
        self.stats = {"built": 0, "shared": 0, "failed": 0}
        self.by_type: dict[str, dict[str, int]] = {}  # gun type -> method -> guns (none: kept the vanilla mesh)
        self.by_method: dict[str, int] = {}

    # --- textures
    def _shaded(self, key: str, tint: tuple[int, int, int]) -> str | None:
        """The decoded Borderlands 2 texture `key` in the manufacturer's colour (see skyrim.dxt.shade)."""
        out = f"{key}_{tint[0]:02x}{tint[1]:02x}{tint[2]:02x}"
        if out not in self.textures:
            try:
                if key not in self.prepared:
                    self.prepared[key] = dxt.prepare(self.raw[key])
                data, note = dxt.shade(self.prepared[key], tint)
            except Exception as e:  # noqa: BLE001 - a texture that cannot be read becomes a plain colour
                self.say(f"Gun models: texture {key} could not be shaded ({type(e).__name__}: {e})")
                return None
            self.textures[out] = data
            if not self.shade_notes.get(note.split(" (")[0]):
                self.shade_notes[note.split(" (")[0]] = 1
                self.say(f"Gun models: texture {key}: {note}")
        return out

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
    def model_for(self, g: dict, built: dict, rarity_id: str, accent: tuple[int, int, int], edid: str,
                  hold: "Hold | None" = None) -> str | None:
        """The path (under Meshes\\) of this gun's NIF, or None to keep the vanilla crossbow mesh. `hold` fits the gun to
        another vanilla weapon instead (the staff prototype): its axes, attach point and turn."""
        if self.method == "off":
            return None
        order = ("native", "umodel", "proxy") if self.method == "auto" else (self.method,)
        if hold is not None and "proxy" not in order:  # a staff gun whose real model cannot be built gets the stylised one, never the staff it is made from
            order = (*order, "proxy")
        for method in order:
            try:
                result = self._build(method, g, built, rarity_id, accent, edid, hold)
            except Exception as e:  # noqa: BLE001 - a bad mesh must never stop the install
                self.say(f"Gun model {edid}: {method} failed ({type(e).__name__}: {e})")
                continue
            if result:
                self.by_method[method] = self.by_method.get(method, 0) + 1
                per_type = self.by_type.setdefault(g.get("type", "?"), {})
                per_type[method] = per_type.get(method, 0) + 1
                return result
        self.stats["failed"] += 1
        self.by_type.setdefault(g.get("type", "?"), {})["none"] = self.by_type.setdefault(g.get("type", "?"), {}).get("none", 0) + 1
        return None

    def _build(self, method: str, g: dict, built: dict, rarity_id: str, accent, edid: str, hold: "Hold | None" = None) -> str | None:
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
                self.raw[tkey] = dds
            body = PALETTE.get(mfr, ((120, 120, 124), (60, 60, 64)))[0]
            for part in parts:  # a part whose texture could not be read still gets the manufacturer's colour
                if part.texture in self.raw:
                    part.texture = self._shaded(part.texture, body)
                if not part.texture or (part.texture not in self.textures and not _hex_rgb(part.texture)):
                    part.texture = f"c_{body[0]:02x}{body[1]:02x}{body[2]:02x}"
                part.normal_map = "flat_n"
            look = f"{method}|" + "|".join(f"{k}={v}" for k, v in sorted(built.get("parts", {}).items()))
        calib_level = S.RARITIES[rarity_id].level if self.calibrate and rarity_id in S.RARITIES else 1
        if self.calibrate:
            look += f"|calibration {calib_level}"
        if hold is not None:
            look += f"|{hold.tag}|{hold.pitch:g},{hold.yaw:g},{hold.roll:g}|{hold.scale:g},{hold.forward:g},{hold.lift:g}"
        key = hashlib.sha1(look.encode()).hexdigest()[:10]
        if key in self.written:
            self.stats["shared"] += 1
            return self.written[key]
        length = LENGTH.get(gun_type, 24.0) * self.scale * (hold.scale if hold is not None else 1.0)
        lo, hi = _bounds_of(parts)
        if method != "proxy":
            _sanity(parts, lo, hi)
        size = hi[1] - lo[1]
        scale = length / size if size > 1e-6 else 1.0
        placed = [M.transformed(p, None, scale, (0.0, 0.0, 0.0)) for p in parts]
        # the grip is the canonical origin for proxies; real meshes are re-centred on the body below the receiver
        if method != "proxy":
            plo, phi = _bounds_of(placed)
            cx, cy, cz = (plo[0] + phi[0]) / 2, plo[1] + (phi[1] - plo[1]) * GRIP_AT, phi[2] - (phi[2] - plo[2]) * GRIP_DEPTH
            placed = [M.transformed(p, None, 1.0, (-cx, -cy, -cz)) for p in placed]
        if method != "proxy":
            placed = [M.ensure_outward(p) for p in placed]
        fit, extra = (hold.fit, hold.extra) if hold is not None else (self.fit, self.extra)
        if hold is not None:
            hold_pitch, hold_yaw, hold_roll = hold.pitch, hold.yaw, hold.roll
        elif self.calibrate:
            hold_pitch, hold_yaw, hold_roll = CALIBRATION[calib_level]
        else:
            hold_pitch, hold_yaw, hold_roll = HOLD_PITCH + self.pitch, HOLD_YAW + self.spin, 0.0
        marker = None
        if hold is not None:
            # the muzzle: the middle of the barrel's end, followed through every turn and the fit below as a one-vertex mesh
            plo, phi = _bounds_of(placed)
            span = max(phi[1] - plo[1], 1e-6)
            end = [pt for pm in placed for pt in pm.positions if pt[1] >= phi[1] - 0.04 * span]
            tip = (sum(pt[0] for pt in end) / len(end), phi[1], sum(pt[2] for pt in end) / len(end)) if end else ((plo[0] + phi[0]) / 2, phi[1], (plo[2] + phi[2]) / 2)
            marker = M.Mesh(positions=[tip], normals=[(0.0, 1.0, 0.0)], tris=[])
            # two more points, followed the same way: the rear end of the barrel and a point above the muzzle (the source gun's up is +z), so the plugin knows the
            # gun's barrel direction and its up when it holds the gun straight in front of the view
            breech = M.Mesh(positions=[(tip[0], plo[1], tip[2])], normals=[(0.0, 1.0, 0.0)], tris=[])
            top = M.Mesh(positions=[(tip[0], tip[1], tip[2] + 0.15 * span)], normals=[(0.0, 1.0, 0.0)], tris=[])
            placed = [*placed, marker, breech, top]
        roll = math.radians(hold_roll)  # about the barrel axis
        placed = [M.transformed(p, ((math.cos(roll), 0.0, math.sin(roll)), (0.0, 1.0, 0.0), (-math.sin(roll), 0.0, math.cos(roll)))) for p in placed] if roll else placed
        pitch = math.radians(hold_pitch)
        up_turn = ((1.0, 0.0, 0.0), (0.0, math.cos(pitch), -math.sin(pitch)), (0.0, math.sin(pitch), math.cos(pitch)))  # barrel +y towards +z
        placed = [M.transformed(p, up_turn) for p in placed]
        if hold_yaw:
            a = math.radians(hold_yaw)
            turn = ((math.cos(a), -math.sin(a), 0.0), (math.sin(a), math.cos(a), 0.0), (0.0, 0.0, 1.0))
            placed = [M.transformed(p, turn) for p in placed]
        if hold is not None and (hold.forward or hold.lift):
            # moved along the barrel and the gun's own up, as they are after the turn (the turn is applied to the basis the same way)
            probe = [M.Mesh(positions=[(0.0, 1.0, 0.0), (0.0, 0.0, 1.0)], normals=[(0.0, 1.0, 0.0), (0.0, 0.0, 1.0)], tris=[]) ]
            basis = probe[0]
            if roll:
                basis = M.transformed(basis, ((math.cos(roll), 0.0, math.sin(roll)), (0.0, 1.0, 0.0), (-math.sin(roll), 0.0, math.cos(roll))))
            basis = M.transformed(basis, up_turn)
            if hold_yaw:
                basis = M.transformed(basis, turn)
            (bx, by, bz), (ux, uy, uz) = basis.positions
            off = tuple((bx, by, bz)[i] * hold.forward * length + (ux, uy, uz)[i] * hold.lift * length for i in range(3))
            placed = [M.transformed(p, None, 1.0, off) for p in placed]
        placed = [fit_mesh(p, fit, 1.0) for p in placed]
        muzzle = None
        marks: list[tuple[str, tuple[float, float, float]]] = []
        if marker is not None:
            muzzle = tuple(float(c) for c in placed[-3].positions[0])
            marks = [(nif.BREECH_NODE, tuple(float(c) for c in placed[-2].positions[0])), (nif.TOP_NODE, tuple(float(c) for c in placed[-1].positions[0]))]
            placed = placed[:-3]
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
        self.sizes.setdefault(gun_type, []).append((hi2[1] - lo2[1], max(hi2[i] - lo2[i] for i in range(3))))
        data = nif.gun(shapes, half, 2.0, "SkylandsGun", extra, muzzle, marks)  # type: ignore[arg-type]
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
        sizes = ", ".join(f"{t} {sum(a for a, _ in v) / len(v):.1f}" for t, v in sorted(self.sizes.items()))
        return (f"Gun models: {self.stats['built']} meshes written, {self.stats['shared']} guns share one, "
                f"{self.stats['failed']} kept the vanilla mesh; by method {self.by_method or 'none'}; by gun type {self.by_type or 'none'}; {len(self.textures)} textures; "
                f"average length of the meshes written (Skyrim units, a hand is about 8): {sizes or 'none'}")


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
