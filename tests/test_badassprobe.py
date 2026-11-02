"""The Badass survey (bl2badass) on a fake install with a regular enemy, its badass and super badass variants, a formula and a pool list."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_bl2  # noqa: E402
from fake_bl2 import ObjBuilder  # noqa: E402

from skylands_setup import badassprobe  # noqa: E402


def badass_install(root):
    fake_bl2.pandora_install(root)
    cooked = root / "WillowGame" / "CookedPCConsole"
    b = ObjBuilder()
    b.obj("GD_Balance_HealthAndDamage.AIParameters.Attribute_HealthMultiplier", "AttributeDefinition",
          b.st("BaseValue", "AttributeInitializationData", b.f("BaseValueConstant", 1.0) + b.f("BaseValueScaleConstant", 1.0)))
    b.obj("GD_AI_Marauder.Class.AIClass_Marauder", "WillowAIClassDefinition", b.o("HealthAttribute", "GD_Balance_HealthAndDamage.AIParameters.Attribute_HealthMultiplier"))
    b.obj("GD_Itempools.ListDefs.BadassEnemyGunsAndGear", "ItemPoolListDefinition", b.f("Probability", 1.0))
    for leaf, name, scale in (("PawnBalance_Marauder", "Marauder", 1.0), ("PawnBalance_MarauderBadass", "Badass Marauder", 4.0),
                              ("PawnBalance_SuperBadassMarauder", "Super Badass Marauder", 10.0)):
        b.obj(f"GD_Population_Marauder.Balance.{leaf}", "AIPawnBalanceDefinition",
              b.o("AIClass", "GD_AI_Marauder.Class.AIClass_Marauder") + b.f("HealthScale", scale)
              + b.arr_structs("PlayThroughs", [b.i("PlayThrough", 1) + b.s("DisplayName", name) + b.o("DefaultItemPoolIncludedLists", "GD_Itempools.ListDefs.BadassEnemyGunsAndGear")]))
    b.obj("GD_Population_Skag.Balance.PawnBalance_Skag", "AIPawnBalanceDefinition", b.f("HealthScale", 1.0))
    b.obj("FX_Badass.Particles.Part_BadassAura", "ParticleSystem", b"")
    b.obj("Ake_VO_Marauder.Ak_Play_VO_Marauder_Badass_Taunt", "AkEvent", b"")
    b.obj("Ake_VO_Marauder.Ak_Play_Skag_Death", "AkEvent", b"")
    (cooked / "Startup_Badass_Fake.upk").write_bytes(b.build())


def test_badass_survey_finds_tiers_formulas_pools_and_enemy_sounds(tmp_path):
    bl2 = tmp_path / "bl2"
    badass_install(bl2)
    out = tmp_path / "report.txt"
    assert badassprobe.main(["--bl2", str(bl2), "--out", str(out), "--no-audio", "--minutes", "2"]) == 0
    text = out.read_text(encoding="utf-8")
    for needle in (
        "badass   GD_Population_Marauder.Balance.PawnBalance_MarauderBadass",
        "super    GD_Population_Marauder.Balance.PawnBalance_SuperBadassMarauder",
        "regular  GD_Population_Skag.Balance.PawnBalance_Skag",
        "Marauder: 3 (",
        "HealthScale: 10.0",  # the super variant dumped in full
        "GD_AI_Marauder.Class.AIClass_Marauder",  # followed to the AI class
        "Attribute_HealthMultiplier",  # and the formula
        "BadassEnemyGunsAndGear",  # the pool list
        "Part_BadassAura",  # presentation
        "ak_play_vo_marauder_badass_taunt",  # enemy voice names by family (name tables are lower case)
        "ak_play_skag_death",
        "-- skag",
        "banks not checked",
        "Finished. Report written",
    ):
        assert needle.lower() in text.lower(), needle
    assert "SECTION" not in text


def test_badass_survey_reports_a_missing_install(tmp_path):
    out = tmp_path / "report.txt"
    assert badassprobe.main(["--bl2", str(tmp_path / "nope"), "--out", str(out)]) == 2


def test_tier_and_family_words():
    assert badassprobe.tier_of("PawnBalance_UltimateBadassVarkid") == "ultimate"
    assert badassprobe.tier_of("PawnBalance_SuperBadassSkag") == "super"
    assert badassprobe.tier_of("PawnBalance_BadassMarauder") == "badass"
    assert badassprobe.tier_of("PawnBalance_Nomad") == "regular"
    assert badassprobe.is_sound_name("Ak_Play_VO_Psycho_Taunt") and badassprobe.is_sound_name("Ak_Play_Skag_Bite")
    assert not badassprobe.is_sound_name("Ak_Play_Wep_SMG_Dahl_Shot") and not badassprobe.is_sound_name("PawnBalance_Skag")
