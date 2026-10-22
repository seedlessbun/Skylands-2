# Enemies with staff guns (0.15.0)

Written before the first test. "Known" = read from the game's data or confirmed in this project's logs; "expected" = how Skyrim's
combat AI is generally understood to behave; "guess" = nothing here confirms it. No enemy tuning has been done beyond the
defaults below; it waits for the first test.

## What was built
* Pandora's enemies are armed by the watcher script (`SkylandsHunter`): it picks a gun from the `SkylandsGunsAny/Good` leveled
  lists, adds it, equips it (plus 30 steel bolts, now pointless), and the same lists decide what enemies drop. Since 0.15.0 those
  lists give the **staff guns** in place of the crossbow SMGs and assault rifles (the tier lists are overridden in
  `SkylandsGunModels.esp`; pistols, shotguns, snipers and launchers are still crossbows). The watcher itself did not change: a
  staff gun carries the `SkylandsGun` keyword, so "is it carrying a gun" and the rarity beams (the `SkylandsGunList` form list) work.
* A staff gun's enchantment is its bullet: one aimed, fire-and-forget, hostile damage effect with the Borderlands projectile
  (known, the tests read it from the plugin). An enemy holding it is an NPC with a staff.
* The SKSE plugin listens for spell casts (`TESSpellCastEvent`). When an enemy (not the player) casts the enchantment of the gun
  in its hands it starts the rest of a burst: `burst - 1` more bullets, one every gun interval, each launched from the gun's
  `SkylandsMuzzle` node at the enemy's current combat target's chest, with twice the player's spread. The burst length is the
  Borderlands automatic burst count of the gun type (submachine gun 6, assault rifle 4, from `sheets/shooting.json`), written in
  the gun's `SkylandsGun_c.._i.._r.._s.._b..` keyword. The first bullet of a burst is the game's own cast.
* Enemies have no magazine and no reload (cost 0, charge never used). Their guns are not fired by the player's attack-button path.

## How the AI is expected to use it
* **Choosing to shoot.** An NPC with a staff in the hand and a hostile, aimed damage spell on it casts at its target when the
  target is in the spell's range and in line of sight (expected: this is how every vanilla staff-wielding bandit mage works).
  The hostile and detrimental flags of the bullet effect come from the vanilla staff's own effect and are kept (a friendly flag
  would make the AI treat the staff as a buff and never aim it). Which actors the AI lets use a staff at all is a combat-style
  matter: archetypes without magic skills may prefer melee even with a staff equipped (guess; the first test shows whether
  ordinary bandits shoot).
* **Range.** The AI starts casting a projectile spell from some way out and stops approaching; staves are used as ranged weapons
  and the NPC keeps its distance or holds position (expected). The bullet's range is 30000 units (about 400 metres), far more than
  the AI's own casting range, so the limit is the AI's, not the bullet's. At close range an NPC with a melee weapon in its pack may
  swap to it (expected; the watcher gives only the gun, so most will not have one).
* **Cadence.** The game casts a staff the way it does for the player's staff: a short wind-up, then the cast, then a pause. That is
  the rate of **bursts**. Inside a burst the plugin sets the rate (0.13 to 0.15 s). So an enemy fires a burst of 4 to 6 bullets,
  stands for the cast cycle, and fires another. This differs from the player, who fires continuously while the button is down; it
  is deliberate (enemies should not be a stream of bullets) and the burst count is one number in the gun's keyword to tune.
* **Aim.** The first bullet is aimed by the AI, with its normal projectile prediction for moving targets (expected). The extra
  bullets are aimed at the target's position when each one leaves (no lead) with a 2x spread, so a target running sideways is
  hit less than by the first bullet. The shooter's bursts stop if it dies or its 3D unloads. They do not check line of sight: an
  enemy that loses sight mid-burst fires the remaining bullets at the target's position anyway (into whatever is in between).
* **Friendly fire.** The bullets are launched with the enemy as shooter, like any spell projectile, so they hit whatever they meet:
  other enemies included (guess: damage to allies may make them hostile to the shooter, as with vanilla spells).
* **Taking cover, strafing, fleeing.** Not touched; the vanilla combat style of each actor decides.

## What the first test should tell us (the log names it)
`Documents/My Games/Skyrim Special Edition/SKSE/SkylandsNative.log`:
* `enemy cast listener registered` at start-up.
* `enemy <id> cast <spell> holding gun <weapon> (its enchantment <ench>): a burst of N` (the first eight casts). If instead it says
  `not the gun's own cast`, the game sends a different form for a staff cast and the plugin needs to match on that.
* If no such line ever appears while enemies visibly fire staffs, `TESSpellCastEvent` is not sent for NPC staff casts and the burst
  has to be driven another way (a hook on the NPC's cast, or the enemy script).
* `bullet origin (enemy): muzzle (...)` once: the muzzle node was found in the enemy's 3D (third person). `hand` means the node
  is missing in their weapon model.
In game: do ordinary bandits raise and fire the guns at range, how long is the pause between bursts, do the bullets come from the
barrel, and do they hit.

## Not done (waiting for the test)
Per-enemy burst or cadence tuning by rarity or enemy class; leading targets; line-of-sight checks inside a burst; reload pauses
for enemies; enemy-specific spread; not firing into allies; replacing the 30 pointless steel bolts the watcher gives.
