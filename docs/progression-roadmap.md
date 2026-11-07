# Character progression for Skylands guns: plan (phase 1 deliverable)

Status: **REVISED after the user's third round (section 2, item 11) and the survey report (section 1.3). No feature code is built.** The deep survey (0.53.3, TestBuild-167) is READ (1.3b). New game: section 3.9. Stage 0 (the BL2 survey) is in 0.53.2 / TestBuild-166 (python only, plugin unchanged at 1.29.1).
Written from the code at 0.53.1 and the user's interview answers (section 2). **Confirmed** = read in the code or a log of this project. **Unconfirmed** = my reading or a guess,
with how it will be checked. No Borderlands 2 install is available to this session, so no BL2 numbers are read yet: every number below marked *design* is a placeholder that the
survey report replaces where BL2 has one (the user's rule: BL2 file values replace static values).

## 0. The short version

* **The problem** (the user): "As of now I gain nothing from using our guns." The plugin fires the player's bullets itself (`Projectile::Launch`), so no game action happens and
  Skyrim awards nothing; Skyrim's character level only rises from skill increases.
* **Kill XP (Borderlands style, no skill training):** a kill made with a Skylands gun adds **character XP** straight to Skyrim's level meter, sized by the enemy's level against yours,
  its Badass tier and boss status, with BL2's shape rescaled to Skyrim's level thresholds. Skills are not trained by guns (the user: "skip training skills for now").
* **Weapon proficiencies:** the **damage** a gun's bullets deal (each bullet's own damage, overkill and damage to shields included) x 0.1 is XP for its **type** track (6) and its
  **manufacturer** track (8). Levels have **no cap** and get slower (level n -> n+1 costs 20 + 10 x n XP); each level gives 1 stat bonus, **milestone levels** (10, 25, 50, 75, 100, ...) give 3-4 bigger ones, and after each milestone the ordinary per-level bonus shrinks, down to a floor.
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

### 1.3 Borderlands 2 (READ: the user's `bl2-progress-report.txt` of TestBuild-166, 4,248 lines, every section ran; the file is on the user's PC only, so the facts are here)
* **Kill XP** (`GD_Balance_Experience.Formulas.Init_BaseEnemyExperience`): `10 x enemy level + 4`, at least 10 (`Multiplier` = `Init_EnemyExperience_PerPlaythrough`: 10 in normal mode,
  11 in True Vault Hunter Mode; `Level` = the pawn's `ExpLevel`; `Power` 1, `Offset` 4; `RangeRestriction.MinValue` 10). So a level 10 enemy gives 104 XP, a level 30 one 304.
* **Level curve** (`Init_ExperienceRequiredForLevel`): `60 x level ^ 2.8 + 7.33` (the total XP to reach a level, read as cumulative: unconfirmed, the deep survey's `Globals.ExpPointsRequiredForLevel`
  says). Between levels 10 and 11 that is ~11,700 XP = ~112 kills of level-10 enemies; BL2's max level is 50 (`Default__GlobalsDefinition.ExpMaxPlayerLevel`, 72 with the DLC packs: not read).
* **Per enemy type and tier:** `GD_AI_Balance.XP.XPMultiplier_01_Chump`, `02_Normal`, `03_NormalHigh`, `04_Tough`, `05_ToughHigh`, `06_Badass`, `07_SuperBadass`, `08_UltimateBadass`, `09_Boss`
  exist; their numbers sit in a 4-part `ValueFormula` the first survey only summarised -> **deep survey**. Also not yet read: `GD_Globals.General.Globals` `ExpScaleByLevelDifference[6]`
  (how XP falls/rises with the level gap), `ExpAwardWeights[4]`, `BaseEnemyExperienceFormula`; `Default__WillowPlayerController.ExpScaleForCriticalHitKills` (crit kills give more).
* **Challenges** (`ChallengeDefinition`, 365 objects; base game list `GD_Challenges.ChallengeList.List` with 227): categories General Combat, Melee, Pistol, Shotgun, SMG, Assault Rifle, Sniper
  Rifle, Rocket Launcher, Shields, Grenades, Health and Recovery, Vehicle, Money and Trading, Loot, Elemental, Enemies (+ one per DLC). Usable ones by name (base game): per gun type "Kill enemies with
  <type>" (Hail of Bullets, Aggravated Assault, The Killer, Shotgun!, Longshot, Rocket and Roll), "Get critical hits with <type>" and "... critical hit kills", shotgun point-blank / long range,
  sniper from the hip / unaware / one-shot shielded, launcher direct hit / splash / long range / one-shot shielded, pistol quick-draw, AR crouched; Knee-Deep in Brass (rounds fired), Critical
  Acclaim (crit kills), day / night kills; elemental kills and status damage (fire, corrosive, shock, slag, explosive); shield kills (nova, spike, amp, roid, absorb); melee kills; loot (chests,
  lootables, weapons picked up, items by rarity white..orange); Heal Plz (health recovered); enemy kinds (bruisers, marauders, nomads, psychos, goliaths, midgets, skags, spiderants, rats,
  stalkers, threshers, varkids, ...). Each has `Levels[5]` (goals and rewards in a struct array the first survey did not open -> **deep survey**). Level/map challenges give a fixed
  `BPReward` = 1 / 5 / 10 / 25 points x `Init_BadassPointsReward`; `Default__ChallengeDefinition.BPReward` 20.
* **Badass Rank rewards** (`BadassRewardDefinition`, exactly 14, `GD_Challenges.BadassRewards.BARD_*`): Critical Hit Damage, Grenade Damage, Gun Accuracy, Gun Damage, Gun Fire Rate, Gun Recoil
  Reduction, Gun Reload Speed, Max Health, Melee Damage, Shield Capacity, Shield Recharge Delay, Shield Recharge Rate, Elemental Effect Damage, Elemental Effect Chance. Each value comes from
  `GD_Challenges.BadassSkill.Init_BadassBonusCalc_<stat>` (the diminishing curve: **deep survey**). The UI strings confirm "BADASS RANK", "Badass Tokens:", "Redeem Token!", "CHOOSE A REWARD!",
  and "BONUS STATS" can be switched off. How many rank points make a token is not in the report (**deep survey**: the `BadassSkill` group and the player controller defaults).
* The survey itself: `progressprobe.py` (`Check-BL2-Progress.bat`, `python -m skylands_setup bl2progress`), all by name; `--deep` (0.53.3, `Check-BL2-Progress-Deep.bat`, writes
  `work\bl2-progress-deep-report.txt`) dumps the objects named above in full, by the paths THIS report gave.

### 1.3b The deep survey (READ: the user's `bl2-progress-deep-report.txt` of TestBuild-167, 19,588 lines, every section ran)
* **XP multiplier per enemy kind** (`GD_AI_Balance.XP.XPMultiplier_*`, `Multiplier` constant, Level 1, Power 1): Chump 0.5, Normal 0.75, NormalHigh 1.0, Tough 1.25, ToughHigh 1.5,
  **Badass 3, Super Badass 10, Ultimate Badass 20, Boss 40**. Skylands reads them against NormalHigh = 1.0 (an ordinary Skyrim enemy).
* **XP by level difference** (`Globals.ExpScaleByLevelDifference`): enemy ABOVE the player by 1..6+ levels x1.00 / 1.03 / 1.06 / 1.09 / 1.12 / 1.15; BELOW by 1..6+ levels
  x0.90 / 0.70 / 0.40 / 0.15 / 0.05 / 0.01. (Party weights `ExpAwardWeights` are co-op only: 1 player = x1.0.)
* **Badass Rank:** a challenge level gives `Init_BadassPointsReward` (5) x the level's scale (SMG Kills: 1, 5, 10, 50, 100 for its five levels = 5 / 25 / 50 / 250 / 500 points);
  the rank needed for the Nth token is `N ^ 1.8` (`Init_BadassRanksRequiredForToken`; the unit of "rank" against points is not proven); each token stat is `1.0 x tokens ^ 0.75`
  (`Att_BadassBonusBase` 1.0, `Att_BadassBonusDiminisher` 0.75, all 14 `Init_BadassBonusCalc_*` alike) x 1 % (`BadassSkill` "Badassitude", `MT_Scale` 0.01; negative for the stats where
  smaller is better: shield delay, accuracy spread, fire interval, recoil, reload time). So 1 token = +1 %, 10 tokens = +5.6 %, 50 tokens = +18.8 %, 100 tokens = +31.6 %.
* **Not read yet:** each challenge level's GOAL (the count): it sits in `<challenge>:ChallengeConditionDefinition_<n>` sub-objects that the deep pass did not print. Needed only for the
  Badass Rank stage; a small third pass then.

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
9. **Second round:** pace **30** same-level kills per level; a gun's own maker gives its **full bonus only** (1.0x, no extra quarter); launchers get **half** the bonus
   projectile chance; **1 stat per ordinary level**.
10. **Proficiency XP rule (replaces "enemies' worth")**: raw damage goes into the pool: every hit of a Skylands gun's bullet on a hostile enemy, per pellet, at the bullet's own damage
   (enchantment magnitude x launch power, so relic and proficiency damage bonuses count; damage to shields counts), **no cap per enemy or per hit, overkill and damage after death count**;
   XP = damage x `ProfXPScale` 0.1 to both the type and the maker track; level n -> n+1 costs `ProfBase` 20 + `ProfStep` 10 x n; no scaling by player level (later guns fill it faster:
   intended); nothing from essential/protected NPCs, followers/teammates, summoned/commanded actors or anything not hostile to the player; added a few times a second; the first 30 hits logged.
   Rocket and elemental splash damage later, at the blast's own damage. Character level: kill XP (3.1) stays (my pick of the two options offered; the damage-to-character-XP option is dropped).
11. **Third round:** `ProfBase` **50**, `ProfStep` **15**; **dead bodies give no proficiency XP** (only living people and creatures; this replaces "damage after death counts"); character XP
   stays on kill; Badass enemies give the same XP per damage as anyone (their extra health already means more damage).

## 3. Design (defaults; every number is an ini key and a sheet value in `sheets/progression.json`, `source: bl2` once the report gives it, else `design`)

### 3.1 Kill XP (stage 1)
* **A gun kill:** at `TESDeathEvent`, `actorKiller` is the player AND the dying actor was hit by one of the player's Skylands bullets in the last `KillXPWindow` 3 s (the hit sink keeps,
  per actor, the time, gun type and maker of the player's last gun hit). Counted once per body (60 s, as `CreatureDeathSink`). Not counted: teammates, summoned/commanded actors,
  critters, children, actors that were not hostile to the player at death (no XP for shooting townsfolk; ini `KillXPNonHostile` 0).
* **Size:** `xp = threshold(Lp) / KillXPKillsPerLevel x shape(Le, Lp) x tier x boss x KillXPScale`
  - `threshold(Lp)` = the game's own `levelThreshold` read at the kill (so it follows any change to the level settings).
  - `KillXPKillsPerLevel` **30** (the user's pick): 30 kills of regular enemies of your own level fill one level, at every level (vanilla skills keep adding their own XP on top).
    Tunable after the first play test.
  - `shape(Le, Lp)` = BL2's kill XP at the enemy's level over BL2's kill XP at the player's level, `(10 x Le + 4) / (10 x Lp + 4)` (**bl2**, 1.3), times BL2's level-difference
    factor (**bl2**, 1.3b): above x1.00..1.15, below x0.90 / 0.70 / 0.40 / 0.15 / 0.05 / 0.01 (6+ levels below: 1 %).
  - `tier` (**bl2**, 1.3b): Badass x3, Super Badass x10, Ultimate Badass x20; `boss` x40 (`IsBoss`; dragons count as bosses). With `KillXPMaxShare` 0.5 a boss or Ultimate gives at most
    half a level.
  - A creature counts like a person (same formula; its class `drop_scale` is not used for XP).
* **Applying it:** amounts are summed and given at most every 250 ms on the game thread: `data->xp += amount`. If `xp >= levelThreshold` the game should offer the level-up in the
  Skills menu (UNCONFIRMED). Stage 1 logs before/after (`xp`, `levelThreshold`, level) for the first 10 kills, and shows its own notice "Level up! Open the Skills menu" the first time
  `xp` passes the threshold, in case the game shows none. Safety: an amount is clamped to `KillXPMaxShare` 0.5 of a level per kill; nothing is written when `skills` or `data` is null.
* **Notices:** none per kill (the user did not pick "XP on kill"); the level-up notice only. A summary line in the log every 30 s ("kill XP: N kills, X XP given, level a (xp b / c)").

### 3.2 Proficiency XP from damage (stage 2)
* **What counts:** every `TESHitEvent` whose `cause` is the player and whose `source` is a Skylands gun (`GunOf`), on a target that counts (below). One event per projectile, so a
  shotgun books each pellet that hits (UNCONFIRMED that every pellet raises its own hit event: stage 2 logs pellets launched against hits booked per shot).
* **Only living targets** (the user, round 3): a hit counts when the target was alive just before it: the killing hit counts in full (overkill included), and so do the other pellets of
  the same shot that land within `ProfKillGrace` 0.25 s of the death; any later hit on the body counts for nothing.
* **How much:** the bullet's own damage, **not** measured health loss: the gun's enchantment magnitude (per pellet, as the installer wrote it: shot damage / pellets x 1.5) x the launch
  power the player's bullets carry at that moment (relic `Variable09` x the gun's proficiency damage multiplier). So relic and proficiency damage bonuses count, damage that lands on a
  shield counts (the bullet's damage does not care what absorbs it), resistances and armour are not taken off. **No cap** per hit or per enemy: overkill of the killing shot counts;
  hits on a body after death do not (above).
* **XP** = damage x `ProfXPScale` 0.1, booked to BOTH the gun's type track and its maker track (the maker gets the same XP, not a share).
* **Which targets count:** living people and creatures hostile to the player (`IsHostileToActor`; for the killing hit, as it was just before the death);
  NOT: essential or protected actors, the player's followers and teammates, summoned or commanded actors (and their bodies), critters, children, or anyone not hostile (townsfolk give
  nothing). A target that becomes hostile (the player attacks a guard) counts from then on.
* **Not yet:** rocket and elemental SPLASH damage (the explosion's own damage) comes later; until then a rocket books its direct hit only, and an explosion's hit event is not counted twice
  (an event with an explosion source, or a second event for the same projectile, is skipped: UNCONFIRMED how explosion hits name their source; the log shows it).
* **Batching:** hits add to a pending total under one lock; the 250 ms pump (`ProfBatchMs`) moves it into the tracks, levels them up and queues the notices. No game call per bullet.
* **Log:** the first 30 booked hits ("prof: hit FF000E22 by gun FE003A99 (smg, Jakobs) pellet: magnitude 6.2 x power 1.15 = 7.1 damage -> 0.71 XP"), every level-up with the held gun's
  total multipliers, a 30 s summary.
* **Cost** of level n -> n+1: `ProfBase` **50** + `ProfStep` **15** x n XP (the user, round 3), no cap, no scaling by player level (later-game guns and enemies fill it faster: intended). Totals:
  level 1 = 50 XP (500 damage), level 10 = 1,175 XP (11,750 damage), level 25 = 5,750 XP (57,500), level 50 = 20,875 XP (208,750), level 100 = 79,250 XP (792,500).

### 3.3 Proficiency bonuses (stage 2 for types, stage 3 for makers)
* **The six stats** (type tracks): damage %, accuracy % (less spread), reload speed %, fire rate %, magazine %, bonus projectile chance (points of percent).
* **Ordinary levels** give **1 stat** (the user's pick), in a fixed rotation so every stat comes up every 6 levels: damage, accuracy, reload, fire rate, magazine, bonus projectiles, ...
* **Milestones** `ProfMilestones` = 10, 25, 50, 75, 100, then every 50: 4 stats (the rotation's stat for that level plus the next three), each `ProfMilestoneMult` 3x the current step.
* **Shrinking step:** the step of a stat at a level = max(floor, start x `ProfDecay` 0.75 ^ milestones passed). Starts / floors (*design*): damage 2 % / 0.5 %, accuracy 2 % / 0.5 %,
  reload 2 % / 0.5 %, fire rate 2 % / **0.5 %** (the user's minimum), magazine 3 % / 1 %, bonus projectiles 4 / 1 points of percent.
  Totals of one type track (worked out from these defaults): level 10: damage +10 %, accuracy +4 %, reload +4 %, fire rate +8 %, magazine +12 %, bonus projectiles +16 points;
  level 25: +17.5 / +11.5 / +11.5 / +15.5 / +18.8 % / +25 points; level 50: +22 / +19.4 / +19.4 / +23.4 / +30.6 % / +34 points (the exact table is generated by `tools/gen.py` into the sheet and tested).
* **Manufacturer tracks** use the same points and levels but raise only that maker's signature stats (*design*, from BL2's manufacturer styles): Jakobs damage, Maliwan damage
  (elemental guns; the elemental effect chance does not exist in Skylands yet) and accuracy, Dahl accuracy and reload, Vladof fire rate and magazine, Tediore reload and magazine,
  Torgue damage and bonus projectiles, Bandit magazine and fire rate, Hyperion accuracy and damage. A level gives 1 of its two stats (alternating), milestones both at 3x.
* **The user's rule:** every gun gets **25 %** (`ProfOtherMakers` 0.25) of the bonuses of every OTHER maker's track and **100 %** of its own maker's track (the user: full bonus only,
  1.0x, not 1.25x).
* **Applied in the plugin, per shot, on top of relics:** fire interval / (relic rate x prof rate), reload / (relic x prof), spread / (relic x prof), clip x relic x prof, power x relic x prof
  (damage), extra projectiles. Nothing goes through actor values (no clash with relics, nothing for a load to drop).
* **Bonus projectiles:** chance c (percent): each shot fires floor(c / 100) extra projectiles plus one more with probability (c mod 100) / 100; a shotgun applies it **per pellet**
  (each pellet can split), every other gun per shot; extras use one round (BL2's "consumes 1 ammo"), go in their own random place in the spread and use the same damage.
  Launchers get extra rockets the same way at **half** the chance (`ProfLauncherProjectiles` 0.5, the user's pick).

### 3.4 Display (stage 2 notices, stage 3 HUD)
* Notices (`ShowHUDMessage`): "SMG proficiency 4: +2% reload, +2% fire rate", "Jakobs proficiency 10 (milestone): +6% damage, +6% accuracy", "Level up! Open the Skills menu" (3.1).
* HUD line under the ammo display (drawn in `HudFrame`, inside the existing `AddUITask` + `Guarded`): `SMG 12  [====---]   Jakobs 4  [=------]` in small text, the bars = progress to the
  next level; only while a gun is held. Ini `ProfHud` 1. A summary power or menu was not chosen (can come later).

### 3.5 Saving and settings
* Co-save record **'PROF' version 1**, per character: for each of 6 types and 8 makers: level, points into the level, total points, legendary count (0; reserved for 3.6); plus the
  kill XP counters for the log. Revert clears everything (new game = 0). An older save without the record starts at 0.
* Ini block `[Progression]` from `sheets/progression.json`:
  - kill XP: `KillXP` 1, `KillXPScale` 1.0, `KillXPKillsPerLevel` 30, `KillXPWindow` 3, `KillXPMaxShare` 0.5, `KillXPNoKiller` 1, `KillXPNonHostile` 0, `KillXPBadass` / `KillXPSuper` /
    `KillXPUltimate` / `KillXPBoss` (BL2's from the report, else 3 / 5 / 10 / 5);
  - proficiency XP: `Prof` 1, `ProfXPScale` 0.1, `ProfBase` 50, `ProfStep` 15, `ProfBatchMs` 250, `ProfLogHits` 30, `ProfKillGrace` 0.25 (seconds after a death in which the
    rest of the killing shot still counts; bodies count for nothing after it);
  - bonuses: `ProfStatsPerLevel` 1, `ProfMilestoneMult` 3, `ProfDecay` 0.75, `ProfOtherMakers` 0.25, `ProfOwnMaker` 1.0, `ProfLauncherProjectiles` 0.5, the per-stat starts and floors
    (`ProfDamageStart` 2 / `ProfDamageFloor` 0.5, ... `ProfProjectileStart` 4 / `ProfProjectileFloor` 1);
  - display: `ProfHud` 1, `ProfNotices` 1, `ProfLog` 1.
  Gone from the first draft: `ProfWindow`, `ProfHitCap` (no measured damage any more). New keys take defaults; the user's values are kept (`merge_ini`).

### 3.6 LATER (jotted down by the user, not built until asked): Legendary proficiencies
* A track can be made Legendary when it reaches its cap: 100 the first time, +10 for each Legendary after (110, 120, ...). Making it Legendary resets the track to level 0 (its level
  bonuses go), and gives a flat bonus to every stat of that track (*design* +2 % each, +5 points bonus projectiles) that stays, so each round ends with higher stats and a longer climb.
  While Legendary is not built, tracks have no cap (the user's answer 6). How it is triggered (a power, a key, a confirm box from the plugin's `MessageBoxData`) is asked then.

### 3.7 The gun's type and maker in the plugin (stage 2)
* Type: from the ammo index (1.2), no record change. Maker: a new keyword `SkylandsMaker_<n>` (8 keywords, 0 Bandit .. 7 Vladof, `manufacturers.json` order) on every gun, records
  appended **last** in `SkylandsGunModels.esp` so no older form id moves (a test asserts it, as for the voice records); `Skylands.esp` is untouched (byte-identical test). The gun's
  numbers keyword itself is not changed (changing its text could split shared keywords and move ids).

### 3.9 Does any of this need a NEW GAME? (the user asked)
Nothing REQUIRES one; two things SUGGEST one for the first test:
* **No new game needed for the saves:** progress lives in a new co-save record ('PROF'); an old save without it simply starts every track at 0. Kill XP goes into Skyrim's own level meter.
  The maker keywords (stage 2) are new records appended LAST in `SkylandsGunModels.esp`, so no existing form id moves (a test asserts it), and no Papyrus property changes (no ghost scripts).
* **Suggested, to judge the PACE fairly:** the kill XP is sized against your current level, and BL2's level-gap rule gives almost nothing for enemies far below you (6+ levels below = 1 %).
  An existing high-level character in cleared or low-level areas would see tiny XP and think it is broken; a new character from level 1 sees the intended 30 same-level kills per level.
  Proficiencies start at 0 either way, but a fresh run shows how they grow from the first fight.
* **Later stages:** Badass Rank is shared across characters through its own file (no new game); a token power, if chosen over a hot key, is a new record appended last (an existing save may
  need the quest-start check described in CLAUDE.md lesson "Quest start"). If any later stage DOES move ids, the build notes will say so in advance.

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
| 0 | BL2 survey: XP formulas, level curve, challenges, Badass Rank (`Check-BL2-Progress.bat`) | python, **built: 0.53.2 / TestBuild-166 (report read, 1.3); deep pass 0.53.3 / TestBuild-167** | class/group names guessed wrong (found by name, so the report says what it found) |
| 1 | Kill XP into character level; hit-source log; gun-kill test | plugin, **built: 0.54.0 / TestBuild-168, plugin 1.30.0** | direct `xp` write does not offer the level-up |
| 2 | Type proficiencies: damage XP from hits, levels, the stats (bonus projectiles excluded), notices, co-save 'PROF' v1, maker keyword records | plugin + python (keywords) | hit events missing per pellet or doubled for explosions; form ids moving |
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
* **The hit event** (UNCONFIRMED): that every pellet raises its own `TESHitEvent`, that `cause` is the player and `source` the gun for the player's plugin-launched bullets, and how an
  explosion's hit names its source. Stage 2 logs the first 30 hits and pellets launched against hits booked.
* **What farming is still possible** (no caps per hit or per enemy; only living hostile targets count):
  - **Shooting bodies: closed** (round 3). Only the killing shot's own pellets within 0.25 s of the death count.
  - **Unkillable or tanky hostiles:** a Badass giant, a regenerating troll, a dragon on a perch, an enemy stuck behind a wall that cannot reach you: damage keeps flowing as long as you have
    ammo (ammo is the only limit: rounds come out of the pack).
  - **Making someone hostile:** attacking a townsperson or guard makes them hostile, and from then on their damage counts (they are excluded only while not hostile). Essential and
    protected ones never count.
  - **High fire rate, big magazines and damage bonuses** fill tracks faster per second (intended: relic and proficiency damage count, and a stronger gun levels faster).
  - **Shotguns** book every pellet that hits (intended; point-blank shots land all pellets).
  - Not farmable: walls, the ground, friendly or neutral actors, summons, followers, missed shots (only hits count).
* **Kill XP** cannot be farmed this way (a body counts once, 60 s; only gun kills of hostile actors).
* **Balance:** compounding bonuses on the type track, the maker track, the other makers' quarters, relics and later tokens; the ini scales each, and stage 2's log prints the
  held gun's total multipliers every time a level changes.
* **Ids:** new records (maker keywords, later the power) go LAST in the second plugin; `Skylands.esp` stays byte-identical (tested). No Papyrus property changes are planned (no ghost scripts).
  Natives keep no String parameters. No lock is taken while holding another (0.43.0). Scaleform only from `AddUITask` inside `Guarded` (0.48.1).
* **Other mods:** none in the user's setup; an XP mod that hooks the same `xp` value would add to ours (ini `KillXP` 0 turns ours off).

## 6. Questions still open for you
None about the design. The deep report is read (1.3b). Stage 1 (kill XP) is APPROVED and built (0.54.0). Waiting for: the in-game report of stage 1.
