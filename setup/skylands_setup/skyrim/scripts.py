"""The Papyrus scripts Skylands needs, written straight to .pex (see pex.py)."""

from __future__ import annotations

from .pex import Function, Script

NONE = ("id", "::nonevar")
SELF = ("id", "self")
ZERO9 = [("float", 0.0)] * 9  # Message.Show's nine optional float arguments


F0 = ("float", 0.0)
SELF_CALL = ("id", "self")


def call(name, *args, dest=NONE):
    return ("callmethod", ("id", name), SELF, dest, *args)

def ret_if(cond, tag):
    """If cond Return EndIf"""
    return [("jmpf", cond, ("lbl", tag)), ("return", None), ("label", tag)]


def ret_unless(cond, tag, tmp=("id", "::temp0")):
    """If !cond Return EndIf (the compiler's shape: not, jump over the return)"""
    return [("not", tmp, cond), ("jmpf", tmp, ("lbl", tag)), ("return", None), ("label", tag)]


def notify(*parts, msg=("id", "msg")):
    """Debug.Notification(a + b + ...) for string literals and string variables."""
    code = [("assign", msg, ("str", ""))]
    for part in parts:
        code.append(("strcat", msg, msg, part))
    code.append(("callstatic", ("id", "Debug"), ("id", "Notification"), NONE, msg))
    return code


def class_choice_quest() -> Script:
    """SkylandsClassQuest extends Quest: the vault hunter choice, then a once-a-second tick that

      * applies the equipped Skylands gun's speed to the player (the speed is the magnitude of the
        last effect of the gun's enchantment),
      * every other tick scans the player's cell: puts rarity beams and lights on Skylands guns lying
        on the ground, hands guns to some hostile humanoids (they wield them), and when a hostile
        humanoid is dead drops its gun - or, sometimes, a new one - on the ground with a beam.

    Properties: ClassChoice, Shouts, Words, StarterGun, StarterAmmo, GunKeyword, RarityKeywords[6], Beams[6],
    Lights[6], GunDrop, GunDropGood, NpcKeyword, ArmChance, DropChance, GoodLevel, ArmPerScan, ScanRadius, Verbose.
    """
    on_init = Function(
        "OnInit",
        locals=[("::nonevar", "None")],
        code=[("array_create", ("id", "Tracked"), ("int", 48)), ("array_create", ("id", "DeadSeen"), ("int", 64)),
              ("array_create", ("id", "ArmSeen"), ("int", 64)),
              ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 2.0)), ("return", None)],
    )
    on_update = Function(
        "OnUpdate",
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            ("not", ("id", "::temp0"), ("id", "Chosen")),
            ("jmpf", ("id", "::temp0"), ("lbl", "ticking")),
            call("Choose"),
            ("label", "ticking"),
            ("jmpf", ("id", "Chosen"), ("lbl", "again")),
            call("Tick"),
            ("label", "again"),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 1.0)),
            ("return", None),
        ],
    )
    choose = Function(
        "Choose",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("choice", "Int"), ("player", "Actor"),
                ("chosenShout", "Shout"), ("chosenWord", "WordOfPower"), ("::temp5", "Bool")],
        code=[
            ("callstatic", ("id", "Utility"), ("id", "IsInMenuMode"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "not_menu")),
            ("return", None),
            ("label", "not_menu"),
            ("callstatic", ("id", "Game"), ("id", "IsMovementControlsEnabled"), ("id", "::temp5")),
            ("not", ("id", "::temp0"), ("id", "::temp5")),  # the compiler's shape for If !X
            ("jmpf", ("id", "::temp0"), ("lbl", "can_move")),
            ("return", None),
            ("label", "can_move"),
            ("callmethod", ("id", "Show"), ("id", "::ClassChoice_var"), ("id", "choice"), *ZERO9),
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("array_getelement", ("id", "chosenShout"), ("id", "::Shouts_var"), ("id", "choice")),
            ("callmethod", ("id", "AddShout"), ("id", "player"), NONE, ("id", "chosenShout")),
            ("array_getelement", ("id", "chosenWord"), ("id", "::Words_var"), ("id", "choice")),
            ("callstatic", ("id", "Game"), ("id", "TeachWord"), NONE, ("id", "chosenWord")),
            ("callstatic", ("id", "Game"), ("id", "UnlockWord"), NONE, ("id", "chosenWord")),
            ("callmethod", ("id", "EquipShout"), ("id", "player"), NONE, ("id", "chosenShout")),
            ("callmethod", ("id", "AddItem"), ("id", "player"), NONE, ("id", "::StarterGun_var"),
             ("int", 1), ("bool", False)),
            ("callmethod", ("id", "AddItem"), ("id", "player"), NONE, ("id", "::StarterAmmo_var"),
             ("int", 60), ("bool", False)),
            ("callmethod", ("id", "EquipItem"), ("id", "player"), NONE, ("id", "::StarterGun_var"),
             ("bool", False), ("bool", False)),
            ("assign", ("id", "Chosen"), ("bool", True)),
            ("return", None),
        ],
    )
    speed_of = Function(
        "SpeedOf",
        return_type="Float",
        params=[("w", "Weapon")],
        locals=[("::temp0", "Bool"), ("::temp1", "Bool"), ("e", "Enchantment"), ("n", "Int"), ("v", "Float")],
    )
    speed_of.code = [
        ("cast", ("id", "::temp1"), ("id", "w")),
        ("jmpf", ("id", "::temp1"), ("lbl", "none")),
        ("callmethod", ("id", "HasKeyword"), ("id", "w"), ("id", "::temp0"), ("id", "::GunKeyword_var")),
        ("jmpf", ("id", "::temp0"), ("lbl", "none")),
        ("callmethod", ("id", "GetEnchantment"), ("id", "w"), ("id", "e")),
        ("cast", ("id", "::temp1"), ("id", "e")),
        ("jmpf", ("id", "::temp1"), ("lbl", "none")),
        ("callmethod", ("id", "GetNumEffects"), ("id", "e"), ("id", "n")),
        ("cmp_lt", ("id", "::temp0"), ("id", "n"), ("int", 1)),
        ("jmpf", ("id", "::temp0"), ("lbl", "read")),
        ("return", ("float", 1.0)),
        ("label", "read"),
        ("isub", ("id", "n"), ("id", "n"), ("int", 1)),
        ("callmethod", ("id", "GetNthEffectMagnitude"), ("id", "e"), ("id", "v"), ("id", "n")),
        ("cmp_lt", ("id", "::temp0"), ("id", "v"), ("float", 0.2)),
        ("jmpf", ("id", "::temp0"), ("lbl", "ok")),
        ("return", ("float", 1.0)),
        ("label", "ok"),
        ("return", ("id", "v")),
        ("label", "none"),
        ("return", ("float", 1.0)),
    ]
    tick = Function(
        "Tick",
        locals=[("::nonevar", "None"), ("player", "Actor"), ("w", "Weapon"), ("want", "Float"), ("::temp0", "Bool"),
                ("::temp1", "Bool"), ("msg", "String"), ("part", "String"), ("got", "Float")],
        code=[
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "GetEquippedWeapon"), ("id", "player"), ("id", "w"), ("bool", False)),
            ("callmethod", ("id", "SpeedOf"), SELF, ("id", "want"), ("id", "w")),
            ("cmp_eq", ("id", "::temp0"), ("id", "want"), ("id", "Speed")),
            ("not", ("id", "::temp1"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp1"), ("lbl", "scan")),  # unchanged: nothing to apply
            ("assign", ("id", "Speed"), ("id", "want")),
            ("callmethod", ("id", "SetActorValue"), ("id", "player"), NONE, ("str", "WeaponSpeedMult"), ("id", "want")),
            ("cmp_eq", ("id", "::temp0"), ("id", "want"), ("float", 1.0)),
            ("not", ("id", "::temp1"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp1"), ("lbl", "scan")),  # back to normal speed: no message
            ("cast", ("id", "msg"), ("id", "want")),
            ("callmethod", ("id", "GetActorValue"), ("id", "player"), ("id", "got"), ("str", "WeaponSpeedMult")),
            ("cast", ("id", "part"), ("id", "got")),
            ("strcat", ("id", "msg"), ("str", "Skylands gun speed x"), ("id", "msg")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", " (game reports ")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "part")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", ")")),
            ("callstatic", ("id", "Debug"), ("id", "Notification"), NONE, ("id", "msg")),
            ("label", "scan"),
            ("not", ("id", "ScanNow"), ("id", "ScanNow")),
            ("jmpf", ("id", "ScanNow"), ("lbl", "end")),
            call("Scan"),
            ("label", "end"),
            ("return", None),
        ],
    )

    def scan_loop(kind: int, actors: bool) -> list[tuple]:
        tag = "a" if actors else "w"
        return [
            ("callmethod", ("id", "GetNumRefs"), ("id", "cell"), ("id", "n"), ("int", kind)),
            ("assign", ("id", "i"), ("int", 0)),
            ("label", f"{tag}_loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("id", "n")),
            ("jmpf", ("id", "::temp0"), ("lbl", f"{tag}_done")),
            ("callmethod", ("id", "GetNthRef"), ("id", "cell"), ("id", "r"), ("id", "i"), ("int", kind)),
            call("Handle" if actors else "Consider", ("id", "r")),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", f"{tag}_loop")),
            ("label", f"{tag}_done"),
        ]

    scan = Function(
        "Scan",
        locals=[("::nonevar", "None"), ("player", "Actor"), ("cell", "Cell"), ("n", "Int"), ("i", "Int"),
                ("r", "ObjectReference"), ("::temp0", "Bool")],
        code=[
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "GetParentCell"), ("id", "player"), ("id", "cell")),
            ("cast", ("id", "::temp0"), ("id", "cell")),
            ("jmpf", ("id", "::temp0"), ("lbl", "nocell")),
            ("assign", ("id", "Budget"), ("id", "::ArmPerScan_var")),
            *scan_loop(41, False),  # weapons lying in the world
            *scan_loop(43, True),   # people: the living may be armed, the dead drop guns
            ("return", None),
            ("label", "nocell"),
            ("return", None),
        ],
    )
    handle = Function(
        "Handle",
        params=[("r", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("::temp1", "Bool"), ("a", "Actor"), ("player", "Actor"),
                ("d", "Float")],
        code=[
            ("cast", ("id", "a"), ("id", "r")),
            ("cast", ("id", "::temp0"), ("id", "a")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("cmp_eq", ("id", "::temp0"), ("id", "a"), ("id", "player")),
            ("jmpf", ("id", "::temp0"), ("lbl", "other")),
            ("return", None),
            ("label", "other"),
            ("callmethod", ("id", "GetDistance"), ("id", "r"), ("id", "d"), ("id", "player")),
            ("cmp_lte", ("id", "::temp0"), ("id", "d"), ("id", "::ScanRadius_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("callmethod", ("id", "IsDead"), ("id", "a"), ("id", "::temp1")),
            ("jmpf", ("id", "::temp1"), ("lbl", "alive")),
            call("Mourn", ("id", "a")),
            ("return", None),
            ("label", "alive"),
            call("Arm", ("id", "a")),
            ("label", "end"),
            ("return", None),
        ],
    )
    seen = Function(
        "Seen",
        return_type="Bool",
        params=[("ring", "ObjectReference[]"), ("r", "ObjectReference")],
        locals=[("::temp0", "Bool"), ("i", "Int"), ("n", "Int"), ("e", "ObjectReference")],
        code=[
            ("array_length", ("id", "n"), ("id", "ring")),
            ("assign", ("id", "i"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("id", "n")),
            ("jmpf", ("id", "::temp0"), ("lbl", "no")),
            ("array_getelement", ("id", "e"), ("id", "ring"), ("id", "i")),
            ("cmp_eq", ("id", "::temp0"), ("id", "e"), ("id", "r")),
            ("jmpf", ("id", "::temp0"), ("lbl", "cont")),
            ("return", ("bool", True)),
            ("label", "cont"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "no"),
            ("return", ("bool", False)),
        ],
    )
    note = Function(
        "Note",
        params=[("ring", "ObjectReference[]"), ("at", "Int"), ("r", "ObjectReference")],
        locals=[("::nonevar", "None")],
        code=[("array_setelement", ("id", "ring"), ("id", "at"), ("id", "r")), ("return", None)],
    )
    eligible = Function(
        "Eligible",
        return_type="Bool",
        params=[("a", "Actor")],
        locals=[("::temp0", "Bool"), ("player", "Actor")],
        code=[
            ("callmethod", ("id", "HasKeyword"), ("id", "a"), ("id", "::temp0"), ("id", "::NpcKeyword_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "no")),
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "IsHostileToActor"), ("id", "a"), ("id", "::temp0"), ("id", "player")),
            ("return", ("id", "::temp0")),
            ("label", "no"),
            ("return", ("bool", False)),
        ],
    )
    worthy = Function(
        "Worthy",
        return_type="Bool",
        params=[("a", "Actor")],
        locals=[("::temp0", "Bool"), ("player", "Actor"), ("killer", "Actor")],
        code=[
            ("callmethod", ("id", "HasKeyword"), ("id", "a"), ("id", "::temp0"), ("id", "::NpcKeyword_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "no")),
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "GetKiller"), ("id", "a"), ("id", "killer")),
            ("cmp_eq", ("id", "::temp0"), ("id", "killer"), ("id", "player")),
            ("jmpf", ("id", "::temp0"), ("lbl", "hostile")),
            ("return", ("bool", True)),
            ("label", "hostile"),
            ("callmethod", ("id", "IsHostileToActor"), ("id", "a"), ("id", "::temp0"), ("id", "player")),
            ("return", ("id", "::temp0")),
            ("label", "no"),
            ("return", ("bool", False)),
        ],
    )
    roll = Function(
        "Roll",
        return_type="Bool",
        params=[("pct", "Int")],
        locals=[("::temp0", "Int"), ("::temp1", "Bool")],
        code=[
            ("callstatic", ("id", "Utility"), ("id", "RandomInt"), ("id", "::temp0"), ("int", 1), ("int", 100)),
            ("cmp_lte", ("id", "::temp1"), ("id", "::temp0"), ("id", "pct")),
            ("return", ("id", "::temp1")),
        ],
    )
    list_for = Function(
        "ListFor",
        return_type="Form",
        params=[("a", "Actor")],
        locals=[("::temp0", "Bool"), ("level", "Int")],
        code=[
            ("callmethod", ("id", "GetLevel"), ("id", "a"), ("id", "level")),
            ("cmp_gte", ("id", "::temp0"), ("id", "level"), ("id", "::GoodLevel_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "plain")),
            ("return", ("id", "::GunDropGood_var")),
            ("label", "plain"),
            ("return", ("id", "::GunDrop_var")),
        ],
    )
    own_drop = Function(
        "OwnDrop",
        return_type="ObjectReference",
        params=[("a", "Actor")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("w", "Weapon"), ("drop", "ObjectReference")],
        code=[
            ("callmethod", ("id", "GetEquippedWeapon"), ("id", "a"), ("id", "w"), ("bool", False)),
            ("cast", ("id", "::temp0"), ("id", "w")),
            ("jmpf", ("id", "::temp0"), ("lbl", "none")),
            ("callmethod", ("id", "HasKeyword"), ("id", "w"), ("id", "::temp0"), ("id", "::GunKeyword_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "none")),
            ("callmethod", ("id", "UnequipItem"), ("id", "a"), NONE, ("id", "w"), ("bool", False), ("bool", True)),
            ("callmethod", ("id", "DropObject"), ("id", "a"), ("id", "drop"), ("id", "w"), ("int", 1)),
            ("return", ("id", "drop")),
            ("label", "none"),
            ("return", None),
        ],
    )
    bonus_drop = Function(
        "BonusDrop",
        return_type="ObjectReference",
        params=[("a", "Actor")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("list", "Form"), ("drop", "ObjectReference")],
        code=[
            ("callmethod", ("id", "Worthy"), SELF, ("id", "::temp0"), ("id", "a")),
            ("jmpf", ("id", "::temp0"), ("lbl", "none")),
            ("callmethod", ("id", "Roll"), SELF, ("id", "::temp0"), ("id", "::DropChance_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "none")),
            ("callmethod", ("id", "ListFor"), SELF, ("id", "list"), ("id", "a")),
            ("callmethod", ("id", "PlaceAtMe"), ("id", "a"), ("id", "drop"), ("id", "list"), ("int", 1), ("bool", False),
             ("bool", False)),
            ("return", ("id", "drop")),
            ("label", "none"),
            ("return", None),
        ],
    )
    announce = Function(
        "Announce",
        params=[("drop", "ObjectReference")],
        locals=[("::nonevar", "None"), ("msg", "String"), ("name", "String")],
        code=[
            call("Consider", ("id", "drop")),
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "end")),
            ("callmethod", ("id", "GetDisplayName"), ("id", "drop"), ("id", "name")),
            *notify(("str", "Skylands drop: "), ("id", "name")),
            ("label", "end"),
            ("return", None),
        ],
    )
    mourn = Function(
        "Mourn",
        params=[("a", "Actor")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("drop", "ObjectReference")],
        code=[
            ("callmethod", ("id", "Seen"), SELF, ("id", "::temp0"), ("id", "DeadSeen"), ("id", "a")),
            ("jmpf", ("id", "::temp0"), ("lbl", "fresh")),
            ("return", None),
            ("label", "fresh"),
            call("Note", ("id", "DeadSeen"), ("id", "DeadNext"), ("id", "a")),
            ("iadd", ("id", "DeadNext"), ("id", "DeadNext"), ("int", 1)),
            ("imod", ("id", "DeadNext"), ("id", "DeadNext"), ("int", 64)),
            ("callmethod", ("id", "OwnDrop"), SELF, ("id", "drop"), ("id", "a")),
            ("cast", ("id", "::temp0"), ("id", "drop")),
            ("jmpf", ("id", "::temp0"), ("lbl", "bonus")),
            call("Announce", ("id", "drop")),
            ("return", None),
            ("label", "bonus"),
            ("callmethod", ("id", "BonusDrop"), SELF, ("id", "drop"), ("id", "a")),
            ("cast", ("id", "::temp0"), ("id", "drop")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            call("Announce", ("id", "drop")),
            ("label", "end"),
            ("return", None),
        ],
    )
    equip = Function(
        "Equip",
        params=[("a", "Actor")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("g", "ObjectReference"), ("f", "Form"), ("msg", "String"),
                ("name", "String"), ("what", "String"), ("list", "Form")],
        code=[
            ("callmethod", ("id", "ListFor"), SELF, ("id", "list"), ("id", "a")),
            ("callmethod", ("id", "PlaceAtMe"), ("id", "a"), ("id", "g"), ("id", "list"), ("int", 1), ("bool", False),
             ("bool", False)),
            ("cast", ("id", "::temp0"), ("id", "g")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("callmethod", ("id", "GetBaseObject"), ("id", "g"), ("id", "f")),
            ("callmethod", ("id", "AddItem"), ("id", "a"), NONE, ("id", "g"), ("int", 1), ("bool", True)),
            ("callmethod", ("id", "AddItem"), ("id", "a"), NONE, ("id", "::StarterAmmo_var"), ("int", 30), ("bool", True)),
            ("callmethod", ("id", "EquipItem"), ("id", "a"), NONE, ("id", "f"), ("bool", False), ("bool", True)),
            ("callmethod", ("id", "EquipItem"), ("id", "a"), NONE, ("id", "::StarterAmmo_var"), ("bool", False),
             ("bool", True)),
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "end")),
            ("callmethod", ("id", "GetDisplayName"), ("id", "a"), ("id", "name")),
            ("callmethod", ("id", "GetName"), ("id", "f"), ("id", "what")),
            *notify(("id", "name"), ("str", " carries "), ("id", "what")),
            ("label", "end"),
            ("return", None),
        ],
    )
    arm = Function(
        "Arm",
        params=[("a", "Actor")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            ("cmp_lt", ("id", "::temp0"), ("id", "Budget"), ("int", 1)),
            ("jmpf", ("id", "::temp0"), ("lbl", "go")),
            ("return", None),
            ("label", "go"),
            ("callmethod", ("id", "Seen"), SELF, ("id", "::temp0"), ("id", "ArmSeen"), ("id", "a")),
            ("jmpf", ("id", "::temp0"), ("lbl", "fresh")),
            ("return", None),
            ("label", "fresh"),
            call("Note", ("id", "ArmSeen"), ("id", "ArmNext"), ("id", "a")),
            ("iadd", ("id", "ArmNext"), ("id", "ArmNext"), ("int", 1)),
            ("imod", ("id", "ArmNext"), ("id", "ArmNext"), ("int", 64)),
            ("callmethod", ("id", "Eligible"), SELF, ("id", "::temp0"), ("id", "a")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("callmethod", ("id", "Roll"), SELF, ("id", "::temp0"), ("id", "::ArmChance_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("isub", ("id", "Budget"), ("id", "Budget"), ("int", 1)),
            call("Equip", ("id", "a")),
            ("label", "end"),
            ("return", None),
        ],
    )
    consider = Function(
        "Consider",
        params=[("r", "ObjectReference")],
        locals=[("::nonevar", "None"), ("player", "Actor"), ("d", "Float"), ("::temp0", "Bool"), ("k", "Int"),
                ("kw", "Keyword"), ("base", "Form"), ("has", "Bool")],
        code=[
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "GetDistance"), ("id", "r"), ("id", "d"), ("id", "player")),
            ("cmp_lte", ("id", "::temp0"), ("id", "d"), ("id", "::ScanRadius_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "far")),
            ("callmethod", ("id", "GetBaseObject"), ("id", "r"), ("id", "base")),
            ("assign", ("id", "k"), ("int", 5)),
            ("label", "loop"),
            ("cmp_gte", ("id", "::temp0"), ("id", "k"), ("int", 0)),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("array_getelement", ("id", "kw"), ("id", "::RarityKeywords_var"), ("id", "k")),
            ("callmethod", ("id", "HasKeyword"), ("id", "base"), ("id", "has"), ("id", "kw")),
            ("jmpf", ("id", "has"), ("lbl", "lower")),
            call("Place", ("id", "r"), ("id", "k")),
            ("assign", ("id", "k"), ("int", -1)),  # found the highest rarity: stop
            ("jmp", ("lbl", "again")),
            ("label", "lower"),
            ("isub", ("id", "k"), ("id", "k"), ("int", 1)),
            ("label", "again"),
            ("jmp", ("lbl", "loop")),
            ("label", "end"),
            ("return", None),
            ("label", "far"),
            ("return", None),
        ],
    )
    place = Function(
        "Place",
        params=[("r", "ObjectReference"), ("k", "Int")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("i", "Int"), ("e", "ObjectReference"), ("bs", "Activator"),
                ("lt", "Light"), ("ln", "Int"), ("b", "ObjectReference"), ("lr", "ObjectReference"),
                ("beam", "SkylandsLootBeam"), ("name", "String"), ("msg", "String")],
        code=[
            ("assign", ("id", "i"), ("int", 0)),
            ("label", "find"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("int", 48)),
            ("jmpf", ("id", "::temp0"), ("lbl", "add")),
            ("array_getelement", ("id", "e"), ("id", "Tracked"), ("id", "i")),
            ("cmp_eq", ("id", "::temp0"), ("id", "e"), ("id", "r")),
            ("jmpf", ("id", "::temp0"), ("lbl", "cont")),
            ("return", None),  # already has a beam
            ("label", "cont"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "find")),
            ("label", "add"),
            ("array_getelement", ("id", "bs"), ("id", "::Beams_var"), ("id", "k")),
            ("callmethod", ("id", "PlaceAtMe"), ("id", "r"), ("id", "b"), ("id", "bs"), ("int", 1), ("bool", False),
             ("bool", False)),
            ("array_length", ("id", "ln"), ("id", "::Lights_var")),
            ("cmp_gt", ("id", "::temp0"), ("id", "ln"), ("id", "k")),
            ("jmpf", ("id", "::temp0"), ("lbl", "nolight")),
            ("array_getelement", ("id", "lt"), ("id", "::Lights_var"), ("id", "k")),
            ("callmethod", ("id", "PlaceAtMe"), ("id", "r"), ("id", "lr"), ("id", "lt"), ("int", 1), ("bool", False),
             ("bool", False)),
            ("label", "nolight"),
            ("cast", ("id", "beam"), ("id", "b")),
            ("cast", ("id", "::temp0"), ("id", "beam")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("callmethod", ("id", "Track"), ("id", "beam"), NONE, ("id", "r"), SELF, ("id", "lr")),
            ("array_setelement", ("id", "Tracked"), ("id", "TrackedNext"), ("id", "r")),
            ("iadd", ("id", "TrackedNext"), ("id", "TrackedNext"), ("int", 1)),
            ("imod", ("id", "TrackedNext"), ("id", "TrackedNext"), ("int", 48)),
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "end")),
            ("callmethod", ("id", "GetDisplayName"), ("id", "r"), ("id", "name")),
            *notify(("str", "Skylands beam: "), ("id", "name")),
            ("label", "end"),
            ("return", None),
        ],
    )
    forget = Function(
        "Forget",
        params=[("t", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("i", "Int"), ("e", "ObjectReference")],
        code=[
            ("assign", ("id", "i"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("int", 48)),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("array_getelement", ("id", "e"), ("id", "Tracked"), ("id", "i")),
            ("cmp_eq", ("id", "::temp0"), ("id", "e"), ("id", "t")),
            ("not", ("id", "::temp0"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "clear")),
            ("jmp", ("lbl", "next")),
            ("label", "clear"),
            ("array_setelement", ("id", "Tracked"), ("id", "i"), None),
            ("label", "next"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "end"),
            ("return", None),
        ],
    )
    return Script(
        name="SkylandsClassQuest",
        parent="Quest",
        variables=[("Chosen", "Bool", ("bool", False)), ("Speed", "Float", ("float", 0.0)),
                   ("ScanNow", "Bool", ("bool", False)), ("Budget", "Int", ("int", 0)),
                   ("TrackedNext", "Int", ("int", 0)), ("DeadNext", "Int", ("int", 0)), ("ArmNext", "Int", ("int", 0)),
                   ("Tracked", "ObjectReference[]", None), ("DeadSeen", "ObjectReference[]", None),
                   ("ArmSeen", "ObjectReference[]", None)],
        auto_properties=[("ClassChoice", "Message"), ("Shouts", "Shout[]"), ("Words", "WordOfPower[]"),
                         ("StarterGun", "Form"), ("StarterAmmo", "Form"), ("GunKeyword", "Keyword"),
                         ("RarityKeywords", "Keyword[]"), ("Beams", "Activator[]"), ("Lights", "Light[]"),
                         ("GunDrop", "Form"), ("GunDropGood", "Form"), ("NpcKeyword", "Keyword"),
                         ("ArmChance", "Int"), ("DropChance", "Int"), ("GoodLevel", "Int"), ("ArmPerScan", "Int"),
                         ("ScanRadius", "Float"), ("Verbose", "Bool")],
        functions=[on_init, on_update, choose, speed_of, tick, scan, handle, seen, note, eligible, worthy, roll, list_for,
                   own_drop, bonus_drop, announce, mourn, equip, arm, consider, place, forget],
    )


def loot_beam() -> Script:
    """SkylandsLootBeam extends ObjectReference: attached to the beam activators, which the class quest
    places over Skylands guns lying on the ground. The beam (and the light the quest placed with it)
    follows its gun and removes itself when the gun is picked up, gone or far away.

      ObjectReference target
      ObjectReference lamp
      SkylandsClassQuest owner

      Function Track(ObjectReference t, SkylandsClassQuest q, ObjectReference l)
        target = t
        owner = q
        lamp = l
        RegisterForSingleUpdate(1.0)
      EndFunction

      Event OnUpdate()
        Bool ok = False
        If target
          If !target.GetContainer()
            ok = target.Is3DLoaded()
          EndIf
        EndIf
        If ok
          MoveTo(target, 0.0, 0.0, 0.0, False)
          If light
            light.MoveTo(target, 0.0, 0.0, 0.0, False)
          EndIf
          RegisterForSingleUpdate(1.0)
        Else
          ... Forget, delete light, Disable, Delete
        EndIf
      EndEvent
    """
    track = Function(
        "Track",
        params=[("t", "ObjectReference"), ("q", "SkylandsClassQuest"), ("l", "ObjectReference")],
        locals=[("::nonevar", "None")],
        code=[
            ("assign", ("id", "target"), ("id", "t")),
            ("assign", ("id", "owner"), ("id", "q")),
            ("assign", ("id", "lamp"), ("id", "l")),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 1.0)),
            ("return", None),
        ],
    )
    on_update = Function(
        "OnUpdate",
        locals=[("::nonevar", "None"), ("ok", "Bool"), ("::temp0", "Bool"), ("c", "ObjectReference")],
        code=[
            ("assign", ("id", "ok"), ("bool", False)),
            ("cast", ("id", "::temp0"), ("id", "target")),
            ("jmpf", ("id", "::temp0"), ("lbl", "decide")),
            ("callmethod", ("id", "GetContainer"), ("id", "target"), ("id", "c")),
            ("cast", ("id", "::temp0"), ("id", "c")),
            ("jmpf", ("id", "::temp0"), ("lbl", "free")),
            ("jmp", ("lbl", "decide")),
            ("label", "free"),
            ("callmethod", ("id", "Is3DLoaded"), ("id", "target"), ("id", "ok")),
            ("label", "decide"),
            ("jmpf", ("id", "ok"), ("lbl", "gone")),
            ("callmethod", ("id", "MoveTo"), SELF, NONE, ("id", "target"), F0, F0, F0, ("bool", False)),
            ("cast", ("id", "::temp0"), ("id", "lamp")),
            ("jmpf", ("id", "::temp0"), ("lbl", "again")),
            ("callmethod", ("id", "MoveTo"), ("id", "lamp"), NONE, ("id", "target"), F0, F0, F0, ("bool", False)),
            ("label", "again"),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 1.0)),
            ("return", None),
            ("label", "gone"),
            ("cast", ("id", "::temp0"), ("id", "owner")),
            ("jmpf", ("id", "::temp0"), ("lbl", "nolight")),
            ("callmethod", ("id", "Forget"), ("id", "owner"), NONE, ("id", "target")),
            ("label", "nolight"),
            ("cast", ("id", "::temp0"), ("id", "lamp")),
            ("jmpf", ("id", "::temp0"), ("lbl", "kill")),
            ("callmethod", ("id", "Disable"), ("id", "lamp"), NONE, ("bool", False)),
            ("callmethod", ("id", "Delete"), ("id", "lamp"), NONE),
            ("label", "kill"),
            ("callmethod", ("id", "Disable"), SELF, NONE, ("bool", False)),
            ("callmethod", ("id", "Delete"), SELF, NONE),
            ("return", None),
        ],
    )
    return Script(
        name="SkylandsLootBeam",
        parent="ObjectReference",
        variables=[("target", "ObjectReference", None), ("lamp", "ObjectReference", None),
                   ("owner", "SkylandsClassQuest", None)],
        functions=[track, on_update],
    )
