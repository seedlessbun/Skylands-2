// Shield items (0.39.0): the armor records the installer makes (setup/skylands_setup/shields.py) become shields.
//
// An item carries its numbers in keywords, like the guns: SkylandsShield (a shield item) and SkylandsShield_t<type>_e<element>_k<capacity per mille of the wearer's max
// health>_r<recharge rate per mille of the capacity per second>_d<delay in tenths of a second>_g<rarity 1-6>. Whoever wears one in the shield slot (ini ShieldSlot, a biped
// slot the installer found nothing else using) has a shield with those numbers (shield.h does the shield; this file says who has which):
//   - the player and every person near the player: what is worn in the slot is the shield; taking it off takes the shield away, putting another on replaces it
//   - people near the player who wear none are, once and by a roll that depends only on their own id (so a loaded game gives the same people shields), given an item
//     of a rarity their level allows, and put it on
//   - the player is handed one starter shield in a new game
//   - a dead person's shield stays on the body (ShieldDropPercent says how often; the loot chances are still to be agreed with the user)
// Which shield items exist is found when the game has loaded: every armor with a SkylandsShield_ keyword.
#pragma once

#include "PCH.h"
#include "shield.h"

#include <charconv>
#include <mutex>
#include <random>
#include <thread>
#include <unordered_set>
#include <vector>

namespace shielditems
{
	using Clock = std::chrono::steady_clock;

	inline int  g_slot = 0;           // ShieldSlot: the biped slot (30-61) shield items are worn in; 0 = no shield items in this install
	inline int   g_enemyPercent = 10;   // EnemyShieldPercent: the chance (percent) that a person of level 1 carries a shield
	inline float g_perLevel = 2.0f;     // EnemyShieldPerLevel: this many percent more for every level above 1 (the user chose "tougher = more likely"); 100 is the most
	inline float g_capScale = 1.0f;     // ShieldCapacityScale: every item's capacity is multiplied by this (for testing: 2 doubles every shield)
	inline int   g_bossLevel = 35;      // ShieldBossLevel: a person this level or higher, or a named one (the base record is "unique"), counts as a boss: always a shield, rare or better, always left on the body
	inline int   g_dropPercent = 25;    // ShieldDropPercent: how often a dead person's shield stays on the body (the user chose 25; bosses always leave theirs)
	inline bool g_starter = true;     // StarterShield=0: the player is not given one

	struct Info
	{
		int  type = 0, element = 0, k = 0, r = 0, d = 0, level = 0;
		bool ok = false;
	};

	inline std::mutex                                g_lock;
	inline std::unordered_map<RE::FormID, Info>      g_info;
	inline std::vector<RE::FormID>                   g_catalog[7];  // the shield items by rarity level (1 common ... 6 e-tech)
	inline std::unordered_map<RE::FormID, RE::FormID> g_equipped;    // actor -> the shield item the equip events last said it put on (0: took off)
	inline std::atomic_bool                          g_ready{ false };
	inline std::unordered_set<RE::FormID>            g_decided;  // people already rolled this session

	inline Info Parse(RE::TESObjectARMO* a_armor)
	{
		Info info;
		bool any = false;
		a_armor->ForEachKeyword([&](RE::BGSKeyword* a_keyword) {
			// the member, not the virtual GetFormEditorID (a vtable slot that moved between runtimes would read garbage)
			const std::string_view edid = a_keyword && a_keyword->formEditorID.c_str() ? a_keyword->formEditorID.c_str() : "";
			constexpr std::string_view prefix = "SkylandsShield_";
			if (edid.starts_with(prefix)) {
				std::string_view rest = edid.substr(prefix.size());
				while (!rest.empty()) {
					const auto             cut = rest.find('_');
					const std::string_view part = rest.substr(0, cut);
					rest = cut == std::string_view::npos ? std::string_view{} : rest.substr(cut + 1);
					if (part.size() < 2) {
						continue;
					}
					int value = 0;
					std::from_chars(part.data() + 1, part.data() + part.size(), value);
					switch (part[0]) {
					case 't': info.type = value; any = true; break;
					case 'e': info.element = value; break;
					case 'k': info.k = value; break;
					case 'r': info.r = value; break;
					case 'd': info.d = value; break;
					case 'g': info.level = value; break;
					default: break;
					}
				}
			}
			return RE::BSContainer::ForEachResult::kContinue;
		});
		info.ok = any && info.k > 0;
		return info;
	}

	inline Info InfoOf(RE::TESObjectARMO* a_armor)
	{
		if (!a_armor) {
			return {};
		}
		const std::lock_guard guard(g_lock);
		if (const auto it = g_info.find(a_armor->GetFormID()); it != g_info.end()) {
			return it->second;
		}
		const Info info = Parse(a_armor);
		g_info[a_armor->GetFormID()] = info;
		static int told = 0;
		if (info.ok && told < 6) {
			++told;
			SKSE::log::info("shield item {:08X} \"{}\": type {}, element {}, capacity {:.1f}% of max health, recharge {:.1f}% of capacity a second, delay {:.1f} s, rarity {}", a_armor->GetFormID(),
				a_armor->GetName(), info.type, info.element, info.k / 10.0f, info.r / 10.0f, info.d / 10.0f, info.level);
		}
		return info;
	}

	// Game thread, once the game's data has loaded: which shield items there are.
	inline void Catalog()
	{
		const auto handler = RE::TESDataHandler::GetSingleton();
		if (!handler || g_slot < 30 || g_slot > 61) {
			SKSE::log::info("shield items: off (ShieldSlot {})", g_slot);
			return;
		}
		int n = 0;
		for (const auto armor : handler->GetFormArray<RE::TESObjectARMO>()) {
			if (!armor) {
				continue;
			}
			const Info info = InfoOf(armor);
			if (info.ok) {
				const std::lock_guard guard(g_lock);
				g_catalog[std::clamp(info.level, 1, 6)].push_back(armor->GetFormID());
				++n;
			}
		}
		g_ready = n > 0;
		SKSE::log::info("shield items: {} found (rarity 1-6: {} {} {} {} {} {}), worn in biped slot {}, a person carries one with {} percent + {} percent a level (bosses from level {} or named: always), {} percent of a dead person's stay on the body (a boss's always)", n,
			g_catalog[1].size(), g_catalog[2].size(), g_catalog[3].size(), g_catalog[4].size(), g_catalog[5].size(), g_catalog[6].size(), g_slot, g_enemyPercent, g_perLevel, g_bossLevel, g_dropPercent);
	}

	inline RE::BGSBipedObjectForm::BipedObjectSlot Mask()
	{
		return static_cast<RE::BGSBipedObjectForm::BipedObjectSlot>(1u << (g_slot - 30));
	}

	inline bool InPack(RE::Actor* a_actor, RE::TESObjectARMO* a_armor)
	{
		const auto counts = a_actor->GetInventoryCounts([&](RE::TESBoundObject& a_object) { return &a_object == a_armor; });
		return !counts.empty();
	}

	// the shield item an actor wears: by what its body says is in the slot, else by the equip events (an armor with no model may not show in the body's data)
	inline RE::TESObjectARMO* Worn(RE::Actor* a_actor)
	{
		if (g_slot < 30 || g_slot > 61 || !a_actor->Is3DLoaded()) {
			return nullptr;
		}
		static std::atomic_int told{ 0 };
		if (const auto armor = a_actor->GetWornArmor(Mask(), true); armor && InfoOf(armor).ok) {
			if (told.fetch_add(1) < 3) {
				SKSE::log::info("shield items: {:08X} wears {:08X} \"{}\" (found in the body's slot data)", a_actor->GetFormID(), armor->GetFormID(), armor->GetName());
			}
			return armor;
		}
		RE::FormID by = 0;
		{
			const std::lock_guard guard(g_lock);
			if (const auto it = g_equipped.find(a_actor->GetFormID()); it != g_equipped.end()) {
				by = it->second;
			}
		}
		if (by) {
			if (const auto armor = RE::TESForm::LookupByID<RE::TESObjectARMO>(by); armor && InPack(a_actor, armor)) {
				if (told.fetch_add(1) < 3) {
					SKSE::log::info("shield items: {:08X} wears {:08X} \"{}\" (found by the equip event)", a_actor->GetFormID(), armor->GetFormID(), armor->GetName());
				}
				return armor;
			}
		}
		return nullptr;
	}

	class EquipSink : public RE::BSTEventSink<RE::TESEquipEvent>
	{
	public:
		static EquipSink* Get()
		{
			static EquipSink sink;
			return std::addressof(sink);
		}

		RE::BSEventNotifyControl ProcessEvent(const RE::TESEquipEvent* a_event, RE::BSTEventSource<RE::TESEquipEvent>*) override
		{
			if (!g_ready || !a_event || !a_event->actor) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto actor = a_event->actor->As<RE::Actor>();
			const auto armor = RE::TESForm::LookupByID<RE::TESObjectARMO>(a_event->baseObject);
			if (actor && armor && InfoOf(armor).ok) {
				const std::lock_guard guard(g_lock);
				g_equipped[actor->GetFormID()] = a_event->equipped ? armor->GetFormID() : 0;
			}
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	inline std::uint64_t Mix(std::uint64_t a_value)
	{
		a_value += 0x9E3779B97F4A7C15ull;
		a_value = (a_value ^ (a_value >> 30)) * 0xBF58476D1CE4E5B9ull;
		a_value = (a_value ^ (a_value >> 27)) * 0x94D049BB133111EBull;
		return a_value ^ (a_value >> 31);
	}

	// the rarities a person of this level can carry (design: the loot chances are still to be agreed) and how common each is (the same weights as the guns' rarities)
	constexpr int kLevelFor[7] = { 0, 1, 3, 8, 15, 30, 40 };
	constexpr int kWeight[7] = { 0, 122, 50, 20, 6, 1, 1 };

	// An item for a person of this level: a rarity by the weights above, then one of that rarity's items by the seed. a_type >= 0 keeps to one type (the starter is a plain shield).
	inline RE::TESObjectARMO* PickFor(std::uint64_t a_seed, int a_level, int a_type = -1, int a_minRarity = 1)
	{
		const auto pool = [&](int a_rarity) {
			std::vector<RE::FormID> out;
			for (const auto id : g_catalog[a_rarity]) {
				if (a_type < 0) {
					out.push_back(id);
				} else if (const auto armor = RE::TESForm::LookupByID<RE::TESObjectARMO>(id); armor && InfoOf(armor).type == a_type) {
					out.push_back(id);
				}
			}
			return out;
		};
		int total = 0;
		std::vector<RE::FormID> lists[7];
		for (int r = 1; r <= 6; ++r) {
			if (r >= a_minRarity && a_level >= kLevelFor[r]) {
				lists[r] = pool(r);
				if (!lists[r].empty()) {
					total += kWeight[r];
				}
			}
		}
		if (total <= 0) {
			return nullptr;
		}
		int roll = static_cast<int>(Mix(a_seed ^ 0x1234) % static_cast<std::uint64_t>(total));
		for (int r = 1; r <= 6; ++r) {
			if (lists[r].empty()) {
				continue;
			}
			if (roll < kWeight[r]) {
				return RE::TESForm::LookupByID<RE::TESObjectARMO>(lists[r][Mix(a_seed ^ 0x5678) % lists[r].size()]);
			}
			roll -= kWeight[r];
		}
		return nullptr;
	}

	inline void PutOn(RE::Actor* a_actor, RE::TESObjectARMO* a_armor)
	{
		if (!InPack(a_actor, a_armor)) {
			a_actor->AddObjectToContainer(a_armor, nullptr, 1, nullptr);
		}
		if (const auto manager = RE::ActorEquipManager::GetSingleton()) {
			manager->EquipObject(a_actor, a_armor, nullptr, 1, nullptr, false, true, false, false);
		}
	}

	// The shield state of one actor follows what it wears. (The caller has seen to a bonus a loaded save still holds: it comes off before anything new is given.)
	inline void Follow(RE::Actor* a_actor, RE::TESObjectARMO* a_worn, bool a_player)
	{
		const RE::FormID id = a_actor->GetFormID();
		const RE::FormID have = shield::ItemOf(id);  // 0: no shield, or a test shield from the settings file
		if (a_worn) {
			if (have == a_worn->GetFormID()) {
				return;
			}
			if (shield::Has(id)) {
				shield::Remove(a_actor);  // another item's shield, or a test shield: replaced
			}
			const Info info = InfoOf(a_worn);
			shield::Give(a_actor, info.k / 1000.0f * g_capScale, a_player, info.r / 1000.0f, info.d / 10.0f, a_worn->GetFormID());
			SKSE::log::info("shield items: {:08X}{} now has \"{}\": capacity {:.1f}% of max health, recharge {:.1f}%/s, delay {:.1f} s", id, a_player ? " (the player)" : "", a_worn->GetName(), info.k / 10.0f * g_capScale,
				info.r / 10.0f, info.d / 10.0f);
		} else if (have) {
			shield::Remove(a_actor);
			SKSE::log::info("shield items: {:08X}{} took its shield off", id, a_player ? " (the player)" : "");
		}
	}

	// a boss: a named person (the base record is flagged unique) or one of a high level
	inline bool IsBoss(RE::Actor* a_actor)
	{
		const auto base = a_actor->GetActorBase();
		return (base && base->IsUnique()) || a_actor->GetLevel() >= g_bossLevel;
	}

	inline bool IsPerson(RE::Actor* a_actor)
	{
		const auto race = a_actor->GetRace();
		return race && race->HasKeywordString("ActorTypeNPC") && !a_actor->IsChild();
	}

	// Game thread, every 400 ms (shield.h calls it in place of the test shields). Returns false when there are no shield items in this install.
	inline bool Pump(RE::PlayerCharacter* a_player, RE::ProcessLists* a_lists)
	{
		if (!g_ready) {
			return false;
		}
		shield::g_stage = "shield items";
		{
			const std::lock_guard guard(shield::g_lock);
			if (shield::g_stale.contains(a_player->GetFormID())) {
				return true;  // the bonus the save held comes off first
			}
		}
		Follow(a_player, Worn(a_player), true);
		if (g_starter && !shield::g_starterGiven && a_player->Is3DLoaded()) {
			shield::g_starterGiven = true;
			const auto armor = PickFor(Mix(a_player->GetFormID() + 7), 1, 0);
			if (armor) {
				PutOn(a_player, armor);
				SKSE::log::info("shield items: the player is given a starter shield, \"{}\"", armor->GetName());
				shield::Tell(std::string("You found a shield: ") + armor->GetName());
			}
		}
		if (!a_lists) {
			return true;
		}
		const auto here = a_player->GetPosition();
		int        gave = 0, looked = 0;
		for (auto& handle : a_lists->highActorHandles) {
			const auto ptr = handle.get();
			const auto actor = ptr.get();
			if (!actor || actor->IsPlayerRef() || actor->IsDead() || !actor->Is3DLoaded() || looked >= 24) {
				continue;
			}
			const auto  there = actor->GetPosition();
			const float dx = there.x - here.x, dy = there.y - here.y, dz = there.z - here.z;
			if (dx * dx + dy * dy + dz * dz > 6000.0f * 6000.0f) {
				continue;
			}
			++looked;
			const RE::FormID id = actor->GetFormID();
			{
				const std::lock_guard guard(shield::g_lock);
				if (shield::g_stale.contains(id)) {
					continue;
				}
			}
			if (const auto worn = Worn(actor)) {
				Follow(actor, worn, false);
				continue;
			}
			if (shield::Has(id)) {
				Follow(actor, nullptr, false);
			}
			if (gave >= 2 || !IsPerson(actor)) {
				continue;
			}
			{
				const std::lock_guard guard(g_lock);
				if (!g_decided.insert(id).second) {
					continue;
				}
			}
			// the chance grows with the level (the user's choice); a boss always has one, rare or better, whatever its level
			const bool boss = IsBoss(actor) && actor->IsHostileToActor(a_player);
			const int  level = actor->GetLevel();
			const int  chance = boss ? 100 : static_cast<int>(std::clamp(g_enemyPercent + g_perLevel * (std::max)(0, level - 1), 0.0f, 100.0f));
			if (Mix(id) % 100 >= static_cast<std::uint64_t>(chance)) {
				continue;
			}
			if (const auto armor = boss ? PickFor(Mix(id), (std::max)(level, 15), -1, 3) : PickFor(Mix(id), level)) {
				PutOn(actor, armor);
				++gave;
				static std::atomic_int told{ 0 };
				if (told.fetch_add(1) < 25) {
					SKSE::log::info("shield items: {:08X} (level {}{}) is given \"{}\" (chance {} percent)", id, level, boss ? ", a boss" : "", armor->GetName(), chance);
				}
			}
		}
		return true;
	}

	// A death: with the chance the settings file gives, the shield stays on the body; otherwise it is taken off the body a moment after (not inside the event: changing a body's
	// pack while the game is still killing it is a known way to crash).
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
			if (!g_ready || !a_event || !a_event->actorDying || !a_event->dead) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto dying = a_event->actorDying->As<RE::Actor>();
			if (!dying || dying->IsPlayerRef()) {
				return RE::BSEventNotifyControl::kContinue;
			}
			static thread_local std::mt19937 rng{ std::random_device{}() };
			if (IsBoss(dying) || static_cast<int>(rng() % 100) < g_dropPercent) {  // a boss always leaves its shield; the others by the settings file's chance
				return RE::BSEventNotifyControl::kContinue;
			}
			const RE::FormID body = dying->GetFormID();
			std::thread([body]() {
				std::this_thread::sleep_for(std::chrono::milliseconds(900));
				shield::Queue([body]() {
					shield::g_stage = "shield drop";
					const auto actor = RE::TESForm::LookupByID<RE::Actor>(body);
					if (!actor || !actor->IsDead()) {
						return;
					}
					RE::FormID by = 0;
					{
						const std::lock_guard guard(g_lock);
						if (const auto it = g_equipped.find(body); it != g_equipped.end()) {
							by = it->second;
						}
					}
					const auto armor = by ? RE::TESForm::LookupByID<RE::TESObjectARMO>(by) : nullptr;
					if (armor && InPack(actor, armor)) {
						actor->RemoveItem(armor, 1, RE::ITEM_REMOVE_REASON::kRemove, nullptr, nullptr);
						SKSE::log::info("shield items: {:08X} died; its shield \"{}\" was not left on the body", body, armor->GetName());
					}
				});
			}).detach();
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	// the settings file: returns true when the key was one of the items'
	inline bool Config(const std::string& a_key, const std::string& a_value)
	{
		const auto number = [&](int a_lo, int a_hi, int& a_out) {
			try {
				a_out = std::clamp(std::stoi(a_value), a_lo, a_hi);
			} catch (...) {
			}
		};
		if (a_key == "ShieldSlot") {
			number(0, 61, g_slot);
		} else if (a_key == "EnemyShieldPercent") {
			number(0, 100, g_enemyPercent);
		} else if (a_key == "EnemyShieldPerLevel") {
			try {
				g_perLevel = std::clamp(std::stof(a_value), 0.0f, 20.0f);
			} catch (...) {
			}
		} else if (a_key == "ShieldCapacityScale") {
			try {
				g_capScale = std::clamp(std::stof(a_value), 0.1f, 20.0f);
			} catch (...) {
			}
		} else if (a_key == "ShieldBossLevel") {
			number(1, 1000, g_bossLevel);
		} else if (a_key == "ShieldDropPercent") {
			number(0, 100, g_dropPercent);
		} else if (a_key == "StarterShield") {
			g_starter = a_value.find('0') == std::string::npos;
		} else {
			return false;
		}
		return true;
	}
}
