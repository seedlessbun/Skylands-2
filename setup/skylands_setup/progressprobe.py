"""python -m skylands_setup bl2progress [--bl2 DIR] [--out FILE] [--minutes N]: how Borderlands 2 does experience, challenges and Badass Rank (changes nothing).

Planning survey for character progression (docs/progression-roadmap.md). Nothing about BL2's experience, challenge or Badass Rank objects has been read yet, and
their class and group names are UNCONFIRMED, so everything is found by NAME (name tables, the index's group and top-level names), never by a guessed path:
  P0  names in every package's name table that say experience / level / challenge / badass rank / token, and which packages hold them
  P1  experience: every group whose name says experience / xp / level-up, plus GD_Globals; each object in them with its properties (kill XP formulas, the level curve),
      then a breadth-first follow of the XP-named ones (formulas, attribute initialisations, curves)
  P2  challenges: every group whose name says challenge; each object with a challenge-like class in one line (name, levels, thresholds, rewards), a few in full,
      a census by class and by the first word of the name
  P3  Badass Rank: groups and objects named badass + rank / reward / token / point / stat / bonus (the token stats and their diminishing-returns curve)
  P4  class defaults (Default__ objects) whose names say experience, challenge, badass, globals or player controller
Each section runs on its own and the report is saved after each one. Packages are opened ONCE each (lesson of 0.45.2: never loop group_objects over many groups).

--deep (0.53.3): the objects the first report (TestBuild-166) named but only summarised, dumped in full by the paths that report gave (not guessed):
  D1  whole groups: GD_AI_Balance.XP (XP multiplier per enemy kind and Badass tier), GD_Balance_Experience.Formulas, GD_Challenges.BadassSkill (the token bonus curves),
      GD_Challenges.BadassRewards, and the combat / loot challenge groups of GD_Challenges (each challenge's Levels: goals and rank points)
  D2  single objects: GD_Globals.General.Globals (ExpScaleByLevelDifference, ExpAwardWeights, the formulas), the Default__ objects of the player controller, experience pool,
      globals and challenge classes
  D3  a two-level follow of what those refer to (Init_BadassPointsReward, the bonus formulas' attributes)
"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import steam
from .badassprobe import objects_in_groups
from .bl2 import upk
from .bl2.index import Index
from .gestaltprobe import show
from .shieldprobe import Ctx, brief, follow

VERSION = 2
XP = re.compile(r"(?i)(experience|(^|[_.])xp($|[_.\d])|xpreward|explevel|exppoints|expreward|levelup|level_up|playerlevel|expscale|expmultiplier)")
CHALLENGE = re.compile(r"(?i)challenge")
RANK = re.compile(r"(?i)badass.*(rank|reward|token|point|stat|bonus|level)|(rank|reward|token).*badass")
ANY = re.compile(r".")
CHALLENGE_CLASS = re.compile(r"(?i)(challenge|reward|badass|level)")
RANK_CLASS = re.compile(r"(?i)(badass|rank|reward|token|attribute|resolver|init|stat|curve|definition)")
DEFAULTS = re.compile(r"(?i)^default__.*(experience|challenge|badass|globals|playercontroller|playerreplicationinfo|levelup)")
MAX_GROUPS = 160  # per section: more would open half the install


def name_scan(ctx: Ctx, upks: list[Path]) -> dict:
    ctx.head("P0. Names in the packages (experience, challenges, badass rank)")
    t0 = time.time()
    found: dict[str, dict[str, set[str]]] = {"xp": defaultdict(set), "challenge": defaultdict(set), "rank": defaultdict(set)}
    unreadable = 0
    for n, p in enumerate(upks):
        try:
            names = upk.read_name_set(p)
        except Exception:  # noqa: BLE001
            unreadable += 1
            continue
        for name in names:
            if XP.search(name):
                found["xp"][name].add(p.stem)
            if CHALLENGE.search(name):
                found["challenge"][name].add(p.stem)
            if RANK.search(name):
                found["rank"][name].add(p.stem)
        if n % 300 == 0:
            print(f"  {n}/{len(upks)} name tables", flush=True)
    ctx.say(f"name tables read in {time.time() - t0:.0f} s ({unreadable} unreadable): " + ", ".join(f"{k} {len(v)} names" for k, v in found.items()))
    for kind, cap in (("xp", 500), ("challenge", 900), ("rank", 400)):
        names = found[kind]
        ctx.say(f"{kind} names ({len(names)}), most-named first:")
        for name, owners in sorted(names.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:cap]:
            ctx.put(f"  {len(owners):4}  {name}  [{', '.join(sorted(owners)[:3])}]")
    ctx.save()
    return found


def groups_like(ix: Index, rx: re.Pattern, extra=()) -> list[str]:
    out = [g for g in ix.groups if rx.search(g) or g.startswith(tuple(extra))]
    # the groups that hold the most objects first (definitions live there; a stray copy in a level package holds one or two)
    out.sort(key=lambda g: -ix.groups[g][0][1])
    return out


def dump_groups(ctx: Ctx, groups: list[str], class_re: re.Pattern, label: str, line: int) -> list[tuple[str, str, dict | None]]:
    if len(groups) > MAX_GROUPS:
        ctx.say(f"{label}: {len(groups)} groups, only the {MAX_GROUPS} biggest are read; the rest: {groups[MAX_GROUPS:MAX_GROUPS + 200]}")
        groups = groups[:MAX_GROUPS]
    ctx.say(f"{label} groups: {groups}")
    found = objects_in_groups(ctx, groups, class_re, keep_props=lambda _p: True, label=label)
    by_class = Counter(c for _p, c, _x in found)
    ctx.say(f"{len(found)} objects; by class: {dict(by_class.most_common(40))}")
    for path, cls, props in sorted(found):
        ctx.put(f"  {path} [{cls}] {brief(props, line) if props else '(no properties read)'}")
    ctx.save()
    return found


def experience(ctx: Ctx) -> None:
    ctx.head("P1. Experience: kill XP, the level curve, XP scaling")
    ix = ctx.ix
    groups = groups_like(ix, XP, extra=("gd_globals.", "gd_balance_experience", "gd_experience", "d_attributes.experience", "gd_levels"))
    found = dump_groups(ctx, groups, ANY, "experience", 900)
    seeds = [p for p, _c, _x in found if XP.search(p.rsplit(".", 1)[-1])]
    # top-level names that say experience (a package of their own) are read through the index's top-level table
    tops = sorted(k for k in ix.top if XP.search(k))[:60]
    ctx.say(f"top-level names that say experience: {tops}")
    seeds += [p for t in tops for p in ix.children(t)][:80]
    seeds = list(dict.fromkeys(seeds))
    ctx.say(f"{len(seeds)} experience objects followed in full")
    follow(ctx, seeds[:200], depth=2, cap=320, lines_each=260, title="experience", fanout=30)


def challenges(ctx: Ctx) -> None:
    ctx.head("P2. Challenges (Badass Rank challenges: names, levels, thresholds, rank points)")
    ix = ctx.ix
    groups = groups_like(ix, CHALLENGE)
    found = dump_groups(ctx, groups, CHALLENGE_CLASS, "challenges", 1400)
    words = Counter(re.split(r"[_\d]", p.rsplit(".", 1)[-1])[0].lower() for p, _c, _x in found)
    ctx.say(f"first words of the challenge names: {dict(words.most_common(60))}")
    # a few of each class in full, down to what they refer to (levels, reward and stat objects)
    per: dict[str, list[str]] = defaultdict(list)
    for p, c, _x in found:
        if len(per[c]) < 6:
            per[c].append(p)
    seeds = [p for v in per.values() for p in v]
    follow(ctx, seeds, depth=2, cap=220, lines_each=300, title="challenges", fanout=25)


def badass_rank(ctx: Ctx) -> None:
    ctx.head("P3. Badass Rank and tokens: the stats a token raises, the curve, rank thresholds")
    ix = ctx.ix
    groups = groups_like(ix, RANK)
    found = dump_groups(ctx, groups, RANK_CLASS, "badass rank", 1400) if groups else []
    tops = sorted(k for k in ix.top if RANK.search(k))[:40]
    ctx.say(f"top-level names that say badass rank: {tops}")
    seeds = [p for p, _c, _x in found][:120] + [p for t in tops for p in ix.children(t)][:60]
    follow(ctx, list(dict.fromkeys(seeds)), depth=2, cap=260, lines_each=300, title="badass rank", fanout=30)


def defaults(ctx: Ctx) -> None:
    ctx.head("P4. Class defaults (Default__ objects) about experience, challenges, badass rank, globals")
    ix = ctx.ix
    names = sorted(k for k in ix.top if DEFAULTS.search(k))[:80]
    ctx.say(f"{len(names)} default objects: {names}")
    for name in names:
        if ctx.out_of_time():
            ctx.say("(time is up)")
            break
        try:
            props = ix.props(name)
        except Exception as e:  # noqa: BLE001
            ctx.put(f"  {name}: {type(e).__name__}")
            continue
        ctx.put(f"  {name} {brief(props, 2400) if props else '(no properties read)'}")
    ctx.save()


DEEP_GROUPS = ("gd_ai_balance.xp", "gd_balance_experience.formulas", "gd_balance_experience.attributes", "gd_challenges.badassskill", "gd_challenges.badassrewards")
# the challenge groups of the base game worth keeping (combat, loot, kinds of enemy); level, echo, vehicle, economy and duel challenges cannot be counted in Skyrim
DEEP_CHALLENGE_SKIP = ("levelchallenges", "levelechochallenges", "vehicles", "economy", "dueling", "challengelist", "categories")
DEEP_OBJECTS = ("GD_Globals.General.Globals", "Default__WillowPlayerController", "Default__ExperienceResourcePool", "Default__GlobalsDefinition", "Default__ChallengeDefinition",
                "Default__BadassRewardDefinition", "Default__WillowPlayerReplicationInfo")


def deep_groups(ctx: Ctx) -> list[str]:
    ctx.head("D1. In full: XP multipliers, experience formulas, Badass Rank bonus curves, and the combat / loot challenges with their levels")
    ix = ctx.ix
    groups = [g for g in DEEP_GROUPS if g in ix.groups]
    groups += sorted(g for g in ix.groups if g.startswith("gd_challenges.") and g.count(".") == 1 and not g.endswith(DEEP_CHALLENGE_SKIP) and g not in groups)
    missing = [g for g in DEEP_GROUPS if g not in ix.groups]
    ctx.say(f"groups: {groups}" + (f"; not in this install: {missing}" if missing else ""))
    found = objects_in_groups(ctx, groups, ANY, keep_props=lambda _p: True, label="deep")
    ctx.say(f"{len(found)} objects; by class: {dict(Counter(c for _p, c, _x in found).most_common(30))}")
    for path, cls, props in sorted(found):
        if ":" in path:
            continue
        ctx.put("")
        ctx.put(f"--- {path} [{cls}]")
        for line in show(props or {}, 1, [400]):
            ctx.put(line)
    ctx.save()
    return [p for p, _c, _x in found if ":" not in p]


def deep_objects(ctx: Ctx) -> None:
    ctx.head("D2. In full: the globals (XP by level difference, award weights) and the class defaults")
    ix = ctx.ix
    for path in DEEP_OBJECTS:
        if ctx.out_of_time():
            ctx.say("(time is up)")
            break
        try:
            props = ix.props(path)
        except Exception as e:  # noqa: BLE001
            ctx.put(f"--- {path}: {type(e).__name__}: {str(e)[:120]}")
            continue
        ctx.put("")
        ctx.put(f"--- {path}" + ("" if props else " (not found or no properties)"))
        for line in show(props or {}, 1, [1500]):
            ctx.put(line)
    ctx.save()


def deep_follow(ctx: Ctx, seeds: list[str]) -> None:
    ctx.head("D3. What those objects refer to (reward formulas, attributes)")
    keep = [p for p in seeds if re.search(r"(?i)(badassskill|badassreward|\.xp\.|formulas)", p)]
    keep += [p for p in seeds if re.search(r"(?i)gd_challenges\.weapons\.smg_kills$", p)]  # one ordinary challenge, to see where its rank points come from
    follow(ctx, list(dict.fromkeys(keep))[:120] + ["GD_Globals.General.Globals"], depth=2, cap=300, lines_each=400, title="deep", fanout=30)


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="skylands bl2progress")
    ap.add_argument("--bl2")
    ap.add_argument("--out", default="BL2-Progress-Report.txt")
    ap.add_argument("--minutes", type=float, default=25.0, help="time allowed for reading packages (the index is extra)")
    ap.add_argument("--deep", action="store_true", help="the objects the first report named, in full (D1-D3)")
    a = ap.parse_args(argv)
    bl2 = Path(a.bl2) if a.bl2 else steam.find("bl2")
    out_path = Path(a.out)
    ctx = Ctx(None, out_path, time.time() + a.minutes * 60)
    ctx.say(f"skylands bl2progress {VERSION}{' --deep' if a.deep else ''}  {time.strftime('%Y-%m-%d %H:%M:%S')}")
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
    for label, rx in (("experience", XP), ("challenge", CHALLENGE), ("badass rank", RANK)):
        ctx.say(f"groups whose name says {label}: {sorted(g for g in ix.groups if rx.search(g))[:150]}")
    ctx.save()
    failed: list[str] = []

    def run(name: str, fn) -> None:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            import traceback

            failed.append(name)
            ctx.say(f"SECTION '{name}' FAILED: {type(e).__name__}: {e}")
            ctx.put(traceback.format_exc())
            ctx.save()

    if a.deep:
        state: dict = {"seeds": []}

        def d1() -> None:
            state["seeds"] = deep_groups(ctx)

        run("deep groups", d1)
        run("deep objects", lambda: deep_objects(ctx))
        run("deep follow", lambda: deep_follow(ctx, state["seeds"]))
        ctx.say("")
        ctx.say(f"Finished{' (sections that failed: ' + ', '.join(failed) + ')' if failed else ''}. Report written to {out_path}. Send it to Claude.")
        ctx.save()
        return 1 if failed else 0
    run("names", lambda: name_scan(ctx, list(ix.files)))
    run("experience", lambda: experience(ctx))
    run("challenges", lambda: challenges(ctx))
    run("badass rank", lambda: badass_rank(ctx))
    run("defaults", lambda: defaults(ctx))
    ctx.say("")
    ctx.say(f"Finished{' (sections that failed: ' + ', '.join(failed) + ')' if failed else ''}. Report written to {out_path}. Send it to Claude.")
    ctx.save()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
