"""SKSE (the Skyrim Script Extender) as a dependency of Skylands: what the player's install has, and what Skylands adds.

Skylands guns need three things the player installs once, none of which Skylands may ship:
  * SKSE64, matching the Skyrim runtime (skse64_loader.exe and skse64_<major>_<minor>_<build>.dll next to SkyrimSE.exe);
  * Address Library for SKSE Plugins (Data/SKSE/Plugins/versionlib-*.bin; version-*.bin on 1.5.97), which every
    CommonLibSSE plugin, including SkylandsNative.dll, uses to find the game's functions on any runtime;
  * Skyrim started through skse64_loader.exe (Steam's Play button starts the game without SKSE).
Skylands installs its own plugin, Data/SKSE/Plugins/SkylandsNative.dll (built by .github/workflows/skse-plugin.yml).
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

PLUGIN_DLL = "SkylandsNative.dll"
PLUGIN_INI = "SkylandsNative.ini"
PLUGIN_REL = f"Data/SKSE/Plugins/{PLUGIN_DLL}"
SKSE_DOWNLOAD = "https://skse.silverlock.org/"
ADDRESS_LIBRARY = "https://www.nexusmods.com/skyrimspecialedition/mods/32444"
DEFAULT_INI = """; SkylandsNative settings
[Skylands]
; the version of this file's defaults: an install keeps the values you changed while this number is the same, and writes the new defaults (the old file is kept as .old) when it is not
IniVersion=5
; how far ahead (game units) the bullets are aimed to cross the crosshair
Convergence=3000
; a short glowing flash at the muzzle with every bullet (1 on, 0 off)
MuzzleFlash=1
; aiming down the sights (hold the block button): the share of the spread left when fully aimed (0.1 to 1)
AimSpread=0.5
; the share of the walking speed left when fully aimed (0.1 to 1)
AimWalk=0.7
; how quickly the aim comes up and goes down (whole aims a second, 1 to 30)
AimRate=7
; the gun moves to the middle of the screen while aimed (1 on, 0 off); where its muzzle sits: ahead of the eye, below it, to the right of it (game units)
AimCenter=1
; the aimed gun is placed from the player's position and angles of this frame (1) or the camera's (0)
AimPredict=1
; the reload key as a keyboard scan code (47 is V; 19 is R, which is also Ready Weapon: while a gun is in the hand it no longer puts the weapon away)
ReloadKey=47
; a mouse button as the reload key as well (3, 4, 5 ... are the side buttons; -1 none)
ReloadMouse=-1
; short ammo messages on the screen: reloading, magazine full, low ammo (1 on, 0 off)
AmmoText=1
; ammo: a player with none of a gun's ammo is given a first stock when the gun is first taken up in a run of the game (StartAmmo=0: none; the amounts are StartAmmo<Type> below)
StartAmmo=300
; ammo by type, sized by the gold value of a round (pistol 5, SMG 8, rifle 10, shotgun 10, sniper 15, rocket 50): the first stock, what a body carries of its own gun's ammo
; (min-max), the extra random kind some bodies carry (min-max), and what every merchant keeps in stock (topped up when you talk to them)
StartAmmoPistol=120
StartAmmoSMG=100
StartAmmoAR=80
StartAmmoShotgun=40
StartAmmoSniper=30
StartAmmoLauncher=6
AmmoDropPistol=12-28
AmmoDropSMG=10-24
AmmoDropAR=8-18
AmmoDropShotgun=5-12
AmmoDropSniper=3-8
AmmoDropLauncher=1-2
AmmoBonusPistol=6-14
AmmoBonusSMG=5-12
AmmoBonusAR=4-10
AmmoBonusShotgun=3-6
AmmoBonusSniper=2-4
AmmoBonusLauncher=1-1
; merchants (1 on): every vendor keeps this many rounds of each kind and ShopGear Skylands guns / shields / relics (new picks every ShopGearDays game days)
Shop=1
ShopAmmoPistol=100
ShopAmmoSMG=80
ShopAmmoAR=60
ShopAmmoShotgun=40
ShopAmmoSniper=30
ShopAmmoLauncher=6
ShopGear=3
ShopGearDays=2
; 1: when a merchant's restock is due, Skylands does it as you start talking (as the game would at the barter) so the restock does not wipe the Skylands stock
ShopReset=1
; 1: Skylands items in a merchant's chest are given that merchant's trade keyword, so the barter menu shows them (merchants only show what they deal in)
ShopKeywords=1
; the Borderlands-style display at the bottom right (1 on, 0 off: the plain messages come back); where its right edge and bottom line are, in a 1280 x 720 HUD
Hud=1
HudRight=70
HudBottom=80
AmmoDrops=1
AimForward=33
AimDown=6.5
AimRight=0
; recoil: degrees the view kicks up with a shot (0 = none), the most it drifts sideways, the share of the kick given back when the shooting stops, the kick's share while aimed, and how far (units) the aimed gun jerks back
RecoilPitch=0.55
RecoilYaw=0.22
RecoilRecover=0.6
RecoilAim=0.6
RecoilGun=1.0
; the arms are hidden while fully aimed (1 on, 0 off); shell casings out of the gun (1 on, 0 off)
HideHands=1
; the first-person left arm is hidden while a gun is held in the right hand (1 on, 0 off)
HideLeftHand=1
Casings=1
; a rocket leaves flame and smoke behind it, and its launcher a cloud of back-blast smoke (1 on, 0 off)
Rockets=1
; the aimed gun's sway (breathing, walking, a lag behind turns): 1 is the default, 0 none, 2 twice as much
Sway=1.0
; the Pandora bandits speak Borderlands 2's lines (1 on, 0 quiet; their Skyrim lines stay silenced either way). The lines are in SkylandsVoices.txt (the installer writes it).
Voices=1
; seconds between two lines of any bandits (a death may always speak), and between two pain lines of one bandit
VoiceGap=2.5
VoicePainGap=4
; a bandit fighting you taunts once in this many seconds, if it is within this many units
VoiceTauntMin=10
VoiceTauntMax=20
VoiceRange=4000
; Skylands drops lying on the ground (guns, shields, relics) go away once you are this many units from them (0 = never; about 4000 units is a
; cell's width). Commoner items go sooner. What you dropped yourself stays.
Despawn=1
DespawnCommon=3000
DespawnUncommon=4500
DespawnRare=7000
DespawnEpic=10000
DespawnLegendary=16000
DespawnEtech=16000
; rarity beams shown at once; past this the lowest rarity loses its beam first
BeamCap=24
"""


def exe_version(path: Path) -> tuple[int, int, int, int] | None:
    """The file version of a Windows executable, from the VS_FIXEDFILEINFO block of its version resource."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    sig = struct.pack("<I", 0xFEEF04BD)
    at = data.find(sig)
    while at != -1 and at + 16 <= len(data):
        struc_version, ms, ls = struct.unpack_from("<III", data, at + 4)
        if struc_version == 0x00010000:
            return ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF
        at = data.find(sig, at + 1)
    return None


@dataclass
class SkseStatus:
    runtime: tuple[int, int, int, int] | None = None
    loader: bool = False
    skse_dll: str | None = None  # the skse64_*.dll that matches the runtime
    skse_dlls: list[str] = field(default_factory=list)  # every skse64_*.dll found
    address_library: str | None = None
    plugin: bool = False  # SkylandsNative.dll in place

    @property
    def ready(self) -> bool:
        return self.loader and self.skse_dll is not None and self.address_library is not None


def status(skyrim: Path) -> SkseStatus:
    """What the player's Skyrim folder has of SKSE, Address Library and the Skylands plugin."""
    sky = Path(skyrim)
    st = SkseStatus()
    st.runtime = exe_version(sky / "SkyrimSE.exe")
    st.loader = (sky / "skse64_loader.exe").is_file()
    st.skse_dlls = sorted(f.name for f in sky.glob("skse64_*.dll"))
    if st.runtime:
        want = f"skse64_{st.runtime[0]}_{st.runtime[1]}_{st.runtime[2]}.dll".lower()
        st.skse_dll = next((n for n in st.skse_dlls if n.lower() == want), None)
    plugins = sky / "Data" / "SKSE" / "Plugins"
    if st.runtime:
        a, b, c, d = st.runtime
        names = [f"versionlib-{a}-{b}-{c}-{d}.bin", f"version-{a}-{b}-{c}-{d}.bin"]
        st.address_library = next((n for n in names if (plugins / n).is_file()), None)
    elif plugins.is_dir():  # the runtime could not be read: any Address Library file will do for the report
        st.address_library = next((f.name for f in plugins.glob("version*-*.bin")), None)
    st.plugin = (plugins / PLUGIN_DLL).is_file()
    return st


def describe(st: SkseStatus) -> list[str]:
    """Lines for the setup log: what is there, and exactly what to do about what is not."""
    rt = ".".join(map(str, st.runtime)) if st.runtime else "unknown (SkyrimSE.exe not readable)"
    out = [f"Skyrim runtime: {rt}"]
    out.append(f"SKSE loader (skse64_loader.exe): {'found' if st.loader else 'MISSING'}")
    if st.runtime:
        want = f"skse64_{st.runtime[0]}_{st.runtime[1]}_{st.runtime[2]}.dll"
        out.append(f"SKSE for this runtime ({want}): {'found' if st.skse_dll else 'MISSING' + (' (found for another version: ' + ', '.join(st.skse_dlls) + ')' if st.skse_dlls else '')}")
    out.append(f"Address Library (versionlib-*.bin in Data/SKSE/Plugins): {st.address_library or 'MISSING'}")
    if not st.ready:
        out.append("Skylands needs SKSE and Address Library for its guns (the staff gun does nothing without them). To add them:")
        if not (st.loader and st.skse_dll):
            out.append(f"  1. Download SKSE64 (the 'Current Anniversary Edition build' for Skyrim {rt}, 7z or installer) from {SKSE_DOWNLOAD}")
            out.append("     and copy skse64_loader.exe, the skse64_*.dll and the Data/Scripts folder into your Skyrim folder (next to SkyrimSE.exe).")
        if not st.address_library:
            out.append(f"  2. Download 'Address Library for SKSE Plugins' (All in one, the file for your runtime) from {ADDRESS_LIBRARY}")
            out.append("     and copy its Data/SKSE/Plugins/versionlib-*.bin file into your Skyrim's Data/SKSE/Plugins folder.")
        out.append("  3. Start Skyrim with skse64_loader.exe (not Steam's Play button, which starts it without SKSE).")
    return out


def _ini_values(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith((";", "[")) and "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def merge_ini(default: str, old: str | None) -> tuple[str, bool]:
    """The settings file to install: the defaults, with the values the player changed kept when the old file has the same IniVersion. Returns (text, kept)."""
    if not old:
        return default, False
    before, after = _ini_values(old), _ini_values(default)
    if before.get("IniVersion") != after.get("IniVersion"):
        return default, False
    lines = []
    # values put back to the defaults once when ShieldDefaultsRev changes (the testing values of 0.39.2 to 0.40.0: every person a shield, every shield dropped)
    reset = {"EnemyShieldPercent", "ShieldDropPercent"} if before.get("ShieldDefaultsRev") != after.get("ShieldDefaultsRev") else set()
    # the drop toss of 0.53.0 was too weak (items still in the bodies): its strengths are put back to the new defaults once when DropTossRev changes
    if before.get("DropTossRev") != after.get("DropTossRev"):
        reset |= {"DropTossUp", "DropTossOut"}
    for line in default.splitlines():
        key = line.partition("=")[0].strip()
        if "=" in line and not line.strip().startswith((";", "[")) and key in before and key != "IniVersion" and key not in reset:
            line = f"{key}={before[key]}"
        lines.append(line)
    return "\n".join(lines) + "\n", True


# shield settings come from the shields sheet; a value read from the player's Borderlands 2 files (extract.shield_stats) replaces the sheet's default
SHIELD_KEYS = {"delay_s": "ShieldDelay", "rate_fraction": "ShieldRate", "gate": "ShieldGate", "low_fraction": "ShieldLow",
               "test_shield_percent": "TestShield", "test_enemy_percent": "TestEnemyShields"}


def shield_ini(bl2_values: dict | None = None, slot: int = 0, relic_slot: int = 0) -> str:
    """The shield part of the settings file. bl2_values: {sheet row id: number read from Borderlands 2}."""
    from . import sheet_data as S

    bl2_values = bl2_values or {}
    lines = ["; shields (docs/shield-roadmap.md). Numbers come from the shields sheet, replaced by the values read from your Borderlands 2 files where they exist.",
             "; Shield=0 turns the feature off. TestShield / TestEnemyShields (stage 1 only): a shield of that percent of max health for you / for every other person nearby (0 = none)",
             "Shield=1"]
    for row_id, key in SHIELD_KEYS.items():
        row = S.SHIELDS[row_id]
        value = bl2_values.get(row_id, row.value)
        if slot and row_id in ("test_shield_percent", "test_enemy_percent"):
            value = 0  # with shield items the test shields are off (they would sit under the items' shields)
        lines.append(f"{key}={value:g}")
    if slot:
        lines += [
            "; shield items: the biped slot they are worn in (30-61; the installer picks one that nothing in your load order uses; change it here if another mod wants it, and reinstall)",
            f"ShieldSlot={slot}",
            "; who carries a shield: the chance (percent) for a person of level 1, and this much more for every level above 1 (at most 100). A boss (a named person, or ShieldBossLevel and higher) always has one, rare or better.",
            "; Each person is decided once by their own id, so a loaded game gives the same people shields.",
            "; (ShieldDefaultsRev: when it changes, the installer puts EnemyShieldPercent and ShieldDropPercent back to these values once, whatever your old file said)",
            "ShieldDefaultsRev=2",
            f"EnemyShieldPercent={S.SHIELDS['enemy_percent'].value:g}",
            "; a person who carries no Skylands gun (a melee fighter) has at least this chance instead (plus EnemyShieldPerLevel a level): tankier on the way to you",
            "EnemyShieldUnarmedPercent=60",
            f"EnemyShieldPerLevel={S.SHIELDS['enemy_percent_per_level'].value:g}",
            f"ShieldBossLevel={S.SHIELDS['boss_level'].value:g}",
            "; every shield's capacity is multiplied by this (1 = as built; 2 doubles every shield: handy for testing)",
            "ShieldCapacityScale=1",
            "; how often a dead person's shield stays on the body to be looted (percent); a boss always leaves its shield",
            f"ShieldDropPercent={S.SHIELDS['drop_percent'].value:g}",
            "; you are given one shield to start (1) or not (0)",
            "StarterShield=1",
        ]
    if relic_slot:
        lines += [
            "; relics: the biped slot they are worn in (like ShieldSlot, a different one), the chance (percent) that a person of level 1 carries one and this much more per level, and how often a dead person's is dropped on the ground",
            "Relics=1",
            f"RelicSlot={relic_slot}",
            "EnemyRelicPercent=8",
            "EnemyRelicPerLevel=1",
            "RelicDropPercent=100",
            "; how strong each relic effect is: 1.0 = Borderlands 2's numbers, 2.0 = double, 0 = off (the item text shows the 1.0 numbers)",
            "RelicHealth=1.0",
            "RelicShieldCapacity=1.0",
            "RelicShieldRecharge=1.0",
            "RelicMagazine=1.0",
            "RelicDamage=1.0",
            "RelicFireResist=1.0",
            "RelicShockResist=1.0",
            "RelicCorrosiveResist=1.0",
            "RelicExplosiveResist=1.0",
        ]
    lines += [
        "; the shield display over your health bar and the enemy's (upper half shield, lower half health). ShieldHud=0 turns it off (the plain lines come back).",
        "; ShieldHudMode=2 leaves the game's bars alone and puts a thin shield bar above them. ShieldHudEnemy=0 turns off the enemy's. ShieldHudFollow=0 ignores the game's fading of its bars.",
        "; Where the game's bars are is read from the game; if a bar sits wrong, move or size it in HUD pixels (1280 x 720): X/Y shift it, Width/Height set the size (0 = as found).",
        "; ShieldHudAlign: 0 fills from the middle (like the game's bars), 1 from the left, 2 from the right. ShieldHudLog=1 writes a line about the bars every 5 seconds.",
        "ShieldHud=1",
        "ShieldHudMode=2",
        "ShieldHudEnemy=1",
        "ShieldHudFollow=1",
        "ShieldHudAlign=0",
        "ShieldHudX=0",
        "ShieldHudY=0",
        "ShieldHudWidth=0",
        "ShieldHudHeight=0",
        "ShieldHudEnemyX=0",
        "ShieldHudEnemyY=0",
        "ShieldHudEnemyWidth=0",
        "ShieldHudEnemyHeight=0",
        "ShieldHudLog=0",
        "; your shield bar is shown while you are in combat, while the shield is not full, and for this many seconds after the shield or your health last changed, then it fades out (0 = always shown)",
        "ShieldHudHideAfter=3",
        "; an enemy with a shield can be wrapped in a soft blue glow that bursts when the shield breaks (ShieldGlow=1: on; ShieldGlowRange: how near, in game units). Off for now.",
        "ShieldGlow=0",
        "ShieldGlowRange=2200",
        "; ShieldHudHealth=1 (with mode 2): the game's own health bar shows health and shield added together, so it drops when the shield takes a hit; this paints the inside of it with your real health alone",
        "; (ShieldHudInsetX/Y: the share of the bar's width / height that is frame and caps, left alone). Off by default: it is a guess at the bar's insides.",
        "ShieldHudHealth=0",
        "ShieldHudInsetX=0.09",
        "ShieldHudInsetY=0.28",
    ]
    return "\n".join(lines) + "\n"


def badass_ini() -> str:
    """The Badass block (docs/badass-roadmap.md 3.1, 3.2): numbers from sheets/badass_tiers.json."""
    from .sheet_data import BADASS_TIERS as T
    from .sheet_data import ENEMY_DROPS as D
    from .sheet_data import GENERATION

    G = GENERATION["main"]

    b, s, u = T["badass"], T["super"], T["ultimate"]
    def num(v: float) -> str:
        return f"{v:g}"
    return "\n".join([
        "; Badass enemies (stage 1: tiers and stats; names, size and drops come later). Every hostile actor near you is rolled once: p = BadassPercent + BadassPerLevel",
        "; per player level above 1, at most BadassMax percent (bosses and dragons x BadassBossOdds). A hit makes a Badass; from player level BadassSuperGate a second hit",
        "; of p makes it a Super Badass, from BadassUltimateGate a third an Ultimate Badass. BadassTest=N (percent) replaces p for every roll and ignores the gates: for testing.",
        "Badass=1",
        f"BadassPercent={num(b.percent)}",
        f"BadassPerLevel={num(b.per_level)}",
        f"BadassMax={num(b.max_percent)}",
        f"BadassBossOdds={num(b.boss_odds)}",
        f"BadassSuperGate={s.player_level_gate}",
        f"BadassUltimateGate={u.player_level_gate}",
        "BadassTest=0",
        f"BadassMaxNear={b.max_near}",
        f"BadassMaxSuper={s.max_near}",
        f"BadassMaxUltimate={u.max_near}",
        "; stats by tier (1 Badass, 2 Super, 3 Ultimate): maximum health, melee/creature damage, speed; BadassGun = the bullets the plugin launches for them",
        *(f"BadassHealth{i}={num(r.health_mult)}" for i, r in ((1, b), (2, s), (3, u))),
        *(f"BadassMelee{i}={num(r.melee_damage_mult)}" for i, r in ((1, b), (2, s), (3, u))),
        *(f"BadassSpeed{i}={num(r.speed_mult)}" for i, r in ((1, b), (2, s), (3, u))),
        f"BadassGun={num(b.gun_damage_mult)}",
        "; the tier's name before the enemy's own (\"Badass Forsworn\") and a bigger body (BadassSize1..3 = scale)",
        "BadassNames=1",
        "BadassSize=1",
        *(f"BadassSize{i}={num(r.size_mult)}" for i, r in ((1, b), (2, s), (3, u))),
        "; creatures (not people): BadassCreatureSize more scale per tier (0.15: a Super Badass creature is 1.30 + 0.30 = 1.60 times its own size);",
        "; their own health counts as at least BadassCreatureHealth + BadassCreatureHealthPerLevel x your level before the tier multiplies it,",
        "; and their melee damage is x(1 + BadassCreatureGap per level they are below you), at most BadassCreatureGapMax",
        "BadassCreatureSize=0.15",
        "BadassCreatureHealth=20",
        "BadassCreatureHealthPerLevel=5",
        "BadassCreatureGap=0.05",
        "BadassCreatureGapMax=3",
        "; guaranteed drops when a Badass dies (BL2: 1 / 2 / 3 items, at least uncommon / rare / epic, each item's rarities moved up to its own floor); what each item is, by weight",
        "BadassDrops=1",
        f"BadassDropGun={num(D['gun_weight'].value)}",
        f"BadassDropShield={num(D['shield_weight'].value)}",
        f"BadassDropRelic={num(D['relic_weight'].value)}",
        "; creature drops: a creature that dies hostile to you drops one item with (its class's drop scale, sheets/enemy_stats.json; else CreatureDropScale) x a person's",
        "; chance at its level (a gun CreatureGunPercent + shield carry x ShieldDropPercent + relic carry x RelicDropPercent), at most CreatureDropCap percent;",
        "; DragonBoss=1: dragons always drop two items, rare or better",
        "; items an enemy drops (guns, shields, relics, a Badass's items) get a small kick so they land around the body, not inside it: units per second up and sideways (DropToss=0: off)",
        "; (DropTossRev: when it changes, the installer puts DropTossUp and DropTossOut back to these values once)",
        "DropTossRev=2",
        "DropToss=1",
        "DropTossUp=420",
        "DropTossOut=150",
        "CreatureDrops=1",
        f"CreatureDropScale={num(D['creature_drop_scale'].value)}",
        f"CreatureDropCap={num(D['creature_drop_cap'].value)}",
        f"CreatureGunPercent={G.drop_chance}",
        "DragonBoss=1",
    ]) + "\n"


def progression_ini() -> str:
    """The kill XP block (docs/progression-roadmap.md 3.1): numbers from sheets/progression.json (Borderlands 2's tier multipliers, the user's pace)."""
    from .sheet_data import PROGRESSION as P

    lines = ["; Character progression, stage 1: kills with a Skylands gun give character XP (your level meter). One regular kill of your own level gives",
             "; 1/KillXPKillsPerLevel of a level; higher-level enemies give more, lower ones much less (Borderlands 2: 6+ levels below you = 1 %).",
             "; Badass / Super / Ultimate / boss multipliers are Borderlands 2's; one kill gives at most KillXPMaxShare of a level.",
             "; Weapon proficiencies (Prof...): your bullets' damage on living enemies raises the gun's type and maker tracks; their levels raise that gun's stats."]
    for row in P.values():
        lines.append(f"; {row.note}")
        lines.append(f"{row.id}={row.value:g}")
    return "\n".join(lines) + "\n"


def default_ini(bl2_values: dict | None = None, slot: int = 0, relic_slot: int = 0) -> str:
    return DEFAULT_INI.rstrip("\n") + "\n" + badass_ini() + progression_ini() + shield_ini(bl2_values, slot, relic_slot)


def stage_plugin(stage: Path, bin_dir: Path, existing_ini: Path | None = None, bl2_shields: dict | None = None, shield_slot: int = 0, relic_slot: int = 0) -> str | None:
    """Put the Skylands plugin (if the build has it) and its settings in the stage folder, so they install and uninstall with the rest. The player's values in an
    installed settings file of the same IniVersion are kept; a file of another version is kept next to the new one as .old."""
    dll = Path(bin_dir) / PLUGIN_DLL
    if not dll.is_file():
        return None
    dest = Path(stage) / "Data" / "SKSE" / "Plugins"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / PLUGIN_DLL).write_bytes(dll.read_bytes())
    old = None
    if existing_ini is not None and Path(existing_ini).is_file():
        try:
            old = Path(existing_ini).read_text(encoding="utf-8", errors="replace")
        except OSError:
            old = None
    text, kept = merge_ini(default_ini(bl2_shields, shield_slot, relic_slot), old)
    (dest / PLUGIN_INI).write_text(text, encoding="utf-8")
    if old and not kept:
        (dest / (PLUGIN_INI + ".old")).write_text(old, encoding="utf-8")
    return f"Data/SKSE/Plugins/{PLUGIN_DLL}"


def parse_version(text: str) -> tuple[int, ...] | None:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?", text)
    return tuple(int(g) for g in m.groups() if g is not None) if m else None
