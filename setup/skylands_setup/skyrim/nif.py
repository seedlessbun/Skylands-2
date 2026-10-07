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
