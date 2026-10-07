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

EXPECTED = """Event OnUpdate()
  If Chosen
    Return
  EndIf
  If Utility.IsInMenuMode()
    Self.RegisterForSingleUpdate(1.0)
    Return
  EndIf
  If !Game.IsMovementControlsEnabled()
    Self.RegisterForSingleUpdate(1.0)
    Return
  EndIf
  Int choice = ClassChoice.Show(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
  Actor player = Game.GetPlayer()
  Shout chosenShout = Shouts[choice]
  player.AddShout(chosenShout)
  WordOfPower chosenWord = Words[choice]
  Game.TeachWord(chosenWord)
  Game.UnlockWord(chosenWord)
  player.EquipShout(chosenShout)
  player.AddItem(StarterGuns, 1, False)
  Chosen = True
  Return
EndEvent"""


def test_header_and_layout():
    data = pex.write(scripts.class_choice_quest())
    assert data[:4] == bytes.fromhex("FA57C0DE") and data[4:6] == bytes([3, 2]) and data[6:8] == b"\x00\x01"


def test_jump_labels_resolve():
    s = pex.Script("J", "Quest", functions=[pex.Function("F", code=[("jmp", ("lbl", "end")), ("label", "end"), ("return", None)])])
    assert pex.write(s)


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_class_quest_decompiles_to_intended_papyrus(tmp_path):
    f = tmp_path / "SkylandsClassQuest.pex"
    f.write_bytes(pex.write(scripts.class_choice_quest()))
    subprocess.run([CHAMPOLLION, str(f), "-p", str(tmp_path / "out")], check=True, timeout=30, capture_output=True)
    psc = "\n".join(line.rstrip() for line in (tmp_path / "out" / "SkylandsClassQuest.psc").read_text().splitlines())
    assert "ScriptName SkylandsClassQuest Extends Quest" in psc
    for prop in ("Message Property ClassChoice Auto", "Shout[] Property Shouts Auto",
                 "WordOfPower[] Property Words Auto", "Form Property StarterGuns Auto"):
        assert prop in psc
    assert EXPECTED in psc


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_loot_beam_decompiles_to_intended_papyrus(tmp_path):
    f = tmp_path / "SkylandsLootBeam.pex"
    f.write_bytes(pex.write(scripts.loot_beam()))
    subprocess.run([CHAMPOLLION, str(f), "-p", str(tmp_path / "out")], check=True, timeout=30, capture_output=True)
    psc = "\n".join(line.rstrip() for line in (tmp_path / "out" / "SkylandsLootBeam.psc").read_text().splitlines())
    assert "ScriptName SkylandsLootBeam Extends ObjectReference" in psc
    assert "Activator Property Beam Auto" in psc
    assert "Event OnLoad()\n  If !beamRef as Bool\n    ObjectReference placed = Self.PlaceAtMe(Beam, 1, False, False)" in psc
    assert "Event OnContainerChanged(ObjectReference akNewContainer, ObjectReference akOldContainer)\n  If akNewContainer as Bool\n    Self.ClearBeam()" in psc
    assert "beamRef.Disable(False)\n    beamRef.Delete()\n    beamRef = None" in psc
