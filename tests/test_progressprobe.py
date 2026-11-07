"""The progression survey (bl2progress) on a fake install: an experience formula and level table, two challenges and a badass rank stat, found by name."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_bl2  # noqa: E402
from fake_bl2 import ObjBuilder  # noqa: E402

from skylands_setup import progressprobe  # noqa: E402


def progress_install(root):
    fake_bl2.pandora_install(root)
    cooked = root / "WillowGame" / "CookedPCConsole"
    b = ObjBuilder()
    b.obj("GD_Balance_Experience.Formulas.Init_KillExperience", "AttributeInitializationDefinition", b.f("ConditionalInitialization", 1.0) + b.f("Multiplier", 6.0))
    b.obj("GD_Balance_Experience.Formulas.Att_ExperienceLevelCurve", "AttributeDefinition", b.f("BaseValueConstant", 60.0) + b.f("Power", 2.8))
    b.obj("GD_Challenges.Combat.Challenge_Kill_SMG", "ChallengeDefinition",
          b.s("ChallengeName", "Hail of Bullets") + b.arr_structs("Levels", [b.i("Goal", 25) + b.i("RewardPoints", 1), b.i("Goal", 100) + b.i("RewardPoints", 3)]))
    b.obj("GD_Challenges.Combat.Challenge_Crit_Sniper", "ChallengeDefinition", b.s("ChallengeName", "Eagle Eye") + b.arr_structs("Levels", [b.i("Goal", 10)]))
    b.obj("GD_BadassRank.Stats.BadassRankStat_GunDamage", "AttributeDefinition", b.f("PerTokenBonus", 0.01))
    (cooked / "Startup_Progress_Fake.upk").write_bytes(b.build())


def test_progress_survey_finds_experience_challenges_and_badass_rank(tmp_path):
    bl2 = tmp_path / "bl2"
    progress_install(bl2)
    out = tmp_path / "report.txt"
    assert progressprobe.main(["--bl2", str(bl2), "--out", str(out), "--minutes", "2"]) == 0
    text = out.read_text(encoding="utf-8")
    for needle in (
        "P0. Names", "init_killexperience", "challenge_kill_smg", "badassrankstat_gundamage",  # name tables are lower case
        "GD_Balance_Experience.Formulas.Init_KillExperience", "Multiplier: 6.0", "Power: 2.79999",
        "GD_Challenges.Combat.Challenge_Kill_SMG [ChallengeDefinition]", "Hail of Bullets", "RewardPoints", "Eagle Eye",
        "first words of the challenge names", "'challenge': 2",
        "GD_BadassRank.Stats.BadassRankStat_GunDamage", "PerTokenBonus: 0.0099999",
        "P4. Class defaults", "Finished. Report written",
    ):
        assert needle.lower() in text.lower(), needle
    assert "SECTION" not in text


def test_progress_survey_reports_a_missing_install(tmp_path):
    assert progressprobe.main(["--bl2", str(tmp_path / "nope"), "--out", str(tmp_path / "r.txt")]) == 2


def test_name_words():
    assert progressprobe.XP.search("Init_KillExperience") and progressprobe.XP.search("GD_XP_Reward") and progressprobe.XP.search("PlayerLevelUp")
    assert not progressprobe.XP.search("Exposure") and not progressprobe.XP.search("Pool_Shields_Explosive")
    assert progressprobe.RANK.search("BadassRankStat_GunDamage") and progressprobe.RANK.search("BadassTokens")
    assert not progressprobe.RANK.search("PawnBalance_BadassMarauder")


def deep_install(root):
    progress_install(root)
    cooked = root / "WillowGame" / "CookedPCConsole"
    b = ObjBuilder()
    b.obj("GD_AI_Balance.XP.XPMultiplier_06_Badass", "AttributeInitializationDefinition", b.st("ValueFormula", "AttributeInitializationData", b.f("BaseValueConstant", 2.5)))
    b.obj("GD_Challenges.BadassSkill.Init_BadassBonusCalc_Gun_Damage", "AttributeInitializationDefinition", b.f("Power", 0.75))
    b.obj("GD_Challenges.Weapons.SMG_Kills", "ChallengeDefinition",
          b.s("ChallengeName", "Hail of Bullets") + b.arr_structs("Levels", [b.i("RewardPoints", 1) + b.f("CompletionValue", 25.0), b.i("RewardPoints", 3) + b.f("CompletionValue", 100.0)]))
    b.obj("GD_Challenges.Vehicles.Vehicles_KillByRamming", "ChallengeDefinition", b.s("ChallengeName", "Hit-and-Fun"))
    (cooked / "Startup_ProgressDeep_Fake.upk").write_bytes(b.build())


def test_deep_progress_survey_dumps_the_named_objects_in_full(tmp_path):
    bl2 = tmp_path / "bl2"
    deep_install(bl2)
    out = tmp_path / "deep.txt"
    assert progressprobe.main(["--bl2", str(bl2), "--out", str(out), "--minutes", "2", "--deep"]) == 0
    text = out.read_text(encoding="utf-8")
    for needle in ("bl2progress 2 --deep", "D1. In full", "--- GD_AI_Balance.XP.XPMultiplier_06_Badass", "BaseValueConstant: 2.5",
                   "Init_BadassBonusCalc_Gun_Damage", "Power: 0.75", "--- GD_Challenges.Weapons.SMG_Kills", "CompletionValue: 100.0", "RewardPoints: 3",
                   "D2. In full", "--- GD_Globals.General.Globals", "RarityLevelColors", "D3.", "Finished. Report written"):
        assert needle in text, needle
    assert "Hit-and-Fun" not in text  # vehicle challenges are skipped
    assert "SECTION" not in text
