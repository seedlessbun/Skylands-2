"""Skylands in the running game: Borderlands 2 hooks, the shout, menus and saving.

Every hook, number and text comes from sheet_data (generated from sheets/*.json).
Each feature writes one "first success" line to unrealsdk.log so a playtest can be checked
from the log (Binaries/Win32/Plugins/unrealsdk.log).
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
from pathlib import Path
from typing import Any

import unrealsdk
from mods_base import SETTINGS_DIR, build_mod, get_pc, hook, keybind
from save_options import HiddenSaveOption, register_save_options
from ui_utils import OptionBox, OptionBoxButton, TrainingBox, show_hud_message
from unrealsdk import logging
from unrealsdk.hooks import Block, Type, prevent_hooking_direct_calls

from . import sheet_data as S
from .progression import Event, Rules
from .skyrim import data as skyrim_data

T = {k: v.value for k, v in S.TUNING.items()}
SKILL_BY_EDID = {row.avif_edid: row for row in S.SKILLS.values()}
SKYRIM_ENV = "SKYLANDS_SKYRIM_DIR"
CACHE_FILE = Path(SETTINGS_DIR) / "skylands_skyrim_cache.json"
PATHS_FILE = Path(os.environ.get("LOCALAPPDATA", ".")) / "Skylands" / "skylands.env"  # Melty writes it before Play

# ---- runtime state (never saved into game objects) --------------------------------------------
RULES: Rules | None = None
LOAD_ERROR = ""
STATE: dict[str, Any] = {}
progress = HiddenSaveOption("progress", {})

_clock = 0.0
_shout_ready_at = 0.0
_shout_was_ready = True
_messages: list[tuple[str, str]] = []
_next_message_at = 0.0
_opening_due_at: float | None = None
_no_skyrim_shown = False
_opening_shown = False
_first_ok: set[str] = set()
_last = {"money": None, "shield": None, "injured": False, "scan_at": 0.0, "enemy_near": False}
_vendor_money: dict[str, int] = {}
_opened: set[int] = set()
_heal_acc = 0.0
_own_heal = False
_speed: dict[str, float] = {}
_status: dict[int, tuple[float, float]] = {}
_shield_full_after_hit = True


def ok_once(feature: str, detail: str = "") -> None:
    if feature not in _first_ok:
        _first_ok.add(feature)
        logging.info(f"[Skylands] {feature} works {detail}".rstrip())


# ---- finding and loading Skyrim ---------------------------------------------------------------
def _from_env_file() -> str:
    try:
        for line in PATHS_FILE.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == SKYRIM_ENV and value.strip():
                return value.strip().strip('"')
    except OSError:
        pass
    return ""


def _from_steam(game_root: Path) -> str:
    candidates = [game_root.parent / "Skyrim Special Edition"]
    steamapps = game_root.parent.parent
    for vdf in (steamapps / "libraryfolders.vdf", steamapps.parent / "config" / "libraryfolders.vdf"):
        try:
            for path in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore")):
                candidates.append(Path(path.replace("\\\\", "\\")) / "steamapps" / "common" / "Skyrim Special Edition")
        except OSError:
            continue
    for c in candidates:
        if (c / "Data" / "Skyrim.esm").is_file():
            return str(c)
    return ""


def find_skyrim() -> str:
    game_root = Path(__file__).resolve().parents[2]  # <BL2>/sdk_mods/skylands/game.py
    return os.environ.get(SKYRIM_ENV, "") or _from_env_file() or _from_steam(game_root)


def _load_skyrim() -> None:
    global RULES, LOAD_ERROR
    folder = find_skyrim()
    if not folder:
        LOAD_ERROR = "Skyrim Special Edition was not found. Start Skylands from Melty, which tells it where Skyrim is."
        logging.warning(f"[Skylands] {LOAD_ERROR}")
        return
    try:
        data = skyrim_data.load(Path(folder), CACHE_FILE)
        rules = Rules(data)
        if rules.missing_skills or not data.get("shout") or not data.get("races"):
            raise skyrim_data.SkyrimNotFound(
                f"Skyrim data incomplete: skills missing {rules.missing_skills}, shout {bool(data.get('shout'))}, "
                f"races {len(data.get('races', []))}"
            )
        if rules.missing_formulas:
            logging.warning(f"[Skylands] using sheet fallbacks for {rules.missing_formulas}")
        RULES = rules
        ok_once("skyrim_load", f"from {folder}: {len(data['skills'])} skills, {len(data['perks'])} perks, "
                f"{len(data['races'])} races, language {data['language']}")
    except Exception as e:  # noqa: BLE001 - report anything to the player and the log
        LOAD_ERROR = f"Could not read Skyrim at {folder}: {e}"
        logging.error(f"[Skylands] {LOAD_ERROR}")


def start_loading() -> None:
    threading.Thread(target=_load_skyrim, name="skylands-skyrim", daemon=True).start()


# ---- helpers ----------------------------------------------------------------------------------
def addr(obj: Any) -> int:
    return obj._get_address() if obj is not None else 0


def my_pawn() -> Any:
    pc = get_pc(possibly_loading=True)
    return None if pc is None else pc.Pawn


def is_me(controller: Any) -> bool:
    pc = get_pc(possibly_loading=True)
    return pc is not None and controller is not None and addr(controller) == addr(pc)


def notify(title: str, msg: str = "") -> None:
    _messages.append((title, msg))


def skill_name(edid: str) -> str:
    return RULES.skyrim["skills"][edid]["name"] if RULES else edid


def apply_events(events: list[Event]) -> None:
    for e in events:
        if e.kind == "skill_up":
            notify(f"{skill_name(e.skill)} increased to {e.value}")
            ok_once("skill_up", e.skill)
        elif e.kind == "level_up":
            notify(f"You have reached level {e.value}", "Perk point available. Press the skills key to spend it.")
            play_sound(S.SOUNDS["s_level_up"].object)
        elif e.kind == "word_learned":
            w = RULES.skyrim["shout"]["words"][e.value - 1]
            notify("Word of Power learned", f"{w['name']} - {w['translation']}")


def use(skill_id: str, units: float = 1.0) -> None:
    if RULES is not None and STATE.get("race"):
        apply_events(RULES.add_use(STATE, skill_id, units))


def mag(skill_id: str) -> float:
    return RULES.magnitude(STATE, skill_id) / 100.0 if RULES is not None and STATE.get("race") else 0.0


def play_sound(path: str) -> None:
    pawn = my_pawn()
    if pawn is None:
        return
    try:
        pawn.PlayAkEvent(InSoundCue=unrealsdk.find_object("AkEvent", path))
    except Exception:  # noqa: BLE001 - the event may not be loaded on this map
        pass


def type_in(dmg_type: Any, column: str) -> bool:
    if column == "*":
        return True
    return dmg_type is not None and dmg_type.Name in column.split(",")


def held_weapon_is_elemental() -> bool:
    pawn = my_pawn()
    weapon = None if pawn is None else pawn.Weapon
    if weapon is None:
        return False
    part = weapon.DefinitionData.ElementalPartDefinition
    return part is not None and not part.Name.endswith("_None")


def pawns_near(origin: Any, radius: float) -> list[Any]:
    """Live hostile pawns within radius; collected first, acted on later (freeze guard)."""
    pc = get_pc(possibly_loading=True)
    me = my_pawn()
    if pc is None or me is None:
        return []
    out, seen = [], set()
    p = pc.WorldInfo.PawnList
    steps = 0
    while p is not None and steps < int(T["t_pawn_walk_limit"]):
        steps += 1
        a = addr(p)
        if a in seen:
            break
        seen.add(a)
        nxt = p.NextPawn
        try:
            if a != addr(me) and p.IsAliveAndWell() and me.IsEnemy(p):
                dx, dy, dz = p.Location.X - origin.X, p.Location.Y - origin.Y, p.Location.Z - origin.Z
                if dx * dx + dy * dy + dz * dz <= radius * radius:
                    out.append(p)
        except Exception:  # noqa: BLE001 - odd pawns (vehicles, turrets) may not answer
            pass
        p = nxt
    return out


def vec(x: float, y: float, z: float) -> Any:
    return unrealsdk.make_struct("Vector", X=x, Y=y, Z=z)


def bullet_class() -> Any:
    return unrealsdk.find_class("WillowDmgSource_Bullet")


# ---- the shout --------------------------------------------------------------------------------
def shout() -> None:
    global _shout_ready_at, _shout_was_ready
    if RULES is None or not STATE.get("race"):
        notify("The Voice is silent", LOAD_ERROR or "Choose your race first.")
        return
    pc, pawn = get_pc(), my_pawn()
    if pawn is None or pawn.IsInjured():
        return
    if _clock < _shout_ready_at:
        notify(RULES.skyrim["shout"]["name"], f"Ready in {math.ceil(_shout_ready_at - _clock)} s")
        return
    words = RULES.words_known(STATE)
    row = next(r for r in S.SHOUT.values() if r.words == words)

    yaw = pc.Rotation.Yaw * math.tau / 65536
    pitch = pc.Rotation.Pitch % 65536
    pitch = (pitch - 65536 if pitch > 32768 else pitch) * math.tau / 65536
    fwd = (math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), math.sin(pitch))
    cone = math.cos(math.radians(row.cone_deg))
    origin = pawn.Location

    targets = []
    for p in pawns_near(origin, row.range_uu):
        d = (p.Location.X - origin.X, p.Location.Y - origin.Y, p.Location.Z - origin.Z)
        dist = math.sqrt(sum(c * c for c in d)) or 1.0
        if sum(f * c for f, c in zip(fwd, d, strict=True)) / dist >= cone:
            targets.append((p, d))

    cap = pawn.GetMaxHealth() * float(T["t_shout_damage_cap"])
    hit = 0
    for p, d in targets:
        flat = math.hypot(d[0], d[1]) or 1.0
        push = vec(d[0] / flat * row.push_speed, d[1] / flat * row.push_speed, row.lift_speed)
        dmg = min(cap, p.GetMaxHealth() * row.damage_frac)
        try:
            with prevent_hooking_direct_calls():
                p.TakeDamage(Damage=dmg, InstigatedBy=pc, HitLocation=p.Location, Momentum=push,
                             DamageType=bullet_class(), HitInfo=unrealsdk.make_struct("TraceHitInfo"),
                             DamageCauser=pawn)
            if p.IsAliveAndWell():
                p.AddVelocity(NewVelocity=push, HitLocation=p.Location, DamageType=bullet_class(),
                              HitInfo=unrealsdk.make_struct("TraceHitInfo"))
            hit += 1
        except Exception as e:  # noqa: BLE001
            logging.warning(f"[Skylands] shout could not push {p.Name}: {e}")

    try:
        pc.ClientPlayCameraAnim(AnimToPlay=unrealsdk.find_object("CameraAnim", row.camera_anim), Scale=1.0,
                                Rate=1.0, BlendInTime=0.05, BlendOutTime=0.4)
    except Exception:  # noqa: BLE001
        pass
    play_sound(S.SOUNDS["s_shout"].object)
    names = " ".join(w["name"].upper() for w in RULES.skyrim["shout"]["words"][:words])
    notify(f"{names}!", f"{RULES.skyrim['shout']['name']}: {hit} pushed back")
    _shout_ready_at = _clock + RULES.shout_cooldown(words)
    _shout_was_ready = False
    ok_once("shout", f"{words} words, {hit} enemies")


# ---- menus ------------------------------------------------------------------------------------
def race_name() -> str:
    for r in RULES.skyrim["races"]:
        if r["edid"] == STATE.get("race"):
            return r["name"]
    return ""


def boosts_text(race: dict) -> str:
    by_index = {str(row.av_index): row.avif_edid for row in S.SKILLS.values()}
    parts = [f"{skill_name(by_index[a])} +{b}" for a, b in race["boosts"].items() if a in by_index]
    return ", ".join(parts)


def show_skills_menu() -> None:
    if RULES is None:
        TrainingBox(title="Skyrim not found", message=LOAD_ERROR or "Still reading Skyrim, try again in a moment.").show()
        return
    if not STATE.get("race"):
        show_race_menu()
        return
    need = RULES.char_xp_needed(STATE["level"])
    buttons, by_button = [], {}
    for school in ("combat", "stealth", "magic"):
        for row in S.SKILLS.values():
            if row.school != school:
                continue
            e = row.avif_edid
            sk = STATE["skills"][e]
            pct = 100 if sk["level"] >= RULES.max_skill else int(100 * sk["xp"] / RULES.skill_xp_needed(e, sk["level"]))
            info = RULES.skyrim["skills"][e]
            label = f"{info['name']}  {sk['level']}"
            by_button[label] = e
            buttons.append(OptionBoxButton(
                label, f"{info['desc']}\n\nOn Pandora: {RULES.pandora_text(STATE, row.id)}\nNext level: {pct}%",
            ))
    box = OptionBox(
        title=f"{race_name()} - Level {STATE['level']} - Perk points: {STATE['points']}",
        message=f"Level progress: {int(100 * STATE['char_xp'] / need)}%",
        buttons=buttons,
        on_select=lambda _b, button: show_perk_menu(by_button[button.name]),
    )
    box.show()
    ok_once("skills_menu")


def show_perk_menu(edid: str) -> None:
    tree = RULES.tree(edid)
    buttons, nodes = [], {}
    for node in tree:
        have = RULES.node_owned_ranks(STATE, node)
        status, req = RULES.node_status(STATE, edid, node)
        perk = RULES.skyrim["perks"][str(node["ranks"][min(have, len(node["ranks"]) - 1)])]
        mark = {"maxed": "*", "available": "+", "no_points": " ", "locked_skill": "-", "locked_parent": "-"}[status]
        label = f"{mark} {perk['name']}  {have}/{len(node['ranks'])}"
        why = {
            "maxed": "Taken.",
            "available": "Press to take this perk.",
            "no_points": "Needs a perk point (gain a level).",
            "locked_skill": f"Needs {skill_name(edid)} {req}.",
            "locked_parent": "Take a perk that leads here first.",
        }[status]
        buttons.append(OptionBoxButton(label, f"{perk['desc']}\n\n{why}"))
        nodes[label] = node
    back = OptionBoxButton("Back")
    sk = STATE["skills"][edid]
    row = SKILL_BY_EDID[edid]

    def on_select(_box: OptionBox, button: OptionBoxButton) -> None:
        if button.name == "Back":
            show_skills_menu()
            return
        taken = RULES.take_perk(STATE, edid, nodes[button.name])
        if taken is not None:
            notify("Perk learned", RULES.skyrim["perks"][str(taken)]["name"])
            ok_once("perk_taken", str(taken))
        show_perk_menu(edid)

    OptionBox(
        title=f"{skill_name(edid)} {sk['level']} - Perk points: {STATE['points']}",
        message=f"On Pandora: {RULES.pandora_text(STATE, row.id)}",
        buttons=[*buttons, back],
        on_select=on_select,
        on_cancel=lambda _b: show_skills_menu(),
    ).show()


def show_race_menu() -> None:
    normalize_state()
    races = RULES.skyrim["races"]
    buttons = [OptionBoxButton(r["name"], f"{r['desc']}\n\n{boosts_text(r)}") for r in races]
    by_name = {r["name"]: r for r in races}

    def on_select(_box: OptionBox, button: OptionBoxButton) -> None:
        race = by_name[button.name]
        RULES.choose_race(STATE, race["edid"])
        w = RULES.skyrim["shout"]["words"][0]
        notify(f"You are a {race['name']}", f"Word of Power: {w['name']} - {w['translation']}. Shout with the action skill key.")
        _save_now()
        ok_once("race_chosen", race["edid"])

    OptionBox(title="Choose your race", message="Who are you?", buttons=buttons, on_select=on_select,
              prevent_cancelling=True).show()


def show_opening() -> None:
    greeting = RULES.skyrim.get("greeting") or "Hey, you. You're finally awake."
    parts = greeting.split(". ", 1)
    title = parts[0] + "."
    rest = parts[1] if len(parts) > 1 else ""
    TrainingBox(
        title=title,
        message=f"{rest}\n\nThis isn't Skyrim. It's Pandora, Dragonborn.\n\nThe Borderlands class skills are sealed. "
                "Your Skyrim skills grow as you fight, sneak, trade and survive.",
        pauses_game=True,
        on_exit=lambda _b: show_race_menu(),
    ).show()
    ok_once("opening")


# ---- saving -----------------------------------------------------------------------------------
def _save_now() -> None:
    progress.value = json.loads(json.dumps(STATE))
    try:
        from save_options.options import trigger_save
        trigger_save()
    except Exception:  # noqa: BLE001 - the regular autosave still picks it up
        pass


def on_save() -> None:
    progress.value = json.loads(json.dumps(STATE))


def normalize_state() -> None:
    """Fill in anything missing from a character's progress (old saves, or loaded before Skyrim was read)."""
    if RULES is None:
        return
    for key, value in RULES.new_state().items():
        STATE.setdefault(key, value)
    if STATE["race"]:
        for e in RULES.skill_by_edid:
            STATE["skills"].setdefault(e, {"level": RULES.start, "xp": 0.0})


def on_load() -> None:
    global _opening_shown
    loaded = progress.value if isinstance(progress.value, dict) else {}
    STATE.clear()
    STATE.update(json.loads(json.dumps(loaded)) if loaded else {})
    normalize_state()
    _opening_shown = False  # the tick schedules the greeting if this character has no race yet
    ok_once("save_load", f"race={STATE.get('race') or 'none'}")


# ---- hooks ------------------------------------------------------------------------------------
H = S.HOOKS


@hook(H["h_action_skill"].function)
def block_action_skill(*_: Any) -> type[Block]:
    shout()
    return Block


@hook(H["h_upgrade_skill"].function)
def block_class_skills(*_: Any) -> type[Block]:
    notify("Class skills are sealed", "Spend Skyrim perk points in the skills menu instead.")
    return Block


@hook(H["h_skills_menu"].function)
def skills_tab(*_: Any) -> type[Block]:
    show_skills_menu()
    return Block


@hook(H["h_possess"].function, Type.POST)
def on_possess(*_: Any) -> None:
    global _opening_due_at
    _last.update(money=None, shield=None, injured=False)
    _opened.clear()
    _speed.clear()
    _status.clear()
    _opening_due_at = _clock + float(T["t_opening_delay_s"])
    ok_once("possess")


@hook(H["h_new_game"].function, Type.POST)
def on_new_game(*_: Any) -> None:
    global _opening_due_at, _opening_shown
    _opening_shown = False
    _opening_due_at = _clock + float(T["t_opening_delay_s"])
    ok_once("new_game")


@hook(H["h_enemy_damage"].function)
def enemy_damage(obj: Any, args: Any, _ret: Any, func: Any) -> Any:
    if RULES is None or not STATE.get("race") or not is_me(args.InstigatedBy):
        return None
    dtype = args.DamageType
    elemental = held_weapon_is_elemental()
    pawn = my_pawn()
    injured = pawn is not None and pawn.IsInjured()
    mult = 1.0
    for row in S.SKILLS.values():
        eff = S.EFFECTS[row.effect]
        if eff.kind != "damage_out" or not type_in(dtype, eff.damage_types):
            continue
        if row.id == "destruction" and not elemental:
            continue
        if row.id == "illusion" and not injured:
            continue
        mult *= 1.0 + mag(row.id)
    # Skill uses (xp_sources): one per hit.
    for row in S.SKILLS.values():
        src = S.XP_SOURCES[row.xp_source]
        if src.hook == "h_enemy_damage" and src.damage_types != "-" and type_in(dtype, src.damage_types):
            if row.id == "destruction" and not elemental:
                continue
            use(row.id)
    args.Damage = args.Damage * mult
    with prevent_hooking_direct_calls():
        func(args)
    # Critical hits: Sneak XP and bonus (read after the game decided it was a crit).
    try:
        if obj.bWasLastDamageACriticalHit:
            use("sneak")
            bonus = mag("sneak")
            melee = dtype is not None and "Melee" in dtype.Name
            if bonus > 0 and not melee and obj.IsAliveAndWell():
                args.Damage = args.Damage * bonus
                with prevent_hooking_direct_calls():
                    func(args)
                ok_once("crit_bonus")
    except Exception as e:  # noqa: BLE001
        logging.warning(f"[Skylands] crit check failed: {e}")
    ok_once("damage_out", f"x{mult:.2f}")
    return Block


@hook(H["h_player_damage"].function)
def player_damage(obj: Any, args: Any, _ret: Any, func: Any) -> Any:
    global _shield_full_after_hit
    pawn = my_pawn()
    if RULES is None or not STATE.get("race") or pawn is None or addr(obj) != addr(pawn):
        return None
    shield_up = obj.GetShieldStrength() > 0
    _shield_full_after_hit = False
    if shield_up:
        use("block")
        cut = mag("block")
    else:
        use("heavy_armor")
        cut = mag("heavy_armor")
    if cut <= 0:
        return None
    args.Damage = args.Damage * (1.0 - cut)
    with prevent_hooking_direct_calls():
        func(args)
    ok_once("damage_in", f"-{cut:.0%}")
    return Block


@hook(H["h_heal"].function)
def on_heal(obj: Any, args: Any, *_: Any) -> None:
    pawn = my_pawn()
    if _own_heal or pawn is None or addr(obj) != addr(pawn) or args.bIsShieldRestore:
        return
    if args.Amount >= pawn.GetMaxHealth() * float(T["t_heal_min_frac"]):
        use("restoration")


def _money() -> int | None:
    pc = get_pc(possibly_loading=True)
    try:
        return int(pc.PlayerReplicationInfo.GetCurrencyOnHand(0))
    except Exception:  # noqa: BLE001
        return None


def _add_money(amount: int) -> None:
    """Give money (if any) and record the new total so the pickup poll does not count it."""
    if amount > 0:
        pc = get_pc()
        with prevent_hooking_direct_calls():
            pc.PlayerReplicationInfo.AddCurrencyOnHand(AddValue=amount, FormOfCurrency=0)
    _last["money"] = _money()


@hook(H["h_vendor_buy"].function)
def vendor_buy_pre(_obj: Any, args: Any, *_: Any) -> None:
    if is_me(args.WPC):
        _vendor_money["buy"] = _money() or 0


@hook(H["h_vendor_buy_post"].function, Type.POST)
def vendor_buy_post(_obj: Any, args: Any, *_: Any) -> None:
    if not is_me(args.WPC) or "buy" not in _vendor_money:
        return
    spent = _vendor_money.pop("buy") - (_money() or 0)
    _last["money"] = _money()
    if spent > 0:
        use("speech")
        _add_money(int(spent * mag("speech")))
        ok_once("speech_buy", str(spent))


@hook(H["h_vendor_sell"].function)
def vendor_sell_pre(_obj: Any, args: Any, *_: Any) -> None:
    if is_me(args.WPC):
        _vendor_money["sell"] = _money() or 0


@hook(H["h_vendor_sell_post"].function, Type.POST)
def vendor_sell_post(_obj: Any, args: Any, *_: Any) -> None:
    if not is_me(args.WPC) or "sell" not in _vendor_money:
        return
    gained = (_money() or 0) - _vendor_money.pop("sell")
    _last["money"] = _money()
    if gained > 0:
        use("speech")
        _add_money(int(gained * mag("speech")))
        ok_once("speech_sell", str(gained))


@hook(H["h_add_inventory"].function, Type.POST)
def on_add_inventory(obj: Any, args: Any, *_: Any) -> None:
    pawn = my_pawn()
    item = args.NewItem
    if item is None or pawn is None or addr(obj.Owner) != addr(pawn):
        return
    rarity = 1
    try:
        if item.Class.Name == "WillowWeapon":
            rarity = int(item.StaticCalculateWeaponRarityLevel(item.DefinitionData))
            part = item.DefinitionData.ElementalPartDefinition
            if part is not None and not part.Name.endswith("_None"):
                use("enchanting")
        else:
            rarity = int(item.StaticCalculateItemRarityLevel(item.DefinitionData))
    except Exception:  # noqa: BLE001
        pass
    rarity = max(1, min(rarity, 5))
    use("smithing", 1.0 + float(T["t_rarity_xp_step"]) * (rarity - 1))


@hook(H["h_use_object"].function, Type.POST)
def on_use_object(obj: Any, args: Any, *_: Any) -> None:
    pawn = my_pawn()
    if pawn is None or addr(args.User) != addr(pawn) or addr(obj) in _opened:
        return
    definition = obj.InteractiveObjectDefinition
    path = definition._path_name() if definition is not None else ""
    if not any(p in path for p in str(T["t_chest_patterns"]).split(",")):
        return
    _opened.add(addr(obj))
    use("lockpicking")
    pc = get_pc()
    level = int(pc.PlayerReplicationInfo.ExpLevel) if hasattr(pc.PlayerReplicationInfo, "ExpLevel") else 1
    worth = float(T["t_chest_cash_base"]) * float(T["t_chest_cash_growth"]) ** (level - 1)
    _add_money(int(worth * mag("lockpicking")))
    ok_once("lockpicking", path)


def _hold_attr(store: dict, key: Any, obj: Any, attr: str, factor: float) -> None:
    """Keep obj.attr at base x factor, re-reading the base whenever the game changes it."""
    cur = float(getattr(obj, attr))
    base, wrote = store.get(key, (cur, None))
    if wrote is None or abs(cur - wrote) > 1e-4 * max(1.0, abs(wrote)):
        base = cur
    new = base * factor
    if abs(new - cur) > 1e-6:
        setattr(obj, attr, new)
    store[key] = (base, new)


@hook(H["h_tick"].function, Type.POST)
def on_tick(_obj: Any, args: Any, *_: Any) -> None:
    global _clock, _next_message_at, _opening_due_at, _no_skyrim_shown, _heal_acc, _own_heal, _opening_shown
    global _shout_was_ready, _shield_full_after_hit
    pc = get_pc(possibly_loading=True)
    if pc is None or pc.WorldInfo.Pauser is not None:
        return
    dt = float(args.DeltaTime)
    _clock += dt

    if _messages and _clock >= _next_message_at:
        title, msg = _messages.pop(0)
        show_hud_message(title, msg)
        _next_message_at = _clock + float(T["t_message_gap_s"])

    pawn = pc.Pawn
    if pawn is None:
        return

    ok_once("tick")
    # Greeting: due a moment after spawning for any character without a race, whatever order
    # the spawn, save-load and Skyrim-reading events arrived in.
    needs_opening = not _opening_shown and not STATE.get("race")
    if needs_opening and _opening_due_at is None:
        _opening_due_at = _clock + float(T["t_opening_delay_s"])
    if needs_opening and _clock >= _opening_due_at:
        if RULES is not None:
            normalize_state()
            _opening_shown = True
            _opening_due_at = None
            show_opening()
        elif LOAD_ERROR and not _no_skyrim_shown:
            _no_skyrim_shown = True
            _opening_due_at = None
            TrainingBox(title="Skyrim not found", message=LOAD_ERROR).show()

    if RULES is None or not STATE.get("race"):
        return

    # Shout cooldown notice.
    if not _shout_was_ready and _clock >= _shout_ready_at:
        _shout_was_ready = True
        notify(RULES.skyrim["shout"]["name"], "ready")

    # Illusion: falling into Fight For Your Life.
    injured = bool(pawn.IsInjured())
    if injured and not _last["injured"]:
        use("illusion")
    _last["injured"] = injured

    # Money from pickups (Pickpocket).
    money = _money()
    if money is not None:
        last = _last["money"]
        if last is not None and money > last and not _vendor_money:
            use("pickpocket")
            _add_money(int((money - last) * mag("pickpocket")))  # also records the new total
            ok_once("pickpocket", str(money - last))
        else:
            _last["money"] = money

    # Shields: Alteration speeds recharge and levels when the shield fills again.
    shield, max_shield = float(pawn.GetShieldStrength()), float(pawn.GetMaxShieldStrength())
    prev = _last["shield"]
    if prev is not None and max_shield > 0:
        if prev < shield < max_shield:
            extra = max_shield * mag("alteration") * dt
            if extra > 0:
                pawn.SetShieldStrength(min(max_shield, shield + extra))
                ok_once("alteration")
        if shield >= max_shield and prev < max_shield and not _shield_full_after_hit:
            _shield_full_after_hit = True
            use("alteration")
    _last["shield"] = float(pawn.GetShieldStrength())

    # Restoration: steady regeneration.
    if not injured:
        _heal_acc += pawn.GetMaxHealth() * mag("restoration") * dt
        if _heal_acc >= 1.0 and pawn.GetHealth() < pawn.GetMaxHealth():
            amount, _heal_acc = int(_heal_acc), _heal_acc - int(_heal_acc)
            _own_heal = True
            try:
                pawn.SetHealth(min(pawn.GetMaxHealth(), pawn.GetHealth() + amount))
                ok_once("restoration")
            finally:
                _own_heal = False
        elif pawn.GetHealth() >= pawn.GetMaxHealth():
            _heal_acc = 0.0

    # Light Armor: speed, and XP for moving with enemies close.
    try:
        _hold_attr(_speed, "ground", pawn, "GroundSpeed", 1.0 + mag("light_armor"))
    except Exception as e:  # noqa: BLE001
        ok_once("light_armor_speed_unavailable", str(e))
    if _clock >= _last["scan_at"]:
        _last["scan_at"] = _clock + float(T["t_scan_interval_s"])
        moving = math.hypot(pawn.Velocity.X, pawn.Velocity.Y) >= float(T["t_moving_speed_uu"])
        if moving and pawns_near(pawn.Location, float(T["t_enemy_near_uu"])):
            use("light_armor", float(T["t_scan_interval_s"]))

    # Enchanting: elemental effect chance on the held gun.
    weapon = pawn.Weapon
    if weapon is not None:
        try:
            _hold_attr(_status, addr(weapon), weapon, "StatusEffectChanceModifier", 1.0 + mag("enchanting"))
        except Exception as e:  # noqa: BLE001
            ok_once("enchanting_unavailable", str(e))


# ---- keys -------------------------------------------------------------------------------------
K = S.KEYBINDS


@keybind("Shout", K["k_shout"].default_key, description=K["k_shout"].action)
def shout_key() -> None:
    shout()


@keybind("Skyrim Skills", K["k_menu"].default_key, description=K["k_menu"].action)
def menu_key() -> None:
    show_skills_menu()


# ---- the mod ----------------------------------------------------------------------------------
def on_enable() -> None:
    if RULES is None:
        start_loading()


mod = build_mod(
    keybinds=[shout_key, menu_key],
    hooks=[block_action_skill, block_class_skills, skills_tab, on_possess, on_new_game, enemy_damage,
           player_damage, on_heal, vendor_buy_pre, vendor_buy_post, vendor_sell_pre, vendor_sell_post,
           on_add_inventory, on_use_object, on_tick],
    options=[],
    on_enable=on_enable,
)
register_save_options(mod, save_options=[progress], on_save=on_save, on_load=on_load)
