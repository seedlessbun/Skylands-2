// Badass enemies, stage 1 (1.25.0): tiers and stats only (docs/badass-roadmap.md sections 3.1, 3.2, 3.6). No names, no size, no drops yet.
//
// Every living actor near the player that is hostile to the player (people and creatures; not children, followers, summons, essential or protected actors) is rolled ONCE, at
// first sight, with the player's level at that moment: p = BadassPercent + BadassPerLevel x (level - 1), at most BadassMax percent (x BadassBossOdds for a boss or dragon).
// A hit makes a Badass; only then, from player level BadassSuperGate, p is rolled again for a Super Badass; only then, from BadassUltimateGate, again for an Ultimate Badass.
// The roll comes from the actor's form id (stable), the result (also "none") is kept in a map and in the co-save ('BDAS'). At most BadassMaxNear tiered actors are near at once
// (BadassMaxSuper / BadassMaxUltimate of the higher tiers); an actor that would pass the cap is rolled again later. BadassTest > 0 replaces p by that percent and ignores the gates.
//
// Stats (Borderlands 2's numbers, sheets/badass_tiers.json): maximum Health x BadassHealth<n> (a tracked temporary bonus; current health rises with it), melee and creature
// damage x BadassMelee<n> (AttackDamageMult), speed x BadassSpeed<n> (SpeedMult), gun bullets the plugin launches x BadassGun (LaunchData.power; the FIRST bullet of an
// enemy's burst is the game's own cast and stays unscaled). The bonuses come off when the actor dies; after a load they are checked and put back if the game dropped them.
// A shield is sized from the health WITHOUT the Badass bonus (shield::g_extraMaxOf).
#pragma once

#include "PCH.h"
#include "shield.h"
#include "shielditems.h"

#include <thread>

namespace badass
{
	using Clock = std::chrono::steady_clock;

	inline bool  g_on = true;
	inline float g_percent = 3.0f, g_perLevel = 0.5f, g_maxPercent = 25.0f, g_bossOdds = 2.0f, g_test = 0.0f;
	inline int   g_gate[4] = { 0, 1, 12, 25 };
	inline int   g_maxNear = 4, g_maxSuper = 1, g_maxUltimate = 1;
	inline float g_health[4] = { 1.0f, 3.0f, 5.8f, 15.0f };
	inline float g_melee[4] = { 1.0f, 2.28f, 2.6f, 2.6f };
	inline float g_gun[4] = { 1.0f, 1.14f, 1.14f, 1.14f };
	inline float g_speed[4] = { 1.0f, 1.0f, 1.05f, 1.10f };
	inline float g_reach = 6000.0f;
	inline constexpr const char* kTierNames[4] = { "none", "Badass", "Super Badass", "Ultimate Badass" };

	struct Entry
	{
		int        tier = 0;
		RE::FormID base = 0;        // the actor's base when it was rolled: a run-time id given to another actor later is rolled again
		bool       applied = false;  // the bonuses below are on the actor
		bool       check = false;    // from a loaded game: look whether the game kept the bonuses
		float      health = 0.0f;    // points added to maximum Health
		float      melee = 0.0f;     // added to AttackDamageMult
		float      speed = 0.0f;     // added to SpeedMult
		float      maxBefore = 0.0f;  // maximum Health before the bonus
	};

	inline std::mutex                             g_lock;
	inline std::unordered_map<RE::FormID, Entry> g_entries;
	inline std::atomic_int                        g_given{ 0 }, g_rolled{ 0 };
	inline std::atomic_int                        g_count[4]{};

	// ---- what other parts of the plugin ask (each takes the lock briefly and calls nothing else) ----
	inline int TierOf(RE::FormID a_id)
	{
		const std::lock_guard guard(g_lock);
		const auto            it = g_entries.find(a_id);
		return it == g_entries.end() ? 0 : it->second.tier;
	}

	inline float HealthBonusOf(RE::FormID a_id)  // for shield::g_extraMaxOf
	{
		const std::lock_guard guard(g_lock);
		const auto            it = g_entries.find(a_id);
		return it != g_entries.end() && it->second.applied ? it->second.health : 0.0f;
	}

	inline float GunPower(RE::FormID a_shooter)  // for the enemy bullets the plugin launches
	{
		if (!g_on) {
			return 1.0f;
		}
		const int tier = TierOf(a_shooter);
		return tier > 0 ? g_gun[tier] : 1.0f;
	}

	// ---- who may be a Badass ----
	inline bool IsDragon(RE::Actor* a_actor)
	{
		const auto race = a_actor->GetRace();
		const std::string_view edid = race && race->formEditorID.c_str() ? race->formEditorID.c_str() : "";
		return (edid.find("Dragon") != std::string_view::npos && edid.find("DragonPriest") == std::string_view::npos) || (race && race->HasKeywordString("ActorTypeDragon"));
	}

	inline bool Eligible(RE::Actor* a_actor, RE::PlayerCharacter* a_player)
	{
		return a_actor && !a_actor->IsPlayerRef() && !a_actor->IsDead() && !a_actor->IsChild() && !a_actor->IsPlayerTeammate() && !a_actor->IsCommandedActor() && !a_actor->IsSummoned() &&
		       !a_actor->IsEssential() && !a_actor->IsProtected() && a_actor->IsHostileToActor(a_player);
	}

	inline float Chance(int a_level, bool a_boss)
	{
		float p = g_test > 0.0f ? g_test : std::min(g_maxPercent, g_percent + g_perLevel * static_cast<float>(std::max(0, a_level - 1)));
		if (a_boss && g_test <= 0.0f) {
			p *= g_bossOdds;
		}
		return std::clamp(p, 0.0f, 95.0f) / 100.0f;
	}

	inline int Roll(RE::FormID a_id, int a_level, bool a_boss)
	{
		const float p = Chance(a_level, a_boss);
		const auto  draw = [&](std::uint64_t a_salt) { return static_cast<float>(shielditems::Mix(a_id ^ a_salt) % 1000000ULL) / 1000000.0f; };
		if (draw(0xBADA55ULL) >= p) {
			return 0;
		}
		if ((g_test <= 0.0f && a_level < g_gate[2]) || draw(0x5EED02ULL) >= p) {
			return 1;
		}
		if ((g_test <= 0.0f && a_level < g_gate[3]) || draw(0x5EED03ULL) >= p) {
			return 2;
		}
		return 3;
	}

	// ---- the bonuses (game thread, no lock held) ----
	inline void Mod(RE::Actor* a_actor, RE::ActorValue a_av, float a_value)
	{
		if (const auto ao = a_actor->AsActorValueOwner(); ao && a_value != 0.0f) {
			ao->ModActorValue(RE::ACTOR_VALUE_MODIFIER::kTemporary, a_av, a_value);
		}
	}

	inline float Value(RE::Actor* a_actor, RE::ActorValue a_av)
	{
		const auto ao = a_actor->AsActorValueOwner();
		return ao ? ao->GetActorValue(a_av) : 0.0f;
	}

	// puts the tier's bonuses on; returns the entry as applied
	inline Entry Apply(RE::Actor* a_actor, Entry a_entry, const char* a_why)
	{
		const int   t = std::clamp(a_entry.tier, 1, 3);
		const float shieldCap = shield::ViewOf(a_actor->GetFormID()).capacity;
		const float maxBefore = a_actor->GetActorValueMax(RE::ActorValue::kHealth);
		const float own = std::max(1.0f, maxBefore - shieldCap);  // the actor's own maximum, without a shield
		const float hpBefore = Value(a_actor, RE::ActorValue::kHealth);
		const float dmgBefore = Value(a_actor, RE::ActorValue::kAttackDamageMult);
		const float speedBefore = Value(a_actor, RE::ActorValue::kSpeedMult);
		a_entry.health = std::max(0.0f, (g_health[t] - 1.0f) * own);
		a_entry.melee = g_melee[t] - 1.0f;
		a_entry.speed = (g_speed[t] - 1.0f) * 100.0f;
		Mod(a_actor, RE::ActorValue::kHealth, a_entry.health);
		Mod(a_actor, RE::ActorValue::kAttackDamageMult, a_entry.melee);
		Mod(a_actor, RE::ActorValue::kSpeedMult, a_entry.speed);
		a_entry.applied = true;
		a_entry.check = false;
		a_entry.maxBefore = maxBefore;
		if (g_given.fetch_add(1) < 80) {
			const char* name = a_actor->GetName();
			SKSE::log::info("badass: {:08X} \"{}\" (level {}, {}{}) is {} {} [{}]: health max {:.0f} -> {:.0f} (current {:.0f} -> {:.0f}; own {:.0f} x{:.2f}{}), melee damage x{:.2f} "
			                "(AttackDamageMult {:.2f} -> {:.2f}), speed x{:.2f} (SpeedMult {:.0f} -> {:.0f}), plugin-launched gun bullets x{:.2f}",
				a_actor->GetFormID(), name ? name : "?", a_actor->GetLevel(), shielditems::IsPerson(a_actor) ? "person" : "creature", IsDragon(a_actor) ? ", dragon" : shielditems::IsBoss(a_actor) ? ", boss" : "",
				t == 3 ? "an" : "a", kTierNames[t], a_why, maxBefore, a_actor->GetActorValueMax(RE::ActorValue::kHealth), hpBefore, Value(a_actor, RE::ActorValue::kHealth), own, g_health[t],
				shieldCap > 0.0f ? fmt::format(", its shield {:.0f} not counted", shieldCap) : std::string(), g_melee[t], dmgBefore, Value(a_actor, RE::ActorValue::kAttackDamageMult), g_speed[t],
				speedBefore, Value(a_actor, RE::ActorValue::kSpeedMult), g_gun[t]);
		}
		return a_entry;
	}

	inline void Strip(RE::Actor* a_actor, const Entry& a_entry, const char* a_why)
	{
		if (!a_entry.applied) {
			return;
		}
		Mod(a_actor, RE::ActorValue::kHealth, -a_entry.health);
		Mod(a_actor, RE::ActorValue::kAttackDamageMult, -a_entry.melee);
		Mod(a_actor, RE::ActorValue::kSpeedMult, -a_entry.speed);
		static std::atomic_int told{ 0 };
		if (told.fetch_add(1) < 40) {
			SKSE::log::info("badass: {:08X} ({}) {}: its bonuses came off (health {:.0f}, melee {:+.2f}, speed {:+.0f})", a_actor->GetFormID(), kTierNames[std::clamp(a_entry.tier, 0, 3)], a_why, a_entry.health,
				a_entry.melee, a_entry.speed);
		}
	}

	// after a load: did the game keep the bonuses? (the shield code saw the player's temporary Health bonus gone after a load on 1.7.104)
	inline bool StillOn(RE::Actor* a_actor, const Entry& a_entry)
	{
		const float maxNow = a_actor->GetActorValueMax(RE::ActorValue::kHealth);
		return a_entry.health <= 0.0f || maxNow >= a_entry.maxBefore + 0.5f * a_entry.health - 0.5f;
	}

	// ---- the pass (game thread, every 500 ms) ----
	inline void Scan()
	{
		const auto player = RE::PlayerCharacter::GetSingleton();
		const auto lists = RE::ProcessLists::GetSingleton();
		if (!g_on || !player || !lists || !player->Is3DLoaded() || RE::UI::GetSingleton()->GameIsPaused()) {
			return;
		}
		shield::g_stage = "badass";
		const auto here = player->GetPosition();
		const int  level = player->GetLevel();
		struct Seen
		{
			RE::Actor* actor;
			RE::FormID id, base;
		};
		std::vector<Seen>    fresh;  // not rolled yet
		std::vector<Seen>    todo;   // rolled, bonuses to put on (or to check after a load)
		std::vector<Seen>    dead;   // tiered and dead: bonuses off
		int                  nearBy[4]{};
		for (auto& handle : lists->highActorHandles) {
			const auto ptr = handle.get();
			const auto actor = ptr.get();
			if (!actor || !actor->Is3DLoaded()) {
				continue;
			}
			const auto there = actor->GetPosition();
			const float d2 = (there.x - here.x) * (there.x - here.x) + (there.y - here.y) * (there.y - here.y) + (there.z - here.z) * (there.z - here.z);
			if (d2 > g_reach * g_reach) {
				continue;
			}
			const auto id = actor->GetFormID();
			const auto baseForm = actor->GetActorBase();
			const RE::FormID base = baseForm ? baseForm->GetFormID() : 0;
			const std::lock_guard guard(g_lock);
			auto it = g_entries.find(id);
			if (it != g_entries.end() && it->second.base != base && it->second.base != 0) {
				g_entries.erase(it);  // the id belongs to another actor now
				it = g_entries.end();
			}
			if (it == g_entries.end()) {
				if (!actor->IsDead()) {
					fresh.push_back({ actor, id, base });
				}
				continue;
			}
			const Entry& e = it->second;
			if (e.tier <= 0) {
				continue;
			}
			if (actor->IsDead()) {
				if (e.applied) {
					dead.push_back({ actor, id, base });
				}
				continue;
			}
			++nearBy[0];
			++nearBy[e.tier];
			if (!e.applied || e.check) {
				todo.push_back({ actor, id, base });
			}
		}
		for (const auto& s : dead) {
			Entry e;
			{
				const std::lock_guard guard(g_lock);
				e = g_entries[s.id];
				g_entries[s.id].applied = false;
			}
			Strip(s.actor, e, "died");
		}
		for (const auto& s : todo) {
			Entry e;
			{
				const std::lock_guard guard(g_lock);
				e = g_entries[s.id];
			}
			if (e.applied && e.check) {
				if (StillOn(s.actor, e)) {
					e.check = false;
					static std::atomic_int kept{ 0 };
					if (kept.fetch_add(1) < 20) {
						SKSE::log::info("badass: {:08X} ({}) kept its bonuses across the load (health max {:.0f})", s.id, kTierNames[e.tier], s.actor->GetActorValueMax(RE::ActorValue::kHealth));
					}
				} else {
					e.applied = false;
					e = Apply(s.actor, e, "put back after a load");
				}
			} else {
				e = Apply(s.actor, e, "rolled");
			}
			const std::lock_guard guard(g_lock);
			g_entries[s.id] = e;
		}
		int rolledNow = 0;
		for (const auto& s : fresh) {
			if (rolledNow >= 6) {
				break;
			}
			if (!Eligible(s.actor, player)) {
				continue;  // not hostile now (or never eligible): looked at again later
			}
			const bool boss = shielditems::IsBoss(s.actor) || IsDragon(s.actor);
			const int  tier = Roll(s.id, level, boss);
			if (tier > 0 && (nearBy[0] >= g_maxNear || (tier == 2 && nearBy[2] >= g_maxSuper) || (tier == 3 && nearBy[3] >= g_maxUltimate))) {
				continue;  // the area is full: rolled again later
			}
			++rolledNow;
			++g_rolled;
			++g_count[tier];
			Entry e;
			e.tier = tier;
			e.base = s.base;
			if (tier > 0) {
				++nearBy[0];
				++nearBy[tier];
				e = Apply(s.actor, e, boss ? "rolled, boss odds" : "rolled");
			}
			const std::lock_guard guard(g_lock);
			if (g_entries.size() > 4000) {
				std::erase_if(g_entries, [](const auto& kv) { return kv.second.tier == 0; });
			}
			g_entries[s.id] = e;
		}
		static Clock::time_point lastLine{};
		static int               lines = 0;
		if (Clock::now() - lastLine > std::chrono::seconds(30) && lines < 60) {
			lastLine = Clock::now();
			++lines;
			SKSE::log::info("badass: player level {}, chance {:.1f}% ({}); rolled so far {} (none {}, Badass {}, Super {}, Ultimate {}); near now: {} Badass, {} Super, {} Ultimate", level,
				Chance(level, false) * 100.0f, g_test > 0.0f ? "BadassTest" : "the sheet's rule", g_rolled.load(), g_count[0].load(), g_count[1].load(), g_count[2].load(), g_count[3].load(), nearBy[1], nearBy[2], nearBy[3]);
		}
	}

	// ---- the co-save ----
	constexpr std::uint32_t kRecord = 0x53414442;  // 'BDAS'

	inline void Save(SKSE::SerializationInterface* a_intfc)
	{
		const std::lock_guard guard(g_lock);
		if (!a_intfc->OpenRecord(kRecord, 1)) {
			return;
		}
		a_intfc->WriteRecordData(static_cast<std::uint32_t>(g_entries.size()));
		int tiered = 0;
		for (const auto& [id, e] : g_entries) {
			a_intfc->WriteRecordData(id);
			a_intfc->WriteRecordData(e.base);
			a_intfc->WriteRecordData(static_cast<std::int32_t>(e.tier));
			a_intfc->WriteRecordData(static_cast<std::uint8_t>(e.applied ? 1 : 0));
			a_intfc->WriteRecordData(e.health);
			a_intfc->WriteRecordData(e.melee);
			a_intfc->WriteRecordData(e.speed);
			a_intfc->WriteRecordData(e.maxBefore);
			tiered += e.tier > 0 ? 1 : 0;
		}
		SKSE::log::info("badass: save - {} actors rolled, {} of them with a tier", g_entries.size(), tiered);
	}

	inline bool Load(SKSE::SerializationInterface* a_intfc, std::uint32_t a_type, std::uint32_t a_version)
	{
		if (a_type != kRecord) {
			return false;
		}
		if (a_version != 1) {
			return true;
		}
		const std::lock_guard guard(g_lock);
		std::uint32_t         n = 0;
		a_intfc->ReadRecordData(n);
		int tiered = 0;
		for (std::uint32_t i = 0; i < n && i < 8000; ++i) {
			std::uint32_t id = 0, newId = 0, base = 0, newBase = 0;
			std::int32_t  tier = 0;
			std::uint8_t  applied = 0;
			Entry         e;
			a_intfc->ReadRecordData(id);
			a_intfc->ReadRecordData(base);
			a_intfc->ReadRecordData(tier);
			a_intfc->ReadRecordData(applied);
			a_intfc->ReadRecordData(e.health);
			a_intfc->ReadRecordData(e.melee);
			a_intfc->ReadRecordData(e.speed);
			a_intfc->ReadRecordData(e.maxBefore);
			if (!a_intfc->ResolveFormID(id, newId)) {
				continue;
			}
			e.tier = std::clamp(static_cast<int>(tier), 0, 3);
			e.base = a_intfc->ResolveFormID(base, newBase) ? newBase : base;
			e.applied = applied != 0;
			e.check = e.applied;
			g_entries[newId] = e;
			tiered += e.tier > 0 ? 1 : 0;
		}
		SKSE::log::info("badass: load - {} actors rolled, {} of them with a tier (their bonuses are checked when they are next near)", g_entries.size(), tiered);
		return true;
	}

	inline void Revert()
	{
		const std::lock_guard guard(g_lock);
		g_entries.clear();
	}

	inline void Start()
	{
		shield::g_extraSave.push_back(&Save);
		shield::g_extraLoad.push_back(&Load);
		shield::g_extraRevert.push_back(&Revert);
		shield::g_extraMaxOf = &HealthBonusOf;
		static std::atomic_bool started{ false };
		if (!g_on || started.exchange(true)) {
			return;
		}
		std::thread([]() {
			static std::atomic_bool queued{ false };
			for (;;) {
				std::this_thread::sleep_for(std::chrono::milliseconds(500));
				if (queued.exchange(true)) {
					continue;
				}
				shield::Queue([]() {
					Scan();
					queued = false;
				});
			}
		}).detach();
		SKSE::log::info("badass: on; chance {:.1f}% + {:.2f}% a player level (at most {:.0f}%), bosses x{:.1f}, Super from level {}, Ultimate from {}, at most {} near ({} Super, {} Ultimate){}; "
		                "health x{:.2f}/{:.2f}/{:.2f}, melee x{:.2f}/{:.2f}/{:.2f}, guns x{:.2f}, speed x{:.2f}/{:.2f}/{:.2f}",
			g_percent, g_perLevel, g_maxPercent, g_bossOdds, g_gate[2], g_gate[3], g_maxNear, g_maxSuper, g_maxUltimate, g_test > 0.0f ? fmt::format("; TEST: every roll {:.0f}%, no level gates", g_test) : std::string(),
			g_health[1], g_health[2], g_health[3], g_melee[1], g_melee[2], g_melee[3], g_gun[1], g_speed[1], g_speed[2], g_speed[3]);
	}

	inline bool Config(const std::string& a_key, const std::string& a_value)
	{
		if (!a_key.starts_with("Badass")) {
			return false;
		}
		float v = 0.0f;
		try {
			v = std::stof(a_value);
		} catch (...) {
			return true;
		}
		const std::string_view k = std::string_view(a_key).substr(6);
		const auto tierOf = [&](std::string_view a_prefix) -> int {
			if (!k.starts_with(a_prefix) || k.size() != a_prefix.size() + 1) {
				return 0;
			}
			const int t = k.back() - '0';
			return t >= 1 && t <= 3 ? t : 0;
		};
		if (k.empty()) {
			g_on = v != 0.0f;
		} else if (k == "Percent") {
			g_percent = std::clamp(v, 0.0f, 100.0f);
		} else if (k == "PerLevel") {
			g_perLevel = std::clamp(v, 0.0f, 100.0f);
		} else if (k == "Max") {
			g_maxPercent = std::clamp(v, 0.0f, 100.0f);
		} else if (k == "BossOdds") {
			g_bossOdds = std::clamp(v, 0.0f, 20.0f);
		} else if (k == "Test") {
			g_test = std::clamp(v, 0.0f, 95.0f);
		} else if (k == "SuperGate") {
			g_gate[2] = std::clamp(static_cast<int>(v), 1, 1000);
		} else if (k == "UltimateGate") {
			g_gate[3] = std::clamp(static_cast<int>(v), 1, 1000);
		} else if (k == "MaxNear") {
			g_maxNear = std::clamp(static_cast<int>(v), 0, 100);
		} else if (k == "MaxSuper") {
			g_maxSuper = std::clamp(static_cast<int>(v), 0, 100);
		} else if (k == "MaxUltimate") {
			g_maxUltimate = std::clamp(static_cast<int>(v), 0, 100);
		} else if (k == "Gun") {
			for (int t = 1; t <= 3; ++t) {
				g_gun[t] = std::clamp(v, 0.1f, 20.0f);
			}
		} else if (const int t = tierOf("Health")) {
			g_health[t] = std::clamp(v, 1.0f, 100.0f);
		} else if (const int t2 = tierOf("Melee")) {
			g_melee[t2] = std::clamp(v, 0.1f, 20.0f);
		} else if (const int t3 = tierOf("Speed")) {
			g_speed[t3] = std::clamp(v, 0.5f, 3.0f);
		}
		return true;
	}
}
