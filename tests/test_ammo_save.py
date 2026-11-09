"""0.60.2: the magazines are kept in the co-save, and the enemy shield bar only shows hostiles."""

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "native" / "skse" / "src"


def test_magazines_and_first_stock_go_through_the_co_save_and_a_load_forgets_the_old_game():
    main = (SRC / "main.cpp").read_text(encoding="utf-8")
    assert "0x47414D53" in main  # 'SMAG'
    for fn in ("MagSave", "MagLoad", "MagRevert"):
        assert f"shield::g_extraSave.push_back(&MagSave)" in main and fn in main
    assert "shield::g_extraLoad.push_back(&MagLoad)" in main and "shield::g_extraRevert.push_back(&MagRevert)" in main
    revert = main[main.index("void MagRevert()"):main.index("void WatchPack(")]
    for reset in ("g_gun.mags.clear()", "g_gun.weapon = 0", "g_gun.reloading = false", "g_startGiven.clear()"):
        assert reset in revert
    # the first stock is once per character, no longer a static map that lives as long as Skyrim runs
    assert "static std::unordered_map<RE::FormID, bool> given" not in main
    assert "g_startGiven.insert(g_gun.ammo->GetFormID()).second" in main
    assert "WatchPack(player, now);" in main


def test_the_enemy_shield_bar_is_only_about_a_hostile_and_does_not_stick():
    hud = (SRC / "shieldhud.h").read_text(encoding="utf-8")
    enemy = hud[hud.index("inline RE::Actor* EnemyActor("):hud.index("// Game thread, at the end of every shield update")]
    assert "HostileTo(actor, a_player)" in enemy
    assert 'Choose(0, "a hostile with no shield in the crosshair"' in enemy
    assert 'Choose(0, "dead, gone or no longer hostile"' in enemy
    assert "kKeepS" in enemy
