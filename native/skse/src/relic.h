// Relics (0.43.0): armor items the installer makes (setup/skylands_setup/relics.py), worn in a biped slot of their own (ini RelicSlot).
//
// A relic carries its numbers in a keyword, like the shields: SkylandsRelic_l<rarity 1-5>_<letter><per level, 1/100000>x<flat, 1/100000>_... one token per effect, where the value
// of an effect is (character level x per level + flat) as a fraction. The letters (what the effect changes while the relic is worn, Borderlands 2's numbers):
//   h  health: that share of the player's base Health (Skyrim's own Health, as a temporary bonus)
//   s  shield capacity %        (actor value Variable01, shield.h)      r  shield recharge rate %     (Variable02)
//   m  magazine size %          (Variable04, main.cpp)                  d  damage %                   (Variable09, main.cpp)
//   f  fire resistance          (ResistFire)   k shock (ResistShock)   c corrosive (PoisonResist)   x explosive (ResistMagic): points of resistance
// The effects are the player's alone; people carry relics (a roll by their own id, like the shields) and leave them for the player to find: dropped on the ground when they die.
#pragma once

#include "PCH.h"
#include "shield.h"
#include "shielditems.h"

#include <charconv>

namespace relic
{
	using Clock = std::chrono::steady_clock;

	inline bool g_on = true;             // Relics=0 switches the whole feature off
	inline int  g_slot = 0;              // RelicSlot: the biped slot (30-61) relics are worn in; 0 = no relics in this install
	inline int  g_enemyPercent = 8;      // EnemyRelicPercent: the chance (percent) that a person of level 1 carries a relic
	inline float g_perLevel = 1.0f;      // EnemyRelicPerLevel: this many percent more for every level above 1
	inline int  g_dropPercent = 100;     // RelicDropPercent: how often a dead person's relic is dropped on the ground (else it is taken off the body)

	struct Effect
	{
		char  code = 0;
		float perLevel = 0.0f;  // as a fraction
		float flat = 0.0f;
	};
	struct Info
	{
		int                 level = 0;
		std::vector<Effect> effects;
		bool                ok = false;
	};

	inline std::mutex                                 g_lock;
	inline std::unordered_map<RE::FormID, Info>       g_info;
	inline std::vector<RE::FormID>                    g_catalog[7];
	inline std::atomic_bool                           g_ready{ false };
	inline RE::FormID                                 g_playerWorn = 0;  // the relic the equip events last said the player put on (0: took off)
	inline std::unordered_set<RE::FormID>             g_decided;
	inline std::unordered_map<RE::ActorValue, float>  g_applied;         // what this plugin has added to each actor value so far (the game does not keep temporary values across a load)

	inline Info Parse(RE::TESObjectARMO* a_armor)
	{
		Info info;
		bool any = false;
		a_armor->ForEachKeyword([&](RE::BGSKeyword* a_keyword) {
			const std::string_view edid = a_keyword && a_keyword->formEditorID.c_str() ? a_keyword->formEditorID.c_str() : "";
			constexpr std::string_view prefix = "SkylandsRelic_";
			if (edid.starts_with(prefix)) {
				any = true;
				std::string_view rest = edid.substr(prefix.size());
				while (!rest.empty()) {
					const auto             cut = rest.find('_');
					const std::string_view part = rest.substr(0, cut);
					rest = cut == std::string_view::npos ? std::string_view{} : rest.substr(cut + 1);
					if (part.size() < 2) {
						continue;
					}
					if (part[0] == 'l') {
						std::from_chars(part.data() + 1, part.data() + part.size(), info.level);
						continue;
					}
					const auto x = part.find('x');
					if (x == std::string_view::npos || x < 2) {
						continue;
					}
					int per = 0, flat = 0;
					std::from_chars(part.data() + 1, part.data() + x, per);
					std::from_chars(part.data() + x + 1, part.data() + part.size(), flat);
					info.effects.push_back({ part[0], static_cast<float>(per) / 100000.0f, static_cast<float>(flat) / 100000.0f });
				}
			}
			return RE::BSContainer::ForEachResult::kContinue;
		});
		info.ok = any && !info.effects.empty() && info.level > 0;
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
		return info;
	}

	// Game thread, once the game's data has loaded.
	inline void Catalog()
	{
		const auto handler = RE::TESDataHandler::GetSingleton();
		if (!g_on || !handler || g_slot < 30 || g_slot > 61) {
			SKSE::log::info("relics: off (RelicSlot {})", g_slot);
			return;
		}
		int n = 0;
		for (const auto armor : handler->GetFormArray<RE::TESObjectARMO>()) {
			if (!armor) {
				continue;
			}
			const Info info = InfoOf(armor);  // takes g_lock itself: never call it while holding the lock (std::mutex is not recursive)
			if (info.ok) {
				const std::lock_guard guard(g_lock);
				g_catalog[std::clamp(info.level, 1, 6)].push_back(armor->GetFormID());
				++n;
			}
		}
		g_ready = n > 0;
		SKSE::log::info("relics: {} found (rarity 1-5: {} {} {} {} {}), worn in biped slot {}, a person carries one with {} percent + {} percent a level, {} percent of a dead person's are dropped", n, g_catalog[1].size(), g_catalog[2].size(),
			g_catalog[3].size(), g_catalog[4].size(), g_catalog[5].size(), g_slot, g_enemyPercent, g_perLevel, g_dropPercent);
	}

	inline RE::BGSBipedObjectForm::BipedObjectSlot Mask()
	{
		return static_cast<RE::BGSBipedObjectForm::BipedObjectSlot>(1u << (g_slot - 30));
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
			if (!g_ready || !a_event || !a_event->actor || !a_event->actor->IsPlayerRef()) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto armor = RE::TESForm::LookupByID<RE::TESObjectARMO>(a_event->baseObject);
			if (armor && InfoOf(armor).ok) {
				g_playerWorn = a_event->equipped ? armor->GetFormID() : 0;
			}
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	// the relic the player wears: by the body's slot data, else by the equip events
	inline RE::TESObjectARMO* WornByPlayer(RE::PlayerCharacter* a_player)
	{
		if (const auto armor = a_player->GetWornArmor(Mask(), true); armor && InfoOf(armor).ok) {
			return armor;
		}
		if (g_playerWorn) {
			if (const auto armor = RE::TESForm::LookupByID<RE::TESObjectARMO>(g_playerWorn); armor && shielditems::InPack(a_player, armor)) {
				return armor;
			}
		}
		return nullptr;
	}

	// Raises or lowers one actor value so that this plugin's share of it is `a_want`.
	inline void Move(RE::PlayerCharacter* a_player, RE::ActorValue a_value, float a_want)
	{
		float&      applied = g_applied[a_value];
		const float delta = a_want - applied;
		if (std::abs(delta) < 0.05f) {
			return;
		}
		shield::g_self = true;
		a_player->AsActorValueOwner()->ModActorValue(RE::ACTOR_VALUE_MODIFIER::kTemporary, a_value, delta);
		shield::g_self = false;
		applied = a_want;
	}

	inline void Revert()
	{
		g_applied.clear();  // a load or a new game: the game dropped the temporary values
		g_playerWorn = 0;
		g_decided.clear();
	}

	// Every 400 ms on the game thread: what the player's worn relic does.
	inline void ApplyToPlayer(RE::PlayerCharacter* a_player)
	{
		static RE::FormID lastShown = 0;
		static int        lastLevel = -1;
		const auto        worn = WornByPlayer(a_player);
		const Info        info = worn ? InfoOf(worn) : Info{};
		const int         level = static_cast<int>(a_player->GetLevel());
		std::unordered_map<RE::ActorValue, float> want;
		want[RE::ActorValue::kHealth] = 0.0f;
		want[RE::ActorValue::kVariable01] = want[RE::ActorValue::kVariable02] = want[RE::ActorValue::kVariable04] = want[RE::ActorValue::kVariable09] = 0.0f;
		want[RE::ActorValue::kResistFire] = want[RE::ActorValue::kResistShock] = want[RE::ActorValue::kPoisonResist] = want[RE::ActorValue::kResistMagic] = 0.0f;
		const float baseHealth = a_player->AsActorValueOwner()->GetBaseActorValue(RE::ActorValue::kHealth);
		for (const auto& e : info.effects) {
			const float fraction = static_cast<float>(level) * e.perLevel + e.flat;
			switch (e.code) {
			case 'h': want[RE::ActorValue::kHealth] += fraction * baseHealth; break;
			case 's': want[RE::ActorValue::kVariable01] += fraction * 100.0f; break;
			case 'r': want[RE::ActorValue::kVariable02] += fraction * 100.0f; break;
			case 'm': want[RE::ActorValue::kVariable04] += fraction * 100.0f; break;
			case 'd': want[RE::ActorValue::kVariable09] += fraction * 100.0f; break;
			case 'f': want[RE::ActorValue::kResistFire] += fraction * 100.0f; break;
			case 'k': want[RE::ActorValue::kResistShock] += fraction * 100.0f; break;
			case 'c': want[RE::ActorValue::kPoisonResist] += fraction * 100.0f; break;
			case 'x': want[RE::ActorValue::kResistMagic] += fraction * 100.0f; break;
			default: break;
			}
		}
		for (const auto& [value, amount] : want) {
			Move(a_player, value, amount);
		}
		const RE::FormID shownId = worn ? worn->GetFormID() : 0;
		if (shownId != lastShown || (shownId && level != lastLevel)) {
			lastShown = shownId;
			lastLevel = level;
			static int told = 0;
			if (told++ < 40) {
				std::string text;
				for (const auto& e : info.effects) {
					text += fmt::format(" {}{:+.1f}%", e.code, (static_cast<float>(level) * e.perLevel + e.flat) * 100.0f);
				}
				if (worn) {
					SKSE::log::info("relics: the player wears \"{}\" (character level {}):{}", worn->GetName(), level, text);
				} else {
					SKSE::log::info("relics: the player wears no relic; every bonus is taken off");
				}
			}
		}
	}

	inline RE::TESObjectARMO* PickFor(std::uint64_t a_seed, int a_level, int a_minRarity = 1)
	{
		int                     total = 0;
		std::vector<RE::FormID> lists[7];
		for (int r = 1; r <= 5; ++r) {
			if (r >= a_minRarity && a_level >= shielditems::kLevelFor[r] && !g_catalog[r].empty()) {
				lists[r] = g_catalog[r];
				total += shielditems::kWeight[r];
			}
		}
		if (total <= 0) {
			return nullptr;
		}
		int roll = static_cast<int>(shielditems::Mix(a_seed ^ 0x9A11) % static_cast<std::uint64_t>(total));
		for (int r = 1; r <= 5; ++r) {
			if (lists[r].empty()) {
				continue;
			}
			if (roll < shielditems::kWeight[r]) {
				return RE::TESForm::LookupByID<RE::TESObjectARMO>(lists[r][shielditems::Mix(a_seed ^ 0x77B3) % lists[r].size()]);
			}
			roll -= shielditems::kWeight[r];
		}
		return nullptr;
	}

	// Game thread, every 400 ms (shield.h calls it): the player's relic, and the people near the player who may carry one.
	inline void Pump(RE::PlayerCharacter* a_player, RE::ProcessLists* a_lists)
	{
		if (!g_ready) {
			return;
		}
		shield::g_stage = "relics";
		ApplyToPlayer(a_player);
		if (!a_lists) {
			return;
		}
		const auto here = a_player->GetPosition();
		int        gave = 0, looked = 0;
		for (auto& handle : a_lists->highActorHandles) {
			const auto ptr = handle.get();
			const auto actor = ptr.get();
			if (!actor || actor->IsPlayerRef() || actor->IsDead() || !actor->Is3DLoaded() || looked >= 40 || gave >= 2) {
				continue;
			}
			const auto  there = actor->GetPosition();
			const float dx = there.x - here.x, dy = there.y - here.y, dz = there.z - here.z;
			if (dx * dx + dy * dy + dz * dz > 6000.0f * 6000.0f || !shielditems::IsPerson(actor)) {
				continue;
			}
			++looked;
			const RE::FormID id = actor->GetFormID();
			{
				const std::lock_guard guard(g_lock);
				if (!g_decided.insert(id).second) {
					continue;
				}
			}
			const bool boss = shielditems::IsBoss(actor) && actor->IsHostileToActor(a_player);
			const int  level = actor->GetLevel();
			const int  chance = boss ? 100 : static_cast<int>(std::clamp(g_enemyPercent + g_perLevel * (std::max)(0, level - 1), 0.0f, 100.0f));
			if (shielditems::Mix(id ^ 0xBEEF) % 100 >= static_cast<std::uint64_t>(chance)) {
				continue;
			}
			if (const auto armor = PickFor(shielditems::Mix(id ^ 0x5151), boss ? (std::max)(level, 15) : level, boss ? 3 : 1)) {
				shielditems::PutOn(actor, armor);
				++gave;
				static std::atomic_int told{ 0 };
				if (told.fetch_add(1) < 25) {
					SKSE::log::info("relics: {:08X} (level {}{}) carries \"{}\" (chance {} percent)", id, level, boss ? ", a boss" : "", armor->GetName(), chance);
				}
			}
		}
	}

	// A death: 900 ms later the relic in the body's pack is dropped on the ground (RelicDropPercent), else taken out of the pack.
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
			const bool                       drop = shielditems::IsBoss(dying) || static_cast<int>(rng() % 100) < g_dropPercent;
			const RE::FormID                 body = dying->GetFormID();
			std::thread([body, drop]() {
				std::this_thread::sleep_for(std::chrono::milliseconds(1100));
				shield::Queue([body, drop]() {
					shield::g_stage = "relic drop";
					const auto actor = RE::TESForm::LookupByID<RE::Actor>(body);
					if (!actor || !actor->IsDead()) {
						return;
					}
					RE::TESObjectARMO* armor = nullptr;
					for (const auto& [object, entry] : actor->GetInventory([](RE::TESBoundObject& a_object) {
							 const auto item = a_object.As<RE::TESObjectARMO>();
							 return item && InfoOf(item).ok;
						 })) {
						armor = object ? object->As<RE::TESObjectARMO>() : nullptr;
						if (armor) {
							break;
						}
					}
					if (!armor) {
						return;
					}
					actor->RemoveItem(armor, 1, drop ? RE::ITEM_REMOVE_REASON::kDropping : RE::ITEM_REMOVE_REASON::kRemove, nullptr, nullptr);
					SKSE::log::info("relics: {:08X} died; its relic \"{}\" was {}", body, armor->GetName(), drop ? "dropped on the ground" : "not left");
				});
			}).detach();
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	inline bool Config(const std::string& a_key, const std::string& a_value)
	{
		const auto number = [&](int a_lo, int a_hi, int& a_out) {
			try {
				a_out = std::clamp(std::stoi(a_value), a_lo, a_hi);
			} catch (...) {
			}
		};
		if (a_key == "Relics") {
			g_on = a_value.find('0') == std::string::npos;
		} else if (a_key == "RelicSlot") {
			number(0, 61, g_slot);
		} else if (a_key == "EnemyRelicPercent") {
			number(0, 100, g_enemyPercent);
		} else if (a_key == "EnemyRelicPerLevel") {
			try {
				g_perLevel = std::clamp(std::stof(a_value), 0.0f, 20.0f);
			} catch (...) {
			}
		} else if (a_key == "RelicDropPercent") {
			number(0, 100, g_dropPercent);
		} else {
			return false;
		}
		return true;
	}
}
