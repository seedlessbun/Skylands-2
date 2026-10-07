import os
import sys
from pathlib import Path

import lzo
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_bl2  # noqa: E402
from skylands_setup.bl2 import lzo as our_lzo  # noqa: E402
from skylands_setup.bl2 import upk  # noqa: E402


@pytest.mark.parametrize("size", [1, 1000, 0x20000, 300_001])
def test_lzo_matches_reference(size):
    data = (os.urandom(size // 4) + b"pandora " * (size // 8))[:size]
    assert our_lzo.decompress(lzo.compress(data, 1, False), len(data)) == data


@pytest.mark.parametrize("kw", [{"compress": False}, {"compress": True}, {"fully": True}])
def test_package_roundtrip(tmp_path, kw):
    path = tmp_path / "GD_Assassin_Skills.upk"
    path.write_bytes(fake_bl2.skills_package(**kw))
    pkg = upk.open_package(path)
    assert pkg.header["version"] == 832 and pkg.header["licensee"] == 56
    res = pkg.find("GD_Assassin_Skills.Misc.Cooldown_Deception:ConstantAttributeValueResolver_0")
    assert res and upk.object_properties(pkg, res) == {"ConstantValue": 15.0}
    skill = pkg.find("GD_Assassin_Skills.ActionSkill.Skill_Deception")
    props = upk.object_properties(pkg, skill)
    assert props["SkillName"] == "Decepti0n"
    assert props["InitialDuration"] == 6.5
    assert props["bAvailableBaseLevel"] is True
    assert props["DurationType"] == "DURATION_Timed"
    assert props["CooldownAttr"] == "GD_Assassin_Skills.Misc.Cooldown_Deception"
    assert props["Scale(1)"] == 2.0
    levels = props["Levels"]
    assert levels["count"] == 2 and levels["items"][0] == {"MinLevel": 5, "Color": [175, 193, 205, 255]}
    assert "Decepti0n" not in upk.read_names_only(path)  # strings are values, not names
    assert "Skill_Deception" in upk.read_names_only(path)


def test_not_a_package(tmp_path):
    p = tmp_path / "x.upk"
    p.write_bytes(b"nope" * 10)
    with pytest.raises(upk.UPKError):
        upk.open_package(p)
