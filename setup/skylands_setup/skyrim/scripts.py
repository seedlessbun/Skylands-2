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


def class_choice_quest() -> Script:
    """SkylandsClassQuest extends Quest: the vault hunter choice, then a once-a-second tick.

      Event OnInit()
        Tracked = new ObjectReference[48]
        RegisterForSingleUpdate(2.0)
      EndEvent

      Event OnUpdate()
        If !Chosen
          Choose()   ; waits for a menu-free moment, then shows the choice and gives shout, gun and ammo
        EndIf
        If Chosen
          Tick()
        EndIf
        RegisterForSingleUpdate(1.0)
      EndEvent

      Function Tick()   ; the equipped Skylands gun's speed goes into the player's weapon speed
        Weapon w = Game.GetPlayer().GetEquippedWeapon(False)
        Float want = 1.0
        If w && w.HasKeyword(GunKeyword)
          want = w.GetReach()      ; the speed is stored in the gun's reach, which guns do not otherwise use
        EndIf
        ...SetActorValue("WeaponSpeedMult", want) and a notification when it changes...
        every other tick: Scan()
      EndFunction

      Function Scan()    ; loot beams over Skylands guns lying in the cell or carried by corpses
      Function Consider(ObjectReference r, Bool corpse)
      Function Place(ObjectReference r, Int k, Bool corpse)
      Function Forget(ObjectReference t)
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
    tick = Function(
        "Tick",
        locals=[("::nonevar", "None"), ("player", "Actor"), ("w", "Weapon"), ("want", "Float"), ("::temp0", "Bool"),
                ("::temp1", "Bool"), ("msg", "String"), ("part", "String"), ("got", "Float")],
        code=[
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "GetEquippedWeapon"), ("id", "player"), ("id", "w"), ("bool", False)),
            ("assign", ("id", "want"), ("float", 1.0)),
            ("cast", ("id", "::temp0"), ("id", "w")),
            ("jmpf", ("id", "::temp0"), ("lbl", "speed")),
            ("callmethod", ("id", "HasKeyword"), ("id", "w"), ("id", "::temp1"), ("id", "::GunKeyword_var")),
            ("jmpf", ("id", "::temp1"), ("lbl", "speed")),
            ("callmethod", ("id", "GetReach"), ("id", "w"), ("id", "want")),
            ("label", "speed"),
            ("cmp_eq", ("id", "::temp0"), ("id", "want"), ("id", "Speed")),
            ("not", ("id", "::temp1"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp1"), ("lbl", "scan")),  # unchanged: nothing to apply
            ("assign", ("id", "Speed"), ("id", "want")),
            ("callmethod", ("id", "SetActorValue"), ("id", "player"), NONE, ("str", "WeaponSpeedMult"), ("id", "want")),
            ("cmp_eq", ("id", "::temp0"), ("id", "want"), ("float", 1.0)),
            ("not", ("id", "::temp1"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp1"), ("lbl", "scan")),  # back to normal speed: no message
            ("cast", ("id", "msg"), ("id", "want")),
            ("strcat", ("id", "msg"), ("str", "Skylands gun speed x"), ("id", "msg")),
            ("callmethod", ("id", "GetActorValue"), ("id", "player"), ("id", "got"), ("str", "WeaponSpeedMult")),
            ("cast", ("id", "part"), ("id", "got")),
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
        code = [
            ("callmethod", ("id", "GetNumRefs"), ("id", "cell"), ("id", "n"), ("int", kind)),
            ("assign", ("id", "i"), ("int", 0)),
            ("label", f"{tag}_loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("id", "n")),
            ("jmpf", ("id", "::temp0"), ("lbl", f"{tag}_done")),
            ("callmethod", ("id", "GetNthRef"), ("id", "cell"), ("id", "r"), ("id", "i"), ("int", kind)),
        ]
        if actors:
            code += [
                ("cast", ("id", "a"), ("id", "r")),
                ("cast", ("id", "::temp0"), ("id", "a")),
                ("jmpf", ("id", "::temp0"), ("lbl", f"{tag}_next")),
                ("callmethod", ("id", "IsDead"), ("id", "a"), ("id", "::temp1")),
                ("jmpf", ("id", "::temp1"), ("lbl", f"{tag}_next")),
            ]
        code += [
            call("Consider", ("id", "r"), ("bool", actors)),
            ("label", f"{tag}_next"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", f"{tag}_loop")),
            ("label", f"{tag}_done"),
        ]
        return code

    scan = Function(
        "Scan",
        locals=[("::nonevar", "None"), ("player", "Actor"), ("cell", "Cell"), ("n", "Int"), ("i", "Int"),
                ("r", "ObjectReference"), ("a", "Actor"), ("::temp0", "Bool"), ("::temp1", "Bool")],
        code=[
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "GetParentCell"), ("id", "player"), ("id", "cell")),
            ("cast", ("id", "::temp0"), ("id", "cell")),
            ("jmpf", ("id", "::temp0"), ("lbl", "nocell")),
            *scan_loop(41, False),  # weapons lying in the world
            *scan_loop(43, True),   # actors: dead ones may carry a Skylands gun
            ("return", None),
            ("label", "nocell"),
            ("return", None),
        ],
    )
    has_kw = Function(
        "Has",
        return_type="Bool",
        params=[("r", "ObjectReference"), ("kw", "Keyword"), ("corpse", "Bool")],
        locals=[("n", "Int"), ("base", "Form"), ("has", "Bool"), ("::temp0", "Bool")],
        code=[
            ("jmpf", ("id", "corpse"), ("lbl", "weapon")),
            ("callmethod", ("id", "GetItemCount"), ("id", "r"), ("id", "n"), ("id", "kw")),
            ("cmp_gt", ("id", "::temp0"), ("id", "n"), ("int", 0)),
            ("return", ("id", "::temp0")),
            ("label", "weapon"),
            ("callmethod", ("id", "GetBaseObject"), ("id", "r"), ("id", "base")),
            ("callmethod", ("id", "HasKeyword"), ("id", "base"), ("id", "has"), ("id", "kw")),
            ("return", ("id", "has")),
        ],
    )
    consider = Function(
        "Consider",
        params=[("r", "ObjectReference"), ("corpse", "Bool")],
        locals=[("::nonevar", "None"), ("player", "Actor"), ("d", "Float"), ("::temp0", "Bool"), ("k", "Int"),
                ("kw", "Keyword"), ("has", "Bool")],
        code=[
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "GetDistance"), ("id", "r"), ("id", "d"), ("id", "player")),
            ("cmp_lte", ("id", "::temp0"), ("id", "d"), ("float", 4500.0)),
            ("jmpf", ("id", "::temp0"), ("lbl", "far")),
            ("assign", ("id", "k"), ("int", 5)),
            ("label", "loop"),
            ("cmp_gte", ("id", "::temp0"), ("id", "k"), ("int", 0)),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("array_getelement", ("id", "kw"), ("id", "::RarityKeywords_var"), ("id", "k")),
            ("callmethod", ("id", "Has"), SELF, ("id", "has"), ("id", "r"), ("id", "kw"), ("id", "corpse")),
            ("jmpf", ("id", "has"), ("lbl", "lower")),
            call("Place", ("id", "r"), ("id", "k"), ("id", "corpse")),
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
        params=[("r", "ObjectReference"), ("k", "Int"), ("corpse", "Bool")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("::temp1", "Bool"), ("i", "Int"), ("e", "ObjectReference"),
                ("bs", "Activator"), ("kw", "Keyword"), ("b", "ObjectReference"), ("beam", "SkylandsLootBeam")],
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
            ("array_getelement", ("id", "kw"), ("id", "::RarityKeywords_var"), ("id", "k")),
            ("callmethod", ("id", "PlaceAtMe"), ("id", "r"), ("id", "b"), ("id", "bs"), ("int", 1), ("bool", False),
             ("bool", False)),
            ("cast", ("id", "beam"), ("id", "b")),
            ("cast", ("id", "::temp0"), ("id", "beam")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("callmethod", ("id", "Track"), ("id", "beam"), NONE, ("id", "r"), ("id", "kw"), ("id", "corpse"), SELF),
            ("array_setelement", ("id", "Tracked"), ("id", "TrackedNext"), ("id", "r")),
            ("iadd", ("id", "TrackedNext"), ("id", "TrackedNext"), ("int", 1)),
            ("imod", ("id", "TrackedNext"), ("id", "TrackedNext"), ("int", 48)),
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
                   ("ScanNow", "Bool", ("bool", False)), ("TrackedNext", "Int", ("int", 0)),
                   ("Tracked", "ObjectReference[]", None)],
        auto_properties=[("ClassChoice", "Message"), ("Shouts", "Shout[]"), ("Words", "WordOfPower[]"),
                         ("StarterGun", "Form"), ("StarterAmmo", "Form"), ("GunKeyword", "Keyword"),
                         ("RarityKeywords", "Keyword[]"), ("Beams", "Activator[]")],
        functions=[on_init, on_update, choose, tick, scan, has_kw, consider, place, forget],
    )


def loot_beam() -> Script:
    """SkylandsLootBeam extends ObjectReference: attached to the beam activators, which the class quest
    places over Skylands guns lying on the ground or carried by corpses. The beam follows its gun and
    removes itself when the gun is picked up, looted or gone.

      ObjectReference target
      Keyword kw
      Bool corpse
      SkylandsClassQuest owner

      Function Track(ObjectReference t, Keyword k, Bool isCorpse, SkylandsClassQuest q)
        target = t
        kw = k
        corpse = isCorpse
        owner = q
        RegisterForSingleUpdate(1.0)
      EndFunction

      Event OnUpdate()
        Bool ok = False
        If target
          If corpse
            ok = target.GetItemCount(kw) > 0
          Else
            ok = !target.GetContainer()
          EndIf
        EndIf
        If ok
          MoveTo(target, 0.0, 0.0, 0.0, False)
          RegisterForSingleUpdate(1.0)
        Else
          If owner
            owner.Forget(target)
          EndIf
          Disable(False)
          Delete()
        EndIf
      EndEvent
    """
    track = Function(
        "Track",
        params=[("t", "ObjectReference"), ("k", "Keyword"), ("isCorpse", "Bool"), ("q", "SkylandsClassQuest")],
        locals=[("::nonevar", "None")],
        code=[
            ("assign", ("id", "target"), ("id", "t")),
            ("assign", ("id", "kw"), ("id", "k")),
            ("assign", ("id", "corpse"), ("id", "isCorpse")),
            ("assign", ("id", "owner"), ("id", "q")),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 1.0)),
            ("return", None),
        ],
    )
    on_update = Function(
        "OnUpdate",
        locals=[("::nonevar", "None"), ("ok", "Bool"), ("::temp0", "Bool"), ("n", "Int"), ("c", "ObjectReference")],
        code=[
            ("assign", ("id", "ok"), ("bool", False)),
            ("cast", ("id", "::temp0"), ("id", "target")),
            ("jmpf", ("id", "::temp0"), ("lbl", "decide")),
            ("jmpf", ("id", "corpse"), ("lbl", "weapon")),
            ("callmethod", ("id", "GetItemCount"), ("id", "target"), ("id", "n"), ("id", "kw")),
            ("cmp_gt", ("id", "ok"), ("id", "n"), ("int", 0)),
            ("jmp", ("lbl", "decide")),
            ("label", "weapon"),
            ("callmethod", ("id", "GetContainer"), ("id", "target"), ("id", "c")),
            ("cast", ("id", "::temp0"), ("id", "c")),
            ("not", ("id", "ok"), ("id", "::temp0")),
            ("label", "decide"),
            ("jmpf", ("id", "ok"), ("lbl", "gone")),
            ("callmethod", ("id", "MoveTo"), SELF, NONE, ("id", "target"), F0, F0, F0, ("bool", False)),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 1.0)),
            ("return", None),
            ("label", "gone"),
            ("cast", ("id", "::temp0"), ("id", "owner")),
            ("jmpf", ("id", "::temp0"), ("lbl", "kill")),
            ("callmethod", ("id", "Forget"), ("id", "owner"), NONE, ("id", "target")),
            ("label", "kill"),
            ("callmethod", ("id", "Disable"), SELF, NONE, ("bool", False)),
            ("callmethod", ("id", "Delete"), SELF, NONE),
            ("return", None),
        ],
    )
    return Script(
        name="SkylandsLootBeam",
        parent="ObjectReference",
        variables=[("target", "ObjectReference", None), ("kw", "Keyword", None), ("corpse", "Bool", ("bool", False)),
                   ("owner", "SkylandsClassQuest", None)],
        functions=[track, on_update],
    )
