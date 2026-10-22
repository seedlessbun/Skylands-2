# Stage 2: which animation type for which gun

Written while the Stage 1 staff SMG (0.13.16) is being tested. Nothing here has been converted: this is the comparison and a
proposal for the Stage 2 test build. "Seen" means seen in a game log or screenshot from this project; "known" means Skyrim
behaviour I am confident of from the game's data; "guess" means unconfirmed.

## What the animation type is
The weapon record's `DNAM` byte 0 picks the animation set the player uses: how the weapon is held, the attack, and (for the
ranged types) the draw, release and reload. Values: 0 hand to hand, 1 one-hand sword, 2 dagger, 3 one-hand axe, 4 one-hand
mace, 5 two-hand sword, 6 two-hand axe / hammer, 7 bow, 8 staff, 9 crossbow. The type also decides what the engine fires for
us: ammo for 7 and 9, the enchantment's spell for 8, nothing for the rest (a script has to fire).

## What we know about each (from this project)
| Type | Pose | Who fires the bullet | Seen |
|---|---|---|---|
| 9 crossbow | two-handed, shoulder | the engine, from the weapon, with ammo | The base of every gun so far. Rate is the draw-and-reload cycle; `WeaponSpeedMult` and ammo counting never gave usable shot messages (cause unknown). |
| 8 staff | one hand out, casting pose | a spell (ours, cast by the script: from the player's face; the staff's own cast comes from the hand) | Weapon, ability, charge, reload, hold loop all work or nearly (0.13.12 to 0.13.16). The cast has a wind-up. |
| 7 bow | two-handed, bow arm out | the engine, with ammo | Not tried. |
| 0-6 melee | fists, one- or two-handed swing | nothing: a script would have to fire on a swing event | Not tried. |

## What each type would mean for the six gun types (guess unless marked)
- **Pistol, SMG**: want a one-hand point-and-shoot pose and no wind-up. Staff gives the pose (known) and, with the hold loop, the
  rate (seen), but the wind-up and the face origin are its costs. A one-hand melee type has no wind-up on a swing (known) but
  the swing animation swings the gun (guess: looks wrong) and the shot would come from a script event.
- **Assault rifle**: same needs, two-handed look. Crossbow has the pose, not the rate (seen).
- **Shotgun, sniper, launcher**: a slow, deliberate shot suits the crossbow's draw and reload (known); only the rate was a
  problem for the fast guns. These three may be fine where they are.
- **Bow (7)**: engine-fired like the crossbow, but a bow's draw is the attack, so it is probably worse for guns than the
  crossbow (guess).

## The two costs that decide it
1. **Where the bullet leaves from.** Engine-fired (7, 9) comes from the weapon. Script-cast (8 and the melee types) comes from
   the player's face in plain Papyrus (seen, 0.13.14); a placed aim point showed no projectile (seen, 0.13.15).
2. **Rate and feel.** 7 and 9 are limited by the draw and reload animation (seen for 9). 8 is limited by the cast wind-up
   (seen) unless a script fires the bullets (seen, hold loop).

## Proposal for the Stage 2 test build (not built)
One install, one weapon per candidate type, all the same SMG model, so the user can swap between them on one character:
- **Crossbow (9)** as today, with a higher `WeaponSpeedMult` (the baseline).
- **Staff (8)**, the 0.13.16 version.
- **One-hand sword (1)** and **hand to hand (0)**: a swing fires a bullet from the script (guess: the shot message fires
  on `attackStart`; the box names the events it sees, as the staff's does).
- Each weapon's equip box reports its type and the events it receives, so the next round can be decided from the log.
- Nothing else converted until the user picks a type per gun type.

## What the user should compare
Press to first bullet, the rate while held, the pose and model in the hand, where the bullet leaves from, the reload, and any crash.
