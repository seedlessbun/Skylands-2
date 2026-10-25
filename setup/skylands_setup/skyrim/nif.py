"""Write the small Skyrim SE meshes Skylands makes itself (the loot beam), and their textures.

NIF 20.2.0.7, user version 12, BS version 100 (Skyrim SE). Block layouts follow niftools'
nif.xml for BSVER 100. The beam is two crossed vertical quads with an unlit additive effect
shader: a vertical gradient texture (white, alpha fading upward) tinted by the rarity colour.
"""

from __future__ import annotations

import struct

# Vertex attribute flags (bits 44+ of the vertex descriptor).
VF_VERTEX, VF_UV, VF_NORMAL, VF_TANGENT, VF_COLORS, VF_FULLPREC = 0x1, 0x2, 0x8, 0x10, 0x20, 0x400

# BSEffectShaderProperty flags.
SLSF1_ZBUFFER_TEST = 0x80000000
SLSF2_ZBUFFER_WRITE, SLSF2_DOUBLE_SIDED, SLSF2_VERTEX_COLORS = 0x1, 0x10, 0x20


def _sized(s: str) -> bytes:
    b = s.encode("cp1252")
    return struct.pack("<I", len(b)) + b


def _short(s: str) -> bytes:
    b = s.encode("cp1252") + b"\0"
    return bytes([len(b)]) + b


def _half(v: float) -> bytes:
    return struct.pack("<e", v)


class NifBuilder:
    def __init__(self) -> None:
        self.blocks: list[tuple[str, bytes]] = []
        self.strings: list[str] = []

    def s(self, text: str) -> int:
        if text == "":
            return -1
        if text not in self.strings:
            self.strings.append(text)
        return self.strings.index(text)

    def add(self, btype: str, data: bytes) -> int:
        self.blocks.append((btype, data))
        return len(self.blocks) - 1

    def set(self, index: int, data: bytes) -> None:
        self.blocks[index] = (self.blocks[index][0], data)

    def encode(self) -> bytes:
        types: list[str] = []
        for t, _ in self.blocks:
            if t not in types:
                types.append(t)
        out = b"Gamebryo File Format, Version 20.2.0.7\n"
        out += struct.pack("<IBII", 0x14020007, 1, 12, len(self.blocks))
        out += struct.pack("<I", 100) + _short("Skylands") + _short("") + _short("")
        out += struct.pack("<H", len(types)) + b"".join(_sized(t) for t in types)
        out += b"".join(struct.pack("<H", types.index(t)) for t, _ in self.blocks)
        out += b"".join(struct.pack("<I", len(d)) for _, d in self.blocks)
        out += struct.pack("<II", len(self.strings), max((len(x) for x in self.strings), default=0))
        out += b"".join(_sized(x) for x in self.strings)
        out += struct.pack("<I", 0)  # groups
        out += b"".join(d for _, d in self.blocks)
        out += struct.pack("<II", 1, 0)  # footer: one root, block 0
        return out


IDENTITY = struct.pack("<9f", 1, 0, 0, 0, 1, 0, 0, 0, 1)


def _net(b: NifBuilder, name: str) -> bytes:
    return struct.pack("<iIi", b.s(name), 0, -1)  # name, no extra data, no controller


def _av(flags: int = 14) -> bytes:
    return struct.pack("<I3f", flags, 0, 0, 0) + IDENTITY + struct.pack("<fi", 1.0, -1)  # no collision


def vertex_desc(flags: int, size_units: int, uv: int, normal: int, color: int) -> int:
    return size_units | (uv << 8) | (normal << 16) | (color << 24) | (flags << 44)


def beam(color: tuple[int, int, int], texture: str, height: float = 140.0, width: float = 7.0) -> bytes:
    """A rarity loot beam: two crossed quads, bottom at the origin, colour from the rarity table."""
    b = NifBuilder()
    root = b.add("BSFadeNode", b"")
    b.s("SkylandsLootBeam")  # strings in block order, as nifly writes them
    shapes = []
    flags = VF_VERTEX | VF_UV | VF_NORMAL | VF_COLORS | VF_FULLPREC
    # position 16 (xyz + unused w), uv 4, normal 4, colour 4 = 28 bytes = 7 units
    desc = vertex_desc(flags, 7, 4, 5, 6)
    for k, (dx, dy) in enumerate(((1.0, 0.0), (0.0, 1.0))):
        corners = [(-dx, -dy, 0.0, 0.0, 1.0), (dx, dy, 0.0, 1.0, 1.0), (dx, dy, height, 1.0, 0.0), (-dx, -dy, height, 0.0, 0.0)]
        verts = b""
        for x, y, z, u, v in corners:
            verts += struct.pack("<3fI", x * width, y * width, z, 0)
            verts += _half(u) + _half(v)
            verts += bytes([128, 128, 255, 128])  # normal (packed) + bitangent y
            verts += bytes([255, 255, 255, 255 if z == 0 else 0])  # vertex alpha fades upward
        tris = struct.pack("<6H", 0, 1, 2, 0, 2, 3)
        data_size = len(verts) + len(tris)
        idx = b.add("BSTriShape", b"")  # shape first, then its properties (Bethesda/nifly order)
        shader = b.add("BSEffectShaderProperty", b"")
        alpha = b.add("NiAlphaProperty", b"")
        shape = _net(b, f"LootBeam{k}") + _av()
        shape += struct.pack("<3ff", 0, 0, height / 2, ((height / 2) ** 2 + width**2) ** 0.5)  # bounding sphere
        shape += struct.pack("<iii", -1, shader, alpha)  # skin, shader, alpha
        shape += struct.pack("<Q", desc)
        shape += struct.pack("<HHI", 2, 4, data_size) + verts + tris
        shape += struct.pack("<I", 0)  # particle data size (SSE)
        b.set(idx, shape)
        shapes.append(idx)
        r, g, bl = (c / 255.0 for c in color)
        eff = _net(b, "")
        eff += struct.pack("<II", SLSF1_ZBUFFER_TEST, SLSF2_DOUBLE_SIDED | SLSF2_VERTEX_COLORS)
        eff += struct.pack("<4f", 0, 0, 1, 1)  # uv offset, uv scale
        eff += _sized(texture)
        eff += bytes([3, 255, 0, 0])  # clamp WRAP_S_WRAP_T, lighting influence, env map LOD, unused
        eff += struct.pack("<4f", 1.0, 0.0, 1.0, 1.0)  # falloff start/stop angle, start/stop opacity
        eff += struct.pack("<4f", r, g, bl, 1.0)  # emissive colour
        eff += struct.pack("<ff", 2.0, 0.0)  # emissive multiple, soft falloff depth
        eff += _sized("")  # greyscale texture
        b.set(shader, eff)
        # additive blending (src alpha, dest one), no alpha test
        b.set(alpha, _net(b, "") + struct.pack("<HB", 0x1 | (6 << 1) | (0 << 5), 0))
    node = _net(b, "SkylandsLootBeam") + _av(14)
    node += struct.pack("<I", len(shapes)) + b"".join(struct.pack("<i", i) for i in shapes)
    node += struct.pack("<I", 0)  # effects
    b.set(root, node)
    return b.encode()


def glow(layers: list[tuple[tuple[int, int, int], float, float, bool, float]], texture: str, name: str = "SkylandsTracer") -> bytes:
    """Glowing crossed quads along +y, any number of layers drawn together: each layer is (colour, length, width, forward, brightness). A layer's bright
    end is at the origin and the other end, `length` behind it (ahead of it when `forward`), fades out; additive and emissive."""
    b = NifBuilder()
    root = b.add("BSFadeNode", b"")
    b.s(name)
    shapes = []
    flags = VF_VERTEX | VF_UV | VF_NORMAL | VF_COLORS | VF_FULLPREC
    desc = vertex_desc(flags, 7, 4, 5, 6)
    for layer, (color, length, width, forward, bright) in enumerate(layers):
        for k, (dx, dz) in enumerate(((1.0, 0.0), (0.0, 1.0))):
            far = length if forward else -length
            corners = [(-dx, 0.0, -dz, 0.0, 1.0), (dx, 0.0, dz, 1.0, 1.0), (dx, far, dz, 1.0, 0.0), (-dx, far, -dz, 0.0, 0.0)]
            verts = b""
            for x, y, z, u, v in corners:
                verts += struct.pack("<3fI", x * width, y, z * width, 0)
                verts += _half(u) + _half(v)
                verts += bytes([128, 255, 128, 128])  # normal (packed) + bitangent y
                verts += bytes([255, 255, 255, 255 if y == 0 else 0])  # vertex alpha fades towards the far end
            tris = struct.pack("<6H", 0, 1, 2, 0, 2, 3)
            data_size = len(verts) + len(tris)
            idx = b.add("BSTriShape", b"")
            shader = b.add("BSEffectShaderProperty", b"")
            alpha = b.add("NiAlphaProperty", b"")
            shape = _net(b, f"Tracer{k}" if len(layers) == 1 else f"Tracer{layer}_{k}") + _av()
            shape += struct.pack("<3ff", 0, (length if forward else -length) / 2, 0, ((length / 2) ** 2 + width**2) ** 0.5)  # bounding sphere
            shape += struct.pack("<iii", -1, shader, alpha)
            shape += struct.pack("<Q", desc)
            shape += struct.pack("<HHI", 2, 4, data_size) + verts + tris
            shape += struct.pack("<I", 0)
            b.set(idx, shape)
            shapes.append(idx)
            r, g, bl = (c / 255.0 for c in color)
            eff = _net(b, "")
            eff += struct.pack("<II", SLSF1_ZBUFFER_TEST, SLSF2_DOUBLE_SIDED | SLSF2_VERTEX_COLORS)
            eff += struct.pack("<4f", 0, 0, 1, 1)
            eff += _sized(texture)
            eff += bytes([3, 255, 0, 0])
            eff += struct.pack("<4f", 1.0, 0.0, 1.0, 1.0)
            eff += struct.pack("<4f", r, g, bl, 1.0)  # emissive colour
            eff += struct.pack("<ff", bright, 0.0)  # emissive multiple, soft falloff depth
            eff += _sized("")
            b.set(shader, eff)
            b.set(alpha, _net(b, "") + struct.pack("<HB", 0x1 | (6 << 1) | (0 << 5), 0))
    node = _net(b, name) + _av(14)
    node += struct.pack("<I", len(shapes)) + b"".join(struct.pack("<i", i) for i in shapes)
    node += struct.pack("<I", 0)
    b.set(root, node)
    return b.encode()


def tracer(color: tuple[int, int, int], texture: str, length: float = 90.0, width: float = 1.6, forward: bool = False) -> bytes:
    """A bullet tracer for a projectile: two crossed quads along +y (the way a projectile flies), the bright head at the
    origin and the tail `length` behind it fading out, glowing (additive, emissive) in the given colour. `forward` puts the fading
    part ahead of the origin instead (a muzzle flash: it leaves the barrel in the way the bullet goes)."""
    return glow([(color, length, width, forward, 3.0)], texture)


ROCKET_STYLES = ("Missile", "Heavy rocket", "Plasma rocket")


def rocket(style: int, tint: tuple[int, int, int], texture: str) -> bytes:
    """A rocket for a launcher's projectile (larger than a bullet's tracer, flying along +y), in one of three looks to compare in play:
    0 a slim missile with a white-hot core and a long flame, 1 a fat, slow shell with a short flame and a dark smoke-grey tail, 2 a plasma bolt with a
    bright core and a wide halo. `tint` is the colour of the flame (the element's, or the plain one)."""
    r, g, b2 = tint
    hot = (255, 255, 235)
    if style == 0:
        layers = [((r, g, b2), 95.0, 5.0, False, 3.0), (hot, 34.0, 3.2, False, 3.5), ((255, 255, 255), 9.0, 5.5, True, 3.5)]
    elif style == 1:
        layers = [((90, 90, 90), 140.0, 7.0, False, 1.6), ((r, g, b2), 60.0, 6.0, False, 3.0), (hot, 16.0, 8.5, False, 3.5), ((r, g, b2), 12.0, 8.5, True, 3.0)]
    else:
        layers = [((r // 2 + 60, g // 2 + 60, b2 // 2 + 120), 80.0, 9.0, False, 2.2), ((255, 255, 255), 44.0, 3.4, False, 4.0), ((r, g, b2), 26.0, 6.0, True, 3.0)]
    return glow(layers, texture, "SkylandsRocket")


def dds_gradient(height: int = 64) -> bytes:
    """1 x height uncompressed RGBA texture: white, alpha 255 at the bottom fading to 0 at the top."""
    width = 4
    header = struct.pack(
        "<4sIIIIIII44sIIIIIIIIIIIII",
        b"DDS ", 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x8, height, width, width * 4, 0, 1, b"\0" * 44,
        32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000, 0x1000, 0, 0, 0, 0,
    )
    rows = b""
    for y in range(height):
        a = int(255 * (y / (height - 1)))  # DDS rows go top to bottom; top transparent
        rows += bytes([255, 255, 255, a]) * width
    return header + rows


# ---- a lit, textured weapon mesh with simple havok collision --------------------------------------------------------

SLSF1_LIT = 0x82400301  # what nifly writes for a plain lit shape (specular, shadows, z-buffer test)
SLSF2_LIT = 0x00008001
VF_TANGENT_SET = VF_VERTEX | VF_UV | VF_NORMAL | VF_TANGENT | VF_FULLPREC
HAVOK_LAYER_CLUTTER = 4
HAVOK_MATERIAL_SOLID_METAL = 1288358971  # SKY_HAV_MAT_SOLID_METAL: sounds and impacts of a metal object


def _byte(v: float) -> int:
    return max(0, min(255, int(round(v * 127.5 + 127.5))))


def _extra_net(b: NifBuilder, name: str, extras: list[int]) -> bytes:
    return struct.pack("<iI", b.s(name), len(extras)) + b"".join(struct.pack("<i", e) for e in extras) + struct.pack("<i", -1)


def _av_c(flags: int = 14, collision: int = -1, scale: float = 1.0) -> bytes:
    return struct.pack("<I3f", flags, 0, 0, 0) + IDENTITY + struct.pack("<fi", scale, collision)


def lit_shape(b: NifBuilder, name: str, mesh, texture: str | None, normal_map: str | None, glossiness: float = 40.0,
              specular: float = 1.0) -> int:
    """Add one BSTriShape (+ lighting shader + texture set) for a `meshes.Mesh`; returns the shape's block index."""
    from .. import meshes as M  # local import: nif.py is also used without the mesh module

    mesh = M.with_normals(mesh)
    n = len(mesh.positions)
    if n == 0 or not mesh.tris:
        raise ValueError(f"{name}: empty mesh")
    if n > 65535 or len(mesh.tris) > 65535:
        raise ValueError(f"{name}: too many vertices or triangles for one shape ({n}/{len(mesh.tris)})")
    tans = M.tangents(mesh)
    uvs = mesh.uvs if len(mesh.uvs) == n else [(0.0, 0.0)] * n
    desc = vertex_desc(VF_TANGENT_SET, 7, 4, 5, 0) | (6 << 20)
    verts = b""
    for i in range(n):
        x, y, z = mesh.positions[i]
        nx, ny, nz = mesh.normals[i]
        (tx, ty, tz), hand = tans[i]
        bt = M.cross((nx, ny, nz), (tx, ty, tz))
        verts += struct.pack("<4f", x, y, z, bt[0] * hand)
        verts += _half(uvs[i][0]) + _half(uvs[i][1])
        verts += bytes([_byte(nx), _byte(ny), _byte(nz), _byte(bt[1] * hand)])
        verts += bytes([_byte(tx), _byte(ty), _byte(tz), _byte(bt[2] * hand)])
    tris = b"".join(struct.pack("<3H", *t) for t in mesh.tris)
    lo, hi = mesh.bounds()
    centre = tuple((a + c) / 2 for a, c in zip(lo, hi))
    radius = max(((p[0] - centre[0]) ** 2 + (p[1] - centre[1]) ** 2 + (p[2] - centre[2]) ** 2) ** 0.5 for p in mesh.positions)
    idx = b.add("BSTriShape", b"")
    shader = b.add("BSLightingShaderProperty", b"")
    texset = b.add("BSShaderTextureSet", b"")
    shape = _extra_net(b, name, []) + _av_c()
    shape += struct.pack("<4f", *centre, radius)
    shape += struct.pack("<iii", -1, shader, -1)  # skin, shader, alpha
    shape += struct.pack("<Q", desc)
    shape += struct.pack("<HHI", len(mesh.tris), n, len(verts) + len(tris)) + verts + tris
    shape += struct.pack("<I", 0)
    b.set(idx, shape)
    sh = struct.pack("<I", 0) + _extra_net(b, "", [])
    sh += struct.pack("<II", SLSF1_LIT, SLSF2_LIT)
    sh += struct.pack("<4f", 0, 0, 1, 1)  # uv offset, scale
    sh += struct.pack("<i", texset)
    sh += struct.pack("<3ffIf", 0, 0, 0, 1.0, 3, 1.0)  # emissive colour, multiple, clamp, alpha
    sh += struct.pack("<ff", 0.0, glossiness)  # refraction, glossiness
    sh += struct.pack("<3ff", 1.0, 1.0, 1.0, specular)
    sh += struct.pack("<ff", 0.3, 2.0)  # lighting effects
    b.set(shader, sh)
    slots = [texture or "", normal_map or ""] + [""] * 7
    b.set(texset, struct.pack("<I", 9) + b"".join(_sized(s) for s in slots))
    return idx


def collision_blocks(b: NifBuilder, half: tuple[float, float, float], mass: float, root: int, layer: int = HAVOK_LAYER_CLUTTER) -> int:
    """A box collision body (havok units, half extents) for the root; returns the collision object's block index."""
    box = b.add("bhkBoxShape", struct.pack("<If", HAVOK_MATERIAL_SOLID_METAL, 0.0) + b"\0" * 8 + struct.pack("<3ff", half[0], half[1], half[2], 0.0))
    # inertia of a solid box, as three rows of four floats
    hx, hy, hz = (2 * h for h in half)
    ix, iy, iz = mass * (hy * hy + hz * hz) / 12, mass * (hx * hx + hz * hz) / 12, mass * (hx * hx + hy * hy) / 12
    body = struct.pack("<i", box) + bytes([layer, 0, 0, 0]) + struct.pack("<i", 0) + bytes([1, 0, 0, 0])
    body += struct.pack("<III", 0, 0, 0x80000000)  # world object property
    body += bytes([1, 0]) + struct.pack("<H", 0xFFFF) + struct.pack("<I", 0) + bytes([layer, 0, 0, 0]) + b"\0" * 12
    body += struct.pack("<4f", 0, 0, 0, 0) + struct.pack("<4f", 0, 0, 0, 1) + struct.pack("<4f", 0, 0, 0, 0) * 2
    body += struct.pack("<12f", ix, 0, 0, 0, 0, iy, 0, 0, 0, 0, iz, 0)
    body += struct.pack("<4f", 0, 0, 0, 0)  # centre of mass
    body += struct.pack("<ffffffffff", mass, 0.1, 0.05, 1.0, 1.0, 0.5, 1.0, 0.4, 104.4, 31.57)
    body += struct.pack("<f", 0.15)
    body += bytes([1, 1, 1, 4, 0, 0, 0, 0]) + b"\0" * 12 + struct.pack("<I", 0) + struct.pack("<H", 0)
    rb = b.add("bhkRigidBodyT", body)
    return b.add("bhkCollisionObject", struct.pack("<iHi", root, 0x81, rb))


MUZZLE_NODE = "SkylandsMuzzle"


BREECH_NODE, TOP_NODE = "SkylandsBreech", "SkylandsTop"  # empty nodes in a gun mesh: the rear end of the barrel and a point above the muzzle


def gun(parts: list, box_half: tuple[float, float, float] = (0.1, 0.4, 0.05), mass: float = 2.0, name: str = "SkylandsGun",
        extra: list[tuple[str, str, str, int]] | None = None, muzzle: tuple[float, float, float] | None = None,
        marks: list[tuple[str, tuple[float, float, float]]] | None = None) -> bytes:
    """A weapon NIF: one lit shape per (mesh, diffuse path, normal path) in `parts`, a BSX flags block, box collision. With
    `muzzle` (a point in the mesh's own coordinates) it also holds an empty NiNode named SkylandsMuzzle there, which the
    SkylandsNative plugin finds in the equipped weapon's 3D to start the bullets from the barrel."""
    b = NifBuilder()
    root = b.add("BSFadeNode", b"")
    bsx = b.add("BSXFlags", struct.pack("<iI", b.s("BSX"), 2))
    extras = [bsx]
    for kind, ename, value, flag in extra or []:  # the vanilla weapon's attach point ("Prn") and behaviour graph
        if kind == "NiStringExtraData":
            extras.append(b.add(kind, struct.pack("<ii", b.s(ename), b.s(value))))
        elif kind == "BSBehaviorGraphExtraData":
            extras.append(b.add(kind, struct.pack("<iiB", b.s(ename), b.s(value), flag)))
    shapes = [lit_shape(b, f"{name}{i}", m, tex, nrm) for i, (m, tex, nrm) in enumerate(parts)]
    if muzzle is not None:
        mz = b.add("NiNode", b"")
        b.set(mz, _net(b, MUZZLE_NODE) + struct.pack("<I3f", 14, *muzzle) + IDENTITY + struct.pack("<fi", 1.0, -1)
              + struct.pack("<I", 0) + struct.pack("<I", 0))  # no children, no effects
        shapes = [*shapes, mz]
    for node_name, point in marks or []:  # more empty nodes (the barrel's rear end, a point above the muzzle), found by name like the muzzle
        mk = b.add("NiNode", b"")
        b.set(mk, _net(b, node_name) + struct.pack("<I3f", 14, *point) + IDENTITY + struct.pack("<fi", 1.0, -1) + struct.pack("<I", 0) + struct.pack("<I", 0))
        shapes = [*shapes, mk]
    col = collision_blocks(b, box_half, mass, root)
    node = _extra_net(b, name, extras) + _av_c(14, col)
    node += struct.pack("<I", len(shapes)) + b"".join(struct.pack("<i", i) for i in shapes)
    node += struct.pack("<I", 0)
    b.set(root, node)
    return b.encode()


def empty(name: str = "SkylandsAimPoint") -> bytes:
    """A NIF with a root node and nothing to draw: gives a placed object 3D (so it can be a projectile source) while
    staying invisible."""
    b = NifBuilder()
    root = b.add("BSFadeNode", b"")
    bsx = b.add("BSXFlags", struct.pack("<iI", b.s("BSX"), 0))
    b.set(root, _extra_net(b, name, [bsx]) + _av_c(14, -1) + struct.pack("<I", 0) + struct.pack("<I", 0))
    return b.encode()


def dds_solid(rgb: tuple[int, int, int], size: int = 4, alpha: int = 255) -> bytes:
    """A tiny uncompressed BGRA texture of one colour (the diffuse of a proxy gun part)."""
    return _dds_bgra(size, size, bytes([rgb[2], rgb[1], rgb[0], alpha]) * (size * size))


def dds_flat_normal(size: int = 4) -> bytes:
    """A flat tangent-space normal map (straight out of the surface)."""
    return _dds_bgra(size, size, bytes([255, 128, 128, 255]) * (size * size))


def _dds_bgra(width: int, height: int, pixels: bytes) -> bytes:
    header = struct.pack(
        "<4sIIIIIII44sIIIIIIIIIIIII",
        b"DDS ", 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x8, height, width, width * 4, 0, 1, b"\0" * 44,
        32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000, 0x1000, 0, 0, 0, 0,
    )
    return header + pixels
