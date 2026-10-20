# Borderlands 2 shooting in Skyrim

Status 2026-10-20. Plan: `/root/.claude/plans/harmonic-meandering-popcorn.md` (kept in the session); this file records what is built.

## Built (0.11.x), all in the optional second plugin (`SkylandsGunModels.esp`), Skylands.esp is unchanged and stays light
- `--gun-shooting blast` (kit: `Install-Skylands-GunModels-Shooting-Blast.bat`): every launcher, and every gun that has an element,
  gets an extra effect on its own enchantment that spawns an explosion (`EXPL`) where the shot lands. The explosion carries the gun's
  element as a vanilla enchantment (fire/shock/corrosive/slag map to the vanilla weapon enchantments in `sheets/elements.json`), has a
  radius per gun type (`SPLASH` in `generate.py`: launcher 420, pistol 90, SMG/AR 80, shotgun 70, sniper 60 Skyrim units) and does a
  fraction of the gun's damage (launcher 100 %, others 25-35 %). Art comes from a vanilla explosion found by editor id in the player's
  Skyrim files (the setup log says which one was used); with none found the blast still works but has no art.
- `--gun-shooting bullets`: the steel bolt (what every Skylands gun fires) gets a fast, nearly flat projectile (gravity 0.02,
  speed 9000) by overriding the bolt's `PROJ`.
- `--gun-shooting both`: both.

## Not built yet
- Reading the real Borderlands 2 numbers (fire modes, pellets, spread, projectile speed, explosion radius): `shootingsurvey`
  (`Run-ShootingSurvey.bat`) writes `work/shooting-survey.json`; the `SPLASH` table and bolt speed above are placeholders until that
  file has been read.
- Script fire modes (burst, automatic, shotgun pellets, magazine and reload) and spell-based bullets: see the plan.
