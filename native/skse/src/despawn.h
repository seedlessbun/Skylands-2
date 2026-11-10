// Despawn (1.23.0): Skylands drops lying on the ground go away once the player is far from them (the user's choice: by distance, rarer items later).
//
// Every 3 seconds the plugin looks at the references of the loaded cells for loose Skylands items (guns, shields, relics: a base with a SkylandsRarity_ keyword)
// that the game made at run time (form id FF......). An item goes (Disable + Delete, and its rarity beam with it) when the player is farther from it than its
// rarity allows (ini DespawnCommon ... DespawnEtech, in game units; 0 = never), or is in another space (another interior, or the world while it lies inside).
// An item whose cell unloaded while the player was that far away is marked and goes when it is next loaded. Never touched: what the player dropped (the
// container-changed event names it), anything in a pack or chest (not a loose reference), records placed by plugins.
// The marks and the player's own drops are kept in the co-save ('DSPN'), so a load does not forget them.
#pragma once

#include "PCH.h"
#include "shield.h"

#include <thread>
#include <unordered_set>

namespace despawn
{
	using Clock = std::chrono::steady_clock;

	inline int   g_beamCap = 24;  // rarity beams at once (main.cpp TrackBeam): past it the lowest rarity loses its beam first
	inline bool  g_on = true;  // Despawn=0 keeps everything
	// 1.38.2: NPCs must not pick up Skylands loot from the ground (the user: enemies walked to it, took it, and it was gone after they died).
	// Every loose item gets the reference flag "No AI Acquire" (kNoAIAcquire) at each scan; an NPC that takes one anyway drops it again (NoNpcPickup=0: off).
	inline bool  g_noPickup = true;
	inline std::atomic_int g_flagged{ 0 };
	inline std::atomic_int g_droppedBack{ 0 };

	inline bool NoAcquire(RE::TESObjectREFR* a_ref)
	{
		constexpr std::uint32_t kFlag = RE::TESObjectREFR::RecordFlags::kNoAIAcquire;
		if (!g_noPickup || !a_ref || (a_ref->formFlags & kFlag) != 0) {
			return false;
		}
		a_ref->formFlags |= kFlag;
		a_ref->AddChange(RE::TESForm::ChangeFlags::kFlags);
		return true;
	}
	inline float g_dist[7] = { 0.0f, 3000.0f, 4500.0f, 7000.0f, 10000.0f, 16000.0f, 16000.0f };  // by rarity 1 common ... 6 e-tech
	inline constexpr const char* kRarityNames[7] = { "?", "common", "uncommon", "rare", "epic", "legendary", "e-tech" };

	struct Item
	{
		int           rarity = 0;
		RE::NiPoint3  pos{};
		RE::FormID    space = 0;  // the interior cell, or the worldspace
		bool          expired = false;
	};

	inline std::mutex                             g_lock;
	inline std::unordered_map<RE::FormID, Item>   g_items;   // loose items seen
	inline std::unordered_set<RE::FormID>         g_exempt;  // dropped by the player
	inline std::unordered_map<RE::FormID, int>    g_rarityOf;  // base form -> rarity (0: not a Skylands item)
	inline std::atomic_int                        g_removed{ 0 };
	inline void (*g_onRemoved)(RE::TESObjectREFR* a_item) = nullptr;  // main.cpp: takes the item's beam away

	inline int RarityOf(RE::TESBoundObject* a_base)
	{
		if (!a_base) {
			return 0;
		}
		{
			const std::lock_guard guard(g_lock);
			if (const auto it = g_rarityOf.find(a_base->GetFormID()); it != g_rarityOf.end()) {
				return it->second;
			}
		}
		int        rarity = 0;
		const auto form = a_base->As<RE::BGSKeywordForm>();
		if (form && (a_base->Is(RE::FormType::Weapon) || a_base->Is(RE::FormType::Armor))) {
			form->ForEachKeyword([&](RE::BGSKeyword* a_keyword) {
				const std::string_view edid = a_keyword && a_keyword->formEditorID.c_str() ? a_keyword->formEditorID.c_str() : "";
				if (edid.starts_with("SkylandsRarity_")) {
					const std::string_view r = edid.substr(15);
					rarity = r == "common" ? 1 : r == "uncommon" ? 2 : r == "rare" ? 3 : r == "epic" ? 4 : r == "legendary" ? 5 : r == "etech" ? 6 : 0;
					return RE::BSContainer::ForEachResult::kStop;
				}
				return RE::BSContainer::ForEachResult::kContinue;
			});
		}
		const std::lock_guard guard(g_lock);
		g_rarityOf[a_base->GetFormID()] = rarity;
		return rarity;
	}

	inline RE::FormID SpaceOf(RE::TESObjectREFR* a_ref)
	{
		const auto cell = a_ref->GetParentCell();
		if (cell && cell->IsInteriorCell()) {
			return cell->GetFormID();
		}
		const auto world = a_ref->GetWorldspace();
		return world ? world->GetFormID() : 0;
	}

	inline float Dist2(const RE::NiPoint3& a, const RE::NiPoint3& b)
	{
		return (a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y) + (a.z - b.z) * (a.z - b.z);
	}

	inline void Remove(RE::TESObjectREFR* a_ref, int a_rarity, float a_dist, bool a_marked)
	{
		if (g_onRemoved) {
			g_onRemoved(a_ref);
		}
		a_ref->Disable();
		a_ref->SetDelete(true);
		if (g_removed.fetch_add(1) < 40) {
			const char* name = a_ref->GetName();
			SKSE::log::info("despawn: {:08X} \"{}\" ({}) {}", a_ref->GetFormID(), name ? name : "?", kRarityNames[std::clamp(a_rarity, 0, 6)],
				a_marked ? "was left behind while its cell was unloaded" : (a_dist < 0.0f ? "lies in another space than the player" : fmt::format("is {:.0f} units away", a_dist)));
		}
	}

	// Game thread, every 3 seconds.
	inline void Scan()
	{
		const auto player = RE::PlayerCharacter::GetSingleton();
		const auto tes = RE::TES::GetSingleton();
		if ((!g_on && !g_noPickup) || !player || !tes || !player->GetParentCell() || RE::UI::GetSingleton()->GameIsPaused()) {
			return;
		}
		shield::g_stage = "despawn";
		int flaggedNow = 0;
		const auto here = player->GetPosition();
		const auto space = SpaceOf(player);
		struct Hit
		{
			RE::TESObjectREFR* ref;
			int                rarity;
			float              dist;
			bool               marked;
		};
		std::vector<Hit>               hits;
		std::unordered_set<RE::FormID> seen;
		int                            loose[7]{};
		tes->ForEachReference([&](RE::TESObjectREFR* a_ref) {
			if (!a_ref || (a_ref->GetFormID() >> 24) != 0xFF || a_ref->IsDisabled() || a_ref->IsDeleted()) {
				return RE::BSContainer::ForEachResult::kContinue;
			}
			const int rarity = RarityOf(a_ref->GetBaseObject());
			if (rarity <= 0) {
				return RE::BSContainer::ForEachResult::kContinue;
			}
			++loose[rarity];
			if (NoAcquire(a_ref)) {
				++flaggedNow;
			}
			if (!g_on) {
				return RE::BSContainer::ForEachResult::kContinue;
			}
			const auto id = a_ref->GetFormID();
			seen.insert(id);
			const auto where = SpaceOf(a_ref);
			bool       marked = false;
			{
				const std::lock_guard guard(g_lock);
				if (g_exempt.contains(id)) {
					return RE::BSContainer::ForEachResult::kContinue;
				}
				auto& item = g_items[id];
				// run-time ids are reused: a mark only counts for the same kind of item where it was left
				const bool same = item.rarity == rarity && item.space == where && Dist2(item.pos, a_ref->GetPosition()) < 300.0f * 300.0f;
				marked = item.expired && same;
				item.rarity = rarity;
				item.pos = a_ref->GetPosition();
				item.space = where;
				item.expired = marked;
			}
			const float limit = g_dist[rarity];
			if (marked) {
				hits.push_back({ a_ref, rarity, 0.0f, true });
			} else if (limit > 0.0f && where != space) {
				hits.push_back({ a_ref, rarity, -1.0f, false });
			} else if (limit > 0.0f && Dist2(a_ref->GetPosition(), here) > limit * limit) {
				hits.push_back({ a_ref, rarity, std::sqrt(Dist2(a_ref->GetPosition(), here)), false });
			}
			return RE::BSContainer::ForEachResult::kContinue;
		});
		if (flaggedNow > 0 && g_flagged.fetch_add(flaggedNow) < 200) {
			SKSE::log::info("despawn: {} loose Skylands item(s) marked 'no AI acquire' (NPCs leave them on the ground)", flaggedNow);
		}
		if (!g_on) {
			return;
		}
		// items not loaded now: the player went far away from where they were last seen -> marked, gone when next loaded
		int marks = 0;
		{
			const std::lock_guard guard(g_lock);
			for (auto& [id, item] : g_items) {
				if (seen.contains(id) || item.expired || item.rarity <= 0 || g_dist[item.rarity] <= 0.0f) {
					continue;
				}
				if (item.space != space || Dist2(item.pos, here) > g_dist[item.rarity] * g_dist[item.rarity]) {
					item.expired = true;
					++marks;
				}
			}
			if (g_items.size() > 4000) {  // forget knowledge rather than grow without end
				std::erase_if(g_items, [](const auto& kv) { return !kv.second.expired; });
				if (g_items.size() > 4000) {
					g_items.clear();
				}
			}
		}
		for (const auto& h : hits) {
			Remove(h.ref, h.rarity, h.dist, h.marked);
			const std::lock_guard guard(g_lock);
			g_items.erase(h.ref->GetFormID());
		}
		static Clock::time_point lastLine{};
		static int               lines = 0;
		if ((Clock::now() - lastLine > std::chrono::seconds(30) || !hits.empty()) && lines < 120) {
			lastLine = Clock::now();
			++lines;
			std::size_t known = 0, exempt = 0;
			{
				const std::lock_guard guard(g_lock);
				known = g_items.size();
				exempt = g_exempt.size();
			}
			SKSE::log::info("despawn: loose Skylands items loaded: common {}, uncommon {}, rare {}, epic {}, legendary {}, e-tech {}; {} removed now, {} newly left behind, {} remembered, {} dropped by the player",
				loose[1], loose[2], loose[3], loose[4], loose[5], loose[6], hits.size(), marks, known, exempt);
		}
	}

	// the player dropped something: it is the player's, never despawned
	class DropSink : public RE::BSTEventSink<RE::TESContainerChangedEvent>
	{
	public:
		static DropSink* Get()
		{
			static DropSink sink;
			return std::addressof(sink);
		}

		RE::BSEventNotifyControl ProcessEvent(const RE::TESContainerChangedEvent* a_event, RE::BSTEventSource<RE::TESContainerChangedEvent>*) override
		{
			if (!a_event) {
				return RE::BSEventNotifyControl::kContinue;
			}
			// an NPC took a Skylands item from the ground: it drops it again (a task: never change a pack inside its own event)
			if (g_noPickup && a_event->oldContainer == 0 && a_event->newContainer != 0 && a_event->newContainer != 0x14 && a_event->baseObj && a_event->reference) {  // a reference = taken from the world (not given by AddItem)
				const auto base = RE::TESForm::LookupByID<RE::TESBoundObject>(a_event->baseObj);
				const int  rarity = RarityOf(base);  // takes g_lock: before the guard below
				const auto taker = rarity > 0 ? RE::TESForm::LookupByID<RE::Actor>(a_event->newContainer) : nullptr;
				if (taker && !taker->IsPlayerRef()) {
					const RE::FormID who = a_event->newContainer, what = a_event->baseObj;
					const int        count = std::max(1, static_cast<int>(a_event->itemCount));
					shield::Queue([who, what, count, rarity]() {
						const auto actor = RE::TESForm::LookupByID<RE::Actor>(who);
						const auto item = RE::TESForm::LookupByID<RE::TESBoundObject>(what);
						if (!actor || !item || actor->IsDead()) {
							return;
						}
						const auto handle = actor->RemoveItem(item, count, RE::ITEM_REMOVE_REASON::kDropping, nullptr, nullptr);
						const auto ref = handle.get();
						NoAcquire(ref.get());
						if (g_droppedBack.fetch_add(1) < 40) {
							const char* an = actor->GetName();
							const char* in = item->GetName();
							SKSE::log::info("despawn: {:08X} \"{}\" picked up {:08X} \"{}\" ({}) from the ground: dropped again{}", who, an ? an : "?", what, in ? in : "?",
								kRarityNames[std::clamp(rarity, 0, 6)], ref ? fmt::format(" as {:08X}", ref->GetFormID()) : " (no reference came back)");
						}
					});
				}
			}
			const auto       ptr = a_event->reference.get();
			const RE::FormID id = ptr ? ptr->GetFormID() : 0;
			if (!id) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const std::lock_guard guard(g_lock);
			if (a_event->oldContainer == 0x14 && a_event->newContainer == 0) {
				if (g_exempt.size() < 4000) {
					g_exempt.insert(id);
				}
				g_items.erase(id);
			} else if (a_event->oldContainer == 0 && a_event->newContainer != 0) {
				g_items.erase(id);  // picked up from the ground: it is no longer loose (its id may be reused)
				g_exempt.erase(id);
			}
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	// ---- the co-save ----
	constexpr std::uint32_t kRecord = 0x4E505344;  // 'DSPN'

	inline void Save(SKSE::SerializationInterface* a_intfc)
	{
		const std::lock_guard guard(g_lock);
		if (!a_intfc->OpenRecord(kRecord, 1)) {
			return;
		}
		a_intfc->WriteRecordData(static_cast<std::uint32_t>(g_exempt.size()));
		for (const auto id : g_exempt) {
			a_intfc->WriteRecordData(id);
		}
		a_intfc->WriteRecordData(static_cast<std::uint32_t>(g_items.size()));
		for (const auto& [id, item] : g_items) {
			a_intfc->WriteRecordData(id);
			a_intfc->WriteRecordData(static_cast<std::int32_t>(item.rarity));
			a_intfc->WriteRecordData(item.pos.x);
			a_intfc->WriteRecordData(item.pos.y);
			a_intfc->WriteRecordData(item.pos.z);
			a_intfc->WriteRecordData(item.space);
			a_intfc->WriteRecordData(static_cast<std::uint8_t>(item.expired ? 1 : 0));
		}
		SKSE::log::info("despawn: save - {} loose items remembered, {} dropped by the player", g_items.size(), g_exempt.size());
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
		std::uint32_t n = 0;
		a_intfc->ReadRecordData(n);
		for (std::uint32_t i = 0; i < n && i < 4000; ++i) {
			std::uint32_t id = 0, newId = 0;
			a_intfc->ReadRecordData(id);
			if (a_intfc->ResolveFormID(id, newId)) {
				g_exempt.insert(newId);
			}
		}
		std::uint32_t m = 0;
		a_intfc->ReadRecordData(m);
		for (std::uint32_t i = 0; i < m && i < 4000; ++i) {
			std::uint32_t id = 0, newId = 0, space = 0, newSpace = 0;
			std::int32_t  rarity = 0;
			Item          item;
			std::uint8_t  expired = 0;
			a_intfc->ReadRecordData(id);
			a_intfc->ReadRecordData(rarity);
			a_intfc->ReadRecordData(item.pos.x);
			a_intfc->ReadRecordData(item.pos.y);
			a_intfc->ReadRecordData(item.pos.z);
			a_intfc->ReadRecordData(space);
			a_intfc->ReadRecordData(expired);
			if (a_intfc->ResolveFormID(id, newId)) {
				item.rarity = std::clamp(static_cast<int>(rarity), 0, 6);
				item.space = a_intfc->ResolveFormID(space, newSpace) ? newSpace : space;
				item.expired = expired != 0;
				g_items[newId] = item;
			}
		}
		SKSE::log::info("despawn: load - {} loose items remembered, {} dropped by the player", g_items.size(), g_exempt.size());
		return true;
	}

	inline void Revert()
	{
		const std::lock_guard guard(g_lock);
		g_items.clear();
		g_exempt.clear();
	}

	inline void Start(RE::ScriptEventSourceHolder* a_holder)
	{
		shield::g_extraSave.push_back(&Save);
		shield::g_extraLoad.push_back(&Load);
		shield::g_extraRevert.push_back(&Revert);
		if (a_holder) {
			a_holder->AddEventSink(DropSink::Get());
		}
		static std::atomic_bool started{ false };
		if (started.exchange(true)) {
			return;
		}
		std::thread([]() {
			static std::atomic_bool queued{ false };
			for (;;) {
				std::this_thread::sleep_for(std::chrono::seconds(3));
				if (queued.exchange(true)) {
					continue;
				}
				shield::Queue([]() {
					Scan();
					queued = false;
				});
			}
		}).detach();
		SKSE::log::info("despawn: on {}; beams at most {}; distances common {:.0f}, uncommon {:.0f}, rare {:.0f}, epic {:.0f}, legendary {:.0f}, e-tech {:.0f} (0 = never)", g_on, g_beamCap, g_dist[1], g_dist[2], g_dist[3],
			g_dist[4], g_dist[5], g_dist[6]);
	}

	inline bool Config(const std::string& a_key, const std::string& a_value)
	{
		static const std::pair<const char*, int> keys[] = { { "DespawnCommon", 1 }, { "DespawnUncommon", 2 }, { "DespawnRare", 3 }, { "DespawnEpic", 4 }, { "DespawnLegendary", 5 },
			{ "DespawnEtech", 6 } };
		if (a_key == "BeamCap") {
			try {
				g_beamCap = std::clamp(std::stoi(a_value), 1, 96);
			} catch (...) {
			}
			return true;
		}
		if (a_key == "NoNpcPickup") {
			try {
				g_noPickup = std::stoi(a_value) != 0;
			} catch (...) {
			}
			return true;
		}
		if (a_key == "Despawn") {
			try {
				g_on = std::stoi(a_value) != 0;
			} catch (...) {
			}
			return true;
		}
		for (const auto& [name, r] : keys) {
			if (a_key == name) {
				try {
					g_dist[r] = std::clamp(std::stof(a_value), 0.0f, 1000000.0f);
				} catch (...) {
				}
				return true;
			}
		}
		return false;
	}
}
