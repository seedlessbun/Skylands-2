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


ARRAY_SIZES = (("Tracked", 48), ("TrackedBeams", 48), ("TrackedLights", 48), ("RosterRef", 128), ("RosterBase", 128),
               ("RosterX", 128), ("RosterY", 128), ("RosterZ", 128), ("RosterCell", 128), ("EntryCells", 16),
               ("EntryMarks", 16))
ARRAYS = [("array_create", ("id", name), ("int", size)) for name, size in ARRAY_SIZES]
# only the ones that are missing or of another length (an array is empty until it is created, and a save keeps the
# length it was made with), one by one
ARRAYS_IF_MISSING = [ins for name, size in ARRAY_SIZES for ins in (
    ("array_length", ("id", "n"), ("id", name)),
    ("cmp_eq", ("id", "::temp0"), ("id", "n"), ("int", size)),
    ("jmpf", ("id", "::temp0"), ("lbl", f"make_{name}")),
    ("jmp", ("lbl", f"have_{name}")),
    ("label", f"make_{name}"),
    ("array_create", ("id", name), ("int", size)),
    ("label", f"have_{name}"))]


def class_choice_quest() -> Script:
    """SkylandsHunterQuest extends Quest.

    * Shows the vault hunter choice once the player can move, teaches and equips that vault hunter's
      shout, and hands over the starter gun, ammo and the respawn power.
    * Loot beams: Consider(ref) puts a rarity-coloured beam (a static) and light on a Skylands gun lying
      on the ground; Sweep() (every couple of seconds, from the player's watcher) moves them with the gun
      and removes them when the gun is picked up or unloaded.
    * Respawning: hostile people enlist themselves (Remember); on a save load the player is asked whether to
      respawn them (Prompt), or the respawn power does it (Settings); Respawn() resets the enlisted ones
      in the player's area and, in an interior, moves the player to where they first came in (NoteEntrance).
    """
    on_init = Function(
        "OnInit",
        locals=[("::nonevar", "None")],
        code=[*ARRAYS, ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 2.0)), ("return", None)],
    )
    bootstrap = Function(
        "Bootstrap",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("player", "Actor"), ("f", "Form")],
        code=[
            # this quest's own properties are fresh, so it can give the player the ability that carries the watcher;
            # only when missing: adding it again restarts the effect. The property is ::AbilityInit_var (the log of 0.13 said
            # "Failed to find variable AbilityInit") and HasSpell takes a Form, not a Spell
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("cast", ("id", "f"), ("id", "::AbilityInit_var")),
            ("callmethod", ("id", "HasSpell"), ("id", "player"), ("id", "::temp0"), ("id", "f")),
            ("jmpf", ("id", "::temp0"), ("lbl", "add")),
            ("return", None),
            ("label", "add"),
            ("callmethod", ("id", "AddSpell"), ("id", "player"), NONE, ("id", "::AbilityInit_var"), ("bool", False)),
            ("return", None),
        ],
    )
    on_update = Function(
        "OnUpdate",
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            call("Bootstrap"),
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
            ("jmpf", ("id", "Refreshed"), ("lbl", "waiting")),
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
            ("callmethod", ("id", "AddSpell"), ("id", "player"), NONE, ("id", "::LogPower_var"), ("bool", False)),
            ("callmethod", ("id", "AddItem"), ("id", "player"), NONE, ("id", "::StarterGun_var"),
             ("int", 1), ("bool", False)),
            ("callmethod", ("id", "AddItem"), ("id", "player"), NONE, ("id", "::StarterAmmo_var"),
             ("int", 60), ("bool", False)),
            ("callmethod", ("id", "EquipItem"), ("id", "player"), NONE, ("id", "::StarterGun_var"),
             ("bool", False), ("bool", False)),
            ("assign", ("id", "Chosen"), ("bool", True)),
            ("return", None),
            ("label", "waiting"),
            ("return", None),
        ],
    )
    make_arrays = Function(
        "MakeArrays",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("n", "Int")],
        code=[*ARRAYS_IF_MISSING, ("return", None)],
    )
    refresh = Function(
        "Refresh",
        params=[("pRarity", "Keyword[]"), ("pBeams", "Form[]"), ("pLights", "Light[]"), ("pPrompt", "Message"),
                ("pSettings", "Message"), ("pMarker", "Form"), ("pRespawn", "Spell"), ("pLog", "Spell"),
                ("pAbility", "Spell"), ("pNpc", "Keyword"), ("pRadius", "Float"), ("pVerbose", "Bool")],
        locals=[("::nonevar", "None")],
        code=[
            # The values a saved game keeps for this script's properties are from the version it was made with and can
            # point at records that have since moved; the player's ability script has the right ones and hands them over.
            ("assign", ("id", "::RarityKeywords_var"), ("id", "pRarity")),
            ("assign", ("id", "::Beams_var"), ("id", "pBeams")),
            ("assign", ("id", "::Lights_var"), ("id", "pLights")),
            ("assign", ("id", "::PromptMsg_var"), ("id", "pPrompt")),
            ("assign", ("id", "::SettingsMsg_var"), ("id", "pSettings")),
            ("assign", ("id", "::MarkerForm_var"), ("id", "pMarker")),
            ("assign", ("id", "::RespawnPower_var"), ("id", "pRespawn")),
            ("assign", ("id", "::LogPower_var"), ("id", "pLog")),
            ("assign", ("id", "::Ability_var"), ("id", "pAbility")),
            ("assign", ("id", "::NpcKeyword_var"), ("id", "pNpc")),
            ("assign", ("id", "::LogRadius_var"), ("id", "pRadius")),
            ("assign", ("id", "::Verbose_var"), ("id", "pVerbose")),
            ("assign", ("id", "Refreshed"), ("bool", True)),
            ("return", None),
        ],
    )
    upgrade = Function(
        "Upgrade",
        locals=[("::nonevar", "None")],
        code=[
            # a save made with an older version: make the arrays this version needs (the player's ability script gives the powers)
            call("MakeArrays"),
            ("return", None),
        ],
    )
    loaded = Function(
        "LoadedSave",
        locals=[("::nonevar", "None")],
        code=[
            call("Bootstrap"),
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
    remove = Function(
        "Remove",
        params=[("old", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            ("cast", ("id", "::temp0"), ("id", "old")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("callmethod", ("id", "Disable"), ("id", "old"), NONE, ("bool", False)),
            ("callmethod", ("id", "Delete"), ("id", "old"), NONE),
            ("label", "end"),
            ("return", None),
        ],
    )
    spawn = Function(
        "Spawn",
        return_type="Bool",
        params=[("i", "Int"), ("player", "Actor")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("base", "Form"), ("n", "ObjectReference"), ("x", "Float"), ("y", "Float"),
                ("z", "Float"), ("px", "Float"), ("py", "Float"), ("pz", "Float")],
        code=[
            ("array_getelement", ("id", "base"), ("id", "RosterBase"), ("id", "i")),
            ("callmethod", ("id", "PlaceAtMe"), ("id", "player"), ("id", "n"), ("id", "base"), ("int", 1), ("bool", False),
             ("bool", False)),
            ("cast", ("id", "::temp0"), ("id", "n")),
            ("jmpf", ("id", "::temp0"), ("lbl", "failed")),
            ("array_getelement", ("id", "x"), ("id", "RosterX"), ("id", "i")),
            ("array_getelement", ("id", "y"), ("id", "RosterY"), ("id", "i")),
            ("array_getelement", ("id", "z"), ("id", "RosterZ"), ("id", "i")),
            # the spot they were first seen at, in world coordinates (MoveTo with the player as the target put them on the player)
            ("callmethod", ("id", "SetPosition"), ("id", "n"), NONE, ("id", "x"), ("id", "y"), ("id", "z")),
            ("array_setelement", ("id", "RosterRef"), ("id", "i"), ("id", "n")),
            ("return", ("bool", True)),
            ("label", "failed"),
            ("return", ("bool", False)),
        ],
    )
    respawn_one = Function(
        "RespawnOne",
        return_type="Bool",
        params=[("i", "Int"), ("player", "Actor")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("old", "ObjectReference"), ("a", "Actor"), ("made", "Bool")],
        code=[
            ("array_getelement", ("id", "old"), ("id", "RosterRef"), ("id", "i")),
            ("cast", ("id", "a"), ("id", "old")),
            ("cast", ("id", "::temp0"), ("id", "a")),
            ("jmpf", ("id", "::temp0"), ("lbl", "go")),
            ("callmethod", ("id", "IsDead"), ("id", "a"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "living")),
            ("label", "go"),
            ("callmethod", ("id", "Remove"), SELF, NONE, ("id", "old")),
            ("callmethod", ("id", "Spawn"), SELF, ("id", "made"), ("id", "i"), ("id", "player")),
            ("return", ("id", "made")),
            ("label", "living"),
            ("return", ("bool", False)),
        ],
    )
    respawn = Function(
        "Respawn",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("::temp1", "Bool"), ("player", "Actor"), ("cell", "Cell"),
                ("i", "Int"), ("n", "Int"), ("back", "Int"), ("known", "Int"), ("base", "Form"), ("m", "ObjectReference"),
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
            ("array_getelement", ("id", "base"), ("id", "RosterBase"), ("id", "i")),
            ("cast", ("id", "::temp0"), ("id", "base")),
            ("jmpf", ("id", "::temp0"), ("lbl", "next")),
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
    find_lost = Function(
        "FindLost",
        return_type="Bool",
        params=[("r", "Actor"), ("base", "Form")],
        locals=[("::temp0", "Bool"), ("i", "Int"), ("b", "Form"), ("ref", "ObjectReference"), ("rr", "ObjectReference"), ("x", "Float"), ("y", "Float"),
                ("dx", "Float"), ("dy", "Float")],
        code=[
            # a roster entry whose reference was lost (the game forgets some after a cell reloads) is claimed by the
            # same kind of person standing near the same spot
            ("assign", ("id", "i"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("int", 128)),
            ("jmpf", ("id", "::temp0"), ("lbl", "none")),
            ("array_getelement", ("id", "b"), ("id", "RosterBase"), ("id", "i")),
            ("cmp_eq", ("id", "::temp0"), ("id", "b"), ("id", "base")),
            ("jmpf", ("id", "::temp0"), ("lbl", "next")),
            ("array_getelement", ("id", "ref"), ("id", "RosterRef"), ("id", "i")),
            ("cast", ("id", "::temp0"), ("id", "ref")),
            ("jmpf", ("id", "::temp0"), ("lbl", "lost")),
            ("jmp", ("lbl", "next")),
            ("label", "lost"),
            ("callmethod", ("id", "GetPositionX"), ("id", "r"), ("id", "dx")),
            ("callmethod", ("id", "GetPositionY"), ("id", "r"), ("id", "dy")),
            ("array_getelement", ("id", "x"), ("id", "RosterX"), ("id", "i")),
            ("array_getelement", ("id", "y"), ("id", "RosterY"), ("id", "i")),
            ("fsub", ("id", "dx"), ("id", "dx"), ("id", "x")),
            ("fsub", ("id", "dy"), ("id", "dy"), ("id", "y")),
            ("fmul", ("id", "dx"), ("id", "dx"), ("id", "dx")),
            ("fmul", ("id", "dy"), ("id", "dy"), ("id", "dy")),
            ("fadd", ("id", "dx"), ("id", "dx"), ("id", "dy")),
            ("cmp_lt", ("id", "::temp0"), ("id", "dx"), ("float", 360000.0)),
            ("jmpf", ("id", "::temp0"), ("lbl", "next")),
            ("cast", ("id", "rr"), ("id", "r")),
            ("array_setelement", ("id", "RosterRef"), ("id", "i"), ("id", "rr")),
            ("return", ("bool", True)),
            ("label", "next"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "none"),
            ("return", ("bool", False)),
        ],
    )
    enlist = Function(
        "Remember",
        return_type="Bool",
        params=[("r", "Actor")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("i", "Int"), ("e", "ObjectReference"), ("rr", "ObjectReference"), ("x", "Float"),
                ("y", "Float"), ("z", "Float"), ("base", "Form"), ("cell", "Cell"), ("name", "String"), ("msg", "String")],
        code=[
            ("assign", ("id", "LogStep"), ("int", 1)),
            call("MakeArrays"),
            ("assign", ("id", "LogStep"), ("int", 2)),
            ("cast", ("id", "rr"), ("id", "r")),
            ("assign", ("id", "i"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("int", 128)),
            ("jmpf", ("id", "::temp0"), ("lbl", "claim")),
            ("array_getelement", ("id", "e"), ("id", "RosterRef"), ("id", "i")),
            ("cast", ("id", "::temp0"), ("id", "e")),  # an empty slot is not a duplicate
            ("jmpf", ("id", "::temp0"), ("lbl", "cont")),
            ("cmp_eq", ("id", "::temp0"), ("id", "e"), ("id", "rr")),
            ("jmpf", ("id", "::temp0"), ("lbl", "cont")),
            ("iadd", ("id", "LogDup"), ("id", "LogDup"), ("int", 1)),
            ("return", ("bool", False)),
            ("label", "cont"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "claim"),
            ("assign", ("id", "LogStep"), ("int", 3)),
            ("callmethod", ("id", "GetBaseObject"), ("id", "r"), ("id", "base")),
            ("callmethod", ("id", "FindLost"), SELF, ("id", "::temp0"), ("id", "r"), ("id", "base")),
            ("jmpf", ("id", "::temp0"), ("lbl", "add")),
            ("iadd", ("id", "LogMerged"), ("id", "LogMerged"), ("int", 1)),
            ("return", ("bool", False)),
            ("label", "add"),
            ("assign", ("id", "LogStep"), ("int", 4)),
            ("iadd", ("id", "LogAdded"), ("id", "LogAdded"), ("int", 1)),
            ("callmethod", ("id", "GetPositionX"), ("id", "r"), ("id", "x")),
            ("callmethod", ("id", "GetPositionY"), ("id", "r"), ("id", "y")),
            ("callmethod", ("id", "GetPositionZ"), ("id", "r"), ("id", "z")),
            ("callmethod", ("id", "GetParentCell"), ("id", "r"), ("id", "cell")),
            ("array_setelement", ("id", "RosterRef"), ("id", "RosterNext"), ("id", "rr")),
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
            ("return", ("bool", True)),
        ],
    )
    known_count = Function(
        "KnownCount",
        return_type="Int",
        locals=[("::temp0", "Bool"), ("i", "Int"), ("n", "Int"), ("base", "Form")],
        code=[
            ("assign", ("id", "i"), ("int", 0)),
            ("assign", ("id", "n"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("int", 128)),
            ("jmpf", ("id", "::temp0"), ("lbl", "done")),
            ("array_getelement", ("id", "base"), ("id", "RosterBase"), ("id", "i")),
            ("cast", ("id", "::temp0"), ("id", "base")),
            ("jmpf", ("id", "::temp0"), ("lbl", "next")),
            ("iadd", ("id", "n"), ("id", "n"), ("int", 1)),
            ("label", "next"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "done"),
            ("return", ("id", "n")),
        ],
    )
    stage = Function(
        "Stage",
        return_type="Int",
        params=[("a", "Actor")],
        locals=[("::temp0", "Bool"), ("player", "Actor")],
        code=[
            # 0 not a person (or the player), 1 dead, 2 not a humanoid, 3 not hostile to the player, 4 a living hostile humanoid
            ("cast", ("id", "::temp0"), ("id", "a")),
            ("jmpf", ("id", "::temp0"), ("lbl", "zero")),
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("cmp_eq", ("id", "::temp0"), ("id", "a"), ("id", "player")),
            ("jmpf", ("id", "::temp0"), ("lbl", "other")),
            ("return", ("int", 0)),
            ("label", "other"),
            ("callmethod", ("id", "IsDead"), ("id", "a"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "living")),
            ("return", ("int", 1)),
            ("label", "living"),
            ("callmethod", ("id", "HasKeyword"), ("id", "a"), ("id", "::temp0"), ("id", "::NpcKeyword_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "notnpc")),
            ("callmethod", ("id", "IsHostileToActor"), ("id", "a"), ("id", "::temp0"), ("id", "player")),
            ("jmpf", ("id", "::temp0"), ("lbl", "calm")),
            ("return", ("int", 4)),
            ("label", "notnpc"),
            ("return", ("int", 2)),
            ("label", "calm"),
            ("return", ("int", 3)),
            ("label", "zero"),
            ("return", ("int", 0)),
        ],
    )
    adopt = Function(
        "Adopt",
        return_type="Bool",
        params=[("a", "Actor")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("fresh", "Bool"), ("v", "Float"), ("st", "Int")],
        code=[
            ("callmethod", ("id", "Stage"), SELF, ("id", "st"), ("id", "a")),
            ("cmp_lt", ("id", "::temp0"), ("id", "st"), ("int", 3)),
            ("jmpf", ("id", "::temp0"), ("lbl", "humanoid")),
            ("return", ("bool", False)),
            ("label", "humanoid"),
            ("iadd", ("id", "LogHuman"), ("id", "LogHuman"), ("int", 1)),
            ("cmp_lt", ("id", "::temp0"), ("id", "st"), ("int", 4)),
            ("jmpf", ("id", "::temp0"), ("lbl", "foe")),
            ("return", ("bool", False)),
            ("label", "foe"),
            ("iadd", ("id", "LogFoes"), ("id", "LogFoes"), ("int", 1)),
            ("assign", ("id", "LogStep"), ("int", 10)),  # reached the call
            ("callmethod", ("id", "Remember"), SELF, ("id", "fresh"), ("id", "a")),
            # people who never loaded with the ability (an old save) get it now; the script itself sets this flag when it starts
            ("callmethod", ("id", "GetActorValue"), ("id", "a"), ("id", "v"), ("str", "Variable09")),
            ("cmp_lt", ("id", "::temp0"), ("id", "v"), ("float", 1.0)),
            ("jmpf", ("id", "::temp0"), ("lbl", "done")),
            ("callmethod", ("id", "AddSpell"), ("id", "a"), NONE, ("id", "::Ability_var"), ("bool", False)),
            ("label", "done"),
            ("return", ("id", "fresh")),
        ],
    )
    log_around = Function(
        "LogAround",
        return_type="Int",
        params=[("tries", "Int"), ("say", "Bool")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("player", "Actor"), ("a", "Actor"), ("r", "ObjectReference"),
                ("i", "Int"), ("count", "Int"), ("known", "Int"), ("seen_a", "Int"), ("seen_b", "Int"), ("x", "Float"),
                ("y", "Float"), ("z", "Float"), ("msg", "String"), ("sa", "String"), ("sb", "String"), ("sh", "String"),
                ("sf", "String"), ("sn", "String"), ("sk", "String"), ("sd", "String"), ("sm", "String"), ("su", "String"), ("ss", "String")],
        code=[
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            ("callmethod", ("id", "GetPositionX"), ("id", "player"), ("id", "x")),
            ("callmethod", ("id", "GetPositionY"), ("id", "player"), ("id", "y")),
            ("callmethod", ("id", "GetPositionZ"), ("id", "player"), ("id", "z")),
            ("assign", ("id", "i"), ("int", 0)),
            ("assign", ("id", "count"), ("int", 0)),
            ("assign", ("id", "seen_a"), ("int", 0)),
            ("jmpf", ("id", "say"), ("lbl", "loop")),  # only a counted search resets the counts (the quiet one runs every 2 s)
            ("assign", ("id", "LogHuman"), ("int", 0)),
            ("assign", ("id", "LogFoes"), ("int", 0)),
            ("assign", ("id", "LogDup"), ("int", 0)),
            ("assign", ("id", "LogMerged"), ("int", 0)),
            ("assign", ("id", "LogAdded"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", ("id", "::temp0"), ("id", "i"), ("id", "tries")),
            ("jmpf", ("id", "::temp0"), ("lbl", "done")),
            ("callstatic", ("id", "Game"), ("id", "FindRandomActor"), ("id", "a"), ("id", "x"), ("id", "y"), ("id", "z"),
             ("id", "::LogRadius_var")),
            ("cast", ("id", "::temp0"), ("id", "a")),
            ("jmpf", ("id", "::temp0"), ("lbl", "next")),
            ("iadd", ("id", "seen_a"), ("id", "seen_a"), ("int", 1)),
            ("callmethod", ("id", "Adopt"), SELF, ("id", "::temp0"), ("id", "a")),
            ("jmpf", ("id", "::temp0"), ("lbl", "next")),
            ("iadd", ("id", "count"), ("id", "count"), ("int", 1)),
            ("label", "next"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "done"),
            ("jmpf", ("id", "say"), ("lbl", "end")),
            ("callmethod", ("id", "KnownCount"), SELF, ("id", "known")),
            ("cast", ("id", "sa"), ("id", "seen_a")),
            ("cast", ("id", "sh"), ("id", "LogHuman")),
            ("cast", ("id", "sf"), ("id", "LogFoes")),
            ("cast", ("id", "sn"), ("id", "count")),
            ("cast", ("id", "sk"), ("id", "known")),
            ("cast", ("id", "sd"), ("id", "LogDup")),
            ("cast", ("id", "sm"), ("id", "LogMerged")),
            ("cast", ("id", "su"), ("id", "LogAdded")),
            ("cast", ("id", "ss"), ("id", "LogStep")),
            *notify(("str", "Pandora log: saw "), ("id", "sa"), ("str", " people; humanoid "), ("id", "sh"), ("str", ", hostile "), ("id", "sf"), ("str", ", new "),
                    ("id", "sn"), ("str", " ("), ("id", "sk"), ("str", " known; dup "), ("id", "sd"), ("str", ", merged "),
                    ("id", "sm"), ("str", ", added "), ("id", "su"), ("str", "; step "), ("id", "ss"), ("str", ")")),
            ("label", "end"),
            ("return", ("id", "count")),
        ],
    )
    log_now = Function(
        "LogNow",
        locals=[("::nonevar", "None"), ("n", "Int")],
        code=[("callmethod", ("id", "LogAround"), SELF, ("id", "n"), ("int", 80), ("bool", True)), ("return", None)],
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
        locals=[("::temp0", "Bool")],
        code=[
            # a gun lying in the world has its 3D loaded; one in a pack or a container does not (ObjectReference has no
            # GetContainer in Skyrim: the log showed "Method GetContainer not found" every second)
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
        name="SkylandsHunterQuest",
        parent="Quest",
        variables=[("Chosen", "Bool", ("bool", False)), ("PendingPrompt", "Bool", ("bool", False)),
                   ("JustLoaded", "Bool", ("bool", False)), ("Refreshed", "Bool", ("bool", False)), ("Mode", "Int", ("int", 0)),
                   ("Generation", "Int", ("int", 0)), ("TrackedNext", "Int", ("int", 0)), ("RosterNext", "Int", ("int", 0)),
                   ("Noted", "Int", ("int", 0)), ("LogHuman", "Int", ("int", 0)), ("LogFoes", "Int", ("int", 0)),
                   ("LogDup", "Int", ("int", 0)), ("LogStep", "Int", ("int", 0)), ("LogMerged", "Int", ("int", 0)), ("LogAdded", "Int", ("int", 0)),
                   ("EntryNext", "Int", ("int", 0)), ("LastCell", "Cell", None),
                   ("Tracked", "ObjectReference[]", None), ("TrackedBeams", "ObjectReference[]", None),
                   ("TrackedLights", "ObjectReference[]", None), ("RosterRef", "ObjectReference[]", None),
                   ("RosterBase", "Form[]", None), ("RosterX", "Float[]", None), ("RosterY", "Float[]", None),
                   ("RosterZ", "Float[]", None), ("RosterCell", "Cell[]", None), ("EntryCells", "Cell[]", None),
                   ("EntryMarks", "ObjectReference[]", None),
                   # handed over by the player's ability script at every start (see Refresh)
                   ("::RarityKeywords_var", "Keyword[]", None), ("::Beams_var", "Form[]", None),
                   ("::Lights_var", "Light[]", None), ("::PromptMsg_var", "Message", None),
                   ("::SettingsMsg_var", "Message", None), ("::MarkerForm_var", "Form", None),
                   ("::RespawnPower_var", "Spell", None), ("::LogPower_var", "Spell", None),
                   ("::Ability_var", "Spell", None), ("::NpcKeyword_var", "Keyword", None),
                   ("::LogRadius_var", "Float", ("float", 5000.0)), ("::Verbose_var", "Bool", ("bool", True))],
        auto_properties=[("ClassChoice", "Message"), ("Shouts", "Shout[]"), ("Words", "WordOfPower[]"),
                         ("StarterGun", "Form"), ("StarterAmmo", "Form"), ("AbilityInit", "Spell")],
        functions=[on_init, on_update, bootstrap, choose, make_arrays, refresh, upgrade, loaded, prompt, settings, generation, in_range, remove, spawn, respawn_one, respawn, find_lost, enlist, known_count, stage, adopt, log_around, log_now,
                   entry_index, entrance_for, note_entrance, arrive, consider, place, report, clear, alive, follow, sweep],
    )


def watcher() -> Script:
    """SkylandsHunter extends ActiveMagicEffect: the effect of an ability every humanoid race (and so
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
            call("Wake"),
            ("callmethod", ("id", "Refresh"), ("id", "::Owner_var"), NONE, ("id", "::RarityKeywords_var"), ("id", "::Beams_var"),
             ("id", "::Lights_var"), ("id", "::PromptMsg_var"), ("id", "::SettingsMsg_var"), ("id", "::MarkerForm_var"),
             ("id", "::RespawnPower_var"), ("id", "::LogPower_var"), ("id", "::Ability_var"), ("id", "::NpcKeyword_var"),
             ("id", "::ScanRadius_var"), ("id", "::Verbose_var")),
            ("callmethod", ("id", "Upgrade"), ("id", "::Owner_var"), NONE),
            ("callmethod", ("id", "GetEquippedWeapon"), ("id", "Me"), ("id", "w"), ("bool", False)),
            call("ApplySpeed", ("id", "w")),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 0.5)),
            ("return", None),
            ("label", "other"),
            ("callmethod", ("id", "SetActorValue"), ("id", "Me"), NONE, ("str", "Variable09"), ("float", 1.0)),  # "I have a watcher"
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
            ("callstatic", ("id", "Utility"), ("id", "RandomFloat"), ("id", "delay"), ("float", 10.0), ("float", 16.0)),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("id", "delay")),
            ("return", None),
        ],
    )
    wake = Function(
        "Wake",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("::temp1", "Bool"), ("msg", "String")],
        code=[
            # a quest added to an old save may not have started
            ("callmethod", ("id", "IsRunning"), ("id", "::Owner_var"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "start")),
            ("return", None),
            ("label", "start"),
            ("callmethod", ("id", "Start"), ("id", "::Owner_var"), ("id", "::temp1")),
            *notify(("str", "Skylands: the quest was stopped; started it")),
            ("return", None),
        ],
    )
    give = Function(
        "Give",
        params=[("sp", "Spell"), ("title", "String")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("msg", "String"), ("f", "Form")],
        code=[
            # the player's copy of this script has this build's own forms, so the powers are granted from here
            # (HasSpell takes a Form: the Spell passed as it is fails with "Type mismatch for argument 1")
            ("cast", ("id", "f"), ("id", "sp")),
            ("callmethod", ("id", "HasSpell"), ("id", "Me"), ("id", "::temp0"), ("id", "f")),
            ("jmpf", ("id", "::temp0"), ("lbl", "add")),
            ("return", None),
            ("label", "add"),
            ("callmethod", ("id", "AddSpell"), ("id", "Me"), NONE, ("id", "sp"), ("bool", False)),
            ("callmethod", ("id", "HasSpell"), ("id", "Me"), ("id", "::temp0"), ("id", "f")),
            ("jmpf", ("id", "::temp0"), ("lbl", "failed")),
            *notify(("str", "Skylands: you learned "), ("id", "title")),
            ("return", None),
            ("label", "failed"),
            ("return", None),
        ],
    )
    diag = Function(
        "Diag",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("n1", "Int"), ("n2", "Int"), ("n3", "Int"), ("s1", "String"),
                ("s2", "String"), ("s3", "String"), ("a", "String"), ("b", "String"), ("msg", "String")],
        code=[
            # once per load: what this copy of the script was given, for when the powers do not show up
            ("jmpf", ("id", "Told"), ("lbl", "tell")),
            ("return", None),
            ("label", "tell"),
            ("assign", ("id", "Told"), ("bool", True)),
            ("array_length", ("id", "n1"), ("id", "::RarityKeywords_var")),
            ("array_length", ("id", "n2"), ("id", "::Beams_var")),
            ("array_length", ("id", "n3"), ("id", "::SpeedKeywords_var")),
            ("cast", ("id", "s1"), ("id", "n1")),
            ("cast", ("id", "s2"), ("id", "n2")),
            ("cast", ("id", "s3"), ("id", "n3")),
            ("callmethod", ("id", "GetName"), ("id", "::RespawnPower_var"), ("id", "a")),
            ("callmethod", ("id", "GetName"), ("id", "::LogPower_var"), ("id", "b")),
            *notify(("str", "Skylands props: rarity "), ("id", "s1"), ("str", ", beams "), ("id", "s2"), ("str", ", speeds "),
                    ("id", "s3"), ("str", ", powers '"), ("id", "a"), ("str", "' '"), ("id", "b"), ("str", "'")),
            ("return", None),
        ],
    )
    hand = Function(
        "Hand",
        locals=[("::nonevar", "None")],
        code=[
            ("callmethod", ("id", "Refresh"), ("id", "::Owner_var"), NONE, ("id", "::RarityKeywords_var"), ("id", "::Beams_var"),
             ("id", "::Lights_var"), ("id", "::PromptMsg_var"), ("id", "::SettingsMsg_var"), ("id", "::MarkerForm_var"),
             ("id", "::RespawnPower_var"), ("id", "::LogPower_var"), ("id", "::Ability_var"), ("id", "::NpcKeyword_var"),
             ("id", "::ScanRadius_var"), ("id", "::Verbose_var")),
            ("callmethod", ("id", "Upgrade"), ("id", "::Owner_var"), NONE),
            call("Diag"),
            call("Give", ("id", "::RespawnPower_var"), ("str", "Pandora Respawn")),
            call("Give", ("id", "::LogPower_var"), ("str", "Pandora Log Enemies")),
            ("return", None),
        ],
    )
    rare = Function(
        "Rare",
        locals=[("::nonevar", "None"), ("::temp0", "Int"), ("::temp1", "Bool"), ("n", "Int")],
        code=[
            # the costlier chores: handing the quest its forms every 20 s, a quiet search for people every 4 s
            ("imod", ("id", "::temp0"), ("id", "Ticks"), ("int", 40)),
            ("cmp_eq", ("id", "::temp1"), ("id", "::temp0"), ("int", 4)),
            ("jmpf", ("id", "::temp1"), ("lbl", "search")),
            call("Hand"),
            ("label", "search"),
            ("imod", ("id", "::temp0"), ("id", "Ticks"), ("int", 8)),
            ("cmp_eq", ("id", "::temp1"), ("id", "::temp0"), ("int", 0)),
            ("jmpf", ("id", "::temp1"), ("lbl", "end")),
            ("callmethod", ("id", "LogAround"), ("id", "::Owner_var"), ("id", "n"), ("int", 4), ("bool", False)),
            ("label", "end"),
            ("return", None),
        ],
    )
    player_tick = Function(
        "PlayerTick",
        locals=[("::nonevar", "None"), ("::temp0", "Int"), ("::temp1", "Bool")],
        code=[
            ("callmethod", ("id", "NoteEntrance"), ("id", "::Owner_var"), NONE),
            ("iadd", ("id", "Ticks"), ("id", "Ticks"), ("int", 1)),
            ("imod", ("id", "::temp0"), ("id", "Ticks"), ("int", 2)),
            ("cmp_eq", ("id", "::temp1"), ("id", "::temp0"), ("int", 0)),
            ("jmpf", ("id", "::temp1"), ("lbl", "end")),
            call("Scan"),
            ("callmethod", ("id", "Sweep"), ("id", "::Owner_var"), NONE),
            call("Rare"),
            ("label", "end"),
            ("return", None),
        ],
    )
    on_load = Function(
        "OnPlayerLoadGame",
        locals=[("::nonevar", "None")],
        code=[
            ("jmpf", ("id", "IsPlayer"), ("lbl", "end")),
            call("Hand"),
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
            ("callmethod", ("id", "Remember"), ("id", "::Owner_var"), NONE, ("id", "Me")),
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
            ("cmp_lt", ("id", "::temp0"), ("id", "tries"), ("int", 8)),
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
    held_in = Function(
        "HeldIn",
        return_type="Weapon",
        params=[("left", "Bool")],
        locals=[("::temp0", "Bool"), ("w", "Weapon"), ("out", "Weapon")],
        code=[
            # the Skylands gun in one hand
            ("callmethod", ("id", "GetEquippedWeapon"), ("id", "Me"), ("id", "w"), ("id", "left")),
            ("cast", ("id", "::temp0"), ("id", "w")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("callmethod", ("id", "HasKeyword"), ("id", "w"), ("id", "::temp0"), ("id", "::GunKeyword_var")),
            ("jmpf", ("id", "::temp0"), ("lbl", "end")),
            ("assign", ("id", "out"), ("id", "w")),
            ("label", "end"),
            ("return", ("id", "out")),
        ],
    )
    gun_held = Function(
        "GunHeld",
        return_type="Weapon",
        locals=[("::temp0", "Bool"), ("w", "Weapon")],
        code=[
            # the Skylands gun in the right hand, else in the left (a staff gun can end up in either)
            ("callmethod", ("id", "HeldIn"), SELF, ("id", "w"), ("bool", False)),
            ("cast", ("id", "::temp0"), ("id", "w")),
            ("not", ("id", "::temp0"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "done")),
            ("callmethod", ("id", "HeldIn"), SELF, ("id", "w"), ("bool", True)),
            ("label", "done"),
            ("return", ("id", "w")),
        ],
    )
    carrying = Function(
        "Carrying",
        return_type="Bool",
        locals=[("::temp0", "Bool"), ("w", "Weapon")],
        code=[
            ("callmethod", ("id", "GunHeld"), SELF, ("id", "w")),
            ("cast", ("id", "::temp0"), ("id", "w")),
            ("return", ("id", "::temp0")),
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
            ("callmethod", ("id", "GunHeld"), SELF, ("id", "w")),
            ("cast", ("id", "::temp0"), ("id", "w")),
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
        name="SkylandsHunter",
        parent="ActiveMagicEffect",
        variables=[("Me", "Actor", None), ("IsPlayer", "Bool", ("bool", False)), ("Armed", "Bool", ("bool", False)),
                   ("Foe", "Bool", ("bool", False)), ("Checked", "Bool", ("bool", False)), ("MyGen", "Int", ("int", 0)),
                   ("Ticks", "Int", ("int", 0)), ("Speed", "Float", ("float", 0.0)),
                   ("Told", "Bool", ("bool", False))],
        auto_properties=[("Owner", "SkylandsHunterQuest"), ("GunKeyword", "Keyword"), ("SpeedKeywords", "Keyword[]"),
                         ("GunList", "FormList"), ("GunDrop", "Form"), ("GunDropGood", "Form"), ("NpcKeyword", "Keyword"),
                         ("Bolts", "Form"), ("ArmChance", "Int"), ("DropChance", "Int"), ("GoodLevel", "Int"),
                         ("ScanRadius", "Float"), ("Verbose", "Bool"), ("RarityKeywords", "Keyword[]"), ("Beams", "Form[]"),
                         ("Lights", "Light[]"), ("PromptMsg", "Message"), ("SettingsMsg", "Message"), ("MarkerForm", "Form"),
                         ("RespawnPower", "Spell"), ("LogPower", "Spell"), ("Ability", "Spell")],
        functions=[on_start, on_update, wake, give, diag, hand, rare, player_tick, on_load, maintain, on_equipped, on_unequipped, on_death, apply_speed, speed_of, scan, eligible,
                   worthy, roll, list_for, held_in, gun_held, carrying, try_arm, equip, own_drop, bonus_drop, announce, cleanup],
    )


def respawn_power() -> Script:
    """SkylandsHunterPower extends ActiveMagicEffect: the effect of the lesser powers "Pandora Respawn" (Action 0:
    open the respawn settings) and "Pandora Log Enemies" (Action 1: note the hostile people around right now).

      Event OnEffectStart(Actor akTarget, Actor akCaster)
        If Action == 1
          Owner.LogNow()
        Else
          Owner.Settings()
        EndIf
      EndEvent
    """
    on_start = Function(
        "OnEffectStart",
        params=[("akTarget", "Actor"), ("akCaster", "Actor")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            ("cmp_eq", ("id", "::temp0"), ("id", "::Action_var"), ("int", 1)),
            ("jmpf", ("id", "::temp0"), ("lbl", "settings")),
            ("callmethod", ("id", "LogNow"), ("id", "::Owner_var"), NONE),
            ("return", None),
            ("label", "settings"),
            ("callmethod", ("id", "Settings"), ("id", "::Owner_var"), NONE),
            ("return", None),
        ],
    )
    return Script(
        name="SkylandsHunterPower",
        parent="ActiveMagicEffect",
        auto_properties=[("Owner", "SkylandsHunterQuest"), ("Action", "Int")],
        functions=[on_start],
    )


def gunner() -> Script:
    """SkylandsGunner extends ActiveMagicEffect: Borderlands shooting for the player (in SkylandsGunModels.esp).

    The gun's kind (pistol, SMG, ...) and element come from keywords on the gun. On equipping a gun its Borderlands rounds are
    handed over and equipped (each kind x element has its own ammo, whose projectile flies at the Borderlands speed and, for
    rockets and elemental guns, explodes). After every shot of the crossbow the script adds what Borderlands does on top:
    a shotgun's extra pellets, an SMG's or assault rifle's automatic burst, all with the gun's spread (extra rounds are fired
    with Weapon.Fire from an invisible marker turned by a random angle); it counts the magazine and, when it is empty, takes
    the rounds away for the reload time and gives them back with a full magazine.

      Event OnEffectStart / OnPlayerLoadGame / OnObjectEquipped / OnPlayerBowShot
    """
    T0, T1 = ("id", "::temp0"), ("id", "::temp1")
    on_start = Function(
        "OnEffectStart",
        params=[("akTarget", "Actor"), ("akCaster", "Actor")],
        locals=[("::nonevar", "None")],
        code=[("assign", ("id", "Me"), ("id", "akTarget")), call("Ready"), ("return", None)],
    )
    on_load = Function("OnPlayerLoadGame", locals=[("::nonevar", "None")], code=[call("Ready"), ("return", None)])
    ready = Function(
        "Ready",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("::temp1", "Bool"), ("w", "Weapon"), ("msg", "String")],
        code=[
            ("cast", T0, ("id", "Aim")),
            ("not", T1, T0),
            ("jmpf", T1, ("lbl", "placed")),
            ("callmethod", ("id", "PlaceAtMe"), ("id", "Me"), ("id", "Aim"), ("id", "::Marker_var"), ("int", 1), ("bool", True),
             ("bool", False)),
            ("label", "placed"),
            ("callmethod", ("id", "GetEquippedWeapon"), ("id", "Me"), ("id", "w"), ("bool", False)),
            call("Setup", ("id", "w")),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 0.25)),
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "end")),
            *notify(("str", "Skylands gunner ready")),
            ("label", "end"),
            ("return", None),
        ],
    )
    on_equipped = Function(
        "OnObjectEquipped",
        params=[("akBaseObject", "Form"), ("akReference", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("w", "Weapon")],
        code=[
            ("cast", ("id", "w"), ("id", "akBaseObject")),
            ("cast", T0, ("id", "w")),
            ("jmpf", T0, ("lbl", "end")),
            call("Setup", ("id", "w")),
            ("label", "end"),
            ("return", None),
        ],
    )
    setup = Function(
        "Setup",
        params=[("w", "Weapon")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("::temp1", "Bool"), ("t", "Int"), ("k", "Keyword"),
                ("kind", "Int"), ("elem", "Int"), ("idx", "Int"), ("f", "Form"), ("have", "Int"), ("want", "Int"),
                ("n", "Int"), ("last", "Int"), ("tens", "Int"), ("units", "Int"), ("msg", "String"), ("a", "String"),
                ("b", "String"), ("c", "String")],
        code=[
            ("assign", ("id", "Kind"), ("int", -1)),
            ("cast", T0, ("id", "w")),
            *ret_unless(T0, "hasw", tmp=T1),
            ("assign", ("id", "Gun"), ("id", "w")),
            # the gun's kind: KindKeywords[t] (a found keyword ends the loop by moving t to the last step)
            ("assign", ("id", "kind"), ("int", -1)),
            ("assign", ("id", "t"), ("int", 0)),
            ("label", "kloop"),
            ("cmp_lt", T0, ("id", "t"), ("int", 6)),
            ("jmpf", T0, ("lbl", "kdone")),
            ("array_getelement", ("id", "k"), ("id", "::KindKeywords_var"), ("id", "t")),
            ("cast", T0, ("id", "k")),
            ("jmpf", T0, ("lbl", "kand")),
            ("callmethod", ("id", "HasKeyword"), ("id", "w"), T0, ("id", "k")),
            ("label", "kand"),
            ("jmpf", T0, ("lbl", "knext")),
            ("assign", ("id", "kind"), ("id", "t")),
            ("assign", ("id", "t"), ("int", 5)),
            ("label", "knext"),
            ("iadd", ("id", "t"), ("id", "t"), ("int", 1)),
            ("jmp", ("lbl", "kloop")),
            ("label", "kdone"),
            ("cmp_lt", T0, ("id", "kind"), ("int", 0)),
            *ret_if(T0, "known"),
            # its element: ElementKeywords[t] -> t + 1 (0 = none)
            ("assign", ("id", "elem"), ("int", 0)),
            ("assign", ("id", "t"), ("int", 0)),
            ("label", "eloop"),
            ("cmp_lt", T0, ("id", "t"), ("int", 4)),
            ("jmpf", T0, ("lbl", "edone")),
            ("array_getelement", ("id", "k"), ("id", "::ElementKeywords_var"), ("id", "t")),
            ("cast", T0, ("id", "k")),
            ("jmpf", T0, ("lbl", "eand")),
            ("callmethod", ("id", "HasKeyword"), ("id", "w"), T0, ("id", "k")),
            ("label", "eand"),
            ("jmpf", T0, ("lbl", "enext")),
            ("iadd", ("id", "elem"), ("id", "t"), ("int", 1)),
            ("assign", ("id", "t"), ("int", 3)),
            ("label", "enext"),
            ("iadd", ("id", "t"), ("id", "t"), ("int", 1)),
            ("jmp", ("lbl", "eloop")),
            ("label", "edone"),
            ("imul", ("id", "idx"), ("id", "kind"), ("int", 5)),
            ("iadd", ("id", "idx"), ("id", "idx"), ("id", "elem")),
            ("array_getelement", ("id", "f"), ("id", "::Rounds_var"), ("id", "idx")),
            ("cast", ("id", "Rnd"), ("id", "f")),
            ("cast", ("id", "RndF"), ("id", "Rnd")),
            ("cast", T0, ("id", "Rnd")),
            *ret_unless(T0, "hasr", tmp=T1),
            ("assign", ("id", "Kind"), ("id", "kind")),
            ("assign", ("id", "Elem"), ("id", "elem")),
            # the gun's profile (type x manufacturer: its own fire rate, spread, reload, pellets, burst)
            ("assign", ("id", "Prof"), ("id", "kind")),
            ("array_length", ("id", "n"), ("id", "::ProfileKeywords_var")),
            ("isub", ("id", "last"), ("id", "n"), ("int", 1)),
            ("assign", ("id", "t"), ("int", 0)),
            ("label", "ploop"),
            ("cmp_lt", T0, ("id", "t"), ("id", "n")),
            ("jmpf", T0, ("lbl", "pdone")),
            ("array_getelement", ("id", "k"), ("id", "::ProfileKeywords_var"), ("id", "t")),
            ("cast", T0, ("id", "k")),
            ("jmpf", T0, ("lbl", "pand")),
            ("callmethod", ("id", "HasKeyword"), ("id", "w"), T0, ("id", "k")),
            ("label", "pand"),
            ("jmpf", T0, ("lbl", "pnext")),
            ("assign", ("id", "Prof"), ("id", "t")),
            ("assign", ("id", "t"), ("id", "last")),
            ("label", "pnext"),
            ("iadd", ("id", "t"), ("id", "t"), ("int", 1)),
            ("jmp", ("lbl", "ploop")),
            ("label", "pdone"),
            # its own magazine size: tens and units keywords (from Borderlands' ClipSize and the parts' clip bonus)
            ("assign", ("id", "tens"), ("int", -1)),
            ("assign", ("id", "units"), ("int", -1)),
            ("assign", ("id", "last"), ("int", 9)),
            ("assign", ("id", "t"), ("int", 0)),
            ("label", "cloop"),
            ("cmp_lt", T0, ("id", "t"), ("int", 10)),
            ("jmpf", T0, ("lbl", "cdone")),
            ("array_getelement", ("id", "k"), ("id", "::ClipTens_var"), ("id", "t")),
            ("cast", T0, ("id", "k")),
            ("jmpf", T0, ("lbl", "cand")),
            ("callmethod", ("id", "HasKeyword"), ("id", "w"), T0, ("id", "k")),
            ("label", "cand"),
            ("jmpf", T0, ("lbl", "cnext")),
            ("assign", ("id", "tens"), ("id", "t")),
            ("assign", ("id", "t"), ("id", "last")),
            ("label", "cnext"),
            ("iadd", ("id", "t"), ("id", "t"), ("int", 1)),
            ("jmp", ("lbl", "cloop")),
            ("label", "cdone"),
            ("assign", ("id", "last"), ("int", 9)),
            ("assign", ("id", "t"), ("int", 0)),
            ("label", "uloop"),
            ("cmp_lt", T0, ("id", "t"), ("int", 10)),
            ("jmpf", T0, ("lbl", "udone")),
            ("array_getelement", ("id", "k"), ("id", "::ClipUnits_var"), ("id", "t")),
            ("cast", T0, ("id", "k")),
            ("jmpf", T0, ("lbl", "uand")),
            ("callmethod", ("id", "HasKeyword"), ("id", "w"), T0, ("id", "k")),
            ("label", "uand"),
            ("jmpf", T0, ("lbl", "unext")),
            ("assign", ("id", "units"), ("id", "t")),
            ("assign", ("id", "t"), ("id", "last")),
            ("label", "unext"),
            ("iadd", ("id", "t"), ("id", "t"), ("int", 1)),
            ("jmp", ("lbl", "uloop")),
            ("label", "udone"),
            ("array_getelement", ("id", "want"), ("id", "::Clip_var"), ("id", "Prof")),
            ("cmp_gte", T0, ("id", "units"), ("int", 0)),
            ("jmpf", T0, ("lbl", "noclip")),
            ("imul", ("id", "want"), ("id", "tens"), ("int", 10)),
            ("iadd", ("id", "want"), ("id", "want"), ("id", "units")),
            ("label", "noclip"),
            ("cmp_lt", T0, ("id", "want"), ("int", 1)),
            ("jmpf", T0, ("lbl", "clipok")),
            ("assign", ("id", "want"), ("int", 1)),
            ("label", "clipok"),
            ("assign", ("id", "MagSize"), ("id", "want")),
            ("assign", ("id", "Mag"), ("id", "want")),
            ("assign", ("id", "Fallback"), ("bool", False)),
            ("label", "labbed"),
            ("callmethod", ("id", "GetItemCount"), ("id", "Me"), ("id", "have"), ("id", "RndF")),
            ("cmp_lt", T0, ("id", "have"), ("int", 100)),
            ("jmpf", T0, ("lbl", "stocked")),
            ("callmethod", ("id", "AddItem"), ("id", "Me"), NONE, ("id", "RndF"), ("int", 200), ("bool", True)),
            ("callmethod", ("id", "GetItemCount"), ("id", "Me"), ("id", "have"), ("id", "RndF")),
            ("cmp_lt", T0, ("id", "have"), ("int", 100)),
            ("jmpf", T0, ("lbl", "stocked")),
            ("callmethod", ("id", "AddItem"), ("id", "Me"), NONE, ("id", "RndF"), ("int", 200), ("bool", True)),
            ("label", "stocked"),
            # if the game will not hold the rounds, shoot steel bolts: magazines, reloads, pellets and bursts still work
            ("callmethod", ("id", "GetItemCount"), ("id", "Me"), ("id", "have"), ("id", "RndF")),
            ("cmp_lt", T0, ("id", "have"), ("int", 1)),
            ("jmpf", T0, ("lbl", "rounds")),
            ("assign", ("id", "Fallback"), ("bool", True)),
            ("assign", ("id", "Rnd"), ("id", "::Bolts_var")),
            ("cast", ("id", "RndF"), ("id", "Rnd")),
            ("callmethod", ("id", "GetItemCount"), ("id", "Me"), ("id", "have"), ("id", "RndF")),
            ("cmp_lt", T0, ("id", "have"), ("int", 100)),
            ("jmpf", T0, ("lbl", "rounds")),
            ("callmethod", ("id", "AddItem"), ("id", "Me"), NONE, ("id", "RndF"), ("int", 200), ("bool", False)),
            ("label", "rounds"),
            ("callmethod", ("id", "EquipItem"), ("id", "Me"), NONE, ("id", "RndF"), ("bool", False), ("bool", True)),
            ("callmethod", ("id", "GetItemCount"), ("id", "Me"), ("id", "Last"), ("id", "RndF")),
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "end")),
            ("cast", ("id", "a"), ("id", "want")),
            ("cast", ("id", "b"), ("id", "Last")),
            ("callmethod", ("id", "IsEquipped"), ("id", "Me"), T0, ("id", "RndF")),
            ("assign", ("id", "c"), ("str", "no")),
            ("jmpf", T0, ("lbl", "noeq")),
            ("assign", ("id", "c"), ("str", "yes")),
            ("label", "noeq"),
            ("jmpf", ("id", "Fallback"), ("lbl", "said")),
            ("strcat", ("id", "c"), ("id", "c"), ("str", " (the game would not hold the rounds: steel bolts)")),
            ("label", "said"),
            ("assign", ("id", "msg"), ("str", "")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", "Skylands gun: ")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "a")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", "-round magazine, rounds in pack: ")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "b")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", ", equipped: ")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "c")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", ". ")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "LabText")),
            ("not", T0, ("id", "Boxed")),
            ("jmpf", T0, ("lbl", "note")),
            ("assign", ("id", "Boxed"), ("bool", True)),
            ("callstatic", ("id", "Debug"), ("id", "MessageBox"), NONE, ("id", "msg")),
            ("return", None),
            ("label", "note"),
            ("callstatic", ("id", "Debug"), ("id", "Notification"), NONE, ("id", "msg")),
            ("label", "end"),
            ("return", None),
        ],
    )
    lab = Function(
        "Lab",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("i", "Int"), ("n", "Int"), ("f", "Form"), ("have", "Int"),
                ("a", "String"), ("msg", "String")],
        code=[
            # once: try to add each test item to the pack and say how many the game reports (0 = it would not hold it)
            ("assign", ("id", "Tested"), ("bool", True)),
            ("assign", ("id", "msg"), ("str", "Item test (rounds, old bolt copy, plain item, steel bolt): ")),
            ("array_length", ("id", "n"), ("id", "::LabItems_var")),
            ("assign", ("id", "i"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", T0, ("id", "i"), ("id", "n")),
            ("jmpf", T0, ("lbl", "done")),
            ("array_getelement", ("id", "f"), ("id", "::LabItems_var"), ("id", "i")),
            ("callmethod", ("id", "AddItem"), ("id", "Me"), NONE, ("id", "f"), ("int", 1), ("bool", True)),
            ("callmethod", ("id", "GetItemCount"), ("id", "Me"), ("id", "have"), ("id", "f")),
            ("cast", ("id", "a"), ("id", "have")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "a")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", " ")),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "done"),
            ("assign", ("id", "LabText"), ("id", "msg")),
            ("return", None),
        ],
    )
    speed = Function(
        "Speed",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("::temp1", "Bool"), ("want", "Float"), ("got", "Float"), ("d", "Float"),
                ("iv", "Float")],
        code=[
            # the crossbow's draw-and-reload is what limits the rate of fire: speed it up to the gun's Borderlands fire interval
            ("cmp_lt", T0, ("id", "Kind"), ("int", 0)),
            *ret_if(T0, "gun"),
            ("array_getelement", ("id", "iv"), ("id", "::Interval_var"), ("id", "Prof")),
            ("fdiv", ("id", "want"), ("float", 1.2), ("id", "iv")),
            ("cmp_lt", T0, ("id", "want"), ("float", 1.0)),
            ("jmpf", T0, ("lbl", "notslow")),
            ("assign", ("id", "want"), ("float", 1.0)),
            ("label", "notslow"),
            ("cmp_gt", T0, ("id", "want"), ("float", 5.0)),
            ("jmpf", T0, ("lbl", "notfast")),
            ("assign", ("id", "want"), ("float", 5.0)),
            ("label", "notfast"),
            ("callmethod", ("id", "GetActorValue"), ("id", "Me"), ("id", "got"), ("str", "WeaponSpeedMult")),
            ("fsub", ("id", "d"), ("id", "got"), ("id", "want")),
            ("cmp_gt", T0, ("id", "d"), ("float", 0.05)),
            ("jmpf", T0, ("lbl", "notabove")),
            ("callmethod", ("id", "SetActorValue"), ("id", "Me"), NONE, ("str", "WeaponSpeedMult"), ("id", "want")),
            ("return", None),
            ("label", "notabove"),
            ("cmp_lt", T0, ("id", "d"), ("float", -0.05)),
            ("jmpf", T0, ("lbl", "same")),
            ("callmethod", ("id", "SetActorValue"), ("id", "Me"), NONE, ("str", "WeaponSpeedMult"), ("id", "want")),
            ("label", "same"),
            ("return", None),
        ],
    )
    on_shot = Function(
        "OnPlayerBowShot",
        params=[("akWeapon", "Weapon"), ("akAmmo", "Ammo"), ("afPower", "Float"), ("abSunGazing", "Bool")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            ("assign", ("id", "Seen"), ("bool", True)),
            ("cmp_lt", T0, ("id", "Kind"), ("int", 0)),
            *ret_if(T0, "gun"),
            call("Shot"),
            ("return", None),
        ],
    )
    poll = Function(
        "Poll",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("n", "Int"), ("fired", "Int"), ("a", "String"), ("msg", "String")],
        code=[
            # Until the game's bow-shot event has been seen, a drop in the count of the gun's rounds is a shot.
            *ret_if(("id", "Seen"), "watch"),
            ("cmp_lt", T0, ("id", "Kind"), ("int", 0)),
            *ret_if(T0, "gun"),
            ("callmethod", ("id", "GetItemCount"), ("id", "Me"), ("id", "n"), ("id", "RndF")),
            ("isub", ("id", "fired"), ("id", "Last"), ("id", "n")),
            ("cmp_gt", T0, ("id", "fired"), ("int", 0)),
            ("jmpf", T0, ("lbl", "quiet")),
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "quiet")),
            ("cast", ("id", "a"), ("id", "n")),
            *notify(("str", "Rounds in pack: "), ("id", "a")),
            ("label", "quiet"),
            ("assign", ("id", "Last"), ("id", "n")),
            ("label", "loop"),
            ("cmp_gt", T0, ("id", "fired"), ("int", 0)),
            ("jmpf", T0, ("lbl", "done")),
            call("Shot"),
            ("isub", ("id", "fired"), ("id", "fired"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "done"),
            ("callmethod", ("id", "GetItemCount"), ("id", "Me"), ("id", "Last"), ("id", "RndF")),
            ("return", None),
        ],
    )
    on_update = Function(
        "OnUpdate",
        locals=[("::nonevar", "None")],
        code=[
            call("Poll"),
            call("Speed"),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 0.25)),
            ("return", None),
        ],
    )
    shot = Function(
        "Shot",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("n", "Int"), ("i", "Int"), ("s", "Float"), ("wait", "Float"),
                ("msg", "String")],
        code=[
            ("isub", ("id", "Mag"), ("id", "Mag"), ("int", 1)),
            ("iadd", ("id", "Shots"), ("id", "Shots"), ("int", 1)),
            ("cmp_eq", T0, ("id", "Shots"), ("int", 1)),
            ("jmpf", T0, ("lbl", "told")),
            ("jmpf", ("id", "::Verbose_var"), ("lbl", "told")),
            *notify(("str", "Skylands: shots are seen; Borderlands firing is on")),
            ("label", "told"),
            # a burst still running (another thread) only counts this shot
            ("jmpf", ("id", "Busy"), ("lbl", "free")),
            call("CheckMag"),
            ("return", None),
            ("label", "free"),
            ("assign", ("id", "Busy"), ("bool", True)),
            ("array_getelement", ("id", "s"), ("id", "::Spread_var"), ("id", "Prof")),
            call("Place"),
            # shotgun pellets: Pellets - 1 more rounds at once
            ("array_getelement", ("id", "n"), ("id", "::Pellets_var"), ("id", "Prof")),
            ("assign", ("id", "i"), ("int", 1)),
            ("label", "ploop"),
            ("cmp_lt", T0, ("id", "i"), ("id", "n")),
            ("jmpf", T0, ("lbl", "pdone")),
            call("FireExtra", ("id", "s")),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "ploop")),
            ("label", "pdone"),
            # automatic fire: Burst - 1 more rounds, one every Interval seconds, while the magazine lasts
            ("array_getelement", ("id", "n"), ("id", "::Burst_var"), ("id", "Prof")),
            ("array_getelement", ("id", "wait"), ("id", "::Interval_var"), ("id", "Prof")),
            ("assign", ("id", "i"), ("int", 1)),
            ("label", "bloop"),
            ("cmp_lt", T0, ("id", "i"), ("id", "n")),
            ("jmpf", T0, ("lbl", "band")),
            ("cmp_gt", T0, ("id", "Mag"), ("int", 0)),
            ("label", "band"),
            ("jmpf", T0, ("lbl", "bdone")),
            ("callstatic", ("id", "Utility"), ("id", "Wait"), NONE, ("id", "wait")),
            call("Place"),
            call("FireExtra", ("id", "s")),
            ("isub", ("id", "Mag"), ("id", "Mag"), ("int", 1)),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "bloop")),
            ("label", "bdone"),
            ("assign", ("id", "Busy"), ("bool", False)),
            call("CheckMag"),
            ("return", None),
        ],
    )
    check_mag = Function(
        "CheckMag",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("t", "Float"), ("have", "Int"), ("msg", "String"), ("a", "String")],
        code=[
            ("cmp_gt", T0, ("id", "Mag"), ("int", 0)),
            *ret_if(T0, "empty"),
            ("jmpf", ("id", "Reloading"), ("lbl", "start")),
            ("return", None),
            ("label", "start"),
            ("assign", ("id", "Reloading"), ("bool", True)),
            ("callmethod", ("id", "UnequipItem"), ("id", "Me"), NONE, ("id", "RndF"), ("bool", False), ("bool", True)),
            ("array_getelement", ("id", "t"), ("id", "::ReloadTime_var"), ("id", "Prof")),
            ("cast", ("id", "a"), ("id", "t")),
            *notify(("str", "Reloading ("), ("id", "a"), ("str", " s)")),
            ("callstatic", ("id", "Utility"), ("id", "Wait"), NONE, ("id", "t")),
            ("assign", ("id", "Mag"), ("id", "MagSize")),
            ("assign", ("id", "Fallback"), ("bool", False)),
            ("callmethod", ("id", "GetItemCount"), ("id", "Me"), ("id", "have"), ("id", "RndF")),
            ("cmp_lt", T0, ("id", "have"), ("int", 100)),
            ("jmpf", T0, ("lbl", "stocked")),
            ("callmethod", ("id", "AddItem"), ("id", "Me"), NONE, ("id", "RndF"), ("int", 200), ("bool", False)),
            ("label", "stocked"),
            # if the game will not hold the rounds, shoot steel bolts: magazines, reloads, pellets and bursts still work
            ("callmethod", ("id", "GetItemCount"), ("id", "Me"), ("id", "have"), ("id", "RndF")),
            ("cmp_lt", T0, ("id", "have"), ("int", 1)),
            ("jmpf", T0, ("lbl", "rounds")),
            ("assign", ("id", "Fallback"), ("bool", True)),
            ("assign", ("id", "Rnd"), ("id", "::Bolts_var")),
            ("cast", ("id", "RndF"), ("id", "Rnd")),
            ("callmethod", ("id", "GetItemCount"), ("id", "Me"), ("id", "have"), ("id", "RndF")),
            ("cmp_lt", T0, ("id", "have"), ("int", 100)),
            ("jmpf", T0, ("lbl", "rounds")),
            ("callmethod", ("id", "AddItem"), ("id", "Me"), NONE, ("id", "RndF"), ("int", 200), ("bool", False)),
            ("label", "rounds"),
            ("callmethod", ("id", "EquipItem"), ("id", "Me"), NONE, ("id", "RndF"), ("bool", False), ("bool", True)),
            ("callmethod", ("id", "GetItemCount"), ("id", "Me"), ("id", "Last"), ("id", "RndF")),
            ("assign", ("id", "Reloading"), ("bool", False)),
            ("return", None),
        ],
    )
    place = Function(
        "Place",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("::temp1", "Bool"), ("ox", "Float"), ("oy", "Float"), ("oz", "Float")],
        code=[
            ("cast", T0, ("id", "Aim")),
            *ret_unless(T0, "aim", tmp=T1),
            # the aim point goes in front of the player's eyes; the view's turn is kept for the rounds fired from it
            ("callmethod", ("id", "GetAngleZ"), ("id", "Me"), ("id", "ViewH")),
            ("callmethod", ("id", "GetAngleX"), ("id", "Me"), ("id", "ViewX")),
            ("callstatic", ("id", "Math"), ("id", "Sin"), ("id", "ox"), ("id", "ViewH")),
            ("fmul", ("id", "ox"), ("id", "ox"), ("float", 40.0)),
            ("callstatic", ("id", "Math"), ("id", "Cos"), ("id", "oy"), ("id", "ViewH")),
            ("fmul", ("id", "oy"), ("id", "oy"), ("float", 40.0)),
            ("callmethod", ("id", "GetHeight"), ("id", "Me"), ("id", "oz")),
            ("fmul", ("id", "oz"), ("id", "oz"), ("float", 0.85)),
            ("callmethod", ("id", "MoveTo"), ("id", "Aim"), NONE, ("id", "Me"), ("id", "ox"), ("id", "oy"), ("id", "oz"),
             ("bool", False)),
            ("return", None),
        ],
    )
    fire_extra = Function(
        "FireExtra",
        params=[("s", "Float")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("::temp1", "Bool"), ("h", "Float"), ("x", "Float"),
                ("d", "Float"), ("lo", "Float")],
        code=[
            ("cast", T0, ("id", "Aim")),
            *ret_unless(T0, "aim", tmp=T1),
            # one round from the aim point, turned like the view plus a random angle within the spread
            ("fneg", ("id", "lo"), ("id", "s")),
            ("callstatic", ("id", "Utility"), ("id", "RandomFloat"), ("id", "d"), ("id", "lo"), ("id", "s")),
            ("fadd", ("id", "x"), ("id", "ViewX"), ("id", "d")),
            ("callstatic", ("id", "Utility"), ("id", "RandomFloat"), ("id", "d"), ("id", "lo"), ("id", "s")),
            ("fadd", ("id", "h"), ("id", "ViewH"), ("id", "d")),
            ("callmethod", ("id", "SetAngle"), ("id", "Aim"), NONE, ("id", "x"), ("float", 0.0), ("id", "h")),
            ("callmethod", ("id", "Fire"), ("id", "Gun"), NONE, ("id", "Aim"), ("id", "Rnd")),
            ("return", None),
        ],
    )
    return Script(
        name="SkylandsGunner",
        parent="ActiveMagicEffect",
        variables=[("Me", "Actor", None), ("Aim", "ObjectReference", None), ("Gun", "Weapon", None), ("Rnd", "Ammo", None),
                   ("RndF", "Form", None),
                   ("Kind", "Int", ("int", -1)), ("Elem", "Int", ("int", 0)), ("Mag", "Int", ("int", 0)),
                   ("Shots", "Int", ("int", 0)), ("Busy", "Bool", ("bool", False)), ("Reloading", "Bool", ("bool", False)),
                   ("Seen", "Bool", ("bool", False)), ("Last", "Int", ("int", 0)),
                   ("Prof", "Int", ("int", 0)), ("MagSize", "Int", ("int", 1)), ("Fallback", "Bool", ("bool", False)), ("Tested", "Bool", ("bool", False)), ("Boxed", "Bool", ("bool", False)), ("LabText", "String", ("str", "")), ("ViewX", "Float", ("float", 0.0)),
                   ("ViewH", "Float", ("float", 0.0))],
        auto_properties=[("Rounds", "Form[]"), ("KindKeywords", "Keyword[]"), ("ElementKeywords", "Keyword[]"), ("Clip", "Int[]"),
                         ("ReloadTime", "Float[]"), ("Burst", "Int[]"), ("Pellets", "Int[]"), ("Spread", "Float[]"),
                         ("Interval", "Float[]"), ("Marker", "Form"), ("Verbose", "Bool"),
                         ("ProfileKeywords", "Keyword[]"), ("ClipTens", "Keyword[]"), ("ClipUnits", "Keyword[]"), ("Bolts", "Ammo"), ("LabItems", "Form[]")],
        functions=[on_start, on_load, ready, on_equipped, setup, lab, speed, on_shot, poll, on_update, shot, check_mag, place, fire_extra],
    )


def gunner_quest() -> Script:
    """SkylandsGunnerQuest extends Quest (start game enabled, in SkylandsGunModels.esp): makes sure the player has the
    gunner ability, once a few seconds after the plugin is loaded and again every 15 seconds (cheap: one HasSpell)."""
    on_init = Function("OnInit", locals=[("::nonevar", "None"), ("msg", "String")],
                       code=[*notify(("str", "Skylands quest started")),
                             ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 2.0)), ("return", None)])
    on_update = Function(
        "OnUpdate",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("player", "Actor"), ("msg", "String"), ("f", "Form")],
        code=[
            ("callstatic", ("id", "Game"), ("id", "GetPlayer"), ("id", "player")),
            # HasSpell takes a Form: the Spell property passed as it is fails ("Type mismatch for argument 1")
            ("cast", ("id", "f"), ("id", "::Ability_var")),
            ("callmethod", ("id", "HasSpell"), ("id", "player"), ("id", "::temp0"), ("id", "f")),
            ("not", ("id", "::temp0"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "has")),
            ("callmethod", ("id", "AddSpell"), ("id", "player"), ("id", "::temp0"), ("id", "::Ability_var"), ("bool", False)),
            *notify(("str", "Skylands: ability added")),
            ("label", "has"),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 15.0)),
            ("return", None),
        ],
    )
    return Script(name="SkylandsGunnerQuest", parent="Quest", auto_properties=[("Ability", "Spell")],
                  functions=[on_init, on_update])


# The player's relic variables: actor values of the player that any ability, relic or enchantment can fortify (or a script can set); the SKSE
# plugin reads them at every shot (percent, 0 = no change; Variable01..10 are the game's spare actor values, Variable10 shows the crossbow
# guns' stats line). Fire rate, reload speed and accuracy.
RELIC_FIRE_RATE, RELIC_RELOAD, RELIC_ACCURACY = "Variable06", "Variable07", "Variable08"


def staff_gun(name: str = "SkylandsStaffGun") -> Script:
    """SkylandsStaffGun extends ActiveMagicEffect: the player's side of every Skylands staff gun (SkylandsGunModels.esp).

    A staff gun is a staff weapon whose enchantment is its bullet; its numbers (magazine, interval, reload, spread) are in a keyword
    of its own that the SKSE plugin reads. The plugin fires the gun: while one is in the hand (SkylandsNative.SetGunMode) it keeps the
    game's attack handler from getting the right attack button, so the staff casts nothing and plays no animation, and it fires, counts
    the magazine, reloads, sets the charge bar, plays the shot sound and applies the relic actor values on its own clock (0.17.0's script loop
    ran at about half the rate it was set to). This script only introduces the gun to the plugin (which one is in the hand, its shot sound),
    gives two guns once at the start, draws the weapon, and shows what the plugin reports: a box on the first equip and, every ten shots,
    the magazine, the fire rate set and measured, the reload and the spread, and when a reload starts and ends.

      Event OnEffectStart / OnPlayerLoadGame / OnObjectEquipped / OnObjectUnequipped / OnUpdate
    """
    T0 = ("id", "::temp0")
    on_start = Function(
        "OnEffectStart",
        params=[("akTarget", "Actor"), ("akCaster", "Actor")],
        locals=[("::nonevar", "None")],
        code=[("assign", ("id", "Me"), ("id", "akTarget")), call("Start"), ("return", None)],
    )
    on_load = Function(
        "OnPlayerLoadGame", locals=[("::nonevar", "None")],
        code=[("assign", ("id", "Boxed"), ("bool", False)), call("Start"), ("return", None)],
    )
    start = Function(
        "Start",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("f", "Form"), ("msg", "String"), ("v", "Int")],
        code=[
            # two staff guns to try, given once
            ("not", T0, ("id", "Given")),
            ("jmpf", T0, ("lbl", "had")),
            ("assign", ("id", "Given"), ("bool", True)),
            ("cast", ("id", "f"), ("id", "::GiftA_var")),
            ("callmethod", ("id", "AddItem"), ("id", "Me"), NONE, ("id", "f"), ("int", 1), ("bool", False)),
            ("cast", ("id", "f"), ("id", "::GiftB_var")),
            ("callmethod", ("id", "AddItem"), ("id", "Me"), NONE, ("id", "f"), ("int", 1), ("bool", False)),
            ("label", "had"),
            # is the SKSE plugin of Skylands loaded? (-1: no)
            ("callstatic", ("id", "SKSE"), ("id", "GetPluginVersion"), ("id", "v"), ("str", "SkylandsNative")),
            ("cmp_gt", ("id", "Native"), ("id", "v"), ("int", 0)),
            # a number for this copy of the script, so two copies running side by side show in the messages
            ("cmp_eq", T0, ("id", "Tag"), ("int", 0)),
            ("jmpf", T0, ("lbl", "tagged")),
            ("callstatic", ("id", "Utility"), ("id", "RandomInt"), ("id", "Tag"), ("int", 100), ("int", 999)),
            ("label", "tagged"),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 1.0)),
            call("Resume"),
            ("return", None),
        ],
    )
    resume = Function(
        "Resume",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("r", "Form"), ("w", "Weapon")],
        code=[
            # a saved game loaded with a staff gun already in the hand: the equip event does not come again; with none, the plugin's
            # gun mode is switched off and the fighting controls an old version switched off are given back
            ("callmethod", ("id", "GetEquippedObject"), ("id", "Me"), ("id", "r"), ("int", 1)),
            ("cast", ("id", "w"), ("id", "r")),
            call("IsGun", ("id", "w"), dest=T0),
            ("jmpf", T0, ("lbl", "away")),
            call("Take", ("id", "w")),
            ("jmp", ("lbl", "end")),
            ("label", "away"),
            call("Let"),
            ("label", "end"),
            ("return", None),
        ],
    )
    is_gun = Function(
        "IsGun",
        params=[("w", "Weapon")],
        return_type="Bool",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("c", "Int")],
        code=[
            # the plugin knows a staff gun by its keyword: its magazine is more than none
            ("callstatic", ("id", "SkylandsNative"), ("id", "GunClip"), ("id", "c"), ("id", "w")),
            ("cmp_gt", T0, ("id", "c"), ("int", 0)),
            ("return", T0),
        ],
    )
    on_equipped = Function(
        "OnObjectEquipped",
        params=[("akBaseObject", "Form"), ("akReference", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("w", "Weapon")],
        code=[
            # a staff gun put on arms the script. The game also announces the gun's enchantment as put on: it is no weapon, nothing happens
            ("cast", ("id", "w"), ("id", "akBaseObject")),
            call("IsGun", ("id", "w"), dest=T0),
            ("jmpf", T0, ("lbl", "no")),
            call("Take", ("id", "w")),
            ("jmp", ("lbl", "end")),
            ("label", "no"),
            call("Unknown", ("id", "w")),
            ("label", "end"),
            ("return", None),
        ],
    )
    unknown = Function(
        "Unknown",
        params=[("w", "Weapon")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("msg", "String")],
        code=[
            # one of the two guns this script gave, and the plugin does not know it as a gun: say so (the plugin's log says why)
            ("cmp_eq", T0, ("id", "w"), ("id", "::GiftA_var")),
            ("jmpf", T0, ("lbl", "end")),
            *notify(("str", "Skylands: the plugin does not know this staff gun (see SkylandsNative.log)")),
            ("label", "end"),
            ("return", None),
        ],
    )
    take = Function(
        "Take",
        params=[("w", "Weapon")],
        locals=[("::nonevar", "None")],
        code=[
            # this gun is the one in the hand
            call("Load", ("id", "w")),
            ("assign", ("id", "Armed"), ("bool", True)),
            call("Grip"),
            call("Arm"),
            ("return", None),
        ],
    )
    load = Function(
        "Load",
        params=[("w", "Weapon")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            # remember the gun, pick its sounds and hand them to the plugin as Forms (a native with a Sound parameter never ran: no log line from it)
            ("assign", ("id", "Gun"), ("id", "w")),
            call("PickSound", ("id", "w")),
            ("callstatic", ("id", "SkylandsNative"), ("id", "SetShotSound"), ("id", "::temp0"), ("id", "Cur")),
            ("callstatic", ("id", "SkylandsNative"), ("id", "SetReloadSounds"), ("id", "::temp0"), ("id", "RelOut"), ("id", "RelIn"), ("id", "RelEnd")),
            ("return", None),
        ],
    )
    on_unequipped = Function(
        "OnObjectUnequipped",
        params=[("akBaseObject", "Form"), ("akReference", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("w", "Weapon")],
        code=[
            # the gun in the hand was put away (another staff gun put on first has already become the Gun)
            ("cast", ("id", "w"), ("id", "akBaseObject")),
            ("cmp_eq", T0, ("id", "w"), ("id", "Gun")),
            ("jmpf", T0, ("lbl", "end")),
            ("jmpf", ("id", "Armed"), ("lbl", "end")),
            ("assign", ("id", "Armed"), ("bool", False)),
            call("Let"),
            ("label", "end"),
            ("return", None),
        ],
    )
    on_update = Function(
        "OnUpdate",
        locals=[("::nonevar", "None"), ("next", "Float")],
        code=[
            # with a gun in the hand the plugin is asked what it did four times a second; without one, once a second
            ("assign", ("id", "next"), ("float", 1.0)),
            ("jmpf", ("id", "Armed"), ("lbl", "idle")),
            ("assign", ("id", "next"), ("float", 0.25)),
            call("Watch"),
            ("label", "idle"),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("id", "next")),
            ("return", None),
        ],
    )
    watch = Function(
        "Watch",
        locals=[("::nonevar", "None")],
        code=[call("Count10"), call("Reloads"), ("return", None)],
    )
    count10 = Function(
        "Count10",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("n", "Int"), ("t", "Int")],
        code=[
            # a new multiple of ten shots fired: tell the numbers
            ("callstatic", ("id", "SkylandsNative"), ("id", "ShotsFired"), ("id", "n")),
            ("idiv", ("id", "t"), ("id", "n"), ("int", 10)),
            ("cmp_eq", T0, ("id", "t"), ("id", "Told")),
            ("jmpf", T0, ("lbl", "differ")),
            ("return", None),
            ("label", "differ"),
            ("assign", ("id", "Told"), ("id", "t")),
            call("TellIf"),
            ("return", None),
        ],
    )
    tell_if = Function(
        "TellIf",
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            ("assign", T0, ("id", "::Verbose_var")),
            ("jmpf", T0, ("lbl", "end")),
            call("Tell"),
            ("label", "end"),
            ("return", None),
        ],
    )
    reloads = Function(
        "Reloads",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("r", "Bool")],
        code=[
            # a reload started or ended
            ("callstatic", ("id", "SkylandsNative"), ("id", "Reloading"), ("id", "r")),
            ("cmp_eq", T0, ("id", "r"), ("id", "WasReloading")),
            ("jmpf", T0, ("lbl", "differ")),
            ("return", None),
            ("label", "differ"),
            ("assign", ("id", "WasReloading"), ("id", "r")),
            call("SayReload", ("id", "r")),
            ("return", None),
        ],
    )
    say_reload = Function(
        "SayReload",
        params=[("started", "Bool")],
        locals=[("::nonevar", "None"), ("msg", "String")],
        code=[
            ("jmpf", ("id", "started"), ("lbl", "ended")),
            *notify(("str", "Staff gun: reloading")),
            ("return", None),
            ("label", "ended"),
            *notify(("str", "Staff gun: reloaded")),
            ("return", None),
        ],
    )
    tell = Function(
        "Tell",
        locals=[("::nonevar", "None"), ("a", "String"), ("b", "String"), ("c", "String"), ("d", "String"), ("e", "String"), ("f", "String"),
                ("msg", "String"), ("n", "Int")],
        code=[
            # what the plugin's gun is doing now, relic bonuses included: magazine, rounds a second set and measured since the trigger went
            # down, reload seconds, shot spread degrees
            ("callstatic", ("id", "SkylandsNative"), ("id", "Magazine"), ("id", "n")),
            ("cast", ("id", "a"), ("id", "n")),
            ("callstatic", ("id", "SkylandsNative"), ("id", "GunClip"), ("id", "n"), ("id", "Gun")),
            ("cast", ("id", "b"), ("id", "n")),
            ("callstatic", ("id", "SkylandsNative"), ("id", "RateTenths"), ("id", "n")),
            ("callmethod", ("id", "Tenths"), SELF, ("id", "c"), ("id", "n")),
            ("callstatic", ("id", "SkylandsNative"), ("id", "MeasuredTenths"), ("id", "n")),
            ("callmethod", ("id", "Tenths"), SELF, ("id", "f"), ("id", "n")),
            ("callstatic", ("id", "SkylandsNative"), ("id", "ReloadMsNow"), ("id", "n")),
            ("idiv", ("id", "n"), ("id", "n"), ("int", 100)),
            ("callmethod", ("id", "Tenths"), SELF, ("id", "d"), ("id", "n")),
            ("callstatic", ("id", "SkylandsNative"), ("id", "SpreadNowTenths"), ("id", "n")),
            ("callmethod", ("id", "Tenths"), SELF, ("id", "e"), ("id", "n")),
            *notify(("str", "Staff gun: magazine "), ("id", "a"), ("str", " of "), ("id", "b"), ("str", ", fire rate "), ("id", "c"),
                    ("str", "/s (measured "), ("id", "f"), ("str", "/s), reload "), ("id", "d"), ("str", " s, spread "), ("id", "e"), ("str", " deg")),
            ("return", None),
        ],
    )
    tenths = Function(
        "Tenths",
        return_type="String",
        params=[("n", "Int")],
        locals=[("::nonevar", "None"), ("whole", "Int"), ("tenth", "Int"), ("a", "String"), ("b", "String"), ("out", "String")],
        code=[
            # a number given in tenths as text with one decimal ("7.2"; Papyrus prints a Float with six)
            ("idiv", ("id", "whole"), ("id", "n"), ("int", 10)),
            ("imod", ("id", "tenth"), ("id", "n"), ("int", 10)),
            ("cast", ("id", "a"), ("id", "whole")),
            ("cast", ("id", "b"), ("id", "tenth")),
            ("strcat", ("id", "out"), ("id", "a"), ("str", ".")),
            ("strcat", ("id", "out"), ("id", "out"), ("id", "b")),
            ("return", ("id", "out")),
        ],
    )
    arm = Function(
        "Arm",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("a", "String"), ("b", "String"), ("c", "String"), ("d", "String"),
                ("e", "String"), ("f", "String"), ("g", "String"), ("v", "Int"), ("msg", "String"), ("r", "Form"), ("w", "Weapon"),
                ("hand", "String")],
        code=[
            # the box (on the first equip after a load) says what the build made and what the game reports: SKSE, the plugin, the hand, the magazine
            *ret_if(("id", "Boxed"), "shown"),
            ("assign", ("id", "Boxed"), ("bool", True)),
            ("callstatic", ("id", "Utility"), ("id", "Wait"), NONE, ("float", 1.0)),
            ("callstatic", ("id", "SkylandsNative"), ("id", "Magazine"), ("id", "v")),
            ("cast", ("id", "b"), ("id", "v")),
            ("callstatic", ("id", "SkylandsNative"), ("id", "GunClip"), ("id", "v"), ("id", "Gun")),
            ("cast", ("id", "c"), ("id", "v")),
            ("callstatic", ("id", "SKSE"), ("id", "GetVersion"), ("id", "v")),
            ("cast", ("id", "d"), ("id", "v")),
            ("callstatic", ("id", "SKSE"), ("id", "GetVersionMinor"), ("id", "v")),
            ("cast", ("id", "e"), ("id", "v")),
            ("callstatic", ("id", "SKSE"), ("id", "GetVersionBeta"), ("id", "v")),
            ("cast", ("id", "f"), ("id", "v")),
            ("assign", ("id", "g"), ("str", "NOT LOADED: copy SkylandsNative.dll into Data/SKSE/Plugins and install Address Library")),
            ("jmpf", ("id", "Native"), ("lbl", "nodll")),
            ("assign", ("id", "g"), ("str", "loaded")),
            ("label", "nodll"),
            ("assign", ("id", "hand"), ("str", "NOT the right hand")),
            ("callmethod", ("id", "GetEquippedObject"), ("id", "Me"), ("id", "r"), ("int", 1)),
            ("cast", ("id", "w"), ("id", "r")),
            ("cmp_eq", T0, ("id", "w"), ("id", "Gun")),
            ("jmpf", T0, ("lbl", "lefty")),
            ("assign", ("id", "hand"), ("str", "right hand")),
            ("label", "lefty"),
            ("assign", ("id", "msg"), ("str", "Skylands staff gun. SKSE ")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "d")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", ".")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "e")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", ".")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "f")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", ", Skylands plugin: ")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "g")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", ". Magazine: ")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "b")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", " of ")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "c")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", "; the gun is in the ")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "hand")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("str", "; the plugin fires it. ")),
            ("strcat", ("id", "msg"), ("id", "msg"), ("id", "::Info_var")),
            ("callstatic", ("id", "Debug"), ("id", "MessageBox"), NONE, ("id", "msg")),
            ("return", None),
        ],
    )
    grip = Function(
        "Grip",
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            # the plugin keeps the right attack button from the game while the gun is in the hand (no animation); fighting controls
            # that 0.14.3 switched off in a saved game are given back; the weapon is drawn
            call("Heal"),
            ("callstatic", ("id", "SkylandsNative"), ("id", "SetGunMode"), ("id", "::temp0"), ("bool", True)),
            ("callmethod", ("id", "IsWeaponDrawn"), ("id", "Me"), T0),
            ("not", T0, T0),
            ("jmpf", T0, ("lbl", "drawn")),
            ("callmethod", ("id", "DrawWeapon"), ("id", "Me"), NONE),
            ("label", "drawn"),
            ("return", None),
        ],
    )
    heal = Function(
        "Heal",
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            # 0.14.3 switched the fighting controls off with Game.DisablePlayerControls and a save keeps that: give them back once
            *ret_unless(("id", "ControlsOff"), "off"),
            ("callstatic", ("id", "Game"), ("id", "EnablePlayerControls"), NONE, ("bool", False), ("bool", True), ("bool", False),
             ("bool", False), ("bool", False), ("bool", False), ("bool", False), ("bool", False), ("int", 0)),
            ("assign", ("id", "ControlsOff"), ("bool", False)),
            ("return", None),
        ],
    )
    let = Function(
        "Let",
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            # the gun is away: the attack button is the game's again
            call("Heal"),
            ("callstatic", ("id", "SkylandsNative"), ("id", "SetGunMode"), ("id", "::temp0"), ("bool", False)),
            ("return", None),
        ],
    )
    pick_sound = Function(
        "PickSound",
        params=[("w", "Weapon")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("i", "Int"), ("n", "Int"), ("k", "Keyword"), ("s", "Form")],
        code=[
            # this gun's shot sound: the one whose keyword the gun carries (one per gun type), else the default
            ("assign", ("id", "Cur"), ("id", "::ShotSound_var")),
            ("assign", ("id", "RelOut"), ("id", "::nonevar")),
            ("assign", ("id", "RelIn"), ("id", "::nonevar")),
            ("assign", ("id", "RelEnd"), ("id", "::nonevar")),
            ("array_length", ("id", "n"), ("id", "::SoundKeywords_var")),
            ("assign", ("id", "i"), ("int", 0)),
            ("label", "loop"),
            ("cmp_lt", T0, ("id", "i"), ("id", "n")),
            ("jmpf", T0, ("lbl", "end")),
            ("array_getelement", ("id", "k"), ("id", "::SoundKeywords_var"), ("id", "i")),
            ("callmethod", ("id", "HasKeyword"), ("id", "w"), T0, ("id", "k")),
            ("jmpf", T0, ("lbl", "next")),
            ("array_getelement", ("id", "s"), ("id", "::Sounds_var"), ("id", "i")),
            ("assign", ("id", "Cur"), ("id", "s")),
            ("array_getelement", ("id", "s"), ("id", "::ReloadOut_var"), ("id", "i")),
            ("assign", ("id", "RelOut"), ("id", "s")),
            ("array_getelement", ("id", "s"), ("id", "::ReloadIn_var"), ("id", "i")),
            ("assign", ("id", "RelIn"), ("id", "s")),
            ("array_getelement", ("id", "s"), ("id", "::ReloadEnd_var"), ("id", "i")),
            ("assign", ("id", "RelEnd"), ("id", "s")),
            ("assign", ("id", "i"), ("id", "n")),
            ("label", "next"),
            ("iadd", ("id", "i"), ("id", "i"), ("int", 1)),
            ("jmp", ("lbl", "loop")),
            ("label", "end"),
            ("return", None),
        ],
    )

    return Script(
        name=name,
        parent="ActiveMagicEffect",
        variables=[("Me", "Actor", None), ("Gun", "Weapon", None), ("Cur", "Form", None), ("RelOut", "Form", None), ("RelIn", "Form", None),
                   ("RelEnd", "Form", None), ("Armed", "Bool", ("bool", False)),
                   ("Boxed", "Bool", ("bool", False)), ("Given", "Bool", ("bool", False)), ("Native", "Bool", ("bool", False)),
                   ("Tag", "Int", ("int", 0)), ("Told", "Int", ("int", 0)), ("WasReloading", "Bool", ("bool", False)),
                   ("ControlsOff", "Bool", ("bool", False))],
        auto_properties=[("GiftA", "Weapon"), ("GiftB", "Weapon"), ("SpeedMult", "Float"), ("ChargePerShot", "Float"),
                         ("OffsetRight", "Float"), ("OffsetUp", "Float"), ("OffsetForward", "Float"), ("ShotSound", "Form"),
                         ("SoundKeywords", "Keyword[]"), ("Sounds", "Form[]"), ("ReloadOut", "Form[]"), ("ReloadIn", "Form[]"),
                         ("ReloadEnd", "Form[]"), ("Info", "String"), ("Verbose", "Bool")],
        functions=[on_start, on_load, start, resume, is_gun, on_equipped, unknown, take, load, on_unequipped, on_update, watch, count10, tell_if,
                   reloads, say_reload, tell, tenths, arm, grip, heal, let, pick_sound],
    )


def native_stub() -> Script:
    """SkylandsNative: the declarations of the functions the SKSE plugin SkylandsNative.dll registers (Data/Scripts/SkylandsNative.pex).
    SKSE binds a plugin's functions to the native functions a script declares, so a plugin's class needs this file or the game
    cannot find the class when another script calls it. The types must be those of the plugin's C++ functions (native/skse/src/main.cpp)."""
    both = 1 | 2  # global, native
    return Script(
        name="SkylandsNative",
        parent="",
        functions=[
            Function("Version", return_type="Int", flags=both),
            Function("SetGunMode", return_type="Bool", flags=both, params=[("abOn", "Bool")]),
            Function("TriggerHeld", return_type="Bool", flags=both),
            Function("TriggerPressed", return_type="Bool", flags=both),
            Function("GunClip", return_type="Int", flags=both, params=[("akWeapon", "Weapon")]),
            Function("GunIntervalMs", return_type="Int", flags=both, params=[("akWeapon", "Weapon")]),
            Function("GunReloadMs", return_type="Int", flags=both, params=[("akWeapon", "Weapon")]),
            Function("GunSpreadTenths", return_type="Int", flags=both, params=[("akWeapon", "Weapon")]),
            Function("Magazine", return_type="Int", flags=both),
            Function("ShotsFired", return_type="Int", flags=both),
            Function("Reloading", return_type="Bool", flags=both),
            Function("RateTenths", return_type="Int", flags=both),
            Function("MeasuredTenths", return_type="Int", flags=both),
            Function("ReloadMsNow", return_type="Int", flags=both),
            Function("SpreadNowTenths", return_type="Int", flags=both),
            Function("SetShotSound", return_type="Bool", flags=both, params=[("akSound", "Form")]),
            Function("SetReloadSounds", return_type="Bool", flags=both, params=[("akOut", "Form"), ("akIn", "Form"), ("akEnd", "Form")]),
            Function("FireGun", return_type="Bool", flags=both,
                     params=[("akShooter", "Actor"), ("afRight", "Float"), ("afUp", "Float"), ("afForward", "Float"), ("afSpreadMult", "Float")]),
        ],
    )


def retired(name: str) -> Script:
    """A script with nothing in it, written over an earlier revision's file: a saved game keeps running the old script
    objects of that name as ghosts, and with this they do nothing."""
    return Script(name=name, parent="ActiveMagicEffect", functions=[])
