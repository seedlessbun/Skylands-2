# Handoff: character progression (gun XP, Skyrim skills and levels, weapon proficiencies; later Badass challenges and tokens)

Paste the "Prompt" section into a new session. Read `CLAUDE.md` first: it has the full history, rules and lessons. Everything below was checked against the code or the CommonLibSSE-NG v12.1.0 headers; anything unproven is marked "unconfirmed".

## Prompt

You are continuing Skylands, a Borderlands 2 x Skyrim SE mashup built on the player's PC from their own game files by `setup/` (nothing from either game is shipped). Read `CLAUDE.md` before anything else, then `docs/badass-roadmap.md`, `docs/shield-roadmap.md` and `docs/relic-roadmap.md` (the shape a roadmap should have: facts, design with defaults, stages, risks, what only the game can confirm).

**The problem, in the user's words:** "As of now I gain nothing from using our guns, and I would like that to change so my character can level up outside of using spells occasionally."

**The feature:** character progression for Skylands guns:
1. Gun use feeds Skyrim's own progression: skill XP, skill levels and therefore character level (Skyrim levels only from skill increases).
2. Weapon proficiencies: a per-gun-type progression of our own (SMG, assault rifle, pistol, shotgun, sniper, launcher), with bonuses as it rises.
3. LATER (the user said "I might save this feature for after our XP and Proficiency systems are in"): Borderlands 2 style Badass Rank challenges and Badass Tokens: milestones (kills by type, damage, criticals, shields broken, ...) give rank points, ranks give tokens, tokens buy small permanent stat boosts. Plan it now in the roadmap, build it last.

**Phase 1 is planning. Write no feature code until the user approves.**
1. Read the code listed below.
2. Interview the user with AskUserQuestion (at most 4 questions per call; several rounds are fine). The questions that change the build are listed under "Interview" below.
3. If numbers should come from Borderlands 2, survey first (the pattern: a survey bat writes a report the user sends back; see `shieldprobe.py --topic relic --deep`, `badassprobe.py`). The user's rule: BL2 file values replace static values. Worth surveying: BL2's XP formulas (kill XP by enemy level and type, the level curve), `ChallengeDefinition` objects (Badass Rank challenges: names, levels, thresholds, rank points), the Badass Rank / token stat list and its diminishing-returns curve. Class and group names are UNCONFIRMED: find them by name tables (`challenge`, `badass`, `exp`, `xp`, `GD_Globals`), never by guessed paths; never loop `group_objects` over hundreds of groups (lesson of 0.45.2).
4. Write `docs/progression-roadmap.md`, then WAIT for approval. Do not skip this wait.

**Phase 2 (after approval)** builds in stages, one build per stage (`python tools/package_testkit.py`; bump `VERSION` in `setup/skylands_setup/build.py` and the TestBuild number in `tools/package_testkit.py`; bump `kVersion` and `.Version` in `native/skse/src/main.cpp` and the version strings the tests assert on; wait for the CI DLL; send ONE zip with SendUserFile; ask for `SkylandsNative.log`).

## Why the guns give nothing today (facts)

- A Skylands gun is a STAFF weapon whose enchantment is the bullet, but the player never casts it. The plugin swallows the attack button (`AttackBlockHandler::ProcessButton` hook, gun mode) and fires bullets itself with `Projectile::Launch` (`main.cpp`, `Launch` / `TickGun`). No game action happens, so the game awards no skill XP. Vanilla staffs give no skill XP anyway (as far as known; unconfirmed whether some school XP comes from a staff hit).
- Skyrim's character XP comes only from skill increases. Each skill-up adds the new skill level to the character's XP; the player levels up when that passes the threshold.

## Hook points that exist (read these before designing)

- **Skill XP, the clean way:** `RE::PlayerCharacter::AddSkillExperience(ActorValue a_skill, float a_experience, TESForm* a_advanceObject = nullptr, std::uint32_t a_advanceAction = 0)` (`PlayerCharacter.h:731`). This is what the game itself uses: skill-ups, the level-up message and character XP follow by themselves. Its address on 1.7.104 is UNCONFIRMED: log the skill's level/xp before and after the first call.
- **Skill data, to read for the HUD and logs:** `player->GetPlayerRuntimeData().skills->data` (`PlayerSkills::Data`): `xp`, `levelThreshold` (character), and per skill `skills[i].level / xp / levelThreshold` (`Skill` enum kOneHanded ... kEnchanting). Writing these directly is possible but skips the game's skill-up logic: prefer `AddSkillExperience`.
- **Where the player's shots happen:** `main.cpp` `TickGun` → `Launch` (player path; the gun's numbers come from its keyword, `GunInfo`, including type, element, pellets, rarity keyword `SkylandsRarity_<n>`).
- **Hits:** `voices.h` already has a `TESHitEvent` sink; `a_event->source` is used there to find the element of a Skylands bullet. What `source` holds for a plugin-launched bullet (the staff weapon or its enchantment) is only partly known: log it for the player's hits before relying on it. `TESHitEvent` carries no damage amount (CommonLib headers).
- **Damage done:** the shield code reads damage taken as max minus current Health per update (`shield.h`); the same trick can measure the player's damage to an enemy, if damage-based XP is wanted.
- **Kills:** `TESDeathEvent` (`actorDying`, `actorKiller`), sinks in `main.cpp` (`DeathSink`), `shielditems.h`, `relic.h`, `badass.h` (`CreatureDeathSink`). `badass::TierOf(id)` gives the Badass tier of the dead, `badass::ClassOf` the enemy class (people, creatures, dragons, from `SkylandsEnemies.txt`), `shielditems::IsBoss` bosses.
- **Player stat bonuses already wired (use these for proficiency and token bonuses):** `docs/relics.md`. The plugin reads the player's spare actor values `Variable01` shield capacity %, `Variable02` recharge rate %, `Variable03` delay shortened %, `Variable04` magazine %, `Variable06` fire rate %, `Variable07` reload %, `Variable08` accuracy %, `Variable09` damage %. These are GLOBAL (all guns). Per-type proficiency bonuses should be applied inside the plugin per gun type (multiply in `GunInfo` at fire time), not through these values, or relics and proficiencies will fight over one value. `relic.h` `Move` shows how to keep a tracked temporary modifier (the game drops temporary modifiers on a load: re-apply after every load).
- **Saving progress:** SKSE co-save records chained through `shield::g_extraSave / g_extraLoad / g_extraRevert` (vectors; `despawn.h` 'DSPN' and `badass.h` 'BDAS' push into them). Give the progression its own record with a version number from the first build.
- **Settings:** `setup/skylands_setup/skse.py` `default_ini` / `merge_ini`: the player's values are kept while `IniVersion` is the same; new keys get defaults; a `...Rev` key (see `ShieldDefaultsRev`, `DropTossRev`) puts chosen keys back to new defaults once. Numbers for the design belong in a `sheets/*.json` sheet (`python tools/gen.py` regenerates `sheet_data.py`), with `source: bl2` or `design`.
- **On-screen text:** `RE::SendHUDMessage::ShowHUDMessage` (plain notices, used by the ammo text), and the plugin's own HUD clip drawn into the game's HUD movie (`HudFrame`, `shieldhud.h`). Anything that writes into Scaleform MUST run as an `AddUITask` inside the SEH `Guarded` wrapper (`QueueHud`): writing from an ordinary task crashed 0.48.1.

## Interview (questions that change the build)

1. **Which Skyrim skill(s) do guns train?** Options: all guns → Archery (closest fit; its perks could then also be made to boost guns); per type (pistol/SMG → One-Handed, rifle/sniper → Archery, shotgun → Two-Handed, launcher → Destruction); or a skill chosen per Vault Hunter class. Also: which skill a shield or a relic trains, if any (Block? Alteration?).
2. **What earns XP?** Per shot fired (easy to farm), per hit (needs the hit event's source checked), per damage dealt, per kill (by enemy level, Badass tier and boss), or a mix. How fast compared with vanilla (a target such as "a level every N fights").
3. **Direct character XP from kills** (Borderlands style), on top of or instead of skill XP? Skyrim has no kill XP; adding to `data->xp` and calling the level-up check is possible but bypasses the skill design. Ask whether character level should follow BL2's kill XP curve.
4. **Should Skyrim's perks act on guns?** E.g. Archery's Overdraw = gun damage, Eagle Eye = aim zoom, Quick Shot = fire rate, Steady Hand = sway, Power Shot = stagger. Each is a check in the plugin (`HasPerk`) plus a multiplier; ask which ones.
5. **Weapon proficiencies:** one track per gun type (6) or per manufacturer too? Levels and cap (Borderlands 1, not BL2, had weapon proficiencies: per type, rising with kills/damage, giving accuracy, reload, fire rate, damage). What each level gives, whether it shows on the HUD or only as notices, whether it is per character (co-save) only.
6. **Badass challenges and tokens (later stage):** keep BL2's list of challenges and rank points as surveyed, or a smaller Skylands list; how tokens are spent (a power that opens a menu, a message box with choices, automatic random picks like BL2's "pick one of two"); which stats tokens raise (BL2: max health, shield capacity, shield recharge delay, shield recharge rate, melee damage, grenade damage, gun accuracy, gun damage, fire rate, recoil reduction, reload speed, elemental effect chance, elemental effect damage, critical hit damage: verify by survey); whether it is per character or shared (BL2 shares it across characters; Skyrim saves would need a file of our own).
7. **Difficulty target and other mods:** how fast the user wants to level, and whether they run XP/level mods (Experience, Leveling Freedom, ...) that would double up.

## Design sketch to refine with the answers (defaults to propose, not decisions)

- **Stage 0 (survey, python only):** BL2 XP formulas, challenge definitions, the token stat list and curve. A report the user sends.
- **Stage 1, skill XP from guns (plugin only):** in `TickGun`/`Launch` count shots, in the hit sink count hits by the player with a Skylands bullet, at a kill by the player add a kill bonus scaled by enemy level, Badass tier (`badass::TierOf`) and boss; give it to the chosen skill with `AddSkillExperience` at most a few times a second (batch the amounts). Ini: `GunXP=1`, `GunXPSkill` (actor value number, no strings in natives), `GunXPPerHit`, `GunXPPerKill`, `GunXPLevelScale`. Log the first calls with the skill's level/xp before and after. No Papyrus change.
- **Stage 2, perks on guns (plugin only):** read the player's perks (`HasPerk` with Skyrim.esm form ids from a table) and multiply the gun's numbers in the plugin.
- **Stage 3, proficiencies:** a plugin table per gun type (points, level), points from the same events as stage 1, bonuses applied per type at fire time, co-save record 'PROF' v1, notices on level-up ("SMG proficiency 4: +4% fire rate"), maybe a HUD line under the ammo display.
- **Stage 4 (later), Badass Rank:** challenge counters in the plugin (events already exist: kills by type, Badass kills, criticals if a head-hit test is added, shields broken from `shield.h`, damage), rank points, tokens, a way to spend them, bonuses through the plugin's own multipliers (and shield/health through the existing Variable/Health paths), co-save record.

## Risks to write into the roadmap

- `AddSkillExperience` address and behaviour on 1.7.104 (UNCONFIRMED; first build must log before/after values and fail safe).
- Too much XP: per-shot XP with a 900 rounds-a-minute SMG levels a skill absurdly fast; cap per second and per kill.
- Temporary actor-value modifiers vanish on a load (proved for shields): any bonus kept as a modifier must be re-applied after a load and taken off before a save is changed; prefer plugin-side multipliers.
- Relics already use `Variable01..09`: proficiencies and tokens must not overwrite them.
- New records shift the second plugin's form ids (the user accepts a new save when that happens, but say so); Papyrus property changes need a new script class (ghost scripts); the plugin stays string-free in natives.

## Rules (from CLAUDE.md, repeated because they cost builds)

- No PR unless asked. The Melty token never appears anywhere. Never publish or upload without a go-ahead.
- `Skylands.esp` stays byte-identical (tested); all new records go in `SkylandsGunModels.esp`.
- Natives take no String parameters. Never call a function that takes a lock while holding that lock (0.43.0). Do not hook `ActorValueOwner` slot 6 for damage. Scaleform only from `AddUITask` inside `Guarded`.
- After every scripted edit, grep that it applied; wait for the CI DLL (commit "SkylandsNative.dll built by CI from <sha>", check the strings) before packaging; check the first line of `SkylandsNative.log` and of `skylands-setup.log` for the version the user actually ran.
- Tests: `python -m pytest tests -q` (183 passed, 20 skipped at 0.53.1; Champollion, espcheck and nifcheck tests skip unless their tools are built).
- Branch: the branch the harness gives you (check it is not behind the latest work); commit trailers from the system reminder.

## Current state at handoff

- Version 0.53.1, TestBuild-165, plugin 1.29.1 ("SkylandsNative 395"). Last confirmed in game: Badass tiers, names, sizes, drops, creature drops and the creature stat floor; the drop toss worked in 0.53.0 (12 "toss: ... kicked" lines) but was too weak; 0.53.1 makes it stronger and kicks again an item that moved under 30 units (UNCONFIRMED in game).
- Open in `CLAUDE.md` section 7 and the Badass roadmap: a Giant seen with 132,975 maximum health before any bonus (not explained).
