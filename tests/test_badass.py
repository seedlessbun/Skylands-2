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
    assert '#include "badass.h"' in main and "badass::Config(" in main and "badass::Start(holder);" in main and "data.power = badass::GunPower(a_shooter);" in main
    assert "g_extraMaxOf ? g_extraMaxOf(a_actor->GetFormID())" in shield and "shield::g_extraMaxOf = &HealthBonusOf;" in h
    assert "shield::g_extraSave.push_back(&Save);" in h and "shield::g_extraSave.push_back(&Save);" in (SRC / "despawn.h").read_text(encoding="utf-8")
    assert "kVersion = 410" in main and "{ 1, 37, 1, 0 }" in main



def test_badasses_are_named_bigger_and_drop_their_guaranteed_items():
    h = (SRC / "badass.h").read_text(encoding="utf-8")
    ini = skse.default_ini().splitlines()
    for line in ("BadassNames=1", "BadassSize=1", "BadassSize1=1.15", "BadassSize3=1.45", "BadassDrops=1", "BadassDropGun=44.44", "BadassDropShield=20", "BadassDropRelic=8.89"):
        assert line in ini, line
    # the name prefix once (the installer's "Badass ..." bandits keep theirs), the size, the drops 1 / 2 / 3 with BL2's floors
    present = h.split("inline void Present(")[1].split("\n\t}\n")[0]
    assert 'name.find("Badass") == std::string_view::npos' in present and "SetDisplayName(" in present and "SetScale(want)" in present and "own * (g_scale[t]" in present
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
    assert "OpenRecord(kRecord, 3)" in h and "health bonus made permanent" in h  # older saves: the temporary bonus is swapped for a permanent one


def test_each_guaranteed_item_is_shifted_to_its_own_floor():
    h = (SRC / "badass.h").read_text(encoding="utf-8")
    assert "PickDrop(seed, a_p.shift[i], a_p.floor[i], level, rarity, type)" in h and "p.shift[i] = kFloors[t][i] - 1;" in h


def test_creatures_drop_by_their_class_and_dragons_always_drop(tmp_path):
    from skylands_setup import generate
    from skylands_setup.sheet_data import ENEMY_STATS
    path = generate.write_enemy_classes(tmp_path)
    rows = [l.split("\t") for l in path.read_text(encoding="utf-8").splitlines() if l.startswith("class\t")]
    assert len(rows) == len(ENEMY_STATS)
    by_id = {r[1]: r for r in rows}
    assert by_id["dragon"][3] == "dragon" and by_id["critter"][4] == "0" and by_id["wolf"][4] == "0.5" and "(?i)" not in by_id["wolf"][2]
    assert by_id["mammoth"][6] == "no"
    ini = skse.default_ini().splitlines()
    for line in ("CreatureDrops=1", "CreatureDropScale=0.5", "CreatureDropCap=60", "CreatureGunPercent=25", "DragonBoss=1"):
        assert line in ini, line
    h = (SRC / "badass.h").read_text(encoding="utf-8")
    sink = h.split("class CreatureDeathSink")[1].split("\n\t};\n")[0]
    assert "TierOf(actor->GetFormID()) > 0" in sink and 'kind == "critter"' in sink and "IsHostileToActor(player)" in sink
    assert 'kind == "dragon" && g_dragonBoss' in sink and "p.n = 2;" in sink and "PersonChance(level) * scale" in sink
    assert "a_holder->AddEventSink(CreatureDeathSink::Get());" in h and "std::regex::icase" in h and "badass::Start(holder);" in (SRC / "main.cpp").read_text(encoding="utf-8")


def test_creatures_grow_more_and_low_level_ones_get_a_stat_floor():
    ini = skse.default_ini().splitlines()
    for line in ("BadassCreatureSize=0.15", "BadassCreatureHealth=20", "BadassCreatureHealthPerLevel=5", "BadassCreatureGap=0.05", "BadassCreatureGapMax=3"):
        assert line in ini, line
    h = (SRC / "badass.h").read_text(encoding="utf-8")
    present = h.split("inline void Present(")[1].split("\n\t}\n")[0]
    # the reference's own scale is grown from what it was (GetScale includes the race's height: a mudcrab read 0.86 at 1.15 and was set again every pass)
    assert "GetReferenceRuntimeData().refScale" in present and "g_creatureSize * static_cast<float>(t)" in present and "GetScale() <" not in present
    apply = h.split("inline Entry Apply(")[1].split("\n\t}\n")[0]
    assert "g_health[t] * counted - own" in apply and "g_melee[t] * gap - 1.0f" in apply
    assert "a_intfc->ReadRecordData(e.scaleBefore);" in h and "e.scaleBefore = 100;" in h  # older saves set the scale from 100
    sink = h.split("class CreatureDeathSink")[1].split("\n\t};\n")[0]
    assert "one roll per body" in sink


def test_gunless_people_are_likelier_to_carry_a_shield_and_drops_are_tossed():
    ini = skse.default_ini(slot=59, relic_slot=58).splitlines()
    for line in ("EnemyShieldUnarmedPercent=60", "DropToss=1", "DropTossUp=420", "DropTossOut=150", "DropTossRev=2"):
        assert line in ini, line
    items = (SRC / "shielditems.h").read_text(encoding="utf-8")
    assert "const bool armed = HasGun(actor);" in items and "(std::max)(g_enemyPercent, g_unarmedPercent)" in items
    assert "now - first < std::chrono::seconds(3)" in items  # the roll waits for the Hunter script to arm the person
    toss = (SRC / "toss.h").read_text(encoding="utf-8")
    assert "RE::BSWriteLockGuard guard(world->worldLock);" in toss and "SetLinearVelocity" in toss and "GetWorldScale()" in toss
    assert "toss::Toss(actor->RemoveItem(" in items and "toss::Toss(dropped);" in (SRC / "relic.h").read_text(encoding="utf-8")
    assert "toss::Toss(placed.get());" in (SRC / "badass.h").read_text(encoding="utf-8")
    main = (SRC / "main.cpp").read_text(encoding="utf-8")
    assert 'RegisterFunction("TossDrop"sv, "SkylandsNative"sv, TossDrop)' in main and "toss::Config(" in main
    from skylands_setup.skyrim import scripts
    assert "TossDrop" in [f.name for f in scripts.native_stub().functions]


def test_a_stronger_toss_reaches_an_old_settings_file_and_stuck_items_get_a_second_kick():
    new = skse.default_ini(slot=59, relic_slot=58)
    old = new.replace("DropTossRev=2\n", "").replace("DropTossUp=420", "DropTossUp=260").replace("DropTossOut=150", "DropTossOut=90").replace("BadassPercent=", "BadassPercent=7#").replace("7#3", "7")
    merged, kept = skse.merge_ini(new, old)
    assert kept and "DropTossUp=420" in merged and "DropTossOut=150" in merged
    toss = (SRC / "toss.h").read_text(encoding="utf-8")
    assert "moved >= 30.0f || a_w.kicks >= 2" in toss and "a_w.kicks > 0 ? 1.4f : 1.0f" in toss
