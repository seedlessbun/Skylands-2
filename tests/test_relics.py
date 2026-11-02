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
    assert relics.keyword_text(vit, 3, 3) == "SkylandsRelic_l3_h1200x6000"
    prot = next(k for k in relics.KINDS if k.id == "protection")
    assert relics.keyword_text(prot, 5, 9) == "SkylandsRelic_l5_s1500x9000_r1500x9000"
    assert "Health +1.2% per character level, +6% on top" in relics.stats_text(vit, 3, 3)


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
    assert (tmp_path / "out" / "Data" / "Meshes" / "Skylands" / "Relics" / "relic_vitality_3.nif").is_file()


def test_relic_models_are_cut_from_the_artifact_gestalt_when_it_is_readable(tmp_path):
    from skylands_setup import meshes as M
    from skylands_setup import relics

    class FakeSource:
        gestalt_table = {n: ("k", 0, 1) for n in ("type_healthbuff", "type_shieldskillskills", "type_elemental", "type_inventory", "type_weapons", "ring_single", "ring_double", "ring_triple")}
        textures: dict = {}

        def _read_gestalt_part(self, part, name):
            assert part == "relic"
            return {"mesh": M.box(0, 0, 0, 1.0, 2.0, 3.0)}

        def _texture(self, path):
            return None

    said: list[str] = []
    colors = {1: (200, 200, 200), 2: (80, 200, 80), 3: (60, 100, 230), 4: (160, 60, 220), 5: (240, 140, 30)}
    got = relics.write_assets(tmp_path, colors, FakeSource(), said.append)
    assert len(got) == 25 and got[("vitality", 5)] == "Skylands\\Relics\\relic_vitality_5.nif"
    assert (tmp_path / "Meshes" / "Skylands" / "Relics" / "relic_aggression_3.nif").is_file()
    assert any("25 cut from Borderlands 2's artifact mesh" in s for s in said)
    # without the mesh every relic is the stand-in ring
    said.clear()
    relics.write_assets(tmp_path / "b", colors, None, said.append)
    assert any("25 stand-in rings" in s for s in said)


def test_loose_uv_search_finds_half_float_uvs_in_a_32_byte_vertex_element():
    import struct

    from skylands_setup.bl2 import gunmesh

    count, size, pos_off = 120, 32, 16
    blob = bytearray()
    tris = []
    for i in range(count):
        u, v = (i % 12) / 12.0, (i // 12) / 10.0
        blob += b"\x7f" * 8 + b"\x00" * 8 + struct.pack("<3f", float(i), float(i % 7), 0.0) + struct.pack("<2e", u, v)
        if i >= 2:
            tris.append((i - 2, i - 1, i))
    uvs, note = gunmesh.loose_uvs(bytes(blob), (0, size, count, pos_off, []), count, tris)
    assert len(uvs) == count and abs(uvs[13][0] - 1 / 12.0) < 1e-3 and "offset 28" in note


def test_per_level_share_grows_with_rarity():
    from skylands_setup import relics

    kind = next(k for k in relics.KINDS if k.id == "aggression")
    shares = [int(relics.keyword_text(kind, lv, relics.GRADE_OF_LEVEL[lv]).split("_d")[1].split("x")[0]) for lv in range(1, 6)]
    assert shares == [300, 600, 900, 1200, 1500]
    assert "+1.5% per character level" in relics.stats_text(kind, 5, 9)
