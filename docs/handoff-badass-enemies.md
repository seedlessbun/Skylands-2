# Handoff: Badass enemies (stats, loot, dialog, effects)

Paste the "Prompt" section into a new session. Read `CLAUDE.md` first: it has the full history, rules and lessons. Everything below was checked against code or logs; anything unproven is marked "unconfirmed".

## Prompt

You are continuing Skylands, a Borderlands 2 x Skyrim SE mashup built on the player's PC from their own game files by `setup/` (nothing from either game is shipped). Read `CLAUDE.md` before anything else, then `docs/relic-roadmap.md` and `docs/shield-roadmap.md` (the shape a roadmap should have).

**The feature:** Badass variants of Skyrim enemies, like Borderlands 2's Badass / Super Badass / Ultimate Badass. They hit harder, have more health, and spawn with and drop better loot. Possibly add Borderlands 2 enemy dialog and effects later. Also adjust enemy stats and drop pools generally.

**Phase 1 is planning. Write no feature code until the user approves.**
1. Read the code that already touches enemies (list below) and the current logs in `/root/.claude/uploads/...` if any are attached.
2. Run an interview with AskUserQuestion (max 4 questions at a time) about the design choices that change the build: how common each tier is (and whether it scales with level or area), which tiers exist (Badass, Super Badass, Ultimate), which actors can be Badass (humanoids only like the guns and shields, or also creatures), the stat multipliers per tier (health, damage, speed, size), the loot bonus (rarity shift, extra drops, guaranteed drop), how a Badass is shown (name prefix, size, aura, health bar, kill message), whether dialog and effects are in this stage or later, and the difficulty target (the user tests on a new character).
3. Survey Borderlands 2 first if numbers are wanted from it (the pattern: a survey bat writes a report the user sends back; see `shieldprobe.py`, `--topic relic`, `Check-BL2-Relics-Deep.bat`). BL2 has `GD_Balance` pawn balances with Badass / Super Badass / Ultimate Badass classes (names unconfirmed: search for "badass" in the name tables and look at the `AIPawnBalanceDefinition` objects, `PlayThroughs`, `DefaultItemPoolIncludedLists`, the health and damage scale attributes, and the Badass presentation, dialog events and particle objects). The user's rule: BL2 file values replace static values.
4. Write `docs/badass-roadmap.md` with: the facts found, the design with defaults, the stages, the risks and the list of things only the game can confirm. Then wait for approval. Do not skip this wait.
5. Give a prioritised list of further features you would suggest, each with a short suggested implementation (see "Suggestions to include" below, but add your own after reading the code).

**Phase 2 (after approval)** builds in stages, one build per stage (`python tools/package_testkit.py`, bump `VERSION` in `build.py` and the TestBuild number, send one zip with SendUserFile, ask for the logs).

## What already touches enemies (read these)

- **Plugin (C++, `native/skse/src/`, CommonLibSSE-NG v12.1.0, CI-built DLL committed to `setup/skylands_setup/bin/`):**
  - `shielditems.h`: the 400 ms Pump walks `ProcessLists::highActorHandles` (40 actors looked at, 4 given per pass), `IsPerson` (ActorTypeNPC keyword, plus race editor id words), `IsBoss` (the base record is flagged unique, or level >= `ShieldBossLevel` 35), `Mix(id)` stable rolls from a form id, `kLevelFor` rarity gates (1, 3, 8, 15, 30) and `kWeight` 122:50:20:6:1, `PutOn`, and a `DeathSink` that drops or removes the worn shield 900 ms after death.
  - `relic.h`: the same pattern for relics (`EnemyRelicPercent`, `PickFor`, bosses always rare or better, drop 1.1 s after death).
  - `shield.h`: a shield is a temporary Health bonus. DAMAGE TAKEN is read as max minus current. The game does NOT keep temporary actor-value modifiers across a load, so the plugin tracks what it applied, re-applies and cleans up through a co-save record. A Badass health bonus needs the same care.
  - `main.cpp`: `CastSink` (enemy casts of our staff guns), the death sink (ammo on bodies), `ScanArmed`. `shieldhud.h` draws the enemy bar over the game's `EnemyHealth_mc` and follows `shield::RecentlyHit`.
- **Papyrus (`setup/skylands_setup/skyrim/scripts.py`):** the `SkylandsHunter` watcher (an ability every race carries) arms people with guns (70 percent, `everyone=True`), clears other weapons, and `DeathDrop` (one roll of the 25 percent `DropChance`: held gun or a random gun from `ListFor`). It decompiles only in small functions (Champollion lessons in CLAUDE.md). Changing a script's properties needs a new class name (the ghost-script lesson).
- **Loot (Python, `shields.loot` in `shields.py`, called through `relics.make`):** per-rarity leveled lists `Skylands<Kind>Tier_<n>`, `...Any`, `...Good` (level-gated), chests through the overridden `SkylandsAmmoDrop`, merchant containers (one override per container holding all stocks), the `SkylandsGunList` FLST for rarity beams (the quest's 4 s scan puts a beam on loose items).
- **Installer ini:** `skse.default_ini` / `merge_ini` (the player's values are kept while `IniVersion` is the same; new keys take defaults; `ShieldDefaultsRev` shows how to reset chosen keys once).

## Rules (from CLAUDE.md, repeated because they cost builds)

- No PR unless asked. The Melty token never appears anywhere. Never publish or upload.
- `Skylands.esp` stays byte-identical (tested); all new records go in `SkylandsGunModels.esp`. The second plugin numbers forms by position, so the user starts a NEW SAVE when the form ids move.
- Natives take no String parameters (they did not arrive on this runtime). Never call a function that takes a lock while holding that lock (it crashed 0.43.0 at data load). Do not hook `ActorValueOwner` slot 6 for damage (combat damage does not pass it).
- After every scripted edit, grep that it applied; wait for the CI DLL (check the plugin version in the first line of `SkylandsNative.log`) before trusting a build; check the setup log's first line for the version the user actually ran.
- Test command: `ESPCHECK=tools/espcheck/target/release/espcheck python -m pytest tests -q` (150 passed, 18 skipped at 0.45.1; Champollion and nifcheck tests skip unless their tools are built).
- Branch: use the branch the harness gives you; commit trailers from the system reminder.

## Suggestions to include (with a first implementation idea)

1. **Tiers and rarity of the enemy itself.** Badass, Super Badass, Ultimate Badass, decided by a stable roll on the form id (`Mix`), level gates like the loot, a cap per area so a cell is not full of them. Implementation: plugin pump, same pattern as `relic::Pump`; store the tier in a plugin map plus a co-save record so it survives a load.
2. **Stats.** Health: a temporary Health bonus (copy the shield's tracking and cleanup). Damage: the actor value `kAttackDamageMult` (and `kWeaponSpeedMult`, unconfirmed on this runtime) as a tracked modifier; the plugin's bullets can also launch with `LaunchData.power` as the player's damage relic does. Size: `SetScale` (check the collision). Speed: `kSpeedMult`.
3. **Loot.** On death the Badass rolls extra from the existing leveled lists with a rarity shift (one tier up, bosses always rare or better) and gets a guaranteed drop of one gun, shield or relic; reuse the DeathSink drop code (`RemoveItem(kDropping)` from the game thread, 0.9 to 1.1 s after death) so the rarity beams work.
4. **Presentation.** Name prefix on the actor (`SetDisplayName`, unconfirmed it survives a load), a tinted red or colored aura using our own temporary-effect meshes (the shield glow in `shieldaura.h` is the pattern, off by default because the user did not like it yet: ask), a "Badass" health bar label on the enemy bar, a kill message, a BL2 sound sting when one spawns.
5. **BL2 dialog and effects.** Dialog and shot sounds are Wwise in the install (`bl2/wwise.py`, `bl2/audio.py` already extract guns and play them as SNDR through the plugin). Enemy voice lines: find the event names by a survey (look for `Ak_Play_*Badass*`, `Ak_Play_*Taunt*`, `Ak_Play_*Death*`), cut to WAV, play at the actor with the existing `PlaySound` path. Effects: the BL2 particle systems are not readable, so use stylised meshes like the muzzle flash and shield glow.
6. **Other ideas to offer the user (pick, do not build unasked):** BL2 loot bosses and named enemies with a fixed drop (unique item per boss); enemy shields scale with the tier (shields already exist); "Rare spawn" notices on the compass or HUD; elemental enemies (a Badass with a fire or shock bullet and the matching shield type); enemy level scaling by area (`ShieldBossLevel`-style gates); a Vault Hunter kill streak or "Badass rank" meter (BL2's Badass ranks and tokens) with a plugin counter and a HUD line; "Loot midgets" style treasure enemies; raid-boss style set pieces. Say what each costs and what it risks (performance of per-actor effects, save compatibility, balance).

## Unconfirmed in the game (so far)

The damage bonus on enemies (`LaunchData.power`) was judged by eye only; relic and shield effects were only seen on the player; `SetDisplayName` and `SetScale` behaviour on people has not been tried here; creature handling (shields were removed for creatures at the user's request: humanoids and NPCs only, "just like the guns").
