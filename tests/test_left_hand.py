"""1.37.0: the left-hand toggle (docs/left-hand-roadmap.md stage 1) and the two spell fixes."""

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))

from skylands_setup import skse  # noqa: E402

SRC = HERE.parent / "native" / "skse" / "src"


def _main():
    return (SRC / "main.cpp").read_text(encoding="utf-8")


def test_the_attack_handler_swallows_only_with_a_gun_really_in_hand_and_gives_the_left_button_to_the_game_when_toggled():
    main = _main()
    hook = main[main.index("struct AttackHook"):main.index("static bool Install()", main.index("struct AttackHook"))]
    assert "g_gunMode.load() && g_gunInHand.load()" in hook
    assert "!(left && g_leftHand.load())" in hook
    # a release the game saw go down is passed on, so a spell cast before the gun came out ends
    assert "g_gameSawDown[i].exchange(false)" in hook


def test_the_toggle_ends_aiming_shows_the_left_arm_and_starts_off_after_a_load():
    main = _main()
    assert "g_aimHeld = button->IsPressed() && !g_leftHand.load();" in main
    arm = main[main.index("void HideLeftArm("):main.index("void RestoreGun()")]
    assert "if (g_leftHand.load())" in arm and "RestoreLeftArm();" in arm
    revert = main[main.index("void MagRevert()"):main.index("void WatchPack(")]
    assert "g_leftHand.exchange(false)" in revert
    assert "g_gunInHand = weapon != nullptr;" in main


def test_the_settings_file_carries_the_left_hand_keys():
    ini = skse.default_ini() if hasattr(skse, "default_ini") else ""
    text = ini if isinstance(ini, str) else ""
    src = (HERE.parent / "setup" / "skylands_setup" / "skse.py").read_text(encoding="utf-8")
    for key in ("LeftHand=1", "LeftHandMouse=2", "LeftHandKey=34", "LeftHandRev=2"):
        assert key in src or key in text
    main = _main()
    for key in ('"LeftHand"', '"LeftHandMouse"', '"LeftHandKey"'):
        assert key in main


def test_an_old_settings_file_gets_the_new_left_hand_keys_once():
    old = "IniVersion=X\nLeftHand=1\nLeftHandMouse=2\nLeftHandKey=-1\n"
    default = "IniVersion=X\nLeftHand=1\nLeftHandMouse=2\nLeftHandKey=34\nLeftHandRev=2\n"
    text, kept = skse.merge_ini(default, old)
    assert kept and "LeftHandKey=34" in text
    again, _ = skse.merge_ini(default, text.replace("LeftHandKey=34", "LeftHandKey=20"))
    assert "LeftHandKey=20" in again  # the player's own choice is kept once the rev matches


def test_the_middle_button_is_also_read_from_windows_and_a_gun_never_stays_in_the_left_hand():
    main = _main()
    poll = main[main.index("void PollToggleMouse()"):main.index("void KeepGunsRight(")]
    assert "GetAsyncKeyState(vk)" in poll and "VK_MBUTTON" in poll and "GetCurrentProcessId()" in poll
    keep = main[main.index("void KeepGunsRight("):main.index("void RestoreGun()")]
    assert "if (g_dualGuns)" in keep and "UnequipObject(a_player, left" in keep and "0x00013F43" in keep
    assert "PollToggleMouse();" in main and "KeepGunsRight(player);" in main
    assert '"DualGuns"' in main
