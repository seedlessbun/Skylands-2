"""Skyrim's progression rules, played from Borderlands events. No game imports: testable offline.

state (saved per Borderlands character):
    race: RACE editor id, "" until chosen
    skills: {AVIF edid: {"level": int, "xp": float}}
    perks: [perk form ids taken, every rank]
    level: Dragonborn (character) level
    char_xp: progress toward the next character level
    points: unspent perk points
"""

from __future__ import annotations

from dataclasses import dataclass

from . import sheet_data as sheets

FORMULA_GMST = {
    "f_level_base": "fXPLevelUpBase",
    "f_level_mult": "fXPLevelUpMult",
    "f_xp_per_rank": "fXPPerSkillRank",
    "f_skill_curve": "fSkillUseCurve",
    "f_skill_start": "iAVDSkillStart",
}


@dataclass
class Event:
    kind: str  # skill_up | level_up | word_learned
    skill: str = ""
    value: int = 0


class Rules:
    """Skyrim data (from skyrim.data.load) plus the sheets."""

    def __init__(self, skyrim: dict) -> None:
        self.skyrim = skyrim
        self.missing_formulas: list[str] = []
        self.formula: dict[str, float] = {}
        for fid, row in sheets.FORMULAS.items():
            gmst = FORMULA_GMST.get(fid)
            if gmst is None:
                self.formula[fid] = float(row.fallback)
            elif gmst in skyrim.get("gmst", {}):
                self.formula[fid] = float(skyrim["gmst"][gmst])
            else:
                self.formula[fid] = float(row.fallback)
                self.missing_formulas.append(gmst)
        self.skill_by_edid = {row.avif_edid: row for row in sheets.SKILLS.values()}
        self.missing_skills = [e for e in self.skill_by_edid if e not in skyrim.get("skills", {})]

    # ---- numbers -------------------------------------------------------------------------
    @property
    def start(self) -> int:
        return int(self.formula["f_skill_start"])

    @property
    def max_skill(self) -> int:
        return int(self.formula["f_skill_max"])

    def avsk(self, edid: str) -> list[float]:
        return self.skyrim["skills"][edid]["avsk"]

    def skill_xp_needed(self, edid: str, level: int) -> float:
        _use, _off, improve_mult, improve_offset = self.avsk(edid)
        return max(1.0, improve_mult * level ** self.formula["f_skill_curve"] + improve_offset)

    def skill_xp_for_use(self, edid: str, base_xp: float) -> float:
        use_mult, use_offset, _im, _io = self.avsk(edid)
        return max(0.0, use_mult * base_xp + use_offset)

    def char_xp_needed(self, level: int) -> float:
        return max(1.0, self.formula["f_level_base"] + self.formula["f_level_mult"] * level)

    # ---- characters ----------------------------------------------------------------------
    def new_state(self) -> dict:
        return {"race": "", "skills": {}, "perks": [], "level": 1, "char_xp": 0.0, "points": 0}

    def choose_race(self, state: dict, race_edid: str) -> None:
        race = next(r for r in self.skyrim["races"] if r["edid"] == race_edid)
        by_index = {str(row.av_index): row.avif_edid for row in sheets.SKILLS.values()}
        state["race"] = race_edid
        state["skills"] = {e: {"level": self.start, "xp": 0.0} for e in self.skill_by_edid}
        for av, bonus in race["boosts"].items():
            if av in by_index:
                state["skills"][by_index[av]]["level"] += int(bonus)

    def skill_level(self, state: dict, edid: str) -> int:
        return int(state["skills"].get(edid, {}).get("level", self.start))

    # ---- earning -------------------------------------------------------------------------
    def add_use(self, state: dict, skill_id: str, units: float = 1.0) -> list[Event]:
        """A Borderlands event that counts as using a skill (xp_sources sheet)."""
        row = sheets.SKILLS[skill_id]
        base = sheets.XP_SOURCES[row.xp_source].base_xp * units
        return self.add_skill_xp(state, row.avif_edid, self.skill_xp_for_use(row.avif_edid, base))

    def add_skill_xp(self, state: dict, edid: str, xp: float) -> list[Event]:
        if not state.get("race") or edid not in state["skills"]:
            return []
        s = state["skills"][edid]
        events: list[Event] = []
        if s["level"] >= self.max_skill:
            return events
        s["xp"] += xp
        while s["level"] < self.max_skill:
            need = self.skill_xp_needed(edid, s["level"])
            if s["xp"] < need:
                break
            s["xp"] -= need
            s["level"] += 1
            events.append(Event("skill_up", edid, s["level"]))
            events += self.add_char_xp(state, self.formula["f_xp_per_rank"] * s["level"])
        if s["level"] >= self.max_skill:
            s["xp"] = 0.0
        return events

    def add_char_xp(self, state: dict, xp: float) -> list[Event]:
        events: list[Event] = []
        state["char_xp"] += xp
        while state["char_xp"] >= self.char_xp_needed(state["level"]):
            state["char_xp"] -= self.char_xp_needed(state["level"])
            state["level"] += 1
            state["points"] += int(self.formula["f_perks_per_level"])
            events.append(Event("level_up", value=state["level"]))
            for row in sheets.SHOUT.values():
                if row.unlock_level == state["level"]:
                    events.append(Event("word_learned", value=row.words))
        return events

    # ---- shout ---------------------------------------------------------------------------
    def words_known(self, state: dict) -> int:
        return max((r.words for r in sheets.SHOUT.values() if r.unlock_level <= state["level"]), default=0)

    def shout_cooldown(self, words: int) -> float:
        return float(self.skyrim["shout"]["words"][words - 1]["recharge"])

    # ---- perks ---------------------------------------------------------------------------
    def perk_ranks(self, first_perk: int) -> list[int]:
        chain, seen = [], set()
        p = first_perk
        while p and p not in seen and str(p) in self.skyrim["perks"]:
            chain.append(p)
            seen.add(p)
            p = self.skyrim["perks"][str(p)]["next"]
        return chain

    def tree(self, edid: str) -> list[dict]:
        """Perk nodes of a skill (root excluded), each with ranks and parents."""
        nodes = self.skyrim["skills"][edid]["nodes"]
        by_index = {n["index"]: n for n in nodes}
        parents: dict[int, list[int]] = {}
        for n in nodes:
            for c in n["children"]:
                parents.setdefault(c, []).append(n["index"])
        out = []
        for n in nodes:
            if not n["perk"] or str(n["perk"]) not in self.skyrim["perks"]:
                continue
            out.append({
                "index": n["index"],
                "ranks": self.perk_ranks(n["perk"]),
                "parents": [p for p in parents.get(n["index"], []) if p in by_index],
                "x": n["x"], "y": n["y"],
            })
        out.sort(key=lambda n: (n["y"], n["x"]))
        return out

    def node_owned_ranks(self, state: dict, node: dict) -> int:
        owned = set(state["perks"])
        return sum(1 for p in node["ranks"] if p in owned)

    def node_status(self, state: dict, edid: str, node: dict) -> tuple[str, int]:
        """('maxed'|'available'|'locked_skill'|'locked_parent'|'no_points', required skill)."""
        have = self.node_owned_ranks(state, node)
        if have >= len(node["ranks"]):
            return "maxed", 0
        nxt = self.skyrim["perks"][str(node["ranks"][have])]
        req = int(nxt["skill_req"])
        nodes = {n["index"]: n for n in self.skyrim["skills"][edid]["nodes"]}
        parent_ok = not node["parents"] or any(
            not nodes[p]["perk"] or nodes[p]["perk"] in set(state["perks"]) for p in node["parents"]
        )
        if not parent_ok:
            return "locked_parent", req
        if self.skill_level(state, edid) < req:
            return "locked_skill", req
        if state["points"] <= 0:
            return "no_points", req
        return "available", req

    def take_perk(self, state: dict, edid: str, node: dict) -> int | None:
        status, _ = self.node_status(state, edid, node)
        if status != "available":
            return None
        perk = node["ranks"][self.node_owned_ranks(state, node)]
        state["perks"].append(perk)
        state["points"] -= 1
        return perk

    def perks_in_tree(self, state: dict, edid: str) -> int:
        return sum(self.node_owned_ranks(state, n) for n in self.tree(edid))

    # ---- effects -------------------------------------------------------------------------
    def magnitude(self, state: dict, skill_id: str) -> float:
        """Effect size in percent (effects sheet), from skill level and perks taken."""
        row = sheets.SKILLS[skill_id]
        if not state.get("race"):
            return 0.0
        over = max(0, self.skill_level(state, row.avif_edid) - self.start)
        perks = self.perks_in_tree(state, row.avif_edid) if row.avif_edid in self.skyrim["skills"] else 0
        return min(row.cap, row.per_level * over + row.per_perk * perks)

    def pandora_text(self, state: dict, skill_id: str) -> str:
        row = sheets.SKILLS[skill_id]
        v = self.magnitude(state, skill_id)
        return sheets.EFFECTS[row.effect].pandora_text.format(v=f"{v:.1f}".rstrip("0").rstrip("."))
