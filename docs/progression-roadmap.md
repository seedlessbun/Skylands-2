# Character progression for Skylands guns: plan (phase 1 deliverable)

Status: **WRITTEN, AWAITING THE USER'S APPROVAL. No feature code is built.** Stage 0 (the BL2 survey) is in 0.53.2 / TestBuild-166 (python only, plugin unchanged at 1.29.1).
Written from the code at 0.53.1 and the user's interview answers (section 2). **Confirmed** = read in the code or a log of this project. **Unconfirmed** = my reading or a guess,
with how it will be checked. No Borderlands 2 install is available to this session, so no BL2 numbers are read yet: every number below marked *design* is a placeholder that the
survey report replaces where BL2 has one (the user's rule: BL2 file values replace static values).

## 0. The short version

* **The problem** (the user): "As of now I gain nothing from using our guns." The plugin fires the player's bullets itself (`Projectile::Launch`), so no game action happens and
  Skyrim awards nothing; Skyrim's character level only rises from skill increases.
* **Kill XP (Borderlands style, no skill training):** a kill made with a Skylands gun adds **character XP** straight to Skyrim's level meter, sized by the enemy's level against yours,
  its Badass tier and boss status, with BL2's shape rescaled to Skyrim's level thresholds. Skills are not trained by guns (the user: "skip training skills for now").
* **Weapon proficiencies:** the **damage** a gun deals raises the proficiency of its **type** (6 tracks) and its **manufacturer** (8 tracks). Levels have **no cap** and get slower;
  each level gives 1-2 stat bonuses, **milestone levels** (10, 25, 50, 75, 100, ...) give 3-4 bigger ones, and after each milestone the ordinary per-level bonus shrinks, down to a floor.
  Stats: damage, accuracy, reload speed, fire rate, magazine size, and a **bonus projectile chance** (over 100 % = guaranteed extras plus a chance of one more).
  Every gun gets a **quarter of every manufacturer track's bonuses**, and the **full** bonus of its own maker's track.
* **Shown as** level-up notices and a **HUD line under the ammo display** (held gun's type and maker level, thin progress bars). Saved **per character** (co-save).
* **Later:** the **Legendary** reset (an idea the user jotted down, section 3.6) and **Badass Rank** (BL2's challenge list adapted, rank points, tokens spent "pick one of five",
  **shared across characters** with an ini switch). Planned here, built last.
* **Build order:** 0 survey (sent) -> 1 kill XP -> 2 type proficiencies + their bonuses -> 3 manufacturer tracks, bonus projectiles, HUD line -> 4 Badass Rank counters + shared file ->
  5 tokens and spending -> (6 Legendary, when the user asks). One test build per stage.

## 1. Facts

### 1.1 Skyrim (CommonLibSSE-NG v12.1.0 headers and the game's settings; Confirmed unless marked)
* Character XP lives in `PlayerCharacter::GetPlayerRuntimeData().skills->data` (`PlayerSkills::Data`): `xp` (float), `levelThreshold` (float). Each skill-up adds the new skill level
  (x `fXPPerSkillRank`, 1.0) to `xp`. The threshold for the next level is `fXPLevelUpBase` 75 + `fXPLevelUpMult` 25 x current level (level 10 -> 11 needs 325, level 30 -> 31 needs 825)
  (Skyrim's documented defaults; **unconfirmed** that the user's game has them unchanged: the first stage-1 log line reads `levelThreshold` back).
* What happens when `xp` passes `levelThreshold` without a skill-up is **UNCONFIRMED**: in vanilla the level-up becomes available and is taken in the Skills menu; whether the HUD's
  "Level up" notice and the menu's "level up" state follow a direct write to `xp` is not known. Stage 1 tests it and falls back to its own notice (section 3.1).
* `PlayerCharacter::AddSkillExperience` exists (`PlayerCharacter.h:731`) but is **not used**: guns train no skill (the user's answer).

### 1.2 Skylands (Confirmed in the code at 0.53.1)
* The player's shots: `main.cpp` `TickGun` -> `Launch` (power = `g_damageMult`, the relic damage bonus from `Variable09`; that spell damage follows `LaunchData.power` is
  **unconfirmed**, the user judged it "looked good" in 0.42.0). The gun's numbers come from its keyword (`GunInfo`: clip, interval, reload, spread, burst, element, pellets, ammo, rarity).
* **The gun's type is not in `GunInfo`**, but it can be read: the `_m` token is the gun's ammo item and `SkylandsAmmos_` lists the six ammo items in `STAFF_KINDS` order
  (smg, assault_rifle, pistol, shotgun, sniper, launcher), so ammo index = type. **The manufacturer is not on the gun at all** (only in its name): stage 2 adds it (section 3.7).
* Relic bonuses are GLOBAL actor values the plugin reads every tick: `Variable04` magazine %, `06` fire rate %, `07` reload %, `08` accuracy %, `09` damage % (`docs/relics.md`).
  Proficiency bonuses must be plugin-side multipliers on top, never those values, or relics and proficiencies would overwrite each other.
* Hits: `voices.h` `HitSink` (`TESHitEvent`): `source` is looked up as a `TESObjectWEAP` and `GunOf` gives its element, so for plugin-launched bullets the source is the gun weapon
  (used for voices since 0.46.0; that it is always the gun and never 0 for the player's bullets is **unconfirmed**: stage 1 logs it). `TESHitEvent` carries no damage amount.
* Damage can be measured as max minus current Health (the shield code does it, `shield.h`); a shield is health stacked on health (0.38.1), so damage to a shield shows as a Health
  drop too (BL2 also counts damage to shields).
* Kills: `TESDeathEvent` (`actorDying`, `actorKiller`); sinks in `main.cpp`, `shielditems.h`, `relic.h`, `badass.h`. `badass::TierOf(id)` (0 none .. 3 Ultimate), `badass::ClassOf`
  (person / creature / dragon), `shielditems::IsBoss`. One mudcrab's death event arrived twice in 0.51.0: every sink must count a body once.
* Saving: co-save records through `shield::g_extraSave / g_extraLoad / g_extraRevert`. HUD: `HudFrame` draws the ammo display; anything in Scaleform runs as `AddUITask` inside `Guarded`.
* Settings: `skse.default_ini` / `merge_ini` (`IniVersion`, `...Rev` keys), numbers from `sheets/*.json` (`python tools/gen.py`).

### 1.3 Borderlands 2 (to be read by the stage 0 survey)
* What is known only from memory, **all unconfirmed until the report**: kill XP depends on the enemy's level and grows faster than linearly; enemies far below the player give little;
  Badasses give more; the level curve grows roughly with a power of the level; challenges have 5 levels each with rising goals and rank points; Badass Rank tokens raise one of
  about 14 stats (max health, shield capacity, shield recharge delay and rate, melee damage, grenade damage, gun accuracy, gun damage, fire rate, recoil reduction, reload speed,
  elemental effect chance and damage, critical hit damage) with diminishing returns as more tokens go into the same stat, and the rank is shared by every character of a profile.
* The survey (`Check-BL2-Progress.bat`, `python -m skylands_setup bl2progress`, writes `work\bl2-progress-report.txt`, `setup/skylands_setup/progressprobe.py`) finds everything by
  name, never by a guessed path: P0 name tables (experience / level / challenge / badass rank words), P1 every group whose name says experience / xp / level-up plus `GD_Globals`
  (each object with its properties, then the XP-named ones followed two levels: formulas, initialisations, curves), P2 every group whose name says challenge (one line per object,
  a census, a few in full), P3 badass rank / reward / token objects, P4 `Default__` objects with those words. Packages are opened once each (lesson of 0.45.2).

## 2. Interview answers (the design inputs)

1. **Skills:** none for now. "I'd like to get a feel for a version of XP on enemy kill, and gaining weapon stats through a Weapon Proficiency system."
2. **What earns what:** damage dealt -> the weapon's proficiency; kills -> character XP to the main level. Kill XP **instead of** skill XP.
3. **Pace:** about like vanilla Archery. **Numbers:** survey BL2, then rescale. **Which kills:** only kills with a Skylands gun.
4. **Proficiency tracks:** per type **and** per manufacturer. Every gun gets a quarter of every manufacturer track's bonuses and the full bonus of its own maker.
5. **Stats a level raises:** magazine size, bonus projectiles (shotguns; and a % chance for any gun to fire a second projectile from one bullet: over 100 % gives 2 plus a chance of 3, ...),
   damage, accuracy, reload speed, fire rate.
6. **Levels:** no cap, slowing down. Each level 1-2 stat bonuses; milestone levels (10, 25, 50, ...) larger bonuses to 3-4 stats; every level after a milestone gives less, down to a
   small minimum (e.g. +0.5 % fire rate). For LATER: allow up to level 100, then reset to 0 = "Legendary" like Skyrim: a flat bonus to every stat each time, and the max level +10 for
   the next one.
7. **Display:** level-up notices and a HUD line by the ammo display. **Other XP mods:** none.
8. **Badass Rank (later):** BL2's challenge list adapted; tokens "pick one of five" like BL2; **shared across characters, with a switch**. Proficiencies (and Legendary): **per character**.

## 3. Design (defaults; every number is an ini key and a sheet value in `sheets/progression.json`, `source: bl2` once the report gives it, else `design`)

### 3.1 Kill XP (stage 1)
* **A gun kill:** at `TESDeathEvent`, `actorKiller` is the player AND the dying actor was hit by one of the player's Skylands bullets in the last `KillXPWindow` 3 s (the hit sink keeps,
  per actor, the time, gun type and maker of the player's last gun hit). Counted once per body (60 s, as `CreatureDeathSink`). Not counted: teammates, summoned/commanded actors,
  critters, children, actors that were not hostile to the player at death (no XP for shooting townsfolk; ini `KillXPNonHostile` 0).
* **Size:** `xp = threshold(Lp) / KillXPKillsPerLevel x shape(Le, Lp) x tier x boss x KillXPScale`
  - `threshold(Lp)` = the game's own `levelThreshold` read at the kill (so it follows any change to the level settings).
  - `KillXPKillsPerLevel` 20 (*design*): 20 kills of regular enemies of your own level fill one level, at every level. This is the "about like vanilla Archery" knob: vanilla gives
    a level for roughly 1-2 cleared dungeons of mixed fighting (a rough estimate, unconfirmed); 20 same-level kills is about that. Tunable after the first play test.
  - `shape(Le, Lp)` = BL2's kill XP at enemy level Le divided by BL2's kill XP at the player's level, times BL2's level-difference factor (from the report). **Fallback** (*design*)
    if the report has no usable formula: `clamp(1 + 0.10 x (Le - Lp), 0.1, 2.0)`.
  - `tier` = BL2's Badass XP multipliers (report) else *design* Badass x3, Super x5, Ultimate x10 (about their health multipliers 3 / 5.8 / 15, a bit less); `boss` x5 (`IsBoss`), dragons x5.
  - A creature counts like a person (same formula; its class `drop_scale` is not used for XP).
* **Applying it:** amounts are summed and given at most every 250 ms on the game thread: `data->xp += amount`. If `xp >= levelThreshold` the game should offer the level-up in the
  Skills menu (UNCONFIRMED). Stage 1 logs before/after (`xp`, `levelThreshold`, level) for the first 10 kills, and shows its own notice "Level up! Open the Skills menu" the first time
  `xp` passes the threshold, in case the game shows none. Safety: an amount is clamped to `KillXPMaxShare` 0.5 of a level per kill; nothing is written when `skills` or `data` is null.
* **Notices:** none per kill (the user did not pick "XP on kill"); the level-up notice only. A summary line in the log every 30 s ("kill XP: N kills, X XP given, level a (xp b / c)").

### 3.2 Proficiency points from damage (stage 2)
* **Measured damage:** the hit sink notes every actor the player's gun hits (time, type, maker, its Health then). A 100 ms game-thread pass reads current Health of the noted actors
  (alive or just dead) and books each **drop** to the gun that hit it last within `ProfWindow` 1 s. Healing is ignored (only drops), damage after the window is not booked, a drop
  is capped at `ProfHitCap` 3 x the bullet's nominal damage x pellets (so a follower's big hit at the same moment is not booked to the gun). **Fallback** if Health cannot be read
  (the log says so): the nominal damage of each hit (enchantment magnitude x power).
* **Points = enemies' worth of damage:** points = damage / the target's maximum Health (Badass bonus included), so one enemy's whole health is 1 point whatever its level; a Badass,
  having 3x the health, is worth 3. Damage past death does not count. Per target at most its max Health in total. Both the gun's type track and its maker track get the points.
* **Points needed** for level n -> n+1: `ProfBase` 5 + `ProfStep` 2 x n (*design*): level 1 after 5 enemies' worth, level 10 after 140, level 25 after 725, level 50 after 2,700,
  level 100 after 10,400. No cap.

### 3.3 Proficiency bonuses (stage 2 for types, stage 3 for makers)
* **The six stats** (type tracks): damage %, accuracy % (less spread), reload speed %, fire rate %, magazine %, bonus projectile chance (points of percent).
* **Ordinary levels** give 2 stats, in a fixed rotation so every stat comes up every 3 levels: (damage + accuracy), (reload + fire rate), (magazine + bonus projectiles), ...
  (the user said 1-2: two per level is the default, `ProfStatsPerLevel` 1 or 2).
* **Milestones** `ProfMilestones` = 10, 25, 50, 75, 100, then every 50: 4 stats (the two of the rotation plus the next two), each `ProfMilestoneMult` 3x the current step.
* **Shrinking step:** the step of a stat at a level = max(floor, start x `ProfDecay` 0.75 ^ milestones passed). Starts / floors (*design*): damage 2 % / 0.5 %, accuracy 2 % / 0.5 %,
  reload 2 % / 0.5 %, fire rate 2 % / **0.5 %** (the user's minimum), magazine 3 % / 1 %, bonus projectiles 4 / 1 points of percent.
  Example, fire rate on the SMG track: levels 2, 5, 8 give +2 % each, milestone 10 +6 %, then +1.5 % every third level, milestone 25 +4.5 %, then +1.1 %, ... never below +0.5 %.
  At level 10 the track has about damage +12 %, fire rate +12 %; at level 25 about +22.5 % / +24 % (the exact table is generated by `tools/gen.py` into the sheet and tested).
* **Manufacturer tracks** use the same points and levels but raise only that maker's signature stats (*design*, from BL2's manufacturer styles): Jakobs damage, Maliwan damage
  (elemental guns; the elemental effect chance does not exist in Skylands yet) and accuracy, Dahl accuracy and reload, Vladof fire rate and magazine, Tediore reload and magazine,
  Torgue damage and bonus projectiles, Bandit magazine and fire rate, Hyperion accuracy and damage. A level gives 1 of its two stats (alternating), milestones both at 3x.
* **The user's rule:** every gun gets **25 %** (`ProfOtherMakers` 0.25) of the bonuses of every OTHER maker's track and **100 %** of its own maker's track (default: own = 1.0x,
  not 1.0x + the quarter = 1.25x; question 2 in section 6).
* **Applied in the plugin, per shot, on top of relics:** fire interval / (relic rate x prof rate), reload / (relic x prof), spread / (relic x prof), clip x relic x prof, power x relic x prof
  (damage), extra projectiles. Nothing goes through actor values (no clash with relics, nothing for a load to drop).
* **Bonus projectiles:** chance c (percent): each shot fires floor(c / 100) extra projectiles plus one more with probability (c mod 100) / 100; a shotgun applies it **per pellet**
  (each pellet can split), every other gun per shot; extras use one round (BL2's "consumes 1 ammo"), go in their own random place in the spread and use the same damage.
  Launchers get extra rockets the same way (strong: `ProfLauncherProjectiles` 0.5 halves their chance; say if launchers should get none).

### 3.4 Display (stage 2 notices, stage 3 HUD)
* Notices (`ShowHUDMessage`): "SMG proficiency 4: +2% reload, +2% fire rate", "Jakobs proficiency 10 (milestone): +6% damage, +6% accuracy", "Level up! Open the Skills menu" (3.1).
* HUD line under the ammo display (drawn in `HudFrame`, inside the existing `AddUITask` + `Guarded`): `SMG 12  [====---]   Jakobs 4  [=------]` in small text, the bars = progress to the
  next level; only while a gun is held. Ini `ProfHud` 1. A summary power or menu was not chosen (can come later).

### 3.5 Saving and settings
* Co-save record **'PROF' version 1**, per character: for each of 6 types and 8 makers: level, points into the level, total points, legendary count (0; reserved for 3.6); plus the
  kill XP counters for the log. Revert clears everything (new game = 0). An older save without the record starts at 0.
* Ini block `[Progression]` from `sheets/progression.json`: `KillXP` 1, `KillXPScale` 1.0, `KillXPKillsPerLevel` 20, `KillXPWindow` 3, `KillXPMaxShare` 0.5, `KillXPBadass/Super/Ultimate/Boss`,
  `Prof` 1, `ProfBase` 5, `ProfStep` 2, `ProfStatsPerLevel` 2, `ProfDecay` 0.75, `ProfMilestoneMult` 3, `ProfOtherMakers` 0.25, `ProfHud` 1, the starts/floors, `ProfLog` 1. New keys take
  defaults; the user's values are kept (`merge_ini`).

### 3.6 LATER (jotted down by the user, not built until asked): Legendary proficiencies
* A track can be made Legendary when it reaches its cap: 100 the first time, +10 for each Legendary after (110, 120, ...). Making it Legendary resets the track to level 0 (its level
  bonuses go), and gives a flat bonus to every stat of that track (*design* +2 % each, +5 points bonus projectiles) that stays, so each round ends with higher stats and a longer climb.
  While Legendary is not built, tracks have no cap (the user's answer 6). How it is triggered (a power, a key, a confirm box from the plugin's `MessageBoxData`) is asked then.

### 3.7 The gun's type and maker in the plugin (stage 2)
* Type: from the ammo index (1.2), no record change. Maker: a new keyword `SkylandsMaker_<n>` (8 keywords, 0 Bandit .. 7 Vladof, `manufacturers.json` order) on every gun, records
  appended **last** in `SkylandsGunModels.esp` so no older form id moves (a test asserts it, as for the voice records); `Skylands.esp` is untouched (byte-identical test). The gun's
  numbers keyword itself is not changed (changing its text could split shared keywords and move ids).

### 3.8 Badass Rank (stages 4-5, LATER, after the user has played with 1-3)
* **Challenges:** BL2's list from the report (P2), adapted: kept when Skylands can count it (kills by gun type, by element, by enemy kind, Badass kills by tier, bosses, shields broken
  (`shield.h` break), damage dealt, critical hits once a head-hit test exists, reloads, kills while the shield is down, ...); dropped when it cannot (vehicles, co-op, grenades,
  second wind, Eridium, missions) or replaced by a Skyrim twin (dragons, shouts used with a gun out). Each keeps BL2's 5 levels and rank points if the report has them.
* **Counters** in the plugin from existing events (death, hit, shield break, reload). Rank points -> **tokens** at BL2's thresholds (report), **spent "pick one of five"**: a lesser power
  (one SPEL + MGEF + a tiny script calling a native, appended last in the second plugin) or a hotkey opens a plugin-made message box (`RE::MessageBoxData`, no MESG records needed)
  with five random stats; the pick adds one token to that stat.
* **Stats:** BL2's token list from the report, those Skylands can apply: gun damage, accuracy, fire rate, reload, magazine (via the plugin's multipliers, a 7th layer next to relics
  and proficiencies), max health (Health permanent modifier, tracked), shield capacity / recharge rate / delay (shield.h's bonus inputs), melee damage (`AttackDamageMult`),
  elemental damage, critical damage (when crits exist). BL2's diminishing-returns curve per stat (report; fallback: bonus = 1 % x tokens^0.75).
* **Shared across characters** (the user): a file of our own `Documents\My Games\Skyrim Special Edition\SKSE\SkylandsBadassRank.txt` (next to `SkylandsNative.log`, outside Data so a mod
  manager does not reset it), written on save and on quit; ini `BadassRankShared` 1 (0 = in the co-save, per character). A character loading a shared file gets its bonuses at once.

## 4. Stages (one test build each)

| Stage | What | Where | Main risk |
|---|---|---|---|
| 0 | BL2 survey: XP formulas, level curve, challenges, Badass Rank (`Check-BL2-Progress.bat`) | python, **built: 0.53.2 / TestBuild-166** | class/group names guessed wrong (found by name, so the report says what it found) |
| 1 | Kill XP into character level; hit-source log; gun-kill test | plugin | direct `xp` write does not offer the level-up |
| 2 | Type proficiencies: damage measurement, points, levels, the 6 stats (projectiles excluded), notices, co-save 'PROF' v1, maker keyword records | plugin + python (keywords) | damage booked to the wrong gun; form ids moving |
| 3 | Manufacturer tracks and their quarter/full bonuses, bonus projectiles, HUD line | plugin | extra launches per pellet cost frame time |
| 4 | Badass Rank: challenge counters, rank points, shared file | plugin + python (challenge table) | the shared file across saves of different characters |
| 5 | Tokens: "pick one of five", stats applied | plugin + one power | message box from the plugin on 1.7.104 |
| 6 | Legendary (only when asked) | plugin | - |

After the survey report: the numbers go into `sheets/progression.json` (`source: bl2`), and the report's facts into section 1.3 of this file, before stage 1 is built.

## 5. Risks and what only the game can confirm
* **Writing `xp` directly** (UNCONFIRMED): the level-up may not be offered until the next skill-up, or the HUD may show no notice. Stage 1 logs before/after and shows its own notice;
  if the menu does not offer it, the next try is calling the game's own level-up check (address to be found; not guessed now).
* **Kill attribution:** `actorKiller` may be empty for spell kills or kills by an explosion (rockets, elemental blasts are explosions); the 3 s gun-hit window covers a kill whose
  killer is missing (`KillXPNoKiller` 1 = count it when the player's gun hit it last and nobody else is named). The hit event's `source` for the player's bullets is logged in stage 1.
* **Damage measurement:** a follower's or another enemy's damage within 1 s of the player's hit is booked to the gun (capped, 3.2); regeneration hides a little damage; the shield's
  recharge is a rise, not a drop, so it is ignored. Good enough for a progression meter; stage 2 logs the first 30 booked hits next to their nominal damage.
* **Farming:** points need hostile targets' Health to drop; a pet or a summon the player beats on gives none (not hostile); a creature that keeps regenerating (trolls) gives points
  for damage it heals back. Capped at max Health per target in total.
* **Balance:** compounding bonuses on the type track, the maker track, the other makers' quarters, relics and later tokens; the ini scales each, and stage 2's log prints the
  held gun's total multipliers every time a level changes.
* **Ids:** new records (maker keywords, later the power) go LAST in the second plugin; `Skylands.esp` stays byte-identical (tested). No Papyrus property changes are planned (no ghost scripts).
  Natives keep no String parameters. No lock is taken while holding another (0.43.0). Scaleform only from `AddUITask` inside `Guarded` (0.48.1).
* **Other mods:** none in the user's setup; an XP mod that hooks the same `xp` value would add to ours (ini `KillXP` 0 turns ours off).

## 6. Questions still open for you (defaults in brackets; nothing blocks the survey)
1. Kill XP pace: **20 same-level kills per level** [20]; Badass / Super / Ultimate / boss multipliers [BL2's from the report, else 3 / 5 / 10 / 5].
2. A gun's own maker: full bonus only [yes, 1.0x], or full + the quarter everyone gets (1.25x)?
3. Launchers and the bonus projectile chance: half [0.5], full, or none?
4. Two stats per ordinary level [2] or one?
5. Points needed per level: `5 + 2 x level` enemies' worth of damage [as written]: level 10 after ~140 enemies, 25 after ~725.
