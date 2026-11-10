"""Borderlands 2's gun paint, rebuilt from the game's own material (0.63.0).

Read from the texture survey (work\\bl2-gun-texture-report.txt of TestBuild-188): every gun's Material part names a MaterialInstanceConstant whose chain
ends at Common_Materials.Weapons.Master_Gun. Its parameters:
  p_Masks     per gun type (Weap_SMG.Tex.Weap_SMG_Comp ...): R / G / B = paint regions A / B / C (soft in places; where all three are ~0 the region is D)
  p_Diffuse   a shared shading atlas, one gun type per channel (static mask p_WeapClassSelect): Weap_AssaultSubSniper_Comp R assault rifle, G SMG,
              B sniper; Weap_LauncherShotgunPistol_Comp R launcher, G shotgun, B pistol (checked: the type's UV seams follow that channel's edges)
  p_AColorShadow/Midtone/Hilight (and B, C): the region's colour at dark / middle / bright shading (linear colour, may exceed 1); p_DColor for region D
  p_Pattern (channel R) x p_PatternColor, tiled by p_PatternScalePosition (scale x y, offset z w), applied to the regions by p_PatternChannelScale (x A, y B, z C)
  p_Decal, P_SimpleReflect, p_NormalScopesEmissive: not used here (logos, reflections, normals)
The shader's wiring is compiled away in the cooked files, so the mix below is a reconstruction (Bone Shredder: bone white and slate, as in the game).
"""

from __future__ import annotations

import hashlib
import struct

from . import gunmesh

# gun type -> (shading atlas word, channel)
CLASS_CHANNEL = {"assault_rifle": 0, "smg": 1, "sniper": 2, "launcher": 0, "shotgun": 1, "pistol": 2}
SIDE = 512  # painted texture size


def _items(value) -> list:
    if isinstance(value, dict):
        value = value.get("items", [])
    return value if isinstance(value, list) else []


def material_params(ix, mic: str, depth: int = 0) -> dict:
    """{"scalar": {...}, "vector": {...}, "texture": {...}} of a material instance and its parents (lower case names; a child's value wins)."""
    out = {"scalar": {}, "vector": {}, "texture": {}}
    if not mic or depth > 6:
        return out
    props = ix.props(mic) or {}
    for key, kind in (("ScalarParameterValues", "scalar"), ("VectorParameterValues", "vector"), ("TextureParameterValues", "texture")):
        for it in _items(props.get(key)):
            if isinstance(it, dict) and it.get("ParameterName") is not None:
                out[kind].setdefault(str(it["ParameterName"]).lower(), it.get("ParameterValue"))
    parent = props.get("Parent")
    if isinstance(parent, str):
        up = material_params(ix, parent, depth + 1)
        for kind in out:
            for k, v in up[kind].items():
                out[kind].setdefault(k, v)
    return out


def decode_rgb(dds: bytes, side: int) -> tuple[int, int, bytes] | None:
    """A DXT DDS as RGB at side x side (nearest pixel), or None."""
    from ..skyrim import dxt

    w, h, rgb = dxt.decode(dds)
    if w < 4 or h < 4:
        return None
    if (w, h) == (side, side):
        return w, h, bytes(rgb)
    out = bytearray(side * side * 3)
    for y in range(side):
        row = (y * h // side) * w
        for x in range(side):
            q = (row + x * w // side) * 3
            o = (y * side + x) * 3
            out[o:o + 3] = rgb[q:q + 3]
    return side, side, bytes(out)


def _colour(v, default=(1.0, 1.0, 1.0)) -> tuple[float, float, float]:
    if isinstance(v, list) and len(v) >= 3 and all(isinstance(x, (int, float)) for x in v[:3]):
        return float(v[0]), float(v[1]), float(v[2])
    return default


def _tone_lut(shadow, mid, hi) -> list[tuple[float, float, float]]:
    out = []
    for i in range(256):
        d = i / 255.0
        if d < 0.5:
            t = d * 2
            out.append(tuple(s + (m - s) * t for s, m in zip(shadow, mid)))
        else:
            t = d * 2 - 1
            out.append(tuple(m + (h - m) * t for m, h in zip(mid, hi)))
    return out


GAMMA = bytes(min(255, int(round(255 * (i / 1023.0) ** (1 / 2.2)))) for i in range(1024))  # linear 0..1 in 1024 steps -> sRGB byte


class Painter:
    """Paints one texture per gun material; textures it reads are kept for the next gun of the type."""

    def __init__(self, ix, tfc_dir, say) -> None:
        self.ix, self.tfc_dir, self.say = ix, tfc_dir, say
        self.images: dict[tuple[str, int], tuple | None] = {}  # (texture path, side) -> (w, h, rgb)
        self.layers: dict[tuple[str, str, int], tuple | None] = {}  # (masks, atlas, channel) -> per-pixel weights and shade
        self.notes = 0

    def _image(self, path: str, side: int):
        key = (path, side)
        if key not in self.images:
            img = None
            try:
                dds = gunmesh.read_texture(self.ix, path, self.tfc_dir, lambda m: None, max_dim=side)
                img = decode_rgb(dds, side) if dds else None
            except Exception as e:  # noqa: BLE001
                self.say(f"gun paint: texture {path} could not be read ({type(e).__name__}: {str(e)[:80]})")
            self.images[key] = img
        return self.images[key]

    def _layers(self, masks: str, atlas: str, channel: int):
        key = (masks, atlas, channel)
        if key in self.layers:
            return self.layers[key]
        m = self._image(masks, SIDE)
        a = self._image(atlas, SIDE)
        result = None
        if m and a:
            mr = m[2]
            ar = a[2]
            n = SIDE * SIDE
            wa, wb, wc, wd, shade = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n, bytearray(n)
            for i in range(n):
                r, g, b = mr[3 * i], mr[3 * i + 1], mr[3 * i + 2]
                s = r + g + b
                shade[i] = ar[3 * i + channel]
                if s < 3:
                    wd[i] = 1.0
                    continue
                d = 1.0 - s / 25.5 if s < 25.5 else 0.0  # nearly no mask: fade to region D
                k = (1.0 - d) / s
                wa[i], wb[i], wc[i], wd[i] = r * k, g * k, b * k, d
            result = (wa, wb, wc, wd, bytes(shade))
        self.layers[key] = result
        return result

    def paint(self, mic: str, gun_type: str) -> tuple[bytes, str] | None:
        """(DXT1 DDS, note) of the gun material `mic` for a gun of `gun_type`, or None (then the caller falls back)."""
        p = material_params(self.ix, mic)
        tex, vec = p["texture"], p["vector"]
        masks, atlas = tex.get("p_masks"), tex.get("p_diffuse")
        channel = CLASS_CHANNEL.get(gun_type)
        if not isinstance(masks, str) or not isinstance(atlas, str) or channel is None:
            return None
        if "comp" not in atlas.lower() or "stub" in masks.lower():  # not the gun shader's layout
            return None
        lay = self._layers(masks, atlas, channel)
        if lay is None:
            return None
        wa, wb, wc, wd, shade = lay
        luts = [_tone_lut(_colour(vec.get(f"p_{r}colorshadow")), _colour(vec.get(f"p_{r}colormidtone")), _colour(vec.get(f"p_{r}colorhilight"))) for r in "abc"]
        dcol = _colour(vec.get("p_dcolor"))
        la, lb, lc = luts
        n = SIDE * SIDE
        # pattern
        pat = None
        ptex = tex.get("p_pattern")
        pcs = _colour(vec.get("p_patternchannelscale"), (0.0, 0.0, 0.0))
        if isinstance(ptex, str) and "stub" not in ptex.lower() and any(pcs):
            img = self._image(ptex, 256)
            if img:
                pat = img
        pcol = _colour(vec.get("p_patterncolor"))
        sp = vec.get("p_patternscaleposition")
        sx, sy, ox, oy = (float(sp[0]), float(sp[1]), float(sp[2]), float(sp[3])) if isinstance(sp, list) and len(sp) >= 4 else (1.0, 1.0, 0.0, 0.0)
        out = bytearray(n * 3)
        for i in range(n):
            di = shade[i]
            a, b, c, dd = wa[i], wb[i], wc[i], wd[i]
            ta, tb, tc = la[di], lb[di], lc[di]
            ds = di / 255.0
            r = a * ta[0] + b * tb[0] + c * tc[0] + dd * dcol[0] * ds
            g = a * ta[1] + b * tb[1] + c * tc[1] + dd * dcol[1] * ds
            bl = a * ta[2] + b * tb[2] + c * tc[2] + dd * dcol[2] * ds
            if pat is not None:
                w = a * pcs[0] + b * pcs[1] + c * pcs[2]
                if w > 0.01:
                    y, x = divmod(i, SIDE)
                    pu = int(((x / SIDE) * sx + ox) % 1.0 * 256) & 255
                    pv = int(((y / SIDE) * sy + oy) % 1.0 * 256) & 255
                    pv_ = pat[2][(pv * 256 + pu) * 3] / 255.0
                    r *= 1 - w + w * pv_ * pcol[0]
                    g *= 1 - w + w * pv_ * pcol[1]
                    bl *= 1 - w + w * pv_ * pcol[2]
            o = 3 * i
            out[o] = GAMMA[min(1023, max(0, int(r * 1023)))]
            out[o + 1] = GAMMA[min(1023, max(0, int(g * 1023)))]
            out[o + 2] = GAMMA[min(1023, max(0, int(bl * 1023)))]
        dds = encode_fast(SIDE, SIDE, bytes(out))
        note = f"masks {masks.rsplit('.', 1)[-1]}, shading {atlas.rsplit('.', 1)[-1]} channel {'RGB'[channel]}, pattern {ptex.rsplit('.', 1)[-1] if pat else 'none'}"
        return dds, note


def key_of(mic: str, gun_type: str) -> str:
    return "p_" + hashlib.sha1(f"{mic}|{gun_type}".lower().encode()).hexdigest()[:10]


def _565(r: int, g: int, b: int) -> int:
    return ((r * 31 + 127) // 255 << 11) | ((g * 63 + 127) // 255 << 5) | ((b * 31 + 127) // 255)


def encode_fast(w: int, h: int, rgb: bytes) -> bytes:
    """An opaque DXT1 DDS: per 4x4 block the darkest and brightest pixel (by luminance) are the ends, each pixel takes the nearest of the four
    steps along that line by its luminance (faster than the nearest colour, nearly as good for painted metal)."""
    out = bytearray()
    pack = struct.pack
    for by in range(h // 4):
        for bx in range(w // 4):
            px = []
            for j in range(4):
                o = ((by * 4 + j) * w + bx * 4) * 3
                row = rgb[o:o + 12]
                px += [(row[0], row[1], row[2]), (row[3], row[4], row[5]), (row[6], row[7], row[8]), (row[9], row[10], row[11])]
            lum = [3 * p[0] + 6 * p[1] + p[2] for p in px]
            lo_l, hi_l = min(lum), max(lum)
            hi, lo = px[lum.index(hi_l)], px[lum.index(lo_l)]
            a, b = _565(*hi), _565(*lo)
            if a == b or hi_l == lo_l:
                out += pack("<HHI", a, a, 0)
                continue
            if a < b:  # keep the four-colour mode (a > b): swap the ends
                a, b = b, a
                lo_l, hi_l = hi_l, lo_l
            span = hi_l - lo_l
            bits = 0
            for k, l_ in enumerate(lum):
                t = (l_ - lo_l) / span  # 0 at b's end (index 1), 1 at a's end (index 0)
                idx = 0 if t > 5 / 6 else 2 if t > 0.5 else 3 if t > 1 / 6 else 1
                bits |= idx << (2 * k)
            out += pack("<HHI", a, b, bits)
    header = b"DDS " + struct.pack("<7I", 124, 0x1007 | 0x80000, h, w, len(out), 0, 1) + b"\0" * 44
    header += struct.pack("<II4s5I", 32, 4, b"DXT1", 0, 0, 0, 0, 0) + struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    return header + bytes(out)
