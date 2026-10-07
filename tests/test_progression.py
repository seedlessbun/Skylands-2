import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mod"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_skyrim  # noqa: E402
from skylands import sheet_data as sheets  # noqa: E402
from skylands.progression import Rules  # noqa: E402
from skylands.skyrim import data as sdata  # noqa: E402


@pytest.fixture(scope="module")
def skyrim(tmp_path_factory):
    d = sdata.build(fake_skyrim.build(tmp_path_factory.mktemp("sky")))
    # The fake install only defines two skills; give the rest a bare entry with the same AVSK.
    for row in sheets.SKILLS.values():
        d["skills"].setdefault(row.avif_edid, {"form_id": 0, "name": row.id, "desc": "", "avsk": [1.0, 0.0, 0.25, 0.0], "nodes": []})
    return d


@pytest.fixture
def rules(skyrim):
    return Rules(skyrim)


def test_formulas_from_skyrim(rules):
    assert rules.missing_formulas == []
    assert rules.start == 15 and rules.max_skill == 100
    assert rules.char_xp_needed(1) == 100  # Skyrim: (level + 3) * 25


def test_race_boosts(rules):
    st = rules.new_state()
    rules.choose_race(st, "NordRace")
    assert rules.skill_level(st, "AVTwoHanded") == 25
    assert rules.skill_level(st, "AVOneHanded") == 20
    assert rules.skill_level(st, "AVSneak") == 15
    assert len(st["skills"]) == 18


def test_no_xp_before_race(rules):
    st = rules.new_state()
    assert rules.add_use(st, "one_handed", 100) == []


def test_skill_and_character_levels(rules):
    st = rules.new_state()
    rules.choose_race(st, "BretonRace")
    events = []
    for _ in range(400):
        events += rules.add_use(st, "one_handed")
    ups = [e for e in events if e.kind == "skill_up"]
    assert ups and ups[0].value == 16
    assert rules.skill_level(st, "AVOneHanded") == ups[-1].value
    # character XP = sum of new skill levels; level 2 needs 100
    gained = sum(e.value for e in ups)
    levels = [e for e in events if e.kind == "level_up"]
    assert st["level"] == 1 + len(levels) and st["points"] == len(levels)
    assert gained >= 100 * (len(levels) > 0)


def test_words_unlock(rules):
    st = rules.new_state()
    rules.choose_race(st, "NordRace")
    assert rules.words_known(st) == 1
    ev = rules.add_char_xp(st, 10_000)
    assert any(e.kind == "word_learned" and e.value == 2 for e in ev)
    assert rules.words_known(st) == 3
    assert rules.shout_cooldown(3) == 45.0


def test_perk_tree_and_ranks(rules):
    st = rules.new_state()
    rules.choose_race(st, "NordRace")
    tree = rules.tree("AVOneHanded")
    armsman, stance = tree
    assert armsman["ranks"] == [0x000BABE4, 0x00079342]
    assert rules.node_status(st, "AVOneHanded", armsman) == ("no_points", 0)
    st["points"] = 3
    assert rules.node_status(st, "AVOneHanded", stance)[0] == "locked_parent"
    assert rules.take_perk(st, "AVOneHanded", armsman) == 0x000BABE4
    # rank 2 needs One-Handed 20: Nord starts at 20
    assert rules.node_status(st, "AVOneHanded", armsman) == ("available", 20)
    assert rules.take_perk(st, "AVOneHanded", armsman) == 0x00079342
    assert rules.node_status(st, "AVOneHanded", armsman)[0] == "maxed"
    assert rules.take_perk(st, "AVOneHanded", stance) == 0x00052D52
    assert st["points"] == 0
    assert rules.perks_in_tree(st, "AVOneHanded") == 3
    # magnitude: (20-15)*0.4 + 3*4 = 14
    assert rules.magnitude(st, "one_handed") == pytest.approx(14.0)
    assert rules.pandora_text(st, "one_handed") == "+14% pistol, SMG and melee damage"


def test_skill_cap(rules):
    st = rules.new_state()
    rules.choose_race(st, "NordRace")
    rules.add_skill_xp(st, "AVOneHanded", 1e12)
    assert rules.skill_level(st, "AVOneHanded") == 100
    assert rules.magnitude(st, "one_handed") == pytest.approx(34.0)
