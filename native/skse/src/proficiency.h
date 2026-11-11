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

	// 1.36.0: kStats = the 6 gun stats + 3 shield stats (the manufacturers' second stat, the user's choice); gun type tracks only ever rotate over the first kGunStats
	// 1.39.0: + 3 Skyrim stats (health, magicka, stamina: Bandit / Maliwan / Vladof's second stat, the user's choice), percent of the player's base value
	constexpr int kTypes = 6, kMakers = 8, kGunStats = 6, kStats = 12;
	enum Stat : int
	{
		kDamage = 0,
		kAccuracy,
		kReload,
		kRate,
		kMag,
		kProj,
		kShieldCap,    // shield capacity, percent
		kShieldRate,   // shield recharge rate, percent
		kShieldDelay,  // shield recharge delay, percent shorter
		kHealth,       // 1.39.0: Skyrim's Health, percent of the base value
		kMagicka,      // Magicka
		kStamina       // Stamina
	};
	inline bool IsVital(int a_stat) { return a_stat >= kHealth && a_stat <= kStamina; }
	inline constexpr const char* kTypeNames[kTypes] = { "SMG", "Assault Rifle", "Pistol", "Shotgun", "Sniper", "Launcher" };  // generate.STAFF_KINDS order (the ammo list)
	inline constexpr const char* kTypeShort[kTypes] = { "SMG", "AR", "Pistol", "Shotgun", "Sniper", "Launcher" };  // the HUD line
	inline constexpr const char* kMakerNames[kMakers] = { "Bandit", "Dahl", "Hyperion", "Jakobs", "Maliwan", "Tediore", "Torgue", "Vladof" };  // sheets/manufacturers.json order
	inline constexpr const char* kStatNames[kStats] = { "damage", "accuracy", "reload speed", "fire rate", "magazine size", "bonus projectile chance", "shield capacity",
		"shield recharge rate", "shield recharge delay", "health", "magicka", "stamina" };
	// each maker's two signature stats (roadmap 3.3; Jakobs' second, fire rate, is a choice: "fire as fast as you can pull the trigger")
	// 1.36.0 (the user): a maker's PRIMARY is a gun stat (its own guns full, every other gun a quarter); its SECONDARY is a shield stat that ALWAYS applies, whatever gun is
	// held or shield worn. Bandit / Jakobs capacity (1.37.3: Torgue = bonus projectile chance, for every gun), Vladof / Hyperion / Maliwan recharge rate, Tediore / Dahl shorter delay (BL2: Bandit big shields, Tediore quick
	// delay, Vladof quick refill; the rest my pick). Five of them (Torgue, Maliwan, Jakobs, Dahl, Hyperion) are meant to move to grenade stats when grenades exist.
	// 1.39.0 (the user): Bandit's second stat is Skyrim's Health, Maliwan's Magicka, Vladof's Stamina: 1 percent of the base value EVERY maker level (ProfHealthStart /
	// ProfMagickaStart / ProfStaminaStart), not alternating with the primary, no milestone or growth; the primary keeps its odd levels and milestones as before
	inline constexpr int kMakerStats[kMakers][2] = { { kMag, kHealth }, { kAccuracy, kShieldDelay }, { kAccuracy, kShieldRate }, { kDamage, kShieldCap },
		{ kDamage, kMagicka }, { kReload, kShieldDelay }, { kDamage, kProj }, { kRate, kStamina } };
	// 1.37.3: Torgue's second stat is the bonus projectile chance again (the user), and like the shield stats it is the CHARACTER's: every gun gets it, not only Torgue's
	inline constexpr bool kSecondaryEverywhere[kMakers] = { false, false, false, false, false, false, true, false };
	constexpr int kLauncher = 5, kShotgun = 3;

	// ---- settings (ini Prof...) ----
	inline bool  g_on = true;
	// 1.36.0: every pace setting is per system (Borderlands 2 style / Skyrim style) and per track kind (gun type / manufacturer)
	inline float g_killGrace = 0.25f;
	inline float g_bl2XPScale = 0.1f, g_bl2TypeRate = 1.0f, g_bl2MakerRate = 1.0f, g_bl2TypeBase = 50.0f, g_bl2TypeStep = 15.0f, g_bl2MakerBase = 50.0f, g_bl2MakerStep = 15.0f;
	inline float g_skyXPScale = 0.1f, g_skyTypeRate = 1.0f, g_skyMakerRate = 1.0f;
	inline float g_skyTypeMult = 0.291f, g_skyTypeExp = 1.95f, g_skyTypeBase = 20.0f, g_skyMakerMult = 0.291f, g_skyMakerExp = 1.95f, g_skyMakerBase = 20.0f;
	inline int   g_statsPerLevel = 1;
	inline float g_milestoneMult = 3.0f, g_decay = 0.75f, g_otherMakers = 0.25f, g_ownMaker = 1.0f, g_launcherProj = 0.5f;
	inline float g_secondary = 0.5f;
	// 1.33.0 maker curve (the user): a fifth of the type track's steps, GROWING x ProfMakerGrowth at each milestone (no floor): Bandit magazine +5 % at level 10, +50 % at level 100
	inline float g_makerStartScale = 0.208333f, g_makerGrowth = 1.105f;
	// 1.33.0 the rough rate knobs (the user): XP multipliers per kind of track, and multipliers on every bonus a level gives
	inline float g_typeBonusScale = 1.0f, g_makerBonusScale = 1.0f;
	// 1.33.0 Legendary (gun type tracks only; maker tracks never cap or reset): cap 100 + 10 a Legendary, the falloff restarts every 100 levels, a Legendary keeps 10 % of the round
	inline bool  g_legOn = true;
	inline int   g_legCap = 100, g_legCapStep = 10, g_testLevels = 0;
	inline float g_legKeep = 0.1f, g_legHold = 2.0f;
	// 1.34.0 Skyrim style (ini ProfSkyrimStyle; the user's poll): proficiency levels act like Skyrim skills - a gun type level n gives n x ProfSkyrimCharXP character XP (Skyrim: a skill
	// raised to n gives n), maker levels x ProfSkyrimMakerXP of that, every track costs ProfSkyrimCurveMult x n ^ ProfSkyrimCurveExp + ProfSkyrimCurveBase (Skyrim's skill curve shape,
	// sized so level 100 costs the same in all as the plain curve), and kill XP is times ProfSkyrimKillXP (0 = off). Off: the 0.57.0 system as it was.
	inline bool  g_skyrim = true;
	inline float g_skyCharXP = 0.5f, g_skyMakerXP = 0.0f, g_skyKill = 0.0f;
	inline float g_charPending = 0.0f;  // character XP from proficiency levels, waiting for progress.h's Apply (under g_lock)
	inline std::atomic_int g_charTold{ 0 };  // a maker's second stat grows at this share of the first (the user: half, a secondary bonus)
	inline float g_start[kStats] = { 2.0f, 2.0f, 2.0f, 2.0f, 3.0f, 4.0f, 3.0f, 3.0f, 3.0f, 1.0f, 1.0f, 1.0f };  // the vitals: percent every maker level, as is  // the shield stats: maker steps only (x MakerStartScale, x SecondaryShare)
	inline float g_floor[kStats] = { 0.5f, 0.5f, 0.5f, 0.5f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f };
	inline std::atomic<float> g_vitalPct[3]{ 0.0f, 0.0f, 0.0f };  // 1.39.0: health / magicka / stamina bonus in percent, for ApplyVitals (no lock crosses)
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
	inline float      g_typeBonus[kTypes][kStats]{}, g_makerBonus[kMakers][kStats]{};
	inline float      g_typeKept[kTypes][kStats]{};  // 1.33.0: what the type track's Legendaries keep for good (worked out from the count, so the ini's numbers apply to old ones too)  // percent (projectiles: points of percent), from the levels
	inline std::unordered_map<RE::FormID, Clock::time_point> g_deathAt;
	inline std::atomic_int g_hitsBooked{ 0 };

	inline bool Milestone(int a_n) { return a_n == 10 || a_n == 25 || a_n == 50 || a_n == 75 || a_n == 100 || (a_n > 100 && a_n % 50 == 0); }
	inline float Cost(int a_level, bool a_maker)
	{
		const float n = static_cast<float>((std::max)(0, a_level));
		if (g_skyrim) {
			return a_maker ? (std::max)(1.0f, g_skyMakerMult * std::pow(n, g_skyMakerExp) + g_skyMakerBase) : (std::max)(1.0f, g_skyTypeMult * std::pow(n, g_skyTypeExp) + g_skyTypeBase);
		}
		return a_maker ? (std::max)(1.0f, g_bl2MakerBase + g_bl2MakerStep * n) : (std::max)(1.0f, g_bl2TypeBase + g_bl2TypeStep * n);
	}
	inline float XPScale() { return g_skyrim ? g_skyXPScale : g_bl2XPScale; }
	inline float TypeRate() { return g_skyrim ? g_skyTypeRate : g_bl2TypeRate; }
	inline float MakerRate() { return g_skyrim ? g_skyMakerRate : g_bl2MakerRate; }
	inline float StepOf(int a_stat, int a_passed) { return (std::max)(g_floor[a_stat], g_start[a_stat] * std::pow(g_decay, static_cast<float>(a_passed))); }
	inline float MakerStepOf(int a_stat, int a_passed) { return g_start[a_stat] * g_makerStartScale * std::pow(g_makerGrowth, static_cast<float>((std::min)(a_passed, 200))); }
	inline int   CapOf(const Track& a_t) { return g_legCap + g_legCapStep * (std::max)(0, a_t.legendary); }
	inline bool  Capped(int a_type) { return g_legOn && a_type >= 0 && a_type < kTypes && g_type[a_type].level >= CapOf(g_type[a_type]); }

	// what level n of a track adds, stat by stat (a_maker < 0: a type track). 1.33.0: maker tracks grow (MakerStepOf); a type track's falloff starts again every
	// ProfLegendaryCap levels (level 101 gives what level 1 gave, 110 what 10 gave: the user's Legendary rule); every gain times its kind's bonus scale.
	inline void Gains(int a_maker, int a_n, float a_out[kStats])
	{
		std::fill(a_out, a_out + kStats, 0.0f);
		const int n = a_maker >= 0 || !g_legOn || g_legCap < 1 ? a_n : ((a_n - 1) % g_legCap) + 1;
		int passed = 0;
		for (int m = 1; m < n; ++m) {
			passed += Milestone(m) ? 1 : 0;
		}
		const bool milestone = Milestone(n);
		if (a_maker >= 0) {
			if (IsVital(kMakerStats[a_maker][1])) {  // 1.39.0: a flat percent every level; the primary on odd levels and milestones as before
				a_out[kMakerStats[a_maker][1]] += g_start[kMakerStats[a_maker][1]];
				const int s = kMakerStats[a_maker][0];
				if (milestone) {
					a_out[s] += MakerStepOf(s, passed) * g_milestoneMult * g_makerBonusScale;
				} else if ((n - 1) % 2 == 0) {
					a_out[s] += MakerStepOf(s, passed) * g_makerBonusScale;
				}
				return;
			}
			if (milestone) {
				for (int i = 0; i < 2; ++i) {
					const int s = kMakerStats[a_maker][i];
					a_out[s] += MakerStepOf(s, passed) * g_milestoneMult * (i == 0 ? 1.0f : g_secondary) * g_makerBonusScale;
				}
			} else {
				const int i = (n - 1) % 2;
				const int s = kMakerStats[a_maker][i];
				a_out[s] += MakerStepOf(s, passed) * (i == 0 ? 1.0f : g_secondary) * g_makerBonusScale;
			}
			return;
		}
		const int per = std::clamp(g_statsPerLevel, 1, kGunStats);
		const int first = ((n - 1) * per) % kGunStats;
		const int count = milestone ? 4 : per;
		for (int i = 0; i < count; ++i) {
			const int s = (first + i) % kGunStats;
			a_out[s] += StepOf(s, passed) * (milestone ? g_milestoneMult : 1.0f) * g_typeBonusScale;
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
			std::fill(std::begin(g_typeKept[t]), std::end(g_typeKept[t]), 0.0f);
			float round[kStats];
			for (int r = 0; r < (std::min)(g_type[t].legendary, 200); ++r) {  // each Legendary kept ProfLegendaryKeep of the track at that round's cap
				Recompute(-1, g_legCap + g_legCapStep * r, round);
				for (int s = 0; s < kStats; ++s) {
					g_typeKept[t][s] += round[s] * g_legKeep;
				}
			}
		}
		float shieldBonus[3]{}, vital[3]{};
		for (int m = 0; m < kMakers; ++m) {
			Recompute(m, g_maker[m].level, g_makerBonus[m]);
			for (int i = 0; i < 3; ++i) {  // the makers' second stats: shield bonuses that always apply (handed to shield.h as plain numbers: no lock crosses)
				shieldBonus[i] += g_makerBonus[m][kShieldCap + i] * g_ownMaker;
				vital[i] += g_makerBonus[m][kHealth + i];  // 1.39.0: the character's health / magicka / stamina
			}
		}
		const bool on = g_on;
		for (int i = 0; i < 3; ++i) {
			g_vitalPct[i] = on ? vital[i] : 0.0f;
		}
		shield::g_profShieldCap = on ? shieldBonus[0] : 0.0f;
		shield::g_profShieldRate = on ? shieldBonus[1] : 0.0f;
		shield::g_profShieldDelay = on ? shieldBonus[2] : 0.0f;
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
				a_out[s] += g_typeBonus[a_type][s] + g_typeKept[a_type][s];
			}
		}
		for (int m = 0; m < kMakers; ++m) {
			if (m == a_maker) {  // its own maker: both stats in full
				for (int s = 0; s < kStats; ++s) {
					a_out[s] += g_makerBonus[m][s] * g_ownMaker;
				}
			} else {  // every other gun: only that maker's PRIMARY stat, at the share (the secondary is for the maker's own guns)
				const int s = kMakerStats[m][0];
				a_out[s] += g_makerBonus[m][s] * g_otherMakers;
				if (kSecondaryEverywhere[m]) {  // 1.37.3: Torgue's projectile chance belongs to the character: every gun gets it in full
					const int s2 = kMakerStats[m][1];
					a_out[s2] += g_makerBonus[m][s2] * g_ownMaker;
				}
			}
		}
		if (a_type == kLauncher) {
			a_out[kProj] *= g_launcherProj;
		}
	}

	struct View
	{
		int   typeLevel = 0, makerLevel = 0, typeLegendary = 0;
		float typeFrac = 0.0f, makerFrac = 0.0f;
		bool  typeReady = false;  // at its cap: a Legendary is waiting
	};
	inline View ViewOf(int a_type, int a_maker)  // for the HUD line
	{
		View v;
		const std::lock_guard guard(g_lock);
		if (a_type >= 0 && a_type < kTypes) {
			v.typeLevel = g_type[a_type].level;
			v.typeFrac = std::clamp(g_type[a_type].xp / Cost(g_type[a_type].level, false), 0.0f, 1.0f);
			v.typeLegendary = g_type[a_type].legendary;
			v.typeReady = Capped(a_type);
			if (v.typeReady) {
				v.typeFrac = 1.0f;
			}
		}
		if (a_maker >= 0 && a_maker < kMakers) {
			v.makerLevel = g_maker[a_maker].level;
			v.makerFrac = std::clamp(g_maker[a_maker].xp / Cost(g_maker[a_maker].level, true), 0.0f, 1.0f);
		}
		return v;
	}

	// 1.40.0: one track for the stats menu (statsmenu in main.cpp): level, XP into the level and the next level's cost, Legendary count, its bonuses (percent)
	struct TrackView
	{
		int   level = 0, legendary = 0, cap = 0;
		float xp = 0.0f, next = 1.0f;
		float bonus[kStats]{};
	};
	inline TrackView TrackOf(int a_index, bool a_maker)
	{
		TrackView v;
		const std::lock_guard guard(g_lock);
		if (a_maker ? (a_index < 0 || a_index >= kMakers) : (a_index < 0 || a_index >= kTypes)) {
			return v;
		}
		const Track& t = a_maker ? g_maker[a_index] : g_type[a_index];
		v.level = t.level;
		v.legendary = t.legendary;
		v.cap = a_maker || !g_legOn ? 0 : CapOf(t);
		v.xp = t.xp;
		v.next = Cost(t.level, a_maker);
		for (int s = 0; s < kStats; ++s) {
			v.bonus[s] = a_maker ? g_makerBonus[a_index][s] : g_typeBonus[a_index][s] + g_typeKept[a_index][s];
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
		const float xp = a_damage * XPScale();
		bool        counted = a_alive;
		{
			const std::lock_guard guard(g_lock);
			if (!a_alive) {
				const auto it = g_deathAt.find(a_target);
				counted = it != g_deathAt.end() && std::chrono::duration<float>(Clock::now() - it->second).count() <= g_killGrace;
			}
			if (counted) {
				if (a_type >= 0 && a_type < kTypes) {
					g_pendType[a_type] += xp * TypeRate();
				}
				if (a_maker >= 0 && a_maker < kMakers) {
					g_pendMaker[a_maker] += xp * MakerRate();
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
				const bool capped = a_maker < 0 && g_legOn;  // a type track stops at its cap until it goes Legendary (a level's worth of XP waits)
				if (capped && a_t.level >= CapOf(a_t)) {
					a_t.xp = (std::min)(a_t.xp + a_pend, Cost(a_t.level, a_maker >= 0));
					a_t.total += a_pend;
					a_pend = 0.0f;
					return;
				}
				a_t.xp += a_pend;
				a_t.total += a_pend;
				a_pend = 0.0f;
				for (int guard2 = 0; guard2 < 50 && a_t.xp >= Cost(a_t.level, a_maker >= 0) && !(capped && a_t.level >= CapOf(a_t)); ++guard2) {
					a_t.xp -= Cost(a_t.level, a_maker >= 0);
					++a_t.level;
					changed = true;
					float g[kStats];
					Gains(a_maker, a_t.level, g);
					const std::string text = fmt::format("{} proficiency {}{}: {}", a_name, a_t.level, Milestone(a_t.level) ? " (milestone)" : "", GainText(g));
					notices.push_back(text);
					SKSE::log::info("prof: {} (total XP {:.0f}, next level at {:.0f})", text, a_t.total, Cost(a_t.level, a_maker >= 0));
					if (g_skyrim) {  // like a Skyrim skill: the new level is character XP
						const float give = static_cast<float>(a_t.level) * g_skyCharXP * (a_maker >= 0 ? g_skyMakerXP : 1.0f);
						if (give > 0.0f) {
							g_charPending += give;
							if (g_charTold.fetch_add(1) < 30) {
								SKSE::log::info("prof: {} {} gives {:.1f} character XP (Skyrim style)", a_name, a_t.level, give);
							}
						}
					}
					if (capped && a_t.level >= CapOf(a_t)) {
						const std::string ready = fmt::format("{} proficiency {}: LEGENDARY READY - hold the reload key {:.0f} s with a {} in hand", a_name, a_t.level, g_legHold, a_name);
						notices.push_back(ready);
						SKSE::log::info("prof: {} (Legendary {} so far)", ready, a_t.legendary);
					}
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

	// 1.34.0: the character XP the proficiency levels have earned since the last call (progress.h adds it to the level meter)
	inline float TakeCharXP()
	{
		const std::lock_guard guard(g_lock);
		const float v = g_charPending;
		g_charPending = 0.0f;
		return v;
	}

	// 1.33.0: a type track at its cap goes Legendary (from main.cpp's tick when the reload key is held ProfLegendaryHold seconds with a gun of that type)
	inline bool Ready(int a_type)
	{
		const std::lock_guard guard(g_lock);
		return Capped(a_type);
	}

	inline bool MakeLegendary(int a_type)
	{
		std::string text;
		{
			const std::lock_guard guard(g_lock);
			if (!Capped(a_type)) {
				return false;
			}
			auto&       t = g_type[a_type];
			const float before[kStats] = { g_typeKept[a_type][0], g_typeKept[a_type][1], g_typeKept[a_type][2], g_typeKept[a_type][3], g_typeKept[a_type][4], g_typeKept[a_type][5] };
			const int   cap = t.level;
			++t.legendary;
			t.level = 0;  // the waiting XP stays and counts towards level 1
			RecomputeAllLocked();
			float gain[kStats];
			for (int s = 0; s < kStats; ++s) {
				gain[s] = g_typeKept[a_type][s] - before[s];
			}
			text = fmt::format("{} LEGENDARY {}: kept for good {}; next cap {}", kTypeNames[a_type], t.legendary, GainText(gain), CapOf(t));
			SKSE::log::info("prof: {} (from level {}; kept in all: damage +{:.1f}%, accuracy +{:.1f}%, reload +{:.1f}%, fire rate +{:.1f}%, magazine +{:.1f}%, bonus projectiles {:.1f})", text, cap,
				g_typeKept[a_type][0], g_typeKept[a_type][1], g_typeKept[a_type][2], g_typeKept[a_type][3], g_typeKept[a_type][4], g_typeKept[a_type][5]);
		}
		if (g_notices) {
			RE::SendHUDMessage::ShowHUDMessage(text.c_str(), nullptr, true);
		}
		return true;
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
		static bool testDone = false;  // ProfTestLevels: once a game session, every track gets N levels (to try the cap and Legendary)
		if (g_testLevels > 0 && !testDone) {
			testDone = true;
			for (auto& tr : g_type) {
				tr.level = g_legOn ? (std::min)(tr.level + g_testLevels, CapOf(tr)) : tr.level + g_testLevels;
			}
			for (auto& tr : g_maker) {
				tr.level += g_testLevels;
			}
			SKSE::log::info("prof: ProfTestLevels {}: every track raised (type tracks at most to their cap)", g_testLevels);
		}
		RecomputeAllLocked();
		std::string levels;
		for (int t = 0; t < kTypes; ++t) {
			levels += fmt::format("{}{} {}{}", levels.empty() ? "" : ", ", kTypeNames[t], g_type[t].level, g_type[t].legendary > 0 ? fmt::format(" (Legendary {})", g_type[t].legendary) : std::string());
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
		g_charPending = 0.0f;
		g_deathAt.clear();
		RecomputeAllLocked();
	}

	inline void Start()
	{
		shield::g_extraSave.push_back(&Save);
		shield::g_extraLoad.push_back(&Load);
		shield::g_extraRevert.push_back(&Revert);
		SKSE::log::info("prof: {}; system {}; {} stat(s) a level, milestones x{:.1f}, decay {:.2f}, other makers' primary stat x{:.2f}, own maker x{:.2f}, second stat (shields, always) x{:.2f}, launchers' projectiles x{:.2f}",
			g_on ? "on" : "off", g_skyrim ? "Skyrim style" : "Borderlands 2 style", g_statsPerLevel, g_milestoneMult, g_decay, g_otherMakers, g_ownMaker, g_secondary, g_launcherProj);
		SKSE::log::info("prof: pace - XP = damage x {:.2f}, gun type XP x{:.2f}, maker XP x{:.2f}; gun type levels cost {:.0f} / {:.0f} / {:.0f} / {:.0f} (levels 1 / 10 / 50 / 100), maker levels {:.0f} / {:.0f} / {:.0f} / {:.0f}",
			XPScale(), TypeRate(), MakerRate(), Cost(1, false), Cost(10, false), Cost(50, false), Cost(100, false), Cost(1, true), Cost(10, true), Cost(50, true), Cost(100, true));
		SKSE::log::info("prof: bonuses x{:.2f} (types) / x{:.2f} (makers); maker steps x{:.3f} of the type's, growing x{:.3f} a milestone; Legendary {} (cap {} + {} each, keeps {:.0f}%, hold {:.1f} s), test levels {}",
			g_typeBonusScale, g_makerBonusScale, g_makerStartScale, g_makerGrowth, g_legOn ? "on" : "off", g_legCap, g_legCapStep, g_legKeep * 100.0f, g_legHold, g_testLevels);
		if (g_skyrim) {
			SKSE::log::info("prof: Skyrim style: a gun type level n gives n x {:.2f} character XP, maker levels x{:.2f} of that, kill XP x{:.2f}", g_skyCharXP, g_skyMakerXP, g_skyKill);
		}
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
		static constexpr std::string_view statKeys[kStats] = { "Damage", "Accuracy", "Reload", "Rate", "Magazine", "Projectile", "ShieldCapacity", "ShieldRecharge", "ShieldDelay", "Health", "Magicka", "Stamina" };
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
		} else if (k == "KillGrace") {
			g_killGrace = std::clamp(v, 0.0f, 5.0f);
		} else if (k == "StatsPerLevel") {
			g_statsPerLevel = std::clamp(static_cast<int>(v), 1, kGunStats);
		} else if (k == "MilestoneMult") {
			g_milestoneMult = std::clamp(v, 0.0f, 100.0f);
		} else if (k == "Decay") {
			g_decay = std::clamp(v, 0.0f, 1.0f);
		} else if (k == "OtherMakers") {
			g_otherMakers = std::clamp(v, 0.0f, 10.0f);
		} else if (k == "SkyrimStyle") {
			g_skyrim = v != 0.0f;
		} else if (k == "SkyrimCharXP") {
			g_skyCharXP = std::clamp(v, 0.0f, 100.0f);
		} else if (k == "SkyrimMakerXP") {
			g_skyMakerXP = std::clamp(v, 0.0f, 100.0f);
		} else if (k == "SkyrimKillXP") {
			g_skyKill = std::clamp(v, 0.0f, 100.0f);
		} else if (k == "BL2XPScale") {
			g_bl2XPScale = std::clamp(v, 0.0f, 1000.0f);
		} else if (k == "BL2TypeRate") {
			g_bl2TypeRate = std::clamp(v, 0.0f, 1000.0f);
		} else if (k == "BL2MakerRate") {
			g_bl2MakerRate = std::clamp(v, 0.0f, 1000.0f);
		} else if (k == "BL2TypeBase") {
			g_bl2TypeBase = std::clamp(v, 1.0f, 1e7f);
		} else if (k == "BL2TypeStep") {
			g_bl2TypeStep = std::clamp(v, 0.0f, 1e7f);
		} else if (k == "BL2MakerBase") {
			g_bl2MakerBase = std::clamp(v, 1.0f, 1e7f);
		} else if (k == "BL2MakerStep") {
			g_bl2MakerStep = std::clamp(v, 0.0f, 1e7f);
		} else if (k == "SkyrimXPScale") {
			g_skyXPScale = std::clamp(v, 0.0f, 1000.0f);
		} else if (k == "SkyrimTypeRate") {
			g_skyTypeRate = std::clamp(v, 0.0f, 1000.0f);
		} else if (k == "SkyrimMakerRate") {
			g_skyMakerRate = std::clamp(v, 0.0f, 1000.0f);
		} else if (k == "SkyrimTypeCurveMult") {
			g_skyTypeMult = std::clamp(v, 0.0f, 1e6f);
		} else if (k == "SkyrimTypeCurveExp") {
			g_skyTypeExp = std::clamp(v, 0.0f, 4.0f);
		} else if (k == "SkyrimTypeCurveBase") {
			g_skyTypeBase = std::clamp(v, 0.0f, 1e7f);
		} else if (k == "SkyrimMakerCurveMult") {
			g_skyMakerMult = std::clamp(v, 0.0f, 1e6f);
		} else if (k == "SkyrimMakerCurveExp") {
			g_skyMakerExp = std::clamp(v, 0.0f, 4.0f);
		} else if (k == "SkyrimMakerCurveBase") {
			g_skyMakerBase = std::clamp(v, 0.0f, 1e7f);
		} else if (k == "TypeBonus") {
			g_typeBonusScale = std::clamp(v, 0.0f, 100.0f);
		} else if (k == "MakerBonus") {
			g_makerBonusScale = std::clamp(v, 0.0f, 100.0f);
		} else if (k == "MakerStartScale") {
			g_makerStartScale = std::clamp(v, 0.0f, 100.0f);
		} else if (k == "MakerGrowth") {
			g_makerGrowth = std::clamp(v, 0.5f, 2.0f);
		} else if (k == "Legendary") {
			g_legOn = v != 0.0f;
		} else if (k == "LegendaryCap") {
			g_legCap = std::clamp(static_cast<int>(v), 1, 100000);
		} else if (k == "LegendaryCapStep") {
			g_legCapStep = std::clamp(static_cast<int>(v), 0, 100000);
		} else if (k == "LegendaryKeep") {
			g_legKeep = std::clamp(v, 0.0f, 10.0f);
		} else if (k == "LegendaryHold") {
			g_legHold = std::clamp(v, 0.2f, 30.0f);
		} else if (k == "TestLevels") {
			g_testLevels = std::clamp(static_cast<int>(v), 0, 100000);
		} else if (k == "SecondaryShare") {
			g_secondary = std::clamp(v, 0.0f, 10.0f);
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
