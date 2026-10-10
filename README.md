# Skylands

**Skyrim, played as a Borderlands vault hunter.** Version 0.2 (in progress) replaces the Borderlands-hosted
0.1 (still in git history). Skyrim Special Edition is the game you play; a one-time setup on the player's PC
reads their own Borderlands 2 install and builds Skyrim files from it:

- a choice of the six vault hunters at character creation, each with their action skill as a Skyrim power
  (real Borderlands names, text, durations and cooldowns);
- Borderlands guns as Skyrim loot (real parts, manufacturers, names, stats, elements), crossbows underneath
  with a placeholder model, glowing with a beam in Borderlands' own rarity colours;
- Skyrim bandits turned into Pandora's bandit types, with Badass versions.

Nothing from either game is shipped. Single player.

## Layout
- `sheets/`: the design (source of truth); `tools/preflight.py`, `tools/gen.py` check and generate from it.
- `setup/skylands_setup/`: the setup program (pure Python + a small LZO helper).
  - `bl2/`: Borderlands 2 package reader (UE3 packages, LZO via `native/lzo` = lzokay, MIT).
  - `skyrim/`: Skyrim plugin/archive/string readers.
  - `survey.py`: test-round tool that reports what it can read from both installs.
- `tools/package_survey.py`: builds the Windows survey kit (bundled CPython from python-build-standalone).

## Status
Survey tool built and tested on synthetic files. Next: confirm the formats on a real install, then the
Skyrim writers (plugin, scripts, placeholder models) and the setup step Melty runs before first launch.

## Gun stats (0.4)

Each gun gets its own enchantment listing its stats: fire rate (shots per second) and reload (seconds) rolled
inside Borderlands 2-like ranges per gun type (`sheets/gun_types.json`), widening toward the top with rarity
(`sheets/rarities.json`), critical damage, and the element's strength. A gun can roll a rare boost that multiplies
one of fire rate, element or crit damage ("ultra fire rate" uniques). Rolls are seeded by the gun's id, so a rebuild
gives the same guns. The fire rate and reload fold into one animation speed. A script on the player (the class quest, ticking once a
second) reads it from the equipped Skylands gun and sets the player's WeaponSpeedMult; a notification shows the value
and what the game reports back. `generate-report.json` lists every gun's rolled stats.

## Rarity beams (0.5)

Every Skylands gun carries a Skylands keyword and a rarity keyword. The same script scans the player's cell every
other second and places a rarity-coloured beam over Skylands guns lying on the ground and over corpses carrying one;
each beam follows its gun and removes itself when the gun is picked up or looted.
