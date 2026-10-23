# Gun feel: sound, flash and the small things (0.17.0)

## Built in 0.17.0
* **Magazine message** (every ten shots, so it does not clutter the screen; from 0.18.0 the numbers come from the plugin, which fires the gun): `Staff gun: magazine 38 of 48, fire rate 7.2/s (measured 6.8/s),
  reload 2.1 s, spread 1.5 deg`. The first three are what the gun is set to do *now*, relic bonuses (`Variable06/07/08`, `docs/relics.md`)
  included; "measured" is what the trigger actually produced since it went down (rounds / seconds, 0 until there are three rounds). The
  measured rate is the one to compare with the description: Papyrus waits are not exact, so it can sit a little under the set rate, and a
  bigger gap between the two at high rates means the script loop, not the gun, is the limit.
* **Shot sound per gun type**: every staff gun carries a keyword `SkylandsSnd_<type>`; the script picks the sound whose keyword the gun
  has (`PickSound`). For now the sounds are Skyrim's own (submachine gun: a crossbow shot; assault rifle: a short bow shot, else the
  crossbow); the install log says which ("shot sound ..."). It is a stand-in.
* **Muzzle flash**: 0.17.0 tried the projectile record's own muzzle-flash feature and the game CRASHED on the first bullet the plugin launched; off since
  0.17.1 (`generate.STAFF_MUZZLE_FLASH = False`). Since 0.18.0 the plugin makes the flash itself: after launching a bullet it spawns a temporary effect of our
  glowing flash mesh (`Flash_Staff_<element>.nif`, one per element colour, written by the installer) at the muzzle for 0.06 s, facing the way the bullet
  goes (`BSTempEffectParticle::Spawn`). It is a flash only (no light). `MuzzleFlash=0` in `Data\\SKSE\\Plugins\\SkylandsNative.ini` turns it off; the log
  says "muzzle flash: spawning ..." / "spawned" for the first three, so a crash in it shows. UNCONFIRMED: that it appears, and where it points.

## Borderlands sounds: what the audio report found (0.18.0), still not built
`Check-BL2-Audio.bat` ran on a real install (Steam, Borderlands 2 with all DLC). What it showed:
* The sound is **Wwise**: `WillowGame\CookedPCConsole\Audio_Banks.pck` (320 MB, sound banks) and `Audio_Streaming.pck` (252 MB, streamed audio),
  plus one pair per DLC (`DLC\<name>\Lic\Audio\...`), all starting `AKPK` (Wwise's file package). There are no loose `.wem` files.
* The game's packages (`.upk`) hold the **event objects** that name the sounds, e.g. `Ak_Play_Wep_SMG_Dahl_Shot_Short`, with banks named
  `Akb_Wep_SMGs`, `Akb_Wep_Assault_Rifles`, `Akb_Wep_Pistols`, `Akb_Wep_Shotguns`, `Akb_Wep_Sniper_Rifle`, `Akb_Wep_Rocket_Launchers`.
* Weapon events per manufacturer (299 weapon event names in all):
  * SMGs: `Ak_Play_Wep_SMG_<Alien|BT|Dahl|Hyperion|Maliwan|Tediore>_Shot_Short`, `_Shot_Long`, `_Shot_Release` (a burst has a start, a held loop
    and a tail; that is the sound of automatic fire).
  * Assault rifles: `Ak_Play_Wep_Rifle_<Alien|Bandit|Dahl|Jakobs|Torgue|Vladof>_Shot[_Short|_Long|_Release]`, plus reload parts
    (`Clip_In`, `Clip_Out`, `Bolt_Close`, ...), also for pistols (`Clip_In`, `Clip_Lock`, `Action`, `Cyl_*`, `Breech_*`), shotguns (`Reload_*`),
    rocket launchers (`Reload_*`, `_Shot`).
So the Borderlands shot sounds exist per weapon type and per manufacturer, as the plan assumed.

What is left to build, in order:
1. **Read the packs.** AKPK has a table of banks and of streamed files; a bank (`BKHD`) holds an `HIRC` section that links an event (named by a hash
   of its name) to actions, to sounds and to the audio file ids. Reading that gives, for `Ak_Play_Wep_SMG_Dahl_Shot_Short`, the audio file(s)
   behind it. (Not started; needs one more look at a bank on the real install, which the next probe version can write out: the first bytes of
   each bank and the event table of `Akb_Wep_SMGs`.)
2. **Decode them.** Wwise audio is mostly Vorbis in Wwise's own packing (`.wem`). The installer would download a free decoder during setup (as it does UModel for
   meshes) and write plain `.wav` files into `Data\Sound\FX\Skylands\`. Nothing from Borderlands is shipped.
3. **Attach them.** A sound descriptor per weapon type and manufacturer in `SkylandsGunModels.esp` (Skyrim sound records pointing at those `.wav` files),
   chosen by the `SkylandsSnd_<key>` keyword mechanism already in place (the plugin plays the sound at each shot; the script hands it the descriptor).
   The held-fire loop sound of automatic guns needs care: the BL2 start/loop/tail structure does not map onto one sound per round; the first
   version would use the `Short` shot per round.

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
