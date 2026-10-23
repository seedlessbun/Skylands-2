# Relic stats: the player's weapon bonuses (0.16.0)

Borderlands 2 relics (and class mods, shields, anything that is worn or learnt) are meant to change how the player's guns behave. The
staff gun script reads three **actor values of the player** every time it acts, so anything that changes them changes every staff gun:

| actor value | what it does | formula |
|---|---|---|
| `Variable06` | fire rate bonus, percent | time between two rounds = the gun's interval / (1 + value / 100) |
| `Variable07` | reload speed bonus, percent | reload time = the gun's reload time / (1 + value / 100) |
| `Variable08` | accuracy bonus, percent | the gun's shot spread (degrees) / (1 + value / 100) |

0 is no change; 50 is one and a half times as fast (or as tight); a negative value slows or loosens. The divisor never goes below 0.2.
They are Skyrim's spare `Variable01`..`Variable10` actor values (`Variable10` shows the crossbow guns' stats line), so nothing else in the
game is expected to touch these three; they start at 0 and are saved with the character.

## How a relic works
Any of these changes the value, and the guns follow at the next shot (no reload of anything):
* an **ability / enchantment** with a *Value Modifier* magic effect on `Variable06`/`07`/`08` (the way "Fortify Smithing" works), on a worn
  amulet or ring, or a perk or spell the player has: the bonuses of several relics add up;
* a **script**: `Game.GetPlayer().ModActorValue("Variable06", 25.0)` (or `SetActorValue`);
* the console, to try it: `player.modav variable06 50` (and `player.modav variable06 -50` takes it back).

Where each stat applies: the bonus changes the wait in the hold loop (`Boost` in `scripts.staff_gun`), the reload wait, and the spread
multiplier handed to the plugin's `FireGun(..., spreadMult)`. Enemies do not use relics.

## The gun's own stats
Each gun's rolled stats set its numbers (they are the ones its description tells): its fire rate (rounds per second) is its rate of
fire, its reload is the reload time, and its accuracy roll (rarity, parts) scales the type's base spread. They are written into the gun's
`SkylandsGun_c<clip>_i<ms>_r<ms>_s<spread*10>_b<burst>` keyword; relics multiply on top.

## Not done
* A **damage** bonus and a **magazine size** bonus: a bullet's damage is the magnitude of its enchantment (fixed in the record), and the
  magazine is the staff's enchantment charge; both need more than a multiplier in the script (the plugin could scale the launched
  projectile's power; the magazine could scale the charge value and the weapon's maximum).
* The items themselves (the relics, their names, rarities, loot): only the variables they would change exist.
* The crossbow guns (pistol, shotgun, sniper, launcher) do not read these values.
