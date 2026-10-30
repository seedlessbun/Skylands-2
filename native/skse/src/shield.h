// Shields (stage 1 of docs/shield-roadmap.md): an extra pool in front of an actor's health that takes damage first, waits a few seconds after the last hit,
// then recharges. State lives here, per actor, in memory. There are no shield items yet: a shield is given by the settings file (TestShield for the player,
// TestEnemyShields for every other person nearby), so the damage path can be proved on its own before anything is built on it.
//
// Where damage is taken: every change to an actor's Health, whatever caused it (a bullet's spell effect, a sword, an arrow, a script), ends in
// ActorValueOwner::ModActorValue(kDamage, kHealth, -n) (virtual slot 6 of the ActorValueOwner part of the actor). That function is replaced here, once for the
// player's table and once for the table every other Character shares; the replacement takes the shield's share out of n first and passes the rest on.
// UNCONFIRMED on the user's runtime (Skyrim 1.7.104): that bullets and melee both arrive as kDamage with a negative value. The first calls are logged,
// and the counters at the end of the log say what kinds of Health change the hook saw.
#pragma once

#include "PCH.h"

#include <spdlog/fmt/fmt.h>

namespace shield
{
	using Clock = std::chrono::steady_clock;

	// settings (SkylandsNative.ini; the installer writes them from the shields sheet, replaced by values read from Borderlands 2)
	inline bool  g_on = true;           // Shield=0 switches the whole feature off (no hook is installed)
	inline bool  g_gate = false;        // ShieldGate=1: a hit that empties the shield loses the rest of its damage
	inline float g_delay = 3.5f;        // ShieldDelay: seconds without a hit before the shield recharges
	inline float g_rate = 0.16f;        // ShieldRate: recharge per second, as a share of the capacity
	inline float g_low = 0.25f;         // ShieldLow: below this share the shield is "low"
	inline float g_testPlayer = 0.0f;   // TestShield: the player's shield as a share of max health (given in percent in the file)
	inline float g_testEnemy = 0.0f;    // TestEnemyShields: the same for every other person near the player
	inline bool  g_messages = true;     // ShieldMessages=0 silences the on-screen lines (stage 1 has no bar yet)

	inline std::atomic<const char*> g_stage{ "start" };

	struct State
	{
		float            capacity = 0.0f;
		float            current = 0.0f;
		float            frac = 0.0f;  // capacity as a share of the wearer's max health (kept so it follows the health)
		float            maxHealth = 0.0f;
		Clock::time_point lastHit{};
		bool             recharging = false;
		bool             pendingBreak = false;  // set by the damage hook, told by the pump (the hook does nothing but arithmetic)
		bool             dirty = false;
		bool             player = false;
		float            lastTold = -1.0f;
		Clock::time_point toldAt{};
	};

	inline std::mutex                             g_lock;
	inline std::unordered_map<RE::FormID, State> g_states;

	// the hook
	inline std::atomic_bool g_hookBad{ false };
	inline std::atomic_int  g_sane{ 0 };
	inline std::ptrdiff_t   g_aoOffset = 0;  // from an Actor to its ActorValueOwner part (0xB0 or 0xB8, whichever this runtime has: asked of a live actor)
	inline std::uintptr_t   g_origPlayer = 0, g_origNpc = 0;
	inline bool             g_hookedPlayer = false, g_hookedNpc = false;

	// what the hook saw (the summary at the end of the log)
	inline std::atomic_int g_nDamagePlayer{ 0 }, g_nDamageNpc{ 0 }, g_nRestore{ 0 }, g_nOther{ 0 }, g_nAbsorbed{ 0 }, g_nBreaks{ 0 };
	inline std::atomic<std::uint64_t> g_absorbedTimes100{ 0 };

	using ModFn = void (*)(RE::ActorValueOwner*, RE::ACTOR_VALUE_MODIFIER, RE::ActorValue, float);

	// Takes the shield's share out of the damage. Returns what is left for Health. Called from the hook, on whatever thread applies the damage.
	inline float Absorb(RE::FormID a_id, float a_damage, bool a_player)
	{
		const std::lock_guard guard(g_lock);
		const auto            it = g_states.find(a_id);
		if (it == g_states.end()) {
			return a_damage;
		}
		State& s = it->second;
		s.lastHit = Clock::now();  // any hit, to the shield or to health, starts the wait again
		s.recharging = false;
		if (s.current <= 0.0f) {
			return a_damage;
		}
		const float taken = (std::min)(s.current, a_damage);
		float       rest = a_damage - taken;
		s.current -= taken;
		s.dirty = true;
		++g_nAbsorbed;
		g_absorbedTimes100 += static_cast<std::uint64_t>(taken * 100.0f);
		if (s.current <= 0.001f) {
			s.current = 0.0f;
			s.pendingBreak = true;
			++g_nBreaks;
			if (g_gate) {
				rest = 0.0f;
			}
		}
		static std::atomic_int told{ 0 };
		if (told.fetch_add(1) < 24) {
			SKSE::log::info("shield: {:08X}{} took {:.1f} of {:.1f} damage, {:.1f} / {:.1f} left{}", a_id, a_player ? " (player)" : "", taken, a_damage, s.current, s.capacity,
				s.pendingBreak ? " - BROKEN" : "");
		}
		return rest;
	}

	template <int Which>
	inline void Thunk(RE::ActorValueOwner* a_this, RE::ACTOR_VALUE_MODIFIER a_mod, RE::ActorValue a_av, float a_value)
	{
		const std::uintptr_t orig = Which == 0 ? g_origPlayer : g_origNpc;
		if (g_on && !g_hookBad.load() && a_this) {
			const auto actor = reinterpret_cast<RE::Actor*>(reinterpret_cast<std::uintptr_t>(a_this) - static_cast<std::uintptr_t>(g_aoOffset));
			const auto id = actor->GetFormID();
			// the first calls are checked: if the arguments look like nonsense the replaced slot is the wrong function, and the hook leaves everything alone from then on
			const int n = g_sane.fetch_add(1);
			if (n < 40) {
				const bool ok = id != 0 && std::isfinite(a_value) && static_cast<unsigned>(a_mod) <= 3u && static_cast<unsigned>(a_av) < 200u;
				if (!ok) {
					g_hookBad = true;
					SKSE::log::error("shield: hook call {} has nonsense arguments (actor {:08X}, modifier {}, value {}): the replaced slot is probably not ModActorValue; the hook is switched off", n,
						id, static_cast<int>(a_mod), a_value);
				} else if (n < 14 && a_av == RE::ActorValue::kHealth) {
					SKSE::log::info("shield: hook saw Health change on {:08X} via {} table: modifier {} ({}), value {:.2f}", id, Which == 0 ? "player" : "npc", static_cast<int>(a_mod),
						a_mod == RE::ACTOR_VALUE_MODIFIER::kDamage ? "damage" : a_mod == RE::ACTOR_VALUE_MODIFIER::kTemporary ? "temporary" : "permanent", a_value);
				}
			}
			if (a_av == RE::ActorValue::kHealth && !g_hookBad.load()) {
				if (a_mod == RE::ACTOR_VALUE_MODIFIER::kDamage && a_value < 0.0f) {
					++(Which == 0 ? g_nDamagePlayer : g_nDamageNpc);
					const float rest = Absorb(id, -a_value, Which == 0);
					if (rest <= 0.0f) {
						return;  // the shield took all of it
					}
					a_value = -rest;
				} else if (a_mod == RE::ACTOR_VALUE_MODIFIER::kDamage) {
					++g_nRestore;
				} else {
					++g_nOther;
				}
			}
		}
		reinterpret_cast<ModFn>(orig)(a_this, a_mod, a_av, a_value);
	}

	inline std::string Where(std::uintptr_t a_address)
	{
		const auto base = REL::Module::get().base();
		return a_address >= base && a_address < base + 0x10000000 ? fmt::format("module+{:X}", a_address - base) : fmt::format("{:X} (outside the game's module)", a_address);
	}

	// Replaces slot 6 of the ActorValueOwner table of a live actor. Returns the original function (0 if nothing was done).
	template <int Which>
	inline std::uintptr_t Patch(RE::Actor* a_actor, std::uintptr_t* a_tableOut)
	{
		const auto ao = a_actor->AsActorValueOwner();
		if (!ao) {
			return 0;
		}
		g_aoOffset = static_cast<std::ptrdiff_t>(reinterpret_cast<std::uintptr_t>(ao) - reinterpret_cast<std::uintptr_t>(a_actor));
		const auto table = *reinterpret_cast<std::uintptr_t**>(ao);
		*a_tableOut = reinterpret_cast<std::uintptr_t>(table);
		const std::uintptr_t original = table[6];
		const std::uintptr_t replacement = reinterpret_cast<std::uintptr_t>(&Thunk<Which>);
		SKSE::log::info("shield hook ({}): ActorValueOwner part at +0x{:X}, table {}, slot 6 holds {}", Which == 0 ? "player" : "npc", g_aoOffset, Where(reinterpret_cast<std::uintptr_t>(table)), Where(original));
		if (original == 0 || original == replacement) {
			return 0;
		}
		if (Which == 0) {
			g_origPlayer = original;
		} else {
			g_origNpc = original;
		}
		REL::safe_write(reinterpret_cast<std::uintptr_t>(&table[6]), &replacement, sizeof(replacement));
		return original;
	}

	inline std::uintptr_t g_playerTable = 0;

	// Game thread: install what can be installed yet (the player first, then the first other person that is loaded).
	inline void TryInstall(RE::PlayerCharacter* a_player, RE::ProcessLists* a_lists)
	{
		if (!g_hookedPlayer) {
			g_stage = "hook player";
			if (Patch<0>(a_player, &g_playerTable)) {
				g_hookedPlayer = true;
				SKSE::log::info("shield hook installed for the player");
			} else {
				g_hookedPlayer = true;  // nothing to retry: it was logged
				g_hookBad = true;
			}
		}
		if (!g_hookedNpc && a_lists) {
			for (auto& handle : a_lists->highActorHandles) {
				const auto ptr = handle.get();
				const auto actor = ptr.get();
				if (!actor || actor->IsPlayerRef() || !actor->Is3DLoaded()) {
					continue;
				}
				g_stage = "hook npc";
				std::uintptr_t table = 0;
				const auto     ao = actor->AsActorValueOwner();
				if (ao && *reinterpret_cast<std::uintptr_t*>(ao) == g_playerTable) {
					SKSE::log::info("shield hook: the other people share the player's table; nothing more to install");
					g_hookedNpc = true;
					g_origNpc = g_origPlayer;
					break;
				}
				if (Patch<1>(actor, &table)) {
					SKSE::log::info("shield hook installed for other people (an actor {:08X})", actor->GetFormID());
				} else {
					g_hookBad = true;
				}
				g_hookedNpc = true;
				break;
			}
		}
	}

	inline void Tell(const std::string& a_text)
	{
		if (g_messages) {
			RE::SendHUDMessage::ShowHUDMessage(a_text.c_str(), nullptr, true);
		}
	}

	inline void GiveShield(RE::Actor* a_actor, float a_frac, bool a_player)
	{
		const float max = a_actor->GetActorValueMax(RE::ActorValue::kHealth);
		if (!(max > 1.0f) || !std::isfinite(max)) {
			return;
		}
		State s;
		s.frac = a_frac;
		s.maxHealth = max;
		s.capacity = a_frac * max;
		s.current = s.capacity;
		s.lastHit = Clock::now() - std::chrono::seconds(60);
		s.player = a_player;
		const std::lock_guard guard(g_lock);
		g_states[a_actor->GetFormID()] = s;
		SKSE::log::info("shield: {:08X}{} has a shield of {:.0f} (max health {:.0f}, {:.0f} percent)", a_actor->GetFormID(), a_player ? " (the player)" : "", s.capacity, max, a_frac * 100.0f);
	}

	inline void Acquire(RE::PlayerCharacter* a_player, RE::ProcessLists* a_lists)
	{
		g_stage = "shield acquire";
		if (g_testPlayer > 0.0f) {
			bool has;
			{
				const std::lock_guard guard(g_lock);
				has = g_states.contains(a_player->GetFormID());
			}
			if (!has) {
				GiveShield(a_player, g_testPlayer, true);
			}
		}
		if (g_testEnemy <= 0.0f || !a_lists) {
			return;
		}
		const auto here = a_player->GetPosition();
		int        given = 0;
		for (auto& handle : a_lists->highActorHandles) {
			const auto ptr = handle.get();
			const auto actor = ptr.get();
			if (!actor || actor->IsPlayerRef() || actor->IsDead() || !actor->Is3DLoaded() || given >= 8) {
				continue;
			}
			const auto  there = actor->GetPosition();
			const float dx = there.x - here.x, dy = there.y - here.y, dz = there.z - here.z;
			if (dx * dx + dy * dy + dz * dz > 6000.0f * 6000.0f) {
				continue;
			}
			{
				const std::lock_guard guard(g_lock);
				if (g_states.contains(actor->GetFormID()) || g_states.size() >= 80) {
					continue;
				}
			}
			GiveShield(actor, g_testEnemy, false);
			++given;
		}
	}

	// Game thread, every 33 ms: recharge, follow the wearer's health, tell the player what happened, forget the dead.
	inline void Update()
	{
		static Clock::time_point last = Clock::now(), lastAcquire{}, lastSummary = Clock::now();
		static bool              firstSeen = false;
		if (!g_on) {
			return;
		}
		const auto player = RE::PlayerCharacter::GetSingleton();
		const auto lists = RE::ProcessLists::GetSingleton();
		if (!player || !player->Is3DLoaded()) {
			return;
		}
		const auto now = Clock::now();
		if (!firstSeen) {
			firstSeen = true;
			SKSE::log::info("shield: the player is loaded; settings: delay {:.2f} s, rate {:.3f} of capacity per second, gate {}, test shield {:.0f} percent, test enemy shields {:.0f} percent",
				g_delay, g_rate, g_gate ? "on" : "off", g_testPlayer * 100.0f, g_testEnemy * 100.0f);
		}
		TryInstall(player, lists);
		if (now - lastAcquire > std::chrono::milliseconds(400)) {
			lastAcquire = now;
			Acquire(player, lists);
		}
		const float dt = (std::min)(0.25f, std::chrono::duration<float>(now - last).count());
		last = now;

		g_stage = "shield update";
		std::vector<RE::FormID> ids;
		{
			const std::lock_guard guard(g_lock);
			ids.reserve(g_states.size());
			for (const auto& [id, _] : g_states) {
				ids.push_back(id);
			}
		}
		for (const auto id : ids) {
			const auto actor = RE::TESForm::LookupByID<RE::Actor>(id);
			if (!actor || (actor->IsDead() && !actor->IsPlayerRef())) {
				const std::lock_guard guard(g_lock);
				g_states.erase(id);
				continue;
			}
			const float max = actor->GetActorValueMax(RE::ActorValue::kHealth);
			std::string say;
			{
				const std::lock_guard guard(g_lock);
				const auto            it = g_states.find(id);
				if (it == g_states.end()) {
					continue;
				}
				State& s = it->second;
				if (std::isfinite(max) && max > 1.0f && std::abs(max - s.maxHealth) > 0.1f * s.maxHealth) {  // the wearer's health changed a lot: the shield follows
					const float share = s.capacity > 0.0f ? s.current / s.capacity : 0.0f;
					s.maxHealth = max;
					s.capacity = s.frac * max;
					s.current = share * s.capacity;
				}
				if (s.current < s.capacity && now - s.lastHit >= std::chrono::duration_cast<Clock::duration>(std::chrono::duration<float>(g_delay))) {
					if (!s.recharging) {
						s.recharging = true;
						if (s.player) {
							say = "Shield recharging";
						}
					}
					s.current = (std::min)(s.capacity, s.current + g_rate * s.capacity * dt);
					s.dirty = true;
					if (s.current >= s.capacity) {
						s.recharging = false;
						if (s.player) {
							say = "Shield full";
						}
					}
				}
				if (s.pendingBreak) {
					s.pendingBreak = false;
					say = s.player ? "SHIELD BROKEN" : "Enemy shield down";
					static std::atomic_int brokeLogged{ 0 };
					if (brokeLogged.fetch_add(1) < 30) {
						SKSE::log::info("shield: {:08X}{} broke (capacity {:.0f})", id, s.player ? " (player)" : "", s.capacity);
					}
				} else if (s.player && s.dirty && say.empty() && now - s.toldAt > std::chrono::milliseconds(1200) && std::abs(s.current - s.lastTold) >= 1.0f) {
					say = fmt::format("Shield {:.0f} / {:.0f}", s.current, s.capacity);
				}
				if (!say.empty()) {
					s.toldAt = now;
					s.lastTold = s.current;
					s.dirty = false;
				}
			}
			if (!say.empty()) {
				Tell(say);
			}
		}
		if (now - lastSummary > std::chrono::seconds(20)) {
			lastSummary = now;
			static int lastTotal = -1;
			const int  total = g_nDamagePlayer + g_nDamageNpc + g_nRestore + g_nOther;
			if (total != lastTotal) {  // only when something happened since the last line
				lastTotal = total;
				SKSE::log::info("shield stats: Health changes seen by the hook: damage to the player {}, damage to others {}, restores {}, other {}; shield absorbed {} times ({:.0f} damage), {} breaks; {} shields now",
					g_nDamagePlayer.load(), g_nDamageNpc.load(), g_nRestore.load(), g_nOther.load(), g_nAbsorbed.load(), g_absorbedTimes100.load() / 100.0, g_nBreaks.load(), ids.size());
			}
		}
	}

	inline void Queue(std::function<void()> a_work)
	{
		if (const auto task = SKSE::GetTaskInterface()) {
			task->AddTask(std::move(a_work));
		}
	}

	inline void StartPump()
	{
		static std::atomic_bool started{ false };
		if (!g_on || started.exchange(true)) {
			return;
		}
		std::thread([]() {
			static std::atomic_bool queued{ false };
			for (;;) {
				std::this_thread::sleep_for(std::chrono::milliseconds(33));
				if (queued.exchange(true)) {
					continue;
				}
				Queue([]() {
					Update();
					queued = false;
				});
			}
		}).detach();
		SKSE::log::info("shield: update thread started");
	}

	// the settings file: returns true when the key was a shield key
	inline bool Config(const std::string& a_key, const std::string& a_value)
	{
		const auto number = [&](float a_lo, float a_hi, float& a_out) {
			try {
				a_out = std::clamp(std::stof(a_value), a_lo, a_hi);
			} catch (...) {
			}
		};
		if (a_key == "Shield") {
			g_on = a_value.find('0') == std::string::npos;
		} else if (a_key == "ShieldGate") {
			g_gate = a_value.find('1') != std::string::npos;
		} else if (a_key == "ShieldMessages") {
			g_messages = a_value.find('0') == std::string::npos;
		} else if (a_key == "ShieldDelay") {
			number(0.1f, 30.0f, g_delay);
		} else if (a_key == "ShieldRate") {
			number(0.01f, 2.0f, g_rate);
		} else if (a_key == "ShieldLow") {
			number(0.0f, 1.0f, g_low);
		} else if (a_key == "TestShield") {
			number(0.0f, 1000.0f, g_testPlayer);
			g_testPlayer /= 100.0f;
		} else if (a_key == "TestEnemyShields") {
			number(0.0f, 1000.0f, g_testEnemy);
			g_testEnemy /= 100.0f;
		} else {
			return false;
		}
		return true;
	}

	// ---- Papyrus ----

	inline std::int32_t Percent(RE::StaticFunctionTag*, RE::Actor* a_actor)
	{
		if (!a_actor) {
			return -1;
		}
		const std::lock_guard guard(g_lock);
		const auto            it = g_states.find(a_actor->GetFormID());
		return it == g_states.end() || it->second.capacity <= 0.0f ? -1 : static_cast<std::int32_t>(std::lround(100.0f * it->second.current / it->second.capacity));
	}

	inline std::int32_t Max(RE::StaticFunctionTag*, RE::Actor* a_actor)
	{
		if (!a_actor) {
			return 0;
		}
		const std::lock_guard guard(g_lock);
		const auto            it = g_states.find(a_actor->GetFormID());
		return it == g_states.end() ? 0 : static_cast<std::int32_t>(std::lround(it->second.capacity));
	}

	inline void Register(RE::BSScript::IVirtualMachine* a_vm)
	{
		a_vm->RegisterFunction("ShieldPercent"sv, "SkylandsNative"sv, Percent);
		a_vm->RegisterFunction("ShieldMax"sv, "SkylandsNative"sv, Max);
	}
}
