"""python -m skylands_setup bl2shields [--bl2 DIR] [--out FILE] [--minutes N] [--no-audio]: how Borderlands 2 builds its shields (changes nothing).

Planning survey for the shield feature. Nothing about BL2's shield objects has been looked at yet, so the survey is driven by names and
classes, not by paths we guess: it finds every package, group and object whose name or class says "shield", lists the classes it finds, dumps
their properties (capacity, recharge rate and delay, type, resistances, rarity, level scaling) and follows the references they hold (attribute
definitions, value resolvers and formulas, part lists, name parts, manufacturers) a few levels deep. Then it reads the loot pools that hold
shields and which enemy types carry shields, the shield meshes (the Item_Shields gestalt definition is cut into its parts like the gun
gestalts), the textures, HUD art and the sounds, and writes everything as plain text to send back.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import steam
from .bl2 import extract, gunmesh, upk
from .bl2.index import Index
from .gestaltprobe import show

SHIELD = re.compile(r"(?i)shield")
# names that look like a class of ours to find (the exports' own classes are listed later and are the authority)
CLASSLIKE = re.compile(r"(?i)^[a-z]*shield[a-z]*(definition|part|balance|pool|collection|attribute|resolver|slot)[a-z]*$")
UI_NAME = re.compile(r"(?i)(shield.*(bar|meter|icon|hud|fill|gauge|flash|warn|ui|gfx|swf|tex)|(hud|ui_|gfx|swf).*shield)")
SOUND_NAME = re.compile(r"(?i)(^ak[a-z0-9_]*shield|shield[a-z0-9]*_(break|recharge|charge|deplet|empty|low|down|hit|warn|alarm|ready|fill|loop|start|stop|on|off)(_|$))")
PATH = re.compile(r"^[A-Za-z_]\w*(\.\w+)+(:\w+)?$")
# classes that cost time and say nothing about numbers (their paths are still listed)
ASSET = re.compile(r"(Texture|Material|SoundCue|SoundNode|ParticleSystem|SkeletalMesh|StaticMesh|AnimSet|AnimTree|PhysicsAsset|Font|"
                   r"Sequence|SwfMovie|Cascade|Distribution|Module|Skel|Light|Surface|GFx)", re.I)
UI_CLASS = re.compile(r"(?i)(Texture2D|GFx|Swf|Movie|Font)")
NUM_CLASS = re.compile(r"(?i)(attribute|resolver|formula|expression|initialization|curve|table|level|scale)")
POOL_CLASS = re.compile(r"(?i)^ItemPool(List)?Definition$")
PAWN_CLASS = re.compile(r"(?i)PawnBalanceDefinition$")
MAX_PACKAGES = 70


class Ctx:
    def __init__(self, ix: Index | None, out_path: Path, deadline: float) -> None:
        self.ix = ix
        self.out_path = out_path
        self.deadline = deadline
        self.lines: list[str] = []

    def out_of_time(self) -> bool:
        return time.time() > self.deadline

    def say(self, msg: str = "") -> None:
        print(msg, flush=True)
        self.lines.append(msg)

    def put(self, msg: str = "") -> None:
        self.lines.append(msg)

    def head(self, title: str) -> None:
        self.say("")
        self.say("=" * 8 + " " + title)
        self.save()

    def save(self) -> None:
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.out_path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


# ---- helpers ------------------------------------------------------------------------------------------------------------------------

def paths_in(value, out: list[str], depth: int = 0) -> None:
    """Every string that looks like an object path anywhere in a decoded property value."""
    if depth > 9:
        return
    if isinstance(value, str):
        if PATH.match(value):
            out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            paths_in(v, out, depth + 1)
    elif isinstance(value, list):
        for v in value:
            paths_in(v, out, depth + 1)


def keys_matching(value, pattern: re.Pattern, trail: str = "", depth: int = 0) -> list[tuple[str, str]]:
    """(key trail, short value) for every property whose key or string value says 'shield'."""
    out: list[tuple[str, str]] = []
    if depth > 9:
        return out
    if isinstance(value, dict):
        for k, v in value.items():
            here = f"{trail}.{k}" if trail else str(k)
            if pattern.search(str(k)) and not isinstance(v, (dict, list)):
                out.append((here, str(v)[:120]))
            out += keys_matching(v, pattern, here, depth + 1)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out += keys_matching(v, pattern, f"{trail}[{i}]", depth + 1)
    elif isinstance(value, str) and pattern.search(value) and PATH.match(value):
        out.append((trail, value[:160]))
    return out


def brief(props: dict, limit: int = 420) -> str:
    """One line: scalar properties, numbers of initialisation data as const*scale, arrays by length."""
    parts = []
    for k, v in props.items():
        if isinstance(v, dict) and "BaseValueConstant" in v:
            attr = v.get("BaseValueAttribute")
            init = v.get("InitializationDefinition")
            parts.append(f"{k}={v.get('BaseValueConstant')}*{v.get('BaseValueScaleConstant', 1)}"
                         + (f" attr={attr.rsplit('.', 1)[-1]}" if isinstance(attr, str) else "")
                         + (f" init={init.rsplit('.', 1)[-1]}" if isinstance(init, str) else ""))
        elif isinstance(v, dict) and v.get("type") == "Array":
            parts.append(f"{k}[{v.get('count')}]")
        elif isinstance(v, dict):
            parts.append(f"{k}={{..{len(v)}}}")
        elif isinstance(v, list):
            parts.append(f"{k}={v[:4]}")
        else:
            parts.append(f"{k}={str(v)[:70]}")
    text = "; ".join(parts)
    return text if len(text) <= limit else text[:limit] + " ..."


def props_at(pkg: upk.Package, i: int) -> dict:
    try:
        return upk.object_properties(pkg, i)
    except Exception:  # noqa: BLE001 - reported as an empty object
        return {}


def ancestors_say_shield(pkg: upk.Package, i: int, cache: dict[int, bool]) -> bool:
    """Is any group above export i named like a shield (GD_Shields.Aspect.X: the X need not say it)."""
    if i in cache:
        return cache[i]
    outer = pkg.outer(i)
    result = False
    guard = 0
    while outer > 0 and guard < 8:
        if SHIELD.search(pkg.obj_name(outer)):
            result = True
            break
        outer = pkg.outer(outer)
        guard += 1
    cache[i] = result
    return result


class Obj:
    """A shield-looking export. Holds no package (open packages are big): the properties are read when it is found, within a budget."""

    read = 0
    LIMIT = 5000

    def __init__(self, pkg: upk.Package, i: int, path: str, cls: str, why: str) -> None:
        self.path, self.cls, self.why = path, cls, why
        self.file = pkg.path
        self.size = pkg.exports[i - 1].serial_size
        self.props: dict = {}
        if Obj.read < Obj.LIMIT and self.size < 400_000:
            Obj.read += 1
            self.props = props_at(pkg, i)


# ---- 1. where shields are ----------------------------------------------------------------------------------------------------------

def name_scan(ctx: Ctx, bl2: Path, upks: list[Path]) -> dict:
    """One pass over every package's name table: class-like, UI-like and sound-like shield names, and which package holds them."""
    t0 = time.time()
    names_in: dict[str, set[str]] = defaultdict(set)  # lower-case shield name -> package stems
    unreadable = 0
    for n, p in enumerate(upks):
        try:
            names = upk.read_name_set(p)
        except Exception:  # noqa: BLE001
            unreadable += 1
            continue
        for name in names:
            if "shield" in name:
                names_in[name].add(p.stem)
        if n % 300 == 0:
            print(f"  {n}/{len(upks)} name tables", flush=True)
    ctx.say(f"{len(names_in)} different names contain 'shield', in {len({s for v in names_in.values() for s in v})} packages ({time.time() - t0:.0f} s, {unreadable} packages unreadable)")
    classlike = {n: s for n, s in names_in.items() if CLASSLIKE.match(n)}
    ctx.say(f"names that look like shield classes/definitions ({len(classlike)}), with the number of packages that name them:")
    for n, s in sorted(classlike.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:120]:
        ctx.put(f"  {len(s):4}  {n}")
    ui = {n: s for n, s in names_in.items() if UI_NAME.search(n)}
    ctx.say(f"names that look like HUD/UI art ({len(ui)}):")
    for n, s in sorted(ui.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:150]:
        ctx.put(f"  {len(s):4}  {n}  [{', '.join(sorted(s)[:3])}]")
    snd = {n: s for n, s in names_in.items() if SOUND_NAME.search(n)}
    ctx.say(f"names that look like shield sound events ({len(snd)}):")
    for n, s in sorted(snd.items())[:200]:
        ctx.put(f"  {n}  [{', '.join(sorted(s)[:3])}]")
    ctx.save()
    return {"names": names_in, "classlike": classlike, "ui": ui, "sound": snd}


def pick_packages(ctx: Ctx, upks: list[Path], scan: dict) -> list[Path]:
    """The packages worth opening: those that DEFINE shield groups (from the index), then those naming a shield class, UI art or sound."""
    ix = ctx.ix
    stems = defaultdict(list)
    for p in upks:
        stems[p.stem].append(p)
    score: Counter = Counter()
    for group, weight in ((scan["classlike"], 2), (scan["ui"], 2), (scan["sound"], 1)):
        for owners in group.values():
            for stem in owners:
                score[stem] += weight
    for key in [k for k in ix.top if SHIELD.search(k)]:
        for i in ix.top[key]:
            score[ix.files[i].stem] += 1000
    for key in [k for k in ix.groups if SHIELD.search(k)]:
        for i, _n in ix.groups[key]:
            score[ix.files[i].stem] += 1000
    for p in upks:
        if SHIELD.search(p.stem):
            score[p.stem] += 1000
        elif p.stem.lower().startswith(("startup", "mancana_startup")) and score[p.stem] > 0:
            score[p.stem] += 500
    ranked = [s for s, w in score.most_common() if w > 0]
    # definers (score >= 1000) first, whatever their size; the rest small first
    ranked.sort(key=lambda s: (0 if score[s] >= 500 else 1, min(p.stat().st_size for p in stems[s])))
    chosen = [p for s in ranked for p in stems[s]][:MAX_PACKAGES]
    ctx.say(f"{len(score)} packages mention shields in some form; opening the {len(chosen)} best: {[p.name for p in chosen][:40]}")
    return chosen


def collect(ctx: Ctx, packages: list[Path]) -> list[Obj]:
    """Open the packages and keep every export whose class, name or enclosing group says shield."""
    ix = ctx.ix
    found: list[Obj] = []
    opened = 0
    t0 = time.time()
    for p in packages:
        if ctx.out_of_time():
            ctx.say(f"(time is up after {opened} of {len(packages)} packages; run again with a larger --minutes for the rest)")
            break
        try:
            pkg = ix.package(p)
        except Exception as e:  # noqa: BLE001
            ctx.say(f"{p.name}: could not be opened ({type(e).__name__}: {str(e)[:100]})")
            continue
        opened += 1
        cache: dict[int, bool] = {}
        n_here = 0
        for i, e in enumerate(pkg.exports, 1):
            cls = pkg.obj_class(i)
            if cls == "Package":
                continue
            why = ""
            if SHIELD.search(cls):
                why = "class"
            elif SHIELD.search(e.name):
                why = "name"
            elif ancestors_say_shield(pkg, i, cache):
                why = "group"
            if why:
                found.append(Obj(pkg, i, pkg.path_of(i), cls, why))
                n_here += 1
        if n_here:
            ctx.put(f"  {p.name} ({p.stat().st_size / 1e6:.1f} MB): {n_here} shield-looking objects")
    ctx.say(f"opened {opened} packages in {time.time() - t0:.0f} s; {len(found)} shield-looking objects")
    return found


def census(ctx: Ctx, objs: list[Obj]) -> None:
    ctx.head("1. Shield-looking objects by class")
    by_class: dict[str, list[Obj]] = defaultdict(list)
    for o in objs:
        by_class[o.cls].append(o)
    for cls, items in sorted(by_class.items(), key=lambda kv: -len(kv[1])):
        ctx.say(f"{len(items):5}  {cls}")
        for o in items[:6]:
            ctx.put(f"           {o.path}  ({o.size} bytes, {o.file.name}, by {o.why})")
    groups = Counter(o.path.rsplit(".", 1)[0] if "." in o.path else o.path for o in objs)
    ctx.say(f"groups holding them ({len(groups)}):")
    for g, n in groups.most_common(80):
        ctx.put(f"  {n:5}  {g}")
    ctx.save()


# ---- 2. definitions ------------------------------------------------------------------------------------------------------------------

def follow(ctx: Ctx, seeds: list[str], depth: int, cap: int, lines_each: int, title: str, fanout: int = 30) -> set[str]:
    """Breadth-first read of the objects a set of seeds refers to; numbers-bearing classes (attributes, resolvers, formulas) first."""
    ix = ctx.ix
    seen: dict[str, str] = {}
    assets: list[str] = []
    queue: list[tuple[str, int, str]] = [(s, 0, "") for s in seeds]
    ctx.say(f"{title}: following {len(seeds)} objects, up to {cap} objects, {depth} levels")
    while queue and len(seen) < cap and not ctx.out_of_time():
        path, d, via = queue.pop(0)
        if path in seen:
            continue
        try:
            got = ix.get(path)
        except Exception:  # noqa: BLE001
            got = None
        if not got:
            seen[path] = "?"
            continue
        pkg, idx = got
        cls = pkg.obj_class(idx)
        seen[path] = cls
        if ASSET.search(cls):
            assets.append(f"{path} [{cls}]")
            continue
        props = ix.props(path) or {}
        ctx.put("")
        ctx.put(f"--- {path} [{cls}] level {d}" + (f" via {via.rsplit('.', 1)[-1]}" if via else ""))
        for line in show(props, 1, [lines_each]):
            ctx.put(line)
        if d < depth:
            refs: list[str] = []
            paths_in(props, refs)
            if re.search(r"(?i)Behavior", cls):  # on-break / on-hit effects are nested objects that nothing points to by path
                for child in children_of_group(ix, path):
                    queue.insert(0, (child, d + 1, path))
            urgent = bool(NUM_CLASS.search(cls))
            wanted = [r for r in dict.fromkeys(refs) if r != path and r not in seen and not r.lower().startswith(("fx_", "ake_", "common_gunmaterials"))]
            if len(wanted) > fanout:  # a part list names hundreds of parts: the first ones show what a part looks like
                ctx.put(f"  ({len(wanted) - fanout} more references not followed)")
                wanted = [r for r in wanted if NUM_CLASS.search(r)] + [r for r in wanted if not NUM_CLASS.search(r)][:fanout]
            for r in wanted:
                if urgent or NUM_CLASS.search(r):
                    queue.insert(0, (r, d + 1, path))
                else:
                    queue.append((r, d + 1, path))
    ctx.say(f"  read {sum(1 for c in seen.values() if c != '?')} objects; {sum(1 for c in seen.values() if c == '?')} references could not be found")
    if assets:
        ctx.put(f"asset references skipped ({len(assets)}): " + "; ".join(assets[:60]))
    ctx.save()
    return set(seen)


def definitions(ctx: Ctx, objs: list[Obj]) -> dict:
    ctx.head("2. Shield definitions, balances, parts: one line per object")
    primary = [o for o in objs if SHIELD.search(o.cls)]
    others = [o for o in objs if not SHIELD.search(o.cls) and not ASSET.search(o.cls)]
    ctx.say(f"{len(primary)} objects of a class named *Shield*, {len(others)} other shield-looking objects (not assets)")
    frag: dict[str, str] = {}
    for o in primary[:600]:
        p = o.props
        ctx.put(f"{o.path} [{o.cls}] {brief(p)}")
        f = p.get("GestaltModeSkeletalMeshName")
        if isinstance(f, str):
            frag[o.path] = f
    ctx.say(f"other objects with shield in their name or group ({len(others)}), one line each:")
    for o in others[:900]:
        ctx.put(f"{o.path} [{o.cls}] {brief(o.props, 300)}")
        f = o.props.get("GestaltModeSkeletalMeshName")
        if isinstance(f, str):
            frag[o.path] = f
    ctx.save()

    # a spread of seeds: different leaf names first (the manufacturers and rarities are in the names)
    def spread(items: list[Obj], n: int) -> list[str]:
        seen_tokens: set[str] = set()
        picked: list[str] = []
        for o in items:
            token = re.sub(r"\d+", "", o.path.rsplit(".", 1)[-1].lower())
            if token in seen_tokens:
                continue
            seen_tokens.add(token)
            picked.append(o.path)
            if len(picked) >= n:
                break
        return picked

    seeds = spread([o for o in primary if re.search(r"(?i)balance", o.cls)], 8) + spread([o for o in primary if not re.search(r"(?i)balance", o.cls)], 8)
    seeds += spread([o for o in others if re.search(r"(?i)(partlist|collection)", o.cls)], 6)
    seeds += spread([o for o in others if re.search(r"(?i)(part|aspect|type)", o.cls)], 6)
    ctx.head("3. Full dump of a sample, with the references they hold (attributes, formulas, part lists, names)")
    seen = follow(ctx, list(dict.fromkeys(seeds)), depth=3, cap=420, lines_each=70, title="sample")
    ctx.head("4. One full example of every other class found")
    by_class: dict[str, list[Obj]] = defaultdict(list)
    for o in objs:
        by_class[o.cls].append(o)
    extra = [items[0].path for cls, items in by_class.items() if items[0].path not in seen and not ASSET.search(cls)]
    follow(ctx, extra[:80], depth=0, cap=80, lines_each=50, title="classes")
    return {"fragments": frag, "primary": primary}


def attributes(ctx: Ctx) -> None:
    """Attribute definitions with shield in the name (capacity, recharge rate, delay ...) and the level/rarity tables the game keeps."""
    ctx.head("5. Attributes, level scaling and rarity")
    ix = ctx.ix
    rows: list[str] = []
    for g in sorted(ix.groups):
        if g.startswith(("d_attributes", "gd_balance", "gd_globals", "gd_itemgrades", "gd_experience", "gd_levels")) or SHIELD.search(g):
            rows.append(f"{g} ({sum(n for _i, n in ix.groups[g])} objects)")
    ctx.say(f"{len(rows)} groups that may hold attributes, balance tables, globals, item grades:")
    for r in rows[:160]:
        ctx.put("  " + r)
    seeds = []
    for g in sorted(ix.groups):
        if g.startswith("d_attributes") or SHIELD.search(g):
            for path in children_of_group(ix, g):
                if SHIELD.search(path.rsplit(".", 1)[-1]):
                    seeds.append(path)
    ctx.say(f"{len(seeds)} attribute-group objects with shield in the name")
    follow(ctx, seeds[:60], depth=2, cap=140, lines_each=40, title="shield attributes")
    errors: list[str] = []
    try:
        ctx.say("rarity colours (GD_Globals): " + json.dumps(extract.rarities(ix, errors)) + (f"  errors: {errors}" if errors else ""))
    except Exception as e:  # noqa: BLE001
        ctx.say(f"rarity colours could not be read: {type(e).__name__}: {e}")
    follow(ctx, ["GD_Globals.General.Globals"], depth=0, cap=1, lines_each=120, title="globals")
    ctx.save()


def children_of_group(ix: Index, group: str) -> list[str]:
    out: list[str] = []
    for f in ix.candidates(group, definers_only=True):
        try:
            pkg = ix.package(f)
        except Exception:  # noqa: BLE001
            continue
        for i in pkg.children_of(group):
            p = pkg.path_of(i)
            if p not in out:
                out.append(p)
    return out


# ---- 3. loot and enemies ------------------------------------------------------------------------------------------------------------

def group_objects(ix: Index, group: str, class_re: re.Pattern):
    """(package, export index, path, class) of every object directly in a group whose class matches."""
    for f in ix.candidates(group, definers_only=True):
        try:
            pkg = ix.package(f)
        except Exception:  # noqa: BLE001
            continue
        for i in pkg.children_of(group):
            cls = pkg.obj_class(i)
            if class_re.search(cls):
                yield pkg, i, pkg.path_of(i), cls


def pools(ctx: Ctx, shield_paths: set[str]) -> dict[str, dict]:
    """The loot-pool graph: pool -> the paths it refers to; which pools hold shields, directly or through other pools."""
    ctx.head("6. Loot pools that hold shields")
    ix = ctx.ix
    graph: dict[str, list[str]] = {}
    sample: dict[str, dict] = {}
    low_shield = {p.lower() for p in shield_paths}
    t0 = time.time()
    for g in sorted(ix.groups):
        if "itempool" not in g and "itemgrade" not in g:
            continue
        for pkg, i, path, cls in group_objects(ix, g, POOL_CLASS):
            props = props_at(pkg, i)
            refs: list[str] = []
            paths_in(props, refs)
            graph[path] = list(dict.fromkeys(refs))
            if len(sample) < 40 and any(SHIELD.search(r) or r.lower() in low_shield for r in refs):
                sample[path] = props
        if ctx.out_of_time():
            ctx.say("(time is up while reading pools)")
            break
    ctx.say(f"{len(graph)} item pools and pool lists read ({time.time() - t0:.0f} s)")

    def is_shield(path: str) -> bool:
        return bool(SHIELD.search(path)) or path.lower() in low_shield

    holds: dict[str, bool] = {}

    def has_shield(path: str, depth: int = 0, trail: tuple = ()) -> bool:
        if path in holds:
            return holds[path]
        if depth > 7 or path in trail:
            return False
        result = any(is_shield(r) or (r in graph and has_shield(r, depth + 1, trail + (path,))) for r in graph.get(path, ()))
        if depth == 0 or result:
            holds[path] = result
        return result

    direct = [p for p, refs in graph.items() if any(is_shield(r) for r in refs)]
    through = [p for p in graph if has_shield(p) and p not in direct]
    ctx.say(f"{len(direct)} pools refer to a shield directly, {len(through)} more only through other pools")
    for p in sorted(direct)[:250]:
        ctx.put(f"  direct   {p}: " + ", ".join(r.rsplit('.', 1)[-1] for r in graph[p] if is_shield(r))[:240])
    for p in sorted(through)[:250]:
        ctx.put(f"  indirect {p}")
    ctx.say(f"{len(sample)} pools that refer to a shield, in full (their entries carry the probabilities and the drop-on-death flags):")
    for path, props in sample.items():
        ctx.put("")
        ctx.put(f"--- {path}")
        for line in show(props, 1, [60]):
            ctx.put(line)
    ctx.save()
    return {"graph": graph, "holds": {p: has_shield(p) for p in graph}}


def enemies(ctx: Ctx, pool_info: dict) -> None:
    ctx.head("7. Which enemy types carry shields")
    ix = ctx.ix
    graph, holds = pool_info["graph"], pool_info["holds"]
    t0 = time.time()
    total = carrying = 0
    rows: list[str] = []
    dump: list[tuple[str, dict]] = []
    for g in sorted(ix.groups):
        if not g.startswith(("gd_population", "gd_enemy", "gd_pawn")) and "balance" not in g.split(".")[-1]:
            continue
        for pkg, i, path, cls in group_objects(ix, g, PAWN_CLASS):
            total += 1
            props = props_at(pkg, i)
            refs: list[str] = []
            paths_in(props, refs)
            pools_hit = [r for r in dict.fromkeys(refs) if holds.get(r) or SHIELD.search(r)]
            keys = keys_matching(props, SHIELD)
            if pools_hit or keys:
                carrying += 1
                rows.append(f"{path} [{cls}]: pools/refs {[r.rsplit('.', 1)[-1] for r in pools_hit][:6]}; keys {keys[:4]}")
                if len(dump) < 6:
                    dump.append((path, props))
        if ctx.out_of_time():
            ctx.say("(time is up while reading enemy balances)")
            break
    ctx.say(f"{total} pawn balances read ({time.time() - t0:.0f} s); {carrying} refer to a shield pool or have a shield-named property")
    for r in rows[:500]:
        ctx.put("  " + r)
    ctx.say("a few of them in full (where in the balance the shield sits, and how big):")
    for path, props in dump:
        ctx.put("")
        ctx.put(f"--- {path}")
        for line in show(props, 1, [90]):
            ctx.put(line)
    ctx.save()


# ---- 4. art and sound ---------------------------------------------------------------------------------------------------------------

def art(ctx: Ctx, objs: list[Obj], frag: dict[str, str]) -> None:
    ctx.head("8. Meshes, textures, HUD art")
    ix = ctx.ix
    meshes = [o for o in objs if re.search(r"(?i)(SkeletalMesh|StaticMesh)$", o.cls)]
    ctx.say(f"{len(meshes)} shield-named meshes outside gestalts:")
    for o in meshes[:60]:
        ctx.put(f"  {o.path} [{o.cls}] {o.size} bytes in {o.file.name}")
    tex = [o for o in objs if UI_CLASS.search(o.cls)]
    ctx.say(f"{len(tex)} shield-named textures, movies, fonts:")
    for o in tex[:120]:
        p = o.props
        ctx.put(f"  {o.path} [{o.cls}] {o.size} bytes {p.get('SizeX', '')}x{p.get('SizeY', '')} {p.get('Format', '')} in {o.file.name}")
    mats = [o for o in objs if re.search(r"(?i)Material", o.cls)]
    ctx.say(f"{len(mats)} shield-named materials; textures behind the first 25:")
    for o in mats[:25]:
        params = gunmesh.texture_parameters(ix, o.path)
        ctx.put(f"  {o.path}: {params}")
    # every gestalt definition, then the shield ones in detail
    defs: list[tuple[upk.Package, int, str]] = []
    direct = ix.get("Item_Shields.GestaltDef_Shields")
    if direct:
        defs.append((direct[0], direct[1], direct[0].path_of(direct[1])))
    for f in ix.files:
        if not re.search(r"(?i)(startup|shield|remaster)", f.stem):
            continue
        try:
            pkg = ix.package(f)
        except Exception:  # noqa: BLE001
            continue
        for i, e in enumerate(pkg.exports, 1):
            if pkg.obj_class(i) == "GestaltSkeletalMeshDefinition" and pkg.path_of(i) not in [d[2] for d in defs]:
                defs.append((pkg, i, pkg.path_of(i)))
    ctx.say(f"{len(defs)} gestalt definitions in Startup/Item packages: {[d[2] for d in defs][:60]}")
    shield_defs = [d for d in defs if SHIELD.search(d[2])]
    if not shield_defs:  # a definition that is not named so but lists shield fragments
        for pkg, i, path in defs:
            blob = json.dumps(props_at(pkg, i), default=str).lower()
            if "shield" in blob:
                shield_defs.append((pkg, i, path))
    ctx.say(f"{len(shield_defs)} gestalt definitions for shields: {[d[2] for d in shield_defs]}")
    fragment_names: set[str] = set()
    for pkg, i, path in shield_defs:
        props = props_at(pkg, i)
        ctx.put("")
        ctx.put(f"=== {path} in {pkg.path.name}")
        for key in ("GestaltSkeletalMesh", "GestaltSocketMappings", "GestaltPartBounds"):
            if key in props:
                for line in show({key: props[key]}, 1, [60]):
                    ctx.put(line)
        infos = props.get("GestaltInfos")
        infos = infos.get("items") if isinstance(infos, dict) else infos
        parts = []
        if isinstance(infos, list) and infos and isinstance(infos[0], dict):
            p0 = infos[0].get("Parts")
            parts = [x for x in (p0.get("items") if isinstance(p0, dict) else p0 or []) if isinstance(x, dict)]
        ctx.say(f"{path}: {len(parts)} parts, {sum(int(p.get('NumPrimitives', 0)) for p in parts)} triangles")
        mesh_path = props.get("GestaltSkeletalMesh")
        full = None
        if isinstance(mesh_path, str):
            try:
                idx = pkg.find(mesh_path)
                data = pkg.export_data(idx) if idx else b""
                end = 4
                for start in (4, 0, 8):
                    try:
                        _p, end = upk.read_properties(pkg, data, start)
                        break
                    except Exception:  # noqa: BLE001
                        continue
                raw = gunmesh.read_mesh_blob(data, end, mesh_path) if data else None
                if raw:
                    full = raw.mesh
                    ctx.say(f"  mesh {mesh_path}: {len(data)} bytes, {raw.note}; materials {gunmesh.material_refs(pkg, data, end)}")
                    for m in gunmesh.material_refs(pkg, data, end)[:6]:
                        ctx.put(f"    material {m}: {gunmesh.texture_parameters(ix, m)}")
                else:
                    ctx.say(f"  mesh {mesh_path}: {len(data)} bytes, the mesh reader found no geometry")
            except Exception as e:  # noqa: BLE001
                ctx.say(f"  mesh {mesh_path}: {type(e).__name__}: {str(e)[:100]}")
        for part in parts:
            name = str(part.get("SkeletalMeshFragmentName"))
            fragment_names.add(name.lower())
            first, count = int(part.get("FirstIndex", 0)), int(part.get("NumPrimitives", 0))
            row = f"  part {name}: first index {first}, {count} triangles"
            if full is not None and count:
                tris = full.tris[first // 3 : first // 3 + count]
                used = {v for t in tris for v in t}
                if used:
                    xs = [full.positions[v][0] for v in used]
                    ys = [full.positions[v][1] for v in used]
                    zs = [full.positions[v][2] for v in used]
                    row += (f"; {len(used)} vertices; x {min(xs):.1f}..{max(xs):.1f} y {min(ys):.1f}..{max(ys):.1f} z {min(zs):.1f}..{max(zs):.1f}")
                    if full.uvs:
                        us = [full.uvs[v][0] for v in used]
                        vs = [full.uvs[v][1] for v in used]
                        row += f"; uv u {min(us):.2f}..{max(us):.2f} v {min(vs):.2f}..{max(vs):.2f}"
            ctx.put(row)
    if frag:
        known = {n for n in fragment_names}
        wanted = Counter(v.lower() for v in frag.values())
        missing = sorted(n for n in wanted if n not in known)
        ctx.say(f"{len(frag)} shield part objects name a fragment (GestaltModeSkeletalMeshName): {len(wanted)} different names, "
                f"{len(missing)} not among the shield definition's fragments: {missing[:30]}")
        for path, name in list(frag.items())[:150]:
            ctx.put(f"  {path} -> {name}{'' if name.lower() in known else '   (not a fragment of the shield gestalt)'}")
    ctx.save()


def swf_strings(data: bytes, want: re.Pattern) -> tuple[str, list[str]] | None:
    """The text inside a Flash movie stored in an export (symbol and instance names): ('header note', matching strings), or None if there is no movie."""
    import zlib

    starts = [x for x in (data.find(b"CWS"), data.find(b"FWS")) if x >= 0]
    if not starts:
        return None
    i = min(starts)
    raw = data[i:]
    try:
        body = zlib.decompressobj().decompress(raw[8:]) if raw[:3] == b"CWS" else raw[8:]
    except zlib.error:
        return f"{raw[:3].decode()} v{raw[3]} but the compressed body could not be inflated", []
    runs = [r.decode("latin-1") for r in re.findall(rb"[ -~]{4,60}", body)]
    hits = list(dict.fromkeys(r for r in runs if want.search(r)))
    return f"{raw[:3].decode()} v{raw[3]}, {len(body)} bytes inflated, {len(runs)} text runs", hits[:300]


def hud_movies(ctx: Ctx) -> None:
    """Where the game's own HUD movie is and what it calls its health and shield parts (the plugin draws its HUD into that movie)."""
    ctx.head("8b. HUD movies")
    ix = ctx.ix
    cand = sorted((f for f in ix.files if re.search(r"(?i)(hud|menu|^ui|gui|gfx|frontend|interface|swf|startup)", f.stem)), key=lambda f: f.stat().st_size)
    ctx.say(f"{len(cand)} packages whose names suggest UI; looking for Flash movies (smallest first, at most 14 packages and 8 MB each)")
    want = re.compile(r"(?i)(shield|health|hud|armor|meter|ammo)")
    opened = 0
    for f in cand:
        if opened >= 14 or ctx.out_of_time():
            break
        if f.stat().st_size > 8_000_000 and not re.search(r"(?i)hud", f.stem):
            continue
        try:
            pkg = ix.package(f)
        except Exception:  # noqa: BLE001
            continue
        opened += 1
        for i, e in enumerate(pkg.exports, 1):
            cls = pkg.obj_class(i)
            if not re.search(r"(?i)(swf|gfxmovie)", cls):
                continue
            path = pkg.path_of(i)
            got = swf_strings(pkg.export_data(i), want) if e.serial_size < 6_000_000 else None
            ctx.put(f"  {path} [{cls}] {e.serial_size} bytes in {f.name}" + (f"; {got[0]}" if got else ""))
            if got and re.search(r"(?i)hud", path):
                ctx.put("    names inside: " + " | ".join(got[1][:120]))
    ctx.say(f"looked in {opened} packages")
    ctx.save()


def sounds(ctx: Ctx, bl2: Path, scan: dict, check_banks: bool) -> None:
    ctx.head("9. Sounds")
    names = sorted(scan["sound"])
    ctx.say(f"{len(names)} shield-looking sound event names in the packages")
    if not check_banks:
        ctx.say("(banks not checked: --no-audio)")
        ctx.save()
        return
    try:
        from .bl2 import audio, wwise

        snd = audio.load(bl2, ctx.say)
    except Exception as e:  # noqa: BLE001
        ctx.say(f"audio banks could not be read: {type(e).__name__}: {e}")
        ctx.save()
        return
    if snd is None:
        ctx.save()
        return
    ok = 0
    for name in names[:250]:
        # the package names are lower-cased; Wwise hashes the lower-case text, so the id is the same
        for label, ident in wwise.event_ids(name):
            ev = snd.first(ident, (wwise.HIRC_EVENT,))
            if ev is None:
                continue
            leads = snd.event_sounds(ident)
            media = [snd.media_of(s) for s in leads]
            sizes = [len(snd.audio(m) or b"") for m in media if m]
            ctx.put(f"  {name} (as {label}): event found, {len(leads)} sound(s), audio files {sizes}")
            ok += 1
            break
        else:
            ctx.put(f"  {name}: no event of that id in the banks")
    ctx.say(f"{ok} of {min(len(names), 250)} names are events in the banks")
    ctx.save()


# ---- the deep survey (--deep) -----------------------------------------------------------------------------------------------------------
#
# The first survey said what exists; this one reads what it cut off or never reached (docs/shield-roadmap.md section 7): the numbers behind the slot grades,
# the type effects, the enemy formulas, the HUD classes' defaults and the HUD movie. Dumps are not capped. The objects named in the shields sheet
# (sheets/shields.json, column bl2_object) come first: they are the values the installer replaces with Borderlands 2's own.

FAMILY = re.compile(r"(?i)^ItemGrade_Gear_Shield_(Standard|Stock|Enemy_Standard|Nova_\w+?|Spike_\w+?|Roid|Impact|Booster|Absorption|Juggernaut|Chimera)(_03_Rare|_Standard)?$")
DEFAULTS = ("Default__ShieldBarGFxObject", "Default__WillowShield", "Default__ShieldResourcePool", "Default__ShieldDefinition", "Default__ShieldPartDefinition",
            "Default__Behavior_SetShieldTriggeredState", "Default__Behavior_PostProcessChain_LostShield")
FORMULAS = ("GD_Balance_HealthAndDamage.Shields.Init_EnemyShield_CapacityMaxValue", "GD_Balance_HealthAndDamage.Shields.Init_EnemyShield_AdditionalShieldCapacityPerPlayer",
            "GD_Balance_HealthAndDamage.Shields.Init_EnemyShieldOnIdleRegenDelay", "GD_Balance_HealthAndDamage.Shields.Init_EnemyShieldOnIdleRegenRate",
            "GD_Balance_HealthAndDamage.AIParameters.Attribute_EnemyShieldMaxValueMultiplier", "GD_Balance_HealthAndDamage.AIParameters.Attribute_EnemyShieldOnIdleRegenDelayMultiplier",
            "GD_Balance_HealthAndDamage.AIParameters.Attribute_EnemyShieldOnIdleRegenRateMultiplier", "GD_Balance.Weighting.Weight_0_VeryCommon", "GD_Balance.Weighting.Weight_1_Common",
            "GD_Balance.Weighting.Weight_2_Uncommon", "GD_Balance.Weighting.Weight_3_Rare", "GD_Balance.Weighting.Weight_4_VeryRare", "GD_Balance.Weighting.Weight_5_Legendary")


def deep_sheet(ctx: Ctx) -> None:
    ctx.head("D1. The objects the shields sheet names (the values that replace the sheet's defaults)")
    from . import sheet_data as S

    seeds = [row.bl2_object for row in S.SHIELDS.values() if row.bl2_object not in ("-", "")]
    seeds = list(dict.fromkeys(seeds + ["GD_Shields.A_Item.Shield_Standard", "GD_Shields.A_Item_BaseEnemy.Shield_Enemy_Standard", "GD_ItemGrades.Gear.ItemGrade_Gear_Shield_Stock"]))
    follow(ctx, seeds, depth=3, cap=300, lines_each=100000, title="sheet objects", fanout=60)


def deep_families(ctx: Ctx) -> None:
    ctx.head("D2. One balance of every shield family, down to its accessory part and skill")
    ix = ctx.ix
    found: dict[str, str] = {}
    for g in sorted(ix.groups):
        if "itemgrade" not in g or ("shield" not in g and "gear" not in g):
            continue
        for path in children_of_group(ix, g):
            leaf = path.rsplit(".", 1)[-1]
            if FAMILY.match(leaf):
                found.setdefault(leaf, path)
    ctx.say(f"{len(found)} family balances found: {sorted(found)}")
    follow(ctx, list(found.values()), depth=5, cap=900, lines_each=100000, title="families", fanout=60)


def deep_formulas(ctx: Ctx) -> None:
    ctx.head("D3. Enemy shield formulas, rarity weights, the player's health formula")
    ix = ctx.ix
    seeds = list(FORMULAS)
    for g in sorted(ix.groups):
        if g.startswith("gd_balance_healthanddamage"):
            for path in children_of_group(ix, g):
                if re.search(r"(?i)(player|health|shield)", path.rsplit(".", 1)[-1]) and ":" not in path:
                    seeds.append(path)
    follow(ctx, list(dict.fromkeys(seeds)), depth=2, cap=260, lines_each=100000, title="formulas", fanout=40)


def deep_defaults(ctx: Ctx) -> None:
    ctx.head("D4. Default objects of the shield classes (low-shield warning events, break behaviour, bar settings)")
    follow(ctx, list(DEFAULTS), depth=1, cap=40, lines_each=100000, title="defaults", fanout=40)


def deep_hud(ctx: Ctx) -> None:
    ctx.head("D5. The HUD movie")
    ix = ctx.ix
    want = re.compile(r"(?i)(shield|health|meter|bar|ammo|hud)")
    seen = 0
    for f in ix.files:
        if ctx.out_of_time():
            ctx.say("(time is up in the HUD search)")
            break
        if f.stat().st_size > 60_000_000 or not re.search(r"(?i)(hud|ui|menu|gui|gfx|frontend|startup|willowgame)", f.stem):
            continue
        try:
            pkg = ix.package(f)
        except Exception:  # noqa: BLE001
            continue
        for i, e in enumerate(pkg.exports, 1):
            cls = pkg.obj_class(i)
            if not re.search(r"(?i)(swf|gfxmovie)", cls):
                continue
            path = pkg.path_of(i)
            if not re.search(r"(?i)hud", path):
                continue
            seen += 1
            got = swf_strings(pkg.export_data(i), want) if e.serial_size < 20_000_000 else None
            ctx.put(f"  {path} [{cls}] {e.serial_size} bytes in {f.name}" + (f"; {got[0]}" if got else ""))
            if got:
                ctx.put("    names inside: " + " | ".join(got[1][:300]))
    ctx.say(f"{seen} HUD-named movies")
    ctx.save()


# ---- main --------------------------------------------------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="skylands bl2shields")
    ap.add_argument("--bl2")
    ap.add_argument("--out", default="BL2-Shield-Report.txt")
    ap.add_argument("--minutes", type=float, default=25.0, help="time allowed for reading packages (the index is extra)")
    ap.add_argument("--no-audio", action="store_true", help="do not read the sound banks")
    ap.add_argument("--deep", action="store_true", help="the second survey: full dumps of the objects the shields sheet names, one balance per shield family, enemy formulas, the HUD classes' defaults, the HUD movie")
    a = ap.parse_args(argv)
    bl2 = Path(a.bl2) if a.bl2 else steam.find("bl2")
    out_path = Path(a.out)
    ctx = Ctx(None, out_path, time.time() + a.minutes * 60)
    ctx.say(f"skylands bl2shields 1  {time.strftime('%Y-%m-%d %H:%M:%S')}")
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
    shield_tops = sorted(k for k in ix.top if SHIELD.search(k))
    shield_groups = sorted(k for k in ix.groups if SHIELD.search(k))
    ctx.say(f"top-level packages with 'shield' in the name: {shield_tops}")
    ctx.say(f"groups with 'shield' in the name ({len(shield_groups)}): {shield_groups[:80]}")
    ctx.save()
    failed: list[str] = []
    state: dict = {"scan": {"classlike": {}, "ui": {}, "sound": {}, "names": {}}, "objs": [], "info": {"fragments": {}, "primary": []},
                   "pool_info": {"graph": {}, "holds": {}}}

    def run(name: str, fn) -> None:
        # a section that fails must not lose the others: the report is the point
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            import traceback

            failed.append(name)
            ctx.say(f"SECTION '{name}' FAILED: {type(e).__name__}: {e}")
            ctx.put(traceback.format_exc())
            ctx.save()

    def names() -> None:
        ctx.head("0. Names in the packages")
        state["scan"] = name_scan(ctx, bl2, list(ix.files))
        packages = pick_packages(ctx, list(ix.files), state["scan"])
        state["objs"] = collect(ctx, packages)

    def defs() -> None:
        state["info"] = definitions(ctx, state["objs"])

    def pool() -> None:
        state["pool_info"] = pools(ctx, {o.path for o in state["info"]["primary"]})

    if a.deep:
        run("sheet objects", lambda: deep_sheet(ctx))
        run("families", lambda: deep_families(ctx))
        run("formulas", lambda: deep_formulas(ctx))
        run("defaults", lambda: deep_defaults(ctx))
        run("hud", lambda: deep_hud(ctx))
        ctx.say("")
        ctx.say(f"Finished{' (sections that failed: ' + ', '.join(failed) + ')' if failed else ''}. Report written to {out_path}. Send it to Claude.")
        ctx.save()
        return 1 if failed else 0
    run("names", names)
    run("census", lambda: census(ctx, state["objs"]))
    run("definitions", defs)
    run("attributes", lambda: attributes(ctx))
    run("pools", pool)
    run("enemies", lambda: enemies(ctx, state["pool_info"]))
    run("art", lambda: art(ctx, state["objs"], state["info"]["fragments"]))
    run("hud", lambda: hud_movies(ctx))
    run("sounds", lambda: sounds(ctx, bl2, state["scan"], not a.no_audio))
    ctx.say("")
    ctx.say(f"Finished{' (sections that failed: ' + ', '.join(failed) + ')' if failed else ''}. Report written to {out_path}. Send it to Claude.")
    ctx.save()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
