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

## Guns in the world (0.8)

Skylands needs no script extender, so its scripts use only what plain Skyrim offers. Every humanoid race (and so
every person and the player) carries one ability whose effect runs the `SkylandsWatcher` script.
* On the player it applies the equipped gun's speed to the player's weapon speed (the speed is a `SkylandsSpeed_n`
  keyword on the gun); every two seconds it looks for guns lying nearby (through a form list of every gun) and the
  quest gives each a rarity-coloured beam (a plain static) and light, which follow the gun and go away when it is
  picked up.
* On everyone else, a few seconds after they load, a hostile humanoid may be handed a gun and ammo and wield it
  (`sheets/generation.json`: arm_chance). When a humanoid dies its gun is dropped on the ground with a beam, or
  sometimes a new gun is (drop_chance). On-screen messages report what the scripts do (verbose in the sheet).

## Respawning enemies (0.8)

Hostile people are noted on the quest's roster - by their own script when they load, and by the player's script,
which every couple of seconds samples the people nearby (Game.FindRandomActor), notes the hostile humanoids and,
for ones that never loaded with the Skylands ability (an old save), gives it to them; the lesser power "Pandora Log
Enemies" does the same sampling in one go for testing. A roster entry holds: their form id (not a reference, which the game
loses when a cell reloads), what they are, and where they stood. When you load a save, a box asks whether to respawn
them (respawn here / not this time / always / never ask); the lesser power "Pandora Respawn" does it at any time and
changes the setting. Respawning looks at the roster entries in your cell (or within a short distance outdoors): a
person still alive is left alone; a dead or missing one is removed and a fresh copy of the same kind is placed where
they stood (and rolls for a gun again). In an interior you are moved back to where you first came in (the quest keeps
an invisible marker at each interior's entrance, set when you arrive).

## Powers on an existing character (0.9.1)

The quest no longer trusts values saved in an old game: the player's watcher hands it the current forms (powers,
messages, beams, ability) every time the game loads, and the quest rebuilds its roster arrays if they are empty.
The Pandora Log message ends with `dup / merged / added` counts so a "0 known" can be traced.

## Form ids stay put (0.9)

A save refers to spells, guns and the quest by form id, so a rebuild must not renumber them. Setup keeps
`work/formids.json` (record type and editor id -> form id) and, before building, also reads the Skylands plugin
already installed to learn its ids; a record that existed before keeps its id, new records get new ones, and ids of
records that no longer exist are never reused. (Before 0.9, inserting a record in the middle shifted every later id,
which is how a power could vanish from a character between versions.)
