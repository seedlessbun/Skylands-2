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

## Built: `--gun-shooting bl2` (kit: `Install-Skylands-GunModels-Shooting-BL2.bat`)
All in the optional second plugin `SkylandsGunModels.esp`; Skylands.esp is unchanged and stays light.
- One AMMO per gun type x element (6 x 5 = 30) with its own projectile (`PROJ`) cloned from the steel bolt: speed = Borderlands
  speed / 3, flat flight. Launchers and elemental guns get an explosion (`EXPL`, art from a vanilla explosion found by name;
  element = the vanilla weapon enchantment of that element, radius 420 for launchers, 60-90 otherwise).
- Fixed ids so the script can find things: ammo `0x800 + kind*5 + element`, kind keywords `0x81E+kind`, element keywords `0x824+element`.
  Every gun's record carries its kind (and element) keyword.
- The watcher script's `GiveRounds` (on `OnObjectEquipped`) finds the keywords with `Game.GetFormFromFile`, tops up the matching
  rounds (to 60 when fewer than 20) and equips them, so a gun always shoots its own rounds.
- Not enemies: bandits' guns still fire steel bolts.

## Also
- `--gun-shooting bullets`: only the steel bolt becomes a fast flat shot (backup version).
- The first attempt (an extra effect on each gun's enchantment that spawned an explosion) did nothing in game and was removed.

## Not built yet
Burst/automatic fire, shotgun pellets, spread, magazine and reload, rocket flight/explosion radius from the game, BL2 sounds.
