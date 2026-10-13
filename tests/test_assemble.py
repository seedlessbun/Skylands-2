import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "setup"))

from skylands_setup import assemble  # noqa: E402
from skylands_setup import sheet_data as S  # noqa: E402

GUN = {
    "balance": "GD_Weap_SMG.A_Weapons.SMG_Vladof_3_Rare", "manufacturer": "Vladof", "title": "SMG", "unique_name": "",
    "element_prefixes": {"Shock": "Shocking"},
    "slots": {"Barrel": ["b1", "b2", "b3"], "Body": ["d1", "d2"], "Elemental": ["GD.Elemental.SMG_Elemental_Shock", "GD.Elemental.SMG_Elemental_None"]},
}
PARTS = {
    "b1": {"prefix": "Rapid", "title": "", "effects": [{"attr": "WeaponFireInterval", "type": "scale", "value": 0.5}]},
    "b2": {"prefix": "", "title": "", "effects": [{"attr": "WeaponDamage", "type": "scale", "value": 1.5}]},
    "b3": {"prefix": "", "title": "", "effects": []},
    "d1": {"prefix": "", "title": "Hornet", "effects": []},
    "d2": {"prefix": "", "title": "", "effects": []},
}


def test_effect_multipliers_read_scales_and_fractions():
    assert assemble.effect_multiplier({"type": "scale", "value": 1.2}) == 1.2
    assert assemble.effect_multiplier({"type": "scale", "value": 0.1}) == 1.1   # a small scale value is a fraction
    assert assemble.effect_multiplier({"type": "preadd", "value": -0.2}) == 0.8
    assert assemble.effect_multiplier({"type": "scale", "value": 50.0}) == 1.0   # nonsense stays neutral
    assert assemble.MULT_MIN <= assemble.effect_multiplier({"type": "scale", "value": 3.9}) <= assemble.MULT_MAX


def test_part_effects_map_to_stats_and_fire_interval_is_inverted():
    quick = assemble.part_mods("b1", "Barrel", PARTS["b1"])
    heavy = assemble.part_mods("b2", "Barrel", PARTS["b2"])
    assert quick["fire_rate"] > 1.8       # half the interval, twice the rate (plus a little personality)
    assert heavy["damage"] > 1.4 and quick["damage"] < 1.2


def test_manufacturer_character_and_unknown_makers():
    assert assemble.manufacturer_mods("Vladof")["fire_rate"] > assemble.manufacturer_mods("Jakobs")["fire_rate"]
    assert set(assemble.manufacturer_mods("Nobody").values()) == {1.0}


def test_variants_are_different_combinations_and_repeatable():
    taken: set = set()
    made = [assemble.pick(GUN, PARTS, k, taken) for k in range(6)]
    keys = {tuple(sorted(m["parts"].items())) for m in made}
    assert len(keys) == 6  # 12 combinations exist; six variants never repeat
    again = assemble.pick(GUN, PARTS, 0, set())
    assert again["parts"] == made[0]["parts"]
    assert {m["element"] for m in made} <= {"Shock", None}


def test_names_come_from_parts_then_the_gun_type():
    chosen = {"Barrel": "b1", "Body": "d1"}
    assert assemble.name_of(GUN, chosen, PARTS, None, {"Vladof": "Vladof"}, "Rare") == "Rapid Hornet (Rare)"
    chosen = {"Barrel": "b3", "Body": "d2"}
    assert assemble.name_of(GUN, chosen, PARTS, "Shock", {"Vladof": "Vladof"}, "Rare") == "Shocking SMG (Rare)"
    assert assemble.name_of(GUN, chosen, PARTS, None, {"Vladof": "Vladof"}, "Rare") == "Vladof SMG (Rare)"
    assert assemble.name_of({**GUN, "unique_name": "Bone Shredder"}, chosen, PARTS, None, {}, "Legendary") == "Bone Shredder (Legendary)"


def test_every_sheet_stat_is_known():
    assert {r.stat for r in S.PART_STATS.values()} <= set(assemble.STATS)
