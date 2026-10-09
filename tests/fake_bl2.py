"""Write small Unreal Engine 3 packages in Borderlands 2's layout for tests (values made up)."""

from __future__ import annotations

import re
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
        # Like the engine: "Name_3" is the name "Name" plus the number 4.
        m = re.fullmatch(r"(.+)_(\d+)", name)
        base, num = (m.group(1), int(m.group(2)) + 1) if m else (name, 0)
        if base not in self.names:
            self.names.append(base)
        return struct.pack("<ii", self.names.index(base), num)

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


class ObjBuilder(Builder):
    """Build packages by object path, creating group packages as needed."""

    def __init__(self) -> None:
        super().__init__()
        self.core = self.imp("Core", "Package", 0, "Core")
        self.classes: dict[str, int] = {}
        self.paths: dict[str, int] = {}

    def cls(self, name: str) -> int:
        if name not in self.classes:
            self.classes[name] = self.imp("Core", "Class", self.core, name)
        return self.classes[name]

    def group(self, path: str) -> int:
        if path in self.paths:
            return self.paths[path]
        if "." in path:
            parent, leaf = path.rsplit(".", 1)
            outer = self.group(parent)
        else:
            outer, leaf = 0, path
        self.paths[path] = self.exp(self.cls("Package"), outer, leaf)
        return self.paths[path]

    def obj(self, path: str, class_name: str, body_props: bytes) -> int:
        if ":" in path:
            parent, leaf = path.rsplit(":", 1)
            outer = self.paths[parent]
        else:
            parent, leaf = path.rsplit(".", 1)
            outer = self.group(parent)
        idx = self.exp(self.cls(class_name), outer, leaf, struct.pack("<i", -1) + body_props + self.none())
        self.paths[path] = idx
        return idx

    # property helpers
    def f(self, name, v):
        return self.prop(name, "FloatProperty", struct.pack("<f", v))

    def i(self, name, v):
        return self.prop(name, "IntProperty", struct.pack("<i", v))

    def s(self, name, v):
        return self.prop(name, "StrProperty", fstr(v))

    def o(self, name, path):
        return self.prop(name, "ObjectProperty", struct.pack("<i", self.paths[path]))

    def b(self, name, v):
        return self.prop(name, "BoolProperty", b"\x01" if v else b"\x00")

    def st(self, name, struct_name, inner: bytes):
        return self.prop(name, "StructProperty", inner + self.none(), struct_name=struct_name)

    def arr_structs(self, name, elems: list[bytes]):
        return self.prop(name, "ArrayProperty", struct.pack("<i", len(elems)) + b"".join(e + self.none() for e in elems))

    def arr_objs(self, name, paths: list[str]):
        return self.prop(name, "ArrayProperty", struct.pack("<i", len(paths)) + b"".join(struct.pack("<i", self.paths[p]) for p in paths))


def pandora_install(root) -> None:
    """A fake BL2 folder with one object of every kind the extractor reads (two packages + a DLC)."""
    from pathlib import Path

    root = Path(root)
    cooked = root / "WillowGame" / "CookedPCConsole"
    cooked.mkdir(parents=True)
    # package 1: classes, skills, pools, globals
    b = ObjBuilder()
    for k, cls_path, skill_path, name, pool_kind in [
        ("assassin", "GD_Assassin.Character.CharClass_Assassin", "GD_Assassin_Skills.ActionSkill.Skill_Deception", "Zer0", "attr"),
        ("siren", "GD_Siren.Character.CharClass_Siren", "GD_Siren_Skills.Phaselock.Skill_Phaselock", "Maya", "const"),
        ("soldier", "GD_Soldier.Character.CharClass_Soldier", "GD_Soldier_Skills.Scorpio.Skill_Scorpio", "Axton", "const"),
        ("mercenary", "GD_Mercenary.Character.CharClass_Mercenary", "GD_Mercenary_Skills.ActionSkill.Skill_Gunzerking", "Salvador", "designer"),
    ]:
        nid = f"GD_PlayerNameId.{k.capitalize()}"
        b.obj(nid, "PlayerNameIdentifierDefinition", b.s("LocalizedCharacterName", name))
        pool = f"D_Resourcepools.PlayerPools.ActiveSkillCooldownPool_{k}"
        if pool_kind == "attr":
            attr = f"GD_{k.capitalize()}_Skills.Misc.Cooldown_{k}"
            b.obj(attr, "InventoryAttributeDefinition", b"")
            res = attr + ":ConstantAttributeValueResolver_0"
            b.obj(res, "ConstantAttributeValueResolver", b.f("ConstantValue", 15.0))
            b.exports[b.paths[attr] - 1]["body"] = struct.pack("<i", -1) + b.arr_objs("ValueResolverChain", [res]) + b.none()
            init = b.f("BaseValueConstant", 0.0) + b.o("BaseValueAttribute", attr) + b.f("BaseValueScaleConstant", 1.0)
        elif pool_kind == "designer":
            attr = f"GD_{k.capitalize()}_Skills.Misc.Cooldown_{k}"
            b.obj(attr, "DesignerAttributeDefinition", b.st("BaseValue", "AttributeInitializationData",
                  b.f("BaseValueConstant", 20.0) + b.f("BaseValueScaleConstant", 1.0)))
            init = b.f("BaseValueConstant", 0.0) + b.o("BaseValueAttribute", attr) + b.f("BaseValueScaleConstant", 1.0)
        else:
            init = b.f("BaseValueConstant", 42.0) + b.f("BaseValueScaleConstant", 1.0)
        b.obj(pool, "ResourcePoolDefinition", b.st("BaseMaxValue", "AttributeInitializationData", init))
        b.obj(cls_path, "PlayerClassDefinition", b.o("CharacterNameId", nid) + b.o("SkillCooldownPoolDefinition", pool))
        b.obj(skill_path, "SkillDefinition", b.s("SkillName", name + " skill") +
              b.s("SkillDescription", "[skill]Action Skill.[-skill] Press <StringAliasMap:Action.ActionSkill> now.") +
              b.f("InitialDuration", 6.5))
    color = lambda r, g, bl: b.prop("Color", "StructProperty", bytes([bl, g, r, 255]), struct_name="Color")  # noqa: E731
    b.obj("GD_Globals.General.Globals", "GlobalsDefinition", b.arr_structs("RarityLevelColors", [
        b.i("MinLevel", 1) + b.i("MaxLevel", 1) + color(255, 255, 255),
        b.i("MinLevel", 5) + b.i("MaxLevel", 5) + color(255, 180, 0),
        *[b.i("MinLevel", lvl) + b.i("MaxLevel", lvl) + color(lvl * 40, 120, 60) for lvl in (2, 3, 4, 6)],
    ]))
    for _k, o, n in [("marauder", "GD_Population_Marauder.Balance.PawnBalance_MarauderRegular", "Marauder"),
                    ("psycho", "GD_Population_Psycho.Balance.PawnBalance_Psycho", "Psycho")]:
        b.obj(o, "AIPawnBalanceDefinition", b.arr_structs("PlayThroughs", [b.i("PlayThrough", 1) + b.s("DisplayName", n)]))
    (cooked / "Startup_Fake.upk").write_bytes(b.build())

    # package 2: a pistol type, two balances (common -> rare chain), a legendary, names, manufacturer
    g = ObjBuilder()
    g.obj("GD_Weap_Pistol.Name.Title_Jakobs.Title__Revolver", "WeaponNamePartDefinition", g.s("PartName", "Revolver"))
    g.obj("GD_Weap_Pistol.Name.Prefix.Prefix_Elemental_Incendiary", "WeaponNamePartDefinition", g.s("PartName", "Incendiary"))
    g.obj("GD_Weap_Pistol.Name.Title_Jakobs.Title_Maggie", "WeaponNamePartDefinition", g.s("PartName", "Maggie"))
    g.obj("GD_Weap_Pistol.elemental.Pistol_Elemental_Fire", "WeaponPartDefinition", b"")
    g.obj("GD_Weap_Pistol.Barrel.Pistol_Barrel_Jakobs_Maggie", "WeaponPartDefinition",
          g.arr_objs("TitleList", ["GD_Weap_Pistol.Name.Title_Jakobs.Title_Maggie"]))
    g.obj("GD_Weap_Pistol.A_Weapons.WeaponType_Jakobs_Pistol", "WeaponTypeDefinition",
          g.arr_objs("TitleList", ["GD_Weap_Pistol.Name.Title_Jakobs.Title__Revolver"]) +
          g.st("InstantHitDamage", "AttributeInitializationData", g.f("BaseValueConstant", 20.0) + g.f("BaseValueScaleConstant", 2.2)) +
          g.i("ProjectilesPerShot", 1) + g.i("ClipSize", 6))
    weighted = lambda part: g.o("Part", part)  # noqa: E731
    g.obj("GD_Weap_Pistol.A_Weapons.Pistol_Jakobs", "WeaponBalanceDefinition", b"")
    g.obj("GD_Weap_Pistol.A_Weapons.Pistol_Jakobs:PartList", "WeaponPartListCollectionDefinition",
          g.o("AssociatedWeaponType", "GD_Weap_Pistol.A_Weapons.WeaponType_Jakobs_Pistol") +
          g.st("ElementalPartData", "PartListData", g.b("bEnabled", True) +
               g.arr_structs("WeightedParts", [weighted("GD_Weap_Pistol.elemental.Pistol_Elemental_Fire")])))
    g.exports[g.paths["GD_Weap_Pistol.A_Weapons.Pistol_Jakobs"] - 1]["body"] = (
        struct.pack("<i", -1) + g.o("WeaponPartListCollection", "GD_Weap_Pistol.A_Weapons.Pistol_Jakobs:PartList") + g.none())
    g.obj("GD_Weap_Pistol.A_Weapons.Pistol_Jakobs_3_Rare", "WeaponBalanceDefinition",
          g.o("BaseDefinition", "GD_Weap_Pistol.A_Weapons.Pistol_Jakobs"))
    g.obj("GD_Weap_Pistol.A_Weapons_Legendary.Pistol_Jakobs_5_Maggie", "WeaponBalanceDefinition",
          g.o("BaseDefinition", "GD_Weap_Pistol.A_Weapons.Pistol_Jakobs"))
    g.obj("GD_Weap_Pistol.A_Weapons_Legendary.Pistol_Jakobs_5_Maggie:PartList", "WeaponPartListCollectionDefinition",
          g.st("BarrelPartData", "PartListData", g.b("bEnabled", True) +
               g.arr_structs("WeightedParts", [weighted("GD_Weap_Pistol.Barrel.Pistol_Barrel_Jakobs_Maggie")])))
    leg = g.paths["GD_Weap_Pistol.A_Weapons_Legendary.Pistol_Jakobs_5_Maggie"]
    g.exports[leg - 1]["body"] = (struct.pack("<i", -1) + g.o("BaseDefinition", "GD_Weap_Pistol.A_Weapons.Pistol_Jakobs")
                                  + g.o("WeaponPartListCollection", "GD_Weap_Pistol.A_Weapons_Legendary.Pistol_Jakobs_5_Maggie:PartList") + g.none())
    g.obj("GD_Manufacturers.Manufacturers.Jakobs", "ManufacturerDefinition",
          g.arr_structs("Grades", [g.s("DisplayName", "Jakobs")]))
    (cooked / "GD_Weapons_Fake.upk").write_bytes(g.build())

    # a DLC package for Gaige
    dlc = root / "DLC" / "Tulip" / "Compat" / "CookedPCConsole"
    dlc.mkdir(parents=True)
    t = ObjBuilder()
    t.obj("GD_TulipPackageDef.PlayerNameId.Mechromancer", "PlayerNameIdentifierDefinition", t.s("LocalizedCharacterName", "Gaige"))
    t.obj("GD_Tulip_Mechromancer_Skills.Action.Pool_DeathTrapCoolDown", "ResourcePoolDefinition",
          t.st("BaseMaxValue", "AttributeInitializationData", t.f("BaseValueConstant", 60.0) + t.f("BaseValueScaleConstant", 1.0)))
    t.obj("GD_Tulip_Mechromancer.Character.CharClass_Mechromancer", "PlayerClassDefinition",
          t.o("CharacterNameId", "GD_TulipPackageDef.PlayerNameId.Mechromancer") +
          t.o("SkillCooldownPoolDefinition", "GD_Tulip_Mechromancer_Skills.Action.Pool_DeathTrapCoolDown"))
    t.obj("GD_Tulip_Mechromancer_Skills.Action.Skill_DeathTrap", "SkillDefinition", t.s("SkillName", "Deathtrap") + t.f("InitialDuration", 20.0))
    (dlc / "GD_Tulip_Fake.upk").write_bytes(t.build())


def level_package_importing(path, names) -> None:
    """A level-style package: it imports objects (so their names are in its name table) but defines none of them."""
    b = Builder()
    core = b.imp("Core", "Package", 0, "Core")
    for n in names:
        b.imp("Core", "Package", core, n)
    top = b.exp(b.imp("Core", "Class", core, "Package"), 0, "Fake_P")
    b.exp(b.imp("Core", "Class", core, "Level"), top, "PersistentLevel")
    path.write_bytes(b.build())
