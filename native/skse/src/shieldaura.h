// The shield's glow (0.40.0): an enemy with a shield is wrapped in a soft blue glow that dims as the shield is used up, and when the shield breaks the glow
// bursts outwards and goes. Made of the plugin's own temporary effects (our meshes Skylands\Fx_ShieldAura_0..2 and Fx_ShieldBurst, written by the installer), respawned every
// 50 ms for a few tenths of a second each, like the shell casings: no spell, no effect record, nothing saved in the game.
#pragma once

#include "PCH.h"
#include "shield.h"

namespace shieldaura
{
	using Clock = std::chrono::steady_clock;

	inline bool  g_on = false;      // ShieldGlow=1 turns the glow on (off by default since 0.40.1)
	inline float g_range = 2200.0f; // only enemies this near get the glow (it costs a few temporary effects each)

	// Game thread, every shield update (33 ms).
	inline void Frame()
	{
		static Clock::time_point last{};
		static int               logged = 0;
		if (!g_on) {
			return;
		}
		const auto now = Clock::now();
		if (std::chrono::duration<float>(now - last).count() < 0.05f) {
			return;
		}
		last = now;
		const auto player = RE::PlayerCharacter::GetSingleton();
		if (!player || !player->Is3DLoaded()) {
			return;
		}
		const auto ui = RE::UI::GetSingleton();
		if (ui && ui->GameIsPaused()) {
			return;
		}
		const auto cell = player->GetParentCell();
		if (!cell) {
			return;
		}
		shield::g_stage = "shield glow";
		static const char* const glows[] = { "Skylands\\Fx_ShieldAura_0.nif", "Skylands\\Fx_ShieldAura_1.nif", "Skylands\\Fx_ShieldAura_2.nif" };
		const auto here = player->GetPosition();
		const float t = std::chrono::duration<float>(now.time_since_epoch()).count();
		int         drawn = 0;
		for (const auto& [id, view] : shield::Views()) {
			if (drawn >= 10) {
				break;
			}
			const bool bursting = view.sinceBreak < 0.55f;
			if (!view.has || (!bursting && view.shield < 0.02f)) {
				continue;
			}
			const auto actor = RE::TESForm::LookupByID<RE::Actor>(id);
			if (!actor || !actor->Is3DLoaded() || actor->GetParentCell() != cell) {
				continue;
			}
			if (actor->IsDead() && !bursting) {
				continue;
			}
			const auto  at = actor->GetPosition();
			const float dx = at.x - here.x, dy = at.y - here.y, dz = at.z - here.z;
			if (dx * dx + dy * dy + dz * dz > g_range * g_range) {
				continue;
			}
			// the glow is centred on the waist; the mesh lies along y and is stood up by a quarter turn about x (it is the same in both directions)
			const RE::NiPoint3 centre{ at.x, at.y, at.z + 64.0f };
			RE::NiMatrix3      up;
			up.SetEulerAnglesXYZ(1.5708f, 0.0f, 0.0f);
			if (bursting) {
				const float share = view.sinceBreak / 0.55f;  // 0 to 1: the burst swells and the effect (0.07 s each) ends with it
				RE::BSTempEffectParticle::Spawn(cell, 0.07f, "Skylands\\Fx_ShieldBurst.nif", up, centre, 0.9f + 2.4f * share, 0, nullptr);
			} else {
				const int   strength = view.shield >= 0.5f ? 0 : view.shield >= 0.2f ? 1 : 2;
				const float breathe = 1.0f + 0.05f * std::sin(t * 3.0f + static_cast<float>(id & 0xFF));
				RE::BSTempEffectParticle::Spawn(cell, 0.07f, glows[strength], up, centre, (0.8f + 0.25f * view.shield) * breathe, 0, nullptr);
			}
			++drawn;
		}
		if (drawn > 0 && logged++ < 3) {
			SKSE::log::info("shield glow: {} enemies wrapped this frame (first lines only)", drawn);
		}
	}

	inline bool Config(const std::string& a_key, const std::string& a_value)
	{
		if (a_key == "ShieldGlow") {
			g_on = a_value.find('1') != std::string::npos;
		} else if (a_key == "ShieldGlowRange") {
			try {
				g_range = std::clamp(std::stof(a_value), 300.0f, 8000.0f);
			} catch (...) {
			}
		} else {
			return false;
		}
		return true;
	}
}
