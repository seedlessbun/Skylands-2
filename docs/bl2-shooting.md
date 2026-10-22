# Borderlands 2 shooting in Skyrim

Status 2026-10-20. Data read from the player's game by `Run-ShootingSurvey.bat` (`work/shooting-survey.json`).

## What Borderlands 2 holds (from the survey)
Per gun type (`GD_Weap_*.A_Weapons.WT_*` weapon types and `GD_Weap_*.FiringModes.*`), Bandit defaults, other manufacturers differ:

| type | fire interval (s) | clip | reload (s) | spread | shots per pull | bullet speed (BL2 units/s) |
|---|---|---|---|---|---|---|
| pistol | 0.23 | 30 | 3.0 | 2.4 | 1 | 21500 |
| SMG | 0.13 | 48 | 4.2 | 1.8 | 1 | 20000 |
| assault rifle | 0.15 | 40 | 5.0 | 2.5 | 1 | 25000 (Torgue "gyrojet": 1000, accelerating, explodes) |
| shotgun | 0.80 | 9 | 4.4 | 8.0 | 6 pellets | 20000 |
| sniper | 0.15 / 0.70 | 6 | 4.0 | 1.0 | 1 | 45000 |
| launcher | 1.0 | 5 | 8.0 | 4.0 | 1 rocket (projectile definition, speed not in the survey) | rocket |

Elemental guns carry `ExplosionOverrideDefinition = GD_Weap_Shared_Effects.Default_Elemental_Explosions`: every elemental shot
spawns an elemental explosion where it lands. Launchers fire a `ProjectileDefinition` (`Projectile_Rocket_*`) that explodes.
The numbers are in `sheets/shooting.json`. The survey did not reach the rocket projectile or explosion radius definitions.

## Built: `--gun-shooting bl2` (kit: `Install-Skylands-GunModels-Shooting-BL2.bat`), 0.12
All in the optional second plugin `SkylandsGunModels.esp`; Skylands.esp is unchanged and stays light.

**Data.** `extract.shooting_of` now reads every gun balance's own weapon type (FireRate, Spread, ReloadTime,
AutomaticBurstCount, ProjectilesPerShot, ClipSize) and default firing mode (Speed, rockets, elemental explosion). A *profile* is one
gun type x manufacturer; profiles 0-5 are the gun-type defaults from `sheets/shooting.json`. Every gun's magazine is its weapon
type's ClipSize times its parts' clip bonus (the "Mag" number on the gun).

**Records.**
- 30 rounds (AMMO + PROJ, + EXPL for launchers and elemental guns): gun type x element, speed from Borderlands (/3), flat.
- Keywords on every gun (in its override): kind, element, profile, magazine tens and units.
- `SkylandsGunnerQuest` (start game enabled) gives the player `SkylandsGunnerAbility`, whose effect runs the script
  `SkylandsGunner` with every form and number as properties. (0.11.3 looked its forms up with `Game.GetFormFromFile` from the
  old watcher; in game it did nothing, so that was removed.)
- `SkylandsAimPoint`: an invisible object with 3D (an empty NIF) that extra rounds are fired from.

**Script `SkylandsGunner`** (on the player):
- Equip a gun: its rounds are topped up (90 when fewer than 30) and equipped; the magazine is filled.
- Every shot (the game's `OnPlayerBowShot`; until that event has been seen, a drop in the rounds count every 0.25 s stands in):
  the magazine counts down; shotguns fire `pellets - 1` more rounds at once; automatic guns fire `burst - 1` more rounds one
  every `fire interval` while the magazine lasts (Skyrim cannot see a held trigger without the script extender, so automatic fire
  is a burst per pull: SMG 6, assault rifle 4, Dahl uses its own burst count, Jakobs is semi-automatic). Extra rounds come from the
  aim point in front of the player's eyes, turned like the view plus a random angle within the spread, with `Weapon.Fire`.
- Empty magazine: the rounds are taken off for the reload time ("Reloading (3 s)"), then put back with a full magazine.
- Messages (Verbose on for now): "Skylands gunner ready", "Skylands gun: N-round magazine", "shots are seen", "Reloading".

**Placeholders** (not yet read from the game): burst size per pull, explosion radius (launcher 420, others 60-90), rocket speed
(6000 Borderlands units/s), the projectile speed scale (/3). `Run-ShootingSurvey.bat` (survey 2) now follows the projectile and
explosion definitions first.

## Also
- `--gun-shooting bullets`: only the steel bolt becomes a fast flat shot (backup version).
- The first attempt (an extra effect on each gun's enchantment that spawned an explosion) did nothing in game and was removed.

## Not built yet
Burst/automatic fire, shotgun pellets, spread, magazine and reload, rocket flight/explosion radius from the game, BL2 sounds.

## Staged move away from the crossbow (Stage 1, with SKSE since 0.14.0)

Goal: every gun type gets its own base weapon records instead of a copy of the crossbow, so fire rate, automatic fire and
feel are not limited by the crossbow's draw-and-reload animation. Stage 1 is one prototype, an SMG on the staff animation
type (`Install-Skylands-GunModels-Shooting-Staff.bat`, `--gun-shooting staff`). Stage 2 (which animation type for which gun
type) is in `stage2-animation-types.md`.

**Needs SKSE** (see `setup/skylands_setup/skse.py`): SKSE64 for the player's Skyrim runtime, Address Library for SKSE Plugins, and
Skyrim started through `skse64_loader.exe`. The installer checks all three and says what is missing. It installs
`Data/SKSE/Plugins/SkylandsNative.dll` (source in `native/skse`, built by `.github/workflows/skse-plugin.yml`).

* Since 0.15.1 every submachine gun and assault rifle is a staff gun: each crossbow variant is overridden in place in the second plugin
  (same form id, parts, rarity, element, stats, name, model) by a copy of a vanilla staff (animation type 8), so the loot lists, the
  beams and any copy in a save or an enemy's pack are staff guns. Enemies are armed from the same lists. The other four types are still
  crossbows. `Skylands.esp` is unchanged.
* The weapon's enchantment IS the bullet: one aimed, fire-and-forget, hostile effect (cost 0, magnitude = the gun's damage) whose
  projectile is the Borderlands bullet of the gun type and element (speed / 3, gravity 0, the element's explosion shared with the
  crossbow rounds, a glowing tracer in the element's colour). Shared per gun type x element: the projectile; per gun: the effect
  (it carries the stats text), the enchantment and the weapon. The old trigger (a concentration cast for the casting pose) is gone:
  the plugin keeps the attack button from the game, so there is no pose to start.
* A keyword per gun holds its numbers: `SkylandsGun_c<clip>_i<ms>_r<ms>_s<spread*10>_b<burst>`; the plugin reads them (`GunStat`).
* The player's bullets are the script's. `SkylandsNative.TriggerPressed/TriggerHeld` (the plugin's listener for the "Right
  Attack/Block" input event: any device, any remapping) say when the button goes down and while it is held; `FireGun` launches
  the held gun's bullet with `Projectile::Launch` from the gun's own muzzle node, aimed at the crosshair 3000 units ahead,
  within the gun's spread. No cast animation, no wind-up, no magicka.
* Enemies cast the staff like any staff; the plugin adds the rest of the burst (`enemy-ai.md`).
* No ammo item: the staff's enchantment charge is the magazine (`RightItemCharge` and `WornObject.SetItemCharge`, 100 per round). A
  reload waits the reload time with the gauge empty, then fills it. The gun stays in the hand.
* `SkylandsStaffGun18` (ActiveMagicEffect on the player, started by `SkylandsStaffGunQuest`): one script for every staff gun (it
  asks the plugin for the numbers of whichever one is put on), gives two staff guns once, fires, counts, reloads, and shows a box
  on the first equip (SKSE version, whether the plugin is loaded, magazine, charge gauge, what was built). A different gun starts with
  a full magazine; the same gun put on again keeps its rounds. The magazine is told on screen every ten shots.
* Native BL2 mesh fitted to the staff's own axes, turned `--staff-turn 60,0,180`, 25% bigger, moved 10% forward and up.
