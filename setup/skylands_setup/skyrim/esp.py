"""Write a Skyrim SE plugin (.esp, ESL-flagged) from records built in Python.

Records are lists of (signature, bytes) subrecords. Copies of the player's own Skyrim records
(read with esm.read_plugin) can be edited and written back as overrides, so values such as a
crossbow's animation data come from the player's game, not from this mod.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

FORM_VERSION = 44  # Skyrim SE
FLAG_ESM, FLAG_ESL = 0x1, 0x200
REC_COMPRESSED = 0x00040000

# Top-level group order Skyrim and xEdit use (only the ones Skylands writes need to be right).
GROUP_ORDER = ["GMST", "KYWD", "LCRT", "AACT", "TXST", "GLOB", "CLAS", "FACT", "HDPT", "HAIR", "EYES", "RACE", "SOUN",
               "ASPC", "MGEF", "SCPT", "LTEX", "ENCH", "SPEL", "SCRL", "ACTI", "TACT", "ARMO", "BOOK", "CONT", "DOOR",
               "INGR", "LIGH", "MISC", "APPA", "STAT", "SCOL", "MSTT", "PWAT", "GRAS", "TREE", "CLDC", "FLOR", "FURN",
               "WEAP", "AMMO", "NPC_", "LVLN", "KEYM", "ALCH", "IDLM", "COBJ", "PROJ", "HAZD", "SLGM", "LVLI", "WTHR",
               "CLMT", "SPGD", "RFCT", "REGN", "NAVI", "CELL", "WRLD", "DIAL", "QUST", "IDLE", "PACK", "CSTY", "LSCR",
               "LVSP", "ANIO", "WATR", "EFSH", "EXPL", "DEBR", "IMGS", "IMAD", "FLST", "PERK", "BPTD", "ADDN", "AVIF",
               "CAMS", "CPTH", "VTYP", "MATT", "IPCT", "IPDS", "ARMA", "ECZN", "LCTN", "MESG", "RGDL", "DOBJ", "LGTM",
               "MUSC", "FSTP", "FSTS", "SMBN", "SMQN", "SMEN", "DLBR", "MUST", "DLVW", "WOOP", "SHOU", "EQUP", "RELA",
               "SCEN", "ASTP", "OTFT", "ARTO", "MATO", "MOVT", "SNDR", "DUAL", "SNCT", "SOPM", "COLL", "CLFM", "REVB",
               "LENS", "VOLI"]


def zstr(s: str) -> bytes:
    return s.encode("cp1252", errors="replace") + b"\0"


def u32(v: int) -> bytes:
    return struct.pack("<I", v & 0xFFFFFFFF)


def f32(v: float) -> bytes:
    return struct.pack("<f", v)


def wstr(s: str) -> bytes:
    b = s.encode("cp1252")
    return struct.pack("<H", len(b)) + b


@dataclass
class Rec:
    type: str
    form_id: int
    subs: list[tuple[str, bytes]] = field(default_factory=list)
    flags: int = 0

    def add(self, sig: str, data: bytes) -> Rec:
        self.subs.append((sig, data))
        return self

    def set(self, sig: str, data: bytes) -> Rec:
        """Replace the first subrecord with this signature (or add it)."""
        for i, (s, _) in enumerate(self.subs):
            if s == sig:
                self.subs[i] = (sig, data)
                return self
        return self.add(sig, data)

    def drop(self, *sigs: str) -> Rec:
        self.subs = [(s, d) for s, d in self.subs if s not in sigs]
        return self

    def get(self, sig: str) -> bytes | None:
        return next((d for s, d in self.subs if s == sig), None)

    def encode(self) -> bytes:
        body = b""
        for sig, data in self.subs:
            if len(data) > 0xFFFF:
                body += b"XXXX" + struct.pack("<HI", 4, len(data)) + sig.encode() + struct.pack("<H", 0) + data
            else:
                body += sig.encode() + struct.pack("<H", len(data)) + data
        flags = self.flags
        if flags & REC_COMPRESSED:
            body = struct.pack("<I", len(body)) + zlib.compress(body)
        return self.type.encode() + struct.pack("<IIIIHH", len(body), flags, self.form_id, 0, FORM_VERSION, 0) + body


class Plugin:
    """An ESL-flagged plugin. New FormIDs are 0x800-0xFFF in this plugin's own index."""

    def __init__(self, name: str, masters: list[str], author: str = "Skylands") -> None:
        self.name = name
        self.masters = masters
        self.author = author
        self.records: list[Rec] = []
        self._next = 0x800
        self.self_index = len(masters) << 24

    def new_id(self) -> int:
        if self._next > 0xFFF:
            raise ValueError("an ESL plugin holds at most 2048 new records")
        fid = self.self_index | self._next
        self._next += 1
        return fid

    def new(self, rtype: str, edid: str) -> Rec:
        r = Rec(rtype, self.new_id())
        r.add("EDID", zstr(edid))
        self.records.append(r)
        return r

    def override(self, rec: Rec) -> Rec:
        self.records.append(rec)
        return rec

    def encode(self) -> bytes:
        hedr = struct.pack("<fII", 1.71, len(self.records), self._next)
        tes4 = Rec("TES4", 0, [("HEDR", hedr), ("CNAM", zstr(self.author))], flags=FLAG_ESL)
        for m in self.masters:
            tes4.add("MAST", zstr(m)).add("DATA", struct.pack("<Q", 0))
        out = tes4.encode()
        by_type: dict[str, list[Rec]] = {}
        for r in self.records:
            by_type.setdefault(r.type, []).append(r)
        for t in sorted(by_type, key=lambda t: GROUP_ORDER.index(t) if t in GROUP_ORDER else 999):
            body = b"".join(r.encode() for r in by_type[t])
            out += b"GRUP" + struct.pack("<I", 24 + len(body)) + t.encode() + struct.pack("<iHHHH", 0, 0, 0, 0, 0) + body
        return out


# ---- script attachments (VMAD) ------------------------------------------------------------------
P_OBJECT, P_STRING, P_INT, P_FLOAT, P_BOOL = 1, 2, 3, 4, 5
P_OBJECT_ARRAY = 11


def _obj(form_id: int) -> bytes:
    return struct.pack("<HhI", 0, -1, form_id)  # format 2: unused, alias (-1 = none), form id


def vmad(scripts: list[tuple[str, list[tuple[str, int, object]]]], quest: bool = False) -> bytes:
    """scripts: [(name, [(property, type, value)])]. Object values are form ids; arrays are lists."""
    out = struct.pack("<hhH", 5, 2, len(scripts))
    for name, props in scripts:
        out += wstr(name) + b"\x00" + struct.pack("<H", len(props))
        for pname, ptype, value in props:
            out += wstr(pname) + bytes([ptype, 1])
            if ptype == P_OBJECT:
                out += _obj(value)
            elif ptype == P_OBJECT_ARRAY:
                out += struct.pack("<I", len(value)) + b"".join(_obj(v) for v in value)
            elif ptype == P_STRING:
                out += wstr(value)
            elif ptype == P_INT:
                out += struct.pack("<i", value)
            elif ptype == P_FLOAT:
                out += f32(value)
            elif ptype == P_BOOL:
                out += bytes([1 if value else 0])
            else:
                raise ValueError(ptype)
    if quest:
        # Quest fragment section with no fragments: version, fragment count, file name, alias count.
        out += b"\x02" + struct.pack("<H", 0) + wstr("") + struct.pack("<H", 0)
    return out
