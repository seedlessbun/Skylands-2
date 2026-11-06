// Badass enemies (docs/badass-roadmap.md): stage 1 (1.25.0) tiers and stats; 1.26.0 adds the name prefix and size (stage 4, moved up) and the guaranteed drops (stage 2).
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
#include "despawn.h"
#include "relic.h"
#include "shield.h"
#include "shielditems.h"

#include <regex>
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
	// 1.26.0: presentation (stage 4, moved up at the user's request) and the guaranteed drops (stage 2)
	inline bool  g_names = true, g_size = true, g_drops = true;
	inline float g_scale[4] = { 1.0f, 1.15f, 1.30f, 1.45f };
	// 1.28.0 (user: "a super badass mudcrab was pretty small", "low level creatures should still pose a threat"): creatures grow g_creatureSize more per tier,
	// count their own health as at least g_creatureHealth + g_creatureHealthPerLevel x the player's level, and hit harder by g_creatureGap per level they are below the player
	inline float g_creatureSize = 0.15f;
	inline float g_creatureHealth = 20.0f, g_creatureHealthPerLevel = 5.0f;
	inline float g_creatureGap = 0.05f, g_creatureGapMax = 3.0f;
	inline float g_dropWeight[3] = { 44.44f, 20.0f, 8.89f };  // gun, shield, relic (sheets/enemy_drops.json: BL2's enemy gear pool)
	inline constexpr int kGateLevel[4] = { 0, 8, 15, 30 };    // the rarity gates of a tier's drops use at least this level
	inline constexpr int kFloors[4][3] = { { 0, 0, 0 }, { 2, 0, 0 }, { 3, 2, 0 }, { 4, 3, 2 } };  // BL2's 1 / 2 / 3 guaranteed drops and their lowest rarities
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
		bool       tempHealth = false;  // the health bonus is a TEMPORARY modifier (a 0.49.0/0.50.0 save): taken off and given again as a permanent one
		std::uint16_t scaleBefore = 0;  // 1.28.0: the reference's own scale (refScale, percent) before Present grew it; 0 = not seen yet (an older save: 100)
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

	// ---- the enemy classes (sheets/enemy_stats.json, written by the installer to Data\SKSE\Plugins\SkylandsEnemies.txt): matched by the race's editor id ----
	struct Class
	{
		std::string id, kind;  // kind: person, creature, dragon, critter
		std::regex  rx;
		float       dropScale = 0.5f;
		int         minRarity = 1;
		bool        badass = true;
	};
	inline std::vector<Class>                  g_classes;  // filled once at data load, read only after
	inline std::mutex                          g_classLock;
	inline std::unordered_map<RE::FormID, int> g_classOfRace;
	inline bool  g_creatureDrops = true, g_dragonBoss = true;
	inline float g_creatureScale = 0.5f, g_creatureCap = 60.0f, g_gunPercent = 25.0f;

	inline void LoadClasses()
	{
		std::ifstream f("Data/SKSE/Plugins/SkylandsEnemies.txt");
		std::string   line;
		while (f && std::getline(f, line)) {
			if (!line.empty() && line.back() == '\r') {
				line.pop_back();
			}
			if (line.rfind("class\t", 0) != 0) {
				continue;
			}
			std::vector<std::string> cols;
			std::size_t              start = 6;
			for (std::size_t tab; (tab = line.find('\t', start)) != std::string::npos; start = tab + 1) {
				cols.push_back(line.substr(start, tab - start));
			}
			cols.push_back(line.substr(start));
			if (cols.size() < 6) {
				continue;
			}
			try {
				Class c;
				c.id = cols[0];
				c.rx = std::regex(cols[1], std::regex::ECMAScript | std::regex::icase);
				c.kind = cols[2];
				c.dropScale = std::stof(cols[3]);
				c.minRarity = std::clamp(std::stoi(cols[4]), 1, 6);
				c.badass = cols[5] == "yes";
				g_classes.push_back(std::move(c));
			} catch (...) {
				SKSE::log::warn("badass: enemy class line not understood: {}", line);
			}
		}
		std::string names;
		for (const auto& c : g_classes) {
			names += (names.empty() ? "" : ", ") + c.id;
		}
		SKSE::log::info("badass: {} enemy classes from SkylandsEnemies.txt ({})", g_classes.size(), names.empty() ? "none: every creature uses CreatureDropScale" : names);
	}

	inline int ClassOf(RE::Actor* a_actor)  // -1: no row for its race
	{
		const auto race = a_actor ? a_actor->GetRace() : nullptr;
		if (!race) {
			return -1;
		}
		const std::lock_guard guard(g_classLock);
		if (const auto it = g_classOfRace.find(race->GetFormID()); it != g_classOfRace.end()) {
			return it->second;
		}
		const std::string edid = race->formEditorID.c_str() ? race->formEditorID.c_str() : "";
		int               found = -1;
		for (int i = 0; i < static_cast<int>(g_classes.size()) && found < 0; ++i) {
			if (!edid.empty() && std::regex_search(edid, g_classes[i].rx)) {
				found = i;
			}
		}
		g_classOfRace[race->GetFormID()] = found;
		static std::atomic_int told{ 0 };
		if (told.fetch_add(1) < 40) {
			SKSE::log::info("badass: race {} is class {}", edid, found >= 0 ? g_classes[found].id : std::string("(none)"));
		}
		return found;
	}

	inline bool IsCreature(RE::Actor* a_actor)
	{
		const int c = ClassOf(a_actor);
		return c >= 0 ? g_classes[c].kind != "person" : !shielditems::IsPerson(a_actor);
	}

	inline bool Eligible(RE::Actor* a_actor, RE::PlayerCharacter* a_player)
	{
		if (const int c = ClassOf(a_actor); c >= 0 && !g_classes[c].badass) {
			return false;  // the sheet says this kind is never a Badass (mammoths, critters)
		}
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
	// 1.26.1: the HEALTH bonus is a PERMANENT modifier: the game's enemy health bar measures current health against the permanent maximum (base + permanent modifiers),
	// so a temporary bonus left the bar full until the health fell below the old maximum (user report on 0.50.0). Damage and speed stay temporary.
	inline void Mod(RE::Actor* a_actor, RE::ActorValue a_av, float a_value, RE::ACTOR_VALUE_MODIFIER a_mod = RE::ACTOR_VALUE_MODIFIER::kTemporary)
	{
		if (const auto ao = a_actor->AsActorValueOwner(); ao && a_value != 0.0f) {
			ao->ModActorValue(a_mod, a_av, a_value);
		}
	}

	inline float Permanent(RE::Actor* a_actor)
	{
		const auto ao = a_actor->AsActorValueOwner();
		return ao ? ao->GetPermanentActorValue(RE::ActorValue::kHealth) : 0.0f;
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
		const bool  creature = IsCreature(a_actor);
		const auto  player = RE::PlayerCharacter::GetSingleton();
		const int   playerLevel = player ? player->GetLevel() : 1;
		// a creature counts its own health as at least the floor (a 5-point mudcrab would otherwise be a 15-point Badass)
		const float counted = creature ? std::max(own, g_creatureHealth + g_creatureHealthPerLevel * static_cast<float>(playerLevel)) : own;
		// and hits harder per level it is below the player
		const float gap = creature ? std::clamp(1.0f + g_creatureGap * static_cast<float>(std::max(0, playerLevel - static_cast<int>(a_actor->GetLevel()))), 1.0f, std::max(1.0f, g_creatureGapMax)) : 1.0f;
		const float hpBefore = Value(a_actor, RE::ActorValue::kHealth);
		const float dmgBefore = Value(a_actor, RE::ActorValue::kAttackDamageMult);
		const float speedBefore = Value(a_actor, RE::ActorValue::kSpeedMult);
		a_entry.health = std::max(0.0f, g_health[t] * counted - own);
		a_entry.melee = g_melee[t] * gap - 1.0f;
		a_entry.speed = (g_speed[t] - 1.0f) * 100.0f;
		const float permBefore = Permanent(a_actor);
		Mod(a_actor, RE::ActorValue::kHealth, a_entry.health, RE::ACTOR_VALUE_MODIFIER::kPermanent);
		a_entry.tempHealth = false;
		Mod(a_actor, RE::ActorValue::kAttackDamageMult, a_entry.melee);
		Mod(a_actor, RE::ActorValue::kSpeedMult, a_entry.speed);
		a_entry.applied = true;
		a_entry.check = false;
		a_entry.maxBefore = maxBefore;
		if (g_given.fetch_add(1) < 80) {
			const char* name = a_actor->GetName();
			SKSE::log::info("badass: {:08X} \"{}\" (level {}, {}{}) is {} {} [{}]: health max {:.0f} -> {:.0f} (current {:.0f} -> {:.0f}; the bar's maximum {:.0f} -> {:.0f}; own {:.0f} x{:.2f}{}), melee damage x{:.2f} "
			                "(AttackDamageMult {:.2f} -> {:.2f}), speed x{:.2f} (SpeedMult {:.0f} -> {:.0f}), plugin-launched gun bullets x{:.2f}",
				a_actor->GetFormID(), name ? name : "?", a_actor->GetLevel(), shielditems::IsPerson(a_actor) ? "person" : "creature", IsDragon(a_actor) ? ", dragon" : shielditems::IsBoss(a_actor) ? ", boss" : "",
				t == 3 ? "an" : "a", kTierNames[t], a_why, maxBefore, a_actor->GetActorValueMax(RE::ActorValue::kHealth), hpBefore, Value(a_actor, RE::ActorValue::kHealth), permBefore, Permanent(a_actor), own, g_health[t],
				(shieldCap > 0.0f ? fmt::format(", its shield {:.0f} not counted", shieldCap) : std::string()) +
					(counted > own ? fmt::format(", counted as {:.0f}: the creature floor at player level {}", counted, playerLevel) : std::string()) +
					(gap > 1.0f ? fmt::format(", melee x{:.2f} for {} levels below the player", gap, playerLevel - static_cast<int>(a_actor->GetLevel())) : std::string()),
				g_melee[t] * gap, dmgBefore, Value(a_actor, RE::ActorValue::kAttackDamageMult), g_speed[t],
				speedBefore, Value(a_actor, RE::ActorValue::kSpeedMult), g_gun[t]);
		}
		return a_entry;
	}

	inline void Strip(RE::Actor* a_actor, const Entry& a_entry, const char* a_why)
	{
		if (!a_entry.applied) {
			return;
		}
		Mod(a_actor, RE::ActorValue::kHealth, -a_entry.health, a_entry.tempHealth ? RE::ACTOR_VALUE_MODIFIER::kTemporary : RE::ACTOR_VALUE_MODIFIER::kPermanent);
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

	// ---- presentation: the tier's name before the actor's own, and a bigger body (game thread) ----
	inline void Present(RE::Actor* a_actor, int a_tier)
	{
		const int t = std::clamp(a_tier, 1, 3);
		if (g_names) {
			const char*            raw = a_actor->GetDisplayFullName();
			const std::string_view name = raw ? raw : "";
			if (!name.empty() && name.find("Badass") == std::string_view::npos) {  // the installer's renamed "Badass ..." bandits keep their name
				const std::string full = fmt::format("{} {}", kTierNames[t], name);
				a_actor->SetDisplayName(RE::BSFixedString(full.c_str()), true);
				static std::atomic_int told{ 0 };
				if (told.fetch_add(1) < 40) {
					SKSE::log::info("badass: {:08X} is now called \"{}\"", a_actor->GetFormID(), full);
				}
			}
		}
		// 1.28.0: GetScale is the reference's scale times the race/base height (a mudcrab is 0.75), so the old test "GetScale < tier scale" never held for small
		// creatures (they were set to 1.15, read back 0.86, and set again every pass). The reference's own scale (refScale, percent) is grown from what it was.
		const std::uint16_t ref = a_actor->GetReferenceRuntimeData().refScale;
		std::uint16_t       first = 0;
		{
			const std::lock_guard guard(g_lock);
			auto&                 e = g_entries[a_actor->GetFormID()];
			if (e.scaleBefore == 0) {
				e.scaleBefore = ref > 0 ? ref : 100;
			}
			first = e.scaleBefore;
		}
		const float own = static_cast<float>(first) / 100.0f;
		const float want = own * (g_scale[t] + (IsCreature(a_actor) ? g_creatureSize * static_cast<float>(t) : 0.0f));
		if (g_size && static_cast<float>(ref) / 100.0f < want - 0.01f) {
			const float before = a_actor->GetScale();
			a_actor->SetScale(want);
			static std::atomic_int told{ 0 };
			if (told.fetch_add(1) < 40) {
				SKSE::log::info("badass: {:08X} size {:.2f} -> {:.2f}", a_actor->GetFormID(), before, a_actor->GetScale());
			}
		}
	}

	// ---- guaranteed drops (stage 2): a Badass 1 item (at least uncommon), a Super 2 (rare, uncommon), an Ultimate 3 (epic, rare, uncommon) ----
	inline std::vector<RE::FormID> g_guns[7];
	inline bool                    g_gunsRead = false;

	inline void ReadGuns()  // game thread, once: every Skylands gun by rarity
	{
		if (g_gunsRead) {
			return;
		}
		g_gunsRead = true;
		const auto handler = RE::TESDataHandler::GetSingleton();
		if (!handler) {
			return;
		}
		for (const auto weapon : handler->GetFormArray<RE::TESObjectWEAP>()) {
			if (weapon && weapon->HasKeywordString("SkylandsGun")) {
				if (const int r = despawn::RarityOf(weapon); r >= 1 && r <= 6) {
					g_guns[r].push_back(weapon->GetFormID());
				}
			}
		}
		SKSE::log::info("badass: drop lists - guns by rarity {} {} {} {} {} {}, shields {} {} {} {} {} {}, relics {} {} {} {} {} {}", g_guns[1].size(), g_guns[2].size(), g_guns[3].size(), g_guns[4].size(),
			g_guns[5].size(), g_guns[6].size(), shielditems::g_catalog[1].size(), shielditems::g_catalog[2].size(), shielditems::g_catalog[3].size(), shielditems::g_catalog[4].size(),
			shielditems::g_catalog[5].size(), shielditems::g_catalog[6].size(), relic::g_catalog[1].size(), relic::g_catalog[2].size(), relic::g_catalog[3].size(), relic::g_catalog[4].size(),
			relic::g_catalog[5].size(), relic::g_catalog[6].size());
	}

	inline const std::vector<RE::FormID>& ListOf(int a_type, int a_rarity)
	{
		return a_type == 0 ? g_guns[a_rarity] : a_type == 1 ? shielditems::g_catalog[a_rarity] : relic::g_catalog[a_rarity];
	}

	// one item: the type by BL2's enemy gear weights, the rarity by the guns' weights shifted up by the tier ("up n": rarity r takes the weight of r - n), at least a_floor,
	// the level gates at a_level (if they leave nothing, the floor alone)
	inline RE::TESBoundObject* PickDrop(std::uint64_t a_seed, int a_tier, int a_floor, int a_level, int& a_rarityOut, int& a_typeOut)
	{
		const float total = g_dropWeight[0] + g_dropWeight[1] + g_dropWeight[2];
		float       roll = total > 0.0f ? static_cast<float>(shielditems::Mix(a_seed ^ 0x7779) % 100000ULL) / 100000.0f * total : 0.0f;
		int         first = 0;
		for (; first < 2 && roll >= g_dropWeight[first]; ++first) {
			roll -= g_dropWeight[first];
		}
		for (int k = 0; k < 3; ++k) {
			const int type = (first + k) % 3;
			for (int gated = 1; gated >= 0; --gated) {
				int weights[7]{}, sum = 0;
				for (int r = std::max(1, a_floor); r <= 6; ++r) {
					const int below = r - a_tier;
					if (below < 1 || ListOf(type, r).empty() || (gated && a_level < shielditems::kLevelFor[r])) {
						continue;
					}
					weights[r] = shielditems::kWeight[below];
					sum += weights[r];
				}
				if (sum <= 0) {
					continue;
				}
				int pick = static_cast<int>(shielditems::Mix(a_seed ^ 0x4242) % static_cast<std::uint64_t>(sum));
				for (int r = 1; r <= 6; ++r) {
					if (pick < weights[r]) {
						const auto& list = ListOf(type, r);
						a_rarityOut = r;
						a_typeOut = type;
						const auto form = RE::TESForm::LookupByID(list[shielditems::Mix(a_seed ^ 0x9999) % list.size()]);
						return form && form->IsBoundObject() ? static_cast<RE::TESBoundObject*>(form) : nullptr;
					}
					pick -= weights[r];
				}
			}
		}
		return nullptr;
	}

	struct Pending
	{
		RE::FormID        id = 0;
		int               n = 0;            // items
		int               floor[3]{};       // each item's lowest rarity
		int               shift[3]{};       // and how far its weights are moved up
		int               level = 1;        // the rarity gates' level
		std::string       what;             // for the log
		Clock::time_point due{};
	};
	inline std::mutex           g_pendLock;
	inline std::vector<Pending> g_pending;
	inline std::atomic_uint64_t g_dropSerial{ 1 };

	inline void Drop(const Pending& a_p)
	{
		const auto body = RE::TESForm::LookupByID<RE::Actor>(a_p.id);
		if (!body || !body->GetParentCell()) {
			return;
		}
		ReadGuns();
		const int   level = a_p.level;
		std::string said;
		for (int i = 0; i < std::clamp(a_p.n, 0, 3); ++i) {
			int        rarity = 0, type = 0;
			const auto seed = shielditems::Mix(a_p.id ^ (g_dropSerial.fetch_add(1) * 0x9E3779B97F4A7C15ULL));
			const auto item = PickDrop(seed, a_p.shift[i], a_p.floor[i], level, rarity, type);
			if (!item) {
				said += (said.empty() ? "" : ", ") + std::string("nothing to pick");
				continue;
			}
			const auto placed = body->PlaceObjectAtMe(item, false);
			const char* name = item->GetName();
			said += fmt::format("{}\"{}\" ({} {}){}", said.empty() ? "" : ", ", name ? name : "?", despawn::kRarityNames[std::clamp(rarity, 0, 6)], type == 0 ? "gun" : type == 1 ? "shield" : "relic",
				placed ? "" : " NOT PLACED");
		}
		static std::atomic_int told{ 0 };
		if (told.fetch_add(1) < 60) {
			SKSE::log::info("badass: {:08X} ({}) dropped {}: {} (rarity gates at level {})", a_p.id, a_p.what, a_p.n, said, level);
		}
	}

	// ---- creature drops (stage 3, docs/badass-roadmap.md 3.5): a creature that dies hostile to the player rolls once ----
	// chance = its class's drop_scale x what a person of its level leaves on average (a gun CreatureGunPercent + the shield carry x ShieldDropPercent + the relic carry x
	// RelicDropPercent), at most CreatureDropCap; one item, the usual rarity weights at the creature's level. A dragon always drops two (rare or better, gates at level 15+),
	// another boss creature one (rare or better). A Badass creature has its tier's guaranteed drop instead.
	inline float PersonChance(int a_level)
	{
		const float l = static_cast<float>(std::max(0, a_level - 1));
		const float shieldCarry = std::clamp(static_cast<float>(shielditems::g_enemyPercent) + shielditems::g_perLevel * l, 0.0f, 100.0f);
		const float relicCarry = std::clamp(static_cast<float>(relic::g_enemyPercent) + relic::g_perLevel * l, 0.0f, 100.0f);
		return g_gunPercent + shieldCarry * static_cast<float>(shielditems::g_dropPercent) / 100.0f + relicCarry * static_cast<float>(relic::g_dropPercent) / 100.0f;
	}

	class CreatureDeathSink : public RE::BSTEventSink<RE::TESDeathEvent>
	{
	public:
		static CreatureDeathSink* Get()
		{
			static CreatureDeathSink sink;
			return std::addressof(sink);
		}

		RE::BSEventNotifyControl ProcessEvent(const RE::TESDeathEvent* a_event, RE::BSTEventSource<RE::TESDeathEvent>*) override
		{
			shield::g_stage = "badass: creature death";
			const auto player = RE::PlayerCharacter::GetSingleton();
			if (!g_on || !g_creatureDrops || !a_event || !a_event->actorDying || !player) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto actor = a_event->actorDying->As<RE::Actor>();
			if (!actor || actor->IsPlayerRef() || TierOf(actor->GetFormID()) > 0) {
				return RE::BSEventNotifyControl::kContinue;  // a Badass has its own drop
			}
			{
				// 1.28.0: the log showed one mudcrab's death rolled twice (the event came twice): one roll per body
				static std::mutex                         seenLock;
				static std::unordered_map<RE::FormID, Clock::time_point> seen;
				const std::lock_guard                     guard(seenLock);
				const auto                                now = Clock::now();
				if (const auto it = seen.find(actor->GetFormID()); it != seen.end() && now - it->second < std::chrono::seconds(60)) {
					return RE::BSEventNotifyControl::kContinue;
				}
				if (seen.size() > 512) {
					seen.clear();
				}
				seen[actor->GetFormID()] = now;
			}
			const int         c = ClassOf(actor);
			const std::string kind = c >= 0 ? g_classes[c].kind : (shielditems::IsPerson(actor) ? "person" : "creature");
			if (kind == "person" || kind == "critter" || actor->IsChild() || actor->IsPlayerTeammate() || actor->IsCommandedActor() || actor->IsSummoned()) {
				return RE::BSEventNotifyControl::kContinue;
			}
			if (!actor->IsHostileToActor(player)) {
				static std::atomic_int calm{ 0 };
				if (calm.fetch_add(1) < 10) {
					SKSE::log::info("badass: {:08X} (creature) died but was not hostile to the player: no drop", actor->GetFormID());
				}
				return RE::BSEventNotifyControl::kContinue;
			}
			const int   level = actor->GetLevel();
			const int   floor = c >= 0 ? g_classes[c].minRarity : 1;
			const char* raw = actor->GetName();
			Pending     p;
			p.id = actor->GetFormID();
			p.level = level;
			if (kind == "dragon" && g_dragonBoss) {
				p.n = 2;
				p.floor[0] = p.floor[1] = std::max(floor, 3);
				p.shift[0] = p.shift[1] = p.floor[0] - 1;
				p.level = std::max(level, 15);
				p.what = "dragon";
			} else if (shielditems::IsBoss(actor)) {
				p.n = 1;
				p.floor[0] = std::max(floor, 3);
				p.shift[0] = p.floor[0] - 1;
				p.level = std::max(level, 15);
				p.what = "boss creature";
			} else {
				const float scale = c >= 0 ? g_classes[c].dropScale : g_creatureScale;
				const float chance = std::min(g_creatureCap, PersonChance(level) * scale);
				const float roll = static_cast<float>(shielditems::Mix(p.id ^ 0xC4EA7ULL ^ (g_dropSerial.fetch_add(1) << 20)) % 10000ULL) / 100.0f;
				static std::atomic_int told{ 0 };
				if (told.fetch_add(1) < 40) {
					SKSE::log::info("badass: {:08X} \"{}\" (creature, class {}, level {}) died: drop chance {:.1f}% (a person's {:.1f}% x {:.2f}), rolled {:.1f}: {}", p.id, raw ? raw : "?",
						c >= 0 ? g_classes[c].id : std::string("none"), level, chance, PersonChance(level), scale, roll, roll < chance ? "drops an item" : "nothing");
				}
				if (roll >= chance) {
					return RE::BSEventNotifyControl::kContinue;
				}
				p.n = 1;
				p.floor[0] = floor;
				p.shift[0] = 0;
				p.what = "creature";
			}
			p.due = Clock::now() + std::chrono::milliseconds(1600);
			const std::lock_guard guard(g_pendLock);
			g_pending.push_back(std::move(p));
			return RE::BSEventNotifyControl::kContinue;
		}
	};

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
		std::vector<Seen>    shown;  // tiered and alive: name and size kept
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
			shown.push_back({ actor, id, base });
		}
		for (const auto& s : dead) {
			Entry e;
			{
				const std::lock_guard guard(g_lock);
				e = g_entries[s.id];
				g_entries[s.id].applied = false;
			}
			Strip(s.actor, e, "died");
			if (g_drops && e.tier > 0) {
				// each guaranteed item is shifted up to its own floor (BL2: an Ultimate drops a very rare, a rare and an uncommon)
				const int t = std::clamp(e.tier, 1, 3);
				Pending   p;
				p.id = s.id;
				p.n = t;
				p.level = std::max(level, kGateLevel[t]);
				p.what = kTierNames[t];
				for (int i = 0; i < t; ++i) {
					p.floor[i] = kFloors[t][i];
					p.shift[i] = kFloors[t][i] - 1;
				}
				if (const int c = ClassOf(s.actor); c >= 0 && g_classes[c].kind == "dragon") {  // a Badass dragon: never below rare
					for (int i = 0; i < t; ++i) {
						p.floor[i] = std::max(p.floor[i], 3);
						p.shift[i] = p.floor[i] - 1;
					}
				}
				p.due = Clock::now() + std::chrono::milliseconds(1600);  // after the shield and relic drops of the body (0.9 and 1.1 s)
				const std::lock_guard guard(g_pendLock);
				g_pending.push_back(std::move(p));
			}
		}
		std::vector<Pending> due;
		{
			const std::lock_guard guard(g_pendLock);
			for (auto it = g_pending.begin(); it != g_pending.end();) {
				if (Clock::now() >= it->due) {
					due.push_back(std::move(*it));
					it = g_pending.erase(it);
				} else {
					++it;
				}
			}
		}
		for (const auto& p : due) {
			Drop(p);
		}
		for (const auto& s : shown) {
			Present(s.actor, TierOf(s.id));
		}
		for (const auto& s : todo) {
			Entry e;
			{
				const std::lock_guard guard(g_lock);
				e = g_entries[s.id];
			}
			if (e.applied && e.check && e.tempHealth && StillOn(s.actor, e)) {  // a temporary bonus from 0.49.0/0.50.0 is still on: given again as a permanent one
				Strip(s.actor, e, "had a temporary health bonus");
				e.applied = false;
				e = Apply(s.actor, e, "health bonus made permanent");
			} else if (e.applied && e.check) {
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
				e.scaleBefore = s.actor->GetReferenceRuntimeData().refScale > 0 ? s.actor->GetReferenceRuntimeData().refScale : 100;
				{
					const std::lock_guard guard(g_lock);
					g_entries[s.id] = e;  // before Present, which reads the scale from the entry
				}
				Present(s.actor, tier);
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
		if (!a_intfc->OpenRecord(kRecord, 3)) {
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
			a_intfc->WriteRecordData(static_cast<std::uint8_t>(e.tempHealth ? 1 : 0));
			a_intfc->WriteRecordData(e.scaleBefore);
			tiered += e.tier > 0 ? 1 : 0;
		}
		SKSE::log::info("badass: save - {} actors rolled, {} of them with a tier", g_entries.size(), tiered);
	}

	inline bool Load(SKSE::SerializationInterface* a_intfc, std::uint32_t a_type, std::uint32_t a_version)
	{
		if (a_type != kRecord) {
			return false;
		}
		if (a_version < 1 || a_version > 3) {
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
			std::uint8_t temp = 1;  // version 1 = 0.49.0/0.50.0: the health bonus was temporary
			if (a_version >= 2) {
				a_intfc->ReadRecordData(temp);
			}
			e.tempHealth = temp != 0;
			e.scaleBefore = 100;  // versions 1-2 set the scale absolutely (from 100)
			if (a_version >= 3) {
				a_intfc->ReadRecordData(e.scaleBefore);
			}
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

	inline void Start(RE::ScriptEventSourceHolder* a_holder)
	{
		LoadClasses();
		if (a_holder) {
			a_holder->AddEventSink(CreatureDeathSink::Get());
		}
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
		if (a_key == "CreatureDrops" || a_key == "DragonBoss" || a_key == "CreatureDropScale" || a_key == "CreatureDropCap" || a_key == "CreatureGunPercent") {
			try {
				const float v = std::stof(a_value);
				if (a_key == "CreatureDrops") {
					g_creatureDrops = v != 0.0f;
				} else if (a_key == "DragonBoss") {
					g_dragonBoss = v != 0.0f;
				} else if (a_key == "CreatureDropScale") {
					g_creatureScale = std::clamp(v, 0.0f, 10.0f);
				} else if (a_key == "CreatureDropCap") {
					g_creatureCap = std::clamp(v, 0.0f, 100.0f);
				} else {
					g_gunPercent = std::clamp(v, 0.0f, 100.0f);
				}
			} catch (...) {
			}
			return true;
		}
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
		} else if (k == "Names") {
			g_names = v != 0.0f;
		} else if (k == "Size") {
			g_size = v != 0.0f;
		} else if (k == "CreatureSize") {
			g_creatureSize = std::clamp(v, 0.0f, 1.0f);
		} else if (k == "CreatureHealth") {
			g_creatureHealth = std::clamp(v, 0.0f, 10000.0f);
		} else if (k == "CreatureHealthPerLevel") {
			g_creatureHealthPerLevel = std::clamp(v, 0.0f, 1000.0f);
		} else if (k == "CreatureGap") {
			g_creatureGap = std::clamp(v, 0.0f, 1.0f);
		} else if (k == "CreatureGapMax") {
			g_creatureGapMax = std::clamp(v, 1.0f, 20.0f);
		} else if (k == "Drops") {
			g_drops = v != 0.0f;
		} else if (k == "DropGun") {
			g_dropWeight[0] = std::max(0.0f, v);
		} else if (k == "DropShield") {
			g_dropWeight[1] = std::max(0.0f, v);
		} else if (k == "DropRelic") {
			g_dropWeight[2] = std::max(0.0f, v);
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
		} else if (const int t4 = tierOf("Size")) {
			g_scale[t4] = std::clamp(v, 0.5f, 3.0f);
		}
		return true;
	}
}
