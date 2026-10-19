"""A plain triangle mesh and the few operations the gun models need (move, scale, rotate, merge, tangents, primitives).

Everything the model methods produce (the Borderlands 2 package reader, the UModel bridge, the proxy builder) ends up as
these, and everything the NIF writer takes is these. Units are whatever the source used until `fit` scales them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

Vec = tuple[float, float, float]


@dataclass
class Mesh:
    positions: list[Vec] = field(default_factory=list)
    normals: list[Vec] = field(default_factory=list)  # empty: computed from the triangles
    uvs: list[tuple[float, float]] = field(default_factory=list)  # empty: zeros
    tris: list[tuple[int, int, int]] = field(default_factory=list)
    texture: str | None = None  # key of the diffuse texture (the caller maps keys to files)
    normal_map: str | None = None
    tint: tuple[int, int, int] | None = None  # multiplies the diffuse when the texture is a flat colour

    def copy(self) -> "Mesh":
        return Mesh(list(self.positions), list(self.normals), list(self.uvs), list(self.tris), self.texture, self.normal_map, self.tint)

    def bounds(self) -> tuple[Vec, Vec]:
        if not self.positions:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        xs, ys, zs = zip(*self.positions)
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def transformed(m: Mesh, matrix: tuple[Vec, Vec, Vec] | None = None, scale: float = 1.0, offset: Vec = (0.0, 0.0, 0.0)) -> Mesh:
    """p' = matrix * p * scale + offset; normals use the matrix only. `matrix` rows are the new x, y, z axes' components."""
    out = m.copy()
    mx = matrix or ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

    def rot(v: Vec) -> Vec:
        return (mx[0][0] * v[0] + mx[0][1] * v[1] + mx[0][2] * v[2],
                mx[1][0] * v[0] + mx[1][1] * v[1] + mx[1][2] * v[2],
                mx[2][0] * v[0] + mx[2][1] * v[1] + mx[2][2] * v[2])

    out.positions = [(rot(p)[0] * scale + offset[0], rot(p)[1] * scale + offset[1], rot(p)[2] * scale + offset[2]) for p in m.positions]
    out.normals = [rot(n) for n in m.normals]
    if det3(mx) < 0:  # a mirror flips the winding
        out.tris = [(a, c, b) for a, b, c in m.tris]
    return out


def det3(m: tuple[Vec, Vec, Vec]) -> float:
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def merged(meshes: list[Mesh]) -> Mesh:
    """One mesh from several that share a texture (the caller groups by texture first)."""
    out = Mesh(texture=meshes[0].texture if meshes else None, normal_map=meshes[0].normal_map if meshes else None,
               tint=meshes[0].tint if meshes else None)
    for m in meshes:
        base = len(out.positions)
        out.positions += m.positions
        out.normals += m.normals if len(m.normals) == len(m.positions) else [(0.0, 0.0, 0.0)] * len(m.positions)
        out.uvs += m.uvs if len(m.uvs) == len(m.positions) else [(0.0, 0.0)] * len(m.positions)
        out.tris += [(a + base, b + base, c + base) for a, b, c in m.tris]
    return out


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(v: Vec) -> Vec:
    n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    return (v[0] / n, v[1] / n, v[2] / n) if n > 1e-12 else (0.0, 0.0, 1.0)


def signed_volume(m: Mesh) -> float:
    v = 0.0
    for a, b, c in m.tris:
        p, q, r = m.positions[a], m.positions[b], m.positions[c]
        v += (p[0] * (q[1] * r[2] - q[2] * r[1]) - p[1] * (q[0] * r[2] - q[2] * r[0]) + p[2] * (q[0] * r[1] - q[1] * r[0])) / 6.0
    return v


def ensure_outward(m: Mesh) -> Mesh:
    """Flip the winding when the mesh is inside out (negative enclosed volume); a no-op for outward meshes."""
    if signed_volume(m) >= 0:
        return m
    out = m.copy()
    out.tris = [(a, c, b) for a, b, c in m.tris]
    out.normals = [(-n[0], -n[1], -n[2]) for n in m.normals]
    return out


def with_normals(m: Mesh) -> Mesh:
    """Smooth vertex normals from the triangles when the mesh has none (or have the wrong count)."""
    if len(m.normals) == len(m.positions) and any(n != (0.0, 0.0, 0.0) for n in m.normals):
        return m
    acc = [[0.0, 0.0, 0.0] for _ in m.positions]
    for a, b, c in m.tris:
        n = cross(sub(m.positions[b], m.positions[a]), sub(m.positions[c], m.positions[a]))
        for i in (a, b, c):
            for k in range(3):
                acc[i][k] += n[k]
    out = m.copy()
    out.normals = [norm((v[0], v[1], v[2])) for v in acc]
    return out


def tangents(m: Mesh) -> list[tuple[Vec, float]]:
    """(tangent, handedness) per vertex from the UVs; a fixed axis when the UVs are missing."""
    n = len(m.positions)
    tan = [[0.0, 0.0, 0.0] for _ in range(n)]
    bit = [[0.0, 0.0, 0.0] for _ in range(n)]
    uvs = m.uvs if len(m.uvs) == n else [(0.0, 0.0)] * n
    for a, b, c in m.tris:
        e1, e2 = sub(m.positions[b], m.positions[a]), sub(m.positions[c], m.positions[a])
        du1, dv1 = uvs[b][0] - uvs[a][0], uvs[b][1] - uvs[a][1]
        du2, dv2 = uvs[c][0] - uvs[a][0], uvs[c][1] - uvs[a][1]
        det = du1 * dv2 - du2 * dv1
        if abs(det) < 1e-12:
            continue
        r = 1.0 / det
        t = ((e1[0] * dv2 - e2[0] * dv1) * r, (e1[1] * dv2 - e2[1] * dv1) * r, (e1[2] * dv2 - e2[2] * dv1) * r)
        bt = ((e2[0] * du1 - e1[0] * du2) * r, (e2[1] * du1 - e1[1] * du2) * r, (e2[2] * du1 - e1[2] * du2) * r)
        for i in (a, b, c):
            for k in range(3):
                tan[i][k] += t[k]
                bit[i][k] += bt[k]
    out = []
    normals = m.normals if len(m.normals) == n else [(0.0, 0.0, 1.0)] * n
    for i in range(n):
        nv = normals[i]
        t = tan[i]
        d = nv[0] * t[0] + nv[1] * t[1] + nv[2] * t[2]
        tv = norm((t[0] - nv[0] * d, t[1] - nv[1] * d, t[2] - nv[2] * d)) if any(t) else norm(cross(nv, (0.0, 0.0, 1.0)) if abs(nv[2]) < 0.9 else (1.0, 0.0, 0.0))
        bv = cross(nv, tv)
        hand = -1.0 if (bv[0] * bit[i][0] + bv[1] * bit[i][1] + bv[2] * bit[i][2]) < 0 else 1.0
        out.append((tv, hand))
    return out


# ---- primitives (the proxy guns and the tests) -------------------------------------------------------------------

def box(cx: float, cy: float, cz: float, sx: float, sy: float, sz: float, texture: str | None = None) -> Mesh:
    """An axis-aligned box centred at (cx, cy, cz) with full sizes (sx, sy, sz); 24 vertices (flat faces), UVs per face."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    faces = [  # normal, u axis, v axis
        ((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
        ((0, 1, 0), (-1, 0, 0), (0, 0, 1)), ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
        ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (1, 0, 0), (0, -1, 0)),
    ]
    m = Mesh(texture=texture)
    half = (hx, hy, hz)
    for n, u, v in faces:
        base = len(m.positions)
        for su, sv, uu, vv in ((-1, -1, 0, 1), (1, -1, 1, 1), (1, 1, 1, 0), (-1, 1, 0, 0)):
            p = tuple(cc + (n[k] + u[k] * su + v[k] * sv) * half[k] for k, cc in enumerate((cx, cy, cz)))
            m.positions.append(p)  # type: ignore[arg-type]
            m.normals.append((float(n[0]), float(n[1]), float(n[2])))
            m.uvs.append((float(uu), float(vv)))
        m.tris += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
        # make the winding face outward
        a, b, c = (m.positions[base + i] for i in range(3))
        if sum(x * y for x, y in zip(cross(sub(b, a), sub(c, a)), n)) < 0:
            m.tris[-2:] = [(base, base + 2, base + 1), (base, base + 3, base + 2)]
    return m


def cylinder(cx: float, cy: float, cz: float, radius: float, length: float, axis: int = 1, sides: int = 12, texture: str | None = None) -> Mesh:
    """A capped cylinder along `axis` (0 x, 1 y, 2 z) centred at (cx, cy, cz)."""
    m = Mesh(texture=texture)
    a1, a2 = [i for i in range(3) if i != axis]
    c = (cx, cy, cz)

    def pt(ang: float, along: float, r: float) -> Vec:
        p = [c[0], c[1], c[2]]
        p[axis] += along
        p[a1] += math.cos(ang) * r
        p[a2] += math.sin(ang) * r
        return (p[0], p[1], p[2])

    for i in range(sides + 1):
        ang = 2 * math.pi * i / sides
        for along in (-length / 2, length / 2):
            m.positions.append(pt(ang, along, radius))
            nv = [0.0, 0.0, 0.0]
            nv[a1], nv[a2] = math.cos(ang), math.sin(ang)
            m.normals.append((nv[0], nv[1], nv[2]))
            m.uvs.append((i / sides, 0.0 if along < 0 else 1.0))
    for i in range(sides):
        a, b = 2 * i, 2 * i + 2
        m.tris += [(a, b, a + 1), (b, b + 1, a + 1)]
    for sign in (1, -1):
        base = len(m.positions)
        nv = [0.0, 0.0, 0.0]
        nv[axis] = float(sign)
        m.positions.append(pt(0.0, sign * length / 2, 0.0))
        m.normals.append((nv[0], nv[1], nv[2]))
        m.uvs.append((0.5, 0.5))
        for i in range(sides + 1):
            ang = 2 * math.pi * i / sides
            m.positions.append(pt(ang, sign * length / 2, radius))
            m.normals.append((nv[0], nv[1], nv[2]))
            m.uvs.append((0.5 + math.cos(ang) / 2, 0.5 + math.sin(ang) / 2))
        for i in range(sides):
            m.tris.append((base, base + 1 + i, base + 2 + i) if sign > 0 else (base, base + 2 + i, base + 1 + i))
    # outward winding check for the side wall
    for k, (a, b, c3) in enumerate(m.tris[: 2 * sides]):
        pa, pb, pc = m.positions[a], m.positions[b], m.positions[c3]
        nrm = cross(sub(pb, pa), sub(pc, pa))
        if sum(x * y for x, y in zip(nrm, m.normals[a])) < 0:
            m.tris[k] = (a, c3, b)
    return m
