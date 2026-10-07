"""Turn the player's Skyrim SE install into the data Skylands plays with.

Everything here is read from the player's own files at runtime (sheet: skyrim_reads).
The result is plain JSON-able dicts, cached next to the mod so later launches are instant.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from .bsa import BSA, BSAError
from .esm import Record, is_localized, read_plugin
from .strings import parse_table

WANTED = {"AVIF", "PERK", "RACE", "SHOU", "WOOP", "GMST"}
GMST_WANTED = ("fXPLevelUpBase", "fXPLevelUpMult", "fXPPerSkillRank", "fSkillUseCurve", "iAVDSkillStart")
GREETING_PREFIX = "Hey, you. You're finally awake"
CACHE_VERSION = 1

# CTDA condition functions that test a skill level.
FN_GET_ACTOR_VALUE = 14
FN_GET_BASE_ACTOR_VALUE = 277


class SkyrimNotFound(FileNotFoundError):
    pass


def find_esm(skyrim_dir: Path) -> Path:
    for candidate in (skyrim_dir / "Data" / "Skyrim.esm", skyrim_dir / "Skyrim.esm"):
        if candidate.is_file():
            return candidate
    raise SkyrimNotFound(f"Skyrim.esm not found under {skyrim_dir}")


class StringTables:
    """Find skyrim_<language>.strings/.dlstrings/.ilstrings loose or inside the archives."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.language = ""
        self._sources: dict[str, object] = {}  # ext -> Path | (BSA, inner path)
        self._tables: dict[str, dict[int, str]] = {}
        self._discover()

    def _discover(self) -> None:
        found: dict[str, dict[str, object]] = {}  # language -> ext -> source
        loose = self.data_dir / "Strings"
        if loose.is_dir():
            for p in loose.iterdir():
                name = p.name.lower()
                if name.startswith("skyrim_") and "." in name:
                    lang, ext = name[7:].rsplit(".", 1)
                    found.setdefault(lang, {})[ext] = p
        archives = sorted(self.data_dir.glob("Skyrim - *.bsa"), key=lambda p: "interface" not in p.name.lower())
        for path in archives:
            try:
                bsa = BSA(path)
            except (BSAError, OSError):
                continue
            for inner in bsa.entries:
                if inner.startswith("strings\\skyrim_"):
                    lang, ext = inner[len("strings\\skyrim_") :].rsplit(".", 1)
                    found.setdefault(lang, {}).setdefault(ext, (bsa, inner))
        complete = [lang for lang, exts in found.items() if {"strings", "dlstrings"} <= set(exts)]
        if not complete:
            return
        self.language = "english" if "english" in complete else sorted(complete)[0]
        self._sources = found[self.language]

    @property
    def available(self) -> bool:
        return bool(self.language)

    def table(self, ext: str) -> dict[int, str]:
        if ext not in self._tables:
            src = self._sources.get(ext)
            if src is None:
                self._tables[ext] = {}
            else:
                raw = src.read_bytes() if isinstance(src, Path) else src[0].read(src[1])
                self._tables[ext] = parse_table(raw, length_prefixed=(ext != "strings"))
        return self._tables[ext]


class Text:
    """Resolve a text subrecord: a string id in localized plugins, inline text otherwise."""

    def __init__(self, localized: bool, tables: StringTables | None) -> None:
        self.localized = localized
        self.tables = tables

    def get(self, data: bytes | None, ext: str = "strings") -> str:
        if not data:
            return ""
        if self.localized:
            if len(data) < 4 or self.tables is None:
                return ""
            (sid,) = struct.unpack_from("<I", data, 0)
            return self.tables.table(ext).get(sid, "") if sid else ""
        return data.rstrip(b"\0").decode("cp1252", errors="replace")


def _f32(data: bytes, off: int = 0) -> float:
    return struct.unpack_from("<f", data, off)[0]


def _u32(data: bytes, off: int = 0) -> int:
    return struct.unpack_from("<I", data, off)[0]


def read_skill_requirement(perk: Record) -> int:
    """Highest 'skill >= n' requirement among a perk's conditions (0 when none)."""
    best = 0
    for c in perk.all("CTDA"):
        if len(c) < 16:
            continue
        op = c[0] >> 5
        uses_global = c[0] & 0x04
        func = struct.unpack_from("<H", c, 8)[0]
        if func in (FN_GET_ACTOR_VALUE, FN_GET_BASE_ACTOR_VALUE) and op in (2, 3) and not uses_global:
            value = int(round(_f32(c, 4)))
            best = max(best, value + (1 if op == 2 else 0))
    return best


def read_perk_tree(avif: Record) -> list[dict]:
    """AVIF perk-tree nodes. CNAM before the first PNAM belongs to the AVIF itself."""
    nodes: list[dict] = []
    node: dict | None = None
    for sig, d in avif.subrecords:
        if sig == "PNAM":
            node = {"perk": _u32(d), "x": 0, "y": 0, "h": 0.0, "v": 0.0, "children": [], "index": len(nodes)}
            nodes.append(node)
        elif node is None:
            continue
        elif sig == "XNAM":
            node["x"] = _u32(d)
        elif sig == "YNAM":
            node["y"] = _u32(d)
        elif sig == "HNAM":
            node["h"] = round(_f32(d), 4)
        elif sig == "VNAM":
            node["v"] = round(_f32(d), 4)
        elif sig == "CNAM":
            node["children"].append(_u32(d))
        elif sig == "INAM":
            node["index"] = _u32(d)
    return nodes


def build(skyrim_dir: Path) -> dict:
    skyrim_dir = Path(skyrim_dir)
    esm = find_esm(skyrim_dir)
    tes4, recs = read_plugin(esm, WANTED)
    localized = is_localized(tes4)
    tables = StringTables(esm.parent) if localized else None
    if localized and not tables.available:
        raise SkyrimNotFound("Skyrim's string tables (Strings/skyrim_<language>.strings) were not found")
    text = Text(localized, tables)

    gmst: dict[str, float] = {}
    for r in recs["GMST"]:
        name = r.edid
        d = r.first("DATA")
        if name in GMST_WANTED and d is not None and len(d) >= 4:
            gmst[name] = float(struct.unpack_from("<i", d)[0]) if name[0] == "i" else round(_f32(d), 6)

    perks: dict[str, dict] = {}
    for r in recs["PERK"]:
        data = r.first("DATA") or b"\0\0\0\0\0"
        nnam = r.first("NNAM")
        perks[str(r.form_id)] = {
            "edid": r.edid,
            "name": text.get(r.first("FULL")),
            "desc": text.get(r.first("DESC"), "dlstrings"),
            "next": _u32(nnam) if nnam else 0,
            "skill_req": read_skill_requirement(r),
            "playable": bool(data[3]) if len(data) > 3 else True,
        }

    skills: dict[str, dict] = {}
    for r in recs["AVIF"]:
        avsk = r.first("AVSK")
        if not r.edid.startswith("AV") or avsk is None or len(avsk) < 16:
            continue
        skills[r.edid] = {
            "form_id": r.form_id,
            "name": text.get(r.first("FULL")),
            "desc": text.get(r.first("DESC"), "dlstrings"),
            "avsk": [round(v, 6) for v in struct.unpack_from("<4f", avsk)],
            "nodes": read_perk_tree(r),
        }

    races: list[dict] = []
    for r in recs["RACE"]:
        data = r.first("DATA")
        if data is None or len(data) < 36 or "vampire" in r.edid.lower():
            continue
        if not (_u32(data, 32) & 0x1):
            continue
        name = text.get(r.first("FULL"))
        if not name:
            continue
        boosts = {}
        for i in range(7):
            av, bonus = data[i * 2], data[i * 2 + 1]
            if av != 0xFF and bonus:
                boosts[str(av)] = bonus
        races.append({"edid": r.edid, "name": name, "desc": text.get(r.first("DESC"), "dlstrings"), "boosts": boosts})
    races.sort(key=lambda x: x["name"])

    words = {r.form_id: r for r in recs["WOOP"]}
    shout = None
    for r in recs["SHOU"]:
        snam = b"".join(r.all("SNAM"))
        entries = [struct.unpack_from("<IIf", snam, i) for i in range(0, len(snam) - 11, 12)]
        if entries and words.get(entries[0][0]) is not None and words[entries[0][0]].edid == "WordFus":
            shout = {
                "edid": r.edid,
                "name": text.get(r.first("FULL")),
                "desc": text.get(r.first("DESC"), "dlstrings"),
                "words": [
                    {
                        "edid": words[w].edid if w in words else "",
                        "name": text.get(words[w].first("FULL")) if w in words else "",
                        "translation": text.get(words[w].first("TNAM")) if w in words else "",
                        "recharge": round(rech, 3),
                    }
                    for w, _spell, rech in entries[:3]
                ],
            }
            break

    greeting = ""
    if tables is not None:
        for s in tables.table("ilstrings").values():
            if s.startswith(GREETING_PREFIX):
                greeting = s
                break

    return {
        "cache_version": CACHE_VERSION,
        "language": tables.language if tables else "",
        "gmst": gmst,
        "skills": skills,
        "perks": perks,
        "races": races,
        "shout": shout,
        "greeting": greeting,
    }


def load(skyrim_dir: Path, cache_file: Path | None = None) -> dict:
    """Read Skyrim, reusing the cache while Skyrim.esm is unchanged."""
    esm = find_esm(Path(skyrim_dir))
    st = esm.stat()
    key = f"{st.st_size}:{int(st.st_mtime)}"
    if cache_file is not None and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if cached.get("key") == key and cached.get("cache_version") == CACHE_VERSION:
                return cached
        except (OSError, ValueError):
            pass
    data = build(Path(skyrim_dir))
    data["key"] = key
    if cache_file is not None:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass
    return data
