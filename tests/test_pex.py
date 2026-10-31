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
  If Self.Waiting()
    Self.RegisterForSingleUpdate(1.5)
    Return
  EndIf
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
    "start": """Function Begin()
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
  If Ticks % 2 == 0
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
    "drop": """  Weapon w = Self.GunHeld()
  If w as Bool
    Me.UnequipItem(w, False, True)
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
    psc = decompile(tmp_path, scripts.staff_gun("SkylandsStaffGun20"), "SkylandsStaffGun20")
    assert "ScriptName SkylandsStaffGun20 Extends ActiveMagicEffect" in psc
    assert "Skipped inoperative" not in psc
    for text in (
            # the plugin knows a staff gun by its keyword (a native with no string parameter) and fires it; the script introduces the gun
            "Int c = SkylandsNative.GunClip(w)", "Return c > 0", "Self.Take(w)", "Self.Load(w)", "Gun = w", "Weapon Gun",
            "SkylandsNative.SetShotSound(Cur)", "SkylandsNative.SetReloadSounds(RelOut, RelIn, RelEnd)", "Cur = ShotSound", "While i < n", "If w.HasKeyword(k)", "Form s = Sounds[i]", "Cur = s",
            "Keyword[] Property SoundKeywords Auto", "Form[] Property Sounds Auto", "Form Property ShotSound Auto",
            "Int v = SKSE.GetPluginVersion(\"SkylandsNative\")", "Native = v > 0", "Weapon Property GiftA Auto", "Form f = GiftA as Form", "f = GiftB as Form",
            "Me.AddItem(f, 1, False)", "Me.GetEquippedObject(1)", "Self.Unknown(w)", "the plugin does not know this staff gun",
            # the plugin keeps the right attack button from the game while a gun is in the hand (no animation); the player's controls stay on
            "SkylandsNative.SetGunMode(True)", "SkylandsNative.SetGunMode(False)", "Me.DrawWeapon()", "Self.Grip()", "Self.Let()", "Self.Heal()",
            "Game.EnablePlayerControls(False, True, False, False, False, False, False, False, 0)", "ControlsOff = False", "If !ControlsOff", "SKSE.GetVersion()",
            # what the plugin reports: the box on the first equip, then every ten shots the numbers, and when a reload starts and ends
            "Int v = SkylandsNative.Magazine()", "String hand = \"NOT the right hand\"", "; the gun is in the ", "; the plugin fires it. ",
            "Int n = SkylandsNative.ShotsFired()", "Int t = n / 10", "If t == Told", "Told = t", "Self.TellIf()", "Self.Tell()",
            "SkylandsNative.RateTenths()", "SkylandsNative.MeasuredTenths()", "SkylandsNative.ReloadMsNow()", "SkylandsNative.SpreadNowTenths()",
            "Staff gun: magazine ", "/s (measured ", "/s), reload ", " s, spread ", " deg", "String Function Tenths(Int n)", "Int tenth = n % 10",
            "Bool r = SkylandsNative.Reloading()", "WasReloading = r", "Staff gun: reloading", "Staff gun: reloaded", "next = 0.25", "Self.Watch()"):
        assert text in psc, text
    # the fire loop is the plugin's now: 0.17.0's script loop (Utility.Wait between shots) fired at about half the rate it was set to
    for text in ("Utility.Wait(gap)", "Utility.Wait(Interval)", "Utility.Wait(rt)", "FireGun", "TriggerHeld", "TriggerPressed", "Boost", "Measured()",
                 "RightItemCharge", "SetItemCharge", "WeaponSpeedMult", "Property BulletSpell", "Property StaffGun", "Property MagSize",
                 "RegisterForAnimationEvent", "OnAnimationEvent", "GetAnimationVariableBool", "UnequipItem", "EquipItem", "Input.", "GetWeaponType",
                 "DisablePlayerControls", "GunStat"):
        assert text not in psc, text


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_native_stub_declares_the_plugins_functions(tmp_path):
    psc = decompile(tmp_path, scripts.native_stub(), "SkylandsNative")
    assert "ScriptName SkylandsNative\n" in psc
    for text in ("Bool Function FireGun(Actor akShooter, Float afRight, Float afUp, Float afForward, Float afSpreadMult) Global Native",
                 "Int Function GunClip(Weapon akWeapon) Global Native", "Int Function GunIntervalMs(Weapon akWeapon) Global Native",
                 "Int Function GunReloadMs(Weapon akWeapon) Global Native", "Int Function GunSpreadTenths(Weapon akWeapon) Global Native",
                 "Int Function Magazine() Global Native", "Int Function ShotsFired() Global Native", "Bool Function Reloading() Global Native", "Int Function RateTenths() Global Native",
                 "Int Function MeasuredTenths() Global Native", "Int Function ReloadMsNow() Global Native", "Int Function SpreadNowTenths() Global Native",
                 "Bool Function SetShotSound(Form akSound) Global Native", "Bool Function TriggerHeld() Global Native",
                 "Bool Function SetGunMode(Bool abOn) Global Native", "Bool Function TriggerPressed() Global Native", "Int Function Version() Global Native",
                 "Bool Function TrackBeam(ObjectReference akGun, ObjectReference akBeam, ObjectReference akLight) Global Native", "Bool Function UntrackBeam(ObjectReference akGun) Global Native",
                 "Int Function ShieldPercent(Actor akActor) Global Native", "Int Function ShieldMax(Actor akActor) Global Native"):
        assert text in psc, text
    assert "String" not in psc and "afSpreadMult" in psc  # no native takes a string: 0.15.1's GunStat(Weapon, String) always read 0 in the game's script
    main = (Path(__file__).resolve().parent.parent / "native" / "skse" / "src" / "main.cpp").read_text(encoding="utf-8")
    for text in ('"FireGun"sv', '"GunClip"sv', '"GunIntervalMs"sv', '"GunReloadMs"sv', '"GunSpreadTenths"sv', '"Magazine"sv', '"ShotsFired"sv', '"Reloading"sv', '"RateTenths"sv', '"MeasuredTenths"sv', '"ReloadMsNow"sv', '"SpreadNowTenths"sv', '"SetShotSound"sv', "BSTempEffectParticle::Spawn", "Variable06", '"SetGunMode"sv', "bool a_on", '"TriggerHeld"sv', '"TriggerPressed"sv',
                 '"Version"sv', "RE::Actor* a_shooter, float a_right, float a_up, float a_forward, float a_spreadMult", "RE::StaticFunctionTag*, RE::TESObjectWEAP* a_weapon)",
                 "TESSpellCastEvent", '"TrackBeam"sv', '"UntrackBeam"sv', "SkylandsGun_", "holder->AddEventSink(CastSink::Get())", "RE::ActorValue::kVariable06", "RE::ActorValue::kVariable07", "RE::ActorValue::kVariable08", "StartPump();", "shield::Register(a_vm)", "shield::StartPump()", "shield::Config("):
        assert text in main, text  # the stub and the plugin's registrations say the same thing
    assert "GunStat" not in main
    shield_h = (Path(__file__).resolve().parent.parent / "native" / "skse" / "src" / "shield.h").read_text(encoding="utf-8")
    for text in ('"ShieldPercent"sv', '"ShieldMax"sv', "ModActorValue", "table[6]", "RE::ActorValue::kHealth", "ACTOR_VALUE_MODIFIER::kDamage", "ACTOR_VALUE_MODIFIER::kTemporary", "AsActorValueOwner", "SetSaveCallback", "SetRevertCallback", "SetLoadCallback", "GetActorValueMax"):
        assert text in shield_h, text  # the stub's two shield functions are registered, and the hook is on slot 6 of the ActorValueOwner table
    hud_h = (Path(__file__).resolve().parent.parent / "native" / "skse" / "src" / "shieldhud.h").read_text(encoding="utf-8")
    for text in ("getBounds", "SkylandsShield", "HUDMovieBaseInstance", "EnemyHealth_mc", "HealthMeterAnim", "GetActiveTarget", "shield::ViewOf", "ShieldHudMode", "ShieldHudEnemy", "ShieldHudX"):
        assert text in hud_h, text  # the shield display reads the game's bars and draws over them
    assert "shieldhud::Frame();" in main and "shield::g_afterUpdate = []()" in main and "shieldhud::Config(" in main
    items_h = (Path(__file__).resolve().parent.parent / "native" / "skse" / "src" / "shielditems.h").read_text(encoding="utf-8")
    for text in ("SkylandsShield_", "GetWornArmor", "EquipObject", "AddObjectToContainer", "TESEquipEvent", "TESDeathEvent", "ShieldSlot", "EnemyShieldPercent", "ShieldDropPercent", "StarterShield", "formEditorID",
                 "GetFormArray<RE::TESObjectARMO>", "shield::Give(", "shield::Remove("):
        assert text in items_h, text  # the plugin finds the shield items by their keywords and follows what is worn in the slot
    assert "shield::g_itemPump = &shielditems::Pump" in main and "shielditems::Config(" in main and "shielditems::EquipSink::Get()" in main
    # 0.39.4: the game drops a temporary Health bonus across a load, so the clean-up looks before it takes one off, the co-save notes the maximum, and a bonus that vanishes is put back
    for text in ("baseMax", "hasBase", "OpenRecord(kRecord, 2)", "version != 1 && version != 2", "lost its shield bonus", "g_nReapplied", "nothing to take off", "g_combatNear", "GameIsPaused", "g_gameNow"):
        assert text in shield_h, text
    assert "Strip(actor, held.first" not in shield_h and "std::pair<float, float>> g_stale" not in shield_h  # the old unconditional strip is gone
    # enemies: creatures get a shield of their own, a person keeps the item's shield while it is in the pack, the pump says what it saw
    for text in ("currentCombatTarget", "g_combatNear = fighting", "InPack(actor, armor)", "living actors within reach", "Follow(actor, armor, false);  // at once"):
        assert text in items_h, text
    # the player's bar fades out when nothing is going on; the combat flag is not the virtual Actor::IsInCombat
    for text in ("ShieldHudHideAfter", "FadeLevel", "shield::g_combatNear.load()", "drawn.alpha *="):
        assert text in hud_h, text
    assert "a_player->IsInCombat()" not in hud_h
    aura_h = (Path(__file__).resolve().parent.parent / "native" / "skse" / "src" / "shieldaura.h").read_text(encoding="utf-8")
    assert "kVersion = 377" in main and "{ 1, 18, 7, 0 }" in main
    assert "shieldaura::Frame();" in main and "shieldaura::Config(" in main and "RecentlyHit" in hud_h and "kDropping" in items_h and "Fx_ShieldBurst" in aura_h


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_retired_script_is_empty(tmp_path):
    psc = decompile(tmp_path, scripts.retired("SkylandsStaffGun"), "SkylandsStaffGun")
    assert "ScriptName SkylandsStaffGun Extends ActiveMagicEffect" in psc and "Function" not in psc and "Event" not in psc


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_the_staff_install_watcher_arms_everyone_seventy_percent_of_the_time_and_hands_out_no_bolts(tmp_path):
    psc = decompile(tmp_path, scripts.watcher(bolts=False, everyone=True, arm_percent=70), "SkylandsHunter")
    eligible = psc.split("Function Eligible()")[1].split("EndFunction")[0]
    assert "IsHostileToActor" not in eligible and "HasKeyword(NpcKeyword)" in eligible, eligible  # any person, not only the player's enemies
    assert "IsChild" in eligible and "Roll(70)" in psc and "Roll(ArmChance)" not in psc  # the saved property is not used: an old save keeps its old value
    assert "Bolts" not in psc.split("Function Equip()")[1].split("EndFunction")[0]
    assert "Roll(ArmChance)" in decompile(tmp_path, scripts.watcher(), "SkylandsHunter")  # the other installs are as they were


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_nothing_of_skylands_starts_until_the_player_has_control_after_the_intro(tmp_path):
    quest = decompile(tmp_path, scripts.class_choice_quest(), "SkylandsHunterQuest")
    waiting = quest.split("Function Waiting()")[1].split("EndFunction")[0]
    assert "Game.IsMovementControlsEnabled()" in waiting and "Self.IntroOver()" in waiting and "Calm >= 3" in waiting and "Begun = True" in waiting  # control on three polls in a row, and the intro over
    over = quest.split("Function IntroOver()")[1].split("EndFunction")[0]
    assert 'Game.GetFormFromFile(210731, "Skyrim.esm")' in over and "q.IsCompleted()" in over and "IsInInterior()" in over and "GetCurrentRealTime()" in over  # Unbound (MQ101), the keep, a fallback
    assert quest.split("Event OnUpdate()")[1].split("Self.Bootstrap()")[0].count("Self.Waiting()") == 1  # before the ability is given
    assert "Function Started()" in quest and "Return Begun" in quest
    watcher = decompile(tmp_path, scripts.watcher(), "SkylandsHunter")
    start = watcher.split("Event OnEffectStart(Actor akTarget, Actor akCaster)")[1].split("EndEvent")[0]
    assert "Self.Go()" in start and "Self.Begin()" in start and "RegisterForSingleUpdate(3.0)" in start
    assert "Owner.Started()" in watcher.split("Function Go()")[1].split("EndFunction")[0] and "Owner.IsRunning()" in watcher
    update = watcher.split("Event OnUpdate()")[1].split("EndEvent")[0]
    assert update.index("If Began") < update.index("Self.Go()") < update.index("Self.Begin()")  # a person or the player begins only once Skylands may
    gunner = decompile(tmp_path, scripts.gunner_quest(), "SkylandsGunnerQuest")
    assert gunner.split("Event OnUpdate()")[1].index("Self.Waiting()") < gunner.split("Event OnUpdate()")[1].index("AddSpell")  # the ability (and the guns) after the intro
    assert "Skylands quest started" not in gunner.split("Event OnInit()")[1].split("EndEvent")[0]


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_a_person_with_a_skylands_gun_keeps_no_other_weapon(tmp_path):
    staff = decompile(tmp_path, scripts.watcher(bolts=False, everyone=True, arm_percent=70), "SkylandsHunter")
    assert "Self.ClearWeapons(f)" in staff.split("Function Equip()")[1].split("EndFunction")[0]  # handed a gun: the others go before it is put in the hand
    assert "Self.NpcEquipped(akBaseObject)" in staff.split("Event OnObjectEquipped")[1].split("EndEvent")[0]  # taking a gun up by any other way too
    clear = staff.split("Function ClearOne(")[1].split("EndFunction")[0]
    assert "t == 41" in clear and "Me.RemoveItem(it, n, True" in clear  # weapons only (form type 41)
    plain = decompile(tmp_path, scripts.watcher(), "SkylandsHunter")
    assert "ClearWeapons" not in plain.split("Function Equip()")[1].split("EndFunction")[0] and "NpcEquipped" not in plain.split("Event OnObjectEquipped")[1].split("EndEvent")[0]


@pytest.mark.skipif(not CHAMPOLLION, reason="set CHAMPOLLION to the Champollion decompiler")
def test_a_dead_person_keeps_no_weapon_and_one_roll_decides_the_drop(tmp_path):
    staff = decompile(tmp_path, scripts.watcher(bolts=False, everyone=True, arm_percent=70), "SkylandsHunter")
    cleanup = staff.split("Function Cleanup(")[1].split("EndFunction")[0]
    assert "Self.GunHeld()" in cleanup and "Self.ClearWeapons(::nonevar)" in cleanup and "Self.DeathDrop(w)" in cleanup  # note the gun, empty the pack of weapons, then one roll
    assert cleanup.index("GunHeld") < cleanup.index("ClearWeapons") < cleanup.index("DeathDrop")
    drop = staff.split("Function DeathDrop(")[1].split("EndFunction")[0]
    assert "Self.Roll(DropChance)" in drop and "Self.WantHeld(w)" in drop and "Self.DropHeld(w)" in drop and "Self.DropRandom()" in drop  # one roll, then the held gun or a random one
    assert "Self.Roll(50)" in staff.split("Function WantHeld(")[1].split("EndFunction")[0]
    assert "Me.PlaceAtMe(f, 1" in staff.split("Function DropHeld(")[1].split("EndFunction")[0]  # the held gun, on the ground
    random = staff.split("Function DropRandom(")[1].split("EndFunction")[0]
    assert "Me.PlaceAtMe(list, 1" in random and "Self.ListFor()" in random  # a random gun from the drop list, on the ground
    assert 'Debug.Trace("Skylands drop:' in staff  # each step says what it did in the Papyrus log
    assert "OwnDrop" not in cleanup and "BonusDrop" not in cleanup  # the old always-drop and the second drop are gone
    clear = staff.split("Function ClearOne(")[1].split("EndFunction")[0]
    assert "If it == keep" in clear and "n -= 1" in clear  # of the kept gun one copy stays
    plain = decompile(tmp_path, scripts.watcher(), "SkylandsHunter")
    assert "Self.OwnDrop()" in plain.split("Function Cleanup(")[1].split("EndFunction")[0]  # the other installs drop as before


def test_the_quest_hands_each_beam_to_the_plugin_and_takes_it_back():
    src = (Path(__file__).resolve().parent.parent / "setup" / "skylands_setup" / "skyrim" / "scripts.py").read_text(encoding="utf-8")
    assert '"TrackBeam"), ("id", "::temp0"), ("id", "r"), ("id", "b"), ("id", "lr")' in src  # Place: the gun, its beam and its light
    assert '"UntrackBeam"), ("id", "::temp0"), ("id", "g")' in src  # Clear: the entry goes when the gun does
