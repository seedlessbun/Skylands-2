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
  Self.Bootstrap()
  If !Chosen
    Self.Choose()
    Self.RegisterForSingleUpdate(1.0)
    Return
  EndIf
  If PendingPrompt
    Self.Prompt()
  EndIf
  Return
EndEvent"""

UPGRADE = """  Self.MakeArrays()
  If Chosen
    If Refreshed"""

ADOPT = """  Int st = Self.Stage(a)
  If st < 3
    Return False
  EndIf
  LogHuman += 1
  If st < 4
    Return False
  EndIf
  LogFoes += 1
  Bool fresh = Self.Enlist(a)
  Float v = a.GetActorValue("Variable09")
  If v < 1.0
    a.AddSpell(Ability, False)
  EndIf
  Return fresh"""

LOG = """    Actor a = Game.FindRandomActor(x, y, z, LogRadius)
    If a as Bool
      seen_a += 1
      If Self.Adopt(a)
        count += 1
      EndIf
    EndIf
    i += 1"""

RESPAWN = """  ObjectReference n = player.PlaceAtMe(base, 1, False, False)
  If n as Bool"""

CHOOSE = """    player.EquipShout(chosenShout)
    player.AddSpell(RespawnPower, False)
    player.AddSpell(LogPower, False)
    player.AddItem(StarterGun, 1, False)
    player.AddItem(StarterAmmo, 60, False)
    player.EquipItem(StarterGun, False, False)
    Chosen = True"""



PROMPT = """  PendingPrompt = False
  If Mode == 2
    Return
  EndIf
  If Mode == 1
    Self.Respawn()
    Return
  EndIf
  Int pick = PromptMsg.Show("""

BEAMS = """  If Self.Alive(r)
    Bool hit
    Form base = r.GetBaseObject()
    Int k = 5
    While k >= 0
      Keyword kw = RarityKeywords[k]
      Bool has = base.HasKeyword(kw)
      If has
        hit = True
        Self.Place(r, k)
        k = -1"""

PLACE = """  Form bs = Beams[k]
  ObjectReference b = r.PlaceAtMe(bs, 1, False, False)"""

CLEAR = """  Tracked[i] = None
  TrackedBeams[i] = None
  TrackedLights[i] = None"""

WATCHER = {
    "start": """Event OnEffectStart(Actor akTarget, Actor akCaster)
  Me = akTarget
  Actor player = Game.GetPlayer()
  If Me == player
    IsPlayer = True
    Owner.Refresh(RarityKeywords, Beams, Lights, PromptMsg, SettingsMsg, MarkerForm, RespawnPower, LogPower, Ability, NpcKeyword, ScanRadius, Verbose)
    Owner.Upgrade()
    Weapon w = Me.GetEquippedWeapon(False)
    Self.ApplySpeed(w)
    Self.RegisterForSingleUpdate(0.5)
    Return
  EndIf""",
    "refresh": "Owner.Refresh(RarityKeywords, Beams, Lights, PromptMsg, SettingsMsg, MarkerForm, RespawnPower, LogPower, Ability, NpcKeyword, ScanRadius, Verbose)",
    "tick": """Function PlayerTick()
  Owner.NoteEntrance()
  Ticks += 1
  If Ticks % 4 == 0
    Self.Hand()
    Self.Scan()
    Owner.Sweep()
    Owner.LogAround(4, False)
  EndIf""",
    "flag": """  Float delay = Utility.RandomFloat(1.5, 4.0)""",
    "maintain": """  If !Checked
    Checked = True
    Foe = Self.Eligible()
    If Foe
      Owner.Enlist(Me)
    EndIf
  EndIf""",
    "load": """Event OnPlayerLoadGame()
  If IsPlayer
    Self.Hand()
    Owner.LoadedSave()
  EndIf""",
    "speed": """      Int n = SpeedKeywords.Length
      Int i = 0
      While i < n
        Keyword k = SpeedKeywords[i]
        If w.HasKeyword(k)
          Float f = i as Float""",
    "scan": "Game.FindRandomReferenceOfAnyTypeInList(GunList, x, y, z, ScanRadius)",
    "arm": """  Armed = True
  If Me.IsDead()
    Return
  EndIf
  If Self.Carrying()
    Return
  EndIf""",
    "equip": """    Me.AddItem(f, 1, True)
    g.Disable(False)
    g.Delete()
    Me.AddItem(Bolts, 30, True)""",
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
                 "Form Property StarterAmmo Auto"):
        assert prop in psc
    assert "Property RespawnPower" not in psc and "Function Refresh(" in psc  # those are handed over, not saved properties
    for text in (QUEST_EXPECTED, UPGRADE, ADOPT, LOG, RESPAWN, CHOOSE, PROMPT, BEAMS, PLACE, CLEAR):
        assert text in psc


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_watcher_decompiles_to_intended_papyrus(tmp_path):
    psc = decompile(tmp_path, scripts.watcher(), "SkylandsWatcher")
    assert "ScriptName SkylandsWatcher Extends ActiveMagicEffect" in psc
    for prop in ("SkylandsClassQuest Property Owner Auto", "Keyword[] Property SpeedKeywords Auto", "FormList Property GunList Auto",
                 "Spell Property RespawnPower Auto", "Message Property PromptMsg Auto",
                 "Form Property GunDrop Auto", "Int Property ArmChance Auto", "Float Property ScanRadius Auto"):
        assert prop in psc
    for text in WATCHER.values():
        assert text in psc


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_respawn_power_decompiles_to_intended_papyrus(tmp_path):
    psc = decompile(tmp_path, scripts.respawn_power(), "SkylandsRespawn")
    assert "ScriptName SkylandsRespawn Extends ActiveMagicEffect" in psc and "Owner.Settings()" in psc
    assert "Owner.LogNow()" in psc and "Int Property Action Auto" in psc
