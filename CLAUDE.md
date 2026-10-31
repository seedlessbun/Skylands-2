# CLAUDE.md

Notes for a fresh session. Everything here was checked against the code or a log from the game; things that are only
suspected are marked "unconfirmed".

## 1. Project
- Skylands is a Borderlands 2 × Skyrim SE mashup, built on the player's PC from their own game files by `setup/`.
  Nothing from either game is shipped.
- A Melty listing comes later. Never upload or publish without an explicit go-ahead.

## 2. Standing rules
- The Melty token (`llc_…`) never appears in files, commits, screenshots, logs or replies.
- No PR unless the user asks.
- Don't use `pkill -f`.
- Commit trailers (use whatever the current system reminder gives; last seen):
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01JsqA4yJHWZFYHUfPM91Vca`.
- Work on branch `claude/borderlands-skyrim-mashup-4946r6`.
- SKSE is a dependency since 0.14.0 (the user decided; Skylands never ships SKSE or Address Library, the player installs them).
  `setup/skylands_setup/skse.py` checks them and the installer logs `skse:` lines; the Skylands plugin is `Data/SKSE/Plugins/SkylandsNative.dll`
  (source `native/skse`, built by `.github/workflows/skse-plugin.yml` on GitHub Actions, which commits the DLL to `setup/skylands_setup/bin/`).
  Plain Papyrus workarounds for what SKSE does are to be removed, not kept (the staff gun's already are).
- The user tests on an EXISTING character (see the ghost-script lesson below).
- `Skylands.esp` stays light and byte-identical: a test builds with and without shooting and compares the bytes
  (`tests/test_generate.py`). All new content goes in `SkylandsGunModels.esp` (`generate.MODELS_PLUGIN`).
  Earlier growth of `Skylands.esp` broke saves (lost powers and guns).
- Script `.pex` files may change without touching `Skylands.esp`.

## 3. Layout (`setup/skylands_setup/` unless noted)
- `generate.py`: builds both plugins and writes scripts. Rounds, Gunner, `make_gunner`, `make_staff_smg`, `staff_donor`.
- `models.py`: gun meshes (native BL2 parts to NIF), hold/size constants, `staff_hold`.
- `skyrim/scripts.py`: hand-assembled Papyrus (`gunner`, `gunner_quest`, `staff_gun`, `retired`, the watcher).
- `skyrim/esp.py`: plugin writer (`Plugin`, `Rec`, `vmad`). `skyrim/pex.py`: `.pex` writer. `skyrim/nif.py`: NIF writer.
- `bl2/`: reads Borderlands 2 packages (extract, meshes, textures, `shooting_of`). `build.py`: installer entry, `VERSION`.
- `sheets/` (repo root): design JSON; `sheet_data.py` is generated from it. `docs/`: `bl2-shooting.md` and notes.
- `skse.py`: SKSE/Address Library detection, plugin staging. `native/skse/`: the C++ plugin (CommonLibSSE-NG). `.github/workflows/skse-plugin.yml`: its build.
- `tools/`: `gen.py`, `package_testkit.py` (zip + install bats), `espcheck/` (Rust), `nifcheck/` (C++).
- `tests/`: pytest; `fake_skyrim.py` / `fake_bl2.py` build tiny fake installs.

## 4. Build and test
Run from the repo root (needs `pytest`, `lz4`):

    CHAMPOLLION=<path>/Champollion ESPCHECK=<path>/espcheck NIFCHECK=<path>/check python -m pytest tests -q

Tests that need a tool skip when its variable is unset; with all three set, 115 passed at 0.15.0 (the DLL test needs the CI-built DLL of the same plugin version).
Rebuild the tools if they are gone:
- Champollion (decompiler): `git clone https://github.com/Orvid/Champollion`, then
  `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build` (needs Boost program_options);
  binary `build/Champollion/Champollion`.
- espcheck: `cd tools/espcheck && cargo build --release` (`target/release/espcheck`).
- nifcheck: see `tools/nifcheck/README.md` (nifly + `g++`; binary `check`; in a fresh container also `apt-get install catch2` and build only `--target nifly`).

Other commands:
- `python tools/gen.py` regenerates `sheet_data.py` from `sheets/*.json` (`--check` tests it is current).
- `python tools/package_testkit.py` builds `dist/Skylands-TestBuild-N.zip`. Each time, bump `VERSION` in `build.py`
  and the TestBuild number in `package_testkit.py`.
- Send ONE build per stage unless the user asks for more.
- Decompile every new script with Champollion and read the output; tests in `tests/test_pex.py` assert on it.

## 5. Hard-won lessons (each cost builds)
- **Type mismatch:** passing a derived type where a base type is expected fails with "Type mismatch for argument 1"
  and the call returns nothing. Seen in the Papyrus log for Actor to `ObjectReference` (`RegisterForAnimationEvent`)
  and Spell to Form (`HasSpell`); earlier for Ammo to Form (`AddItem`). Cast to a base-typed variable first
  (`RndF`, `ref`, `f` in `scripts.py`).
- **Not bound without SKSE:** `Form.GetName` (log: "Unbound native function GetName"). `Weapon.GetWeaponType` read 0 in
  game. `Input.GetMappedKey` / `Input.IsKeyPressed` were never confirmed unbound (unconfirmed); removed to be safe.
  `Form.GetFormID`, `RegisterForAnimationEvent` and `OnAnimationEvent` work.
- **Ghost script objects:** the second plugin numbers its forms by position (`Plugin(ids=None)`), and a save keeps old
  script objects of the same class running with old or empty properties (log: "no native object bound",
  "<nullptr form>"). When a script's properties or logic change: give the class a new name
  (`generate.STAFF_SCRIPT`), overwrite the old file with `scripts.retired(...)`, and bump `STAFF_ID_SHIFT`.
- **Quest start (unconfirmed):** a quest added to a plugin the save already knows did not visibly start in one test and
  did in another. The quest script prints "Skylands quest started" and "Skylands: ability added" so you can see.
- **CNAM:** copying a donor weapon's `CNAM` (template) gave the donor's model. `make_staff_smg` drops it; the model then
  showed correctly in game.
- **Donor staffs:** the game crashed at the splash screen when the donor was `DA15Wabbajack` (scripted quest artifact);
  it loaded once only plain staffs were allowed (`staff_donor`). That it was the sole cause is not proven.
- **Champollion hangs** (or prints "Skipped inoperative debug function") on early-exit jumps and branches that share
  one exit label. Split into small functions with single-condition `if`s; use `ret_if` / `ret_unless`.
- **Papyrus log:** set `bEnableLogging=1`, `bEnableTrace=1`, `bLoadDebugInformation=1` under `[Papyrus]` in
  `Documents\My Games\Skyrim Special Edition\Skyrim.ini`. The newest log is `Papyrus.0.log`.
- **Dead ends:** speeding up the crossbow cycle with `WeaponSpeedMult` and detecting shots with `OnPlayerBowShot` or by
  counting ammo never produced shot messages in game (cause unknown); the crossbow gunner code is still in `scripts.gunner`.

## 6. Current status
- Staged move from crossbow-based guns to per-type base weapons: **Stage 1**, version **0.15.0**, TestBuild-85
  (`Install-Skylands-GunModels-Shooting-Staff.bat`, `--gun-shooting staff`): SMGs and assault rifles are staff guns (see 0.15.0 below).
- Confirmed in game (0.13.11, log and screenshot): quest starts, ability added, staff given, box on equip (events registered,
  script weapon and spell set), shots counted from the cast event, reload (unequip/re-equip) happens. The Papyrus log had no
  error from the staff script; its errors were SkylandsHunter (`AbilityInit`, `GetContainer`) and a ghost `SkylandsGunnerQuest`.
- Seen wrong in 0.13.11: the projectile looked like the vanilla staff's (art is the donor fireball, placeholder; whether the
  6667 speed applied is unconfirmed), holding the button did NOT repeat, the model pointed up or down (turn `-45,0,180`).
- 0.13.12 (burst): confirmed in game, reload and burst worked; hold did not repeat; the cast has a wind-up; the model pointed
  straight up at turn `-45,0,180`.
- 0.13.13 (TestBuild-76): the staff's enchantment is now an aimed concentration cast of `SkylandsStaffSMG_Trigger` (no projectile,
  no damage, no cost, no charge time); `SkylandsStaffSMG_Bullet` (fire and forget, our tracer `Meshes\Skylands\Tracer_StaffSMG.nif`
  from `nif.tracer`, element colour, no muzzle flash) is cast by the script. Script `SkylandsStaffGun13`: `BeginCastRight`
  (or `MRh_SpellAimedConcentrationStart`) = trigger pulled, `Press` -> `Hold` fires `Pull` at once and every `Interval` while
  `Holding`; `MRh_SpellFire_Event` or `MRh_SpellRelease_Event` = let go (UNCONFIRMED: web notes say the spell-fire event ends a
  concentration cast; the box names every event received). Ids skip 120. Model turn default `45,0,180` (a guess; `-135,0,180`
  is the other way). Unconfirmed in game: that a concentration cast with no projectile starts at all, the release event, the
  wind-up being gone, the tracer's look and speed.
- 0.13.13 in game: the game CRASHED on firing (hold: a few tracer bullets, then crash; a single click after a reload: crash).
  Tracers did show (the fireball is gone). The model faced properly at turn `45,0,180`. No crash log was available, and the
  Papyrus log cannot show a native crash. Suspected cause (unconfirmed): the trigger effect was an aimed concentration cast with
  NO projectile (`MGEF` projectile 0); the game builds such a cast around its projectile. Evidence for it: 0.13.12 (same
  bullet, same tracer-less path, fire-and-forget staff cast) did not crash; the only changes were the concentration trigger,
  the tracer and the loop; the tracer itself did spawn.
- 0.13.14 (TestBuild-77): the trigger is a copy of a vanilla concentration effect (`trigger_donor`: `*ConcAimed`, e.g.
  `FireDamageConcAimed`) with a copy of its projectile (our tracer model, no light, sound or explosion), made harmless (cost 0, not
  hostile or detrimental, no hit or enchant shader). If the game has none the staff gun is not built (logged). The model is
  25% bigger (`STAFF_SCALE`) and moved 10% of its length forward along the barrel and 10% up (`STAFF_FORWARD`, `STAFF_LIFT`;
  the directions are computed from the turn, unconfirmed in game). Script `SkylandsStaffGun14`, ids skip 144.
- 0.13.14 in game: no crash any more (the projectile-less trigger was the likely cause); hold fires; the model faced forward;
  bullets left from the player's FACE (`Spell.Cast` from the player); a fireball floated above the gun; reload (unequip, wait,
  re-equip) was slow and "Equipped: id ..." showed twice; the per-shot magazine message cluttered the screen.
- 0.13.15 (TestBuild-78): the charge gauge is the magazine (`RightItemCharge` actor value, written by `Sync` after every shot and
  by `Fill` ten times during a reload; weapon `EAMT` = clip x `STAFF_CHARGE_PER_SHOT`; UNCONFIRMED that the value is writable
  and shows on the HUD, the equip box prints what the game reads back). A reload no longer unequips: the gauge refills over
  the reload time. The per-shot message is now every 10 shots (`Count`/`Tell`). Bullets are cast from an invisible aim point
  (ACTI `SkylandsStaffAim`, `Place`/`Fire`: 40 ahead, 14 right, 0.85 height - 10 up, turned like the view); `--staff-origin face`
  goes back to casting from the player. UNCONFIRMED: that `Spell.Cast` from a placed object fires along its angles, where
  the bullets appear. `quiet_art` strips casting light/art, enchant shader/art and dual casting art from the trigger and the
  bullet (and hit art from the trigger): the fireball floating above the gun was most likely the casting art (unconfirmed).
  The box and "Equipped" messages carry a per-copy tag (`Tag`) so two copies of the script running would show. Script
  `SkylandsStaffGun15`, ids skip 168.
- 0.13.15 in game: charge was spent and the weapon sounded, but NO projectile appeared (the aim point does not work as a
  `Spell.Cast` source: no 3D from an empty nif, or no target for an aimed cast: unconfirmed which); one pull fired the
  whole magazine and could not be stopped (no release event arrived: neither `MRh_SpellFire_Event` nor
  `MRh_SpellRelease_Event` ends the concentration cast); holding showed a steady fire stream (the trigger's flame projectile);
  the "Equipped" message showed twice, once with an id one lower: that is the staff's ENCHANTMENT (created just before the
  weapon, so id - 1) announced as equipped, not a second staff (`tests/test_generate.py` asserts weapon id = enchantment id + 1).
- 0.13.16 (TestBuild-79): bullets are cast from the player again (default `--staff-origin face`; `aim` kept, known not to
  show a projectile). The loop reads the game's animation variables each step: after the first bullet, every next one needs
  `GetAnimationVariableBool("bWantCastRight")` or `("IsCastingRight")` true (`Held`/`Down`); when neither is, the box tells all
  three values (`bRitualSpellActive` too) as "trigger let go". UNCONFIRMED that these variables exist and work in
  vanilla Papyrus (web notes only; if they do not, a pull fires one bullet and the message shows false values). The reload is
  a delay of `ReloadTime` with the gauge empty, then full (`Reload`). The trigger's projectile is a speck
  (`TriggerDot_StaffSMG.nif`, range 24, no flame sounds) so the held cast shows no stream. The "Equipped" message is told for
  weapons only. Script `SkylandsStaffGun16`, ids skip 192.
  Champollion segfaulted on a function with several returns and labels (`Down`, first version): keep one `Return` at the end.
- 0.13.16 in game (user report, no log or screenshot yet): one pull of the trigger fired 2 bullets (so the held check, or the
  loop, ended after the second; which animation-variable values the "trigger let go" message showed is not known), reload
  worked (4 s delay, then full), and holding the trigger STILL casts a fire spell (the speck projectile did not remove it; cause
  unknown: the donor effect's remaining art or sound, or the flame-type projectile itself).
- 0.14.0 (TestBuild-80): SKSE added (see the standing rule and `docs/skse.md`). `skse.py` (installer checks, `Check-SKSE.bat`), `native/skse`
  (plugin `SkylandsNative`: `TriggerHeld`/`TriggerPressed` from the input event of "Right Attack/Block", `FireBullet` =
  `Projectile::Launch` of the bullet spell from `NPC R MagicNode [RMag]`, aimed at the crosshair 3000 units ahead within the
  spread), `SkylandsNative.pex` (`scripts.native_stub`, declares the natives: SKSE needs it), the staff script rewritten
  (`SkylandsStaffGun17`: polls `TriggerPressed` 30 times a second while armed, fires at once and every `Interval` while held,
  gauge = `WornObject.SetItemCharge` 100 a round, reload = delay then full, box shows SKSE version, plugin loaded or not, gauge
  read-back, `Resume` arms a staff already in hand). Removed: animation events and variables, `RightItemCharge`, aim point,
  `--staff-origin`, unequip reload. The trigger effect is still a concentration cast (the cast pose) of a donor flame effect, now
  with no-hit flags and no impact data (the fire the user saw while holding is still unexplained). Hunter script fixes from the 0.13
  Papyrus log: `Bootstrap` used `AbilityInit` instead of `::AbilityInit_var` and passed a Spell to HasSpell, `Spawn`/`RespawnOne` lacked
  `::nonevar`, `Alive` called a `GetContainer` that Skyrim does not have. The DLL is built by CI (run 2 succeeded; the CI commit is
  `SkylandsNative.dll built by CI`); `git pull` after a push that touches `native/skse` (use `[skip ci]` for comment-only changes).
  UNCONFIRMED in game: that the DLL loads (needs SKSE + Address Library for the user's runtime, which the user must install), that
  `SKSE.GetPluginVersion` sees it, that the attack-button listener works, that the bullet leaves the hand and goes where the crosshair
  points, that `WornObject.SetItemCharge` moves the bar. If the plugin does not load, read `Documents/My Games/Skyrim Special
  Edition/SKSE/skse64.log` and `SkylandsNative.log` (both in that SKSE folder).
- 0.14.1 in game: "failed to open address library file" on Skyrim 1.7.104 (user's runtime; SKSE 2.3.1; `versionlib-1-7-104-0.bin`):
  CharmedBaryon's CommonLibSSE-NG picked the SE file name. 0.14.1 patched that; then "unsupported address library format: 5".
  0.14.2 (TestBuild-82): the workflow now clones alandtse/CommonLibSSE-NG v12.1.0 (reads format 5; the CharmedBaryon one cannot). The
  plugin is 1.0.2. Never build the plugin against the old CharmedBaryon library again. UNCONFIRMED: that the plugin then loads and
  works on 1.7.104 (vtable and struct layouts of 1.7 vs the library).
- 0.14.2 in game (user report + screenshot): the plugin LOADS on Skyrim 1.7.104 with SKSE 2.3.1 (box: "SKSE 2.3.1, Skylands plugin:
  loaded", magazine 48 of 48, gauge 4800); firing works well: one click one bullet, held fires rapidly, reload after the magazine,
  the staff gun in the right hand pointing forward. Wrong: bullets left from where the TOP OF THE STAFF would be (the
  `NPC R MagicNode [RMag]` follows the staff's tip, not the gun), the charge bar no longer dropped (`WornObject.SetItemCharge` alone does not move the HUD bar; the
  `RightItemCharge` actor value did in 0.13.15), and the staff's casting animation played while the button was held.
- 0.14.3 (TestBuild-83, plugin 1.0.3): the gun's mesh holds an empty NiNode `SkylandsMuzzle` at the end of the barrel (`nif.gun(muzzle=)`,
  the point followed through roll, pitch, yaw, shift and fit in `models._build`), and `FireBullet` starts the bullet there (fallback: the hand's
  magic node, then a point ahead of the eye; the first use logs "bullet origin: ..." to SkylandsNative.log). `Sync` sets the
  `RightItemCharge` actor value AND `WornObject.SetItemCharge`. While the staff is in the hand the script switches the player's fighting controls
  off (`Game.DisablePlayerControls(fighting)`, `Grip`; back on in `Let` when the staff is unequipped or on a load without it, tracked by
  `ControlsOff`), so the attack button casts nothing and plays no animation; it also draws the weapon (`Actor.DrawWeapon`), since R no longer works. The plugin
  also accepts the attack button by its mapped key when the event has no name (controls that are off may not name their events; UNCONFIRMED). Script
  class and the plugin records are unchanged (no new ids): the existing staff stays. UNCONFIRMED in game: that the muzzle node is found,
  that the bar drops, that the animation is gone, and that the plugin still sees the attack button while fighting controls are off. If a
  save keeps the controls off after the plugin or script is removed: console `enableplayercontrols`.
- 0.14.3 in game: bullets leave from a better spot (the muzzle node works), the charge bar works, removing the player's fighting
  controls removed the animation and felt more realistic, but the controls stayed off until the gun was put away (the user wants them
  back when not shooting); the gun aims a little high.
- 0.14.4 (TestBuild-84, plugin 1.0.4): `--staff-turn` default 60,0,180 (more pitch lowers the barrel: -45 up, 45 a little high). No more
  `DisablePlayerControls`: the plugin hooks the game's `AttackBlockHandler::ProcessButton` (vtable slot 4, 6 from 1.7.99 on) and does not
  pass it the right attack button while `SkylandsNative.SetGunMode(true)` (set by `Grip`, cleared by `Let`; the plugin starts with it off, so a
  save cannot keep it on). Block, shouts and readying work normally. `Heal` gives back fighting controls a 0.14.3 save left off
  (`ControlsOff`). UNCONFIRMED in game: that the hook is safe on 1.7.104 (slot 6) and swallows the attack; if the game crashes on the first press, the slot is wrong.
- 0.15.0 (TestBuild-85, plugin 1.1.0), the user chose "option A": every SMG and assault rifle variant has a staff twin (`generate.Armory`:
  same parts, rarity, element, stats, name and model as the crossbow variant, built inside the crossbow loop; 0.15.0 made twins and overrode the
  loot lists, 0.15.1 converts the variant itself, see below; `Skylands.esp` stays byte-identical, tested). Enemies are armed and drop from the same lists (the watcher is
  unchanged; staff guns carry the `SkylandsGun` keyword), the rarity beams come through an override of the `SkylandsGunList` FLST. Pistols,
  shotguns, snipers and launchers stay crossbows. The staff's enchantment IS the bullet (one hostile aimed fire-and-forget effect, magnitude =
  damage, per-gun MGEF carrying the stats text; projectile shared per type x element with a tracer in the element's colour; the blast is shared
  with the crossbow rounds, `Rounds.expl` now caches). The old concentration trigger and `trigger_donor` are gone (the plugin swallows the
  attack button, so no cast pose is needed). Each gun has a keyword `SkylandsGun_c<clip>_i<ms>_r<ms>_s<spread*10>_b<burst>` that the plugin
  parses (`GunStat`); the script `SkylandsStaffGun18` is generic (retire 17, `STAFF_ID_SHIFT` 300, gives two staff guns once as `GiftA/GiftB`).
  Plugin API now: `Version, SetGunMode, TriggerHeld, TriggerPressed, GunClip, GunIntervalMs, GunReloadMs (Weapon -> Int), FireGun(Actor, right, up, forward)`
  (`FireBullet` removed). Enemies: a `TESSpellCastEvent` sink; when a non-player actor casts the enchantment of the gun in its hands the
  plugin launches `burst-1` more bullets from the muzzle, one per interval, at `currentCombatTarget` (2x spread). Notes in `docs/enemy-ai.md`.
  UNCONFIRMED in game: that the cast event arrives for NPC staff casts with the enchantment's id (the first eight casts are logged in
  `SkylandsNative.log`), that ordinary bandits use a staff gun at all, that `Projectile::Launch` accepts an enchantment as the spell, that the
  per-gun keyword editor ids are readable at run time, the loot mix, gun ids across builds (the second plugin numbers by position, so a gun
  set that changes between builds can change which gun an id is; an old character's earlier staff SMG is gone with 0.15.0).
  Champollion: a function with a `jmpf` over one assignment then more code gave "Skipped inoperative" (`Load`); `Fresh` (jmpf, return, label) is the pattern that decompiles.
- 0.15.0 in game (user report, no log yet): the rapid fire was gone for both the SMG and the assault rifle: the staff's own charging
  animation played on a click and the charge bar no longer moved. That is the unarmed/left-hand picture (gun mode off, or the gun in the LEFT
  hand where "right attack" is not the gun's button and `RightItemCharge` is not its bar). Not proven. Suspects, in the order they were
  hardened in 0.15.1: (1) the staff weapon kept the vanilla staff's equip slot "either hand", so with a gun in the right hand it went to the left;
  (2) the plugin read keyword editor ids through the VIRTUAL `GetFormEditorID` (a slot that may have moved on 1.7.104) and found no
  `SkylandsGun_` numbers, so `GunStat` read 0 and the script never armed.
- 0.15.1 (TestBuild-86, plugin 1.1.1; 0.15.2 / TestBuild-87 / plugin 1.1.2 follows): `ETYP` of every staff gun is EQUP RightHand (0x00013F42, `STAFF_EQUIP_SLOT`); the plugin reads the
  keyword's `formEditorID` member and logs "gun check <id>: N keywords [names] -> clip ..." for the first weapons it looks at; `Sync` also sets
  `LeftItemCharge`; the equip box says which hand holds the gun and the interval the plugin read; equipping the gifted SMG when the plugin
  does not know it says so on screen. If it still fails: read `SkylandsNative.log` ("gun check" lines) and the box.
- 0.15.1 also changes HOW the SMGs and rifles become staff guns (the user still saw crossbow SMGs/ARs spawning and dropping, probably with the
  0.15.0 build and/or copies already generated into saves): no twins and no overridden loot lists any more. `Armory.add` overrides the crossbow
  record itself in `SkylandsGunModels.esp` with the SAME form id (a staff weapon over the crossbow one; `Skylands.esp` still holds the crossbow
  and stays byte-identical), so the tier lists, the beams' FLST, every copy in a save and every gun an enemy carries are staff guns. Staff gun
  ids are therefore Skylands.esp's stable ids. The MGEF/ENCH are `Staff_<edid>` (second plugin, positional ids). Report key `staff_converted`.
- 0.15.1 in game (log `SkylandsNative.log`): the plugin loaded, hooked the attack handler (slot 6), registered both listeners, and READ THE KEYWORDS
  CORRECTLY ("gun check FE003C0A: 5 keywords [... SkylandsGun_c20_i170_r3600_s19_b4] -> clip 20 ..."), enemies cast and got their bursts
  ("enemy FF000E38 cast FE004B17 holding gun FE003A99 (its enchantment FE004B17): a burst of 6", muzzle found in third person: the enemy side
  works and enemies have and drop the staff SMGs). But "gun mode on" never appeared (only one "gun mode off" 7 ms after the first gun check), no
  equip box, no charge bar, no rapid fire: Papyrus asked `GunStat(w, "clip")` and got 0 although the plugin had computed 20. It was the first native
  with a STRING parameter (the `std::string_view` key); on this runtime it did not match. 0.15.2 (plugin 1.1.2) has no native with a string:
  `GunClip(Weapon) Int`, `GunIntervalMs(Weapon) Int`, `GunReloadMs(Weapon) Int` (`GunStat` is gone; a test asserts the stub has no String). Never
  add a string parameter to a native without a log proving it arrives. The plugin logs the first six `GunClip(...) = n` answers.
  Also in 0.15.2: the Hunter finds a Skylands gun in EITHER hand (`HeldIn`/`GunHeld`, used by `Carrying` and `OwnDrop`): OwnDrop looked at the right hand
  only, so a staff gun in the left hand was never dropped on the ground and never got a beam (beams are placed on guns lying loose in the world).
- 0.16.0 (TestBuild-88, plugin 1.2.0), user requests after 0.15.2 ("things are looking good"): (1) beams: some staff guns were slow/missing; the Hunter's
  player scan now runs every 4 s (was 8) with 8 tries (was 3) (`Scan`/`PlayerTick`); unconfirmed that this was the cause. (2) bullets: a plain gun's
  bullet has NO element (the fire donor's hit art, hit shader, impact data, resist (set to -1), sounds (`SNDD`) and keywords are stripped, the PROJ's
  firelight and flight sound are zeroed; this was the "fire explosion on every weapon"); an elemental gun's bullet comes from a staff of its own
  element only (`staff_donor(..., strict=True)`; else it is built like a plain one) and carries that element's hit art; the element's status effect
  rides on a SILENT explosion (`Armory._blast`: no model, light, sound, impact data or placed object); the "second element on top" was the explosion
  of the crossbow rounds (`Rounds.expl`, fire art) plus the donor's fire hit art. Tracer half size (`STAFF_TRACER_LENGTH/WIDTH` 45 x 0.8), bullet
  speed x1.25 (`STAFF_BULLET_SPEED`). (3) gun stats drive firing: the keyword numbers come from the rolled stats (interval = 1/fire_rate, reload =
  stats reload, spread = type spread x `spread_mult`; `stats.roll` draws `spread_mult` LAST so no crossbow number moves); the MGEF text says the spread.
  (4) relics: the player's actor values `Variable06/07/08` = fire rate / reload / accuracy bonus in percent, read by the script's `Boost` every
  shot (`FireGun` got a spread multiplier argument); `docs/relics.md`. The relic items themselves, and damage/magazine bonuses, are not built.
  UNCONFIRMED in game: all of it (bullets look, the hit art, the actor values being usable on this runtime, beams).
- 0.17.0 (TestBuild-89, plugin 1.2.1), user requests: (1) the ten-shot magazine message now also tells the fire rate (commanded, relic bonuses
  included), a MEASURED rate (`Measured`: rounds / seconds since the trigger went down), reload and spread (`Tell`, `Fmt1`; new native
  `GunSpreadTenths(Weapon) Int`); (2) shot sounds per gun type: each staff gun carries keyword `SkylandsSnd_<type>`, props `SoundKeywords`/`Sounds`
  (arrays) and `PickSound` chooses; the sounds are Skyrim stand-ins (SMG: crossbow shot, AR: bow shot) because Borderlands audio is not extracted -
  `audioprobe.py` / `Check-BL2-Audio.bat` (`python -m skylands_setup bl2audio`) writes `work\bl2-audio-report.txt` (file types, audio files, sound-looking
  package names) for the user to send; nothing about BL2's audio format is known yet (Wwise `.wem`/banks vs UE3 sound objects), the plan is in
  `docs/gun-feel.md`; (3) muzzle flash: the bullet PROJ has the muzzle-flash flag, `NAM1` = our `Flash_Staff_*.nif` (`nif.tracer(forward=True)`), muzzle light
  (`muzzle_light`, a LIGH copied from a vanilla light) and duration 0.05 s; UNCONFIRMED in game, and unconfirmed that a plugin-launched projectile
  shows it. Docs: `docs/gun-feel.md` (small details), `docs/staff-roadmap.md` (features from skse.md in order). Note: a careless slice in an edit once
  deleted the Armory class; edit `generate.py` with exact-match replaces and run the tests after each.
- 0.17.0 in game: the game CRASHED on the first shot. Log: "gun mode on", "bullet origin (player): muzzle ... third person", then nothing. The only change in the
  launch path was the muzzle flash on the bullet PROJ (flag 0x8 + `NAM1` model + muzzle light + duration), so it is the suspect (not proven). 0.17.1 (TestBuild-90,
  plugin 1.2.2): `generate.STAFF_MUZZLE_FLASH = False` (no flag, no NAM1, no muzzle light, no flash mesh); the plugin logs "launching <id>'s bullet
  (projectile <id>) from x y z" and "launched" around the first three launches. Never switch a PROJ feature on for plugin-launched projectiles without a test
  that can fail safely. Also in that log: the install had only three plain vanilla staffs (all fire), so Shock/Corrosive/Slag bullets are built like plain
  ones (no hit art); the AR shot sound is `WPNBowFireSD`; the setup log's staff info string still says "Build 0.15.0" (STAFF_REV, harmless).
- 0.17.1 in game: no crash (flash off); no flash, no sound (sound is a stand-in only until BL2 audio is extracted: the user is happy to wait); MEASURED fire rate
  about HALF the set one, varying with the gun. Cause: the Papyrus hold loop (`Utility.Wait(gap)` per shot, 0.17.0) runs at about half speed (Wait + the VM's
  scheduling); not fixable in Papyrus. Audio report (`work\bl2-audio-report.txt`, 8900 lines): BL2 sound = Wwise (`Audio_Banks.pck`, `Audio_Streaming.pck`, magic `AKPK`,
  one pair per DLC) with event objects in the packages (`Ak_Play_Wep_SMG_Dahl_Shot_Short/Long/Release`, `Ak_Play_Wep_Rifle_<Mfr>_Shot...`, banks `Akb_Wep_SMGs` etc.);
  the extraction plan is in `docs/gun-feel.md` (read AKPK/BKHD/HIRC, decode wem with a downloaded tool, make Skyrim sound records).
- 0.18.0 (TestBuild-91, plugin 1.3.0): the plugin fires the player's gun. A thread asks the game thread for a `Tick()` every 4 ms while `SetGunMode(true)`;
  the tick reads the trigger, fires rounds when due by `steady_clock` (up to 3 per tick), keeps the magazine PER GUN (map by weapon form id), reloads, sets
  `RightItemCharge` (100 a round), plays the gun's shot sound (`SetShotSound`, `BSAudioManager::GetSoundHandle`) and applies the relic actor values
  `Variable06/07/08` (`Relic()`); the script no longer loops (it introduces the gun, hands over the sound, shows the box, and every 0.25 s asks `Magazine/
  ShotsFired/Reloading/RateTenths/MeasuredTenths/ReloadMsNow/SpreadNowTenths` for the ten-shot message and the reload notices). New natives are all ints/bool/Sound (no
  strings). `FireGun` stays but is unused. The gun keyword gained `_e<0..4>` (element index) for the flash colour. Muzzle flash from the plugin:
  `SpawnFlash` -> `BSTempEffectParticle::Spawn(cell, 0.06, "Skylands\\Flash_Staff_<element>.nif", matrix, pos, 1, 0, nullptr)` after each launch, `MuzzleFlash=1` in the ini
  (installer-written). UNCONFIRMED in game: the tick thread + task approach (a thread queues one task at a time; do not queue from inside a task - SKSE's queue
  semantics when a task adds a task are not known), that the measured rate now matches, the flash (appearance, direction: `SetEulerAnglesXYZ(pitch, 0, heading)`),
  that `RightItemCharge` set from C++ moves the bar, the sound handle path. If the game hangs or the rate is wrong read the log: "automatic fire: tick thread started",
  "player gun <id>: magazine ...", "muzzle flash: spawning/spawned".
- 0.19.0 (no build sent yet; the user will test TestBuild-91 first and then asks for one build with audio + fire rate + flash): BL2 shot sounds. `bl2/wwise.py` (AKPK
  tables scored by magic numbers, bank chunk walker fallback, HIRC objects, FNV-1 event ids, id-scanning links event -> action -> sound / container -> audio id),
  `bl2/audio.py` (event names per type/manufacturer, PCM read directly, else vgmstream-cli downloaded into `work\vgmstream`, mono 16-bit 44.1 kHz WAV into
  `work\audio\wav`), `generate.Armory._shot_sndr` (SNDR copied from a vanilla standard descriptor, ANAM = `FX\Skylands\x.wav` in the template's style, files
  copied to `Data\Sound\FX\Skylands`), keyword `SkylandsSnd_<type>_<Mfr>` tried before the per-type stand-in; `build.py --bl2-sounds auto|off` (staff mode, auto);
  `Check-BL2-Audio.bat --shots` runs the extraction alone. NOTHING is verified on real files: AKPK layout, HIRC object layouts (events/actions/sounds are found by
  scanning for ids), the Wwise event names (Play_... vs Ak_Play_...), the SNDR file-name style and the vgmstream download are all guesses with logging. Tests use
  synthetic packs (`tests/fake_wwise.py`, `tests/test_audio.py`).
- 0.18.0 in game (TestBuild-91, SkylandsNative.log): the plugin fire loop works ("automatic fire: tick thread started", "player gun ... magazine 24 of 24"), the user
  says the fire rate is right and the muzzle flash looks good ("muzzle flash: spawned"). No shot sound was heard (stand-in `WPNCrossbowFire` on the SMG; no log line
  said whether the sound was handed to the plugin: suspects were a ghost script object with empty properties, or `PlayShot`). `Check-BL2-Audio.bat` report was the old one.
- 0.19.0 (TestBuild-92, plugin 1.4.0, built next): (1) the muzzle flash is smaller by gun type: `generate.STAFF_FLASH_PERCENT` smg 75, assault_rifle 90; the numbers keyword
  gained `_f<percent>`; the flash meshes are `Skylands\Flash_Staff_<element>_<percent>.nif`; the plugin reads `f` (`GunInfo.flash`). (2) BL2 reload sounds: three parts per
  gun type x manufacturer (`bl2/audio.RELOAD_NAMES`: out = Reload_Eject / Clip_Out, in = Reload_Insert / Clip_In, end = Reload_Cock / End / Bolt ...), SNDRs
  `SkylandsReload<Out|In|End>_<type>_<Mfr>`, script arrays `ReloadOut/ReloadIn/ReloadEnd` parallel to `Sounds`; `Load` hands them to the plugin with
  `SetReloadSounds(Sound, Sound, Sound)`; the plugin plays them at 2%, 45% and 86% of the reload time (`BeginReload`/`ReloadSounds`). `extract_shot_sounds` keys:
  `(kind, mfr)` = shot, `(kind, mfr, part)` = reload part. (3) script class `SkylandsStaffGun19` (18 retired), `STAFF_ID_SHIFT` 340: a ghost 18 with empty properties is the
  likeliest reason no sound was heard. The plugin logs "shot sound set", "reload sounds set", "playing sound ... form found/missing" and "sound ...: handle built, valid, play".
  UNCONFIRMED: everything about the Wwise extraction on the real files (read `skylands-setup.log` `audio:` lines), that the reload sounds line up with the animation-less reload.
- 0.20.0-0.20.2 (plugin 1.5.x, TestBuild-95..97): aim down sights, in the plugin (`UpdateAim`, `CenterGun`): hold "Left Attack/Block" (the plugin swallows it in gun mode), zoom by
  `fDefaultWorldFOV:Display` + `PlayerCamera::GetRuntimeData2().worldFOV` (keyword `_z13`/`_z16`; confirmed in game: zoom works), spread x `AimSpread`, walking speed via
  `ModActorValue(kTemporary, kSpeedMult, -taken)` and the exact reverse (`SetActorValue` set the BASE and left it 100 higher each aim, then a sign slip left it a little lower:
  the user's save may need `player.setav speedmult 200`), the first-person weapon node (child of "WEAPON", found from the `SkylandsMuzzle` node) moved and turned from the CAMERA
  node so the barrel points along the view, blended by the aim; ini `AimCenter/AimForward/AimDown/AimRight`. The user tuned 30/6/6 for 0.20.1. 0.20.2 UNCONFIRMED in game.
- 0.21.0 (TestBuild-98, plugin 1.6.0): reload key (`ReloadKey`, R = 19, swallowed from the Ready Weapon handler in gun mode), one round chambered on an early reload, ammo text
  prototype (`RE::SendHUDMessage::ShowHUDMessage`). No ammo reserve yet: ideas given to the user (inventory AMMO items per type as the reserve, plugin counters in an SKSE co-save, ...).
- 0.20.2 log check: the user's log said "SkylandsNative 151" (plugin 1.5.1), so TestBuild-97 (1.5.2: camera-based aimed gun, speed sign fix) was NOT what ran (no "aim: camera at" line,
  speed still drifting 200 -> 160); 0.21.0 / TestBuild-98 contains 1.5.2. Always check the first log line's version against the build. Form ids of the second plugin are 12-bit while it is
  ESL-flagged (0x800-0xFFF): it was at about 0xCEF in 0.19.2 and each `STAFF_ID_SHIFT` bump spends ids, so avoid renaming the script class again (use keywords/natives instead).
- 0.22.0 (TestBuild-99, plugin 1.7.0): ammo as inventory items (the user chose option 1): AMMO records `SkylandsAmmo_smg` / `SkylandsAmmo_assault_rifle` ("SMG Ammo", "Assault Rifle Ammo",
  built from scratch like the rounds), ids reserved in `Armory.__init__` (`ammo_ids`), the gun's numbers keyword gained `_m<form id & 0xFFFFFF>`; the plugin finds the item from the gun's
  ENCHANTMENT id (same plugin; light plugin: `(ench & 0xFFFFF000) | (m & 0xFFF)`), takes the rounds of a reload out of the player's pack when the reload ENDS (a short stock gives a short magazine,
  "Out of ammo" when none, the message shows the stock), gives `StartAmmo` (300) to a player with none the first time a gun of that kind is taken up in a run, and enemies that die with a gun
  get 10-30 of its ammo (`DeathSink`, ini `AmmoDrops`). No script change (no ghost). UNCONFIRMED in game: all of it (that AMMO with projectile 0 shows in the pack, `GetInventoryCounts`,
  `RemoveItem`, `AddObjectToContainer` on corpses, the death event fields).
- 0.22.1 (TestBuild-100, plugin 1.7.1): user report on 0.22.0: ammo works (from the pack, enemies drop it); aimed gun too high (AimDown 9 now the default), still slightly turned, and it lags the
  view while moving ("moves slower than me, follows me"): the arm animation lags the camera, and the gun hung under the arm's weapon node. Now the aimed gun is moved under the first-person
  skeleton ROOT while aimed (`CenterGun`, `RestoreGun`; back to the hand's WEAPON node when the aim ends, a menu opens or the gun goes away) and its turn is set from three nodes in the mesh
  (`SkylandsMuzzle`, `SkylandsBreech` = rear of the barrel, `SkylandsTop` = above the muzzle; `nif.gun(marks=)`): barrel along the view, top up. UNCONFIRMED in game: that reparenting the weapon
  node is safe (a gun left floating if the game removes the weapon while aimed), the held turn, the lag (the root may not pitch with the view: pitch then lags by a frame).
- 0.23.0 (TestBuild-101, plugin 1.8.0): HUD prototype (user chose bottom right, Borderlands style, low-ammo flash, reload bar, gun name in the rarity colour when equipped). Drawn from the plugin into the
  game's own HUD movie, no SWF of ours: `HudBuild` makes the clip `_root.SkylandsHUD` (`CreateEmptyMovieClip`, `createTextField`, the drawing calls, `$EverywhereBoldFont` in HTML), `HudFrame`
  (30 Hz, from `Tick`) finds it by path each update (so a reloaded HUD rebuilds it) and shows the magazine, `/ clip`, `| stock`, a bar while reloading, a flashing LOW AMMO / RELOAD / NO AMMO, and the
  name for 4.5 s after the gun is taken up; rarity colours from the `SkylandsRarity_<id>` keyword (common white, uncommon green, rare blue, epic purple, legendary orange, etech pink). ini `Hud`,
  `HudRight`, `HudBottom` (1280 x 720 HUD coordinates). If it cannot be built the plain `AmmoText` messages stay (`g_hudLive`). UNCONFIRMED in game: all of it (that the HUD movie takes
  `createTextField` from outside, the font name, the position, alpha). Coloured names in the INVENTORY are not possible with plain records (list text is plain); options told to the user.
- 0.23.1 in game: CRASH on load into the game, right after "hud: built" and "hud: the game's HUD base clip holds [...]; meters hidden: 4": 0.23.1 hid every HUD base member with "charge" or
  "enchant" in its name (RightChargeMeter, RightChargeMeterAnim, LeftChargeMeter, LeftChargeMeterAnim) with `SetDisplayInfo`; the "...Anim" ones are probably not display objects. 0.23.2 (TestBuild-103,
  plugin 1.8.2) hides only names ending in "Meter" and only when `IsDisplayObject()`. The HUD base clip's members are in the log (TutorialLockInstance ... RightChargeMeter, LeftChargeMeter, ...).
  The aimed-gun `UpdateDownwardPass` change of 0.23.1 had not run yet at the crash (no "aim started" line). A crash needs the crash logger's log if the plugin log stops cold.
- 0.23.2 in game (log, plugin 182): no crash, HUD works, the old charge bar STILL showed: "meters hidden: 2" were `RightChargeMeter` / `LeftChargeMeter`, which are probably helper objects (like
  `StaminaMeter` next to `StaminaMeterAnim`); the clips are the "...MeterAnim" ones. 0.23.3 (TestBuild-104, plugin 1.8.3) hides names with "charge" ending in "meteranim", only if `IsDisplayObject()`, and logs
  what it found ("hud: RightChargeMeterAnim found ..., display object ..."). The 0.23.1 crash was most likely `SetDisplayInfo` on a non-display helper object. Aimed gun defaults now AimForward 33, AimDown 6
  (user: "up 1, away from the camera 3"; the user said the gun "looks pretty good"; log: "aim: gun held ... turn 13.3 degrees from the hand's").
- 0.23.3 in game (log, plugin 183): charge meter clips found and hidden ("hud: RightChargeMeterAnim found true, display object true"; the user's report on the bar after this build is pending); the aimed gun
  looks right but still trails the player's run; the game CRASHED while the user killed enemies (the log stops at an "aim started" line; one corpse got ammo ("ammo drop: FF000E9B carries 11") a few seconds earlier).
  0.24.0 (TestBuild-105, plugin 1.9.0): (1) crash handler: `SetUnhandledExceptionFilter` logs "CRASH: exception <code> at <addr> in <module> (+offset); the plugin's last stage: <g_stage>" (breadcrumbs in Tick, UpdateAim,
  CenterGun, RestoreGun, the death and cast events, Launch, the ammo drop) and calls the previous filter; (2) the corpse ammo drop is no longer made inside the death event: 800 ms later from the game thread, the body
  looked up again (changing a pack mid-death is a known crash); (3) the aimed gun is placed from the player's position and angles of THIS frame plus the camera's measured offset (`AimPredict`, ini): theory = the camera
  node is worked out after the plugin's tick, so it is a frame old at the tick, and a run is a visible lag; "aim view:" log lines every 100 ms (actor / root / camera / used positions, forward dot) show the real order;
  (4) `ReloadMouse` (a mouse button as a second reload key, -1 off); (5) the installer keeps the player's settings-file values while `IniVersion` is the same (`skse.merge_ini`, the old file kept as `.ini.old` otherwise):
  BUMP `IniVersion` when a default is deliberately changed. UNCONFIRMED in game: all of it.
- 0.24.0 in game (log plugin 190, "aim view" lines): at our tick the player's position and the first-person ROOT are always EQUAL (the root is current), the CAMERA node trails by ~33 units while running (about 55 ms)
  and sits exactly +120.5 above the actor at rest; the player's angles agree with the camera's forward (dot 0.9995-1.0000). 0.24.0's prediction paired a camera value with the previous tick's actor position, so its offset
  included the lag. No crash line in that log. 0.24.1 (TestBuild-106, plugin 1.9.1): the camera offset is measured only when the player stands still (`rest`), origin = actor now + rest; defaults ReloadKey 47 (V),
  AimDown 6.5 (user: "down .5"), IniVersion 3; `ReloadMouse` also accepts code 256+n and the plugin logs the first 30 mouse/pad button presses ("button down: device D code C") to find a side button's code.
  The user's mouse reload button did not work in 0.24.0 (cause not yet known).
- 0.24.1 in game (log plugin 191): the aimed gun stays in place while running, V reloads (user: "very good"). The multi-bullet tap: `TickGun` kept `nextShot` as it was when the trigger went down unless it was MORE
  than one interval ahead, so after a pause shorter than three intervals the catch-up loop (`fired < 3`) fired the owed rounds at once (2-3 bullets from one tap). Not visible in the log (only the first
  launches are logged), found in the code.
- 0.25.0 (TestBuild-107, plugin 1.10.0): (1) tap fix: a pull starts with `nextShot = max(nextShot, now)` (the cooldown holds, no backlog) and a tap that is up again before the tick (`g_latch`) is one round
  (`tapped`, `most = held ? 3 : 1`); (2) recoil and sway, user chose "both sways and Borderlands-style recoil": `AddKick` per shot (pitch `RecoilPitch` 0.55 deg x sqrt(interval/0.12) x aim share, yaw random +-`RecoilYaw`
  0.22), `RecoilFrame` per tick applies it to `player->data.angle` within ~35 ms, gives `RecoilRecover` (0.6) of the pitch back 120 ms after the last shot (time constant 0.2 s), jerks the aimed gun back
  `RecoilGun` units, and works the aimed gun's sway (breathing, walking bob, lag behind turning; `Sway`) into `CenterGun`'s target. Sway is ADS only (the hip gun hangs on the arm animation). Ini keys
  `RecoilPitch/RecoilYaw/RecoilRecover/RecoilAim/RecoilGun/Sway` (IniVersion stays 3: new keys get defaults). UNCONFIRMED in game: that writing `data.angle` moves the first-person view (the log says
  "recoil: first kick moved the view pitch a -> b"), the signs (kick up, sway left when turning right), the strengths.
- 0.25.0 in game (user): recoil and sway "look great". Wrong: the muzzle flash drifts back into the gun when aiming and lags like the gun used to (it was a fixed world effect spawned at the shot's
  muzzle place, 5 units inside the barrel end), and it sat slightly on the barrel. 0.25.1 (TestBuild-108, plugin 1.10.1): the player's flash is respawned every tick for 60 ms (`FollowFlash`, `g_flashFollow`, each
  effect lives 0.03 s) at the muzzle node of THAT tick, along muzzle minus breech, pushed `0.15 x barrel length - 5` units forward (user: "15% away from the gun"); enemies keep the one static flash.
  UNCONFIRMED in game: that the respawned flashes read as one flash (no flicker or double brightness).
- 0.25.1 in game: not reported yet at 0.26.0 time. 0.26.0 (TestBuild-109, plugin 1.11.0), user requests: (1) hands invisible while fully aimed (`HideHands`, ini): `CenterGun` culls (`SetAppCulled`) every
  non-node leaf under the first-person root except the gun when the blend is >= 0.4 (`HideHands`), shows them below it and in `RestoreGun` (`ShowHands`); log "aim: N arm parts hidden". (2) muzzle and shell
  effects prototype (roadmap item 8), all plugin-side, NO new records: temporary effects of our own meshes (`Fx_Casing`, `Fx_Smoke_0..2`, `Fx_Burst_<element>`, `generate.STAFF_FX_MESHES`) moved by the plugin and
  re-spawned every 30-60 ms (`Fx`, `FxFrame`, `EmitShotFx`, `BarrelFrame` from the muzzle/breech/top nodes): casings thrown out of the receiver's right side and falling (gravity 1300, 0.6 s, no ground test),
  a puff at the muzzle per shot plus a wisp for 1.1 s after, and the small elemental burst where an elemental bullet ends (`TrackBullet`: the launched projectile's handle is watched; when it is gone a burst is
  drawn at the last seen place; this replaces the old explosion records, which stay silent). Ini `Casings/Smoke/ImpactBursts`. UNCONFIRMED in game: all of it (looks, performance of ~15 temp effects a tick, that
  a handle that goes null means the bullet ended, the arm cull hiding the right nodes). Damage text: put on hold by the user.
- 0.26.0 in game: not reported at 0.27.0 time. 0.27.0 (TestBuild-110, plugin 1.12.0), user requests: (1) smoke removed (not liked); (2) the plugin-drawn impact bursts removed: elemental bullets (and ALL rockets)
  now ride on real explosion records `SkylandsBlast_<kind>_<element>` (`Rounds.expl`, vanilla explosion art for the element, small radius 60-90, damage = base x 0.25-0.35; rockets radius 420, damage x1.0), the PROJ
  explosion flag set; `Armory._blast` (the silent one) is gone. (3) EVERY gun type is a staff gun: `STAFF_KINDS` = smg, assault_rifle, pistol, shotgun, sniper, launcher (the first two stay first so GiftA/GiftB and
  their ids are as before); each Skylands.esp crossbow stays (byte-identical) and is overridden by a staff weapon of the same id in the second plugin; per-type tables `STAFF_FLASH_PERCENT/ZOOM/AMMO_NAMES/TRACER_SIZE`
  (sniper zoom 3.0x), one ammo item per type (Pistol Ammo, Shotgun Shells, Sniper Ammo, Rocket), keyword `_p<pellets>` (the plugin launches that many projectiles per shot; the effect's magnitude is damage / pellets x 1.5),
  reload and shot BL2 sound names for the new types (`bl2/audio.py`, reload names are the SMG guesses). No crossbow items are given or equipped any more: the ammo-drop list is overridden in the second plugin
  with the six ammo items, the Hunter script (`scripts.watcher(bolts=False)`) and class-choice quest (`class_choice_quest(bolts=False)`) no longer add bolts. Installer: `Install-Skylands-GunModels-All-Staff.bat`
  (`--gun-shooting staff`; the old partial 'Shooting-Staff' bat is gone). With ~4x the guns the second plugin passes 0xFFF ids, so it is no longer ESL-flagged (`esp.py` drops the flag over 0x1000): it takes a normal
  load-order slot, and the form ids of its records change against earlier builds. The class-choice quest and Hunter keep their old props (Skylands.esp is untouched). UNCONFIRMED in game: all of it (pellet spread and
  damage, rocket look/explosion, sniper zoom, whether the vanilla explosion art reads as 'small', ammo/mesh/sounds for the new types, ids and load order of the now non-light second plugin).
- 0.28.0 (TestBuild-111, plugin 1.13.0; the user went to sleep and left a list; 0.27.0's push had a plugin that did not compile: the `pellets` field and `case 'p'` edits had been lost in a script that never wrote the file - after every
  scripted edit check with grep that it applied, and wait for the CI DLL before trusting a version): (1) shotguns: `_p<n>` pellets come from each BL2 gun's own row (cap 24), `Launch` fires them one by one, each at its own random
  place in the spread cone (uniform disc), one flash/sound per shot; damage per pellet = shot damage / pellets x 1.5; an enemy's cast launches the rest of the pellets (`CastSink`). (2) rockets: launchers' bullets are `Rocket_<style>_<element>.nif`
  (`nif.rocket`, `nif.glow` = any number of glowing crossed-quad layers) in three looks picked by the gun's variant `k % 3` (the gun's text names it): 0 Missile (speed x1.1, no light/sound), 1 Heavy rocket (x0.8, a little gravity,
  donor light and flight sound, dark smoke tail), 2 Plasma rocket (x1.5, light and sound); keyword `_t<1..3>` tells the plugin the exhaust: it tracks the launched projectile's handle (`TrackRocket`) and leaves flame (`Fx_Flame_0..2`)
  and smoke (`Fx_Smoke_0..2`, three strengths by age) behind it every 30 ms, and a launcher puffs back-blast smoke (ini `Rockets`); no casings from launchers. Explosions are the real `SkylandsBlast_launcher_*` ones (radius 420). (3) People:
  the Hunter script of a staff install (`scripts.watcher(bolts=False, everyone=True, arm_percent=70)`) lets EVERY person with the NPC keyword (children excluded; not only the player's enemies) roll for a gun, 70 percent (a literal in the pex, because a
  saved property keeps its old value), and a person's death can drop a new gun (`Worthy`) whoever killed them; the plugin also gives bodies ammo: the held gun's (10-30) and, for 30-60 percent of humanoid bodies, 6-20 of a random kind
  (`SkylandsAmmos_<id>_..` keyword on every gun lists the six ammo items; log "ammo set"). Chest lists get the six ammo items through the overridden `SkylandsAmmoDrop`. The gun models of all types use the same hold, grip, muzzle and
  breech/top marks as the SMG and rifle (only `models.LENGTH` differs). UNCONFIRMED in game: everything in this entry.
- 0.28.0 in game (user): the game crashed on the old character (the second plugin's form ids moved: the user accepts a NEW SAVE from now on and says it loads fine on a new save), and all Skylands processes broke the
  new-game intro cutscene. 0.29.0 (TestBuild-112, pex-only, plugin unchanged 1.13.0): nothing of Skylands starts until the player can move after the intro. `scripts.waiting_function`: `Waiting()` on a quest = true until
  `Game.IsMovementControlsEnabled()` was true on three polls in a row (`Calm`), then `Begun` stays true; `SkylandsHunterQuest.OnUpdate` (poll 1.5 s) and `SkylandsGunnerQuest.OnUpdate` (poll 2 s; it adds the staff/gunner
  ability and gifts the guns; its 'Skylands quest started' notification moved to the moment it begins) call it first; the `SkylandsHunter` watcher (the ability every race carries, so it runs on the player and every NPC from the
  first frame) is split into `Go()` (true when the Owner quest is not running or `Owner.Started()`), `OnEffectStart` (sets `Me`, begins at once if `Go()`, else polls every 3 s), `Begin()` (the old start code) and `OnUpdate`
  (`Began`). So the vault hunter choice, the ability, NPC arming/enlisting and the player's guns all wait. Tests: `test_pex.py::test_nothing_of_skylands_starts_until_the_player_has_control_after_the_intro`. UNCONFIRMED in game:
  that `IsMovementControlsEnabled` is false for the whole cart/keep intro and true at the moment of control (if the choice box still comes too early or too late, tune `Calm` (3 polls) or add an MQ101 stage check).
- 0.29.0 in game (user): Skylands started right after the cart (the player can walk about the courtyard then, so `IsMovementControlsEnabled` alone is not the end of the intro). 0.29.1 (TestBuild-113, pex-only):
  `Waiting()` also needs `IntroOver()` (`scripts.intro_over_function`) on each of the three polls: the opening quest MQ101 "Unbound" (Skyrim.esm 0x0003372B, `Game.GetFormFromFile(210731, "Skyrim.esm")`) not found or `IsCompleted()` =
  over; stage > 0 = over only when the player is in an INTERIOR (the Helgen keep: after the cart, the block, the dragon, the player has control and runs there); stage 0 (an intro-skipping start) = over after 60 s of real time.
  The MQ101 stage numbers are NOT known (UESP and Nexus are blocked from the container; a Nexus thread says stage 30 = 'Make our way to the Keep', 50 = entering the keep, 900 = finished: unverified), so it keys on the interior, not
  on a stage. UNCONFIRMED in game: that the keep is the first interior of a new game and the first moment of control after the dragon; if the start is still too early or late, `sqs MQ101` in the console lists the stages and
  a stage threshold can replace the interior test.
- 0.29.1 in game (user): Skylands starts at the right time now. Reported: NPCs carry our guns but dual-wield them with a vanilla one-handed weapon; every shotgun still had the Falmer staff model (the pellets worked);
  the aimed gun does not follow the camera down when the player crouches. 0.30.0 (TestBuild-114, plugin 1.13.1): (1) the watcher of a staff install clears the pack of every other weapon (form type 41) when a person is handed a gun
  (`Equip` -> `ClearWeapons`) or takes a Skylands gun in hand any way (`OnObjectEquipped` -> `NpcEquipped`; `ClearOne` per slot, `PlayerEquipped` holds the old player branch; Champollion segfaults when the event holds the branches
  itself). (2) `GunModels.model_for`: a staff gun (hold given) whose native/UModel model cannot be built falls back to the PROXY model (the old fallback was 'keep the vanilla mesh', which is the staff for staff guns, the
  cause of the shotgun staffs; WHY the native shotgun parts failed is unknown, the old setup log is from before the all-staff build: look for 'Gun model ... failed' and the new 'by gun type' summary in `skylands-setup.log`);
  `gunparts.gun_parts` also takes the biggest part as the body when no Body part could be read (two or more parts read). (3) Crouching: the aimed gun's origin is the player's position plus `rest`, the camera's offset measured
  when the player stood still; the eye's height (rest.z) was only refreshed when the camera was exactly still, so a crouch never updated it. Now `rest.z` follows the camera whenever the player is not jumping/falling (even on the move),
  `rest.x/y` are measured while the player stands still, and the offset (`g_aim.view`) starts from the current eye height at each aim start. UNCONFIRMED in game: all three.
- 0.30.0 in game (user, setup log 509bb60c): enemies dual-wield our guns, their shots make no sound, bodies keep their gun in the pack and sometimes drop a second one, shotguns still not native models. 0.31.0
  (TestBuild-115, plugin 1.14.0): (1) the log: `Gun models ... by gun type {... 'shotgun': {'proxy': 89} ...}` - the proxy fallback worked (shotguns are proxy boxes, never the staff); EVERY shotgun part had no mesh
  ("native: 550 parts looked at, 212 meshes read, 338 without a mesh object ... 39 of 207 meshes located in 43 s" from 124 packages: the shotgun meshes are not among the located ones, reason unknown: the setup log
  now prints the first two parts without a mesh of each gun type with `describe` + `diagnose`, the packages that cannot be opened, and the never-found mesh names by prefix; read those lines in the next log).
  (2) dual wield: cause NOT proven (no Papyrus log). `ClearOne` now keeps ONE copy of the kept gun (two copies of one gun go to both hands) and removes every other weapon. (3) bodies (staff install only,
  `scripts.watcher(everyone=True)`): `Cleanup` = note `GunHeld`, `ClearWeapons(None)` (every weapon out of the pack), `DeathDrop` = ONE roll of `DropChance` (25 from the sheet): half the time the held gun (if any) is
  placed on the ground, else a random gun from `ListFor`; `OwnDrop`/`BonusDrop` (drop the held gun always, plus a bonus one) are not used there. Other installs keep the old `Cleanup`. (4) enemy shot sounds: each gun's
  keyword gained `_o<local id of its Borderlands shot SNDR>` and `_v<vanilla stand-in form id>`; the plugin plays them (`ShotSoundOf`/`PlaySound`) at the muzzle for an enemy's `Launch` and in `CastSink` for the
  game's own first bullet (not for the extra pellets). UNCONFIRMED in game: all of it.
- 0.31.0 in game (user, logs 44b4fb53 / 4283eada): enemy shots are heard; the player's own shots are silent (cause unproven: the player path was unchanged); enemies still dual-wield (Papyrus log shows no
  second watcher instance, no ClearOne error). 0.32.0 (TestBuild-116, plugin 1.14.1): the player's shot sound is chosen by the plugin from the gun's own keywords (`ShotSoundOf`) first, the script's
  `SetShotSound` hand-over is the fallback; log "player shot sound: own .. script .. playing ..". Papyrus: `Maintain` assigned `Remember`'s Bool to None (NoneVar mismatch, fixed), the quest's `Place` passed a Light as a
  Form (cast, fixed), `Equip` clears other weapons again after EquipItem. Dual-wield cause still UNPROVEN: if it persists ask for `SkylandsNative.log` + which items the second hand holds.
- 0.32.0 in game (user, SkylandsNative.log plugin 250): player shot sound is back; enemies hold TWO OF THE SAME gun whatever the weapon. Setup log 44b4fb53: all 26 shotgun mesh names (`sg_*`) are in
  the name tables of ~10 packages but NO package exports a mesh of that name (the 39 located meshes are other types), so shotguns are proxy boxes. 0.33.0 (TestBuild-117, plugin 1.14.2): (1) `gunparts._fuzzy_meshes`
  (after the exact search; `MESH_INDEX_VERSION` 2 so the saved list is redone): looks in every name table for the same slot+manufacturer under another prefix (`shotgun_body_bandit`), opens those packages, takes
  mesh exports; logs `fuzzy search:` lines (names of the type that look like parts, shotgun-named groups, unreadable packages). READ THOSE LINES in the next setup log. (2) plugin `OneGunOnly`: on an enemy's cast, a
  Skylands gun in BOTH hands: the extra copy is removed and the left hand emptied; log "enemy ..: left hand holds gun ..., right hand .., N copies in the pack". UNCONFIRMED in game.
- 0.33.0 in game (user, logs 3271a474 / f0a3cefa): BAD. The fuzzy search mapped other gun types' meshes onto missing names (it matched the tail `body_bandit` against ANY gun type's `pistol_`/`ar_`/`smg_` names: "57 more meshes located"),
  so guns had parts from other types (a pistol with rifle magazines), a launcher 70 units long (was 48). Truth about shotguns: the files hold NO shotgun mesh at all (names `shotgun_*` do not exist; only `sg_*` names as references,
  in the part definitions), so real shotgun models cannot be had from this install; 0.32.0 behaviour (proxy boxes) is right. 0.33.1 (TestBuild-118, plugin 1.14.3): the fuzzy search is per gun type (a test in
  `tests/test_fuzzy_meshes.py`), `MESH_INDEX_VERSION` 3 (the bad saved list is ignored). Dual wield: the plugin log shows ONE copy of the gun in the pack and the SAME gun reported in BOTH hands (`GetEquippedObject`) at every cast, and
  the left unequip did not hold; the weapon carries keyword `WeapTypeStaff`. 0.33.1 tries three times per person: left unequip, then 500 ms later if still both: unequip and `EquipObject` into the RightHand slot only; logs
  "half a second later left .., right ..". UNCONFIRMED. Offer to the user: borrow a real rifle/sniper mesh for shotguns.
- 0.33.2 (TestBuild-119): same as 0.33.1 plus `shotgunprobe.py` / `Check-BL2-Shotguns.bat` (`python -m skylands_setup bl2shotguns`, writes `work\bl2-shotgun-report.txt`): the user is SURE the shotgun data is in their
  BL2 install. It lists weapon-named files, every package with a shotgun-looking name (`sg_`, `shotgun`, ...), then opens those packages and lists the exports and imports with class, path, size and (imports) which package
  they point to and whether that package is in the install, plus the weapon meshes that do exist for the other types. Read it, then teach `gunparts` where the shotgun meshes live.
- 0.33.2 in game (user report 4c91c184, 6180 lines): THE SHOTGUN MESH IS A GESTALT MESH. `Mancana_StartupRemaster.upk` (DLC remaster pack, 19 MB) exports `Remaster_Weap_Shotguns.GestaltDef_Shotgun`
  (GestaltSkeletalMeshDefinition, 18720 bytes), `Remaster_Weap_Shotguns.GestaltDef_Shotgun_GestaltSkeletalMesh` (SkeletalMesh, 1.7 MB, all shotgun parts in ONE mesh) and textures `Remaster_Weap_Shotguns.Tex.Weap_Shotgun_Comp/Nor`.
  The base game imports `Weap_Shotguns.*` (69 packages) but no file exports that package (the survey's "NOT in this install" check compares FILE names; most top-level packages live inside files, so ignore it for
  `gd_*`). Part definitions name their piece with `GestaltModeSkeletalMeshName` (`SG_Body_Bandit`): probably a bone/section of the combined mesh. Other types' missing meshes (168 of 207 never found: ar_/smg_/pistol_/sr_/l_/acc_)
  are probably in remaster gestalt meshes too. 0.33.3 (TestBuild-120): `gestaltprobe.py` / `Check-BL2-Gestalt.bat` (`python -m skylands_setup bl2gestalt`, writes `work\bl2-gestalt-report.txt` and raw
  `work\gestalt\GestaltDef_Shotgun.bin` + `GestaltMesh_Shotgun.bin`): lists every gestalt object, decodes the definitions' properties, shows names stored in the mesh blob, the bytes after the properties, what the heuristic mesh reader finds.
  NEXT: read that report, write a real SkeletalMesh parser (sections/chunks/bone map or the definition's part table) to cut one part out of a gestalt mesh, and hook it into `gunparts` (`mesh_index` for `sg_*`).
- 0.33.3 gestalt report (eadf438c) READ: every gun type has a `GestaltSkeletalMeshDefinition` (`Weap_<Type>.GestaltDef_<Type>` in `Startup.upk`, copies `Remaster_*` in `Mancana_StartupRemaster.upk`) with props
  `GestaltSkeletalMesh` (path), `GestaltInfos[0].Parts[]` = {`SkeletalMeshFragmentName` (e.g. SG_Body_Bandit = the part's `GestaltModeSkeletalMeshName`), `MaterialIndex` (always 0), `FirstIndex` (index-buffer offset),
  `NumPrimitives` (triangles)}, `GestaltSocketMappings`, `GestaltPartBounds`. Parts are CONTIGUOUS (FirstIndex + 3 x NumPrimitives = next FirstIndex) and the sum equals what `gunmesh.read_mesh_blob` finds as the whole
  mesh's triangle count (shotgun: 25227 in Startup, 33904 in the remaster), vertices already sit in assembled-gun space (all manufacturers overlap). 0.34.0 (TestBuild-121, pex/plugin unchanged, plugin 1.14.3):
  `gunparts.Bl2Source._load_gestalt_defs` (Startup first, Mancana fills gaps), `_gestalt_path` (used BEFORE `_stand_in`, after a standalone located mesh), `_gestalt_mesh` (reads the whole mesh once; refuses it if the triangle count differs
  from the definition's total), `_read_gestalt_part` (slice `tris[first//3 : +count]`, compact vertices, `placed: True` so no socket offsets). Log lines `gestalt: ...`, summary '... parts cut from gestalt meshes'.
  UNCONFIRMED in game: textures (the gun's Material part supplies one; the gestalt UV layout may need `Weap_Shotguns.Tex.Weap_Shotgun_Comp`), orientation/size, that variants (`_VarA/_VarB`) are picked by the balances.
- 0.34.0 in game (user logs f33e6543 / a541592d): the setup log says "Skylands 0.33.3 setup": the user ran TestBuild-120 (the survey build), NOT 121, so shotguns were still the proxy boxes (no `gestalt:` lines) - check the
  first line of `skylands-setup.log` for the version before reading anything else. Dual wield: the plugin's log shows ONE copy in the pack and the SAME gun in both hand slots (`GetEquippedObject(false/true)`), which is
  probably just how the engine reports a two-handed/staff-type weapon, so 0.33.1's unequip/re-equip was chasing a false positive. 0.34.1 (TestBuild-122, plugin 1.14.4): `OneGunOnly` no longer touches equipment; at an
  enemy's cast (at most every 3 s per actor) it walks the actor's 3D, finds every `SkylandsMuzzle` node, logs "enemy ..: hands hold .. (right) and .. (left); N gun model(s) in its 3D" and, per copy, the chain of node names
  up to the hand, and hides (`SetAppCulled`) a copy hanging under the LEFT hand (`L Hand` / `SHIELD`). UNCONFIRMED: that the second gun is a second model in the left-hand attach node. If the second gun persists, the log lines
  "gun model under ..." say where it hangs.
- 0.34.1 in game (user, screenshots + log c6f0e8a5, plugin 280): the gestalt models WORK (shotguns present, parts/attachments of every gun type filled in: "I barely realized how many were missing"). Dual wield is now PROVEN from the plugin log:
  an enemy's 3D holds TWO gun models, one under `WEAPON` (right hand) and one under `SHIELD < NPC L Hand [LHnd]` (the game puts the staff-type weapon in BOTH hand slots: `GetEquippedObject` right = left = gun). 0.34.1 hid the left copy
  unconditionally, which made enemies whose RIGHT slot was EMPTY (right 00000000, left = gun, one model under the left hand) shoot from an invisible gun. 0.34.2 (TestBuild-123, plugin 1.14.5): the left copy is hidden only when a right-hand
  model also exists; when the gun is ONLY in the left hand (no model under WEAPON) it stays visible and is unequipped/re-equipped into the RightHand slot (2 tries per person, log "the gun is only in the left hand: equipped again ..."). UNCONFIRMED.
  If enemies still show a gun in the left hand and none in the right while the log says 2 models, the right model may be present but invisible (not explained yet).
- 0.34.2 in game (log 7526821d, plugin 290): enemies show their gun in the LEFT hand but fire from the invisible RIGHT one. Log: every shooting enemy has two models (`WEAPON` and `SHIELD < NPC L Hand`) and the left-hand copy gets re-shown
  by the game now and then ("hid the left-hand copy" again for the same actor a minute later, so the engine re-attaches/re-shows it on draw). Reading: the game keeps the LEFT copy visible (the staff animation is the left-hand one) and the right
  copy is the one nobody sees. 0.35.0 (TestBuild-124, plugin 1.15.0): (1) the enemy policy is reversed: both copies -> the RIGHT (`WEAPON`) copy is culled, the left one kept/uncovered; bullets and flash start at `VisibleMuzzle(root)` (the first
  `SkylandsMuzzle` with no hidden ancestor) for NPCs; the re-equip experiment is gone. (2) player: `HideLeftArm` scales the first-person `NPC L UpperArm [LUar]` bone to 0.001 every tick while a gun is held in first person
  (`RestoreLeftArm` gives the scale back when the gun goes away, a menu opens, third person, ...; ini `HideLeftHand=1`; log "left arm: upper arm bone found ..."). UNCONFIRMED: that animation does not rewrite the bone's scale each frame
  (if the arm flickers back, the scale needs a different node or the arm meshes must be culled), that the hand is skinned to that bone. Dual wield: still no proof why the right copy is invisible.
- 0.35.1 (TestBuild-125, plugin 1.15.1), user: enemies sometimes SPAWN with two guns (the extra goes after a few seconds, i.e. at their first shot), and "enemies only ever drop the gun they hold, the random roll never happens".
  (1) the model fix is no longer tied to the first cast: `ScanArmed` (a thread queues it on the game thread every 400 ms, started in `StartPump`) walks `ProcessLists::highActorHandles` within 6000 units, and for every person
  whose hands hold a Skylands gun runs `FixModels` (the old `OneGunOnly` body; `OneGunOnly(id)` still runs it from a cast). Log lines: first sighting per person (max 40) and "enemy ..: hid the right-hand copy". (2) drops: the
  Papyrus `DeathDrop` was read again and its logic is right (one roll of `DropChance` (25): then 50/50 held gun or random gun from the `ListFor` list; so about 12% of deaths drop the held gun and 12% a random one); it was split into
  `WantHeld`/`DropHeld`/`DropRandom`/`Placed` (Champollion segfaults on the one-function version with three branches) and every step writes `Debug.Trace("Skylands drop: ...")` to the Papyrus log. The cause of "never random" is NOT
  found: read `Papyrus.0.log` for the "Skylands drop:" lines (held / random / PlaceAtMe gave no object / no drop).
- 0.35.1 in game (user, Papyrus.0.log 1afaca36 checked): the "Skylands drop:" lines show held/random/no-drop paths all working (10 "no drop this time", 2 "random gun from the drop list", no errors from our scripts): the user was just unlucky.
  New report: when an enemy drops the gun it held, the rarity beam stays where the enemy died. Cause (likely): the quest's `Sweep` moves beam and light to the gun (`MoveTo`) only every ~4 s, and a ref's
  position data can lag its physics-moved 3D. 0.36.0 (TestBuild-126, plugin 1.15.2): natives `TrackBeam(gun, beam, light)` / `UntrackBeam(gun)` (declared in `native_stub`, called from the quest's `Place` and `Clear`); the plugin keeps
  a list of handles (max 96) and a 33 ms thread queues `FollowBeams` on the game thread: beam and light are set to the gun's 3D `world.translate` (`PlaceRef`: `data.location`, the node's local translate, `Update`). Log "beam: following gun ..".
  The 4 s `Follow` stays as a fallback. UNCONFIRMED in game (that moving the REFR's 3D that way is allowed for these statics, that the beam stays attached while the gun rolls).
- 0.36.0 in game: the user says the beams "look better"; some beams are HORIZONTAL (PlaceAtMe copies the gun's angles to the beam ref). 0.36.1 (TestBuild-127, plugin 1.15.3): `PlaceRef` also clears the beam's and light's turn every frame
  (`data.angle` = 0, node `local.rotate.SetEulerAnglesXYZ(0,0,0)`), assuming the beam mesh points up along z at zero turn. UNCONFIRMED: if a beam is then pointing sideways always, the mesh axis is not z.
- 0.37.0 (TestBuild-128, plugin unchanged 1.15.3, pex/esp unchanged): SHIELDS, PHASE 1 (planning; no feature code). The user asked for BL2-style shields (capacity, damage hits the shield first,
  delayed recharge, shield items with rarity/models/stats from BL2 that enemies spawn with and drop like guns, a HUD bar). Phase 1 = survey, then `docs/shield-roadmap.md`, then WAIT for approval.
  `shieldprobe.py` (`python -m skylands_setup bl2shields`, `Check-BL2-Shields.bat`, writes `work\bl2-shield-report.txt`, `--minutes` 25, `--no-audio`) is driven by NAMES and CLASSES, not guessed paths
  (nothing about BL2's shield objects had been seen): name-table pass over every package (class-like / HUD-art-like / sound-like names), packages that define shield groups first, every export whose class,
  name or enclosing group says 'shield' (census by class), one-line dump of each, a breadth-first follow of references (attributes, resolvers/formulas first, nested Behavior children, part lists capped
  at 30 refs) from a spread of seeds, attribute groups and `GD_Globals`, the item-pool graph (which pools hold shields directly or through other pools, with sample pools in full), pawn balances that refer
  to a shield pool or have a shield-named property, the `Item_Shields.GestaltDef_Shields` gestalt cut into parts (triangles, extents, UV ranges, materials/textures; shield parts' `GestaltModeSkeletalMeshName`
  checked against the fragments), textures/movies, text inside HUD Flash movies (`swf_strings`), and shield sound event names checked against the Wwise banks. Every section runs on its own (`run`), the report is
  saved after each. Tested on a fake install (`tests/test_shieldprobe.py`); UNCONFIRMED on a real install: all of it (class names, group names, how long it takes, memory with ~70 packages open).
  Branch note: this session's branch `claude/sharp-wright-sxhjzr` started at the old 0.13.11 commit; the real latest work (0.36.1, SKSE plugin, relics, probes) was on `origin/claude/bold-ritchie-aw0mh2`,
  so the branch was fast-forwarded to it before any work. The Standing rules' "work on branch ..." means: the branch the harness gives you, after checking it is not behind.
- 0.37.0 report READ (user's `bl2-shield-report.txt`, 13,425 lines, all sections ran; the file lives only on the user's PC, so `docs/shield-roadmap.md` section 1 carries the facts): shields are `ShieldDefinition` items built from
  `ItemPartListCollectionDefinition` part lists (body/battery/capacitor/accessory/material, 9 manufacturers per slot) and `InventoryBalanceDefinition`s; stats come from `ShieldMaxValue / ShieldOnIdleRegenerationDelay (3.5 s base) /
  ShieldOnIdleRegenerationRate (0.16 x capacity per s) / ShieldConsumptionRate (+100000)`; parts only add integer SLOT GRADES (names by grade thresholds; the grade -> number table was NOT captured: the survey's 70-line dump cap cut the stock
  definition); the type effects are skills on accessory parts (numbers not captured); 96 `ItemGrade_Gear_Shield_*` balances, pool tree `Pool_Shields_All -> _01_Common/02_Uncommon/04_Rare/05_VeryRare/06_Legendary -> families`; enemies wear
  `GD_ItempoolsEnemyUse.Shields.Pool_Shields_Standard_EnemyUse` (probability 0.7 / 1.0 per play-through) and their loot lists hold shields at 20 % with `bDropOnDeath False`. The gestalt `Item_Shields.Gestalt.GestaltDef_Shields` cuts fine
  (32 fragments, 4,014 triangles). FRAGMENT NAMES ARE CROSSED: body parts point at `Shield_Accessory_*` meshes, accessory parts at `Shield_Body_*`, Maliwan reuses Pangolin's: always map by the part's `GestaltModeSkeletalMeshName`. 43 shield events exist in the
  Wwise banks (`Ak_Play_UI_Shield_Power_Up/Power_Down/Impact/Confirm/Booster/Roid_Buff`, `Ak_Play_FX_Player_Shield_Spike_*`, `Nova_Power_On`, ...); the break/recharge/low-warning mapping is a guess (the low warning is a property of the HUD object).
  The survey's flaws (to fix in the deep survey): it opened tiny enemy/vehicle packages first (298 particle objects in the census), capped dumps at 70 lines, did not dump `Default__` objects, and did not reach the main HUD movie.
- Shield DESIGN (docs/shield-roadmap.md, WRITTEN, AWAITING THE USER'S APPROVAL, nothing built): damage choke point = `ActorValueOwner::ModActorValue(kDamage, kHealth, negative)` (slot 6 of the ActorValueOwner part, found from a live actor, hooked for
  Character and PlayerCharacter) because our bullets are SPELLS and `Actor::HandleHealthDamage` (slot 0x104) would not see them (CommonLibSSE-NG v12.1.0 headers read: `DamageActorValue` is a wrapper over `ModActorValue`; `TESHitEvent` carries no damage).
  Capacity = ratio x wearer's max Health (BL2's formula text could not be read reliably), delay 3.5 s, rate 0.16 x capacity/s, ARMO items with keyword numbers, free biped slot chosen by the installer, actor values `Variable01/02/03` = capacity/rate/delay bonus,
  plugin-side state map, HUD bar drawn like the ammo HUD, Hunter-script spawn/drop/beam life cycle. Stages: 1 core + deep survey bat, 2 HUD + sound, 3 items, 4 enemies, 5 types, 6 extras. All UNCONFIRMED until stage 1 shows the hook works on 1.7.104.
- 0.38.0 (TestBuild-129, plugin 1.16.0 = "SkylandsNative 340"), SHIELDS STAGE 1 (the user approved the roadmap's defaults, and set the rule: BL2 file values replace static values): (1) `native/skse/src/shield.h`: replaces slot 6 (`ModActorValue`) of the
  ActorValueOwner vtable of the player (`Thunk<0>`) and of the other people (`Thunk<1>`, skipped if the tables are the same) found from LIVE actors (`AsActorValueOwner()`, offset logged), absorbs `kDamage`/`kHealth`/negative values into a per-actor `State`
  (map by form id), any hit restarts the delay, recharge `rate x capacity` per second after `delay`, break flag, optional gate, a 33 ms pump (`Update`) that gives the test shields (player `TestShield`% of max health, others `TestEnemyShields`% within 6000 units),
  recharges, tells the player ("Shield 120 / 300", "SHIELD BROKEN", "Shield recharging", "Shield full", "Enemy shield down") and logs; the hook checks its first 40 calls for nonsense (self-disable) and counts what it sees (`shield stats:` line every 20 s).
  Natives `ShieldPercent(Actor)`, `ShieldMax(Actor)` (no strings). UNCONFIRMED in game: all of it (that slot 6 is ModActorValue on 1.7.104, that bullets and melee arrive as kDamage with a negative value, the table sharing, that nothing crashes). READ FIRST: the log lines
  "shield hook (player/npc): ActorValueOwner part at +0x.., table .., slot 6 holds ..", "shield hook installed ...", "shield: hook saw Health change ...", "shield: .. took .. of .. damage", "shield stats: ..", and any "CRASH ... (shields: <stage>)".
  (2) `sheets/shields.json` (+ `sheet_data.SHIELDS`): every shield number with `source` bl2/design and `bl2_object`; `extract.shield_stats` reads `delay_s` and `rate_fraction`; `skse.shield_ini`/`default_ini` write the settings; build.py logs "shields: read from Borderlands 2: ...".
  (3) `shieldprobe --deep` + `Check-BL2-Shields-Deep.bat` (writes `work\bl2-shield-deep-report.txt`): uncapped dumps of the sheet's `bl2_object`s, one balance per family down to its skill, enemy shield formulas, `Default__` objects of the HUD/shield classes, the HUD movie.
  NEXT after the user's reports: read the log (is the hook right?) and the deep report (fill `design` rows with BL2 values; type effects), then stage 2 (HUD bar + sounds).
- 0.38.0 in game (user, SkylandsNative.log "SkylandsNative 340", Skyrim 1.7.104.0 AE lineage): the plugin loaded, the observer installed (player table module+192A178, npc table module+1923CE8, both slot 6 = module+6C51F0, ActorValueOwner at +0xB8), test shields created
  (player 66 of 110, enemies 14 of 35), BUT "damage to the player 0, damage to others 0, restores 282, other 0; shield absorbed 0": combat damage never goes through ActorValueOwner slot 6, the user died fast with no shield effect. Do NOT hook that slot for damage on this runtime.
  0.38.1 (TestBuild-130, plugin 1.16.1 = "SkylandsNative 350", `shield.h` rewritten): the shield is health stacked on health (temporary Health bonus C; per-update `DamageTaken` = max - current; new damage is booked shield first; recharge restores the shield's share; healing beyond real damage is undone;
  gate gives the rest back; strip on removal); a co-save record ('SKSH'/'SHLD') lists bonuses so a load takes them off (`g_stale`, `Strip`); the slot-6 hook is an observer only (counts and logs the first 60 Health changes after the player loads: "shield: observer saw Health change ..."). UNCONFIRMED in game: that adding a
  temporary Health bonus raises current Health too (the log line "has a shield of C: maximum health a -> b, current c -> d" shows it), that damage reads back as max - current, that a killing blow is absorbed, the co-save round trip (save with a shield on, load: "shield: load - N bonuses ...", then "its shield bonus of C was taken off").
  If the player's max health looks wrong after tests: console `player.modav health -<bonus>` (the bonus is in the log).
- 0.38.1 in game (user): "Shields look like they worked." (logs not re-read here; the deep report and setup log were). The user then asked, while away, for (1) a shield HUD over the player's and the enemies' health bars (shield = upper half
  blue, health = lower half red), (2) shield variations from BL2's parts and manufacturers with the real stats, (3) a new item slot for them, enemies and player equipping randomised shields, (4) as an extra, shields in loot tables, with
  an INTERVIEW about the chances BEFORE any numbers go in (DONE after 0.39.0 was sent; the answers are in 0.39.1 below).
- 0.39.0 (TestBuild-131, plugin 1.18.0 = "SkylandsNative 370"): (a) HUD `native/skse/src/shieldhud.h` (called at the end of `shield::Update`, 33 ms): finds the game's bars in the HUD movie (`_root.HUDMovieBaseInstance.HealthMeterAnim`/`Health` for
  the player, `EnemyHealth_mc` and its parts for the enemy in the crosshair, via `getBounds(_root)`), covers them with its own clip `_root.SkylandsShield` (backing, red lower half = real health, blue upper half = shield, orange when low,
  lighter when recharging, white flash when it breaks), fades with the game's bar (`_alpha`/`_visible` of the clip and its parents), remembers the bar's full width (when the game shows it full). `State.hpFrac` and `shield::ViewOf` feed it.
  Ini `ShieldHud/Mode/Enemy/Follow/Align/X/Y/Width/Height/EnemyX..Height/Log`; mode 2 = a thin bar above the game's. The first 70 lines say what it found ("shield hud: player bar: ...", "enemy bar: EnemyHealth_mc.<part> [x,y - x,y]"): UNCONFIRMED
  in game: all of it (that the geometry guesses are right, that the covering clip hides the game's fill, the enemy bar's part names). The plain "Shield 120 / 300" lines stop once the display has drawn. (b) Items: `tools/shield_report.py`
  parses the deep report (`--emit` writes `setup/skylands_setup/shielddata.py`: body/battery/capacitor/material grades, accessory fragments, prefixes, titles, capacitor lists). BL2's model (read from the report): a shield's slot grade = body + battery +
  capacitor parts (each its own manufacturer, equal grades per manufacturer) + the material (rarity); stat = base x (1 + grade x step), steps capacity +0.03, rate +0.03, delay -0.04 per grade. `shields.py` rolls 6 builds per type x rarity
  (`variants_per_roll`; 19 families incl. 4 uniques; bodies all different, every third build matched), computes ratio/rate/delay (capacity base `capacity_ratio` 0.35 of max health is a DESIGN value: BL2's own formula does not fit Skyrim's health),
  names them like BL2 (prefix by strongest part grade for the body's manufacturer + manufacturer + title), writes KYWD `SkylandsShield` + `SkylandsShield_t.._e.._k.._r.._d.._g..`, an ENCH per item (stats text on a display-only MGEF; a copy of the vanilla
  armor resist enchantment for resistance capacitors, `resist_percent` 50 design), the ARMO (clothing, one biped slot, no worn model: an ARMA with no model; world/inventory model cut from BL2's shield gestalt with the atlas `Item_Shields.Textures.Shield_Dif`,
  or a stylised orb when the BL2 meshes cannot be read). `choose_slot` scans every plugin in Data (not our own) for ARMO/ARMA biped slots and takes the first unused of 60, 61, 59 ...; the choice is kept in the ini (`ShieldSlot`). A real NEW biped slot
  does not exist (Skyrim has 30-61 only): tell the user. `bl2/extract.shield_parts` reads the same part objects from the player's files and `Tables` lays them over the survey (setup log: "N of M part tables read ... differ"). Skylands.esp is unchanged (test).
  (c) Plugin side `shielditems.h`: at data load finds every ARMO with a `SkylandsShield_` keyword (catalog by rarity); the 400 ms pump (`shield::g_itemPump`, replaces the test shields when items exist) gives each actor the state of what it wears in the slot
  (`GetWornArmor`, with `TESEquipEvent` as a fallback because an armor with no model may not show in the body's data), people near the player who wear none get one by a stable roll of their own form id (`EnemyShieldPercent`, rarity by level and the guns' weights
  122/50/20/6/1), the player gets one starter shield (co-save record 'STRT'), `shield::Give(..., rate, delay, item)`/`Remove`. Death: `ShieldDropPercent` (100 = the shield stays on the body = lootable). NO Papyrus changed (no ghost scripts). IniVersion 4: an older
  settings file is kept as .ini.old and the test shields (TestShield/TestEnemyShields) are 0 with items. UNCONFIRMED in game: everything (that the slot is free, that the ARMO with an empty ARMA equips and shows in the slot data, NPC equip via `EquipObject`, the mesh
  cut/scale/texture, the stats card text on an armor enchantment, the resist enchantment donors `^EnchArmor.*Resist(Fire|Shock|Poison|Magic)` being found, the HUD). The type effects (nova, spike, amp, roid, absorb, booster, turtle, adaptive) are NOT active; the item text says so.
  Read first in the next logs: setup log "shields:" lines (slot, items, meshes, part tables), SkylandsNative.log "shield items:" and "shield hud:" lines.
- 0.39.1 (TestBuild-132, plugin 1.18.1 = "SkylandsNative 371"): the loot interview, answered by the user: (1) a worn shield stays on a dead body 25 percent of the time (`ShieldDropPercent` 25); (2) "tougher = more likely": the chance a person carries
  one is `EnemyShieldPercent` 10 + `EnemyShieldPerLevel` 2 per level above 1, at most 95 (`shielditems.h` Pump); (3) also chests and containers, merchants, and the rarity beam on loose shields; (4) "level gates and better loot from bosses": rarity by level
  gates (common 1, uncommon 3, rare 8, epic 15, legendary 30; weights 122:50:20:6:1) and a BOSS (named: the base record is flagged unique; or level >= `ShieldBossLevel` 35; and hostile to the player when it is given) always carries one of rare or better
  and always leaves it on the body (my reading of "better loot from bosses"; say so if the user meant something else). Implementation, all in the models plugin (`shields.loot`): per-rarity leveled lists `SkylandsShieldTier_<n>`, `SkylandsShieldsAny`/`Good` (gated entries,
  the guns' weights), chests: the overridden `SkylandsAmmoDrop` (boss chests already hold it) gets shield entries from the Good list (about `chest_chance` 25 percent of its entries), merchants: every vendor chest (CONT) of Skyrim.esm with "vendor" and
  blacksmith/smith/armor/general in its editor id (max 40, logged: "shield loot: ... merchant chests stock them") is overridden with one `SkylandsShieldStock` entry (chance none 50 percent), beams: the `SkylandsGunList` FLST (Skylands.esp's, untouched) is
  overridden in the second plugin with every shield appended, so the quest's existing 4 s scan (`FindRandomReferenceOfAnyTypeInList` -> `Consider` by the base's `SkylandsRarity_` keyword) puts the beam on a loose shield: NO Papyrus changed. Shields also carry the vanilla
  `VendorItemClothing` keyword so merchants buy them. UNCONFIRMED in game: all of it (that the vendor chest names match real merchants, that vendor chests restock a leveled list entry, that ARMO bases work in `FindRandomReferenceOfAnyTypeInList`, the boss test).
- 0.39.1 in game (user, setup log e2548f05, SkylandsNative.log 40e7d128 "SkylandsNative 371", screenshots): the HUD, the items (372 in 19 families, slot 59, 294 real meshes, 69 of 69 part tables read from the files with 0 differing from the
  survey), the starter shield, enemy shields (two people got one: "FF000E22 given ...") all ran, no crash line. 0 merchant chests matched (names unknown: the log now lists candidates). User: mode 2 (the thin bar) is preferred but too wide, wants the width
  of the game's health bar; "my health still takes damage while the shield takes damage"; unsure whether enemies had shields -> all people get one for testing. FINDINGS: (1) the log's player bar: `Health`/`HealthMeterAnim` are 737 wide because they
  hold `HealthPenaltyMeter_mc` ([272,665 - 1009,683]); the bar itself is `HealthMeter_mc` ([498,667 - 784,687], 286 wide, alpha 0 when the game fades it at full health): the shield bar used the wide parent. (2) damage booking is right in the log:
  every absorbed hit shows "the shield 8.7, its health 0.0" and only overflow reaches health ("shield 4.6, health 34.5"); what the user sees is the GAME's health bar, which draws current/max of Health = health + shield added together, so it falls with
  absorbed hits. (3) the shield was tiny: 23 points (29.8 % of max health 77) against hits of 9-39; one burst killed the player (a "171.8 damage" line is the death: current health fell below 0). (4) enemies: 2 people were given a shield (10 percent odds at level 1).
  The `enemy bar:` structure was never logged because the look-once flag was spent on a first call that failed (an enemy bar not shown has no extent): fixed.
- 0.39.2 (TestBuild-133, plugin 1.18.2 = "SkylandsNative 372", IniVersion 5): `shieldhud.h`: the bar's width, place and height come from `HealthMeter_mc` (not its parents), default `ShieldHudMode=2`; the structure of the health meter is logged once found ("player bar: the game's
  HealthMeter object holds [...]", "HealthMeter_mc.<child> [...]", `lastHealthMeterPercent`) to find the real fill; `ShieldHudHealth=1` (opt-in, mode 2 only, `ShieldHudInsetX/Y` 0.09/0.28 = guessed frame and caps) paints the inside of the game's bar with the REAL health in a flat red over a dark
  backing and fades with the bar's own fill clip (UNCONFIRMED how it looks: the insets are guesses); enemy bar failures are logged (max 3 lines). `shielditems.h`: `ShieldCapacityScale` (every capacity times it), the ordinary-person chance cap is 100. Ini defaults for TESTING:
  `EnemyShieldPercent=100` (sheet `enemy_percent` 100; the user's chosen play odds 10 + 2 a level are in the sheet note and the ini comment: set them back after testing). `shields.loot`: merchant chests by "vendor" + kind, else every "vendor" chest, else a log line naming
  the containers with shop-like words (so the pattern can be corrected from the next log); an empty container gets its count and entry before its data. Read first next time: "shield hud: player bar:" lines (the bar's inside), "enemy bar:" lines, "shield loot:" in the setup log.
- 0.39.2 in game (user, one screenshot, no logs): "I like just having the shield bar drawn, keeping original skyrim hud healthbar" (so `ShieldHudHealth` stays 0 and mode 2 stays the default). The player's thin bar is now exactly as wide as the game's health bar (752-1177 px of
  1920; the empty dark strip is the trough with the shield broken). The ENEMY's thin bar sat on the enemy's own health bar (80-95 px, inside the frame 773-1148 px) and hid it. 0.39.3 (TestBuild-134, plugin 1.18.3 = "SkylandsNative 373", no ini change): `shieldhud.h` `kEnemyDrop` 6 HUD units
  (9 px) added to the enemy bar's place (`ShieldHudEnemyY` still adds to it, positive = down); the user's message was cut off ("... to uncover the enemy'"), read as "the enemy's health bar". The enemy bar's structure lines ("enemy bar: ...") are still not seen in any log. UNCONFIRMED in game.
- 0.39.3 was never sent (its DLL was built by CI, TestBuild-134 not packaged): 0.39.4 replaces it. User report on 0.39.2 (logs 6c1b3493 SkylandsNative "SkylandsNative 372", f9c88382 setup 0.39.2): "only a few enemies had shields" and "my health is lower than my base health".
  READ FROM THE LOG: (1) every enemy that fought (FF000F.. gun-armed bandits, level 1, max health 35) was given a shield ("is given ..", "now has ..", "has a shield of 8..21"), so the loot/arming side worked; the people who never got one were creatures
  (wolves, skeletons, spiders ...: `IsPerson` needs the ActorTypeNPC keyword), plus the shields are tiny (8-21 points on 35) and the enemy bar only shows for the crosshair target. (2) THE GAME DOES NOT KEEP A TEMPORARY HEALTH BONUS ACROSS A LOAD:
  at every load the log said "its shield bonus of 25 was taken off" then "has a shield of 25: maximum health 85 -> 110, current 85 -> 110" - the player's base is 110 (the 0.38.0 log), the old stale-bonus cleanup subtracted a bonus that was not there, so the shield was carved out of
  the player's own pool and granted nothing. Pump/Strip fix below. (3) the vanilla `IsInCombat` is a virtual (slot 0xE3), so the display does not call it.
- 0.39.4 (TestBuild-135, plugin 1.18.4 = "SkylandsNative 374", no IniVersion change: new keys take defaults): (1) health: `State.lastMax/baseMax/reapplied`, `Stale{capacity,shield,baseMax,hasBase}`, co-save record 'SHLD' version 2 (id, capacity, shield, baseMax; version 1 read as "no baseMax = bonus not present");
  on load a listed bonus is taken off ONLY if the actor's max shows it (`maxNow >= baseMax + 0.5 capacity - 0.5`), else the log says "the loaded game no longer has the shield bonus of C on it ... nothing to take off"; in `Step` a max that falls by exactly the capacity between two looks is the bonus lost
  at run time: it is put back (log "lost its shield bonus ... put back", at most 20 times per shield); a line every 20 s: "the player's health now X of Y (without the shield A + shield bonus B)" (Y should be A + B; first 40). After a load the shield starts full (the damage split across a load is not kept).
  (2) enemies (`shielditems.h` Pump): a creature/animal/undead/dragon that is hostile to the player (`IsHostileToActor`) gets an innate shield (item 0) of `EnemyShieldCreatureRatio` 0.35 x its max health (`EnemyShieldCreatures` 1); a person with a shield keeps it while its item is in the pack
  (`InPack`; before, a moment of `Worn()==null` removed it and the once-only roll never gave it back); a person is given the state at once after `PutOn` (`Follow(actor, armor)`); the log line "shield items: N living actors within reach ... M with a shield ... K fighting the player" (every 15 s when it changes, 60 lines)
  says why someone has none. (3) the player's bar fades (`ShieldHudHideAfter` 3 s, 0 = never): up while any actor within reach has the player as `currentCombatTarget` (`shield::g_combatNear`, counted in the Pump), while the shield is below full, and for N s after the shield or health last changed;
  0.15 s in, 0.6 s out. The enemy's bar still follows the game's `EnemyHealth_mc`. The old code used the game's alpha chain only (the HealthMeter clip's own fade was ignored: `meterAlpha`). UNCONFIRMED in game: all of it (the max stays A + B after a load and during play, creatures' shields, the fade, `currentCombatTarget` being the player for NPC attackers).
  Enemy bar structure (from the 6c1b3493 log): EnemyHealth_mc [510,51 - 770,91]; instance120 [510,51 - 770,64], instance121/189/190 [523,55 - 757,59], BracketsInstance [532,60 - 747,91]; the pick is the "bracket" part (the bottom of it).
- 0.39.4 in game (user): many enemies still without shields (the user had turned creature shields off), no shield has DROPPED yet (25 percent of bodies; that is why every NPC should carry one), the recharge delay kept counting while a menu was open
  (the plugin's clock is `steady_clock`; Skyrim's menus pause the game but not it), the player's bar should be about 20 px narrower. The user wants shields on humanoids / NPCs only, "just like the guns" (the `NPC` keyword), NOT creatures.
- 0.39.5 (TestBuild-136, plugin 1.18.5 = "SkylandsNative 375"): (1) creature shields removed (`EnemyShieldCreatures/Ratio` gone). (2) game clock: `shield::g_gameNow` = steady time minus the time `UI::GameIsPaused()` was true; `Step` and `Apply` use it and `dt` is 0 while paused,
  so neither the delay nor the recharge runs in a menu. (3) player bar `kPlayerNarrow` 13 HUD units (about 20 px at 1920), `ShieldHudWidth` still overrides. (4) possible cause of people with no shield: a person whose item is not found in the pack (`InPack`) lost the shield and, rolled once (`g_decided`), never got another;
  now `g_decided.erase(id)` re-rolls them; the pump looks at 40 actors (was 24) and gives 4 per pass (was 2). The pump's line says how many actors in reach have a shield. UNCONFIRMED in game: all of it. If many humanoids still have none read "shield items:" lines (is given / now has / living actors within reach)
  and check whether those races lack the `ActorTypeNPC` keyword (`IsPerson`; draugr, falmer, ... are probably creatures to it - the guns use the NPC keyword on the ACTOR, not the race, so the two tests may differ).
- 0.39.5 in game (log ba8403cb, plugin 375, `ShieldDropPercent=100`): EVERY gun-armed enemy (FF000F00/19/27/48/4B) had a shield; the pump line said "8 living actors, 6 with a shield, 2 actors that are not people, 4 fighting the player" - the unshielded ones are what `IsPerson` rejects
  (names not logged then). No shield dropped although DeathSink removes nothing at 100 percent (the shield should stay in the dead person's pack; cause unknown). 0.39.6 (TestBuild-137, plugin 1.18.6 = "SkylandsNative 376"): `IsPerson` also accepts races whose editor id
  contains Draugr/Falmer/Vampire/Forsworn/Hagraven/Orc/Nord/Breton/... (UNCONFIRMED that race editor ids exist at run time); the first 30 rejected actors are logged with name and race ("is not a person: no shield"); every death of a shield wearer logs
  "died wearing X: 1500 ms / 5000 ms later it is IN/NOT in its pack" - READ THAT to see why nothing drops (item removed by the game/outfit, or present but unlootable).
- 0.39.6 in game (log ce203950, plugin 376): every person had a shield, only mudcrabs/wolves ("race MudcrabRace/WolfRace") were "not a person" (race editor ids ARE readable); NO "died wearing" line at all (so `ItemOf` was already 0 at the death event: the state is erased when `IsDead`), the user
  sees the shield in the corpse's inventory but wants it DROPPED like a gun; enemy shield bars show for "only some" enemies (the log has no "enemy bar:" lines this time: the crosshair target rarely had a shield, it is not the game's "last hit" enemy); enemies heal after a few seconds = the shield recharging.
- 0.40.0 (TestBuild-138, plugin 1.18.7 = "SkylandsNative 377"): (1) `DeathSink`: 900 ms after a person dies the shield ARMO found by `GetInventory` is dropped (`RemoveItem(kDropping)`) with `ShieldDropPercent` chance (boss always), else removed ("died; its shield .. was dropped on the ground / was not left"; none: "died with no shield item in its pack");
  the quest's 4 s scan puts a beam on a loose shield (FLST override, UNCONFIRMED). (2) HUD enemy target: crosshair actor if it has a shield, else `shield::RecentlyHit(4)` (the shielded enemy hit last). (3) `shieldaura.h`: temporary effects of our meshes `Fx_ShieldAura_0..2` (three strengths by the shield left) respawned every 50 ms at the waist of every shielded
  enemy within `ShieldAuraRange` 2200 (max 10 a frame), and `Fx_ShieldBurst` swelling for 0.55 s after a break (`View.sinceBreak`); meshes are `nif.glow` crossed quads written by `shields.build` (stood up by a quarter turn about x; symmetric two layers). Ini `ShieldAura`, `ShieldAuraRange`. UNCONFIRMED in game: all of it (looks, scale, whether the effects show on a moving actor, performance).
- Stage 2: `docs/stage2-animation-types.md` is written; the user is unsure one-handed and hand-to-hand help, so drop them from
  the proposed lineup unless asked; "a new weapon type" would need new animations and a behavior-graph patch (or SKSE with an
  animation replacer), not plain Papyrus.
- Placeholders: tracer/projectile art (donor fireball), per-element ammo on the crossbow guns, explosion radii and
  rocket speeds (`sheets/shooting.json`, `SPLASH`).
- The user's Stage 2 instruction: after the Stage 1 report they say which animation type suits each gun type; convert
  nothing else before that.
- Test tools in a fresh container: `apt-get update`, then `liblzo2-dev libboost-program-options-dev libfmt-dev`, `pip install python-lzo`;
  Champollion needs `#include <cstring>` in `Pex/FileReader.cpp` and `<strings.h>` in `Champollion/CaselessCompare.h` on Ubuntu.

## 7. Open questions for the user
- SKSE: added in 0.14.0. Still unknown: the user's Skyrim runtime version (the installer logs it) and whether they have SKSE and Address Library yet.
- Melty dependency handling.
- Which animation type for each gun type (Stage 2).
