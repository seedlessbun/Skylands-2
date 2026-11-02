# Badass enemies: plan (phase 1 deliverable)

Status: **APPROVED with the defaults, with the user's changes in section 2a. Stage 0 (the BL2 survey, 0.45.2, TestBuild-149) is built; no plugin code yet.** Written from the code at 0.45.1 and the user's interview answers (section 2). **Confirmed** = read in the
code or a log of this project. **Unconfirmed** = my reading or a guess, with how it will be checked. No Borderlands 2 install is available to this session and no logs were
attached, so no new BL2 numbers were read; the BL2 facts below come from `docs/shield-roadmap.md` (the earlier shield survey) and `sheets/`.

## 0. The short version

* Three tiers of enemy, **Badass, Super Badass, Ultimate Badass**, decided once per actor by a roll that depends on the **player's level**, not the enemy's, with a cap on how many are alive near the player.
* A Badass has a **name prefix** and a **bigger body**, more health, more damage and (higher tiers) more speed. All of it is done by the SKSE plugin with temporary modifiers it tracks and puts back after a load (the shield code already does this for Health).
* **Loot:** every Badass leaves **exactly one guaranteed drop**, whatever its tier; the tier shifts the rarity chances up. A Badass human also **carries** gear (gun, shield, relic) of that higher rarity and drops it. A Badass creature drops one random item from the same pools with the shifted chances.
* **Creatures in general** (not only Badasses) can now drop one gun, shield or relic at **half the human rate**; **dragons are bosses** (always drop, rare or better, Super Badass or higher).
* Dialog and effects are **later** (they need a Wwise survey). Presentation is name prefix and size only.
* Build order: 1 tiers + stats, 2 loot for Badasses, 3 creature drops + dragons, 4 name and size, 5 survey for BL2 numbers and replace the design values. One build per stage.

## 1. Facts

### 1.1 Borderlands 2 (from the shield survey and the sheets)
* Pawn balances are `AIPawnBalanceDefinition` objects under `GD_Population_<Type>.Balance.PawnBalance_<Name>`; `sheets/bl2_reads.json` already lists `PawnBalance_MarauderBadass`, `NomadBadass`, `PsychoBadass`
  (paths from the sheet; `read_verified: no`, the names were used only to rename Skyrim bandits). 2,307 pawn balances were read by the shield survey (`docs/shield-roadmap.md` section 1).
* A balance has `PlayThroughs[]` (normal, TVHM, UVHM), each with `CustomItemPoolList [{ItemPool, PoolProbability}]`, and `DefaultItemPoolIncludedLists` (for example `GD_Itempools.ListDefs.StandardEnemyGunsAndGear`).
  Enemy gear pools: `Pool_GunsAndGear_01_Common ...` (weapons 44.44 %, shields 20 %, grenade mods 15.56 %, class mods 11.11 %, artifacts 8.89 %).
* BL2 gives shields to a badass marauder with probability 0.7 in normal mode and 1.0 in the next, and enemy shield capacity comes from `Init_EnemyShield_CapacityMaxValue` times AI multipliers (default 1.0).
* **Not known:** the health and damage scale a Badass / Super / Ultimate balance applies, their `DisplayName` strings, the presentation (particles, dialog events). The names "Badass", "Super Badass",
  "Ultimate Badass" are from the user's request and BL2 knowledge: whether the files hold Super and Ultimate as separate balances (or as a modifier on one) is **unconfirmed**; the survey in stage 5 answers it.

### 1.2 What already touches enemies in Skylands (Confirmed in the code)
* `shielditems.h`: the 400 ms `Pump` walks `ProcessLists::highActorHandles` (40 looked at, 4 given per pass, reach 6000 units); `IsPerson` (ActorTypeNPC keyword or race editor id words), `IsBoss`
  (unique base record, or level >= `ShieldBossLevel` 35), `Mix(id)` stable rolls, `kLevelFor` = 1,3,8,15,30,40 and `kWeight` = 122:50:20:6:1:1, `PickFor`, `PutOn`, `DeathSink` (drops the worn shield 900 ms after death).
* `relic.h`: same pattern (8 % + 1 % a level, bosses always rare or better, drop 1.1 s after death). Both pick items only for **people**: creatures get nothing from the plugin today.
* `shield.h`: a shield is a **temporary Health bonus**; the game does not keep it over a load; the plugin tracks `Stale` entries through a co-save record (`SHLD` version 2) and re-applies or removes. A Badass health bonus must follow this.
* `main.cpp`: `CastSink` (an enemy's cast of a staff gun starts the rest of its burst, bullets launched by the plugin), the death sink (ammo on bodies), `ScanArmed`. The first bullet of a burst is the **game's own cast**.
* Papyrus `SkylandsHunter` (every race carries it): arms people (70 % of those with the NPC keyword), clears other weapons, `DeathDrop` = one 25 % roll (held gun or a random gun from `ListFor`), for people only.
* `sheets/enemies.json`: the Skyrim bandits are renamed and given **flat abilities** by the installer: tier 6 `AbFortifyHealth:100` and bosses `AbFortifyHealth:150`, marked `badass: yes`
  (names from BL2: "Marauder Badass", "Nomad Badass"). These are fixed records in the plugin the installer makes; see risk R9.
* Loot lists in the models plugin (`shields.loot`): per-rarity leveled lists, chest and merchant lists, the `SkylandsGunList` form list for rarity beams.

### 1.3 What is not known (the game decides)
`SetDisplayName` and `SetScale` on a live actor, whether spell (bullet) damage follows `LaunchData.power`, whether `kAttackDamageMult` / `kSpeedMult` modifiers on a non-player stick, and what the game does with a
scaled or renamed actor over a save. All listed in section 7.

## 2a. The user's decisions after reading the plan
* **Survey first** (stage 0 below), and it **looks for the enemy audio too** (voice and sound events per enemy family, checked against the Wwise banks) so enemy sounds can come sooner.
* **A general enemy stats sheet** for easy changes and lookups: `sheets/enemy_stats.json` (one row per Skyrim enemy class, matched by race editor id: kind, closest BL2 family,
  health and damage multipliers, may be Badass, boss rule, drop share, lowest rarity) and `sheets/badass_tiers.json` (one row per tier: level gate, chances, area cap, stat multipliers,
  rarity shift and floor). Both in `sheet_data.py` (`ENEMY_STATS`, `BADASS_TIERS`); tested in `tests/test_enemy_sheets.py`.
* **Badasses appear from player level 1** (gate 1, 3 % + 0.5 % a level).
* The other defaults stay. **Focus on stats and drops now; better gear carried by Badasses is LATER** (section 3.3 marks it). For now a Badass human carries the gear anyone may roll; its guaranteed drop gets the tier's rarity shift.

## 2. Interview answers (the design inputs)

| Question | Answer |
|---|---|
| Tiers | All three: Badass, Super Badass, Ultimate Badass |
| Frequency | Level-scaled and capped per area, **based on the player's level, not the enemy's** |
| Who | People and creatures; dragons are bosses |
| Creature drops | Half of a human's chance, one random item (gun, shield or relic) |
| Stats | Moderate set (section 3.2) as placeholders until BL2 numbers are read |
| Loot | **One guaranteed drop whatever the tier**; the tier shifts rarity chances up. Badass humans carry stronger gear (shield, gun, relic) and can drop it. Badass creatures without equipment drop a random item with the raised chances |
| Display | Name prefix and bigger size. No glow, no kill message |
| Scope | Stats + loot + creature drops first; dialog and effects later; tuned for a new character |

## 3. Design (defaults; every number is an ini key and a sheet value)

### 3.1 Which actors, which tier
* **Eligible:** any living actor near the player that is hostile to the player (`IsHostileToActor`), not a child, not the player, not a summon of the player, not a follower. People (`IsPerson`) and creatures alike.
* **Rolled once**, at first sight, from `Mix(formId ^ salt)` compared with chances that use the **player's level at that moment**. The result (including "none") is stored in a map and in a co-save record, so a loaded game gives the same enemies the same tier.
* Defaults (percent chance for an eligible actor; the three rolls are exclusive and the highest tier that hits wins):

| Tier | From player level | Chance | Cap on the chance |
|---|---|---|---|
| Badass | 1 | 3 % + 0.5 % per level above 1 | 25 % |
| Super Badass | 12 | 0.5 % + 0.2 % per level above 12 | 8 % |
| Ultimate Badass | 25 | 0.2 % + 0.1 % per level above 25 | 3 % |

  (The user chose level 1: a new character meets about 3 % Badasses from the start, and the Badass row's health x2.5 is the main difficulty knob; ini keys `BadassGate/Percent/PerLevel/Max` per tier, defaults from `sheets/badass_tiers.json`.)
* **Area cap:** at most `BadassMaxNear` (default 4) living Badasses of any tier within the pump's reach (6000 units) at the same time, and at most 1 Super and 1 Ultimate. An eligible actor that would exceed the cap is not rolled yet (tried again later), so a pack does not all turn Badass.
* **Bosses** (unique base record, or level >= 35, hostile): at least Super Badass; Ultimate Badass if the player is level 25 or more (50 % by their roll). **Dragons** (keyword `ActorTypeDragon`, race editor id with "Dragon"): bosses by this rule.
  A boss that is already named does not get a prefix twice (section 3.4). Allies, followers and quest-protected actors are never given a tier.

### 3.2 Stats (placeholders; BL2 file values replace them after the stage-5 survey)

| | Badass | Super | Ultimate |
|---|---|---|---|
| Health (x max) | 2.5 | 5 | 10 |
| Damage (x) | 1.3 | 1.6 | 2.0 |
| Speed (x) | 1.0 | 1.05 | 1.10 |
| Size (x) | 1.15 | 1.30 | 1.45 |

* **Health:** a tracked temporary Health bonus of `(mult - 1) x base max` (same care as the shield: record in the co-save, taken off or re-applied after a load, restore current health in proportion so the actor does not spawn hurt).
  The shield, if it has one, is sized from the actor's **base** health so a Badass does not also get a 10x shield (a design choice; tier multiplier for shields is a later knob).
* **Damage:** melee and arrows by the actor value `AttackDamageMult` (tracked modifier). Gun bullets: the plugin launches the burst bullets itself and sets `LaunchData.power`; the **first bullet of a burst is the game's own cast** and
  would stay unscaled (the bullet effect's magnitude is shared by every holder of that gun, so it cannot be scaled per actor). Stage 1 measures it; if the first bullet is unscaled, the plugin adds the missing share as
  direct damage on the hit event. The user judged the earlier `power` bonus by eye only: **this is the least certain number in the plan.**
* **Speed:** `SpeedMult` as a tracked modifier. **Size:** `SetScale` on the actor.
* All modifiers are removed when the actor dies (so nothing carries to the corpse) and are cleared by `Revert()` on a load, then re-applied from the co-save, like `relic::g_applied`.

### 3.3 Loot
Rarity machinery: `kWeight` 122:50:20:6:1:1 and the gates `kLevelFor` are reused. A tier **shifts** the weights up and sets a floor:

| Tier | Weight shift | Floor | Level used for the gates |
|---|---|---|---|
| Badass | up 1 rarity | uncommon | max(player level, 8) |
| Super | up 2 | rare | max(player level, 15) |
| Ultimate | up 3 | epic | max(player level, 30) |

("Up n" means each rarity takes the weight of the rarity n below it, so the common weight lands on rarity 1+n.) The floors also guarantee a Badass is never given a common.

* **LATER (the user's decision): Badass humans carry better gear.** At the roll, in the same pass, a Badass person is given **a shield and a relic** of the shifted rarity (`shielditems::PickFor` / `relic::PickFor` already take `a_minRarity`) with `PutOn`, and a **gun** of the shifted rarity
  when the plugin can place one (see R6: guns are placed by Papyrus today). Its gear drops as for bosses (`IsBoss` currently forces the drop; a tier forces it too).
* **Guaranteed drop, one item, any tier.** At death (the existing 0.9 to 1.1 s game-thread pattern, never inside the event): a Badass human drops **one of the items it carries** (random among gun, shield, relic); a Badass creature (nothing equipped)
  gets **one random item** added to its pack and dropped: gun, shield or relic, chosen by the weights in 3.5, with the shifted rarity. If it carried nothing to drop, it is given one at death.
* The ordinary drop chances (25 % shield, 100 % relic, Papyrus gun roll) are unchanged for non-Badasses.

### 3.4 Presentation
* **Name prefix:** "Badass", "Super Badass", "Ultimate Badass" before the actor's name (`SetDisplayName`), set when the tier is rolled and set again after a load. If the name already starts with or contains "Badass" (the installer's renamed bandits) the prefix is not added twice; only the tier is stored.
* **Size:** `SetScale` by the table. Done once at the roll; checked again each pump (the game resets scale on a re-load of the 3D, unconfirmed).
* The game's own enemy bar shows the name; our shield bar is unchanged. No glow, no message, no sound (the glow code stays off).

### 3.5 Creature drops (all non-person actors, Badass or not)
* A creature killed by anyone while hostile to the player, not summoned, rolls **once at death**: chance = **0.5 x the human chance** at the same level, where the human chance is the expected number of items a human body leaves:
  gun `DropChance` 25 % + shield (`EnemyShieldPercent + EnemyShieldPerLevel x (L-1)` % carry x `ShieldDropPercent` 25 %) + relic (`EnemyRelicPercent + EnemyRelicPerLevel x (L-1)` % x `RelicDropPercent` 100 %), capped at 60 %.
  That is about 17 % at level 1, 32 % at level 20. The ini key `CreatureDropScale` (default 0.5) is that "half".
* If it hits, **one item**: the type by the same shares (gun 25 : shield 2.5 : relic 8 at level 1, so mostly guns and relics early, more shields later), rarity by `PickFor` with the level gates of the **creature's level**.
* **Dragons and other bosses:** always drop (100 %), rarity floor rare, gates at max(level, 15); a dragon also counts as Super Badass or above, so it uses the Super row in 3.3. A dragon corpse is absorbed after some time; the item is dropped at 1 s so it is on the ground first (R7).
* Not eligible: animals that are not hostile to the player at death, summons (`IsSummoned`/commanded), the player's followers, children. Chest-like "loot" of a creature (skin, meat) is untouched.

### 3.6 Settings and saves
* New ini block (written by `skse.default_ini`, new keys take defaults without an `IniVersion` bump; if a default of an existing key must change, bump `IniVersion` or use a `...DefaultsRev` as the shields do): `Badass`, per-tier gate/percent/per-level/max, `BadassMaxNear`, per-tier health/damage/speed/size, `BadassPrefix`, `BadassSize`, `CreatureDropScale`, `CreatureDrops`, `DragonBoss`.
* Co-save record `BDAS` (version 1): actor id, tier, which modifiers are applied (health bonus amount, damage, speed, scale) and the base max health, so a load can take off or re-apply, as `SHLD` does.
* **No Papyrus change** in stages 1 to 4, **no new record in `Skylands.esp`**. A new form in the models plugin is not needed either (drops use existing lists and items). So no ghost-script risk and no new-save requirement.

## 4. Stages (one test build each)

| Stage | Content | You do |
|---|---|---|
| **0. BL2 survey** (0.45.2, TestBuild-149, python only) | `Check-BL2-Badass.bat` (`python -m skylands_setup bl2badass`, `badassprobe.py`) writes `work\bl2-badass-report.txt`: B0 names (badass, enemy sound/voice, dialog), B1 every pawn balance by family and tier, B2 regular + tier variants in full down to the AI class, B3 health/damage formulas and rarity weights, B4 enemy item-pool lists and badass/boss pools, B5 badass-named objects (particles, name parts), B6 enemy sound events per family checked against the Wwise banks, B7 dialog objects | run it, send the report |
| **1. Tiers and stats** (plugin only) | the roll, the cap, the co-save, health / damage / speed modifiers, log lines for every tier given and every modifier read back ("badass: <id> level L tier T: health 77 -> 193 ..."); name and size **off** (so stats alone can be judged) | fight at levels 3 to 12; send `SkylandsNative.log` |
| **2. Loot for Badasses** | the guaranteed drop, rarity shift and floors (carried better gear: later) | kill some Badasses, send the log |
| **3. Creature drops and dragons** | `CreatureDropScale`, creature roll at death, dragon boss rule | kill wolves, spiders, a dragon; log |
| **4. Name and size** | `SetDisplayName` / `SetScale` with the double-prefix rule | check the name after saving and loading |
| **5. Enemy audio** | from the stage-0 report: enemy voice lines and sounds cut to WAV like the gun sounds and played at the actor by the plugin (taunt on spawn of a Badass, death lines), with a cooldown | listen |

The stage-0 report fills `sheets/badass_tiers.json` and `sheets/enemy_stats.json` (`source: bl2` rows replace the design values) before stage 1 is built. Effects (section 6) stay later.

## 5. The survey (stage 0, built in 0.45.2)
A module of its own, `badassprobe.py`, reusing the shield survey's helpers (it looks at more than a topic switch could): name scan for `badass|superbadass|ultimate`, the `AIPawnBalanceDefinition` census under `GD_Population_*` and `GD_Balance`, then in full: three balances of different families
(for example Marauder, Marauder Badass, Super Badass Marauder, Ultimate Badass Marauder if they exist), their `PlayThroughs`, `DefaultItemPoolIncludedLists` and `CustomItemPoolList`, the health / damage scale attributes
(`Att_*Health*`, `Att_*Damage*` on the pawn's `AIClass` / `PawnBalance` / `BodyClass`), the pools that badasses use (`Pool_GunsAndGear_0x`, the rarity weights `Weight_*`), the enemy
name strings, and every enemy- or voice-looking sound event (`Ak_Play_*` with an enemy family word or `vo/taunt/death/pain/attack/...`), grouped by family and checked against the Wwise banks (how many sounds and audio files each event leads to). Extraction comes in stage 5. The survey is read-only and takes 10 to 20 minutes like the others.

## 6. Dialog and effects (later)
* Voice lines: events in the Wwise banks (`Ak_Play_*`), cut to WAV with the existing `bl2/audio.py`, made into SNDR records and played at the actor by the plugin's `PlaySound`. Risk: many Skyrim actors have their own voice; a taunt on spawn needs a cooldown.
* Effects: BL2 particle systems cannot be read, so only stylised meshes (the shield glow pattern). Off by default; the user did not want a glow now.

## 7. Risks and what only the game can confirm

| # | Risk or unknown | How it is checked |
|---|---|---|
| R1 | A temporary Health bonus on a **non-shield** actor survives a load? (The game dropped it for the player; the co-save re-applies.) | stage 1: save with a Badass nearby, load, log "badass: re-applied" / "taken off" |
| R2 | Does `AttackDamageMult` change an enemy's **staff gun** damage? Almost surely not (it scales weapon damage). The first bullet of a burst is the game's cast | stage 1 logs the damage taken by the player per hit with and without a tier; fallback in 3.2 |
| R3 | `LaunchData.power` scaling of spell damage was judged by eye only | same log |
| R4 | `SetDisplayName` survives a save/load, shows on the enemy bar, doesn't break quest names | stage 4 |
| R5 | `SetScale` on a person/creature: collision, animation speed, floating or sunk feet; huge dragons | stage 4, scale capped at 1.6 |
| R6 | Guns are placed by Papyrus (`try_arm`, 70 %) and its `ClearWeapons` removes other weapons. A plugin-placed gun may be cleared or dual-wield (a past problem). A Badass human's gun may need to come from the Papyrus side (a script change, ghost-script rule) or be dropped from the plugin only | stage 2 decision from the log |
| R7 | A dragon dies in the air and is absorbed; a body in the middle of a crash may drop an item out of reach | stage 3: drop position logged |
| R8 | Performance: the tier map and a co-save grow with every actor seen (cap at the same 3000 ids the shield map uses) | stage 1 timing line |
| R9 | The installer's renamed bandits already have `AbFortifyHealth:100/150`. A Badass roll on top stacks: Badass x 2.5 on an already-strong bandit. Default: leave those rows alone (changing records in the installer plugin moves ids), reduce the tier health for them (skip health for a base that already has the ability) if the log shows it too hard | stage 1 |
| R10 | Balance for a **level 1 new character**: gates at player level 3, health x2.5 | user plays; every number is an ini key |
| R11 | Creature drops can be farmed (respawning wolves). The chance is half the human one and the same respawn rule as for humans applies | user's call; `CreatureDropScale` |
| R12 | Never lock while holding a lock; never call a helper that locks inside a `lock_guard` (the 0.43.0 crash); the plugin changes a body's pack only 0.9 s after death from the game thread | code review |
| R13 | Friendly actors and quest targets: the tier is rolled only for actors hostile to the player; a bandit leader whose death triggers a quest is fine (stats only), but a protected or essential actor (`IsEssential`/`IsProtected`) is skipped | code |

## 8. Questions still open for you
1. ANSWERED: level 1. (Was: the 3 % / 0.5 % per level chances and the level-3 gate are my defaults (the answer was "based on the player's level"). Fine, or should Badasses appear from level 1?)
2. Still open (default applies): R9: keep the Pandora bandits' fixed `AbFortifyHealth` as it is (default), or turn it off once the plugin gives a tier?
3. ANSWERED: better gear is later. (Was: a Badass human's **gun** (R6): is it enough that the Badass drops a **tier-boosted gun at death** (the plugin adds it to the pack at the roll and drops it), without changing what it shoots? Default yes (no Papyrus change).)
4. ANSWERED: survey first. (Was: do you want the survey **before** stage 1 so the first build already uses BL2's numbers? Default: no, build the framework first on placeholders.)

## 9. Further features I would suggest (prioritised; none built without your pick)

1. **Tier-scaled enemy shields** (small, low risk). A Badass shield uses the tier as a capacity and rarity multiplier (BL2 gives badasses and named a larger ratio: `enemy_ratio_badass` in `sheets/shields.json`). Implementation: pass `tier` into `shielditems::Pump` so the ratio and `a_minRarity` come from the table; reuses all of `shield.h`.
2. **Named loot bosses with a fixed unique drop** (medium). BL2 has bosses with a unique item. Implementation: a table in the sheet of Skyrim unique-actor editor ids (bandit chiefs, named dragons; story actors like Alduin left out) to a chosen shield/relic/gun; `DeathSink` drops it at 100 %. Risk: the unique items need records (models plugin, new save).
3. **Notice of rare spawns** (small). A one-line screen message when a Super or Ultimate Badass first comes within reach, and "slain" on death, using `shield::Tell`. Off by default since you chose no message.
4. **Elemental Badasses** (medium). A Badass gets an element (fire, shock, corrosive) that matches its bullets and shield type: needs per-actor bullet selection in `CastSink`'s burst launcher and the matching shield from the catalog. Risk: the first bullet is the game's cast.
5. **Badass ranks** (medium). BL2's Badass rank: count kills of each tier in the co-save, give a small permanent bonus (gun damage % or magazine %) at thresholds through the existing relic-style actor values (`Variable09`, `Variable04`), and show a line on the HUD. Risk: balance, a new HUD element.
6. **Loot midget style treasure enemies** (medium). A small rare actor that runs away and drops several items: needs a new actor record (models plugin) and flee AI; best done after the framework is proven.
7. **Area difficulty** (large). Use Skyrim location data (a hold or a dungeon type) in the chance, not only the player's level. Needs a survey of locations. Skip unless levels alone feel flat.
8. **Raid-boss set pieces** (large). A scripted Ultimate Badass with an arena. Needs quests, worth it only after 1 and 2.
9. **A general "enemy stats" sheet** (DONE in 0.45.2: `sheets/enemy_stats.json`). Your request to "adjust enemy stats and drop pools generally": a sheet by race/keyword for health, damage and carry chances, read by the same pump, with the BL2 values filled in after the survey. Same machinery as the tiers (a "tier 0" row).
