"""Badass enemies, stage 1 (plugin 1.25.0): tiers and stats (docs/badass-roadmap.md 3.1, 3.2, 3.6)."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))

from skylands_setup import skse  # noqa: E402
from skylands_setup.sheet_data import BADASS_TIERS  # noqa: E402

SRC = HERE.parent / "native" / "skse" / "src"


def test_the_settings_carry_the_sheets_numbers():
    ini = skse.default_ini()
    b, s, u = BADASS_TIERS["badass"], BADASS_TIERS["super"], BADASS_TIERS["ultimate"]
    for line in ("Badass=1", "BadassPercent=3", "BadassPerLevel=0.5", "BadassMax=25", "BadassSuperGate=12", "BadassUltimateGate=25", "BadassTest=0",
                 "BadassHealth1=3", "BadassHealth2=5.8", "BadassHealth3=15", "BadassMelee1=2.28", "BadassMelee3=2.6", "BadassGun=1.14", "BadassMaxNear=4"):
        assert line in ini.splitlines(), line
    assert (b.health_mult, s.health_mult, u.health_mult) == (3.0, 5.8, 15.0)


def test_the_plugin_rolls_tiers_and_applies_the_stats():
    h = (SRC / "badass.h").read_text(encoding="utf-8")
    main = (SRC / "main.cpp").read_text(encoding="utf-8")
    shield = (SRC / "shield.h").read_text(encoding="utf-8")
    # the roll: p, then a reroll of p for Super from the gate, then again for Ultimate; stable per form id
    roll = h.split("inline int Roll(")[1].split("\n\t}\n")[0]
    assert roll.count("draw(") == 3 and "g_gate[2]" in roll and "g_gate[3]" in roll and "shielditems::Mix(a_id" in roll
    for av in ("kHealth", "kAttackDamageMult", "kSpeedMult"):
        assert f"RE::ActorValue::{av}, a_entry." in h, av
    assert "ACTOR_VALUE_MODIFIER::kTemporary" in h and "0x53414442" in h  # tracked temporary modifiers, co-save 'BDAS'
    assert "IsPlayerTeammate()" in h and "IsCommandedActor()" in h and "IsHostileToActor(a_player)" in h and "IsChild()" in h
    # wiring: settings, start, the guns of a Badass, the shield sized without the bonus, co-save hooks shared with despawn
    assert '#include "badass.h"' in main and "badass::Config(" in main and "badass::Start();" in main and "data.power = badass::GunPower(a_shooter);" in main
    assert "g_extraMaxOf ? g_extraMaxOf(a_actor->GetFormID())" in shield and "shield::g_extraMaxOf = &HealthBonusOf;" in h
    assert "shield::g_extraSave.push_back(&Save);" in h and "shield::g_extraSave.push_back(&Save);" in (SRC / "despawn.h").read_text(encoding="utf-8")
    assert "kVersion = 391" in main and "{ 1, 26, 1, 0 }" in main



def test_badasses_are_named_bigger_and_drop_their_guaranteed_items():
    h = (SRC / "badass.h").read_text(encoding="utf-8")
    ini = skse.default_ini().splitlines()
    for line in ("BadassNames=1", "BadassSize=1", "BadassSize1=1.15", "BadassSize3=1.45", "BadassDrops=1", "BadassDropGun=44.44", "BadassDropShield=20", "BadassDropRelic=8.89"):
        assert line in ini, line
    # the name prefix once (the installer's "Badass ..." bandits keep theirs), the size, the drops 1 / 2 / 3 with BL2's floors
    present = h.split("inline void Present(")[1].split("\n\t}\n")[0]
    assert 'name.find("Badass") == std::string_view::npos' in present and "SetDisplayName(" in present and "SetScale(g_scale[t])" in present
    assert "kFloors[4][3] = { { 0, 0, 0 }, { 2, 0, 0 }, { 3, 2, 0 }, { 4, 3, 2 } }" in h
    pick = h.split("inline RE::TESBoundObject* PickDrop(")[1].split("\n\t}\n")[0]
    assert "const int below = r - a_tier;" in pick and "shielditems::kWeight[below]" in pick  # "up n": rarity r takes the weight of r - n
    assert "PlaceObjectAtMe(item, false)" in h and "std::chrono::milliseconds(1600)" in h


def test_the_health_bonus_is_permanent_so_the_enemy_bar_shows_it():
    h = (SRC / "badass.h").read_text(encoding="utf-8")
    apply = h.split("inline Entry Apply(")[1].split("\n\t}\n")[0]
    assert "Mod(a_actor, RE::ActorValue::kHealth, a_entry.health, RE::ACTOR_VALUE_MODIFIER::kPermanent);" in apply
    strip = h.split("inline void Strip(")[1].split("\n\t}\n")[0]
    assert "a_entry.tempHealth ? RE::ACTOR_VALUE_MODIFIER::kTemporary : RE::ACTOR_VALUE_MODIFIER::kPermanent" in strip
    assert "OpenRecord(kRecord, 2)" in h and "health bonus made permanent" in h  # older saves: the temporary bonus is swapped for a permanent one
