"""python -m skylands_setup bl2textures [--bl2 DIR] [--work DIR] [--out FILE]: how Borderlands 2 paints its guns and relics (changes nothing).

Today the installer takes ONE texture per gun (the diffuse parameter of its Material part's material, a "Comp" texture) and, because that texture is
packed channels rather than a picture, keeps only its brightness tinted with a manufacturer colour (skyrim.dxt.shade): every gun is one solid colour
with a faint texture. Borderlands 2's own shader builds the paint from those channels plus colour/scalar parameters and more textures of the material
instance (manufacturer, rarity). Nothing about that material is known yet, so this survey writes it down:

  T1  the gun Material parts (from work\\pandora.json, the installer's own reading of the balances): per gun type x manufacturer x rarity, the part's
      Material, and that material's whole chain to the root: scalar, vector (colour) and texture parameters of every level
  T2  the root materials (the shader): their expression objects (class, parameter name, texture, constants, mask channels), so the way the channels
      are combined can be rebuilt
  T3  the gestalt meshes of the guns, shields and relics: the materials they refer to and what the mesh reader finds (UVs or not, UV range)
  T4  every texture named above (at most --max-textures): size, format, channel statistics; a PNG of the picture and of each channel R G B A
  T5  per gun type: the mesh's UV layout drawn over its Comp texture (does the layout match the texture?)
  T6  per material instance: a GUESS of the painted texture (mask channels x the instance's colours), to compare with the game

Everything is written to work\\gun-textures\\ and the report, and packed into work\\bl2-gun-textures.zip (send that one file).
"""

from __future__ import annotations

import json
import re
import struct
import time
import zipfile
import zlib
from pathlib import Path

from . import steam
from .bl2 import gunmesh, upk

CHANNELS = "RGBA"


# ---- images ---------------------------------------------------------------------------------------------------------

def _rgb565(v: int) -> tuple[int, int, int]:
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return (r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31


def decode_rgba(dds: bytes) -> tuple[int, int, bytearray]:
    """(width, height, RGBA bytes) of a DXT1/DXT5 DDS (alpha decoded too: DXT5's interpolated alpha block, DXT1's 1-bit)."""
    if dds[:4] != b"DDS ":
        raise ValueError("not a DDS file")
    h, w = struct.unpack_from("<II", dds, 12)
    fourcc, px = dds[84:88], dds[128:]
    if fourcc not in (b"DXT1", b"DXT5"):
        raise ValueError(f"unsupported format {fourcc!r}")
    per = 8 if fourcc == b"DXT1" else 16
    bw, bh = (w + 3) // 4, (h + 3) // 4
    out = bytearray(w * h * 4)
    for by in range(bh):
        for bx in range(bw):
            o = (by * bw + bx) * per
            alpha = [255] * 16
            if per == 16:
                a0, a1 = px[o], px[o + 1]
                bits = int.from_bytes(px[o + 2:o + 8], "little")
                if a0 > a1:
                    pal_a = [a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
                else:
                    pal_a = [a0, a1] + [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255]
                alpha = [pal_a[(bits >> (3 * k)) & 7] for k in range(16)]
                o += 8
            c0, c1, bits = struct.unpack_from("<HHI", px, o)
            p0, p1 = _rgb565(c0), _rgb565(c1)
            if c0 > c1 or per == 16:
                pal = [p0 + (255,), p1 + (255,), tuple((2 * a + b) // 3 for a, b in zip(p0, p1)) + (255,), tuple((a + 2 * b) // 3 for a, b in zip(p0, p1)) + (255,)]
            else:
                pal = [p0 + (255,), p1 + (255,), tuple((a + b) // 2 for a, b in zip(p0, p1)) + (255,), (0, 0, 0, 0)]
            for j in range(4):
                y = by * 4 + j
                if y >= h:
                    continue
                for i in range(4):
                    x = bx * 4 + i
                    if x >= w:
                        continue
                    k = 4 * j + i
                    c = pal[(bits >> (2 * k)) & 3]
                    q = (y * w + x) * 4
                    out[q:q + 4] = bytes((c[0], c[1], c[2], min(c[3], alpha[k])))
    return w, h, out


def shrink(w: int, h: int, rgba: bytes, side: int) -> tuple[int, int, bytearray]:
    step = 1
    while w // step > side or h // step > side:
        step *= 2
    ow, oh = max(1, w // step), max(1, h // step)
    out = bytearray(ow * oh * 4)
    for y in range(oh):
        row = (y * step) * w
        for x in range(ow):
            q = (row + x * step) * 4
            out[(y * ow + x) * 4:(y * ow + x) * 4 + 4] = rgba[q:q + 4]
    return ow, oh, out


def png(w: int, h: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\0" + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def channel_strip(w: int, h: int, rgba: bytes) -> tuple[int, int, bytearray]:
    """The picture (opaque) and its four channels as grey pictures, side by side."""
    W = w * 5
    out = bytearray(W * h * 4)
    for y in range(h):
        for x in range(w):
            q = (y * w + x) * 4
            r, g, b, a = rgba[q:q + 4]
            for k, v in enumerate(((r, g, b), (r, r, r), (g, g, g), (b, b, b), (a, a, a))):
                o = (y * W + k * w + x) * 4
                out[o:o + 4] = bytes((*v, 255))
    return W, h, out


def channel_stats(rgba: bytes) -> str:
    n = len(rgba) // 4
    step = max(1, n // 20000)
    parts = []
    for c in range(4):
        vals = rgba[c::4][::step]
        if not vals:
            continue
        lo, hi = min(vals), max(vals)
        mean = sum(vals) / len(vals)
        binary = sum(1 for v in vals if v < 24 or v > 231) / len(vals)
        parts.append(f"{CHANNELS[c]} min {lo} max {hi} mean {mean:.0f} near-0/255 {binary:.0%}")
    return "; ".join(parts)


def draw_uvs(w: int, h: int, rgba: bytearray, uvs, tris, colour=(255, 255, 255), cap: int = 40000) -> None:
    def put(x: int, y: int) -> None:
        if 0 <= x < w and 0 <= y < h:
            q = (y * w + x) * 4
            rgba[q:q + 4] = bytes((*colour, 255))

    def line(a, b) -> None:
        x0, y0 = a[0] % 1.0 * (w - 1), a[1] % 1.0 * (h - 1)
        x1, y1 = b[0] % 1.0 * (w - 1), b[1] % 1.0 * (h - 1)
        if abs(x1 - x0) > w / 2 or abs(y1 - y0) > h / 2:  # an edge across a tiling seam: skip
            return
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for k in range(n + 1):
            t = k / n
            put(int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t))

    for t in tris[:cap]:
        a, b, c = (uvs[i] for i in t)
        line(a, b)
        line(b, c)
        line(c, a)


# ---- properties ---------------------------------------------------------------------------------------------------------

def _items(value) -> list:
    if isinstance(value, dict):
        value = value.get("items", [])
    return value if isinstance(value, list) else []


def params_of(props: dict) -> dict:
    """{"scalar": {name: value}, "vector": {name: [r,g,b,a]}, "texture": {name: path}, "other": {...}} of one material instance level."""
    out = {"scalar": {}, "vector": {}, "texture": {}}
    for it in _items(props.get("ScalarParameterValues")):
        if isinstance(it, dict):
            out["scalar"][str(it.get("ParameterName"))] = it.get("ParameterValue")
    for it in _items(props.get("VectorParameterValues")):
        if isinstance(it, dict):
            out["vector"][str(it.get("ParameterName"))] = it.get("ParameterValue")
    for it in _items(props.get("TextureParameterValues")):
        if isinstance(it, dict):
            out["texture"][str(it.get("ParameterName"))] = it.get("ParameterValue")
    return out


def short(value, n: int = 140) -> str:
    if isinstance(value, list) and value and all(isinstance(v, float) for v in value):
        return "[" + ", ".join(f"{v:.3f}" for v in value) + "]"
    s = str(value)
    return s if len(s) <= n else s[:n] + "..."


# ---- the survey ---------------------------------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    import argparse

    from .bl2 import gunparts
    from .bl2.index import Index

    ap = argparse.ArgumentParser(prog="skylands bl2textures")
    ap.add_argument("--bl2")
    ap.add_argument("--work", default="work")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-textures", type=int, default=90)
    ap.add_argument("--minutes", type=float, default=30.0)
    a = ap.parse_args(argv)
    work = Path(a.work)
    out_path = Path(a.out) if a.out else work / "bl2-gun-texture-report.txt"
    img_dir = work / "gun-textures"
    img_dir.mkdir(parents=True, exist_ok=True)
    for old in img_dir.glob("*.png"):
        try:
            old.unlink()
        except OSError:
            pass
    stop_at = time.time() + a.minutes * 60
    lines = [f"skylands bl2textures 1  {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    images: list[Path] = []

    def say(msg: str) -> None:
        print(msg, flush=True)
        lines.append(msg)

    def save() -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_png(name: str, w: int, h: int, rgba: bytes) -> str:
        p = img_dir / (re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:110] + ".png")
        p.write_bytes(png(w, h, rgba))
        images.append(p)
        return p.name

    bl2 = Path(a.bl2) if a.bl2 else steam.find("bl2")
    if not bl2 or not bl2.is_dir():
        say(f"Borderlands 2 not found ({bl2}). Run with --bl2 \"D:\\path\\Borderlands 2\".")
        save()
        return 2
    say(f"Borderlands 2 folder: {bl2}")
    ix = Index(bl2, work / "cache" / "bl2_index.json", say)

    textures: dict[str, list[str]] = {}  # texture path -> who uses it (for the report)
    instances: dict[str, dict] = {}  # material instance path -> its merged parameters (child first)

    def want(tex, who: str) -> None:
        if isinstance(tex, str) and tex:
            textures.setdefault(tex, [])
            if len(textures[tex]) < 6:
                textures[tex].append(who)

    roots: dict[str, list[str]] = {}  # root material -> instances using it

    def chain(mat: str, who: str) -> dict:
        """Say the material's chain to its root; return the merged parameters (a child's value wins)."""
        if mat in instances:
            return instances[mat]
        merged = {"scalar": {}, "vector": {}, "texture": {}, "root": None, "levels": []}
        cur, depth = mat, 0
        while isinstance(cur, str) and cur and depth < 8:
            found = ix.get(cur)
            cls = found[0].obj_class(found[1]) if found else "?"
            props = ix.props(cur) or {}
            merged["levels"].append(f"{cur} ({cls})")
            say(f"    level {depth}: {cur}  class {cls}")
            if cls in ("Material", "?") or "Parent" not in props:
                merged["root"] = cur
                roots.setdefault(cur, [])
                if len(roots[cur]) < 8:
                    roots[cur].append(mat)
                other = {k: short(v, 90) for k, v in props.items() if k not in ("Expressions",)}
                say(f"      properties: {dict(list(other.items())[:20])}")
                break
            p = params_of(props)
            for kind in ("scalar", "vector", "texture"):
                for k, v in p[kind].items():
                    merged[kind].setdefault(k, v)
                    say(f"      {kind:7} {k} = {short(v)}")
                    if kind == "texture":
                        want(v, f"{mat} ({k})")
            other = {k: short(v, 90) for k, v in props.items() if k not in ("ScalarParameterValues", "VectorParameterValues", "TextureParameterValues", "Parent")}
            if other:
                say(f"      other: {dict(list(other.items())[:12])}")
            cur, depth = props.get("Parent"), depth + 1
        instances[mat] = merged
        return merged

    # ---- T1: the gun Material parts
    say("")
    say("== T1: gun Material parts (from work\\pandora.json) ==")
    guns = []
    pj = work / "pandora.json"
    try:
        guns = json.loads(pj.read_text(encoding="utf-8")).get("weapons", {}).get("guns", [])
        say(f"{len(guns)} gun balances in {pj}")
    except (OSError, ValueError) as e:
        say(f"{pj} could not be read ({type(e).__name__}): run the installer once first; looking for material parts by name instead")
    mats_by_key: dict[tuple, set[str]] = {}
    for g in guns:
        slots = g.get("slots") or {}
        for slot, opts in slots.items():
            if "material" in slot.lower():
                for p in opts:
                    mats_by_key.setdefault((g.get("type"), g.get("manufacturer"), g.get("rarity")), set()).add(p)
    if not mats_by_key:  # no pandora.json: material parts by their group names
        for key, entries in ix.groups.items():
            if "material" in key and key.startswith("gd_"):
                for f in ix.candidates(key)[:1]:
                    try:
                        pkg = ix.package(f)
                    except Exception:  # noqa: BLE001
                        continue
                    for i in pkg.children_of(key):
                        mats_by_key.setdefault(("?", key, "?"), set()).add(pkg.path_of(i))
    parts_seen: dict[str, str] = {}  # material part -> its Material
    per_type: dict[str, str] = {}  # gun type -> one instance (for T5)
    for key in sorted(mats_by_key, key=lambda k: tuple(str(x) for x in k)):
        if time.time() > stop_at:
            say("time is up (T1)")
            break
        say(f"-- {key[0]} / {key[1]} / {key[2]}: {len(mats_by_key[key])} material part(s)")
        for part in sorted(mats_by_key[key])[:6]:
            if part in parts_seen:
                say(f"  {part} -> {parts_seen[part]} (above)")
                continue
            props = ix.props(part) or {}
            mat = props.get("Material")
            parts_seen[part] = str(mat)
            say(f"  part {part}: Material {mat}; other {dict(list({k: short(v, 70) for k, v in props.items() if k != 'Material'}.items())[:8])}")
            if isinstance(mat, str):
                chain(mat, part)
                per_type.setdefault(str(key[0]), mat)
        save()

    # ---- T3: gestalt meshes (guns, shields, relics)
    say("")
    say("== T3: gestalt meshes and their materials ==")
    src = gunparts.Bl2Source(ix, lambda m: None)
    src.log = lambda msg, force=False: say(f"  {msg}")
    say(f"looking through {len(ix.files)} package name tables for gestalt definitions ...")
    for n_f, f in enumerate(ix.files):  # the installer's own test (gunparts.prepare)
        try:
            names = upk.read_name_set(f)
        except Exception:  # noqa: BLE001
            continue
        if "gestaltskeletalmeshdefinition" in names and any(n.startswith("gestaltdef_") for n in names) and ("startup" in f.stem.lower() or "gestaltdef_shields" in names or "gestaltdef_artifact" in names):
            src.gestalt_files.append(f)
        if n_f % 400 == 399:
            print(f"  {n_f + 1}/{len(ix.files)} name tables", flush=True)
    say(f"gestalt packages: {[f.name for f in src.gestalt_files]}")
    try:
        src._load_gestalt_defs()
    except Exception as e:  # noqa: BLE001
        say(f"gestalt definitions could not be read: {type(e).__name__}: {str(e)[:100]}")
    meshes: dict[str, tuple] = {}  # mesh key -> (mesh, material paths)
    for key, info in src.gestalt_meshes.items():
        if time.time() > stop_at:
            say("time is up (T3)")
            break
        try:
            pkg = ix.package(info["file"])
            idx = pkg.find(info["path"])
            data = pkg.export_data(idx) if idx else b""
            props_end = 4
            for start in (4, 0, 8):
                try:
                    _p, props_end = upk.read_properties(pkg, data, start)
                    break
                except Exception:  # noqa: BLE001
                    continue
            mats = gunmesh.material_refs(pkg, data, props_end) if data else []
            raw = gunmesh.read_mesh_blob(data, props_end, info["path"]) if data else None
            say(f"- {info['path']} ({info['file'].name}, {len(data)} bytes): materials {mats}")
            if raw is None:
                say("    no geometry found")
                continue
            m = raw.mesh
            say(f"    {raw.note}")
            if m.uvs:
                us, vs = [u for u, _ in m.uvs], [v for _, v in m.uvs]
                say(f"    uv range u {min(us):.3f}..{max(us):.3f}, v {min(vs):.3f}..{max(vs):.3f}")
            meshes[key] = (m, mats, info["path"])
            for mat in mats:
                say(f"  material {mat}:")
                chain(mat, info["path"])
                low = info["path"].lower()
                kind = "shield" if "shield" in low else "relic" if "artifact" in low else None
                if kind:
                    per_type.setdefault(kind, mat)
        except Exception as e:  # noqa: BLE001
            say(f"- {info['path']}: {type(e).__name__}: {str(e)[:120]}")
        save()

    # ---- T2: the root materials (the shader)
    say("")
    say("== T2: root materials and their expressions ==")
    for root, users in roots.items():
        if time.time() > stop_at:
            say("time is up (T2)")
            break
        say(f"- {root} (used by {users[:3]})")
        props = ix.props(root) or {}
        exprs = [e for e in _items(props.get("Expressions")) if isinstance(e, str)]
        if not exprs:
            try:
                exprs = list(ix.children(root))
            except Exception:  # noqa: BLE001
                exprs = []
        say(f"  {len(exprs)} expressions; material inputs: {dict(list({k: short(v, 100) for k, v in props.items() if k != 'Expressions'}.items())[:24])}")
        for e in exprs[:320]:
            found = ix.get(e)
            cls = found[0].obj_class(found[1]) if found else "?"
            ep = ix.props(e) or {}
            keep = {k: short(v, 220) for k, v in ep.items() if k not in ("MaterialExpressionEditorX", "MaterialExpressionEditorY", "Material", "EditorX", "EditorY")}
            say(f"    {e.rsplit('.', 1)[-1]} [{cls}] {keep}")
            if isinstance(ep.get("Texture"), str):
                want(ep["Texture"], f"{root} expression {e.rsplit('.', 1)[-1]}")
        save()

    # ---- T4: textures
    say("")
    say(f"== T4: textures ({len(textures)} named; at most {a.max_textures} read) ==")
    decoded: dict[str, tuple[int, int, bytearray]] = {}
    order = sorted(textures, key=lambda t: (0 if "comp" in t.lower() else 1, t))
    for tex in order[:a.max_textures]:
        if time.time() > stop_at:
            say("time is up (T4)")
            break
        props = ix.props(tex) or {}
        info = f"{props.get('SizeX')}x{props.get('SizeY')} {props.get('Format')}, sRGB {props.get('SRGB')}, group {props.get('LODGroup')}, compression {props.get('CompressionSettings')}"
        dds = gunmesh.read_texture(ix, tex, ix.root, lambda m: say(f"    {m}"), max_dim=512)
        if dds is None:
            say(f"- {tex}: {info}; NOT read (used by {textures[tex][:2]})")
            continue
        try:
            w, h, rgba = decode_rgba(dds)
        except Exception as e:  # noqa: BLE001
            say(f"- {tex}: {info}; not decoded ({e})")
            continue
        decoded[tex] = (w, h, rgba)
        sw, sh, small = shrink(w, h, rgba, 256)
        name = write_png("tex_" + tex, *channel_strip(sw, sh, small))
        say(f"- {tex}: {info}; read at {w}x{h}; {channel_stats(rgba)}; picture {name} (colour, R, G, B, A); used by {textures[tex][:3]}")
        save()

    # ---- T5: UV layouts over the textures
    say("")
    say("== T5: UV layouts drawn over the mesh's texture ==")
    for key, (m, mats, path) in meshes.items():
        if not m.uvs:
            say(f"- {path}: no UVs read")
            continue
        tex = None
        for mat in mats:
            p = instances.get(mat) or {}
            for name, t in (p.get("texture") or {}).items():
                if t in decoded and ("comp" in t.lower() or "dif" in t.lower() or "diff" in name.lower()):
                    tex = t
                    break
            if tex:
                break
        if tex is None:  # the gun type's Material part's texture
            low = path.lower()
            for gtype, mat in per_type.items():
                if gtype and gtype.split("_")[0][:4] in low:
                    for t in (instances.get(mat) or {}).get("texture", {}).values():
                        if t in decoded:
                            tex = t
                            break
        if tex is None:
            w = h = 512
            rgba = bytearray(b"\x20\x20\x20\xff" * (w * h))
        else:
            w, h, rgba = shrink(*decoded[tex], 512)
            rgba = bytearray(rgba)
        draw_uvs(w, h, rgba, m.uvs, m.tris)
        name = write_png("uv_" + path, w, h, rgba)
        say(f"- {path}: {len(m.tris)} triangles over {tex or 'grey'} -> {name}")
    save()

    # ---- T6: guessed paint per material instance
    say("")
    say("== T6: guessed paint (mask channels R/G/B of the instance's first packed texture x its first three colours) ==")
    made = 0
    for mat, p in instances.items():
        if made >= 40 or time.time() > stop_at:
            break
        texs = [t for t in (p.get("texture") or {}).values() if t in decoded]
        cols = [(k, v) for k, v in (p.get("vector") or {}).items() if isinstance(v, list) and len(v) >= 3]
        if not texs or not cols:
            continue
        w, h, rgba = shrink(*decoded[texs[0]], 256)
        out = bytearray(len(rgba))
        cs = [c for _, c in cols[:3]] + [[0.5, 0.5, 0.5]] * (3 - min(3, len(cols)))
        for q in range(0, len(rgba), 4):
            acc = [0.0, 0.0, 0.0]
            for ch in range(3):
                mval = rgba[q + ch] / 255.0
                for k in range(3):
                    acc[k] += mval * cs[ch][k]
            out[q:q + 4] = bytes((*(max(0, min(255, int(v * 255))) for v in acc), 255))
        name = write_png("guess_" + mat, w, h, out)
        made += 1
        say(f"- {mat}: {texs[0]} x colours {[k for k, _ in cols[:3]]} -> {name}")
    save()

    # ---- pack
    zpath = work / "bl2-gun-textures.zip"
    say("")
    say(f"Packing the report and {len(images)} pictures into {zpath}")
    save()
    try:
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(out_path, out_path.name)
            for p in images:
                z.write(p, "gun-textures/" + p.name)
    except OSError as e:
        say(f"{zpath} could not be written: {e}")
    save()
    return 0
