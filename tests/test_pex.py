"""Compiled scripts are checked by decompiling them with Champollion (set CHAMPOLLION to its binary)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))

from skylands_setup.skyrim import pex, scripts  # noqa: E402

CHAMPOLLION = os.environ.get("CHAMPOLLION", "")

QUEST_EXPECTED = """Event OnUpdate()
  Self.Choose()
  If Chosen
    Return
  EndIf
  Self.RegisterForSingleUpdate(1.0)"""

CHOOSE = """  Int choice = ClassChoice.Show(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
  Actor player = Game.GetPlayer()
  Shout chosenShout = Shouts[choice]
  player.AddShout(chosenShout)
  WordOfPower chosenWord = Words[choice]
  Game.TeachWord(chosenWord)
  Game.UnlockWord(chosenWord)
  player.EquipShout(chosenShout)
  player.AddItem(StarterGun, 1, False)
  player.AddItem(StarterAmmo, 60, False)
  player.EquipItem(StarterGun, False, False)
  Chosen = True"""

BEAMS = """    Bool has = base.HasKeyword(kw)
    If has
      hit = True
      Self.Place(r, k)
      k = -1"""

PLACE = """    beam.Track(r, Self, lr)
    Tracked[TrackedNext] = r"""

WATCHER = {
    "start": """Event OnEffectStart(Actor akTarget, Actor akCaster)
  Me = akTarget
  Actor player = Game.GetPlayer()
  If Me == player
    IsPlayer = True
    Weapon w = Me.GetEquippedWeapon(False)
    Self.ApplySpeed(w)
    Self.RegisterForSingleUpdate(2.0)
    Return
  EndIf""",
    "speed": """      Int n = SpeedKeywords.Length
      Int i = 0
      While i < n
        Keyword k = SpeedKeywords[i]
        If w.HasKeyword(k)
          Float f = i as Float""",
    "apply": """  Self.ApplySpeed(w)
    Self.RegisterForSingleUpdate(2.0)""",
    "scan": "Game.FindRandomReferenceOfAnyTypeInList(GunList, x, y, z, ScanRadius)",
    "arm": """  Armed = True
  If Me.IsDead()
    Return
  EndIf
  If Self.Carrying()
    Return
  EndIf""",
    "equip": """    Me.AddItem(g, 1, True)
    Me.AddItem(Bolts, 30, True)
    Me.EquipItem(f, False, True)""",
    "drop": """  Me.UnequipItem(w, False, True)
  ObjectReference drop = Me.DropObject(w, 1)""",
    "death": """Event OnDeath(Actor akKiller)
  If IsPlayer
    Return
  EndIf
  Self.Cleanup(akKiller)""",
    "worthy": """  If Me.HasKeyword(NpcKeyword)
    Actor player = Game.GetPlayer()
    If killer == player""",
}


def test_header_and_layout():
    data = pex.write(scripts.class_choice_quest())
    assert data[:4] == bytes.fromhex("FA57C0DE") and data[4:6] == bytes([3, 2]) and data[6:8] == b"\x00\x01"


def test_jump_labels_resolve():
    s = pex.Script("J", "Quest", functions=[pex.Function("F", code=[("jmp", ("lbl", "end")), ("label", "end"), ("return", None)])])
    assert pex.write(s)


def decompile(tmp_path, script, name):
    f = tmp_path / f"{name}.pex"
    f.write_bytes(pex.write(script))
    subprocess.run([CHAMPOLLION, str(f), "-p", str(tmp_path / "out")], check=True, timeout=30, capture_output=True)
    return "\n".join(line.rstrip() for line in (tmp_path / "out" / f"{name}.psc").read_text().splitlines())


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_class_quest_decompiles_to_intended_papyrus(tmp_path):
    psc = decompile(tmp_path, scripts.class_choice_quest(), "SkylandsClassQuest")
    assert "ScriptName SkylandsClassQuest Extends Quest" in psc
    for prop in ("Message Property ClassChoice Auto", "Shout[] Property Shouts Auto", "Form Property StarterGun Auto",
                 "Form Property StarterAmmo Auto", "Keyword[] Property RarityKeywords Auto", "Activator[] Property Beams Auto",
                 "Light[] Property Lights Auto", "Bool Property Verbose Auto"):
        assert prop in psc
    for text in (QUEST_EXPECTED, CHOOSE, BEAMS, PLACE):
        assert text in psc


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_watcher_decompiles_to_intended_papyrus(tmp_path):
    psc = decompile(tmp_path, scripts.watcher(), "SkylandsWatcher")
    assert "ScriptName SkylandsWatcher Extends ActiveMagicEffect" in psc
    for prop in ("SkylandsClassQuest Property Owner Auto", "Keyword[] Property SpeedKeywords Auto", "FormList Property GunList Auto",
                 "Form Property GunDrop Auto", "Int Property ArmChance Auto", "Float Property ScanRadius Auto"):
        assert prop in psc
    for text in WATCHER.values():
        assert text in psc


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_loot_beam_decompiles_to_intended_papyrus(tmp_path):
    psc = decompile(tmp_path, scripts.loot_beam(), "SkylandsLootBeam")
    assert "ScriptName SkylandsLootBeam Extends ObjectReference" in psc
    assert "Function Track(ObjectReference t, SkylandsClassQuest q, ObjectReference l)" in psc
    assert "ok = target.Is3DLoaded()" in psc and "lamp.Delete()" in psc
    assert "owner.Forget(target)\n  EndIf" in psc and "Self.Disable(False)\n  Self.Delete()" in psc
