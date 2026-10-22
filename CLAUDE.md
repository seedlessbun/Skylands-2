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

Tests that need a tool skip when its variable is unset; with all three set, 112 passed at 0.14.0.
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
- Staged move from crossbow-based guns to per-type base weapons: **Stage 1** (staff SMG prototype), version
  **0.14.0**, TestBuild-80 (`Install-Skylands-GunModels-Shooting-Staff.bat`, `--gun-shooting staff`).
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
