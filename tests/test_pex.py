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

UPGRADE = """Function Upgrade()
  Self.MakeArrays()
  Return"""

ADOPT = """  Int st = Self.Stage(a)
  If st < 3
    Return False
  EndIf
  LogHuman += 1
  If st < 4
    Return False
  EndIf
  LogFoes += 1
  LogStep = 10
  Bool fresh = Self.Remember(a)
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
    Self.Wake()
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
    Self.Scan()
    Owner.Sweep()
    Self.Rare()
  EndIf""",
    "flag": """  Float delay = Utility.RandomFloat(1.5, 4.0)""",
    "maintain": """  If !Checked
    Checked = True
    Foe = Self.Eligible()
    If Foe
      Owner.Remember(Me)
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
    psc = decompile(tmp_path, scripts.class_choice_quest(), "SkylandsHunterQuest")
    assert "ScriptName SkylandsHunterQuest Extends Quest" in psc
    for prop in ("Message Property ClassChoice Auto", "Shout[] Property Shouts Auto", "Form Property StarterGun Auto",
                 "Form Property StarterAmmo Auto"):
        assert prop in psc
    assert "Property RespawnPower" not in psc and "Function Refresh(" in psc  # those are handed over, not saved properties
    for text in (QUEST_EXPECTED, UPGRADE, ADOPT, LOG, RESPAWN, CHOOSE, PROMPT, BEAMS, PLACE, CLEAR):
        assert text in psc


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_watcher_decompiles_to_intended_papyrus(tmp_path):
    psc = decompile(tmp_path, scripts.watcher(), "SkylandsHunter")
    assert "ScriptName SkylandsHunter Extends ActiveMagicEffect" in psc
    for prop in ("SkylandsHunterQuest Property Owner Auto", "Keyword[] Property SpeedKeywords Auto", "FormList Property GunList Auto",
                 "Spell Property RespawnPower Auto", "Message Property PromptMsg Auto",
                 "Form Property GunDrop Auto", "Int Property ArmChance Auto", "Float Property ScanRadius Auto"):
        assert prop in psc
    for text in WATCHER.values():
        assert text in psc


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_respawn_power_decompiles_to_intended_papyrus(tmp_path):
    psc = decompile(tmp_path, scripts.respawn_power(), "SkylandsHunterPower")
    assert "ScriptName SkylandsHunterPower Extends ActiveMagicEffect" in psc and "Owner.Settings()" in psc
    assert "Owner.LogNow()" in psc and "Int Property Action Auto" in psc


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_gunner_scripts_decompile(tmp_path):
    psc = decompile(tmp_path, scripts.gunner(), "SkylandsGunner")
    assert "ScriptName SkylandsGunner Extends ActiveMagicEffect" in psc
    for text in ("Event OnPlayerBowShot(Weapon akWeapon, Ammo akAmmo, Float afPower, Bool abSunGazing)", "Gun.Fire(Aim, Rnd)",
                 "Aim.SetAngle(x, 0.0, h)", "Aim.MoveTo(Me, ox, oy, oz, False)", "Me.UnequipItem(RndF, False, True)", "Utility.Wait(t)", "Mag = MagSize",
                 "Me.EquipItem(RndF, False, True)", "Int[] Property Pellets Auto", "Float[] Property Spread Auto"):
        assert text in psc, text
    (tmp_path / "q").mkdir()
    q = decompile(tmp_path / "q", scripts.gunner_quest(), "SkylandsGunnerQuest")
    assert "player.AddSpell(Ability, False)" in q and "Spell Property Ability Auto" in q
    assert "player.HasSpell(Ability as Form)" in q or "Form f = Ability as Form" in q
    assert "Skylands quest started" in q and "Skylands: ability added" in q


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_staff_gun_script_decompiles_to_the_intended_logic(tmp_path):
    psc = decompile(tmp_path, scripts.staff_gun("SkylandsStaffGun18"), "SkylandsStaffGun18")
    assert "ScriptName SkylandsStaffGun18 Extends ActiveMagicEffect" in psc
    assert "Skipped inoperative" not in psc
    for text in (
            # SKSE: the plugin of Skylands (the attack button, the gun's numbers, the bullet launch) and SKSE's own charge and version calls
            "SkylandsNative.TriggerPressed()", "SkylandsNative.TriggerHeld()", "SkylandsNative.FireGun(Me, OffsetRight, OffsetUp, OffsetForward)",
            "SkylandsNative.GunStat(w, \"clip\")", "SkylandsNative.GunStat(w, \"interval\")", "SkylandsNative.GunStat(w, \"reload\")",
            "Int v = SKSE.GetPluginVersion(\"SkylandsNative\")", "Native = v > 0", "WornObject.SetItemCharge(Me, 1, 0, v)", "WornObject.GetItemCharge(Me, 1, 0)", "Me.SetActorValue(\"RightItemCharge\", v)",
            # the plugin keeps the right attack button from the game while a gun is in the hand (no animation); the player's controls stay on
            "SkylandsNative.SetGunMode(True)", "SkylandsNative.SetGunMode(False)", "Me.DrawWeapon()", "Self.Grip()", "Self.Let()", "Self.Heal()",
            "Game.EnablePlayerControls(False, True, False, False, False, False, False, False, 0)", "ControlsOff = False", "If !ControlsOff",
            "SKSE.GetVersion()",
            # one script for every gun: whichever staff gun is put on is the Gun, a different one starts with a full magazine, the same one keeps its rounds
            "Float c = SkylandsNative.GunStat(w, \"clip\")", "Return c > 0.0", "Self.Take(w)", "Self.Load(w)", "Self.Fresh(w)", "If w == Gun", "Gun = w",
            "Interval = i", "ReloadTime = r", "MagSize = n", "Mag = n", "Weapon Gun",
            # the loop: a press fires at once, the button held fires one every Interval, nothing while reloading or with the gun away
            "Bool pressed = SkylandsNative.TriggerPressed()", "Bool go = Self.Pull()", "While go", "Utility.Wait(Interval)",
            "go = SkylandsNative.TriggerHeld() && Self.Pull()", "Bool more = Mag > 1", "Return Armed && !Reloading",
            # the magazine, the gauge, the reload (a delay with the gauge empty, then full) and the messages
            "Mag -= 1", "Int r = Fired % 10", "If r == 0 && Verbose", "v *= ChargePerShot", "Utility.Wait(ReloadTime)", "Mag = MagSize",
            "Staff gun: reloading", "Staff gun: reloaded", "Me.AddItem(f, 1, False)", "Form f = GiftA as Form", "f = GiftB as Form",
            "Me.GetEquippedObject(1)", "Me.SetActorValue(\"WeaponSpeedMult\", SpeedMult)", "Me.SetActorValue(\"WeaponSpeedMult\", 1.0)",
            "ObjectReference ref = Me as ObjectReference", "ShotSound.Play(ref)",
            "Me.SetActorValue(\"LeftItemCharge\", v)", "Self.Unknown(w)", "the plugin does not know this staff gun", "; the gun is in the ", "Weapon Property GiftA Auto", "Float Property ChargePerShot Auto", "Sound Property ShotSound Auto", "Float Property OffsetForward Auto"):
        assert text in psc, text
    # what the old single-gun script kept in properties is the plugin's now; the workarounds of plain Papyrus are gone
    assert "DisablePlayerControls" not in psc  # 0.14.3 switched the fighting controls off; the plugin swallows the attack button instead
    for text in ("Property BulletSpell", "Property StaffGun", "Property MagSize", "Property Interval", "Property ReloadTime", "Property Spread",
                 "FireBullet", "RegisterForAnimationEvent", "OnAnimationEvent", "GetAnimationVariableBool", "Aim", "UnequipItem", "EquipItem",
                 "Input.", "GetWeaponType", "Burst", "Fill"):
        assert text not in psc, text


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_retired_script_is_empty(tmp_path):
    psc = decompile(tmp_path, scripts.retired("SkylandsStaffGun"), "SkylandsStaffGun")
    assert "ScriptName SkylandsStaffGun Extends ActiveMagicEffect" in psc and "Function" not in psc and "Event" not in psc
