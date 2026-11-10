"""1.39.0: Bandit / Maliwan / Vladof levels give Health / Magicka / Stamina, the player runs 25 % faster, no fall damage."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "native/skse/src"


def test_makers_second_stats_are_skyrim_vitals_one_percent_a_level():
    p = (SRC / "proficiency.h").read_text()
    assert "{ { kMag, kHealth }, { kAccuracy, kShieldDelay }, { kAccuracy, kShieldRate }, { kDamage, kShieldCap },\n\t\t{ kDamage, kMagicka }, { kReload, kShieldDelay }, { kDamage, kProj }, { kRate, kStamina } }" in p
    assert "kStats = 12" in p and "3.0f, 3.0f, 3.0f, 1.0f, 1.0f, 1.0f };" in p
    gains = p[p.index("inline void Gains"):p.index("inline void Recompute")]
    assert "if (IsVital(kMakerStats[a_maker][1]))" in gains and "a_out[kMakerStats[a_maker][1]] += g_start[kMakerStats[a_maker][1]];" in gains
    assert 'vital[i] += g_makerBonus[m][kHealth + i];' in p and '"Health", "Magicka", "Stamina" };' in p


def test_vitals_speed_and_fall_damage():
    v = (SRC / "vitals.h").read_text()
    assert 'GetSetting("fJumpFallHeightMult")' in v and "mult->data.f = 0.0f;" in v
    assert "GetBaseActorValue(kValues[i]) * prof::g_vitalPct[i].load() / 100.0f : g_speed" in v
    assert "RE::ACTOR_VALUE_MODIFIER::kTemporary, kValues[i], delta" in v and "kCarryWeight" in v
    assert "shield::g_extraRevert.push_back(&Revert);" in v
    prog = (SRC / "progress.h").read_text()
    assert "vitals::Apply();" in prog and "vitals::Start();" in prog
    main = (SRC / "main.cpp").read_text()
    assert "vitals::DataLoaded();" in main and "vitals::Config(key" in main
    ini = (ROOT / "setup/skylands_setup/skse.py").read_text()
    assert "PlayerSpeedBonus=25" in ini and "NoFallDamage=1" in ini
    from setup.skylands_setup import sheet_data  # noqa: F401  (generated: ProfHealthStart etc.)
    assert all(k in sheet_data.PROGRESSION for k in ("ProfHealthStart", "ProfMagickaStart", "ProfStaminaStart"))
