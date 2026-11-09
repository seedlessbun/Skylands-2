# Handoff: minor tweaks and bug fixes, then the left-hand toggle

Written at 0.60.1 (TestBuild-179, plugin 1.36.1 = "SkylandsNative 407"). Read `CLAUDE.md` first: section 6 is the build-by-build history and
every entry there was checked against code or a log.

## 1. Where things are
- The latest work is on branch `claude/eager-archimedes-xtu69b` (commit "SkylandsNative.dll built by CI from 79dc8aa..."). A new session is usually
  given a different branch: check it is not behind this one (`git fetch origin claude/eager-archimedes-xtu69b` and compare). If it is, fast-forward
  or reset your branch to it BEFORE any work (it happened once: a session's branch started at 0.13.11).
- Last build sent: TestBuild-179 = 0.60.1. The user has not reported on 0.60.0 or 0.60.1 yet.

## 2. Build routine (every build)
1. Bump `VERSION` in `setup/skylands_setup/build.py` and the TestBuild number in `tools/package_testkit.py`.
2. If `native/skse` changes: bump `kVersion` (e.g. 407 -> 408) and `.Version = { 1, 36, 1, 0 }` in `native/skse/src/main.cpp`, and the
   matching asserts in `tests/test_pex.py`, `tests/test_badass.py`, `tests/test_voices.py`.
3. Run the tests (`python -m pytest tests -q`), commit, `git push -u origin <branch>`.
4. If the plugin changed: WAIT for the CI commit "SkylandsNative.dll built by CI from <your sha>", then `git pull`. If none arrives in ~5 min the
   compile failed: read the job log (GitHub MCP `actions_list` / `get_job_logs` with `failed_only`). The container cannot compile the plugin, so CI is
   the only compiler; read CommonLib headers from
   `https://raw.githubusercontent.com/alandtse/CommonLibVR/v12.1.0/include/RE/...` when unsure of an API.
5. `python tools/package_testkit.py`, then send ONE zip (`dist/Skylands-TestBuild-N.zip`) to the user.
6. Add an entry to `CLAUDE.md` section 6 (what changed, what is UNCONFIRMED in game, which log lines to read).

## 3. Lessons that cost builds (short list; full list in CLAUDE.md)
- CommonLib is built multi-target (SE/AE/VR). Some base classes are reached only through accessors: `TESAmmo::AsKeywordForm()`, `GetInfoRuntimeData()`,
  `AsActorValueOwner()`... `As<BGSKeywordForm>()` on ammo returned null (the 0.59.3 "no vendor list").
- Never call a function that takes a lock while holding the same lock (0.43.0 crash at load). Declare atomics before use.
- No string parameters on natives (0.15.1: they did not arrive).
- Scripted edits (python/sed): grep afterwards that they applied; a python edit once dropped `\"` escapes and broke the compile.
- Writing into the HUD movie only from `AddUITask` inside the SEH `Guarded` wrapper (0.48.x crash).
- Do not rename Papyrus script classes (ghost objects; ids are spent). Put new logic in the plugin or keywords.
- `Skylands.esp` stays byte-identical; new records go LAST in `SkylandsGunModels.esp` so older form ids do not move.
- Check the first line of the user's log (`SkylandsNative NNN` / "Skylands x.y.z setup") against the build before reading anything else.
- Ask/confirm numbers with the user before building when they ask for confirmation; the user is testing on their own playthrough.

## 4. Things waiting for the user's in-game report
- 0.60.0: per-system progression pace keys (`ProfBL2*`, `ProfSkyrim*Type*/Maker*`), makers' second stat = shield bonus (log: "prof:" lines,
  `shield::g_profShieldCap/Rate/Delay`).
- 0.60.1: merchant vendor keywords (log: "shop: gave the <kind> ... (fits the item / nothing fitting ...)"); ammo should now show at
  include-only shops (Ulfberth, Adrianne) through `VendorItemArrow`.
- Progression is being playtested in both modes (`ProfSkyrimStyle=0/1`); finalising it is a later session (`docs/progression-roadmap.md`).
- Known untidy bits the user may ask about: the shield/relic HUD and merchant logs are verbose; `STAFF_REV` info string says an old build.

## 5. The left-hand toggle (after the tweaks) - interview FIRST, no code until the user approves a plan
The user wants to be able to toggle use of the player's LEFT hand while holding a Skylands gun (e.g. a spell, torch or one-handed item in the left hand).
What the code does today, all of which the feature collides with:
- Staff guns are staff-type weapons (keyword `WeapTypeStaff`, equip slot forced to RightHand: `STAFF_EQUIP_SLOT`). The engine still reports staff-type
  weapons in BOTH hand slots for NPCs (`GetEquippedObject` left = right = gun; two models in the 3D: CLAUDE.md 0.33-0.35).
- In gun mode the plugin hooks `AttackBlockHandler::ProcessButton` and SWALLOWS "Right Attack/Block" (the trigger) and "Left Attack/Block"
  (aim down sights, `UpdateAim`/`CenterGun`). A usable left hand needs another ADS button or a toggle key (and the reload key logic lives there too).
- First person: `HideLeftArm` scales `NPC L UpperArm [LUar]` to 0.001 every tick while a gun is held (ini `HideLeftHand=1`), and `HideHands` culls arm
  parts while fully aimed. A visible left hand needs those off while the toggle is on.
- The gun is held with the staff's arm animations; a left-hand spell/torch has its own animations, which may clash (no animation replacer in Skylands).
Questions to put to the user: what goes in the left hand (spells only? torches? shields? one-handed weapons?), which key toggles it and what
ADS moves to, whether the gun still fires while a left-hand item is out, first-person look (show the left arm only when toggled), NPCs too or player only.
Then write `docs/left-hand-roadmap.md` (limits, method, risks, stages) and wait for approval, as was done for shields, relics, Badass and progression.
