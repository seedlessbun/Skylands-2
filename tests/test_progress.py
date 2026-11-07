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
    assert '#include "progress.h"' in main and "progress::Start(holder)" in main and "progress::Config(key" in main and "progress::g_isGun" in main
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
    assert "const auto weapon = GunFromSource(a_source);" in main.split("progress::g_isGun")[1][:300]
