import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "setup"))

from skylands_setup import sheet_data as S  # noqa: E402
from skylands_setup import stats  # noqa: E402


def rolls(gt, rr, n=2000, element=True):
    return [stats.roll(f"gun{i}", gt, rr, element) for i in range(n)]


def test_rolls_are_repeatable():
    gt, rr = S.GUN_TYPES["smg"], S.RARITIES["rare"]
    assert stats.roll("a", gt, rr, True) == stats.roll("a", gt, rr, True)


def test_ranges_stay_in_borderlands_bands_and_widen_with_rarity():
    for gt in S.GUN_TYPES.values():
        for rr in S.RARITIES.values():
            for s in rolls(gt, rr, 300):
                if s["boosted"] != "fire_rate":
                    assert gt.rate_min <= s["fire_rate"] <= gt.rate_max
                assert gt.reload_min <= s["reload"] <= gt.reload_max
                assert stats.SPEED_MIN <= s["speed"] <= stats.SPEED_MAX
        common = max(s["fire_rate"] for s in rolls(gt, S.RARITIES["common"], 300) if not s["boosted"])
        legendary = max(s["fire_rate"] for s in rolls(gt, S.RARITIES["legendary"], 300) if not s["boosted"])
        assert legendary > common


def test_boosts_are_rare_big_and_only_element_when_the_gun_has_one():
    gt, rr = S.GUN_TYPES["smg"], S.RARITIES["legendary"]
    got = rolls(gt, rr)
    share = sum(1 for s in got if s["boosted"]) / len(got)
    assert abs(share - rr.roll_chance) < 0.04
    assert {s["boosted"] for s in got} == {None, "fire_rate", "crit_damage", "element"}
    assert all(s["boost"] >= rr.boost_min for s in got if s["boosted"])
    assert "element" not in {s["boosted"] for s in rolls(gt, rr, element=False)}
    assert max(s["fire_rate"] for s in got if s["boosted"] == "fire_rate") > gt.rate_max * 1.5


def test_faster_guns_animate_faster():
    smg = [stats.roll(f"s{i}", S.GUN_TYPES["smg"], S.RARITIES["legendary"], False) for i in range(300)]
    sniper = [stats.roll(f"n{i}", S.GUN_TYPES["sniper"], S.RARITIES["common"], False) for i in range(300)]
    assert min(s["speed"] for s in smg if not s["boosted"]) > 2.0
    assert max(s["speed"] for s in sniper if not s["boosted"]) < 1.0
    assert max(s["speed"] for s in smg) > 4.0  # a boosted SMG is frantic
