"""Write small Unreal Engine 3 packages in Borderlands 2's layout for tests (values made up)."""

from __future__ import annotations

import struct

import lzo

TAG = 0x9E2A83C1


def fstr(s: str) -> bytes:
    if not s:
        return struct.pack("<i", 0)
    b = s.encode("cp1252") + b"\0"
    return struct.pack("<i", len(b)) + b


class Builder:
    def __init__(self) -> None:
        self.names: list[str] = ["None"]
        self.imports: list[tuple[str, str, int, str]] = []
        self.exports: list[dict] = []

    def n(self, name: str) -> bytes:
        if name not in self.names:
            self.names.append(name)
        return struct.pack("<ii", self.names.index(name), 0)

    def imp(self, cp: str, cn: str, outer: int, name: str) -> int:
        for x in (cp, cn, name):
            self.n(x)
        self.imports.append((cp, cn, outer, name))
        return -len(self.imports)

    def exp(self, cls: int, outer: int, name: str, body: bytes = b"") -> int:
        self.n(name)
        self.exports.append({"cls": cls, "outer": outer, "name": name, "body": body})
        return len(self.exports)

    # tagged properties
    def prop(self, name: str, ptype: str, value: bytes, struct_name: str | None = None, enum: str | None = None,
             index: int = 0) -> bytes:
        out = self.n(name) + self.n(ptype)
        if ptype == "BoolProperty":
            return out + struct.pack("<ii", 0, index) + value
        out += struct.pack("<ii", len(value), index)
        if struct_name is not None:
            out += self.n(struct_name)
        if enum is not None:
            out += self.n(enum)
        return out + value

    def none(self) -> bytes:
        return self.n("None")

    def build(self, compress: bool = True, fully: bool = False) -> bytes:
        names = b"".join(fstr(s) + struct.pack("<Q", 0) for s in self.names)
        imports = b"".join(self.n(a) + self.n(b) + struct.pack("<i", o) + self.n(c) for a, b, o, c in self.imports)
        names = b"".join(fstr(s) + struct.pack("<Q", 0) for s in self.names)  # names may have grown

        def header(name_off, imp_off, exp_off, chunks) -> bytes:
            h = struct.pack("<IHHi", TAG, 832, 56, 0) + fstr("None") + struct.pack("<I", 0)
            h += struct.pack("<iiiiiii", len(self.names), name_off, len(self.exports), exp_off,
                             len(self.imports), imp_off, 0)
            h += struct.pack("<iiii", 0, 0, 0, 0) + b"\0" * 16 + struct.pack("<i", 1) + b"\0" * 12
            h += struct.pack("<III", 8639, 0, 2 if chunks else 0) + struct.pack("<i", len(chunks))
            for c in chunks:
                h += struct.pack("<iiii", *c)
            return h + struct.pack("<I", 0) + b"\0" * 8

        n_chunks = 1 if compress and not fully else 0
        head_len = len(header(0, 0, 0, [(0, 0, 0, 0)] * n_chunks))
        name_off = head_len
        imp_off = name_off + len(names)
        exp_off = imp_off + len(imports)
        entry_len = 4 * 3 + 8 + 4 + 8 + 4 + 4 + 4 + 4 + 16 + 4
        data_off = exp_off + entry_len * len(self.exports)
        exports, bodies, off = b"", b"", data_off
        for e in self.exports:
            exports += struct.pack("<iii", e["cls"], 0, e["outer"]) + self.n(e["name"]) + struct.pack("<i", 0)
            exports += struct.pack("<Qii", 0, len(e["body"]), off) + struct.pack("<Ii", 0, 0) + b"\0" * 16 + struct.pack("<I", 0)
            bodies += e["body"]
            off += len(e["body"])
        body = names + imports + exports + bodies
        if fully:
            image = header(name_off, imp_off, exp_off, []) + body
            return chunk(image)
        if not compress:
            return header(name_off, imp_off, exp_off, []) + body
        comp = chunk(body)
        return header(name_off, imp_off, exp_off, [(head_len, len(body), head_len, len(comp))]) + comp


def chunk(data: bytes, block: int = 0x20000) -> bytes:
    blocks = [data[i : i + block] for i in range(0, len(data), block)] or [b""]
    comps = [lzo.compress(b, 1, False) for b in blocks]
    out = struct.pack("<IIII", TAG, block, sum(map(len, comps)), len(data))
    out += b"".join(struct.pack("<II", len(c), len(b)) for c, b in zip(comps, blocks, strict=True))
    return out + b"".join(comps)


def skills_package(**kw) -> bytes:
    b = Builder()
    core = b.imp("Core", "Package", 0, "Core")
    cls_pkg = b.imp("Core", "Class", core, "Package")
    cls_attr = b.imp("Core", "Class", core, "InventoryAttributeDefinition")
    cls_res = b.imp("Core", "Class", core, "ConstantAttributeValueResolver")
    cls_skill = b.imp("Core", "Class", core, "SkillDefinition")
    top = b.exp(cls_pkg, 0, "GD_Assassin_Skills")
    misc = b.exp(cls_pkg, top, "Misc")
    action = b.exp(cls_pkg, top, "ActionSkill")
    attr = b.exp(cls_attr, misc, "Cooldown_Deception")
    res_body = struct.pack("<i", -1) + b.prop("ConstantValue", "FloatProperty", struct.pack("<f", 15.0)) + b.none()
    b.exp(cls_res, attr, "ConstantAttributeValueResolver_0", res_body)
    color = b.prop("Color", "StructProperty", bytes([175, 193, 205, 255]), struct_name="Color")
    elem = b.prop("MinLevel", "IntProperty", struct.pack("<i", 5)) + color + b.none()
    arr = struct.pack("<i", 2) + elem + elem
    skill_body = (struct.pack("<i", -1) + b.prop("SkillName", "StrProperty", fstr("Decepti0n"))
                  + b.prop("InitialDuration", "FloatProperty", struct.pack("<f", 6.5))
                  + b.prop("bAvailableBaseLevel", "BoolProperty", b"\x01")
                  + b.prop("DurationType", "ByteProperty", b.n("DURATION_Timed"), enum="ESkillDurationType")
                  + b.prop("CooldownAttr", "ObjectProperty", struct.pack("<i", attr))
                  + b.prop("Levels", "ArrayProperty", arr)
                  + b.prop("Scale", "FloatProperty", struct.pack("<f", 2.0), index=1)
                  + b.none())
    b.exp(cls_skill, action, "Skill_Deception", skill_body)
    return b.build(**kw)
