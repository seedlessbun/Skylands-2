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
