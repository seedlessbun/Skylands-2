"""Character progression, stage 1 (kill XP): the settings block, Borderlands 2's numbers in the sheet, and the plugin's wiring."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "setup"))

from skylands_setup import skse  # noqa: E402
from skylands_setup.sheet_data import PROGRESSION  # noqa: E402

SRC = ROOT / "native" / "skse" / "src"


def test_kill_xp_settings_are_written_with_borderlands_2_multipliers():
    ini = skse.default_ini()
    for line in ("KillXP=1", "KillXPKillsPerLevel=30", "KillXPMaxShare=0.5", "KillXPBadass=3", "KillXPSuper=10", "KillXPUltimate=20", "KillXPBoss=40", "KillXPNonHostile=0"):
        assert f"\n{line}\n" in ini, line
    assert PROGRESSION["KillXPBoss"].source == "bl2" and "XPMultiplier_09_Boss" in PROGRESSION["KillXPBoss"].bl2_object
    assert PROGRESSION["KillXPKillsPerLevel"].source == "design"


def test_plugin_wires_kill_xp_without_strings_or_nested_locks():
    main = (SRC / "main.cpp").read_text(encoding="utf-8")
    prog = (SRC / "progress.h").read_text(encoding="utf-8")
    assert '#include "progress.h"' in main and "progress::Start(holder)" in main and "progress::Config(key" in main and "progress::g_gunFacts" in main
    # Borderlands 2's level-gap table and tier multipliers
    assert "{ 1.0f, 0.9f, 0.7f, 0.4f, 0.15f, 0.05f, 0.01f }" in prog and "{ 1.0f, 1.0f, 1.03f, 1.06f, 1.09f, 1.12f, 1.15f }" in prog
    assert "{ 1.0f, 3.0f, 10.0f, 20.0f }" in prog and "g_boss = 40.0f" in prog
    # the XP goes into the level meter from the game thread; the game's own check is logged
    assert "GetInfoRuntimeData().skills" in prog and "data->xp = before + add" in prog and "CanLevelUp()" in prog and "shield::Queue(" in prog
    # 0.43.0 lesson: badass::TierOf takes its own lock, so it is read before ours
    tier = prog.index("badass::TierOf(actor->GetFormID())")
    assert tier < prog.index("g_hits[actor->GetFormID()] = h")
    assert prog.rfind("std::lock_guard guard(g_lock)", 0, tier) < prog.index("class HitSink")


def test_a_hit_is_traced_from_the_bullet_spell_back_to_its_gun():
    # the 0.54.0 log: every player hit named the gun's ENCHANTMENT (a SkylandsGunModels.esp record) as its source, so a weapon-only lookup found no gun and no kill gave XP
    main = (SRC / "main.cpp").read_text(encoding="utf-8")
    body = main[main.index("RE::TESObjectWEAP* GunFromSource("):main.index("void CollectNamed(")]
    assert "LookupByID<RE::TESObjectWEAP>(a_source)" in body and "formEnchanting->GetFormID()" in body and "baseEffect->GetFormID()" in body
    assert 'HasKeywordString("SkylandsGun")' in body
    assert "const auto weapon = GunFromSource(a_source);" in main.split("voices::g_elementOf")[1][:300]
    assert "const auto weapon = GunFromSource(a_source);" in main.split("progress::g_gunFacts")[1][:300]


def test_proficiencies_are_wired_into_the_hits_the_shots_the_hud_and_the_save():
    main = (SRC / "main.cpp").read_text(encoding="utf-8")
    prog = (SRC / "progress.h").read_text(encoding="utf-8")
    prof = (SRC / "proficiency.h").read_text(encoding="utf-8")
    assert '#include "proficiency.h"' in prog and "prof::Book(" in prog and "prof::NoteDeath(" in prog and "prof::Apply();" in prog and "prof::Start();" in prog
    # only living, hostile, unprotected targets; the bullet's own damage (magnitude x power)
    book = prog[prog.index("prof::g_on && player"):prog.index("prof::Book(")]
    for check in ("IsHostileToActor(player)", "!actor->IsEssential()", "!actor->IsProtected()", "!actor->IsPlayerTeammate()", "!actor->IsSummoned()", "!actor->IsCommandedActor()"):
        assert check in book, check
    assert "facts.magnitude * facts.power, !actor->IsDead()" in prog and "effect->effectItem.magnitude" in main
    # the user's numbers
    for text in ("g_base = 50.0f", "g_step = 15.0f", "g_killGrace = 0.25f", "g_statsPerLevel = 1", "g_otherMakers = 0.25f", "g_ownMaker = 1.0f", "g_launcherProj = 0.5f",
                 "g_floor[kStats] = { 0.5f, 0.5f, 0.5f, 0.5f, 1.0f, 1.0f }", "0x464F5250"):
        assert text in prof, text
    # the bonuses act per shot on top of the relics, and the HUD shows both levels
    assert "prof::BonusFor(g_gun.info.type, g_gun.info.maker, pb)" in main and "* (1.0f + pb[prof::kRate] * 0.01f)" in main and "* (1.0f + pb[prof::kDamage] * 0.01f)" in main
    assert "prof::Extra(g_profProj, count, info.pellets > 1, rng)" in main
    assert 'field("tfProfT"' in main and 'field("tfProfM"' in main and "prof::ViewOf(ptype, pmaker)" in main
    assert 'edid.starts_with("SkylandsMaker_")' in main and "info.type = static_cast<int>(i)" in main


def _gains(maker, n, stats_per_level=1):
    # a Python copy of proficiency.h's Gains with the default numbers, to pin the bonus tables the roadmap shows
    start, floor, mult, decay = [2, 2, 2, 2, 3, 4], [0.5, 0.5, 0.5, 0.5, 1, 1], 3.0, 0.75
    mile = lambda k: k in (10, 25, 50, 75, 100) or (k > 100 and k % 50 == 0)  # noqa: E731
    passed = sum(1 for m in range(1, n) if mile(m))
    step = lambda s: max(floor[s], start[s] * decay ** passed)  # noqa: E731
    out = [0.0] * 6
    if maker is not None:
        pair = [(4, 3), (1, 2), (1, 0), (0, 3), (0, 1), (2, 4), (0, 5), (3, 4)][maker]
        for s in (pair if mile(n) else (pair[(n - 1) % 2],)):
            out[s] += step(s) * (mult if mile(n) else 1)
        return out
    first = ((n - 1) * stats_per_level) % 6
    for i in range(4 if mile(n) else stats_per_level):
        s = (first + i) % 6
        out[s] += step(s) * (mult if mile(n) else 1)
    return out


def test_the_type_track_bonus_table_matches_the_roadmap():
    total = [0.0] * 6
    for n in range(1, 11):
        total = [a + b for a, b in zip(total, _gains(None, n))]
    assert [round(x, 1) for x in total] == [10.0, 4.0, 4.0, 8.0, 12.0, 16.0]
    for n in range(11, 26):
        total = [a + b for a, b in zip(total, _gains(None, n))]
    assert [round(x, 1) for x in total] == [17.5, 11.5, 11.5, 15.5, 18.8, 25.0]
    prof = (SRC / "proficiency.h").read_text(encoding="utf-8")
    assert "{ kMag, kRate }, { kAccuracy, kReload }, { kAccuracy, kDamage }, { kDamage, kRate }" in prof and "{ kDamage, kAccuracy }, { kReload, kMag }, { kDamage, kProj }, { kRate, kMag }" in prof
