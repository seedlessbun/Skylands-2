"""tools/badass_report.py: the numbers of the Badass sheets come out of a survey report."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import badass_report  # noqa: E402


def cls(name, health, damage, shield=None):
    lines = [f"--- GD_X.Character.{name} [AIClassDefinition] level 2", "  AttributeStartingValues:"]
    for attr, v in (("Attribute_HealthMultiplier", health), ("Attribute_EnemyNonWeaponDamageMultiplier", damage), ("Attribute_EnemyShieldMaxValueMultiplier", shield)):
        if v is not None:
            lines += [f"      Attribute: GD_Balance_HealthAndDamage.AIParameters.{attr}", "      BaseValue:", f"        BaseValueConstant: {v}", "        BaseValueScaleConstant: 1.0"]
    return lines


def cond(name, rows):
    lines = [f"--- {name} [AttributeInitializationDefinition] level 2", "  ConditionalInitialization:"]
    for v, conds in rows:
        lines += ["        BaseValueIfTrue:", f"            BaseValueConstant: {v}", "          Expressions:"]
        for a, c in conds.items():
            lines += [f"                AttributeOperand1: D_Attributes.X.{a}", f"                ConstantOperand2: {c}"]
    return lines


def loot(name, pools):
    lines = [f"--- GD_Itempools.ListDefs.{name} [ItemPoolListDefinition] level 0", "  ItemPools:"]
    for pool, scaled in pools:
        lines += [f"        ItemPool: GD_Itempools.EnemyDropPools.{pool}", "        PoolProbability:", "          BaseValueConstant: 1.0",
                  "          InitializationDefinition: " + ("GD_Balance.WeightingPlayerCount.GearDrops_PerPlayer" if scaled else "None")]
    return lines


def test_report_numbers_become_tier_values():
    text = "\n".join(
        cls("CharClass_Nomad", 3.0, 4.0) + cls("CharClass_NomadBadass", 10.0, 6.0)
        + cls("CharClass_Psycho", 1.0, 2.0) + cls("CharClass_PsychoBadass", 15.0, 5.0)
        + cls("CharClass_Goliath", 6.0, 3.0) + cls("CharClass_GoliathTurret", 12.0, 4.0)
        + cls("CharClass_LoaderBUL", 7.0, 2.0, 5.0) + cls("CharClass_LoaderBadass", 16.0, 5.0, 8.0) + cls("CharClass_LoaderSuperBadass", 22.0, 6.5, 10.0)
        + cond("GD_Balance.WeightingPlayerCount.Enemy_Damage_PerPlayerPerPlaythroughByChampion",
               [(0.65, {"NumberOfPlayers": 1.0, "Targetable_Is_Champion": 0.0, "PlayThroughCount": 1.0}),
                (0.74, {"NumberOfPlayers": 1.0, "Targetable_Is_Champion": 1.0, "PlayThroughCount": 1.0}),
                (0.9, {"NumberOfPlayers": 2.0, "Targetable_Is_Champion": 0.0, "PlayThroughCount": 1.0})])
        + loot("BadassEnemyGunsAndGear", [("Pool_GunsAndGear_02_Uncommon", False), ("Pool_GunsAndGear", True)])
        + loot("SuperBadassEnemyGunsAndGear", [("Pool_GunsAndGear_04_Rare", False), ("Pool_GunsAndGear_02_Uncommon", False)])
    )
    d = badass_report.derive(text)
    x = d["derived"]
    healths = sorted([10 / 3, 15.0, 2.0, 16 / 7])
    assert abs(x["badass_health"] - (healths[1] + healths[2]) / 2) < 1e-9  # the median of the pairs
    assert abs(x["gun"] - 0.74 / 0.65) < 1e-9
    assert abs(x["step"]["super"][0] - 22 / 16) < 1e-9 and x["step"]["super"][2] == 1  # a Super against the same family's Badass
    assert d["loot"]["badass"] == ["Pool_GunsAndGear_02_Uncommon"]  # the per-player one is not guaranteed
    assert d["loot"]["super"] == ["Pool_GunsAndGear_04_Rare", "Pool_GunsAndGear_02_Uncommon"]
    assert x["shield"] == 1.6
