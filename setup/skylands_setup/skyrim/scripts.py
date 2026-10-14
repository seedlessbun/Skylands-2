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


ARRAYS = [("array_create", ("id", name), ("int", size)) for name, size in (
    ("Tracked", 48), ("TrackedBeams", 48), ("TrackedLights", 48), ("RosterId", 128), ("RosterBase", 128), ("RosterX", 128),
    ("RosterY", 128), ("RosterZ", 128), ("RosterCell", 128), ("EntryCells", 16), ("EntryMarks", 16))]


def class_choice_quest() -> Script:
    """SkylandsClassQuest extends Quest.

    * Shows the vault hunter choice once the player can move, teaches and equips that vault hunter's
      shout, and hands over the starter gun, ammo and the respawn power.
    * Loot beams: Consider(ref) puts a rarity-coloured beam (a static) and light on a Skylands gun lying
      on the ground; Sweep() (every couple of seconds, from the player's watcher) moves them with the gun
      and removes them when the gun is picked up or unloaded.
    * Respawning: hostile people enlist themselves (Enlist); on a save load the player is asked whether to
      respawn them (Prompt), or the respawn power does it (Settings); Respawn() resets the enlisted ones
      in the player's area and, in an interior, moves the player to where they first came in (NoteEntrance).
    """
    on_init = Function(
        "OnInit",
        locals=[("::nonevar", "None")],
        code=[*ARRAYS, ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 2.0)), ("return", None)],
    )
    on_update = Function(
        "OnUpdate",
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            ("not", ("id", "::temp0"), ("id", "Chosen")),
            ("jmpf", ("id", "::temp0"), ("lbl", "ready")),
            call("Choose"),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 1.0)),
            ("return", None),
            ("label", "ready"),
            ("jmpf", ("id", "PendingPrompt"), ("lbl", "end")),
            call("Prompt"),
            ("label", "end"),
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
            ("callmethod", ("id", "AddSpell"), ("id", "player"), NONE, ("id", "::RespawnPower_var"), ("bool", False)),
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
    upgrade = Function(
        "Upgrade",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("n", "Int"), ("player", "Actor"), ("msg", "String")],
        code=[
            # a save made with an older version: make the arrays this version needs, and give the player the respawn power
            ("array_length", ("id", "n"), ("id", "RosterId")),
            ("cmp_lt", ("id", "::temp0"), ("id", "n"), ("int", 1)),
            ("jmpf", ("id", "::temp0"), ("lbl", "arrays_ok")),
            *ARRAYS,
            ("label", "arrays_ok"),
            ("jmpf", ("id", "Chosen"), ("lbl", "end")),
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "HasSpell"), ("id", "player"), ("id", "::temp0"), ("id", "::RespawnPower_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "give")),
            ("return", None),
            ("label", "give"),
            ("callmethod", ("id", "AddSpell"), ("id", "player"), NONE, ("id", "::RespawnPower_var"), ("bool", False)),
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "end")),
            *notify(("str", "Skylands: you learned the Pandora Respawn power")),
            ("label", "end"),
            ("return", None),
        ],
    )
    loaded = Function(
        "LoadedSave",
        locals=[("::nonevar", "None")],
        code=[
            call("Upgrade"),
            ("assign", ("id", "JustLoaded"), ("bool", True)),
            ("assign", ("id", "LastCell"), None),
            ("jmpf", ("id", "Chosen"), ("lbl", "end")),
            ("assign", ("id", "PendingPrompt"), ("bool", True)),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 3.0)),
            ("label", "end"),
            ("return", None),
        ],
    )
    prompt = Function(
        "Prompt",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("::temp1", "Bool"), ("pick", "Int")],
        code=[
            ("callstatic", ("id", "Utility"), ("id", "IsInMenuMode"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "not_menu")),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 1.0)),
            ("return", None),
            ("label", "not_menu"),
            ("callstatic", ("id", "Game"), ("id", "IsMovementControlsEnabled"), ("id", "::temp1")),
            ("not", ("id", "::temp0"), ("id", "::temp1")),
            ("jmpf", ("id", "::temp0"), ("lbl", "free")),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 1.0)),
            ("return", None),
            ("label", "free"),
            ("assign", ("id", "PendingPrompt"), ("bool", False)),
            ("cmp_eq", ("id", "::temp0"), ("id", "Mode"), ("int", 2)),
            ("jmpf", ("id", "::temp0"), ("lbl", "not_never")),
            ("return", None),
            ("label", "not_never"),
            ("cmp_eq", ("id", "::temp0"), ("id", "Mode"), ("int", 1)),
            ("jmpf", ("id", "::temp0"), ("lbl", "ask")),
            call("Respawn"),
            ("return", None),
            ("label", "ask"),
            ("callmethod", ("id", "Show"), ("id", "::PromptMsg_var"), ("id", "pick"), *ZERO9),
            ("cmp_eq", ("id", "::temp0"), ("id", "pick"), ("int", 0)),
            ("jmpf", ("id", "::temp0"), ("lbl", "not_now")),
            call("Respawn"),
            ("return", None),
            ("label", "not_now"),
            ("cmp_eq", ("id", "::temp0"), ("id", "pick"), ("int", 2)),
            ("jmpf", ("id", "::temp0"), ("lbl", "not_always")),
            ("assign", ("id", "Mode"), ("int", 1)),
            call("Respawn"),
            ("return", None),
            ("label", "not_always"),
            ("cmp_eq", ("id", "::temp0"), ("id", "pick"), ("int", 3)),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("assign", ("id", "Mode"), ("int", 2)),
            ("label", "end"),
            ("return", None),
        ],
    )
    settings = Function(
        "Settings",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("pick", "Int")],
        code=[
            ("callmethod", ("id", "Show"), ("id", "::SettingsMsg_var"), ("id", "pick"), *ZERO9),
            ("cmp_eq", ("id", "::temp0"), ("id", "pick"), ("int", 0)),
            ("jmpf", ("id", "::temp0"), ("lbl", "ask_me")),
            call("Respawn"),
            ("return", None),
            ("label", "ask_me"),
            ("cmp_eq", ("id", "::temp0"), ("id", "pick"), ("int", 1)),
            ("jmpf", ("id", "::temp0"), ("lbl", "always")),
            ("assign", ("id", "Mode"), ("int", 0)),
            ("return", None),
            ("label", "always"),
            ("cmp_eq", ("id", "::temp0"), ("id", "pick"), ("int", 2)),
            ("jmpf", ("id", "::temp0"), ("lbl", "never")),
            ("assign", ("id", "Mode"), ("int", 1)),
            ("return", None),
            ("label", "never"),
            ("cmp_eq", ("id", "::temp0"), ("id", "pick"), ("int", 3)),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("assign", ("id", "Mode"), ("int", 2)),
            ("label", "end"),
            ("return", None),
        ],
    )
    generation = Function(
        "GenerationNow", return_type="Int", locals=[],
        code=[("return", ("id", "Generation"))],
    )
    in_range = Function(
        "InRange",
        return_type="Bool",
        params=[("i", "Int"), ("cell", "Cell"), ("player", "Actor")],
        locals=[("::temp0", "Bool"), ("stored", "Cell"), ("px", "Float"), ("py", "Float"), ("dx", "Float"), ("dy", "Float"),
                ("x", "Float"), ("y", "Float")],
        code=[
            ("array_getelement", ("id", "stored"), ("id", "RosterCell"), ("id", "i")),
            ("callmethod", ("id", "IsInterior"), ("id", "cell"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "outside")),
            ("cmp_eq", ("id", "::temp0"), ("id", "stored"), ("id", "cell")),
            ("return", ("id", "::temp0")),
            ("label", "outside"),
            ("cast", ("id", "::temp0"), ("id", "stored")),
            ("jmpf", ("id", "::temp0"), ("lbl", "near")),
            ("callmethod", ("id", "IsInterior"), ("id", "stored"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "near")),
            ("return", ("bool", False)),
            ("label", "near"),
            ("callmethod", ("id", "GetPositionX"), ("id", "player"), ("id", "px")),
            ("callmethod", ("id", "GetPositionY"), ("id", "player"), ("id", "py")),
            ("array_getelement", ("id", "x"), ("id", "RosterX"), ("id", "i")),
            ("array_getelement", ("id", "y"), ("id", "RosterY"), ("id", "i")),
            ("fsub", ("id", "dx"), ("id", "x"), ("id", "px")),
            ("fsub", ("id", "dy"), ("id", "y"), ("id", "py")),
            ("fmul", ("id", "dx"), ("id", "dx"), ("id", "dx")),
            ("fmul", ("id", "dy"), ("id", "dy"), ("id", "dy")),
            ("fadd", ("id", "dx"), ("id", "dx"), ("id", "dy")),
            ("cmp_lt", ("id", "::temp0"), ("id", "dx"), ("float", 81000000.0)),
            ("return", ("id", "::temp0")),
        ],
    )
    respawn_one = Function(
        "RespawnOne",
        return_type="Bool",
        params=[("i", "Int"), ("player", "Actor")],
        locals=[("::temp0", "Bool"), ("id", "Int"), ("f", "Form"), ("a", "Actor"), ("old", "ObjectReference"),
                ("base", "Form"), ("n", "ObjectReference"), ("x", "Float"), ("y", "Float"), ("z", "Float"),
                ("px", "Float"), ("py", "Float"), ("pz", "Float")],
        code=[
            ("array_getelement", ("id", "id"), ("id", "RosterId"), ("id", "i")),
            ("callstatic", ("id", "Game"), ("id", "GetForm"), ("id", "f"), ("id", "id")),
            ("cast", ("id", "a"), ("id", "f")),
            ("cast", ("id", "::temp0"), ("id", "a")),
            ("jmpf", ("id", "::temp0"), ("lbl", "gone")),
            ("callmethod", ("id", "IsDead"), ("id", "a"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "living")),
            ("label", "gone"),
            ("cast", ("id", "old"), ("id", "f")),
            ("cast", ("id", "::temp0"), ("id", "old")),
            ("jmpf", ("id", "::temp0"), ("lbl", "spawn")),
            ("callmethod", ("id", "Disable"), ("id", "old"), NONE, ("bool", False)),
            ("callmethod", ("id", "Delete"), ("id", "old"), NONE),
            ("label", "spawn"),
            ("array_getelement", ("id", "base"), ("id", "RosterBase"), ("id", "i")),
            ("callmethod", ("id", "PlaceAtMe"), ("id", "player"), ("id", "n"), ("id", "base"), ("int", 1), ("bool", False),
             ("bool", False)),
            ("cast", ("id", "::temp0"), ("id", "n")),
            ("jmpf", ("id", "::temp0"), ("lbl", "failed")),
            ("array_getelement", ("id", "x"), ("id", "RosterX"), ("id", "i")),
            ("array_getelement", ("id", "y"), ("id", "RosterY"), ("id", "i")),
            ("array_getelement", ("id", "z"), ("id", "RosterZ"), ("id", "i")),
            ("callmethod", ("id", "GetPositionX"), ("id", "player"), ("id", "px")),
            ("callmethod", ("id", "GetPositionY"), ("id", "player"), ("id", "py")),
            ("callmethod", ("id", "GetPositionZ"), ("id", "player"), ("id", "pz")),
            ("fsub", ("id", "x"), ("id", "x"), ("id", "px")),
            ("fsub", ("id", "y"), ("id", "y"), ("id", "py")),
            ("fsub", ("id", "z"), ("id", "z"), ("id", "pz")),
            ("callmethod", ("id", "MoveTo"), ("id", "n"), NONE, ("id", "player"), ("id", "x"), ("id", "y"), ("id", "z"),
             ("bool", False)),
            ("callmethod", ("id", "GetFormID"), ("id", "n"), ("id", "id")),
            ("array_setelement", ("id", "RosterId"), ("id", "i"), ("id", "id")),
            ("return", ("bool", True)),
            ("label", "failed"),
            ("return", ("bool", False)),
            ("label", "living"),
            ("return", ("bool", False)),
        ],
    )
    respawn = Function(
        "Respawn",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("::temp1", "Bool"), ("player", "Actor"), ("cell", "Cell"),
                ("i", "Int"), ("n", "Int"), ("back", "Int"), ("known", "Int"), ("id", "Int"), ("m", "ObjectReference"),
                ("msg", "String"), ("a", "String"), ("b", "String"), ("c", "String")],
        code=[
            call("Upgrade"),
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "GetParentCell"), ("id", "player"), ("id", "cell")),
            ("iadd", ("id", "Generation"), ("id", "Generation"), ("int", 1)),
            ("assign", ("id", "i"), ("int", 0)),
            ("assign", ("id", "n"), ("int", 0)),
            ("assign", ("id", "back"), ("int", 0)),
            ("assign", ("id", "known"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("int", 128)),
            ("jmpf", ("id", "::temp0"), ("lbl", "done")),
            ("array_getelement", ("id", "id"), ("id", "RosterId"), ("id", "i")),
            ("cmp_eq", ("id", "::temp0"), ("id", "id"), ("int", 0)),
            ("jmpf", ("id", "::temp0"), ("lbl", "listed")),
            ("jmp", ("lbl", "next")),
            ("label", "listed"),
            ("iadd", ("id", "known"), ("id", "known"), ("int", 1)),
            ("callmethod", ("id", "InRange"), SELF, ("id", "::temp0"), ("id", "i"), ("id", "cell"), ("id", "player")),
            ("jmpf", ("id", "::temp0"), ("lbl", "next")),
            ("iadd", ("id", "n"), ("id", "n"), ("int", 1)),
            ("callmethod", ("id", "RespawnOne"), SELF, ("id", "::temp1"), ("id", "i"), ("id", "player")),
            ("jmpf", ("id", "::temp1"), ("lbl", "next")),
            ("iadd", ("id", "back"), ("id", "back"), ("int", 1)),
            ("label", "next"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "done"),
            ("callmethod", ("id", "EntranceFor"), SELF, ("id", "m"), ("id", "cell")),
            ("cast", ("id", "::temp0"), ("id", "m")),
            ("jmpf", ("id", "::temp0"), ("lbl", "say")),
            ("callmethod", ("id", "MoveTo"), ("id", "player"), NONE, ("id", "m"), F0, F0, F0, ("bool", True)),
            ("label", "say"),
            ("cast", ("id", "a"), ("id", "known")),
            ("cast", ("id", "b"), ("id", "n")),
            ("cast", ("id", "c"), ("id", "back")),
            *notify(("str", "Pandora respawn: "), ("id", "a"), ("str", " known, "), ("id", "b"), ("str", " here, "),
                    ("id", "c"), ("str", " respawned")),
            ("return", None),
        ],
    )
    enlist = Function(
        "Enlist",
        params=[("r", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("i", "Int"), ("e", "Int"), ("id", "Int"), ("x", "Float"),
                ("y", "Float"), ("z", "Float"), ("base", "Form"), ("cell", "Cell"), ("name", "String"), ("msg", "String")],
        code=[
            ("callmethod", ("id", "GetFormID"), ("id", "r"), ("id", "id")),
            ("assign", ("id", "i"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("int", 128)),
            ("jmpf", ("id", "::temp0"), ("lbl", "add")),
            ("array_getelement", ("id", "e"), ("id", "RosterId"), ("id", "i")),
            ("cmp_eq", ("id", "::temp0"), ("id", "e"), ("id", "id")),
            ("jmpf", ("id", "::temp0"), ("lbl", "cont")),
            ("return", None),
            ("label", "cont"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "add"),
            ("callmethod", ("id", "GetPositionX"), ("id", "r"), ("id", "x")),
            ("callmethod", ("id", "GetPositionY"), ("id", "r"), ("id", "y")),
            ("callmethod", ("id", "GetPositionZ"), ("id", "r"), ("id", "z")),
            ("callmethod", ("id", "GetBaseObject"), ("id", "r"), ("id", "base")),
            ("callmethod", ("id", "GetParentCell"), ("id", "r"), ("id", "cell")),
            ("array_setelement", ("id", "RosterId"), ("id", "RosterNext"), ("id", "id")),
            ("array_setelement", ("id", "RosterBase"), ("id", "RosterNext"), ("id", "base")),
            ("array_setelement", ("id", "RosterX"), ("id", "RosterNext"), ("id", "x")),
            ("array_setelement", ("id", "RosterY"), ("id", "RosterNext"), ("id", "y")),
            ("array_setelement", ("id", "RosterZ"), ("id", "RosterNext"), ("id", "z")),
            ("array_setelement", ("id", "RosterCell"), ("id", "RosterNext"), ("id", "cell")),
            ("iadd", ("id", "RosterNext"), ("id", "RosterNext"), ("int", 1)),
            ("imod", ("id", "RosterNext"), ("id", "RosterNext"), ("int", 128)),
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "end")),
            ("cmp_lt", ("id", "::temp0"), ("id", "Noted"), ("int", 3)),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("iadd", ("id", "Noted"), ("id", "Noted"), ("int", 1)),
            ("callmethod", ("id", "GetDisplayName"), ("id", "r"), ("id", "name")),
            *notify(("str", "Skylands: will respawn "), ("id", "name")),
            ("label", "end"),
            ("return", None),
        ],
    )
    entry_index = Function(
        "EntryIndex",
        return_type="Int",
        params=[("cell", "Cell")],
        locals=[("::temp0", "Bool"), ("i", "Int"), ("e", "Cell")],
        code=[
            ("assign", ("id", "i"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("int", 16)),
            ("jmpf", ("id", "::temp0"), ("lbl", "none")),
            ("array_getelement", ("id", "e"), ("id", "EntryCells"), ("id", "i")),
            ("cmp_eq", ("id", "::temp0"), ("id", "e"), ("id", "cell")),
            ("jmpf", ("id", "::temp0"), ("lbl", "cont")),
            ("return", ("id", "i")),
            ("label", "cont"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "none"),
            ("return", ("int", -1)),
        ],
    )
    entrance_for = Function(
        "EntranceFor",
        return_type="ObjectReference",
        params=[("cell", "Cell")],
        locals=[("::temp0", "Bool"), ("idx", "Int"), ("m", "ObjectReference")],
        code=[
            ("cast", ("id", "::temp0"), ("id", "cell")),
            ("jmpf", ("id", "::temp0"), ("lbl", "none")),
            ("callmethod", ("id", "EntryIndex"), SELF, ("id", "idx"), ("id", "cell")),
            ("cmp_lt", ("id", "::temp0"), ("id", "idx"), ("int", 0)),
            ("jmpf", ("id", "::temp0"), ("lbl", "found")),
            ("return", None),
            ("label", "found"),
            ("array_getelement", ("id", "m"), ("id", "EntryMarks"), ("id", "idx")),
            ("return", ("id", "m")),
            ("label", "none"),
            ("return", None),
        ],
    )
    note_entrance = Function(
        "NoteEntrance",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("player", "Actor"), ("cell", "Cell")],
        code=[
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "GetParentCell"), ("id", "player"), ("id", "cell")),
            ("cast", ("id", "::temp0"), ("id", "cell")),
            ("jmpf", ("id", "::temp0"), ("lbl", "nocell")),
            ("cmp_eq", ("id", "::temp0"), ("id", "cell"), ("id", "LastCell")),
            ("jmpf", ("id", "::temp0"), ("lbl", "changed")),
            ("return", None),
            ("label", "changed"),
            ("assign", ("id", "LastCell"), ("id", "cell")),
            ("jmpf", ("id", "JustLoaded"), ("lbl", "arrived")),
            ("assign", ("id", "JustLoaded"), ("bool", False)),
            ("return", None),
            ("label", "arrived"),
            call("Arrive", ("id", "cell")),
            ("return", None),
            ("label", "nocell"),
            ("return", None),
        ],
    )
    arrive = Function(
        "Arrive",
        params=[("cell", "Cell")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("player", "Actor"), ("idx", "Int"),
                ("m", "ObjectReference"), ("old", "ObjectReference")],
        code=[
            ("callmethod", ("id", "IsInterior"), ("id", "cell"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "outside")),
            ("callmethod", ("id", "EntryIndex"), SELF, ("id", "idx"), ("id", "cell")),
            ("cmp_lt", ("id", "::temp0"), ("id", "idx"), ("int", 0)),
            ("jmpf", ("id", "::temp0"), ("lbl", "known")),
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "PlaceAtMe"), ("id", "player"), ("id", "m"), ("id", "::MarkerForm_var"), ("int", 1),
             ("bool", True), ("bool", False)),
            ("array_getelement", ("id", "old"), ("id", "EntryMarks"), ("id", "EntryNext")),
            ("cast", ("id", "::temp0"), ("id", "old")),
            ("jmpf", ("id", "::temp0"), ("lbl", "store")),
            ("callmethod", ("id", "Delete"), ("id", "old"), NONE),
            ("label", "store"),
            ("array_setelement", ("id", "EntryCells"), ("id", "EntryNext"), ("id", "cell")),
            ("array_setelement", ("id", "EntryMarks"), ("id", "EntryNext"), ("id", "m")),
            ("iadd", ("id", "EntryNext"), ("id", "EntryNext"), ("int", 1)),
            ("imod", ("id", "EntryNext"), ("id", "EntryNext"), ("int", 16)),
            ("return", None),
            ("label", "known"),
            ("return", None),
            ("label", "outside"),
            ("return", None),
        ],
    )
    consider = Function(
        "Consider",
        params=[("r", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("k", "Int"), ("kw", "Keyword"), ("base", "Form"),
                ("has", "Bool"), ("hit", "Bool"), ("name", "String"), ("msg", "String")],
        code=[
            ("callmethod", ("id", "Alive"), SELF, ("id", "::temp0"), ("id", "r")),  # lying loose in the world, not carried or held
            ("jmpf", ("id", "::temp0"), ("lbl", "held")),
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
            ("label", "held"),
            ("return", None),
        ],
    )
    place = Function(
        "Place",
        params=[("r", "ObjectReference"), ("k", "Int")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("i", "Int"), ("e", "ObjectReference"), ("bs", "Form"),
                ("lt", "Light"), ("ln", "Int"), ("b", "ObjectReference"), ("lr", "ObjectReference"), ("slot", "Int")],
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
            ("assign", ("id", "slot"), ("id", "TrackedNext")),
            call("Clear", ("id", "slot")),
            ("array_setelement", ("id", "Tracked"), ("id", "slot"), ("id", "r")),
            ("array_setelement", ("id", "TrackedBeams"), ("id", "slot"), ("id", "b")),
            ("array_setelement", ("id", "TrackedLights"), ("id", "slot"), ("id", "lr")),
            ("iadd", ("id", "TrackedNext"), ("id", "slot"), ("int", 1)),
            ("imod", ("id", "TrackedNext"), ("id", "TrackedNext"), ("int", 48)),
            call("Report", ("id", "r"), ("id", "b"), ("id", "lr")),
            ("return", None),
        ],
    )
    report = Function(
        "Report",
        params=[("r", "ObjectReference"), ("b", "ObjectReference"), ("lr", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("name", "String"), ("msg", "String"), ("beam", "String"),
                ("lamp", "String")],
        code=[
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "end")),
            ("assign", ("id", "beam"), ("str", "ok")),
            ("cast", ("id", "::temp0"), ("id", "b")),
            ("jmpf", ("id", "::temp0"), ("lbl", "nobeam")),
            ("jmp", ("lbl", "lamp")),
            ("label", "nobeam"),
            ("assign", ("id", "beam"), ("str", "FAILED")),
            ("label", "lamp"),
            ("assign", ("id", "lamp"), ("str", "ok")),
            ("cast", ("id", "::temp0"), ("id", "lr")),
            ("jmpf", ("id", "::temp0"), ("lbl", "nolamp")),
            ("jmp", ("lbl", "say")),
            ("label", "nolamp"),
            ("assign", ("id", "lamp"), ("str", "FAILED")),
            ("label", "say"),
            ("callmethod", ("id", "GetDisplayName"), ("id", "r"), ("id", "name")),
            *notify(("str", "Skylands beam "), ("id", "beam"), ("str", ", light "), ("id", "lamp"), ("str", ": "), ("id", "name")),
            ("label", "end"),
            ("return", None),
        ],
    )
    clear = Function(
        "Clear",
        params=[("i", "Int")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("b", "ObjectReference"), ("lr", "ObjectReference")],
        code=[
            ("array_getelement", ("id", "b"), ("id", "TrackedBeams"), ("id", "i")),
            ("cast", ("id", "::temp0"), ("id", "b")),
            ("jmpf", ("id", "::temp0"), ("lbl", "lamp")),
            ("callmethod", ("id", "Disable"), ("id", "b"), NONE, ("bool", False)),
            ("callmethod", ("id", "Delete"), ("id", "b"), NONE),
            ("label", "lamp"),
            ("array_getelement", ("id", "lr"), ("id", "TrackedLights"), ("id", "i")),
            ("cast", ("id", "::temp0"), ("id", "lr")),
            ("jmpf", ("id", "::temp0"), ("lbl", "wipe")),
            ("callmethod", ("id", "Disable"), ("id", "lr"), NONE, ("bool", False)),
            ("callmethod", ("id", "Delete"), ("id", "lr"), NONE),
            ("label", "wipe"),
            ("array_setelement", ("id", "Tracked"), ("id", "i"), None),
            ("array_setelement", ("id", "TrackedBeams"), ("id", "i"), None),
            ("array_setelement", ("id", "TrackedLights"), ("id", "i"), None),
            ("return", None),
        ],
    )
    alive = Function(
        "Alive",
        return_type="Bool",
        params=[("g", "ObjectReference")],
        locals=[("::temp0", "Bool"), ("c", "ObjectReference")],
        code=[
            ("callmethod", ("id", "GetContainer"), ("id", "g"), ("id", "c")),
            ("cast", ("id", "::temp0"), ("id", "c")),
            ("jmpf", ("id", "::temp0"), ("lbl", "free")),
            ("return", ("bool", False)),
            ("label", "free"),
            ("callmethod", ("id", "Is3DLoaded"), ("id", "g"), ("id", "::temp0")),
            ("return", ("id", "::temp0")),
        ],
    )
    follow = Function(
        "Follow",
        params=[("i", "Int"), ("g", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("b", "ObjectReference"), ("lr", "ObjectReference")],
        code=[
            ("array_getelement", ("id", "b"), ("id", "TrackedBeams"), ("id", "i")),
            ("cast", ("id", "::temp0"), ("id", "b")),
            ("jmpf", ("id", "::temp0"), ("lbl", "lamp")),
            ("callmethod", ("id", "MoveTo"), ("id", "b"), NONE, ("id", "g"), F0, F0, F0, ("bool", False)),
            ("label", "lamp"),
            ("array_getelement", ("id", "lr"), ("id", "TrackedLights"), ("id", "i")),
            ("cast", ("id", "::temp0"), ("id", "lr")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("callmethod", ("id", "MoveTo"), ("id", "lr"), NONE, ("id", "g"), F0, F0, F0, ("bool", False)),
            ("label", "end"),
            ("return", None),
        ],
    )
    sweep = Function(
        "Sweep",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("i", "Int"), ("g", "ObjectReference")],
        code=[
            ("assign", ("id", "i"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("int", 48)),
            ("jmpf", ("id", "::temp0"), ("lbl", "done")),
            ("array_getelement", ("id", "g"), ("id", "Tracked"), ("id", "i")),
            ("cast", ("id", "::temp0"), ("id", "g")),
            ("jmpf", ("id", "::temp0"), ("lbl", "next")),
            ("callmethod", ("id", "Alive"), SELF, ("id", "::temp0"), ("id", "g")),
            ("jmpf", ("id", "::temp0"), ("lbl", "gone")),
            call("Follow", ("id", "i"), ("id", "g")),
            ("jmp", ("lbl", "next")),
            ("label", "gone"),
            call("Clear", ("id", "i")),
            ("label", "next"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "done"),
            ("return", None),
        ],
    )
    return Script(
        name="SkylandsClassQuest",
        parent="Quest",
        variables=[("Chosen", "Bool", ("bool", False)), ("PendingPrompt", "Bool", ("bool", False)),
                   ("JustLoaded", "Bool", ("bool", False)), ("Mode", "Int", ("int", 0)),
                   ("Generation", "Int", ("int", 0)), ("TrackedNext", "Int", ("int", 0)), ("RosterNext", "Int", ("int", 0)),
                   ("Noted", "Int", ("int", 0)),
                   ("EntryNext", "Int", ("int", 0)), ("LastCell", "Cell", None),
                   ("Tracked", "ObjectReference[]", None), ("TrackedBeams", "ObjectReference[]", None),
                   ("TrackedLights", "ObjectReference[]", None), ("RosterId", "Int[]", None), ("RosterBase", "Form[]", None),
                   ("RosterX", "Float[]", None), ("RosterY", "Float[]", None), ("RosterZ", "Float[]", None),
                   ("RosterCell", "Cell[]", None),
                   ("EntryCells", "Cell[]", None), ("EntryMarks", "ObjectReference[]", None)],
        auto_properties=[("ClassChoice", "Message"), ("Shouts", "Shout[]"), ("Words", "WordOfPower[]"),
                         ("StarterGun", "Form"), ("StarterAmmo", "Form"), ("RarityKeywords", "Keyword[]"),
                         ("Beams", "Form[]"), ("Lights", "Light[]"), ("Verbose", "Bool"), ("PromptMsg", "Message"),
                         ("SettingsMsg", "Message"), ("MarkerForm", "Form"), ("RespawnPower", "Spell")],
        functions=[on_init, on_update, choose, upgrade, loaded, prompt, settings, generation, in_range, respawn_one, respawn, enlist,
                   entry_index, entrance_for, note_entrance, arrive, consider, place, report, clear, alive, follow, sweep],
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
            ("callmethod", ("id", "Upgrade"), ("id", "::Owner_var"), NONE),
            ("callmethod", ("id", "GetEquippedWeapon"), ("id", "Me"), ("id", "w"), ("bool", False)),
            call("ApplySpeed", ("id", "w")),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 0.5)),
            ("return", None),
            ("label", "other"),
            ("callstatic", ("id", "Utility"), ("id", "RandomFloat"), ("id", "delay"), ("float", 1.5), ("float", 4.0)),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("id", "delay")),
            ("return", None),
        ],
    )
    on_update = Function(
        "OnUpdate",
        locals=[("::nonevar", "None"), ("::temp0", "Int"), ("::temp1", "Bool"), ("delay", "Float")],
        code=[
            ("jmpf", ("id", "IsPlayer"), ("lbl", "other")),
            call("PlayerTick"),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 0.5)),
            ("return", None),
            ("label", "other"),
            call("Maintain"),
            ("callstatic", ("id", "Utility"), ("id", "RandomFloat"), ("id", "delay"), ("float", 5.0), ("float", 8.0)),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("id", "delay")),
            ("return", None),
        ],
    )
    player_tick = Function(
        "PlayerTick",
        locals=[("::nonevar", "None"), ("::temp0", "Int"), ("::temp1", "Bool")],
        code=[
            ("callmethod", ("id", "NoteEntrance"), ("id", "::Owner_var"), NONE),
            ("iadd", ("id", "Ticks"), ("id", "Ticks"), ("int", 1)),
            ("imod", ("id", "::temp0"), ("id", "Ticks"), ("int", 4)),
            ("cmp_eq", ("id", "::temp1"), ("id", "::temp0"), ("int", 0)),
            ("jmpf", ("id", "::temp1"), ("lbl", "end")),
            call("Scan"),
            ("callmethod", ("id", "Sweep"), ("id", "::Owner_var"), NONE),
            ("label", "end"),
            ("return", None),
        ],
    )
    on_load = Function(
        "OnPlayerLoadGame",
        locals=[("::nonevar", "None")],
        code=[
            ("jmpf", ("id", "IsPlayer"), ("lbl", "end")),
            ("callmethod", ("id", "LoadedSave"), ("id", "::Owner_var"), NONE),
            ("label", "end"),
            ("return", None),
        ],
    )
    maintain = Function(
        "Maintain",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("g", "Int")],
        code=[
            ("not", ("id", "::temp0"), ("id", "Checked")),
            ("jmpf", ("id", "::temp0"), ("lbl", "checked")),
            ("assign", ("id", "Checked"), ("bool", True)),
            ("callmethod", ("id", "Eligible"), SELF, ("id", "Foe")),
            ("jmpf", ("id", "Foe"), ("lbl", "checked")),
            ("callmethod", ("id", "Enlist"), ("id", "::Owner_var"), NONE, ("id", "Me")),
            ("label", "checked"),
            ("jmpf", ("id", "Foe"), ("lbl", "end")),
            ("callmethod", ("id", "GenerationNow"), ("id", "::Owner_var"), ("id", "g")),
            ("cmp_eq", ("id", "::temp0"), ("id", "g"), ("id", "MyGen")),
            ("jmpf", ("id", "::temp0"), ("lbl", "renew")),
            ("jmp", ("lbl", "arm")),
            ("label", "renew"),
            ("assign", ("id", "MyGen"), ("id", "g")),
            ("assign", ("id", "Armed"), ("bool", False)),
            ("label", "arm"),
            call("TryArm"),
            ("label", "end"),
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
            ("callmethod", ("id", "AddItem"), ("id", "Me"), NONE, ("id", "f"), ("int", 1), ("bool", True)),
            ("callmethod", ("id", "Disable"), ("id", "g"), NONE, ("bool", False)),  # the copy that was placed is not left lying around
            ("callmethod", ("id", "Delete"), ("id", "g"), NONE),
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
                   ("Foe", "Bool", ("bool", False)), ("Checked", "Bool", ("bool", False)), ("MyGen", "Int", ("int", 0)),
                   ("Ticks", "Int", ("int", 0)), ("Speed", "Float", ("float", 0.0))],
        auto_properties=[("Owner", "SkylandsClassQuest"), ("GunKeyword", "Keyword"), ("SpeedKeywords", "Keyword[]"),
                         ("GunList", "FormList"), ("GunDrop", "Form"), ("GunDropGood", "Form"), ("NpcKeyword", "Keyword"),
                         ("Bolts", "Form"), ("ArmChance", "Int"), ("DropChance", "Int"), ("GoodLevel", "Int"),
                         ("ScanRadius", "Float"), ("Verbose", "Bool")],
        functions=[on_start, on_update, player_tick, on_load, maintain, on_equipped, on_unequipped, on_death, apply_speed, speed_of, scan, eligible,
                   worthy, roll, list_for, carrying, try_arm, equip, own_drop, bonus_drop, announce, cleanup],
    )


def respawn_power() -> Script:
    """SkylandsRespawn extends ActiveMagicEffect: the effect of the lesser power "Pandora Respawn" - it opens
    the respawn settings (Owner.Settings()).

      Event OnEffectStart(Actor akTarget, Actor akCaster)
        Owner.Settings()
      EndEvent
    """
    on_start = Function(
        "OnEffectStart",
        params=[("akTarget", "Actor"), ("akCaster", "Actor")],
        locals=[("::nonevar", "None")],
        code=[("callmethod", ("id", "Settings"), ("id", "::Owner_var"), NONE), ("return", None)],
    )
    return Script(
        name="SkylandsRespawn",
        parent="ActiveMagicEffect",
        auto_properties=[("Owner", "SkylandsClassQuest")],
        functions=[on_start],
    )
