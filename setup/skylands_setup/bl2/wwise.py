"""Borderlands 2's sound: Wwise sound packs (AKPK), sound banks (BKHD with HIRC / DIDX / DATA) and the way an event leads to a sound.

Nothing here is verified against a real Borderlands 2 install yet (the report of the audio probe only showed the pack names, the AKPK
magic and the event names); every reader is therefore tolerant: it scores several layouts against the magic numbers the data must show
(a bank starts with BKHD, a streamed sound with RIFF), it walks the banks by their chunk headers when the pack table cannot be trusted,
and it finds the links between objects by looking for the ids themselves instead of parsing per-version structures. The caller logs what
was found so that the next step can be fitted to the real files.

Wwise names an event by a 32-bit FNV-1 hash of its lower-cased name; an event lists actions; a play action names a sound or a container;
a sound names its audio file (an id) and says whether the file is inside the bank or streamed from the other pack.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC_BANK, MAGIC_RIFF = b"BKHD", b"RIFF"
CHUNKS = {b"BKHD", b"DIDX", b"DATA", b"HIRC", b"STID", b"STMG", b"ENVS", b"FXPR", b"INIT", b"PLAT"}
HIRC_SOUND, HIRC_ACTION, HIRC_EVENT = 2, 3, 4
HIRC_CONTAINERS = (5, 6, 9)  # random / sequence, switch, layer containers: they name the sounds under them
ACTION_PLAY = 0x04


def fnv1(name: str) -> int:
    """Wwise's id of a name: 32-bit FNV-1 of the lower-case text."""
    h = 2166136261
    for c in name.lower().encode("latin-1", errors="replace"):
        h = (h * 16777619) & 0xFFFFFFFF
        h ^= c
    return h


@dataclass
class Entry:
    id: int
    offset: int
    size: int
    lang: int = 0


def _table(data: bytes, pos: int, size: int, scale_base: int) -> list[Entry]:
    if size < 4 or pos + 4 > len(data):
        return []
    count = struct.unpack_from("<I", data, pos)[0]
    if count * 20 + 4 > size or count > 500000:
        return []
    out = []
    p = pos + 4
    for _ in range(count):
        ident, block, length, start, lang = struct.unpack_from("<5I", data, p)
        p += 20
        out.append(Entry(ident, start * (block or 1) + scale_base, length, lang))
    return out


def _score(data: bytes, entries: list[Entry], magic: bytes) -> float:
    good = [e for e in entries if e.offset + e.size <= len(data) and data[e.offset:e.offset + 4] == magic]
    return len(good) / len(entries) if entries else 0.0


@dataclass
class Pack:
    banks: list[Entry] = field(default_factory=list)
    sounds: list[Entry] = field(default_factory=list)
    layout: str = "none"
    bank_score: float = 0.0
    sound_score: float = 0.0


def read_pack(data: bytes) -> Pack:
    """The two tables of an AKPK file (banks, streamed sounds). Layouts tried: with or without a seventh header word, entry offsets from the
    start of the file or from the end of the header; the one whose entries show the right magic numbers wins."""
    if data[:4] != b"AKPK":
        return Pack()
    header, version, langs, banks, sounds = struct.unpack_from("<5I", data, 4)
    best = Pack()
    best_key = (-1.0, -1.0)
    for ext in (False, True):
        pos = 28 if ext else 24
        for base_name, base in (("absolute", 0), ("after-header", header + 8)):
            b = _table(data, pos + langs, banks, base)
            s = _table(data, pos + langs + banks, sounds, base)
            bs, ss = _score(data, b, MAGIC_BANK), _score(data, s, MAGIC_RIFF)
            key = (bs + ss, len(b) + len(s))
            if key > best_key:
                best_key = key
                best = Pack(b, s, f"version {version}, {'7' if ext else '6'} header words, {base_name} offsets", bs, ss)
    return best


@dataclass
class Obj:
    id: int
    type: int
    body: bytes
    bank: int  # index of the bank it came from


@dataclass
class Bank:
    index: int
    bank_id: int = 0
    version: int = 0
    media: dict[int, bytes] = field(default_factory=dict)  # audio inside the bank, by id
    objects: int = 0


def find_banks(data: bytes, pack: Pack) -> list[tuple[int, int]]:
    """(start, end) of every sound bank in a file: from the pack table when it can be trusted, else by looking for BKHD and walking
    the chunks that follow."""
    spans: list[tuple[int, int]] = []
    if pack.banks and pack.bank_score >= 0.9:
        return [(e.offset, e.offset + e.size) for e in pack.banks if data[e.offset:e.offset + 4] == MAGIC_BANK]
    pos = 0
    while True:
        at = data.find(MAGIC_BANK, pos)
        if at < 0:
            break
        end, ok = at, False
        p = at
        while p + 8 <= len(data) and data[p:p + 4] in CHUNKS:
            size = struct.unpack_from("<I", data, p + 4)[0]
            if p == at and not (8 <= size <= 4096):
                break
            ok = True
            p += 8 + size
            end = p
        if ok and end > at + 16:
            spans.append((at, min(end, len(data))))
            pos = end
        else:
            pos = at + 4
    return spans


def read_bank(blob: bytes, index: int, objs: dict[int, list[Obj]], counts: dict[int, int]) -> Bank:
    """One bank: its version and id, the audio inside it, and every HIRC object put into `objs`."""
    bank = Bank(index)
    didx: list[tuple[int, int, int]] = []
    data_at = 0
    p = 0
    while p + 8 <= len(blob):
        tag, size = blob[p:p + 4], struct.unpack_from("<I", blob, p + 4)[0]
        body = p + 8
        if tag not in CHUNKS or body + size > len(blob):
            break
        if tag == b"BKHD" and size >= 8:
            bank.version, bank.bank_id = struct.unpack_from("<II", blob, body)
        elif tag == b"DIDX":
            didx = [struct.unpack_from("<III", blob, body + i) for i in range(0, size - size % 12, 12)]
        elif tag == b"DATA":
            data_at = body
        elif tag == b"HIRC" and size >= 4:
            count = struct.unpack_from("<I", blob, body)[0]
            q, end = body + 4, body + size
            for _ in range(count):
                if q + 9 > end:
                    break
                typ, length = blob[q], struct.unpack_from("<I", blob, q + 1)[0]
                if length < 4 or q + 5 + length > end:
                    break
                ident = struct.unpack_from("<I", blob, q + 5)[0]
                objs.setdefault(ident, []).append(Obj(ident, typ, bytes(blob[q + 5:q + 5 + length]), index))
                counts[typ] = counts.get(typ, 0) + 1
                bank.objects += 1
                q += 5 + length
        p = body + size
    for ident, off, length in didx:
        if data_at and data_at + off + length <= len(blob):
            bank.media[ident] = bytes(blob[data_at + off:data_at + off + length])
    return bank


def contains_ids(body: bytes, ids) -> list[int]:
    """Every id from `ids` that appears as a 32-bit value anywhere in the object (after its own id), in order, without repeats."""
    out: list[int] = []
    for i in range(4, len(body) - 3):
        v = struct.unpack_from("<I", body, i)[0]
        if v in ids and v not in out:
            out.append(v)
    return out


class Sounds:
    """All banks of a pack file (and the streamed audio of the other file) as one lookup."""

    def __init__(self) -> None:
        self.objs: dict[int, list[Obj]] = {}
        self.counts: dict[int, int] = {}
        self.banks: list[Bank] = []
        self.streamed: dict[int, bytes] = {}
        self.versions: set[int] = set()
        self.media_ids: set[int] = set()

    def add_banks(self, data: bytes, pack: Pack) -> None:
        for start, end in find_banks(data, pack):
            bank = read_bank(data[start:end], len(self.banks), self.objs, self.counts)
            self.banks.append(bank)
            self.versions.add(bank.version)
            self.media_ids.update(bank.media)

    def add_streamed(self, data: bytes, pack: Pack) -> None:
        for e in pack.sounds:
            if e.offset + e.size <= len(data):
                self.streamed[e.id] = data[e.offset:e.offset + e.size]
        self.media_ids.update(self.streamed)

    def first(self, ident: int, types=None) -> Obj | None:
        for o in self.objs.get(ident, ()):
            if types is None or o.type in types:
                return o
        return None

    def media_of(self, sound: Obj) -> int | None:
        """The audio file a sound object plays: its id is the 32-bit value, near the front of the object, that is a known audio file."""
        body = sound.body
        for off in (12, 8, 16, 20, 24, 28, 32, 36, 40, 44):
            if off + 4 <= len(body):
                v = struct.unpack_from("<I", body, off)[0]
                if v in self.media_ids:
                    return v
        for i in range(4, min(len(body) - 3, 64)):
            v = struct.unpack_from("<I", body, i)[0]
            if v in self.media_ids:
                return v
        return None

    def audio(self, media: int, prefer_streamed: bool = False) -> bytes | None:
        inside = next((b.media[media] for b in self.banks if media in b.media), None)
        streamed = self.streamed.get(media)
        return (streamed or inside) if prefer_streamed else (inside or streamed)

    def sounds_under(self, ident: int, depth: int = 0, seen: set | None = None) -> list[Obj]:
        """The sound objects an object leads to: itself when it is one, the sounds named inside a container (and, two levels deep, the
        containers inside it). Actor-mixers and buses are not followed: they name their parent and every sibling."""
        seen = seen if seen is not None else set()
        if ident in seen:
            return []
        seen.add(ident)
        o = self.first(ident)
        if o is None:
            return []
        if o.type == HIRC_SOUND:
            return [o]
        if o.type not in HIRC_CONTAINERS or depth > 1:
            return []
        out: list[Obj] = []
        for child in contains_ids(o.body, self.objs):
            c = self.first(child)
            if c is not None and c.type in (HIRC_SOUND, *HIRC_CONTAINERS):
                out += self.sounds_under(child, depth + 1, seen)
        return out

    def event_sounds(self, event_id: int) -> list[Obj]:
        """Every sound a play action of the event leads to. If the strict reading (action type at byte 4, target at byte 6) finds nothing the
        actions are read loosely: any sound or container named anywhere in an action counts."""
        ev = self.first(event_id, (HIRC_EVENT,))
        if ev is None:
            return []
        actions = [a for a in (self.first(i, (HIRC_ACTION,)) for i in contains_ids(ev.body, self.objs)) if a is not None]
        out: list[Obj] = []
        for act in actions:
            if len(act.body) < 10:
                continue
            kind, target = struct.unpack_from("<HI", act.body, 4)
            if kind >> 8 == ACTION_PLAY:
                out += self.sounds_under(target)
        if out:
            return out
        for act in actions:
            for target in contains_ids(act.body, self.objs):
                o = self.first(target)
                if o is not None and o.type in (HIRC_SOUND, *HIRC_CONTAINERS):
                    out += self.sounds_under(target)
        return out


def event_ids(name: str) -> list[tuple[str, int]]:
    """The ids an Unreal-side event name might have in Wwise: the name as it is, without the Ak_ prefix, as Wwise authors write it (Play_...)."""
    base = name
    names = [base]
    low = base.lower()
    if low.startswith("ak_"):
        names.append(base[3:])
    if low.startswith("ak_play_"):
        names.append("Play_" + base[8:])
        names.append(base[8:])
    if low.startswith("ake_"):
        names.append(base[4:])
    return [(n, fnv1(n)) for n in dict.fromkeys(names)]
