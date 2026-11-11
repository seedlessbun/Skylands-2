"""1.38.0: weapon slots (docs/weapon-slots-roadmap.md stage 1)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "native" / "skse" / "src"


def test_slots_are_assigned_with_the_slot_key_and_switched_with_the_wheel():
    main = (SRC / "main.cpp").read_text(encoding="utf-8")
    assert "QueueSlotAssign(static_cast<int>(button->GetIDCode()) - 2);" in main
    assert "QueueSlotSwitch(button->GetIDCode() == 9 ? 1 : -1);" in main
    assign = main[main.index("void SlotAssign(int a_slot)"):main.index("void SlotSwitch(int a_dir)")]
    assert "(already)" in assign  # the same gun on its own slot: left as it is
    switch = main[main.index("void SlotSwitch(int a_dir)"):main.rindex("void QueueSlotAssign(")]
    assert "% 4 + 4) % 4" in switch and "CountOf(player, gun) <= 0" in switch and "g_slots[i] = 0;" in switch
    assert "g_swapUntilMs = now + 600;" in main


def test_the_zoom_and_the_hotkeys_are_swallowed_through_canprocess_slot_1_and_the_slots_are_saved():
    main = (SRC / "main.cpp").read_text(encoding="utf-8")
    assert "ZoomHook<0>::Install(RE::VTABLE_FirstPersonState[1]);" in main and "ZoomHook<1>::Install(RE::VTABLE_ThirdPersonState[1]);" in main
    assert "RE::VTABLE_FavoritesHandler[0]" in main and main.count("write_vfunc(1, Thunk)") == 2
    assert "0x544F4C53" in main and "shield::g_extraSave.push_back(&SlotSave);" in main and "shield::g_extraRevert.push_back(&SlotRevert);" in main
    ini = (ROOT / "setup" / "skylands_setup" / "skse.py").read_text(encoding="utf-8")
    for key in ("WeaponSlots=1", "SlotKey=56", "SlotHookZoom=1", "SlotHookHotkeys=1"):
        assert key in ini


def test_the_wheel_stays_with_the_guns_while_a_swap_takes_the_new_gun_out():
    main = (SRC / "main.cpp").read_text(encoding="utf-8")
    want = main[main.index("bool SlotsWantWheel()\n"):main.index("void SlotAssign(int a_slot)")]
    assert "g_lastSwapMs.load() + g_slotSwapGraceMs" in want
    assert "GetWeaponState() != RE::WEAPON_STATE::kSheathed" in want and "HeldGun(player, info)" in want
    assert "g_gunMode" not in want  # gun mode drops for a moment during a swap
    assert "g_lastSwapMs = NowMs();" in main


def test_the_hud_shows_the_guns_slot_number_before_its_name():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    main = (root / "native/skse/src/main.cpp").read_text()
    assert 'fmt::format("<font size=\\"15\\" color=\\"#D8D8D8\\">[{}]</font> ", slot)' in main
    assert "g_slots[i].load() == g_gun.weapon" in main and "g_slotsOn && g_slotHudNumber" in main
    assert "g_slotNameAgain = true;" in main and "if (g_slotNameAgain.exchange(false))" in main and 'key == "SlotHudNumber"' in main
    assert "SlotHudNumber=1" in (root / "setup/skylands_setup/skse.py").read_text()
