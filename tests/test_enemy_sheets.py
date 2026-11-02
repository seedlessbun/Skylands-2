"""The enemy stats and Badass tier sheets: lookups by race editor id give the class the roadmap means, and the tiers grow in order."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "setup"))

from skylands_setup import sheet_data as S  # noqa: E402


def class_of(race_edid: str) -> str:
    for row in S.ENEMY_STATS.values():
        if re.search(row.race_pattern, race_edid):
            return row.id
    return "creature (no row)"


def test_race_lookups_pick_the_intended_class():
    for race, want in (("NordRace", "person"), ("NordRaceVampire", "person"), ("DraugrRace", "draugr"), ("WolfRace", "wolf"), ("DragonRace", "dragon"),
                       ("UndeadDragonRace", "dragon"), ("AlduinRace", "dragon"), ("DragonPriestRace", "dragon_priest"), ("FrostbiteSpiderRaceGiant", "spider"),
                       ("DwarvenCenturionRace", "dwarven"), ("DeerRace", "critter"), ("ElkRace", "critter"), ("TrollFrostRace", "troll")):
        assert class_of(race) == want, (race, class_of(race))


def test_enemy_stat_rows_are_well_formed():
    for row in S.ENEMY_STATS.values():
        re.compile(row.race_pattern)
        assert row.kind in ("person", "creature", "dragon", "critter")
        assert row.badass in ("yes", "no") and row.boss in ("always", "level", "no")
        assert 0.0 <= row.drop_scale <= 1.0 and 1 <= row.min_rarity <= 6
        assert row.health_mult > 0 and row.damage_mult > 0
    # the user's rules: creatures drop at half the people's rate, dragons are bosses, critters drop nothing
    assert S.ENEMY_STATS["wolf"].drop_scale == 0.5 * S.ENEMY_STATS["person"].drop_scale
    assert S.ENEMY_STATS["dragon"].boss == "always" and S.ENEMY_STATS["dragon"].min_rarity >= 3
    assert S.ENEMY_STATS["critter"].drop_scale == 0.0 and S.ENEMY_STATS["critter"].badass == "no"


def test_tiers_grow_in_order_and_badass_starts_at_level_one():
    tiers = [S.BADASS_TIERS[t] for t in ("badass", "super", "ultimate")]
    assert tiers[0].player_level_gate == 1  # the user's choice
    for a, b in zip(tiers, tiers[1:]):
        assert a.player_level_gate < b.player_level_gate
        for col in ("health_mult", "damage_mult", "speed_mult", "size_mult", "rarity_shift", "min_rarity"):
            assert getattr(a, col) <= getattr(b, col), col
        assert a.percent >= b.percent
    for t in tiers:
        assert t.percent <= t.max_percent and t.name_prefix.endswith("Badass")
