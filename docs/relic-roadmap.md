# Relics: what Borderlands 2 has and how Skylands will do it

## 1. Facts from the first survey (`bl2-relic-report.txt`, 10,704 lines; BL2 calls relics "artifacts")
- A relic is an `ArtifactDefinition` built from four part lists: **Eta = Body** (`GD_Artifacts.Body.PartList_Body`: the relic's TYPE), **Alpha/Beta** (`Enable1st` / `Enable2nd` ... `Enable4th`: "effect" parts that switch the
  further effects on, `EnableFirst_Effect1..7` etc.) and **Theta = Upgrade** (`GD_Artifacts.Upgrade.PartList_Upgrade`: grade parts, `Attribute_SlotGrade_Effect2/3`). The number behind a stat is
  `Init_ModifierBase_Linear` = 1.0 x `ArtifactItemLevel` ^ 1 (the relic's level), times the part's own multiplier. Ready-made balances: `A_<Type>` (common/uncommon) and `A_<Type>_Rare` (rare and up).
- Body types of the main game and what they do (the in-game text): Vitality (health), Protection (shield capabilities), Resistance (less damage from damage types), Stockpile (ammo capacity), Strength (melee),
  Elemental (damage of one element; plus a "Status" variant), Tenacity (second wind), Aggression A-F (damage with one weapon type), Allegiance A-H (weapon capabilities of one manufacturer), Proficiency
  (weapon capabilities, per type), Afterburner (vehicle boost), Endowment (experience), Opportunity (shop timers), Deputy / Sheriff / Vault Hunter / Terramorphous / Enigma (uniques). Many DLC relics too
  (Anemone, Aster, Gladiolus "Ancient" relics with two types in one, Orchid, Sage, Iris); this plan uses the base game's only.
- Loot: `Pool_ArtifactsAll` -> `Pool_Artifacts_01_Common ... 05_Legendary` (tiers 01-02 use the plain balances, 03-05 the `_Rare` ones) -> per-type pools; the enemy gear pools (`Pool_GunsAndGear_01_Common` ...)
  reach them. The report did NOT show what each body changes (the nested behaviours stop at its depth limit), the grade numbers, or the level formula: that is `Check-BL2-Relics-Deep.bat` (the second survey).

## 2. The design, to be approved (nothing is built yet)
1. **Item**: an ARMO in its own spare biped slot (the installer's slot choice, as for shields), keyword `SkylandsRelic_t<type>_..._g<rarity>` with the numbers; one relic worn at a time (the user's choice).
2. **Effects** (the user wants all four groups): (a) gun stats = the actor values the plugin already reads (`Variable06` fire rate, `07` reload, `08` accuracy: docs/relics.md); (b) damage and magazine size: new plugin work
   (damage = scale the launched projectile's power or the enchantment magnitude per shot; magazine = the per-gun clip the plugin already keeps); (c) shield capacity / recharge / delay: the shield code reads the relic's bonuses;
   (d) health, speed, regeneration: Skyrim actor values changed by the plugin while the relic is worn (put back when it is taken off; the same "game does not keep temporary values" care as the shield bonus).
3. **Types of Skylands**: a mapping from BL2's bodies to those effects, with the BL2 numbers (the rule: BL2 file values replace static ones): Vitality -> health; Protection -> shield capacity/recharge; Resistance ->
   resistances (Skyrim resist actor values); Stockpile -> ammo/magazine; Strength -> melee damage; Elemental -> element damage on guns; Tenacity -> health regen/second wind; Aggression A-F -> damage with one gun type;
   Allegiance A-H -> fire rate/reload/accuracy for one manufacturer's guns; Proficiency -> reload/handling. The unique relics come after.
4. **Loot** (user's answers): enemy drops (dropped on the ground with the rarity beam, level-gated rarities, better from bosses; the 25 percent default drop chance), chests (the ammo-drop list), merchants; no starter relic.
5. **Stages**: 1 deep survey (this build's `Check-BL2-Relics-Deep.bat`) -> 2 relic data + items + loot -> 3 plugin: gun/shield/character effects -> 4 damage + magazine -> 5 uniques/extras.
