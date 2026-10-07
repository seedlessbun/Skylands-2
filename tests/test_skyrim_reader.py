import os
import random
import sys
from pathlib import Path

import lz4.frame
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mod"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_skyrim  # noqa: E402
from skylands.skyrim import data as sdata  # noqa: E402
from skylands.skyrim.bsa import BSA  # noqa: E402
from skylands.skyrim.lz4 import decompress_frame  # noqa: E402


@pytest.mark.parametrize("size", [0, 1, 100, 70_000, 300_000])
def test_lz4_roundtrip(size):
    rnd = random.Random(size)
    text = bytes(rnd.choice(b"abcdefgh  \n") for _ in range(size)) + os.urandom(size // 10)
    for kwargs in ({}, {"block_linked": False}, {"block_checksum": True, "content_checksum": True},
                   {"store_size": False}, {"compression_level": 12}):
        assert decompress_frame(lz4.frame.compress(text, **kwargs)) == text


@pytest.fixture(scope="module")
def install(tmp_path_factory):
    return fake_skyrim.build(tmp_path_factory.mktemp("skyrim"))


def test_bsa_lists_and_reads(install):
    bsa = BSA(install / "Data" / "Skyrim - Interface.bsa")
    assert "strings\\skyrim_english.strings" in bsa.entries
    assert bsa.read("interface/fonts_en.swf") == b"not used"


def test_build_reads_everything(install):
    d = sdata.build(install)
    assert d["language"] == "english"
    assert d["gmst"] == {"fXPLevelUpBase": 75.0, "fXPLevelUpMult": 25.0, "fXPPerSkillRank": 1.0,
                         "fSkillUseCurve": 1.95, "iAVDSkillStart": 15.0}
    oh = d["skills"]["AVOneHanded"]
    assert oh["name"] == "One-Handed"
    assert oh["desc"].startswith("The art of fighting")
    assert oh["avsk"] == [6.3, 0.0, 0.25, 0.0]
    assert [n["perk"] for n in oh["nodes"]] == [0, 0x000BABE4, 0x00052D52]
    assert oh["nodes"][0]["children"] == [1] and oh["nodes"][1]["children"] == [2]
    assert oh["nodes"][1]["h"] == 0.5
    assert "AVHealth" not in d["skills"]  # no AVSK -> not a skill
    a1 = d["perks"][str(0x000BABE4)]
    assert a1["name"] == "Armsman" and a1["next"] == 0x00079342 and a1["skill_req"] == 0
    assert d["perks"][str(0x00079342)]["skill_req"] == 20
    assert d["perks"][str(0x00052D52)]["name"] == "Fighting Stance"  # compressed record
    assert [r["name"] for r in d["races"]] == ["Breton", "Nord"]  # vampire and unplayable skipped
    nord = next(r for r in d["races"] if r["edid"] == "NordRace")
    assert nord["boosts"] == {"7": 10, "6": 5, "9": 5}
    s = d["shout"]
    assert s["name"] == "Unrelenting Force"
    assert [(w["name"], w["translation"], w["recharge"]) for w in s["words"]] == [
        ("Fus", "Force", 15.0), ("Ro", "Balance", 20.0), ("Dah", "Push", 45.0)]
    assert d["greeting"].startswith("Hey, you. You're finally awake")


def test_load_caches(install, tmp_path):
    cache = tmp_path / "cache.json"
    first = sdata.load(install, cache)
    assert cache.is_file()
    second = sdata.load(install, cache)
    assert second["skills"] == first["skills"]


def test_missing_skyrim(tmp_path):
    with pytest.raises(sdata.SkyrimNotFound):
        sdata.load(tmp_path)
