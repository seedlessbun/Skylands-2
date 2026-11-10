// The player as a shooter (1.39.0, the user): Skyrim stats from the manufacturer proficiencies, a faster run, no fall damage.
//
// (1) Bandit / Maliwan / Vladof levels give Health / Magicka / Stamina (prof::g_vitalPct, percent of the player's BASE value; 1 % a level by default), as temporary
//     modifiers this file tracks (the game drops temporary values across a load: Revert forgets them and the next pass gives them again).
// (2) PlayerSpeedBonus (25): SpeedMult + that many points (base 100 = +25 % run and walk speed), the same tracked way. A carry-weight nudge makes the game take the new speed.
// (3) NoFallDamage (1): the game setting fJumpFallHeightMult (how much a fall hurts) set to 0 at data load. It is a game setting, so it counts for every actor.
#pragma once

#include "PCH.h"
#include "proficiency.h"
#include "shield.h"

namespace vitals
{
	inline float g_speed = 25.0f;
	inline bool  g_noFall = true;
	inline float g_applied[4]{};  // health, magicka, stamina, speed: what this file has added now (game thread only)
	inline int   g_lines = 0;

	inline bool Config(const std::string& a_key, const std::string& a_value)
	{
		float v = 0.0f;
		if (a_key != "PlayerSpeedBonus" && a_key != "NoFallDamage") {
			return false;
		}
		try {
			v = std::stof(a_value);
		} catch (...) {
			return true;
		}
		if (a_key == "PlayerSpeedBonus") {
			g_speed = std::clamp(v, -90.0f, 500.0f);
		} else {
			g_noFall = v != 0.0f;
		}
		return true;
	}

	// at data load (kDataLoaded)
	inline void DataLoaded()
	{
		if (!g_noFall) {
			SKSE::log::info("vitals: fall damage left as the game has it (NoFallDamage=0)");
			return;
		}
		const auto settings = RE::GameSettingCollection::GetSingleton();
		const auto mult = settings ? settings->GetSetting("fJumpFallHeightMult") : nullptr;
		if (!mult) {
			SKSE::log::info("vitals: the game setting fJumpFallHeightMult was not found; fall damage stays");
			return;
		}
		const float before = mult->data.f;
		mult->data.f = 0.0f;
		const auto minimum = settings->GetSetting("fJumpFallHeightMin");
		SKSE::log::info("vitals: no fall damage - fJumpFallHeightMult {:.3f} -> 0 (falls start hurting above {:.0f} units, now they never do)", before, minimum ? minimum->data.f : -1.0f);
	}

	inline void Revert()
	{
		std::fill(std::begin(g_applied), std::end(g_applied), 0.0f);  // a load or a new game: the game dropped the temporary values
	}

	// game thread, every 250 ms (progress pump)
	inline void Apply()
	{
		const auto player = RE::PlayerCharacter::GetSingleton();
		if (!player || !player->Is3DLoaded() || player->IsDead()) {
			return;
		}
		const auto owner = player->AsActorValueOwner();
		static constexpr RE::ActorValue kValues[4] = { RE::ActorValue::kHealth, RE::ActorValue::kMagicka, RE::ActorValue::kStamina, RE::ActorValue::kSpeedMult };
		static constexpr const char*    kNames[4] = { "health", "magicka", "stamina", "speed" };
		for (int i = 0; i < 4; ++i) {
			const float want = i < 3 ? owner->GetBaseActorValue(kValues[i]) * prof::g_vitalPct[i].load() / 100.0f : g_speed;
			const float delta = want - g_applied[i];
			if (std::abs(delta) < 0.05f) {
				continue;
			}
			const float before = owner->GetActorValue(kValues[i]);
			shield::g_self = true;  // shield.h does not take our health change for damage or healing
			owner->ModActorValue(RE::ACTOR_VALUE_MODIFIER::kTemporary, kValues[i], delta);
			shield::g_self = false;
			g_applied[i] = want;
			if (i == 3) {  // the game takes a new speed when the carry weight changes
				owner->ModActorValue(RE::ACTOR_VALUE_MODIFIER::kTemporary, RE::ActorValue::kCarryWeight, 0.1f);
				owner->ModActorValue(RE::ACTOR_VALUE_MODIFIER::kTemporary, RE::ActorValue::kCarryWeight, -0.1f);
			}
			if (g_lines < 40) {
				++g_lines;
				SKSE::log::info("vitals: {} {:.1f} -> {:.1f} (this plugin's share now {:+.1f}{})", kNames[i], before, owner->GetActorValue(kValues[i]), want,
					i < 3 ? fmt::format(", {:.1f}% of the base {:.0f} from the manufacturer levels", prof::g_vitalPct[i].load(), owner->GetBaseActorValue(kValues[i])) : std::string(", PlayerSpeedBonus"));
			}
		}
	}

	inline void Start()
	{
		shield::g_extraRevert.push_back(&Revert);
		SKSE::log::info("vitals: on; run speed +{:.0f}, fall damage {}, Bandit / Maliwan / Vladof levels give {:.1f} / {:.1f} / {:.1f} % health / magicka / stamina each",
			g_speed, g_noFall ? "off" : "on", prof::g_start[prof::kHealth], prof::g_start[prof::kMagicka], prof::g_start[prof::kStamina]);
	}
}
