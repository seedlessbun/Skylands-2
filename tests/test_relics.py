"""Relic items (relics.py): the records, the keyword numbers the plugin reads, the loot lists they join."""
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_skyrim  # noqa: E402
import test_generate  # noqa: E402

from skylands_setup import generate, relics  # noqa: E402
from skylands_setup.skyrim.esm import read_plugin  # noqa: E402


def test_keyword_numbers_follow_borderlands_2s_formula():
    vit = relics.KINDS[0]
    # level x 0.004 + grade x 0.02 (the deep survey): at grade 3 the flat part is 0.06
    assert relics.keyword_text(vit, 3, 3) == "SkylandsRelic_l3_h400x6000"
    prot = next(k for k in relics.KINDS if k.id == "protection")
    assert relics.keyword_text(prot, 5, 9) == "SkylandsRelic_l5_s300x9000_r300x9000"
    assert "Health +0.4% per character level, +6% on top" in relics.stats_text(vit, 3, 3)


def test_the_slot_is_not_the_shields(tmp_path):
    assert relics.choose_slot(tmp_path / "nothing", taken=60)[0] == 61
    assert relics.choose_slot(tmp_path / "nothing", wanted=44, taken=60)[0] == 44
    assert relics.choose_slot(tmp_path / "nothing", wanted=60, taken=60)[0] == 61


def test_the_install_writes_relics_beside_the_shields(tmp_path):
    bl2 = test_generate.staff_bl2(tmp_path)
    plain = generate.generate(bl2, fake_skyrim.build_full(tmp_path / "sky0"), tmp_path / "out0", gun_models="proxy", shooting="staff")
    rep = generate.generate(bl2, fake_skyrim.build_full(tmp_path / "sky"), tmp_path / "out", gun_models="proxy", shooting="staff", shield_slot=60, relic_slot=59)
    assert rep["relics"]["items"] == len(relics.KINDS) * 5 * 2 and rep["relics"]["slot"] == 59
    assert (tmp_path / "out" / "Data" / "Skylands.esp").read_bytes() == (tmp_path / "out0" / "Data" / "Skylands.esp").read_bytes()
    _, recs = read_plugin(tmp_path / "out" / "Data" / "SkylandsGunModels.esp", {"ARMO", "KYWD", "LVLI", "FLST"})
    kyw = {r.form_id: r.edid for r in recs["KYWD"]}
    mine = [a for a in recs["ARMO"] if a.edid.startswith("SkylandsRelic_")]
    assert len(mine) == rep["relics"]["items"]
    for a in mine:
        assert struct.unpack("<II", a.first("BOD2")) == (1 << 29, 2)  # slot 59
        names = [kyw.get(k, "") for k in struct.unpack_from(f"<{len(a.first('KWDA')) // 4}I", a.first("KWDA"))]
        assert "SkylandsRelic" in names and sum(n.startswith("SkylandsRelic_l") for n in names) == 1
    lists = {r.edid for r in recs["LVLI"]}
    assert {"SkylandsRelicTier_1", "SkylandsRelicsAny", "SkylandsRelicsGood", "SkylandsRelicStock", "SkylandsShieldsAny"} <= lists
    beams = [r for r in recs["FLST"]]
    assert beams and len(beams[0].all("LNAM")) >= rep["relics"]["items"] + rep["shields"]["items"]
    assert (tmp_path / "out" / "Data" / "Meshes" / "Skylands" / "Relics" / "relic_3.nif").is_file()
