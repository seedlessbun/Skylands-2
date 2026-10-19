# Borderlands 2 enemy and player models in Skyrim: feasibility

Written 2026-10-19 after the gun model work. Nothing here is built. The short version: it can be done for humanoid
characters as worn armour, but it is a larger and riskier job than guns and needs real-data feedback first.

## What would be built
Skyrim draws every humanoid from its own skeleton (`skeleton.nif`, ~100 named bones) and a body/head/hands/feet set from
the race; animations move that skeleton. So a Borderlands character cannot be dropped in as its own skeleton or animations.
The workable route is **skinned armour**: convert a BL2 skeletal mesh into a Skyrim armour NIF skinned to Skyrim's bones, give
it an ARMO/ARMA record in the body slot, and equip it on the player (vault hunter outfits) or in an outfit on the Pandora
enemies (psychos, marauders, bandits).

## Steps, and how risky each is
1. **Read the mesh with bone weights.** Our native scavenger finds positions, triangles and UVs but not the packed bone
   indices/weights or the reference skeleton. UModel exports both (PSK `REFSKELT`, `RAWWEIGHTS`), so this needs the UModel
   method. Risk: medium (UModel must support the BL2 files on the player's PC; the gun work will show that).
2. **Retarget the skeleton.** BL2 bones are named for its own rig; they must be mapped to Skyrim bones (spine, limbs, hands,
   head). Name matching is a guess; matching by bind-pose position (nearest Skyrim bone to each BL2 bone) is more robust.
   Proportions differ (BL2 characters are stylised: big heads/hands), so a straight transfer deforms oddly in motion.
   Risk: high for quality, low for "something appears".
3. **Write a Skyrim SE skinned NIF.** `BSTriShape` with `BSSkin::Instance`/`BoneData` (or the dismember instance and skin
   partitions the engine expects for body armour), per-vertex weights (up to 4 bones), bone transforms. nifly can load and
   re-save such files, so it is a good checker. Risk: medium; this is a lot of binary layout to get exactly right blind.
4. **Records.** ARMO + ARMA per outfit, assigned to the player or to enemy outfits (OTFT/leveled item), body slot 32 plus
   hands/feet. Hiding the vanilla body parts the armour replaces (slot flags). Risk: low.
5. **Heads and faces.** Skyrim faces are FaceGen morphs on a race head; a BL2 head cannot be morphed, so it must be a helmet-
   style armour piece over a hidden vanilla head. Risk: medium (clipping, hair, neck seams).
6. **Textures.** BL2 diffuse maps (DXT) work as is; normal maps use a different channel layout than Skyrim's and need
   conversion; specular and "cube" maps do not map across. Risk: low.
7. **Non-humanoid enemies (skags, rakk, stalkers, bosses).** They have their own rigs and animation sets; Skyrim has no
   matching skeleton. Out of scope without new creature races and behaviour graphs. Risk: very high.

## Roadblocks (why I stopped here, as asked)
- It depends on the gun work proving that real BL2 meshes can be read at all on the player's machine (native or UModel).
- Rig mismatch means poor deformation until someone looks at it in game and tunes bone mapping; I cannot see results.
- Vault hunter heads, weapons-in-hand poses and the first-person view would all need separate handling.
- Non-humanoid enemies cannot be done with armour.

## What I would do next, in order, once the gun survey comes back
1. Run `Run-GunModelSurvey.bat` (it now also lists which packages hold character `SkeletalMesh`es and `AnimSet`s).
2. If the UModel method works: export one psycho and one vault hunter body mesh, map bones by position, write one test armour
   and put it on the player. That single result shows how bad deformation is before building outfits for everyone.
3. Then outfits for the humanoid enemy classes, then vault hunter armour, then helmets/heads.
