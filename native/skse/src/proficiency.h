// Weapon proficiencies (docs/progression-roadmap.md 3.2 - 3.5), 1.31.0: a track per gun TYPE (6) and per MANUFACTURER (8), per character (co-save 'PROF').
//
// XP: the bullet's own damage (its enchantment's magnitude x the launch power, so relic and proficiency damage bonuses count; damage on a shield counts) of every hit of
// the player's Skylands bullets on a LIVING actor that is hostile to the player (not essential, protected, a teammate, summoned or commanded), x ProfXPScale, to BOTH the
// gun's type track and its maker track; the killing shot's own pellets count for ProfKillGrace seconds after the death, a body later counts for nothing.
// Levels: level n -> n+1 costs ProfBase + ProfStep x n XP, no cap.
// Bonuses: an ordinary level gives ProfStatsPerLevel stat(s) in a fixed rotation (damage, accuracy, reload, fire rate, magazine, bonus projectiles); a milestone level (10, 25,
// 50, 75, 100, then every 50) gives 4 stats at ProfMilestoneMult x the step; the step of a stat = max(floor, start x ProfDecay ^ milestones passed). A maker track raises its
// maker's two signature stats (one per ordinary level, both at a milestone). A gun gets its type track, its own maker's track in full (ProfOwnMaker) and ProfOtherMakers (a
// quarter) of every other maker's track. The plugin applies the result per shot (fire interval, reload, spread, magazine, launch power, extra projectiles); nothing goes
// through actor values (the relics' Variable04..09 stay theirs).
#pragma once

#include "PCH.h"
#include "shield.h"

namespace prof
{
	using Clock = std::chrono::steady_clock;

	constexpr int kTypes = 6, kMakers = 8, kStats = 6;
	enum Stat : int
	{
		kDamage = 0,
		kAccuracy,
		kReload,
		kRate,
		kMag,
		kProj
	};
	inline constexpr const char* kTypeNames[kTypes] = { "SMG", "Assault Rifle", "Pistol", "Shotgun", "Sniper", "Launcher" };  // generate.STAFF_KINDS order (the ammo list)
	inline constexpr const char* kTypeShort[kTypes] = { "SMG", "AR", "Pistol", "Shotgun", "Sniper", "Launcher" };  // the HUD line
	inline constexpr const char* kMakerNames[kMakers] = { "Bandit", "Dahl", "Hyperion", "Jakobs", "Maliwan", "Tediore", "Torgue", "Vladof" };  // sheets/manufacturers.json order
	inline constexpr const char* kStatNames[kStats] = { "damage", "accuracy", "reload speed", "fire rate", "magazine size", "bonus projectile chance" };
	// each maker's two signature stats (roadmap 3.3; Jakobs' second, fire rate, is a choice: "fire as fast as you can pull the trigger")
	inline constexpr int kMakerStats[kMakers][2] = { { kMag, kRate }, { kAccuracy, kReload }, { kAccuracy, kDamage }, { kDamage, kRate },
		{ kDamage, kAccuracy }, { kReload, kMag }, { kDamage, kProj }, { kRate, kMag } };
	constexpr int kLauncher = 5, kShotgun = 3;

	// ---- settings (ini Prof...) ----
	inline bool  g_on = true;
	inline float g_xpScale = 0.1f, g_base = 50.0f, g_step = 15.0f, g_killGrace = 0.25f;
	inline int   g_statsPerLevel = 1;
	inline float g_milestoneMult = 3.0f, g_decay = 0.75f, g_otherMakers = 0.25f, g_ownMaker = 1.0f, g_launcherProj = 0.5f;
	inline float g_start[kStats] = { 2.0f, 2.0f, 2.0f, 2.0f, 3.0f, 4.0f };
	inline float g_floor[kStats] = { 0.5f, 0.5f, 0.5f, 0.5f, 1.0f, 1.0f };
	inline bool  g_hud = true, g_notices = true;
	inline int   g_logHits = 30;

	struct Track
	{
		std::int32_t level = 0;
		float        xp = 0.0f;     // into the current level
		float        total = 0.0f;  // all ever earned
		std::int32_t legendary = 0;  // reserved (roadmap 3.6); always 0 for now
	};

	inline std::mutex g_lock;
	inline Track      g_type[kTypes], g_maker[kMakers];
	inline float      g_pendType[kTypes]{}, g_pendMaker[kMakers]{};
	inline float      g_typeBonus[kTypes][kStats]{}, g_makerBonus[kMakers][kStats]{};  // percent (projectiles: points of percent), from the levels
	inline std::unordered_map<RE::FormID, Clock::time_point> g_deathAt;
	inline std::atomic_int g_hitsBooked{ 0 };

	inline bool Milestone(int a_n) { return a_n == 10 || a_n == 25 || a_n == 50 || a_n == 75 || a_n == 100 || (a_n > 100 && a_n % 50 == 0); }
	inline float Cost(int a_level) { return (std::max)(1.0f, g_base + g_step * static_cast<float>(a_level)); }
	inline float StepOf(int a_stat, int a_passed) { return (std::max)(g_floor[a_stat], g_start[a_stat] * std::pow(g_decay, static_cast<float>(a_passed))); }

	// what level n of a track adds, stat by stat (a_maker < 0: a type track)
	inline void Gains(int a_maker, int a_n, float a_out[kStats])
	{
		std::fill(a_out, a_out + kStats, 0.0f);
		int passed = 0;
		for (int m = 1; m < a_n; ++m) {
			passed += Milestone(m) ? 1 : 0;
		}
		const bool milestone = Milestone(a_n);
		if (a_maker >= 0) {
			if (milestone) {
				for (const int s : kMakerStats[a_maker]) {
					a_out[s] += StepOf(s, passed) * g_milestoneMult;
				}
			} else {
				const int s = kMakerStats[a_maker][(a_n - 1) % 2];
				a_out[s] += StepOf(s, passed);
			}
			return;
		}
		const int per = std::clamp(g_statsPerLevel, 1, kStats);
		const int first = ((a_n - 1) * per) % kStats;
		const int count = milestone ? 4 : per;
		for (int i = 0; i < count; ++i) {
			const int s = (first + i) % kStats;
			a_out[s] += StepOf(s, passed) * (milestone ? g_milestoneMult : 1.0f);
		}
	}

	inline void Recompute(int a_maker, int a_level, float a_out[kStats])  // a track's bonuses at a level
	{
		std::fill(a_out, a_out + kStats, 0.0f);
		float g[kStats];
		for (int n = 1; n <= (std::min)(a_level, 5000); ++n) {
			Gains(a_maker, n, g);
			for (int s = 0; s < kStats; ++s) {
				a_out[s] += g[s];
			}
		}
	}

	inline void RecomputeAllLocked()
	{
		for (int t = 0; t < kTypes; ++t) {
			Recompute(-1, g_type[t].level, g_typeBonus[t]);
		}
		for (int m = 0; m < kMakers; ++m) {
			Recompute(m, g_maker[m].level, g_makerBonus[m]);
		}
	}

	// the bonuses a gun of this type and maker gets, in percent (a_type / a_maker < 0: unknown, that part left out; an unknown maker gets the quarter of every maker)
	inline void BonusFor(int a_type, int a_maker, float a_out[kStats])
	{
		std::fill(a_out, a_out + kStats, 0.0f);
		if (!g_on) {
			return;
		}
		const std::lock_guard guard(g_lock);
		if (a_type >= 0 && a_type < kTypes) {
			for (int s = 0; s < kStats; ++s) {
				a_out[s] += g_typeBonus[a_type][s];
			}
		}
		for (int m = 0; m < kMakers; ++m) {
			const float share = m == a_maker ? g_ownMaker : g_otherMakers;
			for (int s = 0; s < kStats; ++s) {
				a_out[s] += g_makerBonus[m][s] * share;
			}
		}
		if (a_type == kLauncher) {
			a_out[kProj] *= g_launcherProj;
		}
	}

	struct View
	{
		int   typeLevel = 0, makerLevel = 0;
		float typeFrac = 0.0f, makerFrac = 0.0f;
	};
	inline View ViewOf(int a_type, int a_maker)  // for the HUD line
	{
		View v;
		const std::lock_guard guard(g_lock);
		if (a_type >= 0 && a_type < kTypes) {
			v.typeLevel = g_type[a_type].level;
			v.typeFrac = std::clamp(g_type[a_type].xp / Cost(g_type[a_type].level), 0.0f, 1.0f);
		}
		if (a_maker >= 0 && a_maker < kMakers) {
			v.makerLevel = g_maker[a_maker].level;
			v.makerFrac = std::clamp(g_maker[a_maker].xp / Cost(g_maker[a_maker].level), 0.0f, 1.0f);
		}
		return v;
	}

	// ---- booking: from progress.h's hit sink (the game thread) ----
	inline void NoteDeath(RE::FormID a_id)
	{
		const std::lock_guard guard(g_lock);
		g_deathAt[a_id] = Clock::now();
	}

	// a hit by the player's gun of this type and maker, for a_damage. a_alive: the target was alive at the hit.
	inline void Book(RE::FormID a_target, int a_type, int a_maker, float a_damage, bool a_alive, RE::FormID a_gun, float a_magnitude, float a_power)
	{
		if (!g_on || !(a_damage > 0.0f) || a_damage > 1e7f) {
			return;
		}
		const float xp = a_damage * g_xpScale;
		bool        counted = a_alive;
		{
			const std::lock_guard guard(g_lock);
			if (!a_alive) {
				const auto it = g_deathAt.find(a_target);
				counted = it != g_deathAt.end() && std::chrono::duration<float>(Clock::now() - it->second).count() <= g_killGrace;
			}
			if (counted) {
				if (a_type >= 0 && a_type < kTypes) {
					g_pendType[a_type] += xp;
				}
				if (a_maker >= 0 && a_maker < kMakers) {
					g_pendMaker[a_maker] += xp;
				}
			}
		}
		if (const int n = g_hitsBooked.fetch_add(1); n < g_logHits) {
			SKSE::log::info("prof: hit {:08X} by gun {:08X} ({}, {}): magnitude {:.2f} x power {:.2f} = {:.2f} damage -> {}", a_target, a_gun,
				a_type >= 0 && a_type < kTypes ? kTypeNames[a_type] : "type ?", a_maker >= 0 && a_maker < kMakers ? kMakerNames[a_maker] : "maker ?", a_magnitude, a_power, a_damage,
				counted ? fmt::format("{:.2f} XP", xp) : std::string("nothing (a body)"));
		}
	}

	inline std::string GainText(const float a_g[kStats])
	{
		std::string out;
		for (int s = 0; s < kStats; ++s) {
			if (a_g[s] > 0.0f) {
				out += (out.empty() ? "" : ", ") + fmt::format("+{:.1f}% {}", a_g[s], kStatNames[s]);
			}
		}
		return out;
	}

	// Game thread, every 250 ms (progress.h's pump): the waiting XP goes into the tracks; level-ups are told.
	inline void Apply()
	{
		std::vector<std::string> notices;
		{
			const std::lock_guard guard(g_lock);
			bool changed = false;
			const auto feed = [&](Track& a_t, float& a_pend, int a_maker, const char* a_name) {
				if (a_pend <= 0.0f) {
					return;
				}
				a_t.xp += a_pend;
				a_t.total += a_pend;
				a_pend = 0.0f;
				for (int guard2 = 0; guard2 < 50 && a_t.xp >= Cost(a_t.level); ++guard2) {
					a_t.xp -= Cost(a_t.level);
					++a_t.level;
					changed = true;
					float g[kStats];
					Gains(a_maker, a_t.level, g);
					const std::string text = fmt::format("{} proficiency {}{}: {}", a_name, a_t.level, Milestone(a_t.level) ? " (milestone)" : "", GainText(g));
					notices.push_back(text);
					SKSE::log::info("prof: {} (total XP {:.0f}, next level at {:.0f})", text, a_t.total, Cost(a_t.level));
				}
			};
			for (int t = 0; t < kTypes; ++t) {
				feed(g_type[t], g_pendType[t], -1, kTypeNames[t]);
			}
			for (int m = 0; m < kMakers; ++m) {
				feed(g_maker[m], g_pendMaker[m], m, kMakerNames[m]);
			}
			if (changed) {
				RecomputeAllLocked();
			}
			const auto now = Clock::now();
			std::erase_if(g_deathAt, [&](const auto& kv) { return now - kv.second > std::chrono::seconds(30); });
		}
		if (g_notices) {
			for (const auto& n : notices) {
				RE::SendHUDMessage::ShowHUDMessage(n.c_str(), nullptr, true);
			}
		}
	}

	// extra projectiles for one shot: a chance of c percent (c over 100: floor(c/100) for sure plus the rest as a chance), per pellet for a shotgun
	inline int Extra(float a_chance, int a_pellets, bool a_perPellet, std::mt19937& a_rng)
	{
		if (!(a_chance > 0.0f)) {
			return 0;
		}
		std::uniform_real_distribution<float> unit(0.0f, 1.0f);
		const int   sure = static_cast<int>(a_chance / 100.0f);
		const float rest = a_chance / 100.0f - static_cast<float>(sure);
		int         extra = 0;
		for (int i = 0; i < (a_perPellet ? (std::max)(1, a_pellets) : 1); ++i) {
			extra += sure + (unit(a_rng) < rest ? 1 : 0);
		}
		return (std::min)(extra, 48);
	}

	// ---- the co-save ----
	constexpr std::uint32_t kRecord = 0x464F5250;  // 'PROF'
	inline void Save(SKSE::SerializationInterface* a_intfc)
	{
		const std::lock_guard guard(g_lock);
		if (!a_intfc->OpenRecord(kRecord, 1)) {
			return;
		}
		a_intfc->WriteRecordData(static_cast<std::uint32_t>(kTypes));
		a_intfc->WriteRecordData(static_cast<std::uint32_t>(kMakers));
		for (const auto* list : { static_cast<Track*>(g_type), static_cast<Track*>(g_maker) }) {
			const int n = list == g_type ? kTypes : kMakers;
			for (int i = 0; i < n; ++i) {
				a_intfc->WriteRecordData(list[i].level);
				a_intfc->WriteRecordData(list[i].xp);
				a_intfc->WriteRecordData(list[i].total);
				a_intfc->WriteRecordData(list[i].legendary);
			}
		}
		std::string levels;
		for (int t = 0; t < kTypes; ++t) {
			levels += fmt::format("{}{} {}", levels.empty() ? "" : ", ", kTypeNames[t], g_type[t].level);
		}
		for (int m = 0; m < kMakers; ++m) {
			levels += fmt::format(", {} {}", kMakerNames[m], g_maker[m].level);
		}
		SKSE::log::info("prof: save - {}", levels);
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
		std::uint32_t types = 0, makers = 0;
		a_intfc->ReadRecordData(types);
		a_intfc->ReadRecordData(makers);
		const auto read = [&](Track* a_list, std::uint32_t a_n, int a_have) {
			for (std::uint32_t i = 0; i < a_n && i < 64; ++i) {
				Track t;
				a_intfc->ReadRecordData(t.level);
				a_intfc->ReadRecordData(t.xp);
				a_intfc->ReadRecordData(t.total);
				a_intfc->ReadRecordData(t.legendary);
				if (static_cast<int>(i) < a_have) {
					t.level = std::clamp(t.level, 0, 100000);
					t.xp = std::isfinite(t.xp) ? (std::max)(0.0f, t.xp) : 0.0f;
					a_list[i] = t;
				}
			}
		};
		read(g_type, types, kTypes);
		read(g_maker, makers, kMakers);
		RecomputeAllLocked();
		std::string levels;
		for (int t = 0; t < kTypes; ++t) {
			levels += fmt::format("{}{} {}", levels.empty() ? "" : ", ", kTypeNames[t], g_type[t].level);
		}
		for (int m = 0; m < kMakers; ++m) {
			levels += fmt::format(", {} {}", kMakerNames[m], g_maker[m].level);
		}
		SKSE::log::info("prof: load - {}", levels);
		return true;
	}

	inline void Revert()
	{
		const std::lock_guard guard(g_lock);
		for (auto& t : g_type) {
			t = Track{};
		}
		for (auto& m : g_maker) {
			m = Track{};
		}
		std::fill(std::begin(g_pendType), std::end(g_pendType), 0.0f);
		std::fill(std::begin(g_pendMaker), std::end(g_pendMaker), 0.0f);
		g_deathAt.clear();
		RecomputeAllLocked();
	}

	inline void Start()
	{
		shield::g_extraSave.push_back(&Save);
		shield::g_extraLoad.push_back(&Load);
		shield::g_extraRevert.push_back(&Revert);
		SKSE::log::info("prof: {}; XP = damage x {:.2f}, level n costs {:.0f} + {:.0f} x n, {} stat(s) a level, milestones x{:.1f}, decay {:.2f}, other makers x{:.2f}, own maker x{:.2f}, launchers' projectiles x{:.2f}",
			g_on ? "on" : "off", g_xpScale, g_base, g_step, g_statsPerLevel, g_milestoneMult, g_decay, g_otherMakers, g_ownMaker, g_launcherProj);
	}

	inline bool Config(const std::string& a_key, const std::string& a_value)
	{
		if (!a_key.starts_with("Prof")) {
			return false;
		}
		float v = 0.0f;
		try {
			v = std::stof(a_value);
		} catch (...) {
			return true;
		}
		const std::string_view k = std::string_view(a_key).substr(4);
		static constexpr std::string_view statKeys[kStats] = { "Damage", "Accuracy", "Reload", "Rate", "Magazine", "Projectile" };
		for (int s = 0; s < kStats; ++s) {
			if (k == fmt::format("{}Start", statKeys[s])) {
				g_start[s] = std::clamp(v, 0.0f, 100.0f);
				return true;
			}
			if (k == fmt::format("{}Floor", statKeys[s])) {
				g_floor[s] = std::clamp(v, 0.0f, 100.0f);
				return true;
			}
		}
		if (k.empty()) {
			g_on = v != 0.0f;
		} else if (k == "XPScale") {
			g_xpScale = std::clamp(v, 0.0f, 1000.0f);
		} else if (k == "Base") {
			g_base = std::clamp(v, 1.0f, 1e7f);
		} else if (k == "Step") {
			g_step = std::clamp(v, 0.0f, 1e7f);
		} else if (k == "KillGrace") {
			g_killGrace = std::clamp(v, 0.0f, 5.0f);
		} else if (k == "StatsPerLevel") {
			g_statsPerLevel = std::clamp(static_cast<int>(v), 1, kStats);
		} else if (k == "MilestoneMult") {
			g_milestoneMult = std::clamp(v, 0.0f, 100.0f);
		} else if (k == "Decay") {
			g_decay = std::clamp(v, 0.0f, 1.0f);
		} else if (k == "OtherMakers") {
			g_otherMakers = std::clamp(v, 0.0f, 10.0f);
		} else if (k == "OwnMaker") {
			g_ownMaker = std::clamp(v, 0.0f, 10.0f);
		} else if (k == "LauncherProjectiles") {
			g_launcherProj = std::clamp(v, 0.0f, 10.0f);
		} else if (k == "Hud") {
			g_hud = v != 0.0f;
		} else if (k == "Notices") {
			g_notices = v != 0.0f;
		} else if (k == "LogHits") {
			g_logHits = std::clamp(static_cast<int>(v), 0, 100000);
		}
		return true;
	}
}
