# Weapon slots (Borderlands 2 style): roadmap (APPROVED; stage 1 built as 0.62.0 / plugin 1.38.0)

Written after 0.61.3 (TestBuild-184, plugin 1.37.3 = "SkylandsNative 412").

## 1. The user's answers (interview)
| Question | Answer |
|---|---|
| Slots | **4**, picked by the player from their guns |
| Assigning | **Hold Left Alt, press 1-4** with the gun in hand; while Alt is held, 1-4 only pick a slot (Skyrim's favourites hotkeys 1-4 are blocked) |
| Scroll wheel | **Switches guns while a Skylands gun is drawn**; the camera zoom is blocked then. Sheathed, or anything else in hand: the wheel zooms as normal |
| Order | **Wraps** (4 -> 1, 1 -> 4) and **skips empty slots**; wheel down = next, up = previous |
| A slotted gun leaves the inventory | **The slot empties** (when next used; a notice and a log line). Slots are kept per character |
| Screen | **Notices only** ("Slot 2: <gun name>" on assigning, and the ammo HUD already shows the new gun's name in its rarity colour) |
| Swap speed | **The game's normal equip** (the draw animation plays); faster later if wanted |
| Who | the player (the Gunzerker's two guns stay for the class skills, later) |

Why: Borderlands 2 swaps weapons on the wheel, which speeds play up and frees the number keys for left-hand spells.

## 2. Method (all in the plugin; no record, no script, no Skylands.esp change)
1. **Slots**: `g_slots[4]` = base form ids of Skylands guns (the identity the magazines already use), co-save record `'SLOT'` (cleared on a new game, read on a
   load), so they are per character.
2. **Assigning**: `InputSink` tracks Left Alt (`SlotKey`, ini, default 56). While it is down and a gun is in the right hand, a press of 1-4 (`SlotKeys`, keyboard 2-5)
   puts that gun in the slot (taking it out of any other slot first: no gun in two slots), notice "Slot N: <name>", log line. The game must not ALSO run the
   favourites hotkey: the plugin hooks the favourites handler's button function (`FavoritesHandler::ProcessButton`, like the attack and ready-weapon hooks)
   and drops 1-4 while the slot key is held.
3. **Switching**: while gun mode is on and a gun is really in the hand (`g_gunInHand`), a wheel event (`Zoom In` = previous, `Zoom Out` = next) picks the next
   filled slot that still has its gun in the pack (else the slot empties: notice "Slot N: the gun is no longer with you") and equips it with
   `ActorEquipManager::EquipObject(player, gun, null, 1, RightHand slot)`. The gun script's own equip event then arms it as it does today (no Papyrus change).
   One switch at a time: further wheel ticks are ignored until the new gun is in hand or 600 ms have passed (a wheel notch sends several events).
4. **No zoom while a gun is drawn**: the wheel's camera zoom (and, in first person, the switch to third person on "Zoom Out") must be swallowed while switching. The
   zoom is processed by the camera's first- and third-person states (both are input handlers); the plugin hooks their button function and drops `Zoom In/Out`
   while `g_gunInHand`. Fallback if that hook cannot be placed safely: let the zoom through and put the camera straight back into first person
   (`PlayerCamera::ForceFirstPerson`), which may flicker.
5. **What carries over**: the magazine of the gun put away is kept (as today, per gun), a running reload is cancelled, the left hand and its toggle are untouched.
6. **Logs** (first N each): "slots: slot N = <id> \"name\"", "slots: wheel up/down: slot a -> b (<id>)", "slots: slot N emptied (the gun is gone)", "slots: zoom
   swallowed", "slots: favourites hotkey N blocked while the slot key is held", "slots: save/load - a b c d".

## 3. Limits
- Only Skylands guns go in slots (spells and Skyrim weapons keep the favourites keys, which is the point).
- The wheel switches only while a gun is drawn; to zoom the camera, sheathe the gun (or use Toggle POV).
- No slot display on screen in stage 1 (notices only).
- The swap plays Skyrim's equip/draw animation, so it is not instant.
- Keyboard/mouse only (no gamepad mapping in stage 1).

## 4. Risks (UNCONFIRMED until the stage-1 log)
1. **Hook slots**: the camera states' and the favourites handler's button functions sit in vtables whose slot number moved on 1.7.99+ for the attack handler
   (4 -> 6); the same shift is expected and logged at install ("... hooked (vtable slot N)"). A wrong slot would crash at the first wheel/number press: the
   stage-1 build installs each hook only after checking the function it replaces looks like the right one (logged), and has ini switches to turn each off.
2. **Left Alt**: some tools use Alt (Alt+Tab is Windows'); the key is changeable (`SlotKey`).
3. **Equip while busy**: equipping during a reload, a cast in the left hand or a menu may be refused or delayed by the game (logged: "equip asked, gun in hand
   after N ms / not after 600 ms").
4. **Gun mode flicker**: the script switches gun mode off and on during a swap (as when you swap by hand today); the plugin already copes, but the swallowed
   wheel/attack buttons in that gap are logged.

## 5. Stages (one build each)
- **Stage 1**: sections 2.1-2.6 (slots, assigning, switching, zoom block, co-save, logs). Ini `WeaponSlots=1`, `SlotKey=56`, `SlotHook*` switches.
- **Stage 2** (after your report): a small slot row on the HUD (next to the ammo display) if wanted, a faster swap, gamepad, and whatever stage 1 shows.

## 6. One question before stage 1
- While Left Alt is held, should a press of 1-4 on a slot that already holds the SAME gun clear that slot (a way to empty a slot), or leave it as it is?

## 7. Answer to section 6
Pressing a slot that already holds the same gun leaves it unchanged ("Slot N: <name> (already)").
