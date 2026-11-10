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
- 0.40.0 in game (user): shields drop, every enemy's shield HUD showed. 0.40.1 (TestBuild-139, plugin 1.18.8 = "SkylandsNative 378"), user requests: the glow is OFF by default (keys renamed `ShieldGlow` / `ShieldGlowRange` so the old `ShieldAura=1` in the user's file is ignored; `shieldaura.h` stays for later);
  `EnemyShieldPercent` back to 10 (+2 a level; sheet value 10) and `ShieldDropPercent` 25: `merge_ini` puts those two keys back ONCE when `ShieldDefaultsRev` (ini, now 2) differs from the old file's (the installer otherwise keeps the user's values); shield descriptions list only the stats
  (capacity, recharge, delay, resist, type text; the "Parts:" line and the "(grade +n)" notes are gone). UNCONFIRMED in game.
- 0.40.1 in game (user): "everything's looking good", but the shield models look inside out ("I can see into it"; no screenshot arrived). Cause (found in code): the guns' meshes go through `gunparts.orientation` (a mirror: UE3 is left-handed; `meshes.transformed` reverses the triangles when det < 0),
  the gestalt-cut shield parts did not, so backface culling showed the inside. 0.40.2 (TestBuild-140, python-only, plugin still 1.18.8): `shields.Models.mesh_for` mirrors x (`transformed` with diag(-1,1,1), centred) for real BL2 parts; the proxy orb is untouched. UNCONFIRMED in game. NEXT: relics (docs/relics.md; the user chose to do them next - interview first).
- RELICS, PHASE 1 (0.41.0, TestBuild-141, python-only, plugin still 1.18.8; includes the 0.40.2 shield mesh fix): the user's interview answers: worn in its OWN spare armor slot like shields (one relic at a time); effects wanted: gun stats we have (fire rate / reload / accuracy =
  actor values `Variable06/07/08`, docs/relics.md), AND damage + magazine size (new plugin work), AND shield stats (capacity / recharge / delay), AND health / speed / regen (Skyrim actor values); numbers and names from a Borderlands 2 SURVEY first (BL2 calls relics "artifacts":
  class `ArtifactDefinition`); loot: enemy drops (like shields: dropped on the ground with the rarity beam, level-gated rarities, better from bosses), chests, merchants (no starter relic chosen). The survey: `python -m skylands_setup bl2shields --topic relic` / `Check-BL2-Relics.bat`
  (writes `work\bl2-relic-report.txt`; `shieldprobe.set_topic("relic|artifact")` re-points the name scan, census, definitions, attributes and loot pools; no enemy/art/HUD/sound sections; test `test_relic_survey_finds_artifact_definitions_and_the_pools_that_hold_them`).
  NEXT: the user sends `bl2-relic-report.txt`; read it (classes, part lists, manufacturers, the stat attributes and their grade steps, rarities, loot pools), write `docs/relic-roadmap.md` (like the shield one), WAIT for approval of the defaults, then build `relics.py` / `relicdata.py` (generated from the report like shields), plugin work for damage + magazine, and the loot interview answers above.
- RELIC REPORT READ (0.41.1, TestBuild-142; `bl2-relic-report.txt` 10,704 lines, user's PC only; facts are in `docs/relic-roadmap.md`): `ArtifactDefinition` = Eta body (type) + Alpha/Beta (`Enable1st..4th` effects) + Theta upgrade grades; numbers via `Init_ModifierBase_Linear` (1.0 x `ArtifactItemLevel`); types Vitality, Protection, Resistance, Stockpile, Strength, Elemental(+Status),
  Tenacity, Aggression A-F, Allegiance A-H, Proficiency, uniques; pools `Pool_Artifacts_01..05`; the report stopped before the nested behaviours so WHAT each body changes and by how much is not known. 0.41.1 adds `Check-BL2-Relics-Deep.bat` (`bl2shields --topic relic --deep`, `deep_relics`: R1 parts down to the behaviours, R2 the level formulas,
  writes `work\bl2-relic-deep-report.txt`). NEXT: the user sends it; then relic data (`tools/relic_report.py` like shield_report), items, loot, plugin effects - design in docs/relic-roadmap.md section 2 (the user must approve the defaults first, as for shields).
- RELIC DEEP REPORT READ (user's `bl2-relic-deep-report.txt`, 49,027 lines): the numbers are in each `ArtifactDefinition`'s `AttributeSlotEffects` (the behaviours the first survey looked for are empty): per effect `AttributeToModify`, `ModifierType` (MT_Scale / PostAdd / PreAdd),
  `BaseModifierValue` = `Init_ModifierBase_Linear` (the relic's level) x scale, plus `PerGradeUpgrade` x grade. Value = level x scale + grade x per-grade (a fraction): Vitality HealthMax 0.004/lvl + 0.02/grade; Protection ShieldMax 0.003 + 0.01 and shield regen rate 0.003 + 0.01;
  Resistance six impact modifiers (-0.0024..-0.004 + -0.01..-0.013); Stockpile ammo max 0.005 + 0.03; Strength melee damage 0.003 + 0.01; Tenacity revive (n/a); Terramorphous health regen 0.005; Endowment XP 0.0008 + 0.004; Elemental/Status element damage 0.003 + 0.01 (PostAdd);
  Aggression A-F weapon-type damage 0.003 + 0.01; Allegiance A-H manufacturer: damage 0.003 + 0.01, reload +0.025, fire rate +0.015, clip +0.005 + 0.03, accuracy impulse/idle regen +-0.005 + 0.05/-0.06; Deputy/Sheriff small damage + reload/fire rate; Afterburner/Opportunity/Proficiency/Vault Hunter (n/a: vehicles, shop, skill cooldown, drops).
  The user's decision: general stats first as player variables (health, shield, damage, magazine, speed...), manufacturer/type-specific relics LATER.
- 0.42.0 (TestBuild-143, plugin 1.19.0 = "SkylandsNative 380"): the plugin reads more of the player's spare actor values (docs/relics.md): `Variable09` damage % (the player's bullets launch with `LaunchData.power` = 1 + v/100; UNCONFIRMED that spell damage follows power: check the shield log "took .. damage" with the value at 0 and 100; fallback = bonus
  damage on the hit event), `Variable04` magazine size % (`PlayerGun.baseClip`, `info.clip` rescaled every tick, the magazine capped), shield `Variable01` capacity % (`State.baseFrac`; a change strips and re-applies the shield), `Variable02` recharge rate %, `Variable03` delay shortened %. Console-testable (`player.modav variable09 50`).
  NEXT: relic items (ARMO in a spare slot with a constant-effect enchantment that fortifies those variables, plus Skyrim's own Fortify Health, resists, regen), data from the report above, loot like shields.
- 0.42.0 in game (user, log fd308ede plugin 380): "everything looked good"; the log shows no error or crash; the relic lines work ("relic: damage x21.00 ... magazine x2.00: 86 rounds", "shield: the player's capacity bonus (Variable01) changes the shield from 60.2% to 178.8%"). The log has NO enemy "took .. damage" lines (the first 30 told were
  the player's), so the damage bonus on enemies is judged by the user's eyes only.
- 0.43.0 (TestBuild-144, plugin 1.20.0 = "SkylandsNative 381"): RELIC ITEMS. `relics.py`: 5 kinds (Vitality h, Protection s+r, Resistance f/k/c/x, Stockpile m, Aggression d = all guns: a design generalisation of BL2's weapon-type relic) x 5 rarities x 2 builds (the Prime is one grade better; `GRADE_OF_LEVEL` 0,1,3,6,9) = 50 ARMO (clothing, own biped slot
  `relics.choose_slot`, never the shields', ini `RelicSlot`), stand-in ring mesh `Meshes\Skylands\Relics\relic_<level>.nif` (gem colour = rarity), ENCH text via `stats_effect`, keyword `SkylandsRelic` + `SkylandsRelic_l<level>_<letter><per level 1e-5>x<flat 1e-5>_...` (value = character level x per level + flat, a fraction;
  BL2's numbers from `AttributeSlotEffects`), vendor keyword. `shields.loot` now takes `extra` groups: the relics get `SkylandsRelicTier_n`, `SkylandsRelicsAny/Good`, `SkylandsRelicStock` lists, half the shields' chest/stock chance, one override per vendor container (both stocks), and join the beam FLST.
  Plugin `relic.h`: catalog at data load; every 400 ms (`shield::g_relicPump`, from shield::Update) the player's worn relic (`GetWornArmor` + a `TESEquipEvent` fallback) sets the player's actor values by `Move` (a temporary modifier this plugin tracks in `g_applied`; `Revert()` on a load/new game clears it because the game drops temporary values):
  h -> kHealth (fraction x base Health), s/r/m/d -> Variable01/02/04/09, f/k/c/x -> ResistFire/ResistShock/PoisonResist/ResistMagic (points); log "relics: the player wears ..". People: roll by `Mix(id ^ ..)`, `EnemyRelicPercent` 8 + `EnemyRelicPerLevel` 1 (max 100), bosses always rare+, `PutOn`; `DeathSink`: 1.1 s after death the relic in the pack is dropped
  (`RelicDropPercent` 100) or removed. Enemies get no effects from relics (loot only). Ini keys `Relics`, `RelicSlot`, `EnemyRelicPercent`, `EnemyRelicPerLevel`, `RelicDropPercent` (written when a relic slot was chosen). UNCONFIRMED in game: all of it (that the slot is free, that the relic equips and shows in the slot data, the ring model, the health/resist
  modifiers taking effect and coming off, the loot lists, the compile of relic.h). Not done: weapon-type / manufacturer / element relics, uniques, health regen, melee, XP, a real BL2 mesh (the artifact gestalt `Item_Artifacts.GestaltDef_Artifact`).
- 0.43.0 in game (user): the game CRASHED after the Bethesda logo (Papyrus log empty of Skylands, no plugin log sent). Cause found in code: `relic::Catalog` held `g_lock` and called `InfoOf`, which locks the same non-recursive `std::mutex`
  (deadlock/crash at the first relic found, at data load). 0.43.1 (TestBuild-145, plugin 1.20.1 = "SkylandsNative 382") parses first and locks only to push. LESSON: never call a function that takes a lock while holding it; the same pattern in new
  plugin code should be grepped for (`lock_guard` blocks that call other helpers). Wait for the CI DLL (version 1.20.1) before packaging.
- 0.43.1 in game (user): no crash, relics drop. 0.44.0 (TestBuild-146, python-only, plugin still 1.20.1), user request "get the models from Borderlands 2": relic models are cut from the artifact gestalt mesh
  `Item_Artifacts.GestaltDef_Artifact` (same machinery as the shields: `gunparts` now also loads definitions whose path has `item_artifacts` and files holding `gestaltdef_artifact`). `relics.write_assets(out, colors, source, say)`: one NIF per
  kind x rarity (`relic_<kind>_<level>.nif`) = the kind's body fragment (`BODY_FRAGMENT`: vitality Type_HealthBuff, protection Type_ShieldsKillSkills, resistance Type_Elemental, stockpile Type_Inventory (a guess), aggression Type_Weapons) + the rarity's ring
  (`RING_OF_LEVEL`: Ring_Single/Double/Triple; BL2's upgrade parts use Ring_Double for grades 8-11 and Ring_Triple 12+), x mirrored, scaled to `RELIC_SIZE` 9; fallback = the old ring-with-gem. Textures: the atlas name is NOT known (guesses `ATLAS_GUESSES`; the
  deep report only shows `PickupFlagIcon fx_shared_items.Textures.Artifact_Dif`, the pickup icon), so the cut parts are plain colours (kind colour for the body, rarity colour for the ring). READ in the next setup log: "relic models:" lines (fragments found in the
  table, texture result, "N cut from Borderlands 2's artifact mesh, M stand-in rings") and the "relic: gestalt part ..." lines (triangle counts). UNCONFIRMED in game: that the fragments exist under those names, orientation/size, looks. NEXT: the body parts' `p_EmissiveColor`
  (in the deep report) can replace the design colours; find the atlas texture name from the setup log or a survey.
- 0.44.0 in game (user, setup log d185fef1): the relic models "look good" (25 of 25 cut; the artifact fragments are Ring_Single/Double/Triple and Type_ActionSkill, DownState, Economy, Elemental, Enemies, Grenades, HealthBuff, Inventory, Melee,
  ShieldsKillSkills, Vehicle, Weapons, XP); too small. The artifact texture was NOT found (the guessed names do not exist) and the gestalt mesh was read with NO UVs ("1256 vertices, 1672 triangles, uvs no", element 32 bytes, position at 16).
  0.45.0 (TestBuild-147, plugin 1.21.0 = "SkylandsNative 383"): (1) `RELIC_SIZE` 27 (3x). (2) textures: `gunparts.gestalt_texture("item_artifacts")` finds the diffuse through the materials the gestalt mesh export refers to (`gunmesh.material_refs` ->
  `texture_parameters` -> `pick_textures`; lines "gestalt texture: ..." in the setup log, the texture time budget is lifted for it), `relics.write_assets` shades it per kind (body) and per rarity (ring) with `dxt.shade`; `gunmesh.loose_uvs` is a looser UV search inside a
  one-array vertex element (accepts >= 90% of values inside 0..1, picks the smoothest candidate over the triangles; the note lists every candidate, "loose uv search found none (...)" says why not). UNCONFIRMED: that the texture is found and the UVs right; if the
  relics stay plain read the "gestalt texture:" and "gestalt mesh Item_Artifacts" lines. (3) ini: `RelicHealth`, `RelicShieldCapacity`, `RelicShieldRecharge`, `RelicMagazine`, `RelicDamage`, `RelicFireResist`, `RelicShockResist`, `RelicCorrosiveResist`, `RelicExplosiveResist`
  = multipliers on that effect of every relic (plugin `relic::g_scale`; the item text shows the 1.0 numbers). (4) the user: the per-level share grows with rarity: `PER_LEVEL_FACTOR` 1..5 x BL2's number (Aggression 0.3 / 0.6 / 0.9 / 1.2 / 1.5 % a level), all kinds; the grade part is unchanged.
  The user's message about "adjusting some of the effects" ended at a colon (no list): ask what they want changed.
- 0.45.0 in game (user, setup log 8e3ac6ef): relics stayed plain. READ: the artifact gestalt mesh's UVs ARE the half-float pair at element offset 28 (loose search: in0..1 0.40, 361 distinct, roughness 0.011; the strict test and my 90 percent rule rejected it because the layout tiles past 0..1);
  the material `Item_Artifacts.Materials.Mat_ItemArtifact` is a plain Material (no TextureParameterValues; `texture_parameters` found nothing) and the mesh export refers to no material. 0.45.1 (TestBuild-148, python-only, plugin 1.21.0): `loose_uvs` accepts inside >= 0.3 with roughness < 0.03;
  `gestalt_texture` also logs the material's properties and children (their `Texture`), lists the Texture2D objects whose path holds the word ("gestalt texture: Texture2D objects of the package named like 'item_artifacts'") and tries them (pick_textures, then all). READ those lines next: if no texture is found, the
  artifact texture lives in another package (`fx_shared_items.Textures.Artifact_Dif` is the pickup icon) and the material's expression objects must be walked.
- BADASS ENEMIES, PHASE 1 + stage 0 (0.45.2, TestBuild-149, python only, plugin still 1.21.0): `docs/badass-roadmap.md` (interview answers, design, stages, risks), APPROVED with the user's changes (its section 2a):
  three tiers by the PLAYER's level (Badass from level 1), people AND creatures, dragons are bosses, creatures drop one random gun/shield/relic at half the people's chance, every Badass one guaranteed drop with a
  rarity shift, name prefix + size only, better carried gear LATER. Sheets `sheets/enemy_stats.json` (per Skyrim race class) and `sheets/badass_tiers.json` (per tier) -> `sheet_data.ENEMY_STATS/BADASS_TIERS`
  (not read by the build or plugin yet). Survey `badassprobe.py` (`python -m skylands_setup bl2badass`, `Check-BL2-Badass.bat`, writes `work\bl2-badass-report.txt`): pawn balances by tier, formulas, pools,
  badass objects, and ENEMY AUDIO (voice/sound events per family checked against the Wwise banks), dialog objects. NEXT: read the report, put BL2 values into the two sheets (`source: bl2`), then stage 1 (plugin: tiers + stats).
- 0.45.2 in game (user): the survey STALLED in B1 (pawn balances). Cause (code): B1 walked every `gd_population*` / `gd_balance*` group with `group_objects`, and each population group is copied into many big level packages,
  so with the index's 24-package cache the same packages were reopened and decompressed again and again, with no progress line. 0.45.3 (TestBuild-150, python only): `badassprobe.objects_in_groups` reads each group from ONE package
  (most of the group, smallest file), bundles groups by package and opens every package once (progress line every 10 packages, deadline checked per package); B1 keeps the tier balances' properties for B2 (no second lookup);
  B4's pool list uses the same reader over `gd_itempools*` only. Lesson: never loop `group_objects` over hundreds of groups of a real install. The shield survey's `enemies()` has the same loop (it finished for the user, slowly).
- BADASS REPORT READ (user's `bl2-badass-report.txt` of TestBuild-150, 51,714 lines; facts in `docs/badass-roadmap.md` 1.1b; `python tools/badass_report.py <report>` derives the numbers): a Badass = `Champion=True` balance + its own AI class whose
  `AttributeStartingValues` set `Attribute_HealthMultiplier` / `Attribute_EnemyNonWeaponDamageMultiplier` (melee, not guns) / shield multiplier; median Badass/regular health x3.0 (11 pairs), non-weapon damage x2.0, champion damage factor 0.74/0.65 = x1.14
  (applies to guns too), champion health boost 1.0 in single player. Separate Super/Ultimate classes exist only for the Varkid and Loader; elsewhere "Super Badass X" is the Badass's TVHM name. Loot lists guarantee 1 uncommon / rare + uncommon /
  very rare + rare + uncommon; regular enemies drop gear 8.5 %. Enemy creature/robot sounds (643 events) are in the main pack; HUMAN battle dialog (`Ak_Play_VOBD_*`, 696 names, bank `Akb_VOBD_Bandits`) is NOT in the main pack pair.
  0.45.4 (TestBuild-151, python only, plugin 1.21.0): `sheets/badass_tiers.json` carries BL2's health 3.0/5.8/15, melee damage 2.28/2.6/2.6 (Ultimate held at Super's: asked), gun damage 1.14, shield 1.55/2.0/2.0 (later), floors 2/3/4, `bl2_drops` 1/2/3
  (Skylands gives 1: the user's choice; asked); new `sheets/enemy_drops.json` (gun/shield/relic shares 44.44/20/8.89 from the enemy gear pool, creature scale 0.5, cap 60, BL2 odds for reference). `badassprobe --voice` / `Check-BL2-EnemyVoice.bat`
  (writes `work\bl2-enemy-voice-report.txt`): name scan + B8 (every .pck/.bnk with banks named by Wwise id, each pack searched for the battle-dialog events, speakers' lines by kind). NEXT: read that report, then stage 1 (plugin: tiers + stats).
- 0.45.5 (TestBuild-152, python only, plugin 1.21.0), the user's answers: Ultimate keeps the Super's damage; BL2's 1/2/3 guaranteed drops (`badass_tiers.drops` + `drop_floors` "2" / "3 2" / "4 3 2"); spawn rates: survey BL2 first, FALLBACK = roll the
  Badass chance p (3 % + 0.5 %/player level, max 25), then only after a hit reroll p for Super (from player level 12), then reroll p for Ultimate (from 25): p, p^2, p^3 (`roll` chance/reroll); people and creatures alike; bosses and dragons get NO guaranteed tier,
  they roll at `boss_odds` 2x and keep boss loot. Open: whether the Super/Ultimate level gates stay (default yes). Surveys: `bl2badass --spawns` / `Check-BL2-Spawns.bat` (B9, writes `work\bl2-spawn-report.txt`: population definitions under `GD_Population_*`
  read generically (arrays of structs with a *Factory* field and a *Probability*/*Weight* field; factory -> PawnBalance -> tier), Badass share per mix and the median; class/field names UNCONFIRMED); `--voice` adds B8b: `AkBank` objects stored INSIDE packages
  (those naming a voice bank `akb_*vo*`, their `_LOC_INT` twins, voice-looking `_LOC_INT` packages), battle-dialog events looked up there, audio inside the bank or a streamed id in any .pck. NEXT: read both reports; then stage 1.
- SPAWN + VOICE REPORTS READ (TestBuild-152; facts in `docs/badass-roadmap.md` 1.1c): BL2 has no global Badass rate (dedicated 100 % Badass `PopDef_*` placed by designers; over 169 mixes Badass 10.5 %, Super 1.25 %, Ultimate 0.6 %); the user CONFIRMED
  the rolled table with the level gates. Human voices = `Ak_Play_VOBD_<speaker>_...` events in the LANGUAGE packs (`WillowGame\CookedPCConsole\English(US)\Audio_Banks.pck` + `Audio_Streaming.pck` 480 MB, and one English(US) pair per DLC);
  DLC events resolve to sounds (audio in the streaming twin), base-game events lead to no sound when the pack is read alone. 0.45.6 (TestBuild-153, python only, plugin 1.21.0): `bl2badass --voice` = B10 (`VoiceSet`: language banks + language-free
  banks of the parent folder + streamed index of both streaming packs read by seek; per speaker events / with sounds / with audio / KB; hex structure of unresolved events; one line per kind of every bandit-like speaker decoded with `audio.decode`
  to `work\voice-samples\<speaker>_<kind>_<line>_<n>.wav`, max 80); the old pass is `--voice-packs`. NEXT: the user listens and maps voices to Skyrim enemies; then stage 1 (plugin: tiers + stats) and the voice stage.
- VOICE REPORT READ (TestBuild-153, 80 samples written): with the language pack + sound pack + streaming loaded together EVERY enemy speaker of the base game resolves to audio (nomad 46 lines 6.8 MB, psycho1/2 26, goliath 38,
  banditheavy 15, marauder voices 36 each ...); only the player characters (assassin, commando, siren, merc: switch containers, type 6) do not. The user's choices: voices for the Pandora-named bandits NOW, by name (other races later);
  mapping (sheet `enemies.voices`): Marauder / Badass Marauder = maraudkiller/maraudrip/marauddh/maraudscatshot, Nomad / Badass Nomad = nomad, Psycho = psycho1/psycho2, Bruiser = banditheavy (guess), Goliath = goliath; triggers: entering combat,
  hurt, dying, taunts during the fight (+ gloat); Skyrim's bandit lines SILENCED. 0.46.0 (TestBuild-154, plugin 1.22.0 = "SkylandsNative 384"): `bl2/voice.py` (`VoiceSet`, moved out of badassprobe), `voices.py` (`extract` -> work\audio\voice WAVs by
  speaker x group, `build`: SNDR `SkylandsVO_<speaker>_<group>` LAST in the second plugin (a test checks no older id moves), VTYP `SkylandsSilentVoice`, NPC overrides with VTCK replaced (records without VTCK = template voice, left), table
  `Data\SKSE\Plugins\SkylandsVoices.txt` (NOT the ini: merge_ini would keep stale ids)); `native/skse/src/voices.h` (table read at data load with `TESDataHandler::LookupFormID(local, "SkylandsGunModels.esp")`, speaker by `GetName()` exact or
  " <name>" suffix, Combat/Hit/Death sinks, 1 s taunt pump, `PlayAt` with `SetObjectToFollow`; ini Voices/VoiceGap/VoicePainGap/VoiceTauntMin/VoiceTauntMax/VoiceRange). UNCONFIRMED in game: all of it (that the silent voice type silences them, the
  hit event's `source` for staff bullets (fire/shock deaths), sound volume/category of the copied template, that names match after the game localises them).
- 0.46.0 in game (user): the voices work; one or two FEMALE bandits still spoke Skyrim lines; many drops on the ground cost performance; the beam LIGHTS never appeared ("light FAILED" in every
  verbose line). 0.47.0 (TestBuild-155, plugin 1.23.0 = "SkylandsNative 385"), the user's choices: despawn by DISTANCE only, commoner sooner: `native/skse/src/despawn.h` (every 3 s on the game thread
  `TES::ForEachReference` over run-time (FF) references whose base has a `SkylandsRarity_` keyword; gone (Disable + SetDelete, and its beam via `g_onRemoved` = main.cpp `DropBeamOf`) when the player is
  farther than `DespawnCommon` 3000 / `Uncommon` 4500 / `Rare` 7000 / `Epic` 10000 / `Legendary` 16000 / `Etech` 16000 units, or in another space; an unloaded item the player went far from is marked and goes
  when next loaded (a mark only counts at the same place and rarity: run-time ids are reused); the player's own drops (container event 0x14 -> 0) never go; co-save record 'DSPN' through the new
  `shield::g_extraSave/Load/Revert` hooks). Beam cap `BeamCap` 24 in `TrackBeam` (rarity read BEFORE `g_beamLock`; past the cap the lowest rarity, oldest first, has its beam ref disabled; a new gun
  rarer than none keeps none). The quest's `Place` no longer places a light (pex-only, properties unchanged; Report says "Skylands beam ok: name"); Champollion could not be built in that session
  (sandbox refused the clone): the decompile test was skipped. Voices: the installer now silences records with NO VTCK (they spoke with the RACE's default voice: likeliest cause of the female
  lines) by adding one, and for records whose ACBS template flags have "traits" (bit 0 at offset 18) also the TPLT template (NPC, or a leveled list's NPCs, 4 steps; a renamed record is taken as
  Skylands.esp has it); `LVLN` is now loaded by `Masters`; setup log "voices: <edid> <id>: its own voice / no voice of its own ..., traits from template ..", "sheet row .. renamed no record"; table line
  `silent <id>`; the plugin logs the first 40 Pandora/"...andit" actors it looks at: "voice look: .. female/male base .. voice type .. (Skylands silent / a Skyrim voice)". UNCONFIRMED in game: all of it
  (that `ForEachReference` covers the loaded cells, that Disable+SetDelete on run-time refs is safe, the co-save, the voices fix). The boss row ("Badass Nomad") was missing from the 0.46.0 table: read the
  "sheet row boss" line in the next setup log.
- 0.47.0 in game (user, setup log 5cc24693 "0.47.0", SkylandsNative.log 6e05aef9 "SkylandsNative 385"): one bandit said BOTH Skyrim's and Borderlands lines; the BL2 lines are noticeably quieter. READ: the installer renamed and
  silenced only the 16 `EncBandit0xTemplate*` records (all "own voice 00013AE6"); the bandits that SPAWN are other Skyrim records that take their NAME from those templates (ACBS template flag 0x80, base data) and keep their OWN
  voice (no traits flag): "voice look: FF0008F4 \"Killer Marauder\" female ... voice type 00013ADD (a Skyrim voice)", males 0009843B / 00013AEC / 00013AE6. Also "sheet row boss renamed no record" (`^EncBandit0\dBoss` matches nothing).
  The SNDR template is `NPCCowDeath`. 0.48.0 (TestBuild-156, plugin 1.24.0 = "SkylandsNative 386"): (1) `voices.build` silences every master NPC with flag 0x80 whose TPLT chain (NPC or LVLN, 6 steps) reaches a renamed record ("..
  takes a Pandora name from template .. : silenced", count `named`); for the boss row it logs the game's bandit-boss record names. (2) plugin `Diagnose` (called on the first look at an actor, now also from the 1 s `Taunts`
  pass over every loaded actor, before combat) sets `base->voiceType` to the silent VTYP for a Pandora bandit that still has another ("still had a Skyrim voice type: given the silent one"). (3) `voices.GAIN` 1.35: the WAV
  samples copied to `Data\Sound\FX\Skylands\VO` are scaled (`louder`, 16-bit PCM, clipped). UNCONFIRMED in game: all of it (that a run-time voiceType change on a leveled actor's base sticks, how loud 1.35 sounds).
- 0.48.0 in game (user, SkylandsNative.log 80d6c7d3 "SkylandsNative 386", Papyrus.0.log 699a8092): only Borderlands voices heard (every "voice look:" line says "Skylands silent", the installer fix worked; no
  "still had a Skyrim voice type" line). The game CRASHED on a player shot while aiming during a fight (log ends at "button down ... 'Right Attack/Block'", aim started 2 s before, a bandit had died 3 s before with a
  following death line); NO "CRASH:" line (the unhandled filter set at plugin load was not called: something else handled it first). Same picture as the 0.23.3 crash. Papyrus: 97 x "Unable to call IsInterior" on
  `<nullptr form>` cells in `SkylandsHunterQuest.InRange` (Respawn from the Hunter power: stored roster cells not loaded). 0.48.1 (TestBuild-157, plugin 1.24.1 = "SkylandsNative 387"): (1) `FirstChance` = a VECTORED
  exception handler (added first at plugin load) logs the first 4 fatal-looking exceptions ("first chance exception <code> at <module+offset> (reading address ..); the plugin's last stage ..; on the stack: <module+offset
  of up to 14 code addresses found on the stack>") and passes them on; `ClaimCrashFilter` sets the unhandled filter again after data load and every game load (logs the filter it found). (2) voices: `PlayAt(.., a_follow)`:
  death lines and lines of dead actors no longer `SetObjectToFollow` the body's 3D (a suspected use-after-free when the ragdoll swaps the 3D; UNPROVEN); breadcrumbs "voices: hit event / death event / play / played".
  (3) `InRange` no longer calls `IsInterior` on the stored cell (outside, distance only). READ FIRST next time: "first chance exception" lines. If the user has a crash logger (Crash Logger SSE AE / Trainwreck), its
  `crash-*.log` names the call stack.
- 0.48.1 in game (user, SkylandsNative.log 4afc1b57 "SkylandsNative 387"): crash on firing at an enemy, CAUGHT: "first chance exception C0000005 at SkyrimSE.exe+11A615A (reading address 37); the plugin's last stage: tick: hud (shields:
  shield display: enemy); on the stack: SkyrimSE.exe+1193B21, +D1462E, +CFD4E4, +D9D736 ..." (all game code, the Scaleform/HUD region) and then "CRASH: ..." (our unhandled filter now runs; the filter found at data load was
  SkyrimSE.exe+65F900). Reading: the crash is inside the HUD movie while the plugin's HUD code (ammo display `HudFrame`, called from the game-thread `Tick` task; the shield bars `shieldhud::Frame`, called from `shield::Update`) wrote into it from
  ordinary `AddTask` tasks. 0.48.2 (TestBuild-158, plugin 1.24.2 = "SkylandsNative 388"): both displays run as `AddUITask` tasks (`QueueHud`, `QueueShieldHud`, one waiting at a time) inside `Guarded` (SEH `__try/__except`): a fault
  turns that display off for the session ("hud: a fault inside the game's HUD movie ..." / "shield hud: a fault ...") instead of crashing. UNCONFIRMED in game: that the UI task removes the crash (if a "fault" line shows up, the display code itself
  touches something bad, e.g. the enemy bar's clips after a death); that a recovered fault leaves the game usable.
- 0.48.2 in game (user): "the crash is no longer occurring". BADASS STAGE 1 = 0.49.0 (TestBuild-159, plugin 1.25.0 = "SkylandsNative 389"): `native/skse/src/badass.h`: a 500 ms game-thread pass over `highActorHandles` within 6000 units rolls
  every eligible actor ONCE (hostile to the player; not child/teammate/commanded/summoned/essential/protected; people and creatures) from `shielditems::Mix(formId ^ salt)`: p = `BadassPercent` 3 + `BadassPerLevel` 0.5 x (player level - 1),
  max `BadassMax` 25 (x `BadassBossOdds` 2 for `IsBoss` or dragons); reroll p for Super from `BadassSuperGate` 12, again for Ultimate from `BadassUltimateGate` 25; `BadassTest`=N percent replaces p and ignores the gates (testing);
  caps `BadassMaxNear` 4 / `MaxSuper` 1 / `MaxUltimate` 1 (a capped actor is rolled later). Stats as tracked TEMPORARY modifiers: Health +(mult-1) x own max (without its shield), `AttackDamageMult` +(mult-1), `SpeedMult` +100 x (mult-1);
  plugin-launched enemy bullets `LaunchData.power` = `BadassGun` 1.14 (the game's own first bullet of a burst stays unscaled). Bonuses come off at death; co-save record 'BDAS' v1 (id, base, tier, applied, amounts, max before); after a
  load each tiered actor is checked (`StillOn`: max >= max before + half the bonus) and the bonuses put back if gone. The shield is sized without the Badass bonus (`shield::g_extraMaxOf`). The co-save hooks of shield.h are now LISTS
  (`g_extraSave/Load/Revert`, despawn and badass both push). Ini block `skse.badass_ini()` from `sheets/badass_tiers.json`. Log: "badass: <id> \"name\" (level, person/creature, boss/dragon) is a <tier> [rolled]: health max a -> b (current ..),
  melee damage xM (AttackDamageMult a -> b), speed .., guns ..", "came off", "kept its bonuses across the load", a 30 s summary line. Names, size, drops: later stages. UNCONFIRMED in game: all of it (that a temporary Health modifier raises
  an NPC's current health too, that AttackDamageMult scales NPC melee and creature attacks, that SpeedMult changes apply without a carry-weight nudge, that power scales enemy bullets).
- 0.49.0 in game (user, SkylandsNative.log 23ae3051 "SkylandsNative 389", `BadassTest=50`): the rolls WORK (10 rolled: 5 Badass, 2 Super, 3 none; every bonus read back right: "health max 50 -> 290 (current 50 -> 290), AttackDamageMult
  1.00 -> 2.60, SpeedMult 100 -> 105"; bonuses came off at death; a hurt actor kept its damage: "current 36 -> 136"); the user saw none because stage 1 has no name/size. A crash: "first chance exception C0000005 at SkyrimSE.exe+86AD98
  (reading address 88); last stage: tick: done (shields: shield display)" = no plugin code running; stack all game code (+172DA3, +82D84E, +8768AC, +BCB617, ...); 2 s after a Badass died and its bonus was taken off the corpse,
  while aiming. Cause UNKNOWN; the user installed a crash logger (Crash Logger SSE AE VR): READ its `crash-*.log` next. 0.50.0 (TestBuild-160, plugin 1.26.0 = "SkylandsNative 390"), the user moved names up: `badass.h` `Present` = tier name
  before the display name (`SetDisplayName`, not when the name already holds "Badass") and `SetScale` 1.15 / 1.30 / 1.45 (`BadassNames`, `BadassSize`, `BadassSize1..3`), done at the roll and every pass for tiered living actors near; and
  stage 2's guaranteed drops: 1.6 s after a tiered actor is found dead (after the shield/relic sinks) `PlaceObjectAtMe` of 1 / 2 / 3 items with floors uncommon / rare+uncommon / epic+rare+uncommon (`kFloors`), the type by BL2's gear
  weights (`BadassDropGun/Shield/Relic` 44.44/20/8.89), rarity by the guns' weights shifted up by the tier (rarity r takes `kWeight[r - tier]`), level gates at max(player level, 8/15/30) (relaxed if they leave nothing); guns from every WEAP with
  `SkylandsGun` + rarity keyword (`ReadGuns`), shields/relics from their catalogs. Log "badass: <id> is now called ..", "size a -> b", "drop lists - guns by rarity ..", "badass: <id> (tier) dropped N: \"name\" (rarity type), ...".
  The carried gear keeps its own drop rules (not counted in the 1/2/3). UNCONFIRMED in game: all of it.
- 0.50.0 in game (user, SkylandsNative.log d9a7ec42 "SkylandsNative 390"): no crash; Badasses were bigger, correctly named and dropped several items (log: "drop lists - guns by rarity 99 99 132 132 66 75, shields 90 90 90 93 9 0, relics 10x5";
  "(Ultimate Badass) dropped 3: ... (epic shield), ... (epic relic), ... (epic shield)"). WRONG: the enemy health bar ignored the bonus (it stayed full until the health fell below the old maximum): the game's enemy bar measures against the
  PERMANENT maximum (base + permanent modifiers), and the bonus was a TEMPORARY modifier. Also: every guaranteed item was shifted by the tier, so an Ultimate's "rare" and "uncommon" items could only be epic+. 0.50.1 (TestBuild-161, plugin
  1.26.1 = "SkylandsNative 391"): the Health bonus is a `kPermanent` modifier (melee and speed stay temporary); co-save 'BDAS' v2 adds `tempHealth` (v1 entries = temporary: when the old bonus is still on after a load it is stripped as temporary
  and given again as permanent, log "health bonus made permanent"); the roll line also logs "the bar's maximum a -> b" (`GetPermanentActorValue`); each guaranteed item is shifted to ITS OWN floor (`PickDrop(seed, floor - 1, floor, ..)`:
  Ultimate = epic + rare + uncommon as BL2). CI fix: the "Commit the DLL" step lost DLL commits silently when two runs overlapped (binary rebase conflict, job still green); now an older run skips when newer plugin source is on the
  branch, the rebase uses `-X theirs`, and a failed rebase/push fails the job. UNCONFIRMED in game: that a permanent modifier moves the enemy bar.
- 0.50.1 in game (user): "health bars work now, badass drops look good". 0.51.0 (TestBuild-162, plugin 1.27.0 = "SkylandsNative 392"), BADASS STAGE 3 (creature drops): the installer writes `Data\SKSE\Plugins\SkylandsEnemies.txt`
  (`generate.write_enemy_classes`, every row of `sheets/enemy_stats.json`, tab separated, `(?i)` stripped; the plugin compiles each pattern with `std::regex::icase` and matches the race editor id, first match wins, cached per race:
  `badass::ClassOf`). `CreatureDeathSink` (TESDeathEvent): a non-person (class kind creature/dragon, or no class and not `IsPerson`), not critter/child/teammate/commanded/summoned, hostile to the player at death, not a Badass (a Badass keeps its
  tier drop): dragon (`DragonBoss`) = 2 items floor rare (shift 2) gates max(level,15); other `IsBoss` creature = 1 item floor rare; else chance = class `drop_scale` (or `CreatureDropScale` 0.5) x `PersonChance(level)` (`CreatureGunPercent` 25 +
  shield carry x ShieldDropPercent + relic carry x RelicDropPercent) capped at `CreatureDropCap` 60, one item, floor = class `min_rarity`, no shift, gates at the creature's level. A Badass dragon's tier drops are floored at rare. The class
  `badass` column now also keeps mammoths and critters from being rolled. Pending drops are a generic queue (`Pending{n, floor[3], shift[3], level, what}`, `g_pendLock`). Log: "N enemy classes from SkylandsEnemies.txt", "race X is class Y",
  "<id> (creature, class .., level ..) died: drop chance ..% (a person's ..% x ..), rolled ..: drops an item / nothing", "(dragon) dropped 2: ...". UNCONFIRMED in game: all of it (that dying creatures still read as hostile, regex on race ids).
- 0.51.0 in game (user, SkylandsNative.log bfeb0801 "SkylandsNative 392"): no crash/fault lines; classes loaded and races mapped; creature drops and tier drops all within their floors; "plenty of badass creatures, they all
  dropped what they should". Relics came up in 4 of 11 tier items (expected 12.1 % per item: unlucky, binomial ~4 %; the per-item odds were laid out for the user). FOUND in the log: (1) the size never reached the tier for small races:
  `GetScale` = reference scale x race/base height (mudcrab 0.75), so "GetScale < 1.15" stayed true, SetScale(1.15) read back 0.86 and was set again every 500 ms (log spam "size 0.86 -> 0.86"); (2) one mudcrab's death event arrived twice
  (two drop rolls). 0.52.0 (TestBuild-163, plugin 1.28.0 = "SkylandsNative 393"): `Present` grows the reference's own `refScale` from what it was when rolled (`Entry.scaleBefore`, co-save 'BDAS' v3; v1/v2 entries = 100); creatures (`IsCreature`: class kind
  not person, else not `IsPerson`) get `BadassCreatureSize` 0.15 more per tier (Badass 1.30, Super 1.60, Ultimate 1.90 x own size); the user's "low-level creatures should still pose a threat": a creature's own health counts as at least
  `BadassCreatureHealth` 20 + `BadassCreatureHealthPerLevel` 5 x player level before the tier multiplies it, and its melee is x(1 + `BadassCreatureGap` 0.05 per level below the player, max `BadassCreatureGapMax` 3) on top of the tier; `CreatureDeathSink`
  rolls once per body (60 s). UNCONFIRMED in game: all of it (that refScale is kept by the save, how big an Ultimate dragon at 1.9 looks).
- 0.52.0 in game (user, SkylandsNative.log da8de0c5 "SkylandsNative 393"): "everything looked great"; no exception lines; the creature floor and sizes work ("counted as 40: the creature floor at player level 4", mudcrab 0.75 -> 1.20 as a Super).
  Seen: a Giant 0004BB23 (level 32) was rolled fresh with a maximum health of 132975 BEFORE any bonus (x15 -> 1994625): not explained (another mod/console, or an earlier untracked permanent bonus); ask if it repeats.
  0.53.0 (TestBuild-164, plugin 1.29.0 = "SkylandsNative 394"), user requests: (1) a person with NO Skylands gun (held or in the pack, `shielditems::HasGun`) has at least `EnemyShieldUnarmedPercent` 60 (+ per level) shield chance, so melee
  fighters are tankier; the roll now waits 3 s after the pump first sees a person (`g_firstSeen`) so the Hunter script has armed them; log "shield items: .. carries a gun / has no gun: shield chance N percent" (first 40).
  (2) `toss.h`: dropped items (Badass `PlaceObjectAtMe`, shield/relic `RemoveItem(kDropping)` handles, the Hunter's `Placed` via the new native `TossDrop(ObjectReference) Bool`) get their first rigid body's linear velocity set
  (`DropTossUp` 260 up, `DropTossOut` 90 sideways, game units/s x `bhkWorld::GetWorldScale()`, under `worldLock`) once their 3D is up (100 ms task while anything waits, 25 tries); log "toss: .. kicked .." (first 12) / "had no 3D/rigid body".
  UNCONFIRMED in game: all of it (that SetLinearVelocity wakes a resting body, that the lock is safe, that the Papyrus drop gets its 3D in time).
- 0.53.0 in game (user, SkylandsNative.log e7560015 "SkylandsNative 394"): no exception lines; the toss works ("toss: .. kicked 231 up, 82 out (after 0 tries)", 12 lines, guns, shields, relics, a Badass mudcrab's drop) but "a lot still stuck in the body".
  0.53.1 (TestBuild-165, plugin 1.29.1 = "SkylandsNative 395"): `DropTossUp` 420 / `DropTossOut` 150 (`DropTossRev=2` makes `merge_ini` put an old file's 260/90 back to the new defaults once); 450 ms after a kick an item that moved under 30 units is kicked
  again x1.4 (log "moved only N units after its kick: kicked again, harder"). Creature drops go through the same `badass::Drop` path (tossed). UNCONFIRMED in game. NEXT FEATURE: character progression, see `docs/handoff-character-progression.md`
  (gun XP into Skyrim skills/levels, weapon proficiencies, later Badass Rank challenges and tokens; planning + interview first).
- PROGRESSION, PHASE 1 (0.53.2, TestBuild-166, python only, plugin unchanged 1.29.1 = "SkylandsNative 395"): interview done, `docs/progression-roadmap.md` WRITTEN, AWAITING APPROVAL (no feature code). The user's answers: NO skill
  training; kills with a Skylands gun give CHARACTER XP straight to the level meter (BL2's shape, surveyed, rescaled to Skyrim's threshold; pace ~ vanilla Archery); DAMAGE dealt feeds weapon proficiencies per TYPE (6) and per
  MANUFACTURER (8); every gun gets a quarter of every maker track's bonuses and its own maker's in full; stats: damage, accuracy, reload, fire rate, magazine, bonus projectile chance (>100 % = guaranteed extras); no cap, slowing
  down, milestone levels (10, 25, 50, ...) give 3-4 bigger bonuses, the step shrinks after each milestone to a floor (fire rate 0.5 %); level-up notices + a HUD line under the ammo; per character (co-save). LATER: "Legendary" reset
  (cap 100, +10 each time, flat bonus to every stat), Badass Rank (BL2's challenges adapted, tokens "pick one of five", SHARED across characters with an ini switch). Survey `progressprobe.py` (`python -m skylands_setup bl2progress`,
  `Check-BL2-Progress.bat`, writes `work\bl2-progress-report.txt`): P0 name tables, P1 experience groups + GD_Globals, P2 challenge groups, P3 badass rank objects, P4 Default__ objects; all by name, packages opened once
  (`badassprobe.objects_in_groups`). Round 2 (pace 30, own maker full only, launchers half, 1 stat a level, proficiency XP = bullet damage x 0.1, level cost 20 + 10n, no caps, damage after death counts) is in the roadmap; NEXT: approval of the revised roadmap (section 6: 3 questions) and the report; then stage 1 (kill XP).
- PROGRESS REPORT READ (user's `bl2-progress-report.txt` of TestBuild-166, 4,248 lines, all sections ran; facts in `docs/progression-roadmap.md` 1.3): kill XP = 10 x enemy level + 4 (min 10;
  `Init_BaseEnemyExperience`, x11 in TVHM), level curve 60 x level^2.8 + 7.33 (`Init_ExperienceRequiredForLevel`), tier XP multipliers exist as `GD_AI_Balance.XP.XPMultiplier_01_Chump..09_Boss` (numbers NOT read: nested
  formula), `GD_Globals.General.Globals.ExpScaleByLevelDifference[6]` not read; 365 `ChallengeDefinition`s (base list `GD_Challenges.ChallengeList.List`, 227) with `Levels[5]` not opened; 14 `BadassRewardDefinition`s
  (`GD_Challenges.BadassRewards.BARD_*`, values from `GD_Challenges.BadassSkill.Init_BadassBonusCalc_<stat>`, not read). User round 3: `ProfBase` 50, `ProfStep` 15, dead bodies give NO proficiency XP (only the killing
  shot within `ProfKillGrace` 0.25 s), kill XP stays, Badasses same XP per damage. 0.53.3 (TestBuild-167, python only, plugin 1.29.1): `progressprobe --deep` / `Check-BL2-Progress-Deep.bat` (writes
  `work\bl2-progress-deep-report.txt`): D1 whole groups `gd_ai_balance.xp`, `gd_balance_experience.*`, `gd_challenges.badassskill/badassrewards` and the combat/loot `gd_challenges.*` groups in full, D2 `GD_Globals.General.Globals`
  + class defaults in full, D3 a 2-level follow. NEXT: the deep report and the user's approval; then stage 1 (kill XP).
- PROGRESS DEEP REPORT READ (TestBuild-167, 19,588 lines; facts in `docs/progression-roadmap.md` 1.3b): XP multipliers Chump 0.5 / Normal 0.75 / NormalHigh 1.0 / Tough 1.25 / ToughHigh 1.5 / Badass 3 / Super 10 / Ultimate 20 / Boss 40;
  level gap above x1.00..1.15, below x0.90/0.70/0.40/0.15/0.05/0.01 (1..6+); challenge level points 5 x (1,5,10,50,100); token N needs rank N^1.8; token stat = 1 % x tokens^0.75. Challenge GOALS are in `:ChallengeConditionDefinition_<n>`
  sub-objects (not printed: the deep pass skips ':' paths; a third pass at the Badass Rank stage). New game: none required (co-save record, records appended last); suggested for judging the kill-XP pace (roadmap 3.9).
- PROGRESSION STAGE 1 = 0.54.0 (TestBuild-168, plugin 1.30.0 = "SkylandsNative 396"; the user APPROVED the roadmap): `native/skse/src/progress.h` KILL XP. `HitSink` (TESHitEvent, cause = player, source = a Skylands gun via
  `progress::g_isGun` = GunOf) notes per actor the last gun hit (time, hostile then, `badass::TierOf` read BEFORE our lock, boss = `shielditems::IsBoss` or `badass::IsDragon`, level); `DeathSink`: killer = player (or none, `KillXPNoKiller`),
  last gun hit within `KillXPWindow` 3 s, hostile (unless `KillXPNonHostile`), not teammate/summoned/commanded/child, once per body (60 s): xp = levelThreshold / `KillXPKillsPerLevel` 30 x (10 Le + 4)/(10 Lp + 4) x BL2 level gap
  (above 1.00..1.15, below 0.90/0.70/0.40/0.15/0.05/0.01) x max(tier 3/10/20, boss 40) x `KillXPScale`, capped at `KillXPMaxShare` 0.5 of a level; a 250 ms `shield::Queue` task adds it to
  `GetInfoRuntimeData().skills->data->xp` (CommonLib v12.1.0 `PlayerCharacter::PlayerSkills::Data{xp, levelThreshold, ...}`); the first time xp passes the threshold a HUD notice "Level up! Open the Skills menu to level up."
  Ini block `skse.progression_ini()` from the new `sheets/progression.json` (`sheet_data.PROGRESSION`, sources bl2/design). Log: "kill xp: on ...", the first 20 "the player hit ... source .. projectile ..: a Skylands gun / not",
  the first 30 "kill xp: <id> (level .., tier, boss) killed with gun ..: N XP ..." / "no XP (why)", the first 10 "character XP a -> b (read back c), level, threshold; the game says it can level up: yes/no" (`PlayerSkills::CanLevelUp`),
  a 30 s summary. NO esp/pex change (no ids move, no ghost scripts). New game SUGGESTED for judging the pace (roadmap 3.9), not required. UNCONFIRMED in game: all of it (hit source for the player's bullets, killer for explosion kills,
  that a direct xp write offers the level-up in the Skills menu, the HUD notice).
- 0.54.0 in game (user, SkylandsNative.log "SkylandsNative 396"): NO XP was given: every player hit was "source 070011B9 projectile 07001101: not a Skylands gun" while the held gun was FE003DA5: a hit by a PLUGIN-LAUNCHED bullet
  names the gun's ENCHANTMENT (the bullet spell, a record of SkylandsGunModels.esp = load slot 07) as its source, NOT the weapon (so `voices::g_elementOf` never found the element for the player's bullets either). Every death was
  "the player killed it" (the killer IS named). 0.54.1 (TestBuild-169, plugin 1.30.1 = "SkylandsNative 397"): `main.cpp` `GunFromSource(source)` = the weapon if the source is one, else a map built once from every WEAP with
  `SkylandsGun` keyword: its `formEnchanting` id and each effect's `baseEffect` id -> the gun (log "hit sources: N Skylands guns mapped ..."); used by `progress::g_isGun` (now returns the gun's id, logged "Skylands gun <id>") and voices.
- 0.54.1 in game (user, SkylandsNative.log "SkylandsNative 397"): KILL XP WORKS ("hit sources: 603 Skylands guns mapped from their enchantments (603 effects)"; a level-1 kill at player level 5 = 0.3 XP (x0.259 levels, x0.15 gap), a level-5
  Super Badass = 66.7 XP; "character XP 12.3 -> 78.9 (read back 78.9)"; "the game says it can level up: no" because 78.9 < threshold 200). User: "Looks like it worked", then (going to sleep) asked for proficiencies + the HUD line.
- PROFICIENCIES = 0.55.0 (TestBuild-170, plugin 1.31.0 = "SkylandsNative 398"; roadmap stages 2+3 in one build, the user's request): (1) installer: `Armory.add` records (gun record, `maker_index(mfr)`) and `add_maker_keywords()`, called
  AFTER the voices (the last records), creates `SkylandsMaker_<n>_<Name>` KYWD (n = `sheets/manufacturers.json` order: 0 Bandit, 1 Dahl, 2 Hyperion, 3 Jakobs, 4 Maliwan, 5 Tediore, 6 Torgue, 7 Vladof) and appends it to each staff gun's KWDA/KSIZ
  (no older form id moves; test `test_every_staff_gun_carries_its_manufacturer_keyword_added_last`; the voices test leaves `SkylandsMaker_` out of its no-move check). Report key `maker_keywords`. (2) plugin: `GunInfo.type` (index of `_m` ammo in
  `g_ammoLocals` = STAFF_KINDS order) and `.maker` (keyword); `native/skse/src/proficiency.h` (namespace `prof`): 6 type + 8 maker tracks {level, xp, total, legendary(reserved)}, co-save 'PROF' v1; `progress::HitSink` books
  `prof::Book(target, type, maker, magnitude x power, alive)` for hostile, non-essential/protected/teammate/summoned/commanded/child targets (a dead target only within `ProfKillGrace` 0.25 s of `prof::NoteDeath`); XP = damage x `ProfXPScale` 0.1 to both tracks;
  cost `ProfBase` 50 + `ProfStep` 15 x n; `prof::Apply` in the 250 ms progress pump levels up, logs "prof: <track> proficiency N (milestone): +x% ..." and shows it as a HUD notice; `Gains`: 1 stat a level in turn (damage, accuracy, reload, fire rate,
  magazine, bonus projectiles), milestones 10/25/50/75/100/every 50 = 4 stats x3, step x0.75 per milestone passed, floors 0.5/0.5/0.5/0.5/1/1; maker tracks: 2 signature stats each (`kMakerStats`: Bandit mag+rate, Dahl acc+reload, Hyperion acc+damage,
  Jakobs damage+rate (rate a choice), Maliwan damage+acc, Tediore reload+mag, Torgue damage+projectiles, Vladof rate+mag), one per level alternating, both at a milestone; `BonusFor(type, maker)` = type + own maker x1.0 + others x0.25 (launchers' projectiles x0.5).
  `TickGun` multiplies fire rate / reload / accuracy / damage (`g_damageMult` = launch power) / magazine by (1 + bonus%) ON TOP of the relic values; `Launch` adds `prof::Extra` projectiles (per pellet for shotguns; same round). HUD: `tfProfT` "SMG 4" (blue)
  and `tfProfM` "Jakobs 2" (gold) at y 46 of the ammo clip with 88-unit bars `profTFill`/`profMFill` at y 66. Ini `Prof*` keys (`sheets/progression.json`, `progression_ini`). Log: "prof: on; ...", the first 30 "prof: hit <id> by gun .. (type, maker): magnitude x power = damage -> XP",
  "prof: gun <id> (type / maker): damage +..% ..." when the held gun's bonuses change, "prof: N bonus projectile(s)", "prof: save/load - SMG n, ...". NEEDS A FRESH INSTALL (new keywords; no older id moves, so the save stays). UNCONFIRMED in game: all of it
  (that the maker keyword is read, the HUD layout, that launch power scales damage (unconfirmed since 0.42.0), the extra projectiles).
- 0.55.0 in game (user, SkylandsNative.log edfb681f "SkylandsNative 398"): the HUD line works (user: "great"); log: "prof: on", maker keywords read (gun check "type 0, maker 1" ...), 30 "prof: hit" lines
  (magnitude 8.00 x power 1.00 -> 0.80 XP), level-ups (SMG 1 +2% damage, Bandit 1 +3% magazine, Bandit 2 +2% fire rate, Shotgun 2, Hyperion 2), other makers' quarters on a gun, 'PROF' save/load across loads, no exception lines.
  Not seen yet: bonus projectile lines (no track reached a projectile level). 0.56.0 (TestBuild-171, plugin 1.32.0 = "SkylandsNative 399"), the user's maker rule: a maker's second stat grows at HALF the first's step
  (`ProfSecondaryShare` 0.5, `g_secondary`), and other makers' guns get only the maker's PRIMARY stat (`kMakerStats[m][0]`) at `ProfOtherMakers` 0.25; the own maker's guns get both. Legendary: PROPOSAL in
  `docs/progression-roadmap.md` 3.6 (box trigger, cap 100 + 10, flat +3 %, `ProfTestLevels`), awaiting the user's answers; nothing built.
- 0.57.0 (TestBuild-172, plugin 1.33.0 = "SkylandsNative 400"), the user's numbers (confirmed before building): (1) maker tracks: steps = type starts x `ProfMakerStartScale` 0.2083, GROWING x `ProfMakerGrowth` 1.105
  a milestone, no floor (`MakerStepOf`): Bandit magazine +5 % at 10, +50 % at 100. (2) LEGENDARY, gun type tracks only (makers never cap/reset): cap `ProfLegendaryCap` 100 + 10 a Legendary, type-track `Gains` uses level
  ((n-1) % cap) + 1 (falloff restarts), a Legendary resets to 0 and keeps `ProfLegendaryKeep` 10 % of the track at its cap (`g_typeKept`, recomputed from the `legendary` count already in 'PROF' v1); trigger = hold the
  reload key `ProfLegendaryHold` 2 s with a gun of the capped type (`g_reloadHeldS` from `HeldDuration`, `prof::MakeLegendary` in TickGun); HUD "SMG 100 MAX" (gold) / "SMG 12 *2". (3) knobs `ProfTypeRate/MakerRate` (XP),
  `ProfTypeBonus/MakerBonus` (strength), `ProfTestLevels` (adds levels on the first load of a session; needs a save with a 'PROF' record). UNCONFIRMED in game: all of it (the hold on the reload key, the notices).
- 0.58.0 (TestBuild-173, plugin 1.34.0 = "SkylandsNative 401"): SKYRIM-STYLE PROFICIENCIES behind ini `ProfSkyrimStyle` (default 1; 0 = the 0.57.0 system), the user's poll: a gun type level n gives n x `ProfSkyrimCharXP` 0.5 character XP
  (`g_charPending`, `prof::TakeCharXP` added in `progress::Apply`), maker levels x `ProfSkyrimMakerXP` 0, kill XP x `ProfSkyrimKillXP` 0, `Cost` = 0.291 x n^1.95 + 20 (same total at 100 as the plain curve). Our HUD stays; Skyrim's own notices LATER.
  Log: "prof: Skyrim style ON: ...", "prof: SMG 12 gives 6.0 character XP", "kill xp: .. and N XP from proficiency levels: character XP a -> b". UNCONFIRMED in game.
- 0.59.0 (TestBuild-174, plugin 1.35.0 = "SkylandsNative 402"), the user's request (ammo economy for early-game playthroughs): (1) ammo gold values `generate.STAFF_AMMO_VALUE` pistol 5, SMG 8, AR 10, shotgun 10, sniper 15, rocket 50 (AMMO DATA value;
  merchants sell at Skyrim's barter markup on top). (2) MERCHANTS: the old `shields.loot` vendor-chest-by-name override NEVER matched a real install (no shields/guns ever seen at merchants), now off (`vendors_by_name=False`); `native/skse/src/merchants.h`
  (namespace `shop`): on Dialogue/Barter menu open, the speaker's `GetVendorFaction()->vendorData.merchantContainer` is TOPPED UP to `ShopAmmo<Type>` (Pistol 100, SMG 80, AR 60, Shotgun 40, Sniper 30, Launcher 6) and `ShopGear` 3
  Skylands items (`badass::PickDrop` tier 0 at the player's level, new picks every `ShopGearDays` 2); every vendor. (3) ammo amounts by gold value: body's own gun `AmmoDrop<Type>=min-max` (Pistol 12-28, SMG 10-24, AR 8-18, Shotgun 5-12, Sniper 3-8, Launcher 1-2),
  extra random kind `AmmoBonus<Type>` (about half), first stock `StartAmmo<Type>` (120/100/80/40/30/6; `StartAmmo`=0 switches it off; it was 300 of any kind). Log "shop: on ...", "shop: <id> \"name\" (merchant chest ..): added ..". UNCONFIRMED in game: all of it
  (that MenuTopicManager's speaker is set when the Dialogue Menu opens, that items added to a merchant chest show in the barter menu, gear prices).
- 0.59.0 in game (user, SkylandsNative.log 3d1bae24 "SkylandsNative 402"): 3 shops visited, only one weapon seen, no ammo. Log: every merchant was found and stocked TWICE (dialogue, then barter 2 s later) and BOTH times
  "0 Skylands items in it before": what was added at the dialogue was gone when the barter menu opened. Reading (UNPROVEN): the game restocks (resets) a due vendor chest when bartering starts (first barter: lastDayReset 0), wiping
  the dialogue stock, and the barter-time stock came after the menu built its list. 0.59.1 (TestBuild-175, plugin 1.35.1 = "SkylandsNative 403"): at the dialogue, a due restock (`lastDayReset == 0` or today >= last + `iDaysToRespawnVendor`)
  is done first (`chest->ResetInventory(false)`, `lastDayReset = today`, ini `ShopReset` 1), then the top-up; the log line now gives day / last restock / due / done and reads the pistol rounds back. If the read-back is 0 right after
  adding, `AddObjectToContainer` on an unloaded merchant chest does not stick (then try `GetInventoryChanges()` / a Papyrus AddItem path).
- 0.59.1 in game (user, SkylandsNative.log 659bb737 "SkylandsNative 403"): still nothing at merchants. LOG READ: a never-restocked vendor has `lastDayReset` 0xFFFFFFFF (not 0); the barter open then restocks and writes floor(days passed)
  (0 on day 0.79), wiping what the dialogue added; 0.59.1 treated only 0 as due and, when it did restock, wrote max(today,1) = 1, a day AHEAD of the game's 0, which the game's unsigned today - last again took as due. 0.59.2 (TestBuild-176,
  plugin 1.35.2 = "SkylandsNative 404"): due = last 0xFFFFFFFF or today < last or today - last >= `iDaysToRespawnVendor`; our restock writes `lastDayReset = today`. The barter-time top-up (after the menu built its list) never shows; it is the fallback.
  Note: the user reloads the same save (day 0.79) between tests; stock added in one session is gone after a reload.
- 0.59.2 in game (user, SkylandsNative.log 235fbdea "SkylandsNative 404"): the restock fix WORKS (dialogue "a restock was due - done now ... pistol rounds now 100", barter "no restock due; 3 Skylands items in it before"; the user opened the chest and saw the ammo),
  but the BARTER MENU still showed none of it. Cause (Skyrim rule): a merchant shows only chest items carrying a keyword of its vendor list (`vendorData.vendorSellBuyList`; `notBuySell` inverts it). 0.59.3 (TestBuild-177, plugin 1.35.3 =
  "SkylandsNative 405"): `shop::Fit` gives every stocked Skylands item (ammo, gear in the chest) the vendor list's FIRST keyword at run time (`BGSKeywordForm::AddKeyword`, not saved: redone at each stocking; ini `ShopKeywords` 1); log
  "shop: <id>'s vendor list .. (N keywords, deals only in these / all BUT these): Skylands items already matches / given the vendor's keyword / ..." and "gave <item> the vendor keyword ..". UNCONFIRMED in game.
- 0.59.3 in game (user, SkylandsNative.log 5f0ba64b "SkylandsNative 405"): ammo shows in shops. The keyword given is the vendor list's FIRST one (Ulfberth: VendorItemAnimalHide); `Fit` said "no vendor list" for the AMMO items (no keyword form?)
  but the user saw ammo; Belethor's list is notBuySell. Tidy later only if asked (the user said: no changes while planning).
- 0.60.0 (TestBuild-178, plugin 1.36.0 = "SkylandsNative 406"), the user's request: (1) the ini keeps each progression system's PACE apart and the makers apart from the gun types: BL2 style `ProfBL2XPScale/TypeRate/MakerRate/TypeBase/TypeStep/MakerBase/MakerStep`,
  Skyrim style `ProfSkyrimXPScale/TypeRate/MakerRate/TypeCurveMult/Exp/Base/MakerCurveMult/Exp/Base` (`Cost(level, maker)`, `XPScale()/TypeRate()/MakerRate()` by `g_skyrim`); the old shared `ProfXPScale/ProfBase/ProfStep/ProfTypeRate/ProfMakerRate/ProfSkyrimCurve*`
  are GONE (not read). Bonus/Legendary settings stay shared (the user). (2) the makers' SECOND stat is a SHIELD stat that ALWAYS applies (`kStats` 9 = 6 gun + `kShieldCap/Rate/Delay`, type tracks rotate over `kGunStats` 6): Bandit/Jakobs/Torgue capacity,
  Vladof/Hyperion/Maliwan recharge rate, Tediore/Dahl shorter delay (starts `ProfShieldCapacityStart/RechargeStart/DelayStart` 3, x MakerStartScale, x SecondaryShare); `RecomputeAllLocked` hands the totals to `shield::g_profShieldCap/Rate/Delay` (atomics, no lock crosses),
  which multiply the player's shield capacity / recharge rate / delay on top of the relics. Torgue/Maliwan/Jakobs/Dahl/Hyperion move to GRENADE stats when grenades exist (the user). UNCONFIRMED in game.
- 0.60.1 (TestBuild-179, plugin 1.36.1 = "SkylandsNative 407"): merchant keywords. The six AMMO records carry the vanilla `VendorItemArrow` (KSIZ/KWDA, no id moves); `shop::Fit` finds the item's keyword part
  through `KeywordsOf` (ammo: `TESAmmo::AsKeywordForm()`, its keyword part is at a runtime-dependent offset in the multi-target CommonLib, so neither `As<BGSKeywordForm>` nor an upcast reaches it: that was the 0.59.3 "no vendor list") and, for an include-only vendor list without a match, gives the keyword that FITS the kind when the list has it
  (ammo: Arrow, Weapon; guns: Weapon, Staff; relics: Jewelry, Clothing, Armor; shields: Armor, Clothing, Jewelry), else the list's first keyword (the user's choice: every shop shows every kind). Log "shop: gave the <kind> ..
  the vendor keyword .. (fits the item / nothing fitting in the list: its first keyword)". UNCONFIRMED in game.
- 0.60.2 (TestBuild-180, plugin 1.36.2 = "SkylandsNative 408"; the session's tweaks, built together with no report on 0.60.0/0.60.1 yet). (1) AMMO ACROSS LOADS, the user: "ammo fluctuates
  when saves are loaded, guns with no ammo have a full magazine when I load". Cause (code): the rounds left in each gun (`g_gun.mag`, `g_gun.mags`) lived ONLY in plugin memory, never in the co-save and never
  reset on a load: a load kept the magazines of the game that was running (shots fired after the save stayed spent; a reload after the save stayed full while the pack got its rounds back = free rounds), the
  first load after starting Skyrim had every gun full, a reload running at the load finished into the loaded game; the first stock (`StartAmmo<Type>`) was a static map, once per RUN of Skyrim, so a restart gave a
  player with none of a kind a new stock. Fix: co-save record 'SMAG' v1 (`MagSave/MagLoad/MagRevert` through `shield::g_extraSave/Load/Revert`): every gun's magazine (the gun in hand included) and the
  ammo kinds already given a first stock (`g_startGiven`, now per character); Revert clears the magazines, the gun in hand and a running reload. An older save has no record: the first load gives full guns once.
  Log: "ammo: save - N magazines (the gun in hand ..)", "ammo: the running game is replaced ...", "ammo: load - N magazines from the save ...", "player gun ..: magazine a of b (as the save had it / not in the
  save: full / the save has no magazine record ...)", "ammo: first gun in hand after the load: .. magazine n, its ammo in the pack m", "ammo: reload of .. done: magazine a + b, the pack x -> y" (first 40),
  `WatchPack`: "ammo: <id> in the pack a -> b outside a reload" (first 40, once a second). Note: magazines are kept per gun BASE record, so two copies of one gun share a magazine (as before).
  (2) ENEMY SHIELD BAR, the user: it did not always clear on a new target, and showed a FRIENDLY person's shield until another shielded hostile was looked at. `shieldhud::EnemyActor`: only `HostileTo`
  (`IsHostileToActor(player)` or `currentCombatTarget` = player, alive, not a teammate) counts; a hostile with no shield in the crosshair clears the bar; a friendly/neutral one in the crosshair is ignored; else
  the shielded hostile hit last (4 s); the choice is dropped when dead/gone/not hostile or after `kKeepS` 4 s without being in the crosshair or hit. Log "shield hud: enemy bar: now about <id> (why; was <id>)"
  (first 40). UNCONFIRMED in game: all of it (the co-save round trip, that `IsHostileToActor` is false for a friendly person who is merely in the crosshair).
- LEFT HAND, PHASE 1 (after 0.60.2, docs only): interview done, `docs/left-hand-roadmap.md` WRITTEN, AWAITING APPROVAL (no feature code). Answers: spells + shields in the
  left hand, a HOTKEY (default middle mouse) that only switches the mode (equipment untouched), no ADS while ON, gun and left hand usable at once, first-person left
  arm shown while ON, player only. The user keeps the shared magazine per gun base record. Open: roadmap section 6 (the user's left-hand/weapon-switching issues,
  keeping the state in the save, HUD tag).
- LEFT HAND STAGE 1 = 0.61.0 (TestBuild-181, plugin 1.37.0 = "SkylandsNative 409"; the user APPROVED the roadmap, answers to its section 6: the toggle starts OFF after a load, no HUD tag, an
  on-screen notice for testing; the user also reports the 0.60.2 ammo fix "seems to work", no log yet). (1) Toggle: `g_leftHand` (OFF at start, `MagRevert` sets it OFF on every load/new game), ini `LeftHand` 1,
  `LeftHandMouse` 2 (middle; code n or 256+n like `ReloadMouse`), `LeftHandKey` -1; `InputSink` -> `ToggleLeftHand` (only with a gun really in hand, no menu): notice "Skylands: left hand ON / OFF (aim down sights)",
  log "left hand: ON/OFF by the key (device, code, the game's event for it '..'); the left hand holds <spell/shield/weapon/torch/nothing> <id> "name"" (first 40; also when pressed with no gun: tells the middle
  button's own game event). ON: `g_aimHeld` stays false (aim ends), `AttackHook` passes "Left Attack/Block" to the game (log "left hand: the left button went to the game ..", first 20), `HideLeftArm` restores
  the arm. (2) The user's spell bugs: "after unequipping the gun spells sometimes refused to cast" = gun mode left on with no gun in hand, and the hook swallowed both buttons: now it swallows only while
  `g_gunInHand` (set by the tick from `HeldGun`, cleared by `SetGunMode(false)`; log "attack handler: gun mode is on but no Skylands gun is in the hand .."); "a healing spell kept casting after the gun was
  drawn" = the button's RELEASE was swallowed: `g_gameSawDown[2]` remembers a press the game saw and passes its release even while swallowing (log "attack handler: the .. button came up after a gun was taken in
  hand: its release goes to the game"). UNCONFIRMED in game: all of it (whether the middle button has a game action, the staff + spell/shield animations with our gun, the arm popping back, that a passed release ends the cast).
- 0.61.0 in game (user, SkylandsNative.log 5c6ec292 "SkylandsNative 409"): the middle click did NOTHING (no notice, no camera change) and the log has NO "left hand:" line at all, so `ToggleLeftHand`
  was never called; the 30-press "button down" log was used up by wheel zooms (codes 8/9 'Zoom In/Out'), so what the middle click sent is unknown (possible: the user's `ReloadMouse` takes code 2 first, or the
  mouse software remaps the wheel click). 0.61.1 (TestBuild-182, plugin 1.37.1 = "SkylandsNative 410"), the user chose middle + G: `LeftHandKey` default 34 (G), `LeftHandRev=2` makes `merge_ini` put
  `LeftHandMouse`/`LeftHandKey` back to the defaults once; "mouse button down: code N event name '..'; Skylands takes it for: the reload / the left-hand toggle / nothing" for every mouse press but the wheel (first 60),
  logged BEFORE the reload check. READ those lines next.
- 0.61.1 in game (user, SkylandsNative.log 31f82f1d "SkylandsNative 410"): G WORKS (ON/OFF lines, "left hand holds spell 00012FCD Flames", "the left button went to the game"); the middle click still does
  nothing and NO "mouse button down: code 2" line came in 14:19-14:22 (the 60 lines were spent on left/right clicks, codes 0/1, but code 2 never showed): the middle click does not reach the game's input
  events on the user's setup. The user equipped a SECOND Skylands gun in the left hand ("left hand holds weapon FE0038E0 lite Revolver") and it broke both guns. User rules: left hand = Skyrim's one-handed
  things only (spells, staffs, weapons, shields); two guns only later for the Gunzerker's action skill. 0.61.2 (TestBuild-183, plugin 1.37.2 = "SkylandsNative 411"): (1) `PollToggleMouse` (tick, gun in hand)
  reads `LeftHandMouse` 2/3/4 = VK_MBUTTON/XBUTTON1/XBUTTON2 with `GetAsyncKeyState` while Skyrim's window is in front (log "left hand: mouse button N seen down by Windows"); `ToggleLeftHand(device, code, name)`
  ignores a second call within 250 ms (`g_lastToggleMs`); `user32` linked. (2) `KeepGunsRight` (tick, every 1.5 s at most): a Skylands gun in the left hand that is not the same record as the right one is
  unequipped from the left (`ActorEquipManager::UnequipObject`, slot `LookupByID<BGSEquipSlot>(0x13F43)` LeftHand) and, when the right holds no gun, equipped into the right (0x13F42); notice "Skylands: guns go in the
  right hand only"; log "left hand: Skylands gun .. was in the left hand ..: moved to the right hand / taken out of the left hand"; ini `DualGuns=1` (not written, read if present) switches it off for the Gunzerker later.
  (3) the mouse log skips codes 0/1 too. UNCONFIRMED in game: all of it (the poll, the equip moves; 0x13F43 = LeftHand is from memory of Skyrim.esm).
- 0.61.2 in game (user, SkylandsNative.log 8049baed "SkylandsNative 411"): G works great, the middle mouse "had some issues" (the log has NO "seen down by Windows" line: the poll never saw it); the spell bugs are GONE
  ("attack handler: the left button came up after a gun was taken in hand: its release goes to the game" x3), ammo is consistent, every shop shows ammo; `KeepGunsRight` works ("Skylands gun FE003C88 was in the left
  hand (right hand FE003E0B, a gun): taken out of the left hand" x3); the enemy bar picks and drops the shielded hostile ("now about FF000E66 (the shielded hostile hit last)", "not in the crosshair or hit for a while",
  "dead, gone or no longer hostile"); a maker shield bonus showed ("the player's capacity bonus changes the shield from 70.0% to 73.1%": Jakobs 8 capacity; rate/delay changes are not logged); a bonus projectile fired
  ("prof: 1 bonus projectile(s) on 1 (4.0% chance)"). 0.61.3 (TestBuild-184, plugin 1.37.3 = "SkylandsNative 412"), the user: (1) no mouse button for the toggle by default (`LeftHandMouse=-1`, `LeftHandRev=3` resets
  it once; the setting and the Windows poll for 2/3/4 stay); (2) Torgue's second stat is the BONUS PROJECTILE CHANCE again (`kMakerStats[6] = {kDamage, kProj}`) and it is the CHARACTER's: `kSecondaryEverywhere` makes
  `BonusFor` give it to every gun in full (launchers still x0.5); Torgue no longer adds shield capacity. UNCONFIRMED in game. NEXT FEATURE: WEAPON SLOTS, PHASE 1 (docs only): interview done, `docs/weapon-slots-roadmap.md` WRITTEN, AWAITING APPROVAL (4 slots, hold Left Alt + 1-4 to assign, wheel switches while a gun is drawn with the zoom swallowed, wrap + skip empty, lost gun empties its slot, notices only, the game's equip; open: section 6).
- WEAPON SLOTS STAGE 1 = 0.62.0 (TestBuild-185, plugin 1.38.0 = "SkylandsNative 413"; the user approved the roadmap, section 6: pressing the slot that already holds the same gun leaves it unchanged).
  `g_slots[4]` (base form ids, co-save 'SLOT' v1 via `SlotSave/SlotLoad/SlotRevert`); `InputSink`: `SlotKey` (56 Left Alt) held -> keyboard 1-4 (codes 2-5) = `QueueSlotAssign` (task -> `SlotAssign`: the gun in hand into the
  slot, out of any other slot, notice "Slot N: name" / "(already)"); wheel codes 8/9 while `SlotsWantWheel()` (slots on, gun mode, gun really in hand, `AsActorState()->IsWeaponDrawn()`, no menu, a slot filled) =
  `QueueSlotSwitch` (600 ms guard `g_swapUntilMs`; task -> `SlotSwitch`: next filled slot, wraps, skips empty and the gun in hand, a gun no longer in the pack empties its slot with a notice, `ActorEquipManager::EquipObject`
  into RightHand 0x13F42); hooks on slot 1 = `CanProcess` (before the slots that moved on 1.7.99): `ZoomHook<0/1>` on `VTABLE_FirstPersonState[1]` / `VTABLE_ThirdPersonState[1]` (the PlayerInputHandler part) answer false
  for Zoom In/Out while `SlotsWantWheel()`, `HotkeyHook` on `VTABLE_FavoritesHandler[0]` answers false for Hotkey1-4 while the slot key is held. Ini `WeaponSlots`, `SlotKey`, `SlotHookZoom`, `SlotHookHotkeys` (new keys
  take defaults). Log "slots: on ...", "slots: ... hooked (vtable slot 1, was module+..)", "slots: slot N = ..", "slots: wheel down/up: slot a -> slot b (..)", "slots: slot N emptied", "the camera's zoom swallowed",
  "a favourites hotkey (1-4) blocked", "slots: save/load - ..". UNCONFIRMED in game: all of it (that CanProcess is slot 1 on 1.7.104 for these handlers, that the zoom is handled by the camera states, the equip while drawn).
- 0.62.0 in game (user, SkylandsNative.log 0049b3aa "SkylandsNative 413"): "works great"; all three hooks installed on 1.7.104 (first-person camera was module+8F5430, third-person module+8FDCA0, favourites module+962120), assigning,
  the hotkey block and the zoom swallowing logged, no exception lines. Seen: scrolling while the new gun comes out zooms the camera for a moment (gun mode and `IsWeaponDrawn` both drop during a swap). 0.62.1 (TestBuild-186,
  plugin 1.38.1 = "SkylandsNative 414"): `SlotsWantWheel` = slots on, no menu, a slot filled, and (within `SlotSwapGraceMs` 1500 of the last switch, `g_lastSwapMs`) or (a Skylands gun in EITHER hand via `HeldGun`
  and weapon state not `kSheathed`, i.e. drawing counts); no longer reads gun mode. UNCONFIRMED in game. The user also asked how Borderlands-style cel shading could be done (options given, nothing built).
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
