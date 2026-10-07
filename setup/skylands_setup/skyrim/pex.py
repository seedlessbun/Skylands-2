"""Write compiled Papyrus scripts (.pex) for Skyrim, without the Creation Kit.

Skyrim's .pex is big-endian, version 3.2, game id 1. Layout from Champollion's reader
(github.com/Orvid/Champollion, Pex/FileReader.cpp). Every script this writes is checked in
the tests by decompiling it with Champollion.

Functions are written as small assembly lists. Values:
  ("id", name)  identifier (variable, property backing var, "self", "::nonevar")
  ("str", text) ("int", n) ("float", x) ("bool", b) None
Jumps use labels: ("label", "name") as an instruction, and ("lbl", "name") as a jump argument.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field

OPCODES = {
    "nop": (0, 0, False), "iadd": (1, 3, False), "fadd": (2, 3, False), "isub": (3, 3, False),
    "fsub": (4, 3, False), "imul": (5, 3, False), "fmul": (6, 3, False), "idiv": (7, 3, False),
    "fdiv": (8, 3, False), "imod": (9, 3, False), "not": (10, 2, False), "ineg": (11, 2, False),
    "fneg": (12, 2, False), "assign": (13, 2, False), "cast": (14, 2, False), "cmp_eq": (15, 3, False),
    "cmp_lt": (16, 3, False), "cmp_lte": (17, 3, False), "cmp_gt": (18, 3, False), "cmp_gte": (19, 3, False),
    "jmp": (20, 1, False), "jmpt": (21, 2, False), "jmpf": (22, 2, False), "callmethod": (23, 3, True),
    "callparent": (24, 2, True), "callstatic": (25, 3, True), "return": (26, 1, False), "strcat": (27, 3, False),
    "propget": (28, 3, False), "propset": (29, 3, False), "array_create": (30, 2, False),
    "array_length": (31, 2, False), "array_getelement": (32, 3, False), "array_setelement": (33, 3, False),
    "array_findelement": (34, 4, False), "array_rfindelement": (35, 4, False),
}

PROP_READ, PROP_WRITE, PROP_AUTO = 1, 2, 4


@dataclass
class Function:
    name: str
    return_type: str = "None"
    params: list[tuple[str, str]] = field(default_factory=list)
    locals: list[tuple[str, str]] = field(default_factory=list)
    code: list[tuple] = field(default_factory=list)
    flags: int = 0  # 1 global, 2 native
    doc: str = ""


@dataclass
class Script:
    name: str
    parent: str
    variables: list[tuple[str, str, object]] = field(default_factory=list)  # name, type, default value
    auto_properties: list[tuple[str, str]] = field(default_factory=list)  # name, type (backed by ::<name>_var)
    functions: list[Function] = field(default_factory=list)  # in the default state
    doc: str = ""


class _Strings:
    def __init__(self) -> None:
        self.items: list[str] = []
        self.index: dict[str, int] = {}

    def __call__(self, s: str) -> int:
        if s not in self.index:
            self.index[s] = len(self.items)
            self.items.append(s)
        return self.index[s]


def _bstr(s: str) -> bytes:
    b = s.encode("cp1252")
    return struct.pack(">H", len(b)) + b


def _resolve_jumps(code: list[tuple]) -> list[tuple]:
    labels, out = {}, []
    for ins in code:
        if ins[0] == "label":
            labels[ins[1]] = len(out)
        else:
            out.append(ins)
    resolved = []
    for i, ins in enumerate(out):
        args = []
        for a in ins[1:]:
            if isinstance(a, tuple) and a and a[0] == "lbl":
                args.append(("int", labels[a[1]] - i))
            else:
                args.append(a)
        resolved.append((ins[0], *args))
    return resolved


def write(script: Script, source_name: str | None = None) -> bytes:
    st = _Strings()

    def val(v) -> bytes:
        if v is None:
            return b"\x00"
        kind, x = v
        if kind == "id":
            return b"\x01" + struct.pack(">H", st(x))
        if kind == "str":
            return b"\x02" + struct.pack(">H", st(x))
        if kind == "int":
            return b"\x03" + struct.pack(">i", int(x))
        if kind == "float":
            return b"\x04" + struct.pack(">f", float(x))
        if kind == "bool":
            return b"\x05" + bytes([1 if x else 0])
        raise ValueError(kind)

    def function_body(fn: Function) -> bytes:
        out = struct.pack(">HHIB", st(fn.return_type), st(fn.doc), 0, fn.flags)
        out += struct.pack(">H", len(fn.params)) + b"".join(struct.pack(">HH", st(n), st(t)) for n, t in fn.params)
        out += struct.pack(">H", len(fn.locals)) + b"".join(struct.pack(">HH", st(n), st(t)) for n, t in fn.locals)
        code = _resolve_jumps(fn.code)
        out += struct.pack(">H", len(code))
        for ins in code:
            op, nargs, varargs = OPCODES[ins[0]]
            args = list(ins[1:])
            fixed, extra = args[:nargs], args[nargs:]
            if len(fixed) != nargs or (extra and not varargs):
                raise ValueError(f"{fn.name}: {ins[0]} takes {nargs} arguments")
            out += bytes([op]) + b"".join(val(a) for a in fixed)
            if varargs:
                out += val(("int", len(extra))) + b"".join(val(a) for a in extra)
        return out

    # Object body (strings are interned while building, so build it before the table).
    body = struct.pack(">HHI", st(script.parent), st(script.doc), 0) + struct.pack(">H", st(""))  # auto state ""
    variables = list(script.variables) + [(f"::{n}_var", t, None) for n, t in script.auto_properties]
    body += struct.pack(">H", len(variables))
    for n, t, default in variables:
        body += struct.pack(">HHI", st(n), st(t), 0) + val(default)
    body += struct.pack(">H", len(script.auto_properties))
    for n, t in script.auto_properties:
        body += struct.pack(">HHHIB", st(n), st(t), st(""), 0, PROP_READ | PROP_WRITE | PROP_AUTO)
        body += struct.pack(">H", st(f"::{n}_var"))
    body += struct.pack(">H", 1) + struct.pack(">H", st(""))  # one state: the default ""
    body += struct.pack(">H", len(script.functions))
    for fn in script.functions:
        body += struct.pack(">H", st(fn.name)) + function_body(fn)
    obj = struct.pack(">H", st(script.name)) + struct.pack(">I", len(body) + 4) + body
    user_flags = [("hidden", 0), ("conditional", 1)]
    uf = struct.pack(">H", len(user_flags)) + b"".join(struct.pack(">HB", st(n), i) for n, i in user_flags)

    header = bytes.fromhex("FA57C0DE") + bytes([3, 2]) + struct.pack(">HQ", 1, int(time.time()))
    header += _bstr(source_name or f"{script.name}.psc") + _bstr("Skylands") + _bstr("Skylands")
    table = struct.pack(">H", len(st.items)) + b"".join(_bstr(s) for s in st.items)
    return header + table + b"\x00" + uf + struct.pack(">H", 1) + obj
