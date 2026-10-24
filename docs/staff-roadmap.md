# What else the staff guns can get (from docs/skse.md), in a suggested order

Cost: S = under a day of work and a test build, M = a few builds, L = a project. Risk is what could go wrong on this runtime (Skyrim 1.7.104).

| # | Feature | What it is | How, with what we have | Cost | Risk |
|---|---|---|---|---|---|
| 1 | **Reload on a key** | R (any key) starts a reload now, switching weapon cancels it, a round stays chambered if you reload early | the plugin already sees the keyboard (input sink); add a key event and a native `ReloadPressed()` polled like the trigger | S | low |
| 2 | **Fire modes** | a key toggles semi / burst / full-auto per gun, from the Borderlands data | the script's hold loop already has the pieces (one shot vs a loop vs N shots); a keyword says what a gun allows | S | low |
| 3 | **Recoil and spread bloom** | camera kick per shot with recovery; spread grows while held | plugin nudges the camera angles per shot (`PlayerCamera` / player angles); bloom is a multiplier on the existing spread argument | M | medium (camera API on 1.7) |
| 4 | **Hitscan and damage falloff** | sniper-style instant hits, damage by distance, headshots | plugin ray cast from the muzzle (`bhkPickData`) instead of a projectile; damage dealt through the game; headshot from the hit node | M | medium |
| 5 | **Damage model** | Borderlands: shields, crits, element status effects, floating numbers | plugin listens to hit events (`TESHitEvent`) and applies effects; numbers via a small UI; crit chance from the gun's stats (already rolled) | L | medium |
| 6 | **A real HUD** | ammo counter, reload bar, fire-mode light | SKSE's UI / a small Scaleform menu, or the free "iWant"-style approach; replaces the charge bar | M | high (UI on 1.7) |
| 7 | **Aim down sights** | held key zooms and tightens spread, slows walking | field-of-view and move speed from the plugin; spread multiplier already exists (`FireGun`'s argument) | M | medium |
| 8 | **Muzzle and shell effects** | casings with physics, smoke, per-element impact sparks | placed objects from the plugin at an ejection node in the mesh (like `SkylandsMuzzle`); impact data sets per element on the effects | M | low |
| 9 | **Per-instance guns** | one record per gun type with its stats stored on the item (names, parts, rarity per copy) | `ExtraData` / `WornObject` from the plugin instead of ~40 records per balance; changes how loot is made | L | high (saves) |
| 10 | **Relic items** | the Borderlands relics, class mods, shields as wearable items | value-modifier abilities on `Variable06/07/08` (done: `docs/relics.md`); this is item design and loot, not code | M | low |
| 11 | **Animations** | gun reload / draw / fire animations replace the staff's | needs animation files someone authors and an animation replacer (OAR) the player installs; the plugin can send animation events | L | high (assets) |
| 12 | **Crossbow guns on the same engine** | pistol, shotgun, sniper, launcher use the plugin too | pistol and sniper first (single shots, hitscan for the sniper), shotgun = N pellets per pull, launcher = one slow projectile with a big silent-or-visible blast | M each | medium |
| 13 | **Enemy behaviour** | bursts with pauses, line-of-sight checks, leading, reload pauses, not shooting through allies | `docs/enemy-ai.md` lists them; all live in the plugin's cast listener | M | medium |
| 14 | **Loot and enemies** | injection without huge lists, boss health bars, vault-hunter models | leveled-list changes (done in part) and UI | L | medium |

Suggested order after the sound and flash tests: 1 and 2 (small, make the guns feel like guns), then 3 and 7 (handling), then 8 (looks),
then 5 and 6 (the Borderlands layer), with 10 whenever the relic list is decided. 4 and 12 are the way to bring the sniper and pistol
over; 9 and 11 are the big ones and should wait for a decision on whether Skylands wants to depend on more than SKSE.

## Aim down sights (0.20.0, plugin 1.5.0)

Hold the block button ("Left Attack/Block", right mouse by default): the view zooms (1.3x SMG, 1.6x rifle, keyword `_z13` / `_z16`, `generate.STAFF_ZOOM`), the
spread narrows to `AimSpread` (0.5) and walking slows to `AimWalk` (0.7) of normal, all eased by `AimRate` (ini `Data/SKSE/Plugins/SkylandsNative.ini`). While a gun
is in the hand the plugin keeps the game's attack handler from getting the left button too, so there is no block, bash or left-hand cast. The zoom is the world field of
view (the INI setting `fDefaultWorldFOV:Display` and `PlayerCamera::worldFOV`, restored exactly when the aim ends); the gun model does not move to the middle of the screen
(that needs animations). UNCONFIRMED in game: that the field of view change shows (the game may rewrite it each frame), that the walking slow works (`SpeedMult`
actor value), and that nothing stays changed after a save made while aiming. The ten-shot message's spread shows the aimed value.
