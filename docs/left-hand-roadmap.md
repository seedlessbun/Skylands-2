# Left-hand toggle: roadmap (PHASE 1, awaiting the user's approval, no feature code yet)

Written at 0.60.2 (TestBuild-180, plugin 1.36.2 = "SkylandsNative 408").

## 1. The user's answers (interview, 0.60.2)
| Question | Answer |
|---|---|
| What goes in the left hand | **Spells and shields** (not torches, not one-handed weapons) |
| Aiming down sights while the left hand is in use | **No ADS while the toggle is ON**; toggle OFF = aiming as today |
| How it is switched | **A hotkey** |
| What the hotkey does | **Mode only**: the player equips the spell/shield; the key only decides whether the left button uses it (ON) or aims (OFF). Equipment is never touched by the plugin. |
| Gun firing while the left hand casts/blocks | **Both at once** (right button fires, left button casts/blocks, independently) |
| First-person left arm | **Shown while ON**, hidden as today while OFF |
| Default key | **Middle mouse button** (Skylands is meant for first person, so losing a camera action on it is fine) |
| Who | **Player only** (enemies keep today's gun handling) |

## 2. What the code does today (all of it collides with the feature)
- Staff guns are staff-type weapons forced into the RightHand equip slot (`STAFF_EQUIP_SLOT`). For the PLAYER the left hand slot is free in the
  engine: vanilla Skyrim allows a staff in the right hand with a spell or a shield in the left, with its own animations for both.
- `AttackHook` (`AttackBlockHandler::ProcessButton`, vtable slot 6 on 1.7.104) swallows BOTH "Right Attack/Block" (the trigger) and
  "Left Attack/Block" (aim down sights) while gun mode is on, so today a left-hand spell can never be cast and a shield never raised.
- `InputSink` sets `g_aimHeld` from "Left Attack/Block"; `UpdateAim` zooms, narrows the spread, slows walking and moves the gun to the view.
- `HideLeftArm` scales the first-person `NPC L UpperArm [LUar]` bone to 0.001 every tick while a gun is held (ini `HideLeftHand=1`). A shield
  and a spell's hand art hang below that bone, so they vanish with it. `HideHands` culls the arms while fully aimed.
- The reload key and its Legendary hold are on the keyboard/`ReloadMouse`; the plugin already logs the first 30 mouse/pad presses with the
  game's event name for that button ("button down: device D code C event name '...'").
- The Papyrus gun script (`SkylandsStaffGun19`) arms on equip of a staff gun and lets go when THAT gun is unequipped; equipping a spell or a
  shield does not touch it (read in `scripts.py`: `OnObjectEquipped` -> `IsGun`, `OnObjectUnequipped` compares with `Gun`). No script change is planned.

## 3. Method (all in the plugin; no record, no script, no Skylands.esp change)
1. **State**: `g_leftHand` (atomic bool), OFF at start and after every load / new game (co-save Revert; see question 6.2 for keeping it in the save).
2. **Hotkey**: ini `LeftHandKey` = mouse button code (default `2` = middle mouse; the `ReloadMouse` rule accepts `n` or `256+n`), `LeftHandKeyboard`
   = keyboard scan code (default -1 = none), `LeftHand=1` switches the feature on. `InputSink` flips the state on the key's DOWN, only while gun mode
   is on and no menu is open. A notice says "Left hand: ON (spell / shield)" or "Left hand: OFF (aim down sights)"; the ammo HUD shows a small
   "LEFT HAND" tag while ON.
3. **Left button**: while ON, `AttackHook` passes "Left Attack/Block" to the game (cast / block as vanilla does with a staff in the right hand);
   the right button stays swallowed (the gun). `InputSink` does not set `g_aimHeld` while ON, so ADS never starts; switching ON while aimed ends the aim
   at once (`ReleaseAim`, the walking speed given back exactly as today).
4. **Left arm**: while ON, `HideLeftArm` is skipped and `RestoreLeftArm` gives the bone its scale back; OFF hides it again.
5. **Gun and left hand at once**: nothing to do: the trigger path (`TickGun`) does not look at the left hand. Recoil keeps kicking the view while casting.
6. **Logs** (first N lines each): "left hand: ON/OFF by key (device, code); left hand holds <spell/shield/weapon/nothing> <id>", "left hand: left button
   passed to the game (cast/block)", "left hand: aim ended by the toggle", the event name the game gives the middle button (is it bound?).

## 4. Limits
- **Spells and shields only** are planned. A torch would also work through the same path (nothing to block); a one-handed weapon in the left hand
  with a staff in the right is not a vanilla combination and is NOT planned.
- **No shield bash**: a bash is "right attack while blocking", and the right button is the gun's trigger. Firing while blocking fires the gun.
- **No dual casting** (the right hand holds the gun).
- **No ADS while ON** (the user's choice). With the toggle ON and nothing in the left hand the left button goes to the game and probably does nothing
  with a staff in the right hand (UNCONFIRMED); a notice "left hand is empty" is shown once.
- **Player only.** NPCs' staff guns show in both hand slots (CLAUDE.md 0.33-0.35); giving NPCs a left item is a separate, riskier job.
- **Gamepad**: no default pad button (the ini can take a pad code later if wanted).
- **Third person**: the toggle works there too (left button, no ADS); the arm hiding is first-person only, as today.

## 5. Risks (UNCONFIRMED until the stage-1 log)
1. **Middle mouse may be bound by the game** (the user thinks it toggles the camera; vanilla PC binds "Toggle POV" to F, and whether the middle button
   has an action in the user's control map is not known). The stage-1 log names its event. If it is bound: first choice = unbind it in the game's
   Controls menu; fallback = the plugin swallows that one action while a gun is in hand (another handler hook = another vtable slot to get right on 1.7.104).
2. **Animations**: staff + spell and staff + shield are vanilla pairs, but our gun is held with the staff's right-arm animations plus our aimed-gun code;
   a left cast or block may move the right arm/gun in first person (the hip gun hangs on the arm animation). Judged by eye in stage 1.
3. **The left arm bone**: un-hiding mid-animation may pop; the old "arm flickers back" worry (0.35.0) applies in reverse.
4. **The game's charge meters**: the HUD hides `LeftChargeMeterAnim` while a gun is up (0.23.3). A spell or shield has no charge, so nothing is lost; an
   enchanted shield's charge would not show (shields have no charge in vanilla).
5. **Equip edge cases**: equipping a two-handed item or a staff into the left hand unequips the gun (engine rule): the gun mode then ends as today.
6. **The user's reported left-hand / weapon-switching issues** (not yet described): the toggle may fix them; the stage-1 logs should cover them (question 6.1).

## 6. Questions before stage 1
1. Which left-hand / weapon-switching issues did you see (what you did, what happened)? I will make stage 1 log exactly that.
2. Should the toggle's state be kept in the save (a load keeps ON/OFF), or start OFF after every load (proposed: OFF, the safe default)?
3. HUD: is a small "LEFT HAND" tag on the ammo HUD wanted while ON (proposed: yes), and a notice on each press (proposed: yes)?

## 7. Stages (one build each)
- **Stage 1** (plugin only, 1.37.0): sections 3.1-3.6; ini `LeftHand`, `LeftHandKey`, `LeftHandKeyboard` (new keys take defaults, no `IniVersion` bump).
  The user tests: toggle on/off, a spell (fire-and-forget and concentration) and a shield while firing, the left arm, ADS back after OFF, the middle button's
  own action, and the weapon-switching issues. Send `SkylandsNative.log`.
- **Stage 2** (after the report): fixes from the log (a middle-button hook if needed, animation/arm problems, the switching issues), and anything the user
  adds (torches, keeping the state in the save, a pad button).
