"""A stand-in for the Willow2 SDK and a tiny Borderlands 2 world, so game.py can be smoke-tested
off the game. It checks Python logic only; the real API is checked in the running game."""

from __future__ import annotations

import contextlib
import enum
import sys
import types
from dataclasses import dataclass, field
from types import SimpleNamespace as NS
from typing import Any

LOG: list[str] = []
HUD: list[tuple[str, str]] = []
SHOWN: list[Any] = []
WORLD = NS(pc=None, objects={})


class FakeObj:
    _next = 1

    def __init__(self, name: str = "Obj", **kw: Any) -> None:
        FakeObj._next += 1
        self._addr = FakeObj._next
        self.Name = name
        self.calls: list[tuple[str, dict]] = []
        for k, v in kw.items():
            setattr(self, k, v)

    def _get_address(self) -> int:
        return self._addr

    def _path_name(self) -> str:
        return self.Name


class Pawn(FakeObj):
    def __init__(self, name: str, x: float, y: float, z: float = 0.0, hp: float = 1000.0, enemy: bool = True) -> None:
        super().__init__(name, Location=NS(X=x, Y=y, Z=z), Velocity=NS(X=0.0, Y=0.0, Z=0.0), NextPawn=None,
                         GroundSpeed=440.0, Weapon=None)
        self.hp, self.max_hp, self.enemy = hp, hp, enemy
        self.shield, self.max_shield = 0.0, 0.0
        self.injured = False

    def IsAliveAndWell(self) -> bool:
        return self.hp > 0

    def IsEnemy(self, other: Any) -> bool:
        return getattr(other, "enemy", False)

    def IsInjured(self) -> bool:
        return self.injured

    def GetMaxHealth(self) -> float:
        return self.max_hp

    def GetHealth(self) -> float:
        return self.hp

    def SetHealth(self, v: float) -> None:
        self.hp = v

    def GetShieldStrength(self) -> float:
        return self.shield

    def GetMaxShieldStrength(self) -> float:
        return self.max_shield

    def SetShieldStrength(self, v: float) -> None:
        self.shield = v

    def TakeDamage(self, **kw: Any) -> None:
        self.calls.append(("TakeDamage", kw))
        self.hp -= kw["Damage"]

    def AddVelocity(self, **kw: Any) -> None:
        self.calls.append(("AddVelocity", kw))

    def PlayAkEvent(self, **kw: Any) -> None:
        self.calls.append(("PlayAkEvent", kw))


def make_world() -> NS:
    me = Pawn("Player", 0, 0, enemy=False)
    me.max_shield = me.shield = 100.0
    front = Pawn("BanditFront", 500, 0)
    behind = Pawn("BanditBehind", -500, 0)
    far = Pawn("BanditFar", 5000, 0)
    me.NextPawn, front.NextPawn, behind.NextPawn = front, behind, far
    pri = FakeObj("PRI", ExpLevel=5)
    pri.money = 100
    pri.GetCurrencyOnHand = lambda _form: pri.money

    def add_money(AddValue: int, FormOfCurrency: int) -> None:  # noqa: N803
        pri.money += AddValue
    pri.AddCurrencyOnHand = add_money
    pc = FakeObj("PC", Pawn=me, Rotation=NS(Yaw=0, Pitch=0), PlayerReplicationInfo=pri,
                 WorldInfo=NS(Pauser=None, PawnList=me))
    pc.ClientPlayCameraAnim = lambda **kw: pc.calls.append(("Camera", kw))
    WORLD.pc = pc
    return NS(pc=pc, me=me, front=front, behind=behind, far=far, pri=pri)


def install(settings_dir: str) -> None:
    # unrealsdk
    sdk = types.ModuleType("unrealsdk")
    sdk.find_object = lambda cls, name: FakeObj(name)
    sdk.find_class = lambda name: FakeObj(name)
    sdk.make_struct = lambda name, **kw: NS(**kw)
    logging = types.ModuleType("unrealsdk.logging")
    logging.info = logging.warning = logging.error = LOG.append
    hooks = types.ModuleType("unrealsdk.hooks")

    class Block:
        pass

    class Type(enum.Enum):
        PRE = 0
        POST = 1
        POST_UNCONDITIONAL = 2

    hooks.Block, hooks.Type = Block, Type
    hooks.prevent_hooking_direct_calls = contextlib.nullcontext
    sdk.logging, sdk.hooks = logging, hooks
    sys.modules.update({"unrealsdk": sdk, "unrealsdk.logging": logging, "unrealsdk.hooks": hooks})

    # mods_base
    mb = types.ModuleType("mods_base")
    mb.SETTINGS_DIR = settings_dir
    mb.get_pc = lambda possibly_loading=False: WORLD.pc

    def hook(name: str, hook_type: Any = None):
        def deco(f):
            f.hook_name = name
            return f
        return deco

    def keybind(name: str, key: str, description: str = ""):
        def deco(f):
            f.key = key
            return f
        return deco

    mb.hook, mb.keybind = hook, keybind
    mb.build_mod = lambda **kw: NS(**kw)
    sys.modules["mods_base"] = mb

    # save_options
    so = types.ModuleType("save_options")

    @dataclass
    class HiddenSaveOption:
        identifier: str
        value: Any = None

    so.HiddenSaveOption = HiddenSaveOption
    so.register_save_options = lambda mod, **kw: mod
    so_opts = types.ModuleType("save_options.options")
    so_opts.trigger_save = lambda: LOG.append("saved")
    sys.modules.update({"save_options": so, "save_options.options": so_opts})

    # ui_utils
    ui = types.ModuleType("ui_utils")

    @dataclass
    class OptionBoxButton:
        name: str
        tip: str = ""

    @dataclass
    class OptionBox:
        title: str
        message: str = ""
        buttons: list = field(default_factory=list)
        on_select: Any = None
        on_cancel: Any = None
        prevent_cancelling: bool = False

        def show(self) -> None:
            SHOWN.append(self)

    @dataclass
    class TrainingBox:
        title: str
        message: str
        pauses_game: bool = False
        on_exit: Any = None

        def show(self) -> None:
            SHOWN.append(self)

    ui.OptionBox, ui.OptionBoxButton, ui.TrainingBox = OptionBox, OptionBoxButton, TrainingBox
    ui.show_hud_message = lambda title, msg, duration=2.5: HUD.append((title, msg))
    sys.modules["ui_utils"] = ui
