# MODLOG

## 2026-10-07 - 0.1 build
- Route: Willow2 Mod Manager v3.8 (pyunrealsdk, Python 3.14) Python mod, bundled in the release; Melty has
  no loader for BL2. Skyrim is a companion game read from disk only (no Skyrim mod, no loader there).
- Hook names verified against OpenBLCMM BL2 data pack 2023-04-20 (`tools/preflight.py --bl2-db`).
  Arguments are read by name (the data pack does not keep declaration order).
- Following universal-modder field note "BL3 weapons and movement in Borderlands 2": block-and-recall
  damage in one hook per direction, collect pawns before damaging them, guard PawnList walks, relative
  tolerance when holding attributes, WeakPointer/addresses instead of cached UObjects.
- Melty: recipe valid, one_click_check yes (62 files placed). Launch passes Skyrim's folder as
  SKYLANDS_SKYRIM_DIR (env) and in %LOCALAPPDATA%/Skylands/skylands.env (settings).
- Not verified in game yet. First playtest checklist: unrealsdk.log lines `[Skylands] ... works`
  for skyrim_load, opening, race_chosen, damage_out, skill_up, shout, skills_menu, perk_taken, save_load.
- Open risks: StartActionSkill may not be called before the action skill unlocks (the F keybind covers it);
  AddVelocity knockback strength; money polling also counts mission rewards as Pickpocket.
