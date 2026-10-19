"""Read ActorX .psk / .pskx files (what UModel exports for skeletal and static meshes) into a `meshes.Mesh`.

Chunks: a 32-byte header (20-byte id, type flag, record size, record count) then the records. Used chunks: PNTS0000
(points), VTXW0000 / VTXW3200 (wedges: a point with its UV), FACE0000 / FACE3200 (triangles of wedges) and MATT0000
(materials). Each wedge becomes one vertex, so UV seams are already split.
"""

from __future__ import annotations

import struct

from .. import meshes as M


class PSKError(ValueError):
    pass


def chunks(data: bytes):
    p = 0
    while p + 32 <= len(data):
        name = data[p:p + 20].split(b"\0")[0].decode("ascii", "replace")
        _flag, size, count = struct.unpack_from("<III", data, p + 20)
        body = data[p + 32:p + 32 + size * count]
        if len(body) != size * count:
            raise PSKError(f"chunk {name} is cut off")
        yield name, size, count, body
        p += 32 + size * count


def read(data: bytes) -> tuple[M.Mesh, list[str]]:
    """Returns the mesh (all materials together; `tint`/texture left empty) and the material names by index.

    Triangles keep their material index in `Mesh.tris` order through the returned list `face_materials` attribute-free API:
    use `read_by_material` when the materials matter."""
    parts = read_by_material(data)
    mesh = M.merged([m for m, _ in parts]) if parts else M.Mesh()
    return mesh, [name for _, name in parts]


def read_by_material(data: bytes) -> list[tuple[M.Mesh, str]]:
    points: list[tuple[float, float, float]] = []
    wedges: list[tuple[int, float, float, int]] = []
    faces: list[tuple[int, int, int, int]] = []
    mats: list[str] = []
    for name, size, count, body in chunks(data):
        if name == "PNTS0000" and size == 12:
            points = [struct.unpack_from("<3f", body, i * 12) for i in range(count)]
        elif name == "VTXW0000" and size == 16:
            for i in range(count):
                pi, u, v, mi = struct.unpack_from("<HxxffB", body, i * 16)
                wedges.append((pi, u, v, mi))
        elif name == "VTXW3200" and size == 16:
            for i in range(count):
                pi, u, v, mi = struct.unpack_from("<IffB", body, i * 16)
                wedges.append((pi, u, v, mi))
        elif name == "FACE0000" and size == 12:
            for i in range(count):
                a, b, c, mi = struct.unpack_from("<HHHB", body, i * 12)
                faces.append((a, b, c, mi))
        elif name == "FACE3200" and size == 18:
            for i in range(count):
                a, b, c, mi = struct.unpack_from("<IIIB", body, i * 18)
                faces.append((a, b, c, mi))
        elif name == "MATT0000" and size >= 64:
            for i in range(count):
                mats.append(body[i * size:i * size + 64].split(b"\0")[0].decode("ascii", "replace"))
    if not points or not wedges or not faces:
        raise PSKError("no geometry in the file")
    by_mat: dict[int, M.Mesh] = {}
    remap: dict[tuple[int, int], int] = {}
    for a, b, c, mi in faces:
        m = by_mat.setdefault(mi, M.Mesh())
        tri = []
        for w in (a, b, c):
            key = (mi, w)
            if key not in remap:
                pi, u, v, _wm = wedges[w]
                remap[key] = len(m.positions)
                m.positions.append(points[pi])
                m.uvs.append((u, v))
            tri.append(remap[key])
        m.tris.append((tri[0], tri[1], tri[2]))
    out = []
    for mi in sorted(by_mat):
        out.append((by_mat[mi], mats[mi] if mi < len(mats) else f"material{mi}"))
    return out


def write(mesh: M.Mesh, material: str = "Mat") -> bytes:
    """A minimal PSK (for tests and tools): one material."""
    def chunk(name: str, size: int, records: list[bytes]) -> bytes:
        return name.encode().ljust(20, b"\0") + struct.pack("<III", 1999801, size, len(records)) + b"".join(records)

    uvs = mesh.uvs if len(mesh.uvs) == len(mesh.positions) else [(0.0, 0.0)] * len(mesh.positions)
    out = chunk("ACTRHEAD", 0, [])
    out += chunk("PNTS0000", 12, [struct.pack("<3f", *p) for p in mesh.positions])
    out += chunk("VTXW0000", 16, [struct.pack("<HxxffBxxx", i, uvs[i][0], uvs[i][1], 0) for i in range(len(mesh.positions))])
    out += chunk("FACE0000", 12, [struct.pack("<HHHBBI", a, b, c, 0, 0, 1) for a, b, c in mesh.tris])
    out += chunk("MATT0000", 88, [material.encode().ljust(64, b"\0") + struct.pack("<iIiIii", 0, 0, -1, 0, 0, 0)])
    return out
