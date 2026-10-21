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
- Plain Papyrus only, no SKSE.
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
- `tools/`: `gen.py`, `package_testkit.py` (zip + install bats), `espcheck/` (Rust), `nifcheck/` (C++).
- `tests/`: pytest; `fake_skyrim.py` / `fake_bl2.py` build tiny fake installs.

## 4. Build and test
Run from the repo root (needs `pytest`, `lz4`):

    CHAMPOLLION=<path>/Champollion ESPCHECK=<path>/espcheck NIFCHECK=<path>/check python -m pytest tests -q

Tests that need a tool skip when its variable is unset; with all three set, 100 passed, 2 skipped (nifcheck not built) at 0.13.12.
Rebuild the tools if they are gone:
- Champollion (decompiler): `git clone https://github.com/Orvid/Champollion`, then
  `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build` (needs Boost program_options);
  binary `build/Champollion/Champollion`.
- espcheck: `cd tools/espcheck && cargo build --release` (`target/release/espcheck`).
- nifcheck: see `tools/nifcheck/README.md` (nifly + `g++`; binary `check`).

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
  **0.13.12**, TestBuild-75 (`Install-Skylands-GunModels-Shooting-Staff.bat`, `--gun-shooting staff`).
- Confirmed in game (0.13.11, log and screenshot): quest starts, ability added, staff given, box on equip (events registered,
  script weapon and spell set), shots counted from the cast event, reload (unequip/re-equip) happens. The Papyrus log had no
  error from the staff script; its errors were SkylandsHunter (`AbilityInit`, `GetContainer`) and a ghost `SkylandsGunnerQuest`.
- Seen wrong in 0.13.11: the projectile looked like the vanilla staff's (art is the donor fireball, placeholder; whether the
  6667 speed applied is unconfirmed), holding the button did NOT repeat, the model pointed up or down (turn `-45,0,180`).
- 0.13.12: burst fire. The staff's own cast is bullet 1; `Burst`/`Extra` in `scripts.staff_gun` cast `BulletSpell` from the
  player `burst - 1` more times, `Interval` apart (SMG: 6 at 0.13 s), each counted against the magazine. Class
  `SkylandsStaffGun12`, ids skip 96. `Spell.Cast` on the player is unconfirmed in game.
- Placeholders: tracer/projectile art (donor fireball), per-element ammo on the crossbow guns, explosion radii and
  rocket speeds (`sheets/shooting.json`, `SPLASH`).
- The user's Stage 2 instruction: after the Stage 1 report they say which animation type suits each gun type; convert
  nothing else before that.
- Test tools in a fresh container: `apt-get update`, then `liblzo2-dev libboost-program-options-dev libfmt-dev`, `pip install python-lzo`;
  Champollion needs `#include <cstring>` in `Pex/FileReader.cpp` and `<strings.h>` in `Champollion/CaselessCompare.h` on Ubuntu.

## 7. Open questions for the user
- SKSE: yes or no?
- Melty dependency handling.
- Which animation type for each gun type (Stage 2).
