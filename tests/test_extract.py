import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_bl2  # noqa: E402
from skylands_setup.bl2 import extract  # noqa: E402


def test_extract_everything(tmp_path):
    fake_bl2.pandora_install(tmp_path / "bl2")
    d = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    assert d["packages"] == 3
    assert d["rarities"][0] == {"min": 1, "max": 1, "rating": None, "rgb": [255, 255, 255], "alpha": 255}
    assert d["rarities"][1]["rgb"] == [255, 180, 0]
    cls = {c["id"]: c for c in d["classes"]}
    assert cls["assassin"]["character"] == "Zer0" and cls["assassin"]["cooldown"] == 15.0
    assert cls["assassin"]["skill_desc"] == "Action Skill. Press your shout key now."
    assert cls["siren"]["cooldown"] == 42.0 and cls["mechromancer"]["character"] == "Gaige"
    assert cls["mechromancer"]["cooldown"] == 60.0 and cls["mechromancer"]["duration"] == 20.0
    assert "psycho" not in cls and any("class psycho" in e for e in d["errors"])
    guns = {g["balance"].rsplit(".", 1)[1]: g for g in d["weapons"]["guns"]}
    assert guns["Pistol_Jakobs"]["rarity"] == 1 and guns["Pistol_Jakobs_3_Rare"]["rarity"] == 3
    assert guns["Pistol_Jakobs_3_Rare"]["title"] == "Revolver" and guns["Pistol_Jakobs_3_Rare"]["elements"] == ["Fire"]
    assert guns["Pistol_Jakobs_3_Rare"]["element_prefixes"] == {"Fire": "Incendiary"}
    assert guns["Pistol_Jakobs_5_Maggie"]["rarity"] == 5 and guns["Pistol_Jakobs_5_Maggie"]["unique_name"] == "Maggie"
    assert guns["Pistol_Jakobs"]["damage_scale"] == 2.2 and guns["Pistol_Jakobs"]["clip"] == 6
    assert d["weapons"]["manufacturers"] == {"Jakobs": "Jakobs"}
    assert d["enemies"] == {"b_enemy_marauder": "Marauder", "b_enemy_psycho": "Psycho"}
    # cached index gives the same answer
    again = extract.extract(tmp_path / "bl2", tmp_path / "cache")
    assert again["classes"] == d["classes"]


def test_budget_stops_extraction_and_reports(tmp_path):
    fake_bl2.pandora_install(tmp_path / "bl2")
    d = extract.extract(tmp_path / "bl2", None, budget_minutes=1e-9)
    assert any("time budget" in e for e in d["errors"]) and d["log"] and d["log"][0].endswith("Indexing 3 Borderlands 2 packages ...")
