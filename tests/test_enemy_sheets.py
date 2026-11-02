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
        for col in ("health_mult", "melee_damage_mult", "gun_damage_mult", "shield_mult", "speed_mult", "size_mult", "rarity_shift", "min_rarity", "drops"):
            assert getattr(a, col) <= getattr(b, col), col
        assert a.percent >= b.percent
    for t in tiers:
        assert t.percent <= t.max_percent and t.name_prefix.endswith("Badass")
        for col in t.bl2_columns.split():
            assert hasattr(t, col), col


def test_tiers_carry_borderlands_numbers():
    # read from the user's badass survey (tools/badass_report.py): BL2 file values replace the earlier design values
    b, s, u = (S.BADASS_TIERS[t] for t in ("badass", "super", "ultimate"))
    assert (b.health_mult, s.health_mult, u.health_mult) == (3.0, 5.8, 15.0)
    assert b.gun_damage_mult == s.gun_damage_mult == u.gun_damage_mult == 1.14  # the champion factor; guns are the gun's damage
    assert (b.min_rarity, s.min_rarity, u.min_rarity) == (2, 3, 4)  # uncommon, rare, very rare guaranteed
    assert (b.drops, s.drops, u.drops) == (1, 2, 3)  # BL2's 1 / 2 / 3 guaranteed items (the user chose BL2's system)
    for tier in (b, s, u):
        floors = [int(x) for x in tier.drop_floors.split()]
        assert len(floors) == tier.drops and max(floors) == tier.min_rarity
    w = S.ENEMY_DROPS
    assert (w["gun_weight"].value, w["shield_weight"].value, w["relic_weight"].value) == (44.44, 20.0, 8.89)
    assert w["creature_drop_scale"].value == 0.5 and w["creature_drop_scale"].source == "design"


def test_super_and_ultimate_are_rerolls_of_the_badass_chance_and_bosses_get_double_odds():
    b, s, u = (S.BADASS_TIERS[t] for t in ("badass", "super", "ultimate"))
    assert b.roll == "chance" and s.roll == u.roll == "reroll"
    assert (s.percent, s.per_level, s.max_percent) == (u.percent, u.per_level, u.max_percent) == (b.percent, b.per_level, b.max_percent)
    assert b.player_level_gate == 1 and s.player_level_gate == 12 and u.player_level_gate == 25
    assert b.boss_odds == s.boss_odds == u.boss_odds == 2.0
    assert u.melee_damage_mult == s.melee_damage_mult  # the user: keep the Ultimate at the Super's damage
