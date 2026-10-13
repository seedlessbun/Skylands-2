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

## Guns from parts (0.6)

Guns are assembled the way Borderlands 2 does it. A Borderlands balance (say `Pistol_Jakobs_3_Rare`) names the pool
of parts (body, barrel, grip, stock, sight, accessories, material, element) a gun of that make and rarity may be built
from. Setup reads those pools and every part's stat effects (damage, fire interval, reload speed, clip size, spread,
status chance ...) from the player's own Borderlands 2 files, then builds several guns per balance by picking one part
per slot: each gun is a different combination, named from its parts' prefix and title, with stats combined from its
parts and its manufacturer (`sheets/part_stats.json` maps Borderlands attributes to Skylands stats,
`sheets/manufacturers.json` is each maker's character). Parts without a readable effect still nudge stats by a small
fixed amount derived from their name. Nothing of the parts is shown; they only change the stats and the name.

Each gun carries a stats line on its enchantment (fire rate, reload, magazine, crit damage, element strength, the
parts it was built from) and can roll a rare boost on one stat (`sheets/rarities.json`). Fire rate and reload fold into
animation speed: half goes into the weapon's own speed, half into the player's weapon speed, which a script on the
player (the class quest, ticking once a second) reads from the stats effect of the equipped gun.

## Guns in the world (0.7)

Skylands needs no script extender, so its scripts use only what plain Skyrim offers. Every humanoid race (and so
every person and the player) carries one ability whose effect runs the `SkylandsWatcher` script.
* On the player it applies the equipped gun's speed to the player's weapon speed (the speed is a `SkylandsSpeed_n`
  keyword on the gun) and every two seconds looks for guns lying nearby (through a form list of every gun) to give
  them a rarity-coloured beam and light, which follow the gun and go away when it is picked up.
* On everyone else, a few seconds after they load, a hostile humanoid may be handed a gun and ammo and wield it
  (`sheets/generation.json`: arm_chance). When a humanoid dies its gun is dropped on the ground with a beam, or
  sometimes a new gun is (drop_chance). On-screen messages report what the scripts do (verbose in the sheet).
