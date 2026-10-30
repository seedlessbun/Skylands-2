# Shields, the Borderlands 2 way: plan (phase 1 deliverable)

Status: **APPROVED by the user with the defaults in section 8; stage 1 is built (0.38.0).** Decisions: see section 9. Original status: planning only. Written after reading the user's `bl2-shield-report.txt` (TestBuild-128, 13,425 lines,
all sections ran). Line numbers below (`report L2176`) are lines of that report so a claim can be checked; the report itself is on the user's PC
(`work\bl2-shield-report.txt`). **Confirmed** = seen in the report. **Unconfirmed** = my reading or a guess, with how it will be checked.

## 0. The short version

* BL2 shields are *items* with stats built from parts (body, battery, capacitor, accessory, material) and a rarity, worn in one slot. A shield is a resource pool
  in front of health with a capacity, a recharge delay (3.5 s base) and a recharge rate; the HUD shows a bar; enemies carry a shield from a "shield pool".
* In Skyrim the one thing that has to be right is **where damage is taken**. Our gun bullets are *spells* (a hostile damage effect), so hooking only
  `Actor::HandleHealthDamage` (melee and arrows) would miss every Skylands bullet. The place all health damage passes is
  **`ActorValueOwner::ModActorValue(kDamage, kHealth, -n)`** (virtual slot 6 of the actor's ActorValueOwner part). Plan: hook that, absorb there. This is the first thing to prove (stage 1).
* Everything else (HUD bar, items, enemy shields and drops, types) reuses machinery we already have: the plugin's HUD, keyword-carried numbers, the Hunter
  script's spawn/drop life cycle, the beam tracker, the Wwise audio extractor, the gestalt mesh cutter.
* Build order: **1 core mechanic (no items, no UI)** -> **2 HUD bar + sounds** -> **3 shield items for the player** -> **4 enemies: spawn, drop, beam** ->
  **5 shield types** (nova, spike, amp, roid, absorb, booster, turtle, adaptive) -> **6 extras**. One test build per stage.
* One more survey run is recommended (small, bundled into the stage 1 build, section 7): the report did not capture the stock shield's stat tables, the type effect
  numbers or the enemy shield formulas, and I know why (a line cap in my own survey). Nothing in stage 1 needs them.

## 1. What Borderlands 2 does (from the survey)

### 1.1 The item model (Confirmed)
* `ShieldDefinition` (class) is the item. Properties seen (L2176-2248, L2554-2688): `ShieldType` (`SHT_Spike`, `SHT_Absorption`, `SHT_Chimera`; also seen in the pool names:
  Standard, Nova, Roid, Impact (= Amp), Booster, Juggernaut), `ShieldPrimeMechanism` (`SPM_AlwaysPrimed`, `SPM_PrimeOnFull`, `SPM_PrimedWhenNotEmpty`: when the on-hit or on-break effect is ready),
  `ShieldTypeFlashFrameName` (a frame of the HUD bar art: `absorb`, `chimera` ...), `GestaltMesh = Item_Shields.Gestalt.GestaltDef_Shields`, five part-list slots
  `AlphaParts` (body), `BetaParts` (battery), `GammaParts` (capacitor), `DeltaParts` (accessory), `MaterialParts` (rarity look), `ExternalAttributeEffects`, `PickupSounds`
  (`Ak_Play_Obj_Pickup_Shield`), `PickupFlagIcon`, `UIStatList`, `bUsesPlayerLevelRequirement`.
* `InventoryBalanceDefinition` = what drops (`InventoryDefinition`, `Manufacturers`, `PartListCollection`); `ItemPartListCollectionDefinition` holds the five part lists
  (`PartReplacementMode` complete/selective); `ItemPartListDefinition` lists `WeightedParts` with a manufacturer weight, `MinGameStage` 1, `MaxGameStage` 100 and a rarity weight
  (`GD_Balance.Weighting.Weight_1_Common` = 100 ...).
* `ShieldPartDefinition` has `ShieldPartType` (`SHIELD_PART_Battery / Capacitor / Accessory / Material` printed; the body parts print none, which is the default value, so presumably body), `ItemAttributeEffects`, `AttributeSlotUpgrades` and a mesh fragment
  `GestaltModeSkeletalMeshName` (L4156-4300 etc.). Each slot has 9 parts (Tediore 1, Bandit 2, Vladof 3, Dahl 4, Anshin/Maliwan 5, Torgue 6, Hyperion 7, Pangolin 8).
  **The fragment names are crossed (Confirmed, read from the report):** the *body* parts point at `Shield_Accessory_<Mfr>` fragments (Tediore's at `Shield_Body_Tediore`; Maliwan's body at `Shield_Accessory02_Pangolin`, its battery at `Shield_Battery_Pangolin`: **Maliwan has no meshes of its own and reuses Pangolin's**),
  while the *accessory* parts (the Aster/Orchid/Sage customs seen) point at the big `Shield_Body_<Mfr>` fragments. So the mesh for a slot must be taken from the part's own `GestaltModeSkeletalMeshName`, never guessed from the fragment's name.
* The player resource is `D_Resources.Shield` -> `WillowGame.ShieldResourcePool` with the attributes `ShieldMaxValue` (capacity), `ShieldOnIdleRegenerationDelay`, `ShieldOnIdleRegenerationRate`,
  `ShieldConsumptionRate`, `ShieldCurrentPercentOfMaxValue` (L2393-2472). A shield item *adds* to those (`ExternalAttributeEffects`, `MT_PreAdd`).

### 1.2 The numbers (partly confirmed)
* **Recharge delay: 3.5 s** (`GD_Shields.Misc.Att_UniversalShieldBaseDelayConstant`, L3717-3731). Confirmed.
* **Consumption rate: +100000** (`MT_PostAdd`, L2219-2225): damage drains the shield instantly; there is no slow bleed. Confirmed.
* **Capacity** `Init_ShieldItem_CapacityMaxValue` (L3748): formula `Multiplier x Level ^ Power` with Multiplier = `Att_UniversalBalanceMultiplier_HealthShields` (80.0) x 0.8 = 64,
  Level = `Att_UniversalBalanceScaler` (1.13, constant fallback 85), Power = `ShieldItemLevel` (the item's `ExpLevel`). **Unconfirmed how to read it**: taken literally it gives 72 at level 1 and
  28,800 at level 50, far above what a level 50 shield shows in game; so either the formula text does not mean `M x L^P` or grades/other terms cut it down. Skylands will not depend on it (section 2.3).
* **Recharge rate** `Init_ShieldItem_BaseRegenRatePercentage` (L3734): Multiplier = the capacity formula, Level 0.16, Power 1.0, minimum 1 -> **0.16 x capacity per second** (full recharge about 6 s after the delay). Same reading caveat, but the shape (a fixed fraction of capacity per second) is clear.
* **Slot grades**: parts do not carry the stats directly; they add integer *grades* to four attributes `ShieldCapacity / ShieldRechargeRate / ShieldRechargeDelay / ShieldSpecial SlotGradeMinusRarity`. Examples (L4156, L4496):
  Tediore body capacity -4, rate +4, delay +4, special +1; Hyperion body capacity -4, rate -2, delay +8, special +3. A rarity "material" part adds grade (a rare custom shield: +12, L2542).
  The grade sets the **name prefix** by thresholds (`Prefix_Capacity_*`: grade <= -9 "Terminal", -8..-4 "Inferior", 6..12 "Diagnostic" (rarity >= 3), 12..20 "Maximal", >= 20 "Superior"; the same for Rate, Delay, Special; "Balanced").
  **Not captured:** how a grade becomes a number (the stock definition's slot table was cut off by my survey's 70-line limit). Section 7.
* **Elemental resistance**: attributes `D_Attributes.DamageTypeModifers.{Normal,Explosive,Corrosive,Shock,Incendiary,Amp}ImpactDamageModifier` (and `...StatusEffectDamageModifier`); capacitor parts `Capacitor5_Maliwan_{Corrosive,Fire,Shock}Res` and
  `Capacitor6_Torgue_ExplosiveRes` give them; the Blockade shield scales them by `Init_Blockade_Resistance_Major/Minor` (L2763-2850, L3983, L7696+). Confirmed that they exist; the values were not captured.
* **Rarity colours** (`GD_Globals`, L9598): 1 common white (255,255,255), 2 uncommon green (61,210,11), 3 rare blue (60,142,255), 4 very rare purple (168,63,229), 5 legendary orange (255,180,0), 6 e-tech pink (202,0,168), 501 seraph (255,154,184). Same as the guns.

### 1.3 Types and their effects (partly confirmed)
* Families seen as loot pools (L9725+): **Standard, Nova (corrosive, explosive, fire, shock), Spike (the same four), Roid, Impact (amp), Booster, Absorption, Juggernaut, Chimera (adaptive)**; 96 distinct `ItemGrade_Gear_Shield_*` balances including legendaries
  (`Nova_Singularity`, `Spike_Acid_05_Legendary`, `Absorption_05_LegendaryShock`, `Roid_ThresherRaid`, `Booster_PotOGold`, `Standard_CrackedSash` ...) and mission rewards per manufacturer.
* The effects are **skills activated by the accessory part** (`Behavior_ActivateSkill` on equip, `Behavior_DeactivateSkill` on unequip) with `SkillDefinition` events such as `SDE_DamagedByEnemy`, plus behaviours
  `Behavior_SetShieldTriggeredState`, `Behavior_PostProcessChain_LostShield`, `Behavior_SetShieldColor`, `Behavior_SetShieldDamageResistanceType`. Seen in full only for the DLC customs (Antagonist = spike, Blockade = absorb/resist,
  Seraph Anshin = health regen); the vanilla nova/spike/roid skill numbers were **not** captured. Section 7.
* Bodies of pawns know shields too: `BodyClassDefinition.bHideEmptyShieldBar`, `LostShieldAnim`, `LostShieldDamageTriggers`, `bCloakingRequiresShields`; `WillowDmgSource_Shield / ShieldNova / ShieldSpike` are damage sources (so nova and spike damage are tagged and can be told apart).

### 1.4 Loot (Confirmed)
* Pool tree: `Pool_Shields_All` -> `Pool_Shields_All_01_Common / 02_Uncommon / 04_Rare / 05_VeryRare / 06_Legendary` -> family pools (`Pool_Shields_Standard_*`, `NovaShields_All_*` -> by element, `SpikeShields_All_*`, `Roid`, `Juggernaut`, `Booster`, `Impact`, `Absorption`, `Chimera`) -> balances.
  184 pools refer to a shield directly, 39 more through other pools.
* Enemy loot pools mix gear: `Pool_GunsAndGear_01_Common`: weapons 44.44 %, **shields 20.00 %**, grenade mods 15.56 %, class mods 11.11 %, artifacts 8.89 % (L11004). The shield entry has `bDropOnDeath: False`, the others True (meaning unconfirmed:
  the enemy-gear pools exist so a pawn can be *given* a shield; its drop is a separate matter). `Pool_GunsAndGear_WeightedShields` puts shields at 45.45 % (the other `Weighted*` pools are one gun type with the shield pool as a smaller entry).
* Shop pools: `HealthShop_Items` (common, uncommon), `HealthShop_FeaturedItem` (uncommon, rare, very rare, legendary); `Pool_Gear`, `Pool_GunsAndGear`, `Pool_Locker_Items`, `Pool_Nest_Items` (chests, indirect). Mission rewards per manufacturer. Boss uniques (`Pool_Terramorphous`, `Pool_Warrior` ...).

### 1.5 Enemies (Confirmed in shape, numbers not captured)
* 2,307 pawn balances were read. A pawn balance has `PlayThroughs[]` (normal, TVHM, UVHM), each with `CustomItemPoolList [{ItemPool, PoolProbability}]` and the balance has `DefaultItemPoolIncludedLists` (e.g. `GD_Itempools.ListDefs.StandardEnemyGunsAndGear`).
  The shield an enemy wears: `GD_ItempoolsEnemyUse.Shields.Pool_Shields_Standard_EnemyUse` -> `ItemGrade_Gear_Shield_Enemy_Standard` -> `Shield_Enemy_Standard` (one generic "Orb Shield" definition). Probability per play-through: 0.7 for a badass marauder in
  normal mode, 1.0 in the next (L12734-12777). Special pool `Pool_Shields_Special_EnemyUse` (nova, impact; common/uncommon) and `Grunt_Shields`, `Pool_Shields_BoomBoom` for particular enemies.
* Enemy capacity and regen come from `Init_EnemyShield_CapacityMaxValue`, `Init_EnemyShield_AdditionalShieldCapacityPerPlayer`, `Init_EnemyShieldOnIdleRegenDelay/Rate`, times AI parameters `Attribute_EnemyShield{MaxValue,OnIdleRegenDelay,OnIdleRegenRate}Multiplier` (default 1.0).
  The formula values were not captured. Section 7.

### 1.6 Art and sound
* **Mesh** (Confirmed): `Item_Shields.Gestalt.GestaltDef_Shields` in Startup.upk: 32 fragments, 4,014 triangles, 5,156 vertices, read by our mesh reader (L13218). Fragments: `Shield_Body_*` (8, the big ones, 94-532 triangles), `Shield_Battery_*` (8), `Shield_Capacitor_*` (8),
  `Shield_Accessory_*` (8, the long thin ones, Pangolin has two), one per manufacturer except Maliwan; which fragment a part uses is in the part (section 1.1). They sit in assembled-item space and overlap, like the guns. Size: body about 8 x 44 x 20, whole item about 12 x 45 x 35 units. `Shield_Pickup_A-1` (named by every material part) is *not* in the gestalt: the ground pickup is something else (unconfirmed what).
* **Texture** (Confirmed): materials `Item_Shields.Materials.Mati_Shield<Mfr><Rarity>` (e.g. `Mati_ShieldJakobsCommon`, `ShieldMaliwanEpic`) share **one** atlas `Item_Shields.Textures.Shield_Dif / Shield_Nrm / Shield_Comp` plus pattern overlays; the rarity/manufacturer look is material parameters. One DDS set serves every shield.
* **HUD art** (not found): the bar is the native `ShieldBarGFxObject` (`RefreshShieldBar`, `ShieldText`, `ShieldModifierText`, frames named by `ShieldTypeFlashFrameName`, `hudequippedcard_shield`, `hudpickupcard_shield`). The survey opened only 14 small UI packages
  (Bank, Stash, EchoVersion, Credits movies) and did not reach the main HUD movie. We draw our own bar anyway (the plugin already draws its ammo HUD), so this matters little.
* **Sound** (Confirmed, 43 events in the banks, decode path exists): `Ak_Play_UI_Shield_Power_Up` (1 file, 50 KB), `..._Power_Down`, `..._Confirm`, `..._Impact`, `..._Booster`, `..._Roid_Buff`, `..._Roid_Buff_Hit`, `Ak_Play_UI_Player_Shield_Absorption` (6 files),
  `..._Chimera_Switch_{Fire,Shock,Corrosive,Off}`, `..._Chimera_Damage`, `Ak_Play_FX_Player_Shield_Nova_Power_On`, `Ak_Play_FX_Player_Shield_Spike_{Fire,Shock,Corrosive,Explosive}`, `Ak_Play_Obj_Pickup_Shield(_Boost)`.
  **Not found as events:** a named break or recharge sound and the low-shield warning: the HUD object has properties `ShieldLowWarningStartAkEvent` / `...StopAkEvent` whose values the survey did not read. My guess (unconfirmed): break = `Power_Down`, recharge start = `Power_Up`, hit = `Impact`.

## 2. How each piece works in Skyrim, and why

### 2.1 Damage interception (the core)
| option | sees spell/bullet damage | sees melee, arrows | stops a killing blow | needs a vtable slot we have not checked on 1.7.104 | verdict |
|---|---|---|---|---|---|
| **A. hook `ActorValueOwner::ModActorValue` (slot 6), act on `kDamage` + `kHealth` + negative value** | yes (a magic effect that damages health ends here; `DamageActorValue` is a wrapper that calls it, CommonLibSSE-NG v12.1.0 `ActorValueOwner.cpp`) | yes (expected: melee and arrows also reach health through it; confirm in stage 1) | **yes**, the value is cut before it is applied | slot 6 of the ActorValueOwner part of `Character` and `PlayerCharacter`; the part sits at +0xB0 or +0xB8 depending on runtime, so find the table from a live actor (`AsActorValueOwner()`), do not use an assumed index of the actor | **chosen** |
| B. hook `Actor::HandleHealthDamage` (slot 0x104, your suggestion) | **no** (our bullets are spells) | yes | yes | yes | not enough alone |
| C. `TESHitEvent` + give the health back | the event has no damage number (`TESHitEvent` = target, cause, source, projectile, flags) | | **no** (dead before we can restore) | no | rejected |
| D. "overheal": shield = a temporary Health bonus, remaining shield = health above the real maximum | yes | yes | yes | no | fallback if A cannot be hooked; wrong feel (regen and healing fill the shield, the vanilla bar shows combined health) |

Choice: **A**. It is the one choke point, it works for the player and for every NPC with the same code ("absorbing must work for enemies": `Character` covers all NPCs, `PlayerCharacter` the player), and it can stop a lethal blow.
Safety (the lessons of the attack-handler hook): the hook is a pure pass-through when the actor has no shield; the first ten calls are logged (actor, modifier, value, shield state); if the log shows the arguments do not look like
(modifier 0..2, a real actor, finite value) the hook switches itself off and says so; the crash handler already reports the plugin's last stage. Stage 1 exists to prove this on the user's runtime before anything is built on it.
Unconfirmed until stage 1: that damage arrives as `kDamage` with a negative value for our bullets, that melee does too, that the player's and an NPC's tables are different tables (we patch both).

The rule (BL2): damage `d` on an actor with shield `s`: `absorbed = min(s, d)`; `s -= absorbed`; the health damage is `d - absorbed`; any hit, to shield or health, sets `lastHit = now`. When `s` reaches 0 from above, that is the **break** (sound, flash, nova on break etc.).
Option **shield-gate** (a hit that empties the shield loses its overflow) is a one-line switch in the ini; BL2 itself carries the overflow into health, so off by default.
Damage that skips shields in BL2 is not known from the survey; v1 treats all damage the same, with an ini list later (poison/fall/script damage `Papyrus DamageActorValue`) if it feels wrong.

### 2.2 State, time and recharge
Per actor, in the plugin (memory only, `unordered_map<FormID, ShieldState>` guarded by the game thread; nothing to do with Papyrus): `capacity, current, rate, delay, lastHit, type, element, special, itemFormID, rarity, flags (broken, recharging)`.
A tick (the plugin already has a 4 ms game-thread tick for the player and a 33 ms pump for beams; shields use a 33 ms pump for everybody who has a shield, within 6000 units of the player like `ScanArmed`): if `now - lastHit >= delay` and `current < capacity`, `current += rate * dt`.
Not persisted across save/load in v1 (a loaded game starts with full shields; stated, cheap, and SKSE's co-save is the later fix). Papyrus reads: `ShieldPercent(Actor) Int`, `ShieldMax(Actor) Int` (ints only: **no String parameter in any native**, the lesson of 0.15.1).

### 2.3 The numbers and level scaling (design, not BL2's own formulas)
Because the BL2 capacity formula could not be read reliably (section 1.2) and Skyrim's health scale is different, **capacity is a fraction of the wearer's maximum Health**, taken when the shield is put on and whenever Health max changes by more than 10 %:
`capacity = ratio(rarity, grade) x maxHealth`, starting ratios (to tune in play, unconfirmed against BL2): common 0.30, uncommon 0.40, rare 0.55, very rare 0.75, legendary 1.00, e-tech 1.20, grades +-30 % across a rarity.
`delay = 3.5 s` (BL2) x grade factor (0.6 .. 1.4); `rate = 0.16 x capacity per second` (BL2) x grade factor (0.6 .. 1.5). A relic bonus multiplies on top (2.6). Enemies use `ratio_enemy x maxHealth`, 0.5 normal, 1.0 for badass/named (BL2 gives bosses and badasses much more).
This makes the shield scale automatically with whatever the player or a mod does to health. Manufacturer flavour from the survey: Hyperion = long delay grade, Tediore = faster rate, small capacity (the grades in 1.2); I will keep the sign pattern and normalise the sizes.

### 2.4 Shield items
* Record type **ARMO**, one per (family x rarity x manufacturer look), made in `SkylandsGunModels.esp` (`Skylands.esp` stays byte-identical, tested). A new test checks that. The second plugin is no longer ESL-flagged, so ids are not tight.
* **Slot:** the installer scans the load order's ARMO records and takes a free biped slot among 44-61 (default 55), writes it to the ini, and the plugin reads "what is worn in that slot". Not slot 39 (the vanilla shield slot; the game also hangs the second copy of an enemy's staff-type gun under the `SHIELD` node, 0.34.x).
  Why not a fixed slot: other mods use 45-61 for capes, wings, tails, backpacks; picking from what is free in *this* install avoids a clash.
* **Numbers in keywords**, like the guns: `SkylandsShield` (marker: "is a shield", used by the Hunter and the beam sweep), `SkylandsRarity_<id>` (reused), and one grammar keyword
  `SkylandsShield_t<type>_e<element>_k<capacity per mille of max health>_r<rate per mille of capacity per second>_d<delay tenths of a second>_s<special>` (ints only; the plugin parses the keyword's own `formEditorID` member, which is proven to work on this runtime).
* **Look:** world and inventory model (MOD2/MOD4 slots) = the four parts of the roll (body, battery, capacitor, accessory) assembled from the gestalt by `gunparts._read_gestalt_part`, one atlas DDS, scaled up so it reads as a handheld device. Worn model: **none** at first (an unskinned mesh in a worn slot renders at the actor's feet; a skinned belt model is an optional later experiment).
* **Name/description:** BL2-style prefix + manufacturer + title by grade thresholds from 1.2 ("Maximal Hyperion Nova Shield"), and the stats text on the record (as the guns' enchantment text does), which is also the inventory text.
* **Equip:** the plugin listens to `TESEquipEvent` (actor, base object, equipped), looks the item up by keyword, builds or removes that actor's `ShieldState`. NPCs are given the item by the Hunter script and equipped as it already does for guns.
* **Loot:** shields join the gun lists: a tiered `SkylandsShieldList` form list per rarity for drops, chest/vendor injection later (stage 6), and the same rarity beams.

### 2.5 HUD
Drawn by the plugin into the game's HUD movie with the same `HudBuild` / `HudFrame` machinery as the ammo display (proven: the HUD works, 0.23.x). A blue bar **directly above the vanilla health bar**
(BL2 puts it beside the health bar; Skyrim's bars are bottom-centre, so "above" keeps it readable; ini `ShieldBarX/Y/W/H`). States: blue fill; brighter blue sweep while recharging; amber pulse below 25 %; white flash at the break; dim grey frame with no fill while the shield is
empty and waiting for the delay; hidden when no shield is worn (BL2 `bHideEmptyShieldBar` hides the bar for enemies that have none). Number and type tint optional. Risk: the vanilla health bar's position differs per UI mod (SkyUI, widgets); read it from the HUD clip at run time like we found the charge meters, with ini overrides.
Enemy shields on the enemy health bar (the game's `EnemyHealth` clip): a thin second bar, stage 6, medium risk.

### 2.6 Enemies (spawn, record, drop, beam)
Same life cycle as guns, in the `SkylandsHunter` watcher (it runs on every NPC):
1. **spawn:** a person who rolled a gun also rolls a shield (`shield_percent`; BL2 gives 70 % to badass and 100 % to super badass in its first play-through; for ordinary humans I suggest 30 %, named/boss 100 %; ini/sheet value, literal in the pex like `arm_percent` because a saved property keeps its old value);
   `TryShield` -> `PickShield(rarity tier by level)` from the rarity-tiered lists -> `AddItem` + `EquipItem` -> the plugin's equip listener creates the state.
2. **record:** the carried shield is the one in the biped slot (no extra bookkeeping).
3. **death:** `DeathShield` mirrors `DeathDrop`: one roll of `DropChance`, half the time the worn shield, otherwise a random one from the tier list (`ListForShield`), with `Debug.Trace("Skylands shield drop: ...")` lines like the gun drop (they proved the gun drops work). The dead body keeps nothing else (`ClearShields`).
4. **beam:** `TrackBeam/UntrackBeam` as for guns, the sweep treats `SkylandsShield` like `SkylandsGun`.
Papyrus note: a changed script gets a **new class name** and the old one is retired (`scripts.retired`), the ghost-script lesson; I will fold gun and shield into one revision of the watcher so it is renamed once.

### 2.7 Types and effects (stage 5)
The plugin already has the machinery each needs: hit and cast listeners, bullet launching, temporary visual effects, timers. With the keyword's `t` and `e`:
| BL2 type | effect | Skyrim mechanism | cost |
|---|---|---|---|
| Standard | none | the core | - |
| **Nova** (4 elements) | on break: an elemental blast around the wearer | on break, launch an explosion (an existing `SkylandsBlast_*` explosion record, radius and damage from the sheet) at the wearer | S |
| **Spike** (4 elements) | when hit with shield up: damage returns to the attacker | on absorbed damage with a known attacker (the hook's cause is not given by `ModActorValue`; use the last `TESHitEvent`/`TESSpellCastEvent` cause in the same frame), apply elemental damage to it | M (needs the attacker) |
| **Amp** (impact) | the next shot after the shield is full does bonus damage, shield drains | a "primed" flag on the state (`SPM_PrimeOnFull`) that the gun's launch code reads to scale the bullet's magnitude | M |
| **Roid** | melee bonus damage and a buff while the shield is up/after break | a temporary damage multiplier actor value while shielded (`Variable`), melee only by checking weapon type | M |
| **Absorb** | a chance to turn a shot into shield | on absorbed damage, roll; `current += d` instead of subtracting | S |
| **Booster** | shield gives bonus to fire rate/reload while up | writes the relic actor values (`Variable06/07`) while the state is up | S |
| **Juggernaut ("turtle")** | big capacity, slow, health regen | ratio x1.6, rate x0.5, small health regen per second | S |
| **Adaptive (chimera)** | switches resistance to the last element it was hit by | stores `lastElement`, applies resistance scale to the next absorbed hit of that element | M |
Resistances (per-element damage scale) need the damage's element, which `ModActorValue` does not give; the same "last hit/cast event in this frame" source serves it. Unconfirmed that the cause can be matched reliably; stage 5 starts with nova, absorb, booster, juggernaut (no cause needed).

### 2.8 Sound and feel
Break, recharge start, low warning, hit and pickup sounds from the Wwise banks through the existing extractor (`bl2/audio.py`: events -> vgmstream -> mono WAV -> SNDR records), played by the plugin like the gun sounds (`PlaySound`). Mapping guess in 1.6; the deep survey reads the real names from the HUD object.
Low-shield warning: BL2's own start/stop pair; loop while below 25 % and not empty; stop on recharge. Number of damage absorbed (floating text) stays out; the damage-number work is on hold.

### 2.9 Relics and bonuses
Actor values read by the plugin each tick, like `Variable06/07/08` (relics, `docs/relics.md`): **`Variable01` = shield capacity bonus %, `Variable02` = recharge rate bonus %, `Variable03` = recharge delay reduction %**.
In use by Skylands today: `Variable06/07/08` (relics) and `Variable10` (the old crossbow guns' stats line). `Variable01-05` and `09` are free as far as Skylands goes; whether vanilla scripts or other mods touch them is **unverified** (the guns' relics have run on 06-08 without trouble).
The plugin does not write actor values for other systems to read; they call `ShieldPercent(Actor)`.

## 3. Data model

```
keyword  SkylandsShield                      marker (Hunter, beam sweep, equip listener)
keyword  SkylandsRarity_<n>                  reused
keyword  SkylandsShield_t<type>_e<elem>_k<capacity permille of max health>_r<rate permille of capacity per s>_d<delay tenths of s>_s<special>
         type 0 standard 1 nova 2 spike 3 amp 4 roid 5 absorb 6 booster 7 juggernaut 8 adaptive ; elem 0 none 1 fire 2 shock 3 corrosive 4 explosive

plugin   struct ShieldState { capacity, current, rate, delay, lastHit, type, element, special, rarity, item, flags }   map FormID -> ShieldState
         inputs: worn item's keyword, wearer's max Health, Variable01/02/03 (bonuses), ini (gate, scales)
natives  Version, ShieldPercent(Actor) Int, ShieldMax(Actor) Int, SetShieldMode(Bool)            (no strings)
ini      Shield=1  ShieldGate=0  ShieldSlot=55  ShieldBarX/Y/W/H  ShieldRatioScale=1.0  ShieldDelayScale=1.0  ShieldRateScale=1.0  TestShield=0 (stage 1 only)
records  ARMO per family x rarity x look in SkylandsGunModels.esp ; FLST SkylandsShieldList (per rarity tier) ; SNDR per sound ; meshes Meshes\Skylands\Shield_<id>.nif ; one atlas
```
Record count: starter set of 6 families (standard, nova, spike, amp, roid, absorb) x 5 rarities x 4 manufacturer looks = 120 ARMO; all 11 families = about 220. Per-instance stats (rolled on the item with `ExtraData`, no per-variant records) stay a later option, as for the guns.

## 4. Staged build order (one test build per stage)

| stage | ships (plugin / records / script) | the user checks | exit |
|---|---|---|---|
| **1. Core** (plugin 1.16.0, no records, no script change) | the hook, `ShieldState`, recharge tick, ini `TestShield=<percent of max health>` gives the player a shield with no item, `TestEnemyShields=<percent>` gives every NPC a shield; screen messages "Shield 120 / 300", log lines for the first hits; the deep survey bat (section 7) in the same zip | log first line `SkylandsNative 3xx` = the build; "shield hook installed ..." ; get hit by a bandit with a gun (spell damage) and by a melee/arrow attacker: the message shows shield falling and health unchanged until it is 0; the remainder carries into health; 4 s of no damage later the shield refills; a killing blow on a shielded character is absorbed; an enemy with the test shield survives more bullets (count them); no crash in a fight with ten NPCs | damage path proven for spells, melee, arrows; decide hook vs fallback D |
| **2. HUD + sound** (plugin 1.17.0; audio extraction of the shield events) | the blue bar above the health bar, low-shield pulse, break flash, recharge sweep, sounds for break / recharge / low / hit; ini positions | screenshot of the bar in each state; hear the cues; bar hidden with no shield; bar follows a resolution change; log lines "hud: shield bar built" | bar and cues work with SkyUI or without |
| **3. Items for the player** (plugin 1.18.0, records, a Papyrus gift in the existing gunner quest) | ARMO shields with BL2 meshes and names, slot chosen by the installer, equip/unequip changes the state, a starter "Stock Shield" given with the guns, stats text in the inventory, keywords parsed ("shield check <id>: ... -> capacity" log lines) | the item in the inventory looks right (size, textures), equip: bar appears with the right capacity; unequip: it goes; swap shields; the numbers on the card match the bar; rarity colours | items work; texture/UV check of the atlas |
| **4. Enemies** (plugin 1.19.0, watcher script revision, lists) | spawn with a shield (chance by NPC kind), worn shield visible in the pack, death drop of the worn or a random shield with the rarity beam, `Papyrus.0.log` "Skylands shield drop:" lines, enemy shield bar (optional) | kill ten bandits: some had shields (it takes more shots), some drop shields with beams; pick one up and wear it | the same loop as guns, no ghost scripts |
| **5. Types** (several small builds: 5a nova, absorb, booster, juggernaut; 5b spike, amp; 5c roid, adaptive) | one family group per build, effects with BL2 sounds | each family's effect on a test fight | per family |
| **6. Extras** (as chosen) | see 5 | per feature | |

Rules kept in every stage: `Skylands.esp` byte-identical (test), new records only in the second plugin, no String parameter in natives, version line check ("SkylandsNative NNN loading" and "Skylands 0.x.y setup" against the build), one build per stage, decompile every new script, update `CLAUDE.md`.

## 5. Features worth choosing (ranked, costed)

| # | feature | cost | risk | recommend |
|---|---|---|---|---|
| 1 | core shield (absorb first, delay, recharge) incl. for enemies | M | **high until stage 1** (the hook) | yes |
| 2 | shield HUD bar with low/break/recharge states and sounds | M | medium | yes |
| 3 | shield items with rarity, BL2 meshes/names/stat text | L | medium (atlas, slot) | yes |
| 4 | enemies spawn with / drop shields, beams | M | low (same pattern as guns) | yes |
| 5 | types: nova, absorb, booster, juggernaut | M | low | yes |
| 6 | types: spike, amp, roid, adaptive; elemental resistance | M-L | medium (needs the cause/element of a hit) | later |
| 7 | relic bonuses via `Variable01-03` | S | low | yes (with stage 3) |
| 8 | shield-gate switch | S | none | ini only |
| 9 | "shield bypass" for chosen damage sources (poison, fall, script) | S | low | ini list, on request |
| 10 | shields in chests, vendors (leveled lists, `HealthShop` style) | M | low | stage 6 |
| 11 | shield on the enemy health bar | M | medium (UI clip) | optional |
| 12 | console-free test shield | S | none | stage 1 ini, then the starter shield in stage 3 |
| 13 | inventory text with stats | S | none | part of 3 |
| 14 | per-instance rolled shields (`ExtraData`) | L | high | not now |
| 15 | worn belt model | L | high (skinning) | not now |
| 16 | shield persistence across save/load | M | medium (SKSE co-save) | not now |

## 6. Risks (and what limits each)
1. **The hook** (section 2.1): wrong slot or a different call pattern on 1.7.104 -> crash or nothing absorbed. Limit: pass-through when idle, argument sanity check with self-disable, crash handler stage, log of the table addresses; fallback D.
2. **Which damage reaches the hook** (spell vs melee vs arrows vs fall vs poison): the log of the first hits settles it in stage 1; the design assumes all of it reaches `ModActorValue`.
3. **Cause/element of a hit is not in the hook's arguments**: spike, amp, adaptive and resistances need it; the plan is the same-frame `TESHitEvent`/cast event; may not be reliable -> those types move to "later".
4. **HUD layout** differs with UI mods (SkyUI, widgets, resolution): read positions from the HUD clip, ini overrides, hide cleanly if the clip is not found (the ammo HUD already does).
5. **Worn slot clash** with another mod: the installer picks a free slot per install; a mod added later could take it (the ini key lets the player move it).
6. **Level/health scaling** by ratio may feel wrong (too tanky or paper thin): three ini scales, tuned in the first item test.
7. **Ghost scripts and ids**: any new/changed script gets a new class name and the old one is retired; the second plugin's ids move when records are added, so a **new save** is assumed (the user already accepts it since 0.28.0).
8. **Performance**: a 33 ms pump over the NPCs in range with shields; hundreds of states are cheap, the work is in the HUD redraw (30 Hz, as the ammo HUD).
9. **Audio**: the shield events are decodable (43 found), but break/recharge/low names are guesses until the HUD object is read.
10. **Textures**: one atlas for all parts; the gestalt UVs were read (ranges listed in the report) but never rendered, so the first look at an item may need a UV or orientation fix, as the first gun models did.

## 7. The second survey (small, ships inside the stage 1 build)
The first survey answered *what exists*; these things it cut off or never reached, found while reading it. `Check-BL2-Shields-Deep.bat` (about 10 minutes), with fixes to the tool itself (package choice favoured tiny enemy packages, the object dump stopped at 70 lines, defaults of the WillowGame classes were not dumped):
1. Full, uncapped dumps of `GD_Shields.A_Item.Shield_Standard` and `Shield_Enemy_Standard`, and one balance per family (`ItemGrade_Gear_Shield_<Family>_03_Rare`) down to its accessory part and skill: the **slot-grade -> number tables**, the **type effect numbers** (nova/spike damage, amp bonus, roid bonus, absorb chance), elemental resist values, `PrimeMechanism` meaning.
2. `Init_EnemyShield_CapacityMaxValue`, `..PerPlayer`, `..OnIdleRegenDelay/Rate`, the `Weight_*` rarity weights, and the player's health formula (to calibrate the capacity ratios against BL2's own shield/health ratio).
3. The `Default__` objects of `ShieldBarGFxObject`, `WillowShield`, `ShieldResourcePool`, `ShieldDefinition` (the low-warning events, break/recharge behaviour, `bHideEmptyShieldBar`, shield-gate-like settings).
4. The HUD movie: search every package for `SwfMovie` named like a HUD (not the first 14 UI packages) and list the shield symbols inside.
5. One level-1 and one level-50 shield definition value, so the formula reading in 1.2 can be settled against known game values.

## 8. Open questions for you (my default in brackets)
1. **Hook A** as the damage choke point, with the log-only first look in stage 1? [yes]
2. **Overflow:** BL2 carries the rest of a hit into health; shield-gate off by default? [off]
3. **Which families first** (stage 5 order)? [nova, absorb, booster, juggernaut; then spike, amp, roid, adaptive]
4. **Capacity scale:** fraction of max Health with the ratios in 2.3 (common 0.30 ... legendary 1.00)? Or something closer to BL2's raw numbers after the deep survey? [fractions, retuned after the survey]
5. **Enemy spawn rates:** 30 % of ordinary humans, 100 % of named/boss; and drops: the same 25 % roll as guns? [yes]
6. **HUD position:** above the vanilla health bar, bottom centre (BL2 puts it beside the health bar)? [above]
7. **Slot:** let the installer pick a free biped slot (default 55) and no worn model at first? [yes]
8. **Starter shield:** gift a "Stock Shield" with the guns in stage 3 so no console is needed? [yes]
9. **Bundle the deep survey into the stage 1 build** (one zip, one run for you)? [yes]
10. **Persistence** of the current shield across saves: skip in v1 (shields come back full on load)? [skip]
11. **Scope of the first release:** items for the player plus enemy shields and drops (stages 1-4) before any type effects? [yes]
12. Any damage that should skip shields (poison, fall, drowning, your own explosions)? [none in v1]

Nothing will be built until you answer, or tell me to go with the defaults above.

## 9. Decisions (from the user)
* "Go with the defaults": every bracketed default in section 8 is chosen.
* **Standing rule: when a Borderlands 2 value for a shield number is found in the game files, it replaces the static (design) value.** Implemented as `sheets/shields.json`: every number has `value` (the default),
  `source` (`bl2` or `design`) and `bl2_object` (where the real value lives). `bl2/extract.shield_stats` reads the ones it can (today `delay_s` 3.5 and `rate_fraction` 0.16, from the objects the first survey showed);
  the installer writes them into the plugin's settings (`skse.shield_ini`) in place of the sheet's defaults and logs `shields: read from Borderlands 2: {...}`. The deep survey (`Check-BL2-Shields-Deep.bat`) dumps every
  `bl2_object` in full; each time its report gives a real value for a `design` row, the row becomes `bl2`, a reader is added to `shield_stats`, and a test pins it.
* Stage 1 (0.38.0, plugin 1.16.0): the core in `native/skse/src/shield.h`, settings `Shield`, `ShieldGate`, `ShieldDelay`, `ShieldRate`, `ShieldLow`, `ShieldMessages`, `TestShield` (60), `TestEnemyShields` (40); natives `ShieldPercent`, `ShieldMax`.

## 10. Stage 1 result and the change of mechanism (0.38.0 -> 0.38.1)
**Seen in the user's `SkylandsNative.log` (plugin 340):** the plugin loaded on Skyrim 1.7.104, the observer hook installed for the player (table module+192A178) and for other people (table module+1923CE8), both holding the same slot-6 function (module+6C51F0),
the ActorValueOwner part sits at +0xB8; test shields were created (player 66 of max health 110, enemies 14 of 35). Then, over a fight in which the player and several enemies took damage and the user died: **"damage to the player 0, damage to others 0, restores 282, other 0; shield absorbed 0 times"**.
The hook saw positive Health changes only. So the game's combat damage does **not** pass through the ActorValueOwner virtual slot 6 (it calls the underlying function directly), and a vtable hook there cannot absorb it. Option A of section 2.1 is disproved on this runtime; B (HandleHealthDamage) would miss spells; C cannot stop a killing blow.

**New mechanism (option D, reworked): the shield is health stacked on top of health.** When an actor gets a shield of C points, C is added to its Health as a temporary bonus (`ModActorValue(kTemporary, kHealth, +C)`: maximum and current rise by C). Every damage source lowers current Health,
so each 33 ms the plugin reads the damage taken so far (maximum minus current), books the new part: shield first, the rest is real-health damage. Recharge gives the shield's share back after the delay; healing can only heal real health (surplus is undone). The actor dies only when shield and health are both gone, so a killing blow
is absorbed while the shield holds, as in BL2; the gate switch gives back what the shield could not take. It does not depend on which function applies the damage. Costs: the vanilla health bar shows shield and health together until the shield HUD bar exists (stage 2); the bonus is a saved modifier, so the plugin keeps a co-save record of the bonuses
on actors and takes them off again after a load (`g_stale`, `Strip`); `Shield=0` stops new bonuses but does not remove existing ones (a save made with a shield on is cleaned on its next load).
The old hook remains as an observer: it counts and logs the Health changes it sees (the next log shows whether damage arrives as negative `kDamage` anywhere).
