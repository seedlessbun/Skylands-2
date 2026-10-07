import os
import random
import sys
from pathlib import Path

import lz4.frame
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_skyrim  # noqa: E402
from skylands_setup.skyrim.bsa import BSA  # noqa: E402
from skylands_setup.skyrim.esm import is_localized, read_plugin  # noqa: E402
from skylands_setup.skyrim.lz4 import decompress_frame  # noqa: E402
from skylands_setup.skyrim.strings import parse_table  # noqa: E402


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


def test_bsa_and_strings(install):
    bsa = BSA(install / "Data" / "Skyrim - Interface.bsa")
    assert bsa.read("interface/fonts_en.swf") == b"not used"
    names = parse_table(bsa.read("strings/skyrim_english.strings"), False)
    assert names[3] == "Nord"
    dl = parse_table(bsa.read("strings/skyrim_english.dlstrings"), True)
    assert dl[102].startswith("One-handed weapons")


def test_plugin_records(install):
    tes4, recs = read_plugin(install / "Data" / "Skyrim.esm", {"PERK", "RACE", "SHOU", "GMST"})
    assert is_localized(tes4)
    assert {r.edid for r in recs["RACE"]} >= {"NordRace", "BretonRace"}
    stance = next(r for r in recs["PERK"] if r.edid == "FightingStance")  # compressed record
    assert stance.first("CTDA") is not None
    assert len(recs["GMST"]) == 6
