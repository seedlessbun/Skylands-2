# Gun feel: sound, flash and the small things (0.17.0)

## Built in 0.17.0
* **Magazine message** (every ten shots, so it does not clutter the screen): `Staff gun: magazine 38 of 48, fire rate 7.2/s (measured 6.8/s),
  reload 2.1 s, spread 1.5 deg`. The first three are what the gun is set to do *now*, relic bonuses (`Variable06/07/08`, `docs/relics.md`)
  included; "measured" is what the trigger actually produced since it went down (rounds / seconds, 0 until there are three rounds). The
  measured rate is the one to compare with the description: Papyrus waits are not exact, so it can sit a little under the set rate, and a
  bigger gap between the two at high rates means the script loop, not the gun, is the limit.
* **Shot sound per gun type**: every staff gun carries a keyword `SkylandsSnd_<type>`; the script picks the sound whose keyword the gun
  has (`PickSound`). For now the sounds are Skyrim's own (submachine gun: a crossbow shot; assault rifle: a short bow shot, else the
  crossbow); the install log says which ("shot sound ..."). It is a stand-in.
* **Muzzle flash**: tried in 0.17.0 through the projectile record's own muzzle-flash feature (flag on, our `Flash_Staff_*.nif`, a short light) and the
  game CRASHED on the first bullet the plugin launched (`SkylandsNative.log` ends right after "bullet origin (player): muzzle"). Switched off in 0.17.1
  (`generate.STAFF_MUZZLE_FLASH = False`; the code is kept). The plugin now logs "launching ..." / "launched" around the first three launches, so a
  crash inside the game's launch call shows. A safer flash would be made by the plugin itself: place a short-lived light and glow mesh at the
  muzzle node after each launch (no projectile feature involved).

## Borderlands sounds: not built yet, and why
Borderlands 2 keeps its sound in its own format (Wwise banks and streamed `.wem` files, or Unreal sound objects in the packages; which one
is not known until a real install is looked at). Skyrim plays `.wav`/`.xwm` files through sound-descriptor records. So the work is:
1. **Find them.** `Check-BL2-Audio.bat` (new in the test kit) lists the audio files of the Borderlands folder and the sound-looking objects
   in its packages, with the weapon ones picked out, into `work\bl2-audio-report.txt`. Nothing is changed. Send that file.
2. **Name them.** Work out which sound belongs to which weapon type and manufacturer (the weapon definitions point at sound events).
3. **Decode them.** `.wem` is usually Wwise Vorbis; the installer would download a free decoder during setup (as it does UModel for meshes) and
   write plain `.wav` files into `Data\Sound\FX\Skylands\`. Nothing from Borderlands is shipped; it is made on the player's PC.
4. **Attach them.** One sound descriptor per weapon type (later per manufacturer and element) in `SkylandsGunModels.esp`, and the
   `SkylandsSnd_<key>` keyword mechanism already in place picks it per gun. Enemies' first bullet uses the effect's cast sound the same way.

## Small details that would make the guns feel better (nothing here is built)
Sound
* Dry-fire click on an empty magazine, reload start / magazine-in / bolt sounds timed to the reload, a low-ammo warning tick.
* Element layer on the shot: a soft crackle, hiss or zap with the plain gun sound for shock, corrosive, slag, fire.
* Pitch and volume by rarity or fire rate so a legendary sounds different; a reverb tail outdoors; enemies' shots audible from far away.
* Hit sounds: flesh, armour, shield, critical; the Borderlands shield-break and shield-recharge sounds.
Visuals
* Shell casings from an ejection port (physics objects), a small smoke puff after bursts, tracers only every few rounds, element-coloured
  impact sparks and decals, a bright flicker on the weapon itself.
* Hit marker on the crosshair, floating damage numbers (white, yellow for crits, element colours), a crit flash.
Handling
* Recoil: a small camera kick per shot that recovers, growing while held; spread that blooms the longer the trigger is down and tightens when
  standing still or crouching; a little screen shake on big guns.
* Aim down sights (zoom, tighter spread, slower walk), weapon sway, a reload that tilts or lowers the gun, sprint-to-fire delay.
* Fire modes per gun (semi / burst / full-auto) on a key; reload on a key (R) and a cancel by switching weapons.
Interface
* An ammo counter and reload bar instead of the charge bar and the ten-shot message; the gun card shown on pickup with damage per second
  worked out from rate, damage, crit and element; rarity colour on the name.
