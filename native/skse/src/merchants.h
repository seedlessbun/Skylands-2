#pragma once

// Merchants and ammo amounts (0.59.0, the user's request).
//
// The installer's old way (overriding vendor chests found by editor-id name) never matched a Skyrim chest, so merchants are now stocked here, at run time:
// when the player starts talking to someone (the Dialogue Menu opens) whose vendor faction has a merchant chest, the chest is topped up to `ShopAmmo<Type>`
// rounds of each Skylands ammo and to `ShopGear` Skylands guns / shields / relics (picked like a Badass drop with no tier: the guns' rarity weights and the
// level gates at the player's level; a new pick every `ShopGearDays` game days). It is a top-up, so talking again or reloading never piles items up, and when
// the game restocks the chest (every 48 game hours) the next talk fills it again. Every vendor gets it.
//
// The amounts a body carries and the first stock a player gets are per ammo type here too, sized by the ammo's gold value (pistol 5, SMG 8, rifle 10,
// shotgun 10, sniper 15, rocket 50): a body's ammo is worth about 75-135 gold whatever the type.

#include "PCH.h"
#include "badass.h"
#include "despawn.h"
#include "shield.h"
#include "shielditems.h"

namespace shop
{
	constexpr int kTypes = 6;  // generate.STAFF_KINDS order = the gun keyword's ammo list: smg, assault_rifle, pistol, shotgun, sniper, launcher
	inline constexpr const char* kKeys[kTypes] = { "SMG", "AR", "Pistol", "Shotgun", "Sniper", "Launcher" };

	inline bool g_on = true;                                          // ini Shop=0: no merchant stocking
	inline bool g_reset = true;                                       // ShopReset: do the game's due restock ourselves before stocking (0.59.1)
	inline int  g_stock[kTypes] = { 80, 60, 100, 40, 30, 6 };         // ShopAmmo<Type>: rounds a merchant keeps of each kind
	inline int  g_gear = 3;                                           // ShopGear: Skylands guns / shields / relics a merchant keeps
	inline int  g_gearDays = 2;                                       // ShopGearDays: game days before the picks change
	inline int  g_dropMin[kTypes] = { 10, 8, 12, 5, 3, 1 };           // AmmoDrop<Type>=min-max: rounds of the held gun's ammo on a body
	inline int  g_dropMax[kTypes] = { 24, 18, 28, 12, 8, 2 };
	inline int  g_bonusMin[kTypes] = { 5, 4, 6, 3, 2, 1 };            // AmmoBonus<Type>=min-max: the extra random kind some bodies carry
	inline int  g_bonusMax[kTypes] = { 12, 10, 14, 6, 4, 1 };
	inline int  g_start[kTypes] = { 100, 80, 120, 40, 30, 6 };        // StartAmmo<Type>: the first stock of a kind a player with none gets (StartAmmo=0 turns it off)

	inline std::function<RE::TESBoundObject*(int)> g_ammo;  // main.cpp: the ammo item of a type
	inline std::atomic_int g_told{ 0 };

	inline int Pick(int a_type, bool a_bonus, std::mt19937& a_rng)
	{
		if (a_type < 0 || a_type >= kTypes) {
			a_type = 0;
		}
		const int lo = a_bonus ? g_bonusMin[a_type] : g_dropMin[a_type];
		const int hi = (std::max)(lo, a_bonus ? g_bonusMax[a_type] : g_dropMax[a_type]);
		return std::uniform_int_distribution<int>(lo, hi)(a_rng);
	}

	inline int StartOf(int a_type) { return a_type >= 0 && a_type < kTypes ? g_start[a_type] : g_start[0]; }

	// 0.59.3, from the 0.59.2 log + the user (the chest held the ammo, the barter list did not show it): a merchant only shows the chest's items that carry a keyword of
	// its vendor list (VEND; with notBuySell the list is the ones it will NOT deal in). Skylands items lack those keywords, so the vendor's first listed keyword is given
	// to the item's base form at run time (not saved: done again at every stocking). ini ShopKeywords=0 turns it off.
	inline bool g_fitKeywords = true;
	inline std::atomic_int g_fitTold{ 0 };

	inline const char* Fit(RE::TESBoundObject* a_item, RE::TESFaction* a_faction)
	{
		const auto kwForm = a_item ? a_item->As<RE::BGSKeywordForm>() : nullptr;
		const auto list = a_faction ? a_faction->vendorData.vendorSellBuyList : nullptr;
		if (!kwForm || !list) {
			return "no vendor list";
		}
		bool                matches = false;
		RE::BGSKeyword*     first = nullptr;
		list->ForEachForm([&](RE::TESForm* a_form) {
			if (const auto kw = a_form ? a_form->As<RE::BGSKeyword>() : nullptr) {
				if (!first) {
					first = kw;
				}
				if (kwForm->HasKeyword(kw)) {
					matches = true;
					return RE::BSContainer::ForEachResult::kStop;
				}
			}
			return RE::BSContainer::ForEachResult::kContinue;
		});
		if (a_faction->vendorData.vendorValues.notBuySell) {
			return matches ? "excluded by the vendor's list" : "allowed (the list excludes others)";
		}
		if (matches) {
			return "already matches";
		}
		if (!first || !g_fitKeywords) {
			return "does not match, nothing to give";
		}
		kwForm->AddKeyword(first);
		if (g_fitTold.fetch_add(1) < 30) {
			SKSE::log::info("shop: gave {:08X} \"{}\" the vendor keyword {:08X} \"{}\" so the barter menu shows it", a_item->GetFormID(), a_item->GetName(), first->GetFormID(),
				first->formEditorID.c_str() ? first->formEditorID.c_str() : "");
		}
		return "given the vendor's keyword";
	}

	inline int RespawnDays()
	{
		const auto settings = RE::GameSettingCollection::GetSingleton();
		const auto s = settings ? settings->GetSetting("iDaysToRespawnVendor") : nullptr;
		return s ? (std::max)(1, s->GetInteger()) : 2;
	}

	inline int Count(RE::TESObjectREFR* a_chest, RE::TESBoundObject* a_item)
	{
		const auto counts = a_chest->GetInventoryCounts();
		const auto it = counts.find(a_item);
		return it == counts.end() ? 0 : it->second;
	}

	// game thread: top a merchant's chest up. 0.59.1: the 0.59.0 log showed everything added at the dialogue was gone 2 s later when the barter menu opened
	// ("0 Skylands items in it before" both times): the game restocks (resets) a vendor chest when bartering starts if the restock is due, and that wiped
	// our items; what was added after the barter menu opened was not in the list it had already built. So at the dialogue, a due restock is done here first
	// (ResetInventory, lastDayReset = today, as the game does), then the chest is topped up, and the barter menu finds no restock due.
	inline void Stock(RE::TESObjectREFR* a_chest, RE::Actor* a_who, RE::TESFaction* a_faction, bool a_barter)
	{
		if (!a_chest) {
			return;
		}
		std::vector<RE::TESBoundObject*> ours;  // every Skylands item that ends up in the chest, to be fitted to the vendor's list
		const auto     calendar = RE::Calendar::GetSingleton();
		const float    daysNow = calendar ? calendar->GetDaysPassed() : 0.0f;
		const auto     today = static_cast<std::uint32_t>((std::max)(0.0f, daysNow));
		std::string    resetNote;
		if (a_faction) {
			auto&      v = a_faction->vendorData;
			const int  every = RespawnDays();
			// 0.59.2, from the 0.59.1 log: a merchant never restocked has lastDayReset 0xFFFFFFFF; the game writes floor(days passed) when it restocks (0 on day 0.79)
			// and restocks again at the barter when today - last (unsigned) is at least the period, so a last day AHEAD of today (0.59.1 wrote 1 on day 0) is due too
			const bool due = v.lastDayReset == 0xFFFFFFFFu || today < v.lastDayReset || today - v.lastDayReset >= static_cast<std::uint32_t>(every);
			resetNote = fmt::format("day {:.2f}, last restock day {}, every {} days: {}", daysNow, v.lastDayReset, every, due ? "a restock was due" : "no restock due");
			if (due && g_reset && !a_barter) {
				a_chest->ResetInventory(false);
				v.lastDayReset = today;
				resetNote += " - done now";
			}
		}
		const auto player = RE::PlayerCharacter::GetSingleton();
		const int  level = player ? player->GetLevel() : 1;
		auto       counts = a_chest->GetInventoryCounts();
		std::string added;
		for (int i = 0; i < kTypes; ++i) {
			const auto ammo = g_ammo ? g_ammo(i) : nullptr;
			if (!ammo || g_stock[i] <= 0) {
				continue;
			}
			ours.push_back(ammo);
			const auto it = counts.find(ammo);
			const int  have = it == counts.end() ? 0 : it->second;
			if (have < g_stock[i]) {
				a_chest->AddObjectToContainer(ammo, nullptr, g_stock[i] - have, nullptr);
				added += fmt::format("{}{} {}", added.empty() ? "" : ", ", g_stock[i] - have, kKeys[i]);
			}
		}
		int gear = 0;
		for (const auto& [obj, n] : counts) {
			if (obj && n > 0 && despawn::RarityOf(obj) > 0) {
				gear += n;
				ours.push_back(obj);
			}
		}
		const auto     day = static_cast<std::uint64_t>(today);
		const auto     period = day / static_cast<std::uint64_t>((std::max)(1, g_gearDays));
		badass::ReadGuns();
		for (int k = gear; k < g_gear; ++k) {
			int        rarity = 0, type = 0;
			const auto seed = static_cast<std::uint64_t>(a_chest->GetFormID()) ^ (period << 24) ^ (static_cast<std::uint64_t>(k) * 0x9E3779B97F4A7C15ULL);
			if (const auto item = badass::PickDrop(seed, 0, 1, level, rarity, type)) {
				a_chest->AddObjectToContainer(item, nullptr, 1, nullptr);
				ours.push_back(item);
				added += fmt::format("{}\"{}\" ({} {})", added.empty() ? "" : ", ", item->GetName(), rarity, type == 0 ? "gun" : type == 1 ? "shield" : "relic");
			}
		}
		std::string fitted;
		for (const auto item : ours) {
			const char* how = Fit(item, a_faction);
			if (fitted.find(how) == std::string::npos) {
				fitted += fmt::format("{}{}", fitted.empty() ? "" : ", ", how);
			}
		}
		if (g_told.fetch_add(1) < 60) {
			const auto list = a_faction ? a_faction->vendorData.vendorSellBuyList : nullptr;
			SKSE::log::info("shop: {:08X}'s vendor list {:08X} ({} keywords, {}): Skylands items {}", a_who ? a_who->GetFormID() : 0, list ? list->GetFormID() : 0, list ? list->forms.size() : 0,
				a_faction && a_faction->vendorData.vendorValues.notBuySell ? "deals in all BUT these" : "deals only in these", fitted.empty() ? std::string("none") : fitted);
			const auto first = g_ammo ? g_ammo(2) : nullptr;  // read back: does what was added stay in the chest?
			SKSE::log::info("shop: {} {:08X} \"{}\" (merchant chest {:08X}; {}; {} Skylands items in it before): {}; pistol rounds now {}", a_barter ? "barter with" : "talking to",
				a_who ? a_who->GetFormID() : 0, a_who ? a_who->GetName() : "?", a_chest->GetFormID(), resetNote, gear, added.empty() ? std::string("already stocked") : "added " + added,
				first ? Count(a_chest, first) : -1);
		}
	}

	inline void StockSpeaker(bool a_barter)
	{
		const auto topics = RE::MenuTopicManager::GetSingleton();
		if (!topics) {
			return;
		}
		auto ref = topics->speaker.get();
		if (!ref) {
			ref = topics->lastSpeaker.get();
		}
		const auto actor = ref ? ref->As<RE::Actor>() : nullptr;
		if (!actor) {
			return;
		}
		const auto faction = actor->GetVendorFaction();
		const auto chest = faction ? faction->vendorData.merchantContainer : nullptr;
		static std::atomic_int notVendor{ 0 };
		if (!chest) {
			if (notVendor.fetch_add(1) < 10) {
				SKSE::log::info("shop: talking to {:08X} \"{}\": {}", actor->GetFormID(), actor->GetName(), faction ? "a vendor faction with no merchant chest" : "not a merchant");
			}
			return;
		}
		Stock(chest, actor, faction, a_barter);
	}

	class MenuSink : public RE::BSTEventSink<RE::MenuOpenCloseEvent>
	{
	public:
		static MenuSink* Get()
		{
			static MenuSink sink;
			return std::addressof(sink);
		}

		RE::BSEventNotifyControl ProcessEvent(const RE::MenuOpenCloseEvent* a_event, RE::BSTEventSource<RE::MenuOpenCloseEvent>*) override
		{
			if (a_event && a_event->opening && (a_event->menuName == RE::DialogueMenu::MENU_NAME || a_event->menuName == RE::BarterMenu::MENU_NAME)) {
				const bool barter = a_event->menuName == RE::BarterMenu::MENU_NAME;
				shield::Queue([barter]() {
					shield::g_stage = barter ? "shop: barter" : "shop: dialogue";
					StockSpeaker(barter);
				});
			}
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	inline void Start()
	{
		if (!g_on) {
			SKSE::log::info("shop: off (Shop=0)");
			return;
		}
		if (const auto ui = RE::UI::GetSingleton()) {
			ui->AddEventSink<RE::MenuOpenCloseEvent>(MenuSink::Get());
		}
		std::string stock, drops;
		for (int i = 0; i < kTypes; ++i) {
			stock += fmt::format("{}{} {}", stock.empty() ? "" : ", ", kKeys[i], g_stock[i]);
			drops += fmt::format("{}{} {}-{} (+{}-{})", drops.empty() ? "" : ", ", kKeys[i], g_dropMin[i], g_dropMax[i], g_bonusMin[i], g_bonusMax[i]);
		}
		SKSE::log::info("shop: on; merchants keep {} rounds and {} Skylands items (new picks every {} game days); bodies carry {}", stock, g_gear, g_gearDays, drops);
	}

	inline bool Range(const std::string& a_value, int& a_lo, int& a_hi)
	{
		try {
			const auto dash = a_value.find('-', 1);
			a_lo = std::clamp(std::stoi(a_value.substr(0, dash)), 0, 100000);
			a_hi = dash == std::string::npos ? a_lo : std::clamp(std::stoi(a_value.substr(dash + 1)), a_lo, 100000);
			return true;
		} catch (...) {
			return false;
		}
	}

	inline bool Config(const std::string& a_key, const std::string& a_value)
	{
		const auto typeOf = [&](std::string_view a_prefix) -> int {
			if (!a_key.starts_with(a_prefix)) {
				return -1;
			}
			const std::string_view rest = std::string_view(a_key).substr(a_prefix.size());
			for (int i = 0; i < kTypes; ++i) {
				if (rest == kKeys[i]) {
					return i;
				}
			}
			return -1;
		};
		try {
			if (a_key == "ShopKeywords") {
				g_fitKeywords = std::stof(a_value) != 0.0f;
			} else if (a_key == "ShopReset") {
				g_reset = std::stof(a_value) != 0.0f;
			} else if (a_key == "Shop") {
				g_on = std::stof(a_value) != 0.0f;
			} else if (a_key == "ShopGear") {
				g_gear = std::clamp(std::stoi(a_value), 0, 20);
			} else if (a_key == "ShopGearDays") {
				g_gearDays = std::clamp(std::stoi(a_value), 1, 1000);
			} else if (const int a = typeOf("ShopAmmo"); a >= 0) {
				g_stock[a] = std::clamp(std::stoi(a_value), 0, 100000);
			} else if (const int b = typeOf("StartAmmo"); b >= 0) {
				g_start[b] = std::clamp(std::stoi(a_value), 0, 100000);
			} else if (const int c = typeOf("AmmoDrop"); c >= 0) {
				Range(a_value, g_dropMin[c], g_dropMax[c]);
			} else if (const int d = typeOf("AmmoBonus"); d >= 0) {
				Range(a_value, g_bonusMin[d], g_bonusMax[d]);
			} else {
				return false;
			}
		} catch (...) {
		}
		return true;
	}
}
