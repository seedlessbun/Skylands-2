"""python -m skylands_setup bl2badass [--bl2 DIR] [--out FILE] [--minutes N] [--no-audio]: how Borderlands 2 makes its Badass enemies (changes nothing).

Planning survey for the Badass feature (docs/badass-roadmap.md). Nothing about BL2's enemy balances has been read in full yet (the shield survey only
listed which pawns carry a shield), so it is driven by names and classes:
  B0  names in every package's name table: badass-like names, enemy sound and dialog-looking names, and which packages hold them
  B1  every AIPawnBalanceDefinition, grouped by family (GD_Population_<X>), with the tier its name says (regular / badass / super / ultimate / boss / loot)
  B2  full dumps of a regular and every tier variant of the families that have one, down to the pawn archetype and AI class (health and damage start values)
  B3  the health and damage formulas (GD_Balance_HealthAndDamage), the rarity weights
  B4  the item-pool lists enemies drop from (GD_Itempools.ListDefs), pools named for badasses and bosses
  B5  presentation: objects named like badasses (particles, materials, name parts) in the packages that hold them
  B6  enemy audio: sound and dialog event names per enemy family, checked against the Wwise banks (audio files found, sizes); dialog objects by class
Each section runs on its own and the report is saved after each one.
"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import steam
from .bl2 import upk
from .bl2.index import Index
from .shieldprobe import Ctx, PAWN_CLASS, POOL_CLASS, brief, children_of_group, follow, props_at

BADASS = re.compile(r"(?i)badass")
# what a pawn balance's leaf name says about its tier; the first that matches wins
TIERS = (("ultimate", re.compile(r"(?i)ultimate")), ("super", re.compile(r"(?i)super")), ("badass", re.compile(r"(?i)badass")),
         ("boss", re.compile(r"(?i)(boss|raid|unique|named)")), ("loot", re.compile(r"(?i)(loot|chubby|treasure)")))
# enemy families: the word in names that says which enemy a sound or balance belongs to (lower case)
FAMILIES = ("marauder", "nomad", "psycho", "bruiser", "goliath", "midget", "buzzard", "bandit", "hyperion", "loader", "surveyor", "constructor", "engineer",
            "gunloader", "bullymong", "skag", "spiderant", "rakk", "stalker", "varkid", "thresher", "crystalisk", "creeper", "saturn", "warrior",
            "dragon", "orc", "knight", "skeleton", "spider", "golem", "wizard", "mimic", "dwarf", "treant", "wurm", "tink", "yeti", "savage", "witchdoctor",
            "scaylion", "boroks", "sandworm", "anchor", "badass", "enemy", "creature")
# words that say "an enemy makes this sound / says this line"
VOICE = re.compile(r"(?i)(^|_)(vo|dialog|dialogue|taunt|pain|death|die|dying|grunt|scream|attack|idle|alert|spot|spotted|combat|hurt|injured|battlecry|"
                   r"laugh|roar|growl|howl|charge|enrage|spawn|intro|kill|victory|flee|cower|breath|footstep|melee|bark|chatter|call)(_|$|\d)")
FAMILY_RE = re.compile("(?i)(" + "|".join(FAMILIES) + ")")


def family_of(name: str) -> str:
    m = FAMILY_RE.search(name)
    return m.group(1).lower() if m else "other"


def tier_of(leaf: str) -> str:
    for tier, rx in TIERS:
        if rx.search(leaf):
            return tier
    return "regular"


def is_sound_name(name: str) -> bool:
    low = name.lower()
    return low.startswith(("ak_play_", "ak_stop_", "akb_", "ake_", "play_")) and (bool(FAMILY_RE.search(low)) or bool(VOICE.search(low)))


# ---- B0 ------------------------------------------------------------------------------------------------------------------------------

def name_scan(ctx: Ctx, upks: list[Path]) -> dict:
    ctx.head("B0. Names in the packages (badass, enemy sounds, enemy dialog)")
    t0 = time.time()
    badass: dict[str, set[str]] = defaultdict(set)
    sound: dict[str, set[str]] = defaultdict(set)
    dialog: dict[str, set[str]] = defaultdict(set)
    banks: dict[str, set[str]] = defaultdict(set)  # akb_* : the Wwise bank names the packages load
    vobd: dict[str, set[str]] = defaultdict(set)   # ak_play_vobd_*: battle dialog (taunts, pain, death ...) of enemies and heroes
    popnames: dict[str, set[str]] = defaultdict(set)  # population (spawn) class and object names: PopDef_*, *PopulationDefinition, PopulationFactory*
    unreadable = 0
    for n, p in enumerate(upks):
        try:
            names = upk.read_name_set(p)
        except Exception:  # noqa: BLE001
            unreadable += 1
            continue
        for name in names:
            if BADASS.search(name):
                badass[name].add(p.stem)
            low = name.lower()
            if re.search(r"(population|^popdef)", low):
                popnames[name].add(p.stem)
            if low.startswith("akb_"):
                banks[name].add(p.stem)
            if low.startswith("ak_play_") and "vobd_" in low:
                vobd[name].add(p.stem)
            if is_sound_name(name):
                sound[name].add(p.stem)
            elif re.search(r"(?i)dialog", name):
                dialog[name].add(p.stem)
        if n % 300 == 0:
            print(f"  {n}/{len(upks)} name tables", flush=True)
    ctx.say(f"name tables read in {time.time() - t0:.0f} s ({unreadable} unreadable): {len(badass)} badass names, {len(sound)} enemy/voice-looking sound names, {len(dialog)} dialog names")
    ctx.say(f"badass names ({len(badass)}), with how many packages name them:")
    for name, owners in sorted(badass.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:600]:
        ctx.put(f"  {len(owners):4}  {name}  [{', '.join(sorted(owners)[:3])}]")
    by_family: dict[str, list[str]] = defaultdict(list)
    for name in sound:
        by_family[family_of(name)].append(name)
    ctx.say("enemy/voice sound names by family: " + ", ".join(f"{f} {len(v)}" for f, v in sorted(by_family.items(), key=lambda kv: -len(kv[1]))))
    for fam, names in sorted(by_family.items()):
        ctx.put(f"  -- {fam} ({len(names)})")
        for name in sorted(names)[:150]:
            ctx.put(f"     {name}  [{', '.join(sorted(sound[name])[:2])}]")
    ctx.say(f"dialog names ({len(dialog)}), the first 300:")
    for name in sorted(dialog)[:300]:
        ctx.put(f"  {name}  [{', '.join(sorted(dialog[name])[:2])}]")
    ctx.save()
    return {"badass": badass, "sound": sound, "dialog": dialog, "banks": banks, "vobd": vobd, "popnames": popnames}


# ---- reading many groups: each package opened once -----------------------------------------------------------------------------

def objects_in_groups(ctx: Ctx, groups: list[str], class_re: re.Pattern, keep_props=None, label: str = "groups") -> list[tuple[str, str, dict | None]]:
    """(path, class, props or None) of every object directly in the groups whose class matches. A group is copied into many level packages; reading it
    group by group opened and decompressed the same big packages again and again (the index keeps 24 open), which looked like a hang in B1. So each group
    is read from ONE package (the one holding most of it, the smallest file among those), the groups are bundled by that package, and every package is
    opened once. keep_props(path) says which objects' properties to read while the package is open."""
    ix = ctx.ix
    by_file: dict[int, list[str]] = defaultdict(list)
    for g in groups:
        entries = ix.groups.get(g) or []
        if not entries:
            continue
        most = entries[0][1]
        best = min((i for i, n in entries if n == most), key=lambda i: ix.files[i].stat().st_size)
        by_file[best].append(g)
    order = sorted(by_file, key=lambda i: ix.files[i].stat().st_size)
    ctx.say(f"{label}: {len(groups)} groups in {len(order)} packages ({sum(ix.files[i].stat().st_size for i in order) / 1e6:.0f} MB to open)")
    out: list[tuple[str, str, dict | None]] = []
    seen: set[str] = set()
    t0 = time.time()
    for n, i in enumerate(order, 1):
        if ctx.out_of_time():
            ctx.say(f"(time is up after {n - 1} of {len(order)} packages; run again with a larger --minutes for the rest)")
            break
        f = ix.files[i]
        try:
            pkg = upk.open_package(f)  # not through the index's cache: read once and let go
        except Exception as e:  # noqa: BLE001
            ctx.put(f"  {f.name}: could not be opened ({type(e).__name__}: {str(e)[:100]})")
            continue
        for g in by_file[i]:
            for idx in pkg.children_of(g):
                cls = pkg.obj_class(idx)
                if not class_re.search(cls):
                    continue
                path = pkg.path_of(idx)
                if path in seen:
                    continue
                seen.add(path)
                props = None
                if keep_props is not None and keep_props(path):
                    try:
                        props = props_at(pkg, idx)
                    except Exception:  # noqa: BLE001
                        props = None
                out.append((path, cls, props))
        del pkg
        if n % 10 == 0 or n == len(order):
            print(f"  {label}: {n}/{len(order)} packages, {len(out)} objects ({time.time() - t0:.0f} s)", flush=True)
    return out


# ---- B1 ------------------------------------------------------------------------------------------------------------------------------

def balance_groups(ix) -> list[str]:
    """The groups that hold pawn balances: GD_Population_<X>.Balance (and the like: a 'balance' group of an enemy package)."""
    out = []
    for g in ix.groups:
        top, _, sub = g.partition(".")
        if "balance" in sub and top.startswith(("gd_population", "gd_enemy", "gd_pawn", "gd_ai")):
            out.append(g)
    return sorted(out)


def balances(ctx: Ctx) -> dict[str, list[tuple[str, str, str]]]:
    """family -> [(path, class, tier)] for every pawn balance; the properties of the tier balances are kept in ctx (for B2)."""
    ctx.head("B1. Every enemy (pawn) balance, by family and tier")
    ix = ctx.ix
    t0 = time.time()
    fams: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    found = objects_in_groups(ctx, balance_groups(ix), PAWN_CLASS, keep_props=lambda p: tier_of(p.rsplit(".", 1)[-1]) != "regular", label="pawn balances")
    ctx.tier_props = {}
    for path, cls, props in found:
        top = path.split(".")[0]
        fam = top[len("GD_Population_"):] if top.lower().startswith("gd_population_") else top
        fams[fam].append((path, cls, tier_of(path.rsplit(".", 1)[-1])))
        if props is not None:
            ctx.tier_props[path] = props
    total = sum(len(v) for v in fams.values())
    tiers = Counter(t for v in fams.values() for _p, _c, t in v)
    ctx.say(f"{total} pawn balances in {len(fams)} families ({time.time() - t0:.0f} s); by the tier their names say: {dict(tiers)}")
    for fam, rows in sorted(fams.items()):
        here = Counter(t for _p, _c, t in rows)
        ctx.put(f"  {fam}: {len(rows)} ({', '.join(f'{t} {n}' for t, n in here.most_common())})")
        for path, cls, tier in sorted(rows, key=lambda r: (r[2] == "regular", r[0]))[:40]:
            ctx.put(f"      {tier:8} {path} [{cls}]")
    ctx.save()
    return fams


# ---- B2 ------------------------------------------------------------------------------------------------------------------------------

def pick_pairs(fams: dict[str, list[tuple[str, str, str]]], n_families: int = 14) -> list[str]:
    """For the families that have a tier variant: one regular balance and every tier variant (ultimate/super first), families with the most tiers first."""
    scored = []
    for fam, rows in fams.items():
        tiers = {t for _p, _c, t in rows if t in ("badass", "super", "ultimate")}
        if tiers:
            scored.append((-len(tiers), fam))
    seeds: list[str] = []
    for _s, fam in sorted(scored)[:n_families]:
        rows = fams[fam]
        regular = [p for p, _c, t in rows if t == "regular"]
        if regular:
            seeds.append(sorted(regular, key=len)[0])
        for want in ("ultimate", "super", "badass"):
            seeds += [p for p, _c, t in rows if t == want][:2]
    return list(dict.fromkeys(seeds))


def tier_dumps(ctx: Ctx, fams: dict) -> None:
    ctx.head("B2. A regular enemy and its Badass / Super / Ultimate variants in full (archetype, AI class, start values, item pools)")
    seeds = pick_pairs(fams)
    ctx.say(f"{len(seeds)} balances chosen: {seeds}")
    # one line each of every tier balance first (the display names and play-through pools side by side), from the properties B1 read
    kept = getattr(ctx, "tier_props", {})
    for fam, rows in sorted(fams.items()):
        for path, _cls, tier in rows:
            if tier != "regular" and path in kept:
                ctx.put(f"{tier:8} {path} {brief(kept[path], 600)}")
    ctx.save()
    follow(ctx, seeds, depth=3, cap=700, lines_each=400, title="tier balances", fanout=40)


# ---- B3 ------------------------------------------------------------------------------------------------------------------------------

WEIGHTS = ("GD_Balance.Weighting.Weight_0_VeryCommon", "GD_Balance.Weighting.Weight_1_Common", "GD_Balance.Weighting.Weight_2_Uncommon", "GD_Balance.Weighting.Weight_3_Rare",
           "GD_Balance.Weighting.Weight_4_VeryRare", "GD_Balance.Weighting.Weight_5_Legendary")


def formulas(ctx: Ctx) -> None:
    ctx.head("B3. Health and damage formulas, AI parameters, rarity weights")
    ix = ctx.ix
    seeds: list[str] = list(WEIGHTS)
    groups = [g for g in sorted(ix.groups) if g.startswith(("gd_balance_healthanddamage", "gd_aiclass", "d_attributes.balance", "d_attributes.ai", "gd_balance_experience"))]
    ctx.say(f"{len(groups)} groups: {groups[:80]}")
    for g in groups:
        for path in children_of_group(ix, g):
            if ":" not in path and re.search(r"(?i)(health|damage|badass|enemy|pawn|multiplier|scale|level|experience)", path.rsplit(".", 1)[-1]):
                seeds.append(path)
    seeds = list(dict.fromkeys(seeds))
    ctx.say(f"{len(seeds)} formula objects")
    follow(ctx, seeds[:300], depth=2, cap=420, lines_each=200, title="formulas", fanout=30)


# ---- B4 ------------------------------------------------------------------------------------------------------------------------------

def pools(ctx: Ctx) -> None:
    ctx.head("B4. What enemies drop: the item-pool lists and the pools named for badasses and bosses")
    ix = ctx.ix
    seeds: list[str] = []
    lists = [g for g in sorted(ix.groups) if g.startswith("gd_itempools") and "listdefs" in g]
    for g in lists:
        seeds += [p for p in children_of_group(ix, g) if ":" not in p]
    ctx.say(f"{len(seeds)} item-pool lists in {lists}")
    groups = [g for g in ix.groups if g.startswith("gd_itempools")]
    named = [path for path, _cls, _p in objects_in_groups(ctx, sorted(groups), POOL_CLASS, label="item pools")
             if re.search(r"(?i)(badass|boss|raid|enemyuse|unique|named|loot|chubby)", path.rsplit(".", 1)[-1])]
    ctx.say(f"{len(named)} pools named for badasses, bosses, enemy use or loot:")
    for p in named[:300]:
        ctx.put(f"  {p}")
    ctx.save()
    follow(ctx, list(dict.fromkeys(seeds[:80] + named[:60])), depth=2, cap=360, lines_each=200, title="pools", fanout=30)


# ---- B5 ------------------------------------------------------------------------------------------------------------------------------

def presentation(ctx: Ctx, scan: dict) -> None:
    ctx.head("B5. Presentation: objects named like badasses (particles, materials, name parts, sounds)")
    ix = ctx.ix
    holders = Counter(stem for owners in scan["badass"].values() for stem in owners)
    files = {f.stem: f for f in ix.files}
    chosen = sorted((s for s in holders if s in files), key=lambda s: files[s].stat().st_size)[:40]
    ctx.say(f"{len(holders)} packages name a badass; opening the {len(chosen)} smallest: {chosen}")
    by_class: dict[str, list[str]] = defaultdict(list)
    for stem in chosen:
        if ctx.out_of_time():
            ctx.say("(time is up in the presentation search)")
            break
        try:
            pkg = ix.package(files[stem])
        except Exception as e:  # noqa: BLE001
            ctx.put(f"  {stem}: could not be opened ({type(e).__name__})")
            continue
        for i, _e in enumerate(pkg.exports, 1):
            path = pkg.path_of(i)
            if BADASS.search(path):
                by_class[pkg.obj_class(i)].append(path)
    for cls, paths in sorted(by_class.items(), key=lambda kv: -len(kv[1])):
        ctx.say(f"{len(paths):5}  {cls}")
        for p in sorted(set(paths))[:25]:
            ctx.put(f"         {p}")
    small = [p for cls, paths in by_class.items() if re.search(r"(?i)(namepart|name|string|definition|skill|behavior)", cls) for p in paths[:6]]
    if small:
        follow(ctx, list(dict.fromkeys(small))[:40], depth=1, cap=60, lines_each=80, title="badass names and skills", fanout=20)
    ctx.save()


# ---- B6 ------------------------------------------------------------------------------------------------------------------------------

def audio(ctx: Ctx, bl2: Path, scan: dict, check_banks: bool) -> None:
    ctx.head("B6. Enemy audio: sound and voice events per family, checked against the Wwise banks")
    names = sorted(scan["sound"])
    ctx.say(f"{len(names)} enemy/voice-looking sound names in the packages")
    if not check_banks:
        ctx.say("(banks not checked: --no-audio)")
        ctx.save()
        return
    try:
        from .bl2 import audio as bl2audio
        from .bl2 import wwise

        snd = bl2audio.load(bl2, ctx.say)
    except Exception as e:  # noqa: BLE001
        ctx.say(f"audio banks could not be read: {type(e).__name__}: {e}")
        ctx.save()
        return
    if snd is None:
        ctx.save()
        return
    found: dict[str, list[str]] = defaultdict(list)
    missing: dict[str, int] = Counter()
    for name in names[:6000]:
        fam = family_of(name)
        for label, ident in wwise.event_ids(name):
            if snd.first(ident, (wwise.HIRC_EVENT,)) is None:
                continue
            leads = snd.event_sounds(ident)
            media = [m for m in (snd.media_of(s) for s in leads) if m]
            sizes = [len(snd.audio(m) or b"") for m in media]
            found[fam].append(f"{name} (as {label}): {len(leads)} sound(s), {len(media)} audio file(s), {sum(sizes) // 1024} KB")
            break
        else:
            missing[fam] += 1
    total = sum(len(v) for v in found.values())
    ctx.say(f"{total} of {min(len(names), 6000)} names are events in the banks; by family: "
            + ", ".join(f"{f} {len(v)} (+{missing[f]} not events)" for f, v in sorted(found.items(), key=lambda kv: -len(kv[1]))))
    for fam, rows in sorted(found.items()):
        ctx.put(f"  -- {fam} ({len(rows)})")
        for r in rows[:200]:
            ctx.put(f"     {r}")
    ctx.save()


def dialog_objects(ctx: Ctx, scan: dict) -> None:
    ctx.head("B7. Dialog objects (how an enemy picks a line: event tags, groups, the sound each line plays)")
    ix = ctx.ix
    holders = Counter(stem for owners in scan["dialog"].values() for stem in owners)
    files = {f.stem: f for f in ix.files}
    chosen = [s for s in sorted(holders, key=lambda s: (not FAMILY_RE.search(s), files[s].stat().st_size if s in files else 1 << 40)) if s in files][:20]
    ctx.say(f"{len(holders)} packages name dialog; opening {len(chosen)}: {chosen}")
    by_class: dict[str, list[str]] = defaultdict(list)
    for stem in chosen:
        if ctx.out_of_time():
            ctx.say("(time is up in the dialog search)")
            break
        try:
            pkg = ix.package(files[stem])
        except Exception:  # noqa: BLE001
            continue
        for i, _e in enumerate(pkg.exports, 1):
            cls = pkg.obj_class(i)
            if re.search(r"(?i)(dialog|talk)", cls):
                by_class[cls].append(pkg.path_of(i))
    for cls, paths in sorted(by_class.items(), key=lambda kv: -len(kv[1])):
        ctx.say(f"{len(paths):5}  {cls}")
        for p in paths[:8]:
            ctx.put(f"         {p}")
    seeds = [paths[0] for paths in by_class.values()] + [p for paths in by_class.values() for p in paths[1:4]]
    if seeds:
        follow(ctx, list(dict.fromkeys(seeds))[:40], depth=2, cap=120, lines_each=120, title="dialog samples", fanout=20)
    ctx.save()


# ---- B8: enemy voices (battle dialog) in every sound pack -------------------------------------------------------------------------------

VOBD = re.compile(r"(?i)^ak_play_(?:[a-z0-9]+_)?vobd_([a-z0-9]+)_(.*)$")
VOICE_KIND = (("death", re.compile(r"(?i)death|dying|die")), ("pain", re.compile(r"(?i)pain|injur|hurt")), ("taunt", re.compile(r"(?i)taunt|kill|victory|laugh")),
              ("attack", re.compile(r"(?i)attack|melee|charge|throw|grenade|start")), ("spot", re.compile(r"(?i)spot|alert|see|found|confirm|focus")),
              ("other", re.compile(".")))


def voice_kind(rest: str) -> str:
    for kind, rx in VOICE_KIND:
        if rx.search(rest):
            return kind
    return "other"


def voices(ctx: Ctx, bl2: Path, scan: dict) -> None:
    """The first survey found no battle-dialog event (ak_play_vobd_*) in the main pack pair, though the packages name a bank akb_vobd_bandits:
    the voices live in another pack (a DLC's, or a language's). Every .pck/.bnk in the install is listed with its banks (named where a bank
    name's Wwise id matches), then each pack is loaded on its own and the dialog events are looked up in it."""
    from .bl2 import wwise

    ctx.head("B8. Enemy voices (battle dialog): every sound pack in the install, which banks it holds, which dialog events and audio it has")
    names = sorted(scan.get("vobd", {}))
    by_char: dict[str, list[str]] = defaultdict(list)
    for n in names:
        m = VOBD.match(n)
        if m:
            by_char[m.group(1).lower()].append(n)
    ctx.say(f"{len(names)} battle-dialog names in the packages, {len(by_char)} speakers: "
            + ", ".join(f"{c} {len(v)}" for c, v in sorted(by_char.items(), key=lambda kv: -len(kv[1]))[:60]))
    for c, v in sorted(by_char.items()):
        kinds = Counter(voice_kind(VOBD.match(n).group(2)) for n in v)
        ctx.put(f"  -- {c} ({len(v)}): {dict(kinds)}")
        for n in sorted(v)[:40]:
            ctx.put(f"     {n}")
    bank_names = {wwise.fnv1(b): b for b in scan.get("banks", {})}
    ctx.say(f"{len(bank_names)} bank names (akb_*) in the packages: {sorted(bank_names.values())[:120]}")
    packs = sorted(p for p in bl2.rglob("*") if p.is_file() and p.suffix.lower() in (".pck", ".bnk"))
    ctx.say(f"{len(packs)} sound pack/bank files in the install:")
    ids = {n: [i for _l, i in wwise.event_ids(n)] for n in names}
    found_any: dict[str, list[str]] = defaultdict(list)
    for f in packs:
        if ctx.out_of_time():
            ctx.say("(time is up in the voice search)")
            break
        rel = f.relative_to(bl2)
        size = f.stat().st_size
        try:
            data = f.read_bytes()
        except OSError as e:
            ctx.put(f"  {rel}: unreadable ({e})")
            continue
        snd = wwise.Sounds()
        if f.suffix.lower() == ".pck":
            pack = wwise.read_pack(data)
            snd.add_banks(data, pack)
            if pack.sounds and pack.sound_score >= 0.5:
                snd.add_streamed(data, pack)
            langs = sorted({e.lang for e in pack.banks + pack.sounds})
            named = [bank_names.get(e.id, f"{e.id:08X}") for e in pack.banks]
            ctx.say(f"  {rel} ({size // 1048576} MB): layout [{pack.layout}], {len(pack.banks)} banks (match {pack.bank_score:.2f}), {len(pack.sounds)} streamed (match {pack.sound_score:.2f}), languages {langs}")
            ctx.put(f"     banks: {named[:200]}")
        else:
            pack = wwise.Pack()
            snd.add_banks(data, pack)
            ctx.say(f"  {rel} ({size // 1024} KB): {len(snd.banks)} bank(s)")
        del data
        hits: list[str] = []
        for n, idents in ids.items():
            for ident in idents:
                if snd.first(ident, (wwise.HIRC_EVENT,)) is None:
                    continue
                leads = snd.event_sounds(ident)
                media = [m for m in (snd.media_of(s) for s in leads) if m]
                sizes = [len(snd.audio(m) or b"") for m in media]
                hits.append(f"{n}: {len(leads)} sound(s), {len(media)} audio file(s) found here, {sum(sizes) // 1024} KB")
                found_any[str(rel)].append(n)
                break
        if hits:
            ctx.say(f"     {len(hits)} battle-dialog events in this pack; the first 120:")
            for h in hits[:120]:
                ctx.put(f"       {h}")
        ctx.save()
    total = sum(len(v) for v in found_any.values())
    ctx.say(f"battle-dialog events found: {total} of {len(names)} names, in {len(found_any)} packs: {[(k, len(v)) for k, v in found_any.items()]}")
    ctx.save()


def voice_banks_in_packages(ctx: Ctx, bl2: Path, scan: dict) -> None:
    """Wwise banks can live INSIDE the game's packages (an AkBank object holding the bank's bytes, often in a localised _LOC_INT package) instead of a .pck:
    the packages that name a voice bank (akb_*vo*) are opened, every export holding a bank (BKHD) is read, and the battle-dialog events are looked up in it.
    Audio a bank does not hold itself is looked for among the streamed files of every .pck (by id)."""
    from .bl2 import wwise

    ctx.head("B8b. Voice banks stored inside the packages (AkBank objects)")
    names = sorted(scan.get("vobd", {}))
    ids = {n: [i for _l, i in wwise.event_ids(n)] for n in names}
    voice_banks = {b: owners for b, owners in scan.get("banks", {}).items() if re.search(r"(?i)akb_.*(vo|dialog|dlg)", b)}
    ctx.say(f"{len(voice_banks)} voice-looking bank names: {sorted(voice_banks)[:80]}")
    streamed: dict[int, str] = {}
    for f in sorted(p for p in bl2.rglob("*.pck") if p.is_file()):
        try:
            data = f.read_bytes()
        except OSError:
            continue
        for e in wwise.read_pack(data).sounds:
            streamed.setdefault(e.id, str(f.relative_to(bl2)))
        del data
    ctx.say(f"{len(streamed)} streamed audio files in the .pck files (audio a bank only points to)")
    files = {f.stem.lower(): f for f in ctx.ix.files}
    stems: set[str] = set()
    for owners in voice_banks.values():
        for s in owners:
            stems.add(s.lower())
            stems.add((s + "_LOC_INT").lower())
    for s in list(files):
        if s.endswith("_loc_int") and re.search(r"(?i)(vo|dialog|bandit|psycho|marauder|nomad|goliath|midget)", s):
            stems.add(s)
    chosen = sorted((files[s] for s in stems if s in files), key=lambda f: f.stat().st_size)[:120]
    ctx.say(f"opening {len(chosen)} packages (those naming a voice bank, their _LOC_INT twins and voice-looking _LOC_INT packages), smallest first")
    total, by_speaker = 0, Counter()
    for f in chosen:
        if ctx.out_of_time():
            ctx.say("(time is up in the package bank search)")
            break
        try:
            pkg = upk.open_package(f)
        except Exception as e:  # noqa: BLE001
            ctx.put(f"  {f.name}: could not be opened ({type(e).__name__})")
            continue
        for i, e in enumerate(pkg.exports, 1):
            if e.serial_size < 64:
                continue
            cls = pkg.obj_class(i)
            if "akbank" not in cls.lower() and not pkg.obj_name(i).lower().startswith("akb_"):
                continue
            data = pkg.export_data(i)
            if b"BKHD" not in data:
                ctx.put(f"  {f.name}: {pkg.path_of(i)} [{cls}] {e.serial_size} bytes, no bank inside")
                continue
            snd = wwise.Sounds()
            snd.add_banks(data, wwise.Pack())
            hits = []
            for n, idents in ids.items():
                for ident in idents:
                    if snd.first(ident, (wwise.HIRC_EVENT,)) is None:
                        continue
                    leads = snd.event_sounds(ident)
                    inside = outside = 0
                    for s in leads:
                        m = snd.media_of(s)
                        if m and snd.audio(m):
                            inside += 1
                        else:
                            # a streamed sound names its file id in its body; look for any streamed id there
                            body_ids = wwise.contains_ids(s.body, streamed)
                            outside += 1 if body_ids else 0
                    hits.append(f"{n}: {len(leads)} sound(s), audio inside the bank {inside}, in a .pck {outside}")
                    m2 = VOBD.match(n)
                    if m2:
                        by_speaker[m2.group(1).lower()] += 1
                    break
            total += len(hits)
            ctx.say(f"  {f.name}: {pkg.path_of(i)} [{cls}] {e.serial_size // 1024} KB: {len(snd.banks)} bank(s), {sum(b.objects for b in snd.banks)} objects, "
                    f"{sum(len(b.media) for b in snd.banks)} audio files inside, {len(hits)} battle-dialog events")
            for h in hits[:60]:
                ctx.put(f"       {h}")
        del pkg
        ctx.save()
    ctx.say(f"battle-dialog events found in package banks: {total}; by speaker: {dict(by_speaker.most_common(60))}")
    ctx.save()


# ---- B10: the human enemies' voice lines, resolved and sampled ------------------------------------------------------------------------------

BANDIT_SPEAKERS = re.compile(r"(?i)^(maraud|psycho|nomad|goliath|banditheavy|bandit|bt$|rat|ratleader|midget|savage|biker|bulkybiker|boomboom|scav|bndt|piratepsycho|lilac|bikemarauder)")
SAMPLE_KINDS = ("death", "pain", "taunt", "attack", "spot")


class VoiceSet:
    """One language's voices: its bank pack, its streamed audio, and the language-free bank pack of the same folder (which can hold the sound objects the
    voice events lead to: the first voice survey loaded each pack on its own and found the base game's events but no sounds behind them)."""

    def __init__(self, lang_banks: Path) -> None:
        from .bl2 import wwise

        self.lang_banks = lang_banks
        self.dir = lang_banks.parent
        self.sfx_dir = self.dir.parent
        self.snd = wwise.Sounds()
        self.stream_index: dict[int, tuple[Path, int, int]] = {}
        self.files: list[str] = []

    def load(self, ctx: Ctx) -> None:
        from .bl2 import wwise

        stem = self.lang_banks.name.replace("Audio_Banks", "Audio_Streaming")
        sfx_banks = self.sfx_dir / self.lang_banks.name
        for f, kind in ((self.lang_banks, "banks"), (sfx_banks, "banks"), (self.dir / stem, "stream"), (self.sfx_dir / stem, "stream")):
            if not f.is_file():
                continue
            data = f.read_bytes()
            pack = wwise.read_pack(data)
            if kind == "banks":
                self.snd.add_banks(data, pack)
            for e in pack.sounds:
                self.stream_index.setdefault(e.id, (f, e.offset, e.size))
            self.snd.media_ids.update(e.id for e in pack.sounds)
            self.files.append(f"{f.name} ({len(data) // 1048576} MB, {len(pack.banks)} banks, {len(pack.sounds)} streamed)")
            del data

    def audio(self, media: int) -> bytes | None:
        got = self.snd.audio(media)
        if got:
            return got
        where = self.stream_index.get(media)
        if not where:
            return None
        f, off, size = where
        with f.open("rb") as h:
            h.seek(off)
            return h.read(size)


def voice_lines(ctx: Ctx, bl2: Path, scan: dict, out_dir: Path, decode_samples: bool = True) -> None:
    """For every English voice pack set (base game and DLCs): which battle-dialog lines resolve to audio, per speaker; the structure of lines that do not;
    and a few lines of the bandit-like speakers decoded to WAV in work\\voice-samples so they can be heard."""
    from .bl2 import audio as bl2audio
    from .bl2 import wwise

    ctx.head("B10. Enemy voice lines: each English voice pack with its streamed audio and its sound pack, resolved per speaker, with samples")
    names = sorted(scan.get("vobd", {}))
    lang_packs = sorted(p for p in bl2.rglob("Audio_Banks*.pck") if p.parent.name.lower().startswith("english"))
    ctx.say(f"{len(names)} battle-dialog names; {len(lang_packs)} English voice packs: {[str(p.relative_to(bl2)) for p in lang_packs]}")
    samples_dir = out_dir / "voice-samples"
    decoder_box: list = [None, decode_samples]
    total_samples = 0
    summary: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])  # speaker -> events, with sounds, with audio, KB
    for lp in lang_packs:
        if ctx.out_of_time():
            ctx.say("(time is up in the voice line search)")
            break
        vs = VoiceSet(lp)
        try:
            vs.load(ctx)
        except MemoryError:
            ctx.say(f"  {lp.relative_to(bl2)}: out of memory while loading")
            continue
        ctx.say(f"  {lp.relative_to(bl2)}: loaded {vs.files}")
        unresolved: list[tuple[str, int]] = []
        per_kind_samples: dict[tuple[str, str], int] = defaultdict(int)
        for n in names:
            m = VOBD.match(n)
            if not m:
                continue
            speaker = m.group(1).lower()
            ident = next((i for _l, i in wwise.event_ids(n) if vs.snd.first(i, (wwise.HIRC_EVENT,)) is not None), None)
            if ident is None:
                continue
            row = summary[f"{speaker} [{lp.parent.parent.parent.name if 'DLC' in str(lp) else 'base game'}]"]
            row[0] += 1
            leads = vs.snd.event_sounds(ident)
            if not leads:
                unresolved.append((n, ident))
                continue
            row[1] += 1
            media = list(dict.fromkeys(mm for mm in (vs.snd.media_of(s) for s in leads) if mm))
            blobs = [(mm, vs.audio(mm)) for mm in media]
            blobs = [(mm, b) for mm, b in blobs if b]
            if blobs:
                row[2] += 1
                row[3] += sum(len(b) for _mm, b in blobs) // 1024
            kind = voice_kind(m.group(2))
            if decode_samples and blobs and BANDIT_SPEAKERS.match(speaker) and kind in SAMPLE_KINDS and per_kind_samples[(speaker, kind)] < 1 and total_samples < 80:
                if decoder_box[0] is None and decoder_box[1]:
                    decoder_box[0] = bl2audio.find_decoder(out_dir) or bl2audio.download_decoder(out_dir, ctx.say)
                    decoder_box[1] = False
                samples_dir.mkdir(parents=True, exist_ok=True)
                for k, (mm, b) in enumerate(blobs[:2]):
                    wav = bl2audio.decode(b, out_dir, f"vo_{speaker}_{mm:08X}", decoder_box[0], ctx.put)
                    if wav:
                        dest = samples_dir / f"{speaker}_{kind}_{m.group(2)[:40]}_{k + 1}.wav"
                        dest.write_bytes(wav)
                        total_samples += 1
                        ctx.put(f"     sample: {dest.name} ({len(wav) // 1024} KB) from {n}")
                per_kind_samples[(speaker, kind)] += 1
        ctx.say(f"     {len(unresolved)} events lead to no sound; the structure of the first ones:")
        for n, ident in unresolved[:5]:
            ev = vs.snd.first(ident, (wwise.HIRC_EVENT,))
            ctx.put(f"     {n} event {ident:08X}: {len(ev.body)} bytes {ev.body[:48].hex()}")
            for aid in wwise.contains_ids(ev.body, vs.snd.objs)[:4]:
                act = vs.snd.first(aid)
                ctx.put(f"        -> {aid:08X} type {act.type} ({len(act.body)} bytes) {act.body[:40].hex()}")
                for tid in wwise.contains_ids(act.body, vs.snd.objs)[:4]:
                    tgt = vs.snd.first(tid)
                    ctx.put(f"           -> {tid:08X} type {tgt.type} ({len(tgt.body)} bytes) {tgt.body[:40].hex()}")
        del vs
        ctx.save()
    ctx.say("per speaker: events found / leading to sounds / with audio / KB of audio:")
    for sp, (a, b, c, kb) in sorted(summary.items(), key=lambda kv: (not BANDIT_SPEAKERS.match(kv[0]), kv[0])):
        ctx.put(f"  {sp}: {a} / {b} / {c} / {kb} KB" + ("   <- bandit-like" if BANDIT_SPEAKERS.match(sp) else ""))
    ctx.say(f"{total_samples} sample WAV files written to {samples_dir}" if decode_samples else "(no samples: --no-audio)")
    ctx.save()


# ---- B9: how often a Badass spawns ---------------------------------------------------------------------------------------------

def _struct_items(props: dict) -> list[dict]:
    """Every struct inside every array of an object's properties."""
    out: list[dict] = []
    for v in props.values():
        if isinstance(v, dict) and v.get("type") == "Array":
            out += [x for x in v.get("items", []) if isinstance(x, dict)]
    return out


def _weight(entry: dict) -> tuple[float | None, str]:
    """An entry's probability: (constant x scale, or None when it comes from an attribute/formula, and what it is)."""
    for k, v in entry.items():
        if "prob" in k.lower() or "weight" in k.lower():
            if isinstance(v, dict) and "BaseValueConstant" in v:
                attr, init = v.get("BaseValueAttribute"), v.get("InitializationDefinition")
                c = float(v.get("BaseValueConstant") or 0) * float(v.get("BaseValueScaleConstant", 1) or 1)
                if isinstance(attr, str) or isinstance(init, str):
                    return None, f"{c} attr={str(attr).rsplit('.', 1)[-1]} init={str(init).rsplit('.', 1)[-1]}"
                return c, f"{c}"
            if isinstance(v, (int, float)):
                return float(v), f"{v}"
    return None, "no probability field"


def _balance_of(ctx: Ctx, factory: str, depth: int = 0) -> list[str]:
    """The pawn balances a spawn factory leads to (directly, or through a nested population definition)."""
    if depth > 2:
        return []
    try:
        props = ctx.ix.props(factory) or {}
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for k, v in props.items():
        if isinstance(v, str) and "." in v:
            if "pawnbalance" in v.lower() or "balance" in k.lower():
                out.append(v)
            elif "population" in k.lower() or "popdef" in v.lower():
                out += _pop_balances(ctx, v, depth + 1)
    return out


def _pop_balances(ctx: Ctx, popdef: str, depth: int) -> list[str]:
    try:
        props = ctx.ix.props(popdef) or {}
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for e in _struct_items(props):
        for k, v in e.items():
            if isinstance(v, str) and "factory" in k.lower():
                out += _balance_of(ctx, v, depth)
    return out


def spawns(ctx: Ctx, scan: dict) -> None:
    """BL2 spawns enemies from population definitions (a mix of spawn factories, each pointing at a pawn balance, with a probability): the share of
    the Badass / Super / Ultimate entries in each mix is how often a Badass replaces a regular spawn. Class and field names are not known yet,
    so it looks by name: classes with 'population' in them, array entries with a '*Factory*' field and a '*Probability*'/'*Weight*' field."""
    ctx.head("B9. How often a Badass spawns: the population definitions (spawn mixes)")
    ix = ctx.ix
    pn = scan.get("popnames", {})
    cls_like = sorted(n for n in pn if re.match(r"(?i)^[a-z]*population[a-z]*(definition|factory|opportunity|den|encounter)[a-z]*$", n))
    ctx.say(f"{len(pn)} population-looking names; class-like ({len(cls_like)}): {cls_like[:60]}")
    popdefs = sorted(n for n in pn if n.lower().startswith("popdef"))
    ctx.say(f"{len(popdefs)} PopDef_* names, e.g. {popdefs[:40]}")
    groups = sorted(g for g in ix.groups if g.startswith("gd_population") and "balance" not in g.partition(".")[2])
    found = objects_in_groups(ctx, groups, re.compile(r"(?i)population|popdef"), keep_props=lambda p: True, label="population definitions")
    defs = [(p, c, pr) for p, c, pr in found if "factory" not in c.lower()]
    ctx.say(f"{len(found)} population objects in {len(groups)} groups ({len(defs)} definitions); classes: {dict(Counter(c for _p, c, _pr in found))}")
    shares: list[tuple[str, dict[str, float], int]] = []
    unknown = 0
    for path, cls, props in defs:
        if ctx.out_of_time():
            ctx.say("(time is up while reading the spawn mixes)")
            break
        entries = []
        for e in _struct_items(props or {}):
            fac = next((v for k, v in e.items() if isinstance(v, str) and "factory" in k.lower()), None)
            if not fac:
                continue
            w, note = _weight(e)
            bal = _balance_of(ctx, fac)
            tiers = sorted({tier_of(b.rsplit(".", 1)[-1]) for b in bal}) or ["?"]
            maxact = next((v for k, v in e.items() if "maxactive" in k.lower()), None)
            entries.append((fac.rsplit(".", 1)[-1], [b.rsplit(".", 1)[-1] for b in bal][:3], tiers, w, note, maxact))
        if not entries:
            continue
        tot: Counter = Counter()
        for _f, _b, tiers, w, _n, _m in entries:
            if w is None:
                unknown += 1
                continue
            for tr in tiers:
                tot[tr] += w / len(tiers)
        s = sum(tot.values())
        if s > 0:
            shares.append((path, {k: v / s for k, v in tot.items()}, len(entries)))
        ctx.put(f"{path} [{cls}]: " + "; ".join(f"{f} -> {b} {tr} p={note} max={m}" for f, b, tr, w, note, m in entries[:12]))
    ctx.say(f"{len(shares)} spawn mixes with known probabilities ({unknown} entries had a formula/attribute instead of a number)")
    with_badass = [(p, sh) for p, sh, _n in shares if any(k in sh for k in ("badass", "super", "ultimate"))]
    ctx.say(f"{len(with_badass)} of them can spawn a Badass; their shares (badass / super / ultimate):")
    for p, sh in with_badass[:200]:
        ctx.put(f"  {p.rsplit('.', 1)[-1]}: " + ", ".join(f"{k} {v * 100:.1f}%" for k, v in sorted(sh.items())))
    for tier in ("badass", "super", "ultimate"):
        vals = sorted(sh.get(tier, 0.0) for _p, sh in with_badass)
        allv = sorted(sh.get(tier, 0.0) for _p, sh, _n in shares)
        if vals:
            ctx.say(f"SHARE {tier}: median {vals[len(vals) // 2] * 100:.1f}% in the mixes that have Badasses, mean {sum(allv) / len(allv) * 100:.2f}% over all {len(allv)} mixes")
    seeds = [p for p, _sh in with_badass[:6]] + [p for p, _c, _pr in defs[:4]]
    if seeds:
        follow(ctx, list(dict.fromkeys(seeds)), depth=2, cap=80, lines_each=200, title="spawn mix samples", fanout=20)
    ctx.save()


# ---- main ----------------------------------------------------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="skylands bl2badass")
    ap.add_argument("--bl2")
    ap.add_argument("--out", default="BL2-Badass-Report.txt")
    ap.add_argument("--minutes", type=float, default=25.0, help="time allowed for reading packages (the index is extra)")
    ap.add_argument("--no-audio", action="store_true", help="do not read the sound banks")
    ap.add_argument("--voice", action="store_true", help="the name scan and the enemy voice lines: each English voice pack with its audio, per speaker, with WAV samples (B0, B10)")
    ap.add_argument("--voice-packs", action="store_true", help="the name scan and the first voice search: every sound pack on its own and the voice banks inside packages (B0, B8, B8b)")
    ap.add_argument("--spawns", action="store_true", help="the name scan and how often a Badass spawns: BL2's population definitions (B0, B9)")
    a = ap.parse_args(argv)
    bl2 = Path(a.bl2) if a.bl2 else steam.find("bl2")
    out_path = Path(a.out)
    ctx = Ctx(None, out_path, time.time() + a.minutes * 60)
    ctx.say(f"skylands bl2badass 1  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    if not bl2 or not (bl2 / "WillowGame").is_dir():
        ctx.say(f"Borderlands 2 not found ({bl2}). Run with --bl2 \"D:\\path\\Borderlands 2\".")
        ctx.save()
        return 2
    ctx.say(f"Borderlands 2 folder: {bl2}")
    try:
        ctx.ix = ix = Index(bl2, out_path.parent / "cache" / "bl2_index.json", ctx.put)
    except Exception as e:  # noqa: BLE001
        ctx.say(f"The Borderlands 2 index could not be built: {type(e).__name__}: {e}")
        ctx.save()
        return 1
    ctx.deadline = time.time() + a.minutes * 60  # the clock starts after the index
    ctx.say(f"{len(ix.files)} packages indexed; {len(ix.top)} top-level names, {len(ix.groups)} groups")
    ctx.say(f"groups with 'badass' in the name: {sorted(k for k in ix.groups if BADASS.search(k))[:120]}")
    ctx.save()
    failed: list[str] = []
    state: dict = {"scan": {"badass": {}, "sound": {}, "dialog": {}, "banks": {}, "vobd": {}, "popnames": {}}, "fams": {}}

    def run(name: str, fn) -> None:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            import traceback

            failed.append(name)
            ctx.say(f"SECTION '{name}' FAILED: {type(e).__name__}: {e}")
            ctx.put(traceback.format_exc())
            ctx.save()

    def names() -> None:
        state["scan"] = name_scan(ctx, list(ix.files))

    def fams() -> None:
        state["fams"] = balances(ctx)

    run("names", names)
    if a.voice or a.spawns or a.voice_packs:
        if a.spawns:
            run("spawns", lambda: spawns(ctx, state["scan"]))
        if a.voice_packs:
            run("voices", lambda: voices(ctx, bl2, state["scan"]))
            run("voice banks in packages", lambda: voice_banks_in_packages(ctx, bl2, state["scan"]))
        if a.voice:
            run("voice lines", lambda: voice_lines(ctx, bl2, state["scan"], out_path.parent, decode_samples=not a.no_audio))
        ctx.say("")
        ctx.say(f"Finished{' (sections that failed: ' + ', '.join(failed) + ')' if failed else ''}. Report written to {out_path}. Send it to Claude.")
        ctx.save()
        return 1 if failed else 0
    run("balances", fams)
    run("tier balances", lambda: tier_dumps(ctx, state["fams"]))
    run("formulas", lambda: formulas(ctx))
    run("pools", lambda: pools(ctx))
    run("presentation", lambda: presentation(ctx, state["scan"]))
    run("audio", lambda: audio(ctx, bl2, state["scan"], not a.no_audio))
    run("dialog", lambda: dialog_objects(ctx, state["scan"]))
    ctx.say("")
    ctx.say(f"Finished{' (sections that failed: ' + ', '.join(failed) + ')' if failed else ''}. Report written to {out_path}. Send it to Claude.")
    ctx.save()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
