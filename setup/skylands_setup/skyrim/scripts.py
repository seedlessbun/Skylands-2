"""The Papyrus scripts Skylands needs, written straight to .pex (see pex.py)."""

from __future__ import annotations

from .pex import Function, Script

NONE = ("id", "::nonevar")
SELF = ("id", "self")
ZERO9 = [("float", 0.0)] * 9  # Message.Show's nine optional float arguments


def class_choice_quest() -> Script:
    """SkylandsClassQuest extends Quest.

    As soon as the player can move after character creation (and is not in a menu), show the
    vault hunter choice once, then teach and equip that vault hunter's action-skill shout and give
    the starting gun and its ammo. Works the same on an existing save.

      Event OnInit()
        RegisterForSingleUpdate(2.0)
      EndEvent

      Event OnUpdate()
        If Chosen
          Return
        EndIf
        If Utility.IsInMenuMode()
          RegisterForSingleUpdate(1.0)
          Return
        EndIf
        If !Game.IsMovementControlsEnabled()
          RegisterForSingleUpdate(1.0)
          Return
        EndIf
        Int i = ClassChoice.Show()
        Actor player = Game.GetPlayer()
        player.AddShout(Shouts[i])
        Game.TeachWord(Words[i])
        Game.UnlockWord(Words[i])
        player.EquipShout(Shouts[i])
        player.AddItem(StarterGun, 1, False)
        player.AddItem(StarterAmmo, 60, False)
        player.EquipItem(StarterGun, False, False)
        Chosen = True
      EndEvent
    """
    on_init = Function(
        "OnInit",
        locals=[("::nonevar", "None")],
        code=[("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 2.0)), ("return", None)],
    )
    on_update = Function(
        "OnUpdate",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("choice", "Int"), ("player", "Actor"),
                ("chosenShout", "Shout"), ("chosenWord", "WordOfPower"), ("::temp5", "Bool")],
        code=[
            ("jmpf", ("id", "Chosen"), ("lbl", "not_chosen")),
            ("return", None),
            ("label", "not_chosen"),
            ("callstatic", ("id", "Utility"), ("id", "IsInMenuMode"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp0"), ("lbl", "not_menu")),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 1.0)),
            ("return", None),
            ("label", "not_menu"),
            ("callstatic", ("id", "Game"), ("id", "IsMovementControlsEnabled"), ("id", "::temp5")),
            ("not", ("id", "::temp0"), ("id", "::temp5")),  # the compiler's shape for If !X
            ("jmpf", ("id", "::temp0"), ("lbl", "can_move")),
            ("callmethod", ("id", "RegisterForSingleUpdate"), SELF, NONE, ("float", 1.0)),
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
    return Script(
        name="SkylandsClassQuest",
        parent="Quest",
        variables=[("Chosen", "Bool", ("bool", False))],
        auto_properties=[("ClassChoice", "Message"), ("Shouts", "Shout[]"), ("Words", "WordOfPower[]"),
                         ("StarterGun", "Form"), ("StarterAmmo", "Form")],
        functions=[on_init, on_update],
    )


def loot_beam() -> Script:
    """SkylandsLootBeam extends ObjectReference (attached to every Skylands gun).

      Activator Property Beam Auto
      ObjectReference beamRef

      Event OnLoad()
        If !beamRef
          beamRef = PlaceAtMe(Beam, 1, False, False)
        EndIf
      EndEvent

      Event OnUnload()
        ClearBeam()
      EndEvent

      Event OnContainerChanged(ObjectReference akNewContainer, ObjectReference akOldContainer)
        If akNewContainer
          ClearBeam()
        EndIf
      EndEvent

      Function ClearBeam()
        If beamRef
          beamRef.Disable(False)
          beamRef.Delete()
          beamRef = None
        EndIf
      EndFunction
    """
    clear_call = ("callmethod", ("id", "ClearBeam"), SELF, NONE)
    on_load = Function(
        "OnLoad",
        locals=[("::nonevar", "None"), ("::temp0", "Bool"), ("::temp1", "Bool"), ("placed", "ObjectReference")],
        code=[
            ("cast", ("id", "::temp0"), ("id", "beamRef")),
            ("not", ("id", "::temp1"), ("id", "::temp0")),
            ("jmpf", ("id", "::temp1"), ("lbl", "done")),
            ("callmethod", ("id", "PlaceAtMe"), SELF, ("id", "placed"), ("id", "::Beam_var"), ("int", 1),
             ("bool", False), ("bool", False)),
            ("assign", ("id", "beamRef"), ("id", "placed")),
            ("label", "done"),
            ("return", None),
        ],
    )
    on_unload = Function("OnUnload", locals=[("::nonevar", "None")], code=[clear_call, ("return", None)])
    on_container = Function(
        "OnContainerChanged",
        params=[("akNewContainer", "ObjectReference"), ("akOldContainer", "ObjectReference")],
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            ("cast", ("id", "::temp0"), ("id", "akNewContainer")),
            ("jmpf", ("id", "::temp0"), ("lbl", "done")),
            clear_call,
            ("label", "done"),
            ("return", None),
        ],
    )
    clear = Function(
        "ClearBeam",
        locals=[("::nonevar", "None"), ("::temp0", "Bool")],
        code=[
            ("cast", ("id", "::temp0"), ("id", "beamRef")),
            ("jmpf", ("id", "::temp0"), ("lbl", "done")),
            ("callmethod", ("id", "Disable"), ("id", "beamRef"), NONE, ("bool", False)),
            ("callmethod", ("id", "Delete"), ("id", "beamRef"), NONE),
            ("assign", ("id", "beamRef"), None),
            ("label", "done"),
            ("return", None),
        ],
    )
    return Script(
        name="SkylandsLootBeam",
        parent="ObjectReference",
        variables=[("beamRef", "ObjectReference", None)],
        auto_properties=[("Beam", "Activator")],
        functions=[on_load, on_unload, on_container, clear],
    )
