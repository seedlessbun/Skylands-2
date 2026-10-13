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
    """SkylandsClassQuest extends Quest.

    * Shows the vault hunter choice once the player can move, teaches and equips that vault hunter's
      shout, and hands over the starter gun and ammo.
    * Keeps the loot beams: Consider(ref) puts a rarity-coloured beam and light on a Skylands gun lying
      on the ground (once per gun), Forget(ref) lets a gun get a new beam later.

    Properties: ClassChoice, Shouts, Words, StarterGun, StarterAmmo, RarityKeywords[6], Beams[6], Lights[6], Verbose.
    """
    on_init = Function(
        "OnInit",
        locals=[("::nonevar", "None")],
        code=[("array_create", ("id", "Tracked"), ("int", 48)),
              ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 2.0)), ("return", None)],
    )
    on_update = Function(
        "OnUpdate",
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            call("Choose"),
            ("jmpf", ("id", "Chosen"), ("lbl", "again")),
            ("return", None),
            ("label", "again"),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 1.0)),
            ("return", None),
        ],
    )
    # NB: jmpf Chosen jumps when NOT chosen: wait one more second and look again.
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
    consider = Function(
        "Consider",
        params=[("r", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("k", "Int"), ("kw", "Keyword"), ("base", "Form"),
                ("has", "Bool"), ("hit", "Bool"), ("name", "String"), ("msg", "String")],
        code=[
            ("callmethod", ("id", "GetBaseObject"), ("id", "r"), ("id", "base")),
            ("assign", ("id", "k"), ("int", 5)),
            ("label", "loop"),
            ("cmp_gte", ("id", "::temp0"), ("id", "k"), ("int", 0)),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("array_getelement", ("id", "kw"), ("id", "::RarityKeywords_var"), ("id", "k")),
            ("callmethod", ("id", "HasKeyword"), ("id", "base"), ("id", "has"), ("id", "kw")),
            ("jmpf", ("id", "has"), ("lbl", "lower")),
            ("assign", ("id", "hit"), ("bool", True)),
            call("Place", ("id", "r"), ("id", "k")),
            ("assign", ("id", "k"), ("int", -1)),  # found the highest rarity: stop
            ("jmp", ("lbl", "again")),
            ("label", "lower"),
            ("isub", ("id", "k"), ("id", "k"), ("int", 1)),
            ("label", "again"),
            ("jmp", ("lbl", "loop")),
            ("label", "end"),
            ("jmpf", ("id", "hit"), ("lbl", "miss")),
            ("return", None),
            ("label", "miss"),
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "out")),
            ("callmethod", ("id", "GetDisplayName"), ("id", "r"), ("id", "name")),
            *notify(("str", "Skylands: no rarity keyword on "), ("id", "name")),
            ("label", "out"),
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
            ("jmpf", ("id", "::temp0"), ("lbl", "broken")),
            ("callmethod", ("id", "Track"), ("id", "beam"), NONE, ("id", "r"), SELF, ("id", "lr")),
            ("array_setelement", ("id", "Tracked"), ("id", "TrackedNext"), ("id", "r")),
            ("iadd", ("id", "TrackedNext"), ("id", "TrackedNext"), ("int", 1)),
            ("imod", ("id", "TrackedNext"), ("id", "TrackedNext"), ("int", 48)),
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "end")),
            ("callmethod", ("id", "GetDisplayName"), ("id", "r"), ("id", "name")),
            *notify(("str", "Skylands beam: "), ("id", "name")),
            ("label", "end"),
            ("return", None),
            ("label", "broken"),
            call("Complain", ("id", "b")),
            ("return", None),
        ],
    )
    complain = Function(
        "Complain",
        params=[("b", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("msg", "String")],
        code=[
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "end")),
            ("cast", ("id", "::temp0"), ("id", "b")),
            ("jmpf", ("id", "::temp0"), ("lbl", "nomake")),
            *notify(("str", "Skylands: beam made but its script is not attached")),
            ("return", None),
            ("label", "nomake"),
            *notify(("str", "Skylands: the game did not make the beam")),
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
        variables=[("Chosen", "Bool", ("bool", False)), ("TrackedNext", "Int", ("int", 0)),
                   ("Tracked", "ObjectReference[]", None)],
        auto_properties=[("ClassChoice", "Message"), ("Shouts", "Shout[]"), ("Words", "WordOfPower[]"),
                         ("StarterGun", "Form"), ("StarterAmmo", "Form"), ("RarityKeywords", "Keyword[]"),
                         ("Beams", "Activator[]"), ("Lights", "Light[]"), ("Verbose", "Bool")],
        functions=[on_init, on_update, choose, consider, place, complain, forget],
    )


def watcher() -> Script:
    """SkylandsWatcher extends ActiveMagicEffect: the effect of an ability every humanoid race (and so
    every person, and the player) carries. It runs once per person.

    On the player: applies the equipped Skylands gun's speed as the player's WeaponSpeedMult (the speed is
    a "SkylandsSpeed_n" keyword on the gun) and, every 2 seconds, looks for Skylands guns lying near the
    player to give beams (Owner.Consider).
    On anyone else: a few seconds after loading, hostile humanoids may get a gun and ammo and wield it;
    when one dies its gun, or sometimes a new one, is dropped on the ground with a beam.

      Event OnEffectStart(Actor akTarget, Actor akCaster)
      Event OnUpdate()
      Event OnDeath(Actor akKiller)
      Event OnObjectEquipped(Form akBaseObject, ObjectReference akReference)
      Event OnObjectUnequipped(Form akBaseObject, ObjectReference akReference)
    """
    on_start = Function(
        "OnEffectStart",
        params=[("akTarget", "Actor"), ("akCaster", "Actor")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("player", "Actor"), ("w", "Weapon"), ("delay", "Float")],
        code=[
            ("assign", ("id", "Me"), ("id", "akTarget")),
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("cmp_eq", ("id", "::temp0"), ("id", "Me"), ("id", "player")),
            ("jmpf", ("id", "::temp0"), ("lbl", "other")),
            ("assign", ("id", "IsPlayer"), ("bool", True)),
            ("callmethod", ("id", "GetEquippedWeapon"), ("id", "Me"), ("id", "w"), ("bool", False)),
            call("ApplySpeed", ("id", "w")),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 2.0)),
            ("return", None),
            ("label", "other"),
            ("callstatic", ("id", "Utility"), ("id", "RandomFloat"), ("id", "delay"), ("float", 1.5), ("float", 4.0)),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("id", "delay")),
            ("return", None),
        ],
    )
    on_update = Function(
        "OnUpdate",
        locals=[("::nonevar", "None")],
        code=[
            ("jmpf", ("id", "IsPlayer"), ("lbl", "other")),
            call("Scan"),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 2.0)),
            ("return", None),
            ("label", "other"),
            call("TryArm"),
            ("return", None),
        ],
    )
    on_equipped = Function(
        "OnObjectEquipped",
        params=[("akBaseObject", "Form"), ("akReference", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("w", "Weapon")],
        code=[
            ("jmpf", ("id", "IsPlayer"), ("lbl", "end")),
            ("cast", ("id", "w"), ("id", "akBaseObject")),
            ("cast", ("id", "::temp0"), ("id", "w")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            call("ApplySpeed", ("id", "w")),
            ("label", "end"),
            ("return", None),
        ],
    )
    on_unequipped = Function(
        "OnObjectUnequipped",
        params=[("akBaseObject", "Form"), ("akReference", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("w", "Weapon")],
        code=[
            ("jmpf", ("id", "IsPlayer"), ("lbl", "end")),
            ("cast", ("id", "w"), ("id", "akBaseObject")),
            ("cast", ("id", "::temp0"), ("id", "w")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("callmethod", ("id", "GetEquippedWeapon"), ("id", "Me"), ("id", "w"), ("bool", False)),
            call("ApplySpeed", ("id", "w")),
            ("label", "end"),
            ("return", None),
        ],
    )
    apply_speed = Function(
        "ApplySpeed",
        params=[("w", "Weapon")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("::temp1", "Bool"), ("want", "Float"), ("got", "Float"),
                ("msg", "String"), ("part", "String")],
        code=[
            ("callmethod", ("id", "SpeedOf"), SELF, ("id", "want"), ("id", "w")),
            ("cmp_eq", ("id", "::temp0"), ("id", "want"), ("id", "Speed")),
            ("jmpf", ("id", "::temp0"), ("lbl", "change")),
            ("return", None),
            ("label", "change"),
            ("assign", ("id", "Speed"), ("id", "want")),
            ("callmethod", ("id", "SetActorValue"), ("id", "Me"), NONE, ("str", "WeaponSpeedMult"), ("id", "want")),
            ("cmp_eq", ("id", "::temp0"), ("id", "want"), ("float", 1.0)),
            ("jmpf", ("id", "::temp0"), ("lbl", "say")),
            ("return", None),
            ("label", "say"),
            ("cast", ("id", "msg"), ("id", "want")),
            ("callmethod", ("id", "GetActorValue"), ("id", "Me"), ("id", "got"), ("str", "WeaponSpeedMult")),
            ("cast", ("id", "part"), ("id", "got")),
            ("strcat", ("id", "msg"), ("str", "Skylands gun speed x"), ("id", "msg")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", " (game reports ")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "part")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", ")")),
            ("callstatic", ("id", "Debug"), ("id", "Notification"), NONE, ("id", "msg")),
            ("return", None),
        ],
    )
    speed_of = Function(
        "SpeedOf",
        return_type="Float",
        params=[("w", "Weapon")],
        locals=[("::temp0", "Bool"), ("::temp1", "Bool"), ("i", "Int"), ("n", "Int"), ("k", "Keyword"), ("f", "Float")],
        code=[
            ("cast", ("id", "::temp1"), ("id", "w")),
            ("jmpf", ("id", "::temp1"), ("lbl", "none")),
            ("callmethod", ("id", "HasKeyword"), ("id", "w"), ("id", "::temp0"), ("id", "::GunKeyword_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "none")),
            ("array_length", ("id", "n"), ("id", "::SpeedKeywords_var")),
            ("assign", ("id", "i"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("id", "n")),
            ("jmpf", ("id", "::temp0"), ("lbl", "done")),
            ("array_getelement", ("id", "k"), ("id", "::SpeedKeywords_var"), ("id", "i")),
            ("callmethod", ("id", "HasKeyword"), ("id", "w"), ("id", "::temp0"), ("id", "k")),
            ("jmpf", ("id", "::temp0"), ("lbl", "next")),
            ("cast", ("id", "f"), ("id", "i")),
            ("fmul", ("id", "f"), ("id", "f"), ("float", 0.05)),
            ("fadd", ("id", "f"), ("id", "f"), ("float", 0.5)),
            ("return", ("id", "f")),
            ("label", "next"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "done"),
            ("return", ("float", 1.0)),
            ("label", "none"),
            ("return", ("float", 1.0)),
        ],
    )
    scan = Function(
        "Scan",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("tries", "Int"), ("r", "ObjectReference"), ("x", "Float"),
                ("y", "Float"), ("z", "Float")],
        code=[
            ("callmethod", ("id", "GetPositionX"), ("id", "Me"), ("id", "x")),
            ("callmethod", ("id", "GetPositionY"), ("id", "Me"), ("id", "y")),
            ("callmethod", ("id", "GetPositionZ"), ("id", "Me"), ("id", "z")),
            ("assign", ("id", "tries"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "tries"), ("int", 6)),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("callstatic", ("id", "Game"), ("id", "FindRandomReferenceOfAnyTypeInList"), ("id", "r"),
             ("id", "::GunList_var"), ("id", "x"), ("id", "y"), ("id", "z"), ("id", "::ScanRadius_var")),
            ("cast", ("id", "::temp0"), ("id", "r")),
            ("jmpf", ("id", "::temp0"), ("lbl", "skip")),
            ("callmethod", ("id", "Consider"), ("id", "::Owner_var"), NONE, ("id", "r")),
            ("label", "skip"),
            ("iadd", ("id", "tries"), ("id", "tries"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "end"),
            ("return", None),
        ],
    )
    eligible = Function(
        "Eligible",
        return_type="Bool",
        locals=[("::temp0", "Bool"), ("player", "Actor")],
        code=[
            ("callmethod", ("id", "HasKeyword"), ("id", "Me"), ("id", "::temp0"), ("id", "::NpcKeyword_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "no")),
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "IsHostileToActor"), ("id", "Me"), ("id", "::temp0"), ("id", "player")),
            ("return", ("id", "::temp0")),
            ("label", "no"),
            ("return", ("bool", False)),
        ],
    )
    worthy = Function(
        "Worthy",
        return_type="Bool",
        params=[("killer", "Actor")],
        locals=[("::temp0", "Bool"), ("player", "Actor")],
        code=[
            ("callmethod", ("id", "HasKeyword"), ("id", "Me"), ("id", "::temp0"), ("id", "::NpcKeyword_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "no")),
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("cmp_eq", ("id", "::temp0"), ("id", "killer"), ("id", "player")),
            ("jmpf", ("id", "::temp0"), ("lbl", "hostile")),
            ("return", ("bool", True)),
            ("label", "hostile"),
            ("callmethod", ("id", "IsHostileToActor"), ("id", "Me"), ("id", "::temp0"), ("id", "player")),
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
        locals=[("::temp0", "Bool"), ("level", "Int")],
        code=[
            ("callmethod", ("id", "GetLevel"), ("id", "Me"), ("id", "level")),
            ("cmp_gte", ("id", "::temp0"), ("id", "level"), ("id", "::GoodLevel_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "plain")),
            ("return", ("id", "::GunDropGood_var")),
            ("label", "plain"),
            ("return", ("id", "::GunDrop_var")),
        ],
    )
    carrying = Function(
        "Carrying",
        return_type="Bool",
        locals=[("::temp0", "Bool"), ("w", "Weapon")],
        code=[
            ("callmethod", ("id", "GetEquippedWeapon"), ("id", "Me"), ("id", "w"), ("bool", False)),
            ("cast", ("id", "::temp0"), ("id", "w")),
            ("jmpf", ("id", "::temp0"), ("lbl", "no")),
            ("callmethod", ("id", "HasKeyword"), ("id", "w"), ("id", "::temp0"), ("id", "::GunKeyword_var")),
            ("return", ("id", "::temp0")),
            ("label", "no"),
            ("return", ("bool", False)),
        ],
    )
    try_arm = Function(
        "TryArm",
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            ("jmpf", ("id", "Armed"), ("lbl", "first")),
            ("return", None),
            ("label", "first"),
            ("assign", ("id", "Armed"), ("bool", True)),
            ("callmethod", ("id", "IsDead"), ("id", "Me"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "alive")),
            ("return", None),
            ("label", "alive"),
            ("callmethod", ("id", "Carrying"), SELF, ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "bare")),
            ("return", None),
            ("label", "bare"),
            ("callmethod", ("id", "Eligible"), SELF, ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("callmethod", ("id", "Roll"), SELF, ("id", "::temp0"), ("id", "::ArmChance_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            call("Equip"),
            ("label", "end"),
            ("return", None),
        ],
    )
    equip = Function(
        "Equip",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("g", "ObjectReference"), ("f", "Form"), ("msg", "String"),
                ("name", "String"), ("what", "String"), ("list", "Form")],
        code=[
            ("callmethod", ("id", "ListFor"), SELF, ("id", "list")),
            ("callmethod", ("id", "PlaceAtMe"), ("id", "Me"), ("id", "g"), ("id", "list"), ("int", 1), ("bool", False),
             ("bool", False)),
            ("cast", ("id", "::temp0"), ("id", "g")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("callmethod", ("id", "GetBaseObject"), ("id", "g"), ("id", "f")),
            ("callmethod", ("id", "AddItem"), ("id", "Me"), NONE, ("id", "g"), ("int", 1), ("bool", True)),
            ("callmethod", ("id", "AddItem"), ("id", "Me"), NONE, ("id", "::Bolts_var"), ("int", 30), ("bool", True)),
            ("callmethod", ("id", "EquipItem"), ("id", "Me"), NONE, ("id", "f"), ("bool", False), ("bool", True)),
            ("callmethod", ("id", "EquipItem"), ("id", "Me"), NONE, ("id", "::Bolts_var"), ("bool", False),
             ("bool", True)),
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "end")),
            ("callmethod", ("id", "GetDisplayName"), ("id", "Me"), ("id", "name")),
            ("callmethod", ("id", "GetName"), ("id", "f"), ("id", "what")),
            *notify(("id", "name"), ("str", " carries "), ("id", "what")),
            ("label", "end"),
            ("return", None),
        ],
    )
    own_drop = Function(
        "OwnDrop",
        return_type="ObjectReference",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("w", "Weapon"), ("drop", "ObjectReference")],
        code=[
            ("callmethod", ("id", "GetEquippedWeapon"), ("id", "Me"), ("id", "w"), ("bool", False)),
            ("cast", ("id", "::temp0"), ("id", "w")),
            ("jmpf", ("id", "::temp0"), ("lbl", "none")),
            ("callmethod", ("id", "HasKeyword"), ("id", "w"), ("id", "::temp0"), ("id", "::GunKeyword_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "none")),
            ("callmethod", ("id", "UnequipItem"), ("id", "Me"), NONE, ("id", "w"), ("bool", False), ("bool", True)),
            ("callmethod", ("id", "DropObject"), ("id", "Me"), ("id", "drop"), ("id", "w"), ("int", 1)),
            ("return", ("id", "drop")),
            ("label", "none"),
            ("return", None),
        ],
    )
    bonus_drop = Function(
        "BonusDrop",
        return_type="ObjectReference",
        params=[("killer", "Actor")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("list", "Form"), ("drop", "ObjectReference")],
        code=[
            ("callmethod", ("id", "Worthy"), SELF, ("id", "::temp0"), ("id", "killer")),
            ("jmpf", ("id", "::temp0"), ("lbl", "none")),
            ("callmethod", ("id", "Roll"), SELF, ("id", "::temp0"), ("id", "::DropChance_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "none")),
            ("callmethod", ("id", "ListFor"), SELF, ("id", "list")),
            ("callmethod", ("id", "PlaceAtMe"), ("id", "Me"), ("id", "drop"), ("id", "list"), ("int", 1), ("bool", False),
             ("bool", False)),
            ("return", ("id", "drop")),
            ("label", "none"),
            ("return", None),
        ],
    )
    announce = Function(
        "Announce",
        params=[("drop", "ObjectReference")],
        locals=[("::nonevar", "None"), ("name", "String"), ("msg", "String")],
        code=[
            ("callmethod", ("id", "Consider"), ("id", "::Owner_var"), NONE, ("id", "drop")),
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "end")),
            ("callmethod", ("id", "GetDisplayName"), ("id", "drop"), ("id", "name")),
            *notify(("str", "Skylands drop: "), ("id", "name")),
            ("label", "end"),
            ("return", None),
        ],
    )
    cleanup = Function(
        "Cleanup",
        params=[("akKiller", "Actor")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("drop", "ObjectReference")],
        code=[
            ("callmethod", ("id", "OwnDrop"), SELF, ("id", "drop")),
            ("cast", ("id", "::temp0"), ("id", "drop")),
            ("jmpf", ("id", "::temp0"), ("lbl", "bonus")),
            call("Announce", ("id", "drop")),
            ("return", None),
            ("label", "bonus"),
            ("callmethod", ("id", "BonusDrop"), SELF, ("id", "drop"), ("id", "akKiller")),
            ("cast", ("id", "::temp0"), ("id", "drop")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            call("Announce", ("id", "drop")),
            ("label", "end"),
            ("return", None),
        ],
    )
    on_death = Function(
        "OnDeath",
        params=[("akKiller", "Actor")],
        locals=[("::nonevar", "None")],
        code=[
            ("jmpf", ("id", "IsPlayer"), ("lbl", "npc")),
            ("return", None),
            ("label", "npc"),
            call("Cleanup", ("id", "akKiller")),
            ("return", None),
        ],
    )
    return Script(
        name="SkylandsWatcher",
        parent="ActiveMagicEffect",
        variables=[("Me", "Actor", None), ("IsPlayer", "Bool", ("bool", False)), ("Armed", "Bool", ("bool", False)),
                   ("Speed", "Float", ("float", 0.0))],
        auto_properties=[("Owner", "SkylandsClassQuest"), ("GunKeyword", "Keyword"), ("SpeedKeywords", "Keyword[]"),
                         ("GunList", "FormList"), ("GunDrop", "Form"), ("GunDropGood", "Form"), ("NpcKeyword", "Keyword"),
                         ("Bolts", "Form"), ("ArmChance", "Int"), ("DropChance", "Int"), ("GoodLevel", "Int"),
                         ("ScanRadius", "Float"), ("Verbose", "Bool")],
        functions=[on_start, on_update, on_equipped, on_unequipped, on_death, apply_speed, speed_of, scan, eligible,
                   worthy, roll, list_for, carrying, try_arm, equip, own_drop, bonus_drop, announce, cleanup],
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
          If lamp
            lamp.MoveTo(target, 0.0, 0.0, 0.0, False)
          EndIf
          RegisterForSingleUpdate(1.0)
        Else
          ... Forget, delete lamp, Disable, Delete
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
