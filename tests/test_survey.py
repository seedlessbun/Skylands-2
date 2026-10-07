import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_bl2  # noqa: E402
import fake_skyrim  # noqa: E402
from skylands_setup import survey  # noqa: E402


def test_survey_end_to_end(tmp_path):
    bl2 = tmp_path / "Borderlands 2"
    cooked = bl2 / "WillowGame" / "CookedPCConsole"
    cooked.mkdir(parents=True)
    (cooked / "GD_Assassin_Skills.upk").write_bytes(fake_bl2.skills_package())
    (cooked / "GD_Assassin_Broken.upk").write_bytes(b"garbage")
    loc = bl2 / "WillowGame" / "Localization" / "INT"
    loc.mkdir(parents=True)
    (loc / "GD_Assassin_Skills.int").write_bytes("[Skill_Deception SkillDefinition]\r\nSkillName=Decepti0n\r\n".encode("utf-16-le"))
    sky = fake_skyrim.build(tmp_path / "sky")
    out = tmp_path / "report.json"
    assert survey.main(["--bl2", str(bl2), "--skyrim", str(sky), "--out", str(out)]) == 0
    rep = json.loads(out.read_text())
    assert "fatal" not in rep, rep.get("fatal")
    t = rep["bl2"]["targets"]["b_skill_assassin"]
    assert t["found"] and t["class"] == "SkillDefinition"
    assert t["properties"]["InitialDuration"] == 6.5
    assert any("error" in s for s in rep["bl2"]["targets"]["b_class_assassin"]["searched"])
    assert rep["bl2"]["localization_hits"][0]["file"] == "GD_Assassin_Skills.int"
    assert rep["skyrim"]["localized"] is True
