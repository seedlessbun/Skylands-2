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
