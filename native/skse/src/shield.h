// Shields (docs/shield-roadmap.md): a pool in front of an actor's health that takes damage first, waits a few seconds after the last hit, then recharges.
// State lives here, per actor, in memory. There are no shield items yet: a shield is given by the settings file (TestShield for the player,
// TestEnemyShields for every other person nearby), so the damage path can be proved on its own before anything is built on it.
//
// How damage is taken (changed in 1.16.1). 1.16.0 replaced slot 6 of the ActorValueOwner table (ModActorValue) and the log showed the game never sends combat
// damage through it (the hook saw 299 restores and no damage while the player and seven enemies were killed). So the shield no longer depends on a hook:
// it is health stacked on top of health. When an actor gets a shield of C points, C is added to its Health as a temporary bonus (the actor's maximum and current
// health both rise by C). Every damage source (bullets, melee, arrows, scripts) lowers current health, so each update the plugin reads how much damage the
// actor has taken in total, sees how much was new, and books it: the shield takes it first, what is left is damage to the real health. The shield recharges
// by restoring the damage that belongs to it; natural regeneration and potions can only heal real health (anything beyond that is undone). The actor dies only when
// the shield AND the health are gone, so a killing blow is absorbed while the shield holds, as in Borderlands 2.
// The bonus is a saved modifier: a record in the SKSE co-save lists the bonuses applied, and after a load they are taken off again before a new one is given.
// The old hook stays as an observer (it counts and logs what it sees; it changes nothing).
#pragma once

#include "PCH.h"

#include <spdlog/fmt/fmt.h>

namespace shield
{
	using Clock = std::chrono::steady_clock;

	// settings (SkylandsNative.ini; the installer writes them from the shields sheet, replaced by values read from Borderlands 2)
	inline bool  g_on = true;           // Shield=0 switches the whole feature off
	inline bool  g_gate = false;        // ShieldGate=1: a hit that empties the shield loses the rest of its damage
	inline float g_delay = 3.5f;        // ShieldDelay: seconds without a hit before the shield recharges
	inline float g_rate = 0.16f;        // ShieldRate: recharge per second, as a share of the capacity
	inline float g_low = 0.25f;         // ShieldLow: below this share the shield is "low"
	inline float g_testPlayer = 0.0f;   // TestShield: the player's shield as a share of max health (given in percent in the file)
	inline float g_testEnemy = 0.0f;    // TestEnemyShields: the same for every other person near the player
	inline bool  g_messages = true;     // ShieldMessages=0 silences the on-screen lines (there is no bar yet)

	inline std::atomic<const char*> g_stage{ "start" };

	struct State
	{
		float             frac = 0.0f;       // capacity as a share of the wearer's max health (before the bonus)
		float             capacity = 0.0f;   // C: the bonus added to Health (0 until it is applied)
		float             shield = 0.0f;     // points of shield left, 0..C
		float             prevDamage = 0.0f; // damage the actor had taken when the plugin last looked (after the plugin's own changes)
		bool              applied = false;
		bool              failed = false;    // the bonus did not show in the actor's maximum: nothing more is tried
		Clock::time_point lastHit{};
		bool              recharging = false;
		bool              pendingBreak = false;
		bool              dirty = false;
		bool              player = false;
		float             lastTold = -1.0f;
		Clock::time_point toldAt{};
	};

	inline std::mutex                                                g_lock;
	inline std::unordered_map<RE::FormID, State>                    g_states;
	inline std::unordered_map<RE::FormID, std::pair<float, float>> g_stale;  // bonuses a loaded save still holds: id -> (capacity, shield); taken off when the actor is next seen
	inline thread_local bool                                         g_self = false;  // the plugin's own change of Health (the observer does not count it)

	// the observer hook (ActorValueOwner slot 6): what the game sends through it, for the log only
	inline std::atomic_bool g_hookBad{ false };
	inline std::atomic_int  g_sane{ 0 };
	inline std::atomic_bool g_logHealth{ false };
	inline std::atomic_int  g_loggedHealth{ 0 };
	inline std::ptrdiff_t   g_aoOffset = 0;
	inline std::uintptr_t   g_origPlayer = 0, g_origNpc = 0, g_playerTable = 0;
	inline bool             g_hookedPlayer = false, g_hookedNpc = false;
	inline std::atomic_int  g_nNeg{ 0 }, g_nPos{ 0 }, g_nTemp{ 0 }, g_nOther{ 0 }, g_nSelf{ 0 };
	inline std::atomic_int  g_nAbsorbed{ 0 }, g_nBreaks{ 0 }, g_nHeals{ 0 };
	inline std::atomic<std::uint64_t> g_absorbedTimes100{ 0 };

	using ModFn = void (*)(RE::ActorValueOwner*, RE::ACTOR_VALUE_MODIFIER, RE::ActorValue, float);

	template <int Which>
	inline void Thunk(RE::ActorValueOwner* a_this, RE::ACTOR_VALUE_MODIFIER a_mod, RE::ActorValue a_av, float a_value)
	{
		const std::uintptr_t orig = Which == 0 ? g_origPlayer : g_origNpc;
		if (g_on && !g_hookBad.load() && a_this && !g_self) {
			const auto actor = reinterpret_cast<RE::Actor*>(reinterpret_cast<std::uintptr_t>(a_this) - static_cast<std::uintptr_t>(g_aoOffset));
			const auto id = actor->GetFormID();
			const int  n = g_sane.fetch_add(1);
			if (n < 40) {
				const bool ok = id != 0 && std::isfinite(a_value) && static_cast<unsigned>(a_mod) <= 3u && static_cast<unsigned>(a_av) < 200u;
				if (!ok) {
					g_hookBad = true;
					SKSE::log::error("shield: observer hook call {} has nonsense arguments (actor {:08X}, modifier {}, value {}): it is switched off", n, id, static_cast<int>(a_mod), a_value);
				}
			}
			if (a_av == RE::ActorValue::kHealth && !g_hookBad.load()) {
				if (a_mod == RE::ACTOR_VALUE_MODIFIER::kDamage) {
					++(a_value < 0.0f ? g_nNeg : g_nPos);
				} else if (a_mod == RE::ACTOR_VALUE_MODIFIER::kTemporary) {
					++g_nTemp;
				} else {
					++g_nOther;
				}
				if (g_logHealth.load() && g_loggedHealth.fetch_add(1) < 60) {
					SKSE::log::info("shield: observer saw Health change on {:08X} via {} table: modifier {} ({}), value {:.2f}", id, Which == 0 ? "player" : "npc", static_cast<int>(a_mod),
						a_mod == RE::ACTOR_VALUE_MODIFIER::kDamage ? "damage" : a_mod == RE::ACTOR_VALUE_MODIFIER::kTemporary ? "temporary" : "permanent", a_value);
				}
			}
		} else if (g_self) {
			++g_nSelf;
		}
		reinterpret_cast<ModFn>(orig)(a_this, a_mod, a_av, a_value);
	}

	inline std::string Where(std::uintptr_t a_address)
	{
		const auto base = REL::Module::get().base();
		return a_address >= base && a_address < base + 0x10000000 ? fmt::format("module+{:X}", a_address - base) : fmt::format("{:X} (outside the game's module)", a_address);
	}

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
		SKSE::log::info("shield observer ({}): ActorValueOwner part at +0x{:X}, table {}, slot 6 holds {}", Which == 0 ? "player" : "npc", g_aoOffset, Where(reinterpret_cast<std::uintptr_t>(table)), Where(original));
		if (original == 0 || original == replacement) {
			return 0;
		}
		(Which == 0 ? g_origPlayer : g_origNpc) = original;
		REL::safe_write(reinterpret_cast<std::uintptr_t>(&table[6]), &replacement, sizeof(replacement));
		return original;
	}

	inline void TryInstall(RE::PlayerCharacter* a_player, RE::ProcessLists* a_lists)
	{
		if (!g_hookedPlayer) {
			g_stage = "observer player";
			g_hookedPlayer = true;
			if (!Patch<0>(a_player, &g_playerTable)) {
				g_hookBad = true;
			}
		}
		if (!g_hookedNpc && a_lists && !g_hookBad.load()) {
			for (auto& handle : a_lists->highActorHandles) {
				const auto ptr = handle.get();
				const auto actor = ptr.get();
				if (!actor || actor->IsPlayerRef() || !actor->Is3DLoaded()) {
					continue;
				}
				g_stage = "observer npc";
				std::uintptr_t table = 0;
				const auto     ao = actor->AsActorValueOwner();
				g_hookedNpc = true;
				if (ao && *reinterpret_cast<std::uintptr_t*>(ao) == g_playerTable) {
					g_origNpc = g_origPlayer;
				} else if (!Patch<1>(actor, &table)) {
					g_hookBad = true;
				}
				break;
			}
		}
	}

	// ---- Health, as the plugin reads and changes it (game thread) ----

	// damage the actor has taken in total, in health points: its maximum (which includes the shield's bonus) minus what it has
	inline float DamageTaken(RE::Actor* a_actor)
	{
		const auto ao = a_actor->AsActorValueOwner();
		if (!ao) {
			return 0.0f;
		}
		return (std::max)(0.0f, a_actor->GetActorValueMax(RE::ActorValue::kHealth) - ao->GetActorValue(RE::ActorValue::kHealth));
	}

	inline void Write(RE::Actor* a_actor, RE::ACTOR_VALUE_MODIFIER a_mod, float a_value)
	{
		if (const auto ao = a_actor->AsActorValueOwner()) {
			g_self = true;
			ao->ModActorValue(a_mod, RE::ActorValue::kHealth, a_value);
			g_self = false;
		}
	}

	// the shield's bonus goes on: maximum and current health both rise by the capacity
	inline void Apply(RE::Actor* a_actor, State& s)
	{
		const float before = a_actor->GetActorValueMax(RE::ActorValue::kHealth);
		if (!(before > 1.0f) || !std::isfinite(before)) {
			return;
		}
		const float capacity = s.frac * before;
		const float hpBefore = a_actor->AsActorValueOwner() ? a_actor->AsActorValueOwner()->GetActorValue(RE::ActorValue::kHealth) : 0.0f;
		Write(a_actor, RE::ACTOR_VALUE_MODIFIER::kTemporary, capacity);
		const float after = a_actor->GetActorValueMax(RE::ActorValue::kHealth);
		const float hpAfter = a_actor->AsActorValueOwner() ? a_actor->AsActorValueOwner()->GetActorValue(RE::ActorValue::kHealth) : 0.0f;
		if (after < before + 0.5f * capacity) {  // the bonus did not show: leave this actor alone
			s.failed = true;
			SKSE::log::error("shield: {:08X} - adding {:.1f} temporary health did not raise its maximum ({:.1f} -> {:.1f}); no shield for it", a_actor->GetFormID(), capacity, before, after);
			return;
		}
		s.capacity = capacity;
		s.shield = capacity;
		s.applied = true;
		s.prevDamage = DamageTaken(a_actor);
		s.lastHit = Clock::now() - std::chrono::seconds(60);
		SKSE::log::info("shield: {:08X}{} has a shield of {:.0f}: maximum health {:.0f} -> {:.0f}, current {:.0f} -> {:.0f}", a_actor->GetFormID(), s.player ? " (the player)" : "", capacity, before, after, hpBefore, hpAfter);
	}

	// the shield's bonus comes off, keeping the real health as it is: the damage that belongs to the shield part is given back first
	inline void Strip(RE::Actor* a_actor, float a_capacity, float a_shield)
	{
		if (a_capacity <= 0.0f) {
			return;
		}
		if (a_capacity - a_shield > 0.0f) {
			Write(a_actor, RE::ACTOR_VALUE_MODIFIER::kDamage, a_capacity - a_shield);
		}
		Write(a_actor, RE::ACTOR_VALUE_MODIFIER::kTemporary, -a_capacity);
		SKSE::log::info("shield: {:08X} - its shield bonus of {:.0f} was taken off", a_actor->GetFormID(), a_capacity);
	}

	// One update of one actor's shield: book new damage, undo healing that would fill the shield, recharge. Returns a line for the player ("" for none).
	inline std::string Step(RE::Actor* a_actor, State& s, Clock::time_point a_now, float a_dt)
	{
		std::string say;
		float       damage = DamageTaken(a_actor);
		const float delta = damage - s.prevDamage;
		if (delta > 0.05f) {  // new damage since the last look
			s.lastHit = a_now;
			s.recharging = false;
			const float taken = (std::min)(s.shield, delta);
			float       rest = delta - taken;
			s.shield -= taken;
			s.dirty = true;
			if (taken > 0.0f) {
				++g_nAbsorbed;
				g_absorbedTimes100 += static_cast<std::uint64_t>(taken * 100.0f);
			}
			const bool broke = taken > 0.0f && s.shield <= 0.001f;
			if (broke) {
				s.shield = 0.0f;
				s.pendingBreak = true;
				++g_nBreaks;
				if (g_gate && rest > 0.0f) {  // the gate: what the shield could not take is lost
					Write(a_actor, RE::ACTOR_VALUE_MODIFIER::kDamage, rest);
					damage -= rest;
					rest = 0.0f;
				}
			}
			static std::atomic_int told{ 0 };
			if (told.fetch_add(1) < 30) {
				SKSE::log::info("shield: {:08X}{} took {:.1f} damage: the shield {:.1f}, its health {:.1f}; shield {:.1f} / {:.1f}{}", a_actor->GetFormID(), s.player ? " (player)" : "", delta, taken, rest,
					s.shield, s.capacity, broke ? " - BROKEN" : "");
			}
		} else if (delta < -0.05f) {  // healed (regeneration, a potion): it may only heal real health, never fill the shield
			++g_nHeals;
			const float real = (std::max)(0.0f, s.prevDamage - (s.capacity - s.shield));
			const float heal = -delta;
			const float excess = heal - (std::min)(heal, real);
			if (excess > 0.05f) {
				Write(a_actor, RE::ACTOR_VALUE_MODIFIER::kDamage, -excess);
				damage += excess;
			}
		}
		if (s.shield < s.capacity && a_now - s.lastHit >= std::chrono::duration_cast<Clock::duration>(std::chrono::duration<float>(g_delay))) {
			if (!s.recharging) {
				s.recharging = true;
				if (s.player) {
					say = "Shield recharging";
				}
			}
			const float x = (std::min)(s.capacity - s.shield, g_rate * s.capacity * a_dt);
			if (x > 0.0f) {
				Write(a_actor, RE::ACTOR_VALUE_MODIFIER::kDamage, x);
				damage = (std::max)(0.0f, damage - x);
				s.shield += x;
				s.dirty = true;
			}
			if (s.shield >= s.capacity - 0.001f) {
				s.shield = s.capacity;
				s.recharging = false;
				if (s.player) {
					say = "Shield full";
				}
			}
		}
		s.prevDamage = damage;
		if (s.pendingBreak) {
			s.pendingBreak = false;
			say = s.player ? "SHIELD BROKEN" : "Enemy shield down";
			static std::atomic_int brokeLogged{ 0 };
			if (brokeLogged.fetch_add(1) < 30) {
				SKSE::log::info("shield: {:08X}{} broke (capacity {:.0f})", a_actor->GetFormID(), s.player ? " (player)" : "", s.capacity);
			}
		} else if (s.player && s.dirty && say.empty() && a_now - s.toldAt > std::chrono::milliseconds(1200) && std::abs(s.shield - s.lastTold) >= 1.0f) {
			say = fmt::format("Shield {:.0f} / {:.0f}", s.shield, s.capacity);
		}
		if (!say.empty()) {
			s.toldAt = a_now;
			s.lastTold = s.shield;
			s.dirty = false;
		}
		return say;
	}

	inline void Tell(const std::string& a_text)
	{
		if (g_messages) {
			RE::SendHUDMessage::ShowHUDMessage(a_text.c_str(), nullptr, true);
		}
	}

	inline void Give(RE::Actor* a_actor, float a_frac, bool a_player)
	{
		State s;
		s.frac = a_frac;
		s.player = a_player;
		const std::lock_guard guard(g_lock);
		g_states[a_actor->GetFormID()] = s;
	}

	inline void Acquire(RE::PlayerCharacter* a_player, RE::ProcessLists* a_lists)
	{
		g_stage = "shield acquire";
		if (g_testPlayer > 0.0f) {
			bool has;
			{
				const std::lock_guard guard(g_lock);
				has = g_states.contains(a_player->GetFormID()) || g_stale.contains(a_player->GetFormID());
			}
			if (!has) {
				Give(a_player, g_testPlayer, true);
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
				if (g_states.contains(actor->GetFormID()) || g_stale.contains(actor->GetFormID()) || g_states.size() >= 80) {
					continue;
				}
			}
			Give(actor, g_testEnemy, false);
			++given;
		}
	}

	// Game thread, every 33 ms.
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
			g_logHealth = true;
			SKSE::log::info("shield: the player is loaded; settings: delay {:.2f} s, rate {:.3f} of capacity per second, gate {}, test shield {:.0f} percent, test enemy shields {:.0f} percent",
				g_delay, g_rate, g_gate ? "on" : "off", g_testPlayer * 100.0f, g_testEnemy * 100.0f);
		}
		TryInstall(player, lists);

		// bonuses a loaded save still holds come off before anything new is given
		std::vector<std::pair<RE::FormID, std::pair<float, float>>> stale;
		{
			const std::lock_guard guard(g_lock);
			for (const auto& e : g_stale) {
				stale.push_back(e);
			}
		}
		for (const auto& [id, held] : stale) {
			const auto actor = RE::TESForm::LookupByID<RE::Actor>(id);
			if (!actor || actor->IsDead() || (!actor->IsPlayerRef() && !actor->Is3DLoaded())) {
				continue;
			}
			g_stage = "shield strip";
			Strip(actor, held.first, held.second);
			const std::lock_guard guard(g_lock);
			g_stale.erase(id);
		}

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
				g_states.erase(id);  // the dead keep whatever they had
				continue;
			}
			if (!actor->IsPlayerRef() && !actor->Is3DLoaded()) {
				continue;
			}
			std::string say;
			{
				const std::lock_guard guard(g_lock);
				const auto            it = g_states.find(id);
				if (it == g_states.end()) {
					continue;
				}
				State& s = it->second;
				if (s.failed) {
					continue;
				}
				if (!s.applied) {
					g_stage = "shield apply";
					Apply(actor, s);
					continue;
				}
				g_stage = "shield step";
				say = Step(actor, s, now, dt);
			}
			if (!say.empty()) {
				Tell(say);
			}
		}
		if (now - lastSummary > std::chrono::seconds(20)) {
			lastSummary = now;
			static int lastTotal = -1;
			const int  total = g_nNeg + g_nPos + g_nTemp + g_nOther + g_nAbsorbed + g_nHeals;
			if (total != lastTotal) {
				lastTotal = total;
				SKSE::log::info("shield stats: shield absorbed damage {} times ({:.0f} points), {} breaks, {} heals seen; observer hook saw Health changes: damage {}, restore/positive {}, temporary {}, other {}, our own {}; {} shields now",
					g_nAbsorbed.load(), g_absorbedTimes100.load() / 100.0, g_nBreaks.load(), g_nHeals.load(), g_nNeg.load(), g_nPos.load(), g_nTemp.load(), g_nOther.load(), g_nSelf.load(), ids.size());
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

	// ---- the co-save: bonuses that are on actors when the game is saved ----

	constexpr std::uint32_t kUniqueId = 0x48534B53;  // 'SKSH'
	constexpr std::uint32_t kRecord = 0x444C4853;    // 'SHLD'

	inline void OnSave(SKSE::SerializationInterface* a_intfc)
	{
		struct Entry
		{
			std::uint32_t id;
			float         capacity;
			float         shield;
		};
		std::vector<Entry> entries;
		{
			const std::lock_guard guard(g_lock);
			for (const auto& [id, s] : g_states) {
				if (s.applied) {
					entries.push_back({ id, s.capacity, s.shield });
				}
			}
			for (const auto& [id, held] : g_stale) {  // not yet taken off: still on the actor
				entries.push_back({ id, held.first, held.second });
			}
		}
		if (a_intfc->OpenRecord(kRecord, 1)) {
			const std::uint32_t n = static_cast<std::uint32_t>(entries.size());
			a_intfc->WriteRecordData(n);
			for (const auto& e : entries) {
				a_intfc->WriteRecordData(e.id);
				a_intfc->WriteRecordData(e.capacity);
				a_intfc->WriteRecordData(e.shield);
			}
		}
		SKSE::log::info("shield: save - {} shield bonuses recorded in the co-save", entries.size());
	}

	inline void OnRevert(SKSE::SerializationInterface*)
	{
		// the game is being replaced (a load, a new game): what the plugin knew belongs to the old one
		const std::lock_guard guard(g_lock);
		g_states.clear();
		g_stale.clear();
	}

	inline void OnLoad(SKSE::SerializationInterface* a_intfc)
	{
		std::uint32_t type = 0, version = 0, length = 0;
		while (a_intfc->GetNextRecordInfo(type, version, length)) {
			if (type != kRecord || version != 1) {
				continue;
			}
			std::uint32_t n = 0;
			a_intfc->ReadRecordData(n);
			const std::lock_guard guard(g_lock);
			for (std::uint32_t i = 0; i < n && i < 1000; ++i) {
				std::uint32_t id = 0, newId = 0;
				float         capacity = 0.0f, shield = 0.0f;
				a_intfc->ReadRecordData(id);
				a_intfc->ReadRecordData(capacity);
				a_intfc->ReadRecordData(shield);
				if (a_intfc->ResolveFormID(id, newId)) {
					g_stale[newId] = { capacity, shield };
				}
			}
			SKSE::log::info("shield: load - {} shield bonuses in the save will be taken off as their actors are met", g_stale.size());
		}
	}

	inline void RegisterSerialization()
	{
		if (const auto ser = SKSE::GetSerializationInterface()) {
			ser->SetUniqueID(kUniqueId);
			ser->SetSaveCallback(OnSave);
			ser->SetLoadCallback(OnLoad);
			ser->SetRevertCallback(OnRevert);
		}
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
		return it == g_states.end() || !it->second.applied || it->second.capacity <= 0.0f ? -1 : static_cast<std::int32_t>(std::lround(100.0f * it->second.shield / it->second.capacity));
	}

	inline std::int32_t Max(RE::StaticFunctionTag*, RE::Actor* a_actor)
	{
		if (!a_actor) {
			return 0;
		}
		const std::lock_guard guard(g_lock);
		const auto            it = g_states.find(a_actor->GetFormID());
		return it == g_states.end() || !it->second.applied ? 0 : static_cast<std::int32_t>(std::lround(it->second.capacity));
	}

	inline void Register(RE::BSScript::IVirtualMachine* a_vm)
	{
		a_vm->RegisterFunction("ShieldPercent"sv, "SkylandsNative"sv, Percent);
		a_vm->RegisterFunction("ShieldMax"sv, "SkylandsNative"sv, Max);
	}
}
