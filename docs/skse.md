# SKSE in Skylands

Since 0.14.0 Skylands depends on SKSE (the Skyrim Script Extender). Skylands never ships SKSE or Address Library: the player
installs them once (`Check-SKSE.bat` says what is missing; the installer logs the same under `skse:`).

## What the player installs
1. **SKSE64** for their Skyrim runtime: https://skse.silverlock.org/ . `skse64_loader.exe` and `skse64_<major>_<minor>_<build>.dll`
   next to `SkyrimSE.exe`, and SKSE's `Data/Scripts` (the `SKSE.psc`/`.pex`, `WornObject`, `Input`, ...) in the Data folder.
2. **Address Library for SKSE Plugins**, the "All in one" file for their runtime:
   https://www.nexusmods.com/skyrimspecialedition/mods/32444 . `Data/SKSE/Plugins/versionlib-*.bin`.
3. Start Skyrim through `skse64_loader.exe`.

## What Skylands adds
`Data/SKSE/Plugins/SkylandsNative.dll` (+ `SkylandsNative.ini`), built from `native/skse` by `.github/workflows/skse-plugin.yml`
(MSVC, CommonLibSSE-NG, Address Library: it runs on every runtime Address Library supports). Its log:
`Documents/My Games/Skyrim Special Edition/SKSE/SkylandsNative.log`.

Papyrus class `SkylandsNative` (static functions):
| function | what it does |
|---|---|
| `Int Version()` | the plugin version (100 = 1.0.0) |
| `Bool TriggerHeld()` | the attack button ("Right Attack/Block": keyboard, mouse or gamepad, as remapped) is down, and no menu is open |
| `Bool TriggerPressed()` | the button went down since the last call (a tap shorter than a script poll is still seen) |
| `Bool FireBullet(Actor, Spell, Float spread, Float right, Float up, Float forward)` | launches the spell's projectile (`Projectile::Launch`) from the right hand's magic node (the first-person skeleton in first person), aimed at the point the crosshair looks at 3000 units ahead (`Convergence` in the ini), within a cone of `spread` degrees, offset in view space; no animation, no wind-up, no magicka. Runs on the game's thread a frame later. |

SKSE's own Papyrus used by the staff gun: `SKSE.GetPluginVersion`, `SKSE.GetVersion*`, `WornObject.GetItemCharge/SetItemCharge`.

## What the staff gun no longer needs (removed in 0.14.0)
animation-event guesses for press and release, `GetAnimationVariableBool` polling, the `RightItemCharge` actor value, the aim
point and the face origin (`--staff-origin`), unequip-and-re-equip reloads, the burst-per-pull of the crossbow guns' era.

## What SKSE and the plugin could give the guns (not built; roughly in order of value)
* **Recoil and sway**: nudge the camera pitch and heading per shot with a recovery curve (`PlayerCamera`/`PlayerCharacter` angles from the plugin), so automatic fire climbs and spreads.
* **Aim down sights**: a held key narrows the field of view and spread (`Game.SetGameSettingFloat`/the camera's FOV in the plugin), slows movement a little.
* **Real spread and bullet physics**: per-bullet random cones are in; gravity drop and speed come from the PROJ record; hitscan for snipers (`bhkPickData` ray cast from the plugin) with headshot detection and damage falloff by distance.
* **Muzzle effects**: a light and a flash NIF placed at the muzzle node for a frame, shell casings (placed objects with physics) from the ejection port, a shot sound per gun type from our own records.
* **A proper HUD**: an ammo counter and reload bar drawn with SKSE's UI/Scaleform (or a small custom menu), instead of the enchantment charge bar and notifications.
* **Reload on a key**: `R` (any key, from the plugin's input listener) starts a reload; cancelling it with a weapon switch; tactical reload (a round stays in the chamber).
* **Fire modes**: a key toggles semi/burst/auto, per gun, from the BL2 data.
* **Animations**: with an animation-replacer mod (Open Animation Replacer, an SKSE plugin the player installs) the staff's cast and the crossbow's draw and reload can be swapped for gun animations on weapons that carry a Skylands keyword; this needs animation files someone authors (Skylands cannot make them from Borderlands' files). The plugin can also send animation events directly (`Actor::NotifyAnimationGraph`) so a reload plays a chosen idle.
* **Damage model**: Borderlands numbers: shields, crits, element status effects (burn, shock, corrode, slag) applied by the plugin on hit events (`TESHitEvent`), floating damage numbers.
* **Item data**: SKSE's `Form.GetName`, `WornObject` (charge, enchantment, names per instance), `ExtraData`: per-instance gun stats and names instead of one record per variant, real Borderlands parts and rarity per instance.
* **Loot and enemies**: leveled item injection without huge leveled lists, `RaceMenu`-free vault hunter models (NiOverride/skeleton nodes), boss health bars.

## The crossbow guns (all other guns today)
They are still crossbows (animation type 9) with Borderlands rounds as ammo (`make_gunner`, `scripts.gunner`):
a shot is the engine's, extra rounds (shotgun pellets, an SMG's burst) are `Weapon.Fire` from an invisible marker, the magazine and
reload take the rounds away, and shots were found by counting ammo because `OnPlayerBowShot` never arrived. With SKSE:
* **Detect the shot properly**: the plugin listens for the projectile launch (`BSTEventSink<TESObjectLoadedEvent>`/a hook on `Projectile::Launch`) or SKSE's `RegisterForActorAction` (bow release): no ammo counting, no 0.25 s polling.
* **Spawn the extra rounds at the right place**: `FireBullet`-style launches from the weapon's muzzle node with the gun's spread instead of a marker in front of the eyes (pellets, bursts, rockets).
* **Take the draw and reload out of the way**: set the crossbow's attack speed and reload time per instance (`Actor::SetAnimationVariable`, weapon speed multipliers), or fire from the trigger event like the staff does while the crossbow animation only gives the pose; later replace the animation with OAR.
* **Per-instance data**: one crossbow record per gun *type* with stats on the instance (`WornObject`, `ExtraData`) instead of 40 variants per balance.
* **Magazine in the enchantment charge** like the staff, instead of rounds taken out of the pack.
