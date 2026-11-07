// Character progression (docs/progression-roadmap.md), stage 1 (1.30.0): KILL XP. A kill made with a Skylands gun adds character XP straight to Skyrim's level meter
// (PlayerSkills::Data::xp); guns train no skill (the user's choice). Borderlands 2's numbers (the user's survey, roadmap 1.3 / 1.3b):
//   xp = levelThreshold / KillXPKillsPerLevel x (10 x enemy level + 4) / (10 x player level + 4) x level-gap factor x tier x boss x KillXPScale, at most KillXPMaxShare of a level
//   level gap: enemy ABOVE by 1..6+ levels x1.00 / 1.03 / 1.06 / 1.09 / 1.12 / 1.15, BELOW by 1..6+ x0.90 / 0.70 / 0.40 / 0.15 / 0.05 / 0.01 (Globals.ExpScaleByLevelDifference)
//   tier: Badass x3, Super Badass x10, Ultimate Badass x20; boss x40 (GD_AI_Balance.XP.XPMultiplier_*, read against NormalHigh 1.0)
// A gun kill: the player is the killer (or no killer is named, KillXPNoKiller) and the dying actor was hit by one of the player's Skylands bullets in the last KillXPWindow seconds.
// The hit sink notes, per actor, the last such hit, whether the actor was hostile to the player then, its Badass tier and whether it is a boss (all taken while it was alive).
// Not counted: the player's teammates, summoned or commanded actors, children, actors not hostile to the player (KillXPNonHostile=1 counts them). A body counts once (60 s).
// The XP is added on the game thread at most every 250 ms. UNCONFIRMED in game: that a direct write to xp makes the game offer the level-up (the plugin shows its own notice the
// first time xp passes the threshold) and what the hit event's source holds for the player's bullets (the first 20 hits are logged).
#pragma once

#include "PCH.h"
#include "badass.h"
#include "proficiency.h"
#include "shield.h"
#include "shielditems.h"

#include <thread>

namespace progress
{
	using Clock = std::chrono::steady_clock;

	inline bool  g_on = true;            // KillXP=0 switches kill XP off
	inline float g_scale = 1.0f;         // KillXPScale: every amount times it
	inline float g_killsPerLevel = 30.0f;  // KillXPKillsPerLevel: same-level regular kills that fill one level (the user: 30)
	inline float g_window = 3.0f;        // KillXPWindow: seconds after the player's last gun hit in which a death counts as a gun kill
	inline float g_maxShare = 0.5f;      // KillXPMaxShare: at most this share of a level from one kill
	inline bool  g_noKiller = true;      // KillXPNoKiller: a death with no killer named counts when the player's gun hit it last
	inline bool  g_nonHostile = false;   // KillXPNonHostile: also kills of actors that were not hostile to the player
	inline float g_tier[4] = { 1.0f, 3.0f, 10.0f, 20.0f };  // KillXPBadass / KillXPSuper / KillXPUltimate (Borderlands 2)
	inline float g_boss = 40.0f;         // KillXPBoss (Borderlands 2)
	inline float g_above[7] = { 1.0f, 1.0f, 1.03f, 1.06f, 1.09f, 1.12f, 1.15f };  // by levels above the player, 0..6+
	inline float g_below[7] = { 1.0f, 0.9f, 0.7f, 0.4f, 0.15f, 0.05f, 0.01f };   // by levels below the player, 0..6+

	// set by main.cpp: the Skylands gun a hit's source belongs to (the source is the gun's enchantment for plugin-launched bullets: the 0.54.0 log), with what the
	// proficiencies need: its type (0..5) and maker (0..7, -1 unknown), its bullet's damage (the enchantment's magnitude) and the player's launch power now
	struct GunFacts
	{
		RE::FormID gun = 0;
		int        type = -1, maker = -1;
		float      magnitude = 0.0f, power = 1.0f;
	};
	inline bool (*g_gunFacts)(RE::FormID, GunFacts&) = nullptr;

	struct Hit
	{
		Clock::time_point at{};
		bool              hostile = false;
		bool              boss = false;
		int               tier = 0;
		int               level = 1;
		RE::FormID        gun = 0;
	};

	inline std::mutex                             g_lock;
	inline std::unordered_map<RE::FormID, Hit>    g_hits;      // by the actor hit
	inline std::unordered_map<RE::FormID, Clock::time_point> g_counted;  // bodies already counted (a death event can come twice)
	inline float                                  g_pending = 0.0f;  // XP waiting for the game thread
	inline int                                    g_pendingKills = 0;
	inline std::atomic_int                        g_kills{ 0 }, g_hitsSeen{ 0 };
	inline std::atomic<float>                     g_given{ 0.0f };
	inline std::atomic_bool                       g_toldLevelUp{ false };

	inline float GapFactor(int a_enemy, int a_player)
	{
		const int d = a_enemy - a_player;
		return d >= 0 ? g_above[std::min(d, 6)] : g_below[std::min(-d, 6)];
	}

	// The XP one kill gives, before the cap. a_threshold: the game's levelThreshold now.
	inline float KillXP(float a_threshold, int a_enemy, int a_player, int a_tier, bool a_boss)
	{
		const float shape = (10.0f * static_cast<float>(std::max(1, a_enemy)) + 4.0f) / (10.0f * static_cast<float>(std::max(1, a_player)) + 4.0f);
		const float tier = g_tier[std::clamp(a_tier, 0, 3)];
		const float xp = a_threshold / std::max(1.0f, g_killsPerLevel) * shape * GapFactor(a_enemy, a_player) * std::max(tier, a_boss ? g_boss : 1.0f) * g_scale;
		return std::min(xp, a_threshold * g_maxShare);
	}

	// CommonLibSSE-NG v12.1.0: PlayerCharacter::PlayerSkills (in the INFO_RUNTIME_DATA block, an accessor that follows the 1.7.99 shift) holds Data { xp, levelThreshold, skills[18] }
	inline RE::PlayerCharacter::PlayerSkills* Skills()
	{
		const auto player = RE::PlayerCharacter::GetSingleton();
		return player ? player->GetInfoRuntimeData().skills : nullptr;
	}

	inline RE::PlayerCharacter::PlayerSkills::Data* SkillData()
	{
		const auto skills = Skills();
		return skills ? skills->data : nullptr;
	}

	// ---- hits: the player's Skylands bullets ----
	class HitSink : public RE::BSTEventSink<RE::TESHitEvent>
	{
	public:
		static HitSink* Get()
		{
			static HitSink sink;
			return std::addressof(sink);
		}

		RE::BSEventNotifyControl ProcessEvent(const RE::TESHitEvent* a_event, RE::BSTEventSource<RE::TESHitEvent>*) override
		{
			shield::g_stage = "progress: hit event";
			if ((!g_on && !prof::g_on) || !a_event || !a_event->target || !a_event->cause || !a_event->cause->IsPlayerRef()) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto actor = a_event->target->As<RE::Actor>();
			if (!actor || actor->IsPlayerRef()) {
				return RE::BSEventNotifyControl::kContinue;
			}
			GunFacts         facts;
			const bool       gun = g_gunFacts && g_gunFacts(a_event->source, facts) && facts.gun != 0;
			const RE::FormID gunId = facts.gun;
			if (const int n = g_hitsSeen.fetch_add(1); n < 20) {
				SKSE::log::info("kill xp: the player hit {:08X} (level {}, {}) with source {:08X} projectile {:08X}: {}", actor->GetFormID(), actor->GetLevel(), actor->IsDead() ? "dead" : "alive",
					a_event->source, a_event->projectile, gun ? fmt::format("Skylands gun {:08X}", gunId) : std::string("not a Skylands gun"));
			}
			if (!gun) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto player = RE::PlayerCharacter::GetSingleton();
			// proficiency XP (proficiency.h): living hostile actors (the killing shot's pellets a moment after the death), not the protected kinds
			if (prof::g_on && player && actor->IsHostileToActor(player) && !actor->IsEssential() && !actor->IsProtected() && !actor->IsPlayerTeammate() && !actor->IsSummoned() &&
				!actor->IsCommandedActor() && !actor->IsChild()) {
				prof::Book(actor->GetFormID(), facts.type, facts.maker, facts.magnitude * facts.power, !actor->IsDead(), gunId, facts.magnitude, facts.power);
			}
			if (!g_on || actor->IsDead()) {
				return RE::BSEventNotifyControl::kContinue;
			}
			Hit        h;
			h.at = Clock::now();
			h.hostile = player && actor->IsHostileToActor(player);
			h.boss = shielditems::IsBoss(actor) || badass::IsDragon(actor);
			h.tier = badass::TierOf(actor->GetFormID());  // read before taking our own lock
			h.level = actor->GetLevel();
			h.gun = gunId;
			const std::lock_guard guard(g_lock);
			g_hits[actor->GetFormID()] = h;
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	// ---- deaths ----
	class DeathSink : public RE::BSTEventSink<RE::TESDeathEvent>
	{
	public:
		static DeathSink* Get()
		{
			static DeathSink sink;
			return std::addressof(sink);
		}

		RE::BSEventNotifyControl ProcessEvent(const RE::TESDeathEvent* a_event, RE::BSTEventSource<RE::TESDeathEvent>*) override
		{
			shield::g_stage = "progress: death event";
			if (!a_event || !a_event->actorDying) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto dying = a_event->actorDying->As<RE::Actor>();
			if (!dying || dying->IsPlayerRef()) {
				return RE::BSEventNotifyControl::kContinue;
			}
			prof::NoteDeath(dying->GetFormID());
			if (!g_on) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto killer = a_event->actorKiller.get();
			const bool byPlayer = killer && killer->IsPlayerRef();
			const bool noKiller = !killer;
			if (!byPlayer && !(noKiller && g_noKiller)) {
				return RE::BSEventNotifyControl::kContinue;
			}
			if (dying->IsPlayerTeammate() || dying->IsSummoned() || dying->IsCommandedActor() || dying->IsChild()) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto player = RE::PlayerCharacter::GetSingleton();
			const auto data = SkillData();
			if (!player || !data) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto now = Clock::now();
			const RE::FormID id = dying->GetFormID();
			Hit  hit;
			bool found = false;
			{
				const std::lock_guard guard(g_lock);
				if (const auto c = g_counted.find(id); c != g_counted.end() && now - c->second < std::chrono::seconds(60)) {
					return RE::BSEventNotifyControl::kContinue;  // this body was counted already
				}
				if (const auto it = g_hits.find(id); it != g_hits.end()) {
					hit = it->second;
					found = true;
					g_hits.erase(it);
				}
			}
			const float since = found ? std::chrono::duration<float>(now - hit.at).count() : 1e9f;
			const bool  gunKill = found && since <= g_window;
			static std::atomic_int told{ 0 };
			if (!gunKill || (!hit.hostile && !g_nonHostile)) {
				if (told.fetch_add(1) < 30) {
					SKSE::log::info("kill xp: {:08X} died ({}): no XP ({})", id, byPlayer ? "the player killed it" : "no killer named",
						!found ? "no Skylands gun hit from the player" : !gunKill ? fmt::format("the last gun hit was {:.1f} s before", since) : std::string("it was not hostile to the player"));
				}
				return RE::BSEventNotifyControl::kContinue;
			}
			const int   lp = player->GetLevel();
			const float threshold = data->levelThreshold;
			const float xp = KillXP(threshold, hit.level, lp, hit.tier, hit.boss);
			{
				const std::lock_guard guard(g_lock);
				g_counted[id] = now;
				g_pending += xp;
				++g_pendingKills;
			}
			g_kills.fetch_add(1);
			if (told.fetch_add(1) < 30) {
				SKSE::log::info("kill xp: {:08X} (level {}{}{}) killed with gun {:08X} {:.1f} s after the hit ({}): {:.1f} XP (player level {}, threshold {:.0f}: x{:.3f} for the levels, x{:.2f} for the gap)", id, hit.level,
					hit.tier > 0 ? fmt::format(", Badass tier {}", hit.tier) : std::string(), hit.boss ? ", boss" : "", hit.gun, since, byPlayer ? "the player killed it" : "no killer named", xp, lp, threshold,
					(10.0f * hit.level + 4.0f) / (10.0f * lp + 4.0f), GapFactor(hit.level, lp));
			}
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	// Game thread, every 250 ms: the waiting XP goes into the level meter.
	inline void Apply()
	{
		float add = 0.0f;
		int   kills = 0;
		{
			const std::lock_guard guard(g_lock);
			add = g_pending;
			kills = g_pendingKills;
			g_pending = 0.0f;
			g_pendingKills = 0;
			const auto now = Clock::now();
			std::erase_if(g_counted, [&](const auto& kv) { return now - kv.second > std::chrono::seconds(120); });
			std::erase_if(g_hits, [&](const auto& kv) { return now - kv.second.at > std::chrono::seconds(30); });
		}
		if (add <= 0.0f) {
			return;
		}
		const auto player = RE::PlayerCharacter::GetSingleton();
		const auto data = SkillData();
		if (!player || !data || !(add < 1e7f)) {
			return;
		}
		const float before = data->xp;
		const float threshold = data->levelThreshold;
		data->xp = before + add;
		g_given = g_given.load() + add;
		static std::atomic_int told{ 0 };
		if (told.fetch_add(1) < 10) {
			const auto skills = Skills();
			SKSE::log::info("kill xp: {} kill(s): character XP {:.1f} -> {:.1f} (read back {:.1f}), level {}, threshold {:.1f}; the game says it can level up: {}", kills, before, before + add, data->xp,
				player->GetLevel(), threshold, skills && skills->CanLevelUp() ? "yes" : "no");
		}
		if (before < threshold && data->xp >= threshold && !g_toldLevelUp.exchange(true)) {
			RE::SendHUDMessage::ShowHUDMessage("Level up! Open the Skills menu to level up.", nullptr, true);
			SKSE::log::info("kill xp: XP {:.1f} passed the threshold {:.1f}: told the player to level up in the Skills menu", data->xp, threshold);
		}
		if (data->xp < threshold) {
			g_toldLevelUp = false;  // a level was taken: the next time is told again
		}
	}

	inline void Start(RE::ScriptEventSourceHolder* a_holder)
	{
		prof::Start();
		if ((!g_on && !prof::g_on) || !a_holder) {
			SKSE::log::info("kill xp: off; proficiencies: off");
			return;
		}
		a_holder->AddEventSink(HitSink::Get());
		a_holder->AddEventSink(DeathSink::Get());
		std::thread([]() {
			static std::atomic_bool queued{ false };
			auto lastSummary = Clock::now();
			for (;;) {
				std::this_thread::sleep_for(std::chrono::milliseconds(250));
				if (Clock::now() - lastSummary > std::chrono::seconds(30) && g_kills.load() > 0) {
					lastSummary = Clock::now();
					SKSE::log::info("kill xp: {} gun kills so far, {:.0f} XP given", g_kills.load(), g_given.load());
				}
				if (queued.exchange(true)) {
					continue;
				}
				shield::Queue([]() {
					shield::g_stage = "progress: apply";
					Apply();
					shield::g_stage = "progress: proficiencies";
					prof::Apply();
					queued = false;
				});
			}
		}).detach();
		SKSE::log::info("kill xp: on; {:.0f} same-level kills a level, window {:.1f} s, at most {:.2f} of a level a kill, tiers x{:.0f}/{:.0f}/{:.0f}, boss x{:.0f}, scale {:.2f}{}{}", g_killsPerLevel, g_window,
			g_maxShare, g_tier[1], g_tier[2], g_tier[3], g_boss, g_scale, g_noKiller ? ", deaths with no killer count" : "", g_nonHostile ? ", non-hostile kills count" : "");
	}

	inline bool Config(const std::string& a_key, const std::string& a_value)
	{
		if (!a_key.starts_with("KillXP")) {
			return false;
		}
		float v = 0.0f;
		try {
			v = std::stof(a_value);
		} catch (...) {
			return true;
		}
		const std::string_view k = std::string_view(a_key).substr(6);
		if (k.empty()) {
			g_on = v != 0.0f;
		} else if (k == "Scale") {
			g_scale = std::clamp(v, 0.0f, 100.0f);
		} else if (k == "KillsPerLevel") {
			g_killsPerLevel = std::clamp(v, 1.0f, 100000.0f);
		} else if (k == "Window") {
			g_window = std::clamp(v, 0.1f, 60.0f);
		} else if (k == "MaxShare") {
			g_maxShare = std::clamp(v, 0.01f, 10.0f);
		} else if (k == "NoKiller") {
			g_noKiller = v != 0.0f;
		} else if (k == "NonHostile") {
			g_nonHostile = v != 0.0f;
		} else if (k == "Badass") {
			g_tier[1] = std::clamp(v, 0.0f, 1000.0f);
		} else if (k == "Super") {
			g_tier[2] = std::clamp(v, 0.0f, 1000.0f);
		} else if (k == "Ultimate") {
			g_tier[3] = std::clamp(v, 0.0f, 1000.0f);
		} else if (k == "Boss") {
			g_boss = std::clamp(v, 0.0f, 1000.0f);
		}
		return true;
	}
}
