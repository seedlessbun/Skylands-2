# Skylands

**Borderlands 2, played as Skyrim's Dragonborn.** A Borderlands 2 mod (Willow2 Python SDK) that reads
Skyrim Special Edition's real skills, perk trees, races and Unrelenting Force from the player's own Skyrim
install while it runs, and puts them in place of the Borderlands class skills.

## What a player gets (0.1, single player)
- A new game opens with Skyrim's *"Hey, you. You're finally awake."* (read from your Skyrim's strings) and a
  choice of Skyrim's playable races, each with its real starting skill bonuses.
- All 18 Skyrim skills level up from Borderlands play: pistols/SMGs/melee raise One-Handed, crits raise
  Sneak, vending machines raise Speech, chests raise Lockpicking, grenades raise Conjuration, and so on
  (`sheets/xp_sources.json`). Skyrim's own XP multipliers and level formulas drive it.
- Dragonborn level-ups give perk points for Skyrim's real perk trees in a skills menu (K, or the Skills tab).
  Skill level and perks change Borderlands stats (`sheets/effects.json`).
- Class skill trees and the class action skill are sealed. The action skill key (F) shouts **Unrelenting
  Force**: Fus at level 1, Ro at 5, Dah at 10, with Skyrim's cooldowns.
- Progress is stored in each Borderlands character's save.

Requires Borderlands 2 (Windows, Steam) and Skyrim Special Edition. Nothing from either game is shipped.

## How it is built
- `sheets/*.json`: the design, one row per thing. Source of truth.
- `tools/preflight.py`: checks every cell is filled and every cross-sheet reference resolves
  (`--bl2-db` also checks hook names against the OpenBLCMM BL2 data pack). Run before every build.
- `tools/gen.py`: generates `mod/skylands/sheet_data.py` from the sheets.
- `mod/skylands/skyrim/`: readers for Skyrim.esm, BSA v104/v105 (LZ4) and string tables.
- `mod/skylands/progression.py`: Skyrim's progression rules (no game imports).
- `mod/skylands/game.py`: the Borderlands 2 hooks, shout, menus and saving.
- `tools/package.py`: builds `dist/Skylands-<version>.zip` with the Willow2 Mod Manager v3.8 bundled
  (LGPL-3.0, credited in `CREDITS.md`).

```
python tools/preflight.py && python tools/gen.py && python -m pytest tests && python tools/package.py
```

## Status
Built and tested offline: the Skyrim readers against synthetic Skyrim-format files, the progression rules,
and `game.py`'s logic against a stand-in SDK. **Not yet run in the real game**; every sheet cell marked
`in_game: "no"` still has to be seen working there.
