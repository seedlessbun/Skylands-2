// Voices (1.22.0): the Pandora bandits speak Borderlands 2's battle dialog (docs/badass-roadmap.md, the voice stage).
//
// The installer (setup/skylands_setup/voices.py) cuts the lines of each Pandora name's Borderlands 2 speakers into sound descriptors of SkylandsGunModels.esp,
// gives the renamed bandits a silent voice type (so Skyrim's own bandit lines are gone) and writes Data/SKSE/Plugins/SkylandsVoices.txt:
//   speaker <name> <aggro> <taunt> <pain> <crit> <death> <death_fire> <death_shock> <gloat>   (sound descriptor ids of that plugin, without the file; 0 = none)
//   name <the name in game>|<speaker>,<speaker>...
// A bandit is known by its name in game (an exact match, or a name that ends with it: "Super Badass Marauder" speaks as the "Badass Marauder"), and keeps one of
// its name's speakers for its life (a roll on its form id). It speaks: entering combat with the player (aggro), when hit (pain; crit for a power or sneak
// attack), dying (death; the fire or shock line when the last hit was a fire or shock gun), now and then while fighting the player (taunt), and one of them gloats
// when the player dies. No two lines start within VoiceGap seconds of each other (a death always may).
#pragma once

#include "PCH.h"
#include "shield.h"
#include "shielditems.h"

#include <fstream>
#include <random>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace voices
{
	using Clock = std::chrono::steady_clock;

	enum Line : int
	{
		kAggro,
		kTaunt,
		kPain,
		kCrit,
		kDeath,
		kDeathFire,
		kDeathShock,
		kGloat,
		kLines
	};
	inline constexpr const char* kLineNames[kLines] = { "aggro", "taunt", "pain", "crit", "death", "death_fire", "death_shock", "gloat" };

	inline bool  g_on = true;        // Voices=0 keeps the bandits quiet (their Skyrim lines stay silenced: that is the records)
	inline float g_gap = 2.5f;       // VoiceGap: seconds between two lines of any bandits (a death may always speak)
	inline float g_painGap = 4.0f;   // VoicePainGap: seconds between two pain lines of one bandit
	inline float g_tauntMin = 10.0f; // VoiceTauntMin / VoiceTauntMax: a bandit fighting the player taunts once in this many seconds
	inline float g_tauntMax = 20.0f;
	inline float g_range = 4000.0f;  // VoiceRange: only bandits this near the player taunt

	// the element of a Skylands gun (1 fire, 2 shock, 3 corrosive, 4 slag; 0 none or not a gun), set by main.cpp (it knows the guns)
	inline int (*g_elementOf)(RE::FormID a_source) = nullptr;

	struct Speaker
	{
		std::string   name;
		std::uint32_t raw[kLines]{};
		RE::FormID    id[kLines]{};
	};
	struct State
	{
		int               speaker = -1;  // -1 not looked at yet, -2 not a Pandora bandit
		bool              aggro = false;
		bool              deathSaid = false;
		int               element = 0;  // of the last hit
		Clock::time_point nextTaunt{}, lastPain{}, lastLine{};
	};

	inline std::mutex                                            g_lock;
	inline std::vector<Speaker>                                  g_speakers;
	inline std::vector<std::pair<std::string, std::vector<int>>> g_names;  // longest first
	inline std::unordered_map<RE::FormID, State>                 g_state;
	inline Clock::time_point                                     g_lastAny{};
	inline std::atomic_bool                                      g_ready{ false };
	inline std::atomic_int                                       g_said{ 0 };

	inline float Rand(float a_lo, float a_hi)
	{
		static thread_local std::mt19937 rng{ std::random_device{}() };
		return std::uniform_real_distribution<float>(a_lo, (std::max)(a_lo, a_hi))(rng);
	}

	inline Clock::duration Seconds(float a_s) { return std::chrono::duration_cast<Clock::duration>(std::chrono::duration<float>(a_s)); }

	// Game thread, at data load: the table the installer wrote.
	inline void Load()
	{
		std::ifstream f("Data/SKSE/Plugins/SkylandsVoices.txt");
		if (!f) {
			SKSE::log::info("voices: no SkylandsVoices.txt: the bandits keep their Skyrim voices");
			return;
		}
		const auto                                            handler = RE::TESDataHandler::GetSingleton();
		std::vector<Speaker>                                  speakers;
		std::vector<std::pair<std::string, std::vector<int>>> names;
		std::vector<std::string>                              pending;
		std::string                                           line;
		int                                                   resolved = 0, missing = 0;
		while (std::getline(f, line)) {
			if (!line.empty() && line.back() == '\r') {
				line.pop_back();
			}
			if (line.rfind("speaker ", 0) == 0) {
				std::istringstream in(line.substr(8));
				Speaker            s;
				in >> s.name;
				for (int i = 0; i < kLines; ++i) {
					std::string hex;
					if (!(in >> hex)) {
						break;
					}
					s.raw[i] = static_cast<std::uint32_t>(std::strtoul(hex.c_str(), nullptr, 16));
					if (s.raw[i] && handler) {
						s.id[i] = handler->LookupFormID(s.raw[i], "SkylandsGunModels.esp");
						if (s.id[i] && RE::TESForm::LookupByID<RE::BGSSoundDescriptorForm>(s.id[i])) {
							++resolved;
						} else {
							++missing;
							s.id[i] = 0;
						}
					}
				}
				speakers.push_back(std::move(s));
			} else if (line.rfind("name ", 0) == 0) {
				pending.push_back(line.substr(5));
			}
		}
		for (const auto& entry : pending) {
			const auto bar = entry.find('|');
			if (bar == std::string::npos) {
				continue;
			}
			std::vector<int>  idx;
			std::stringstream list(entry.substr(bar + 1));
			std::string       one;
			while (std::getline(list, one, ',')) {
				for (int i = 0; i < static_cast<int>(speakers.size()); ++i) {
					if (speakers[i].name == one) {
						idx.push_back(i);
					}
				}
			}
			if (!idx.empty()) {
				names.emplace_back(entry.substr(0, bar), std::move(idx));
			}
		}
		std::sort(names.begin(), names.end(), [](const auto& a, const auto& b) { return a.first.size() > b.first.size(); });
		const auto nSpeakers = speakers.size();
		const auto nNames = names.size();
		std::string listed;
		for (const auto& [name, idx] : names) {
			listed += (listed.empty() ? "" : ", ") + name + " (" + std::to_string(idx.size()) + ")";
		}
		{
			const std::lock_guard guard(g_lock);
			g_speakers = std::move(speakers);
			g_names = std::move(names);
		}
		g_ready = nSpeakers > 0 && nNames > 0;
		SKSE::log::info("voices: {} speakers, {} lines resolved ({} not found in SkylandsGunModels.esp), names: {}", nSpeakers, resolved, missing, listed);
	}

	// with g_lock held: the speaker of an actor by its name in game, -2 when it is not a Pandora bandit (calls nothing that locks)
	inline int SpeakerOfLocked(RE::Actor* a_actor)
	{
		const char*            raw = a_actor->GetName();
		const std::string_view name = raw ? raw : "";
		for (const auto& [pandora, idx] : g_names) {
			const bool exact = name == pandora;
			const bool ends = name.size() > pandora.size() + 1 && name.ends_with(pandora) && name[name.size() - pandora.size() - 1] == ' ';
			if (exact || ends) {
				return idx[shielditems::Mix(a_actor->GetFormID() ^ 0x70CE) % idx.size()];
			}
		}
		return -2;
	}

	inline void PlayAt(RE::FormID a_sound, RE::Actor* a_actor)
	{
		const auto form = RE::TESForm::LookupByID<RE::BGSSoundDescriptorForm>(a_sound);
		const auto manager = RE::BSAudioManager::GetSingleton();
		if (!form || !manager) {
			return;
		}
		RE::BSSoundHandle handle;
		manager->GetSoundHandle(handle, form);
		auto at = a_actor->GetPosition();
		at.z += 100.0f;
		handle.SetPosition(at);
		if (const auto node = a_actor->Get3D()) {
			handle.SetObjectToFollow(node);
		}
		handle.Play();
	}

	// One line of a bandit; false when it is not a Pandora bandit, has no such line, or it is too soon.
	inline bool Say(RE::Actor* a_actor, Line a_line, bool a_force = false)
	{
		if (!g_ready || !g_on || !a_actor) {
			return false;
		}
		RE::FormID  sound = 0;
		Line        used = a_line;
		std::string speaker;
		{
			const std::lock_guard guard(g_lock);
			if (g_state.size() > 3000) {
				g_state.clear();
			}
			auto& st = g_state[a_actor->GetFormID()];
			if (st.speaker == -1) {
				st.speaker = SpeakerOfLocked(a_actor);
			}
			if (st.speaker < 0 || st.speaker >= static_cast<int>(g_speakers.size())) {
				return false;
			}
			const auto now = Clock::now();
			if (!a_force && (now - g_lastAny < Seconds(g_gap) || now - st.lastLine < Seconds(1.0f))) {
				return false;
			}
			const auto& s = g_speakers[st.speaker];
			sound = s.id[a_line];
			if (!sound) {  // a line this speaker does not have: the nearest one it has
				const Line fallback = a_line == kCrit ? kPain : (a_line == kDeathFire || a_line == kDeathShock) ? kDeath : (a_line == kGloat || a_line == kAggro) ? kTaunt : a_line;
				sound = s.id[fallback];
				used = fallback;
			}
			if (!sound) {
				return false;
			}
			g_lastAny = now;
			st.lastLine = now;
			speaker = s.name;
		}
		PlayAt(sound, a_actor);
		if (g_said.fetch_add(1) < 40) {
			const char* name = a_actor->GetName();
			SKSE::log::info("voice: {:08X} \"{}\" says {} ({} as {}, sound {:08X})", a_actor->GetFormID(), name ? name : "?", kLineNames[used], speaker, kLineNames[a_line], sound);
		}
		return true;
	}

	class CombatSink : public RE::BSTEventSink<RE::TESCombatEvent>
	{
	public:
		static CombatSink* Get()
		{
			static CombatSink sink;
			return std::addressof(sink);
		}

		RE::BSEventNotifyControl ProcessEvent(const RE::TESCombatEvent* a_event, RE::BSTEventSource<RE::TESCombatEvent>*) override
		{
			if (!g_ready || !a_event || !a_event->actor) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto actor = a_event->actor->As<RE::Actor>();
			const auto target = a_event->targetActor ? a_event->targetActor->As<RE::Actor>() : nullptr;
			if (!actor || actor->IsDead()) {
				return RE::BSEventNotifyControl::kContinue;
			}
			bool speak = false;
			{
				const std::lock_guard guard(g_lock);
				auto&                 st = g_state[actor->GetFormID()];
				if (a_event->newState == RE::ACTOR_COMBAT_STATE::kCombat && target && target->IsPlayerRef()) {
					speak = !st.aggro;
					st.aggro = true;
					st.nextTaunt = Clock::now() + Seconds(Rand(g_tauntMin, g_tauntMax));
				} else if (a_event->newState == RE::ACTOR_COMBAT_STATE::kNone) {
					st.aggro = false;
				}
			}
			if (speak) {
				Say(actor, kAggro);
			}
			return RE::BSEventNotifyControl::kContinue;
		}
	};

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
			if (!g_ready || !a_event || !a_event->target) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto actor = a_event->target->As<RE::Actor>();
			if (!actor || actor->IsPlayerRef() || actor->IsDead()) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const int element = g_elementOf ? g_elementOf(a_event->source) : 0;
			bool      pain = false;
			{
				const std::lock_guard guard(g_lock);
				auto&                 st = g_state[actor->GetFormID()];
				st.element = element;
				const auto now = Clock::now();
				if (st.speaker != -2 && now - st.lastPain >= Seconds(g_painGap)) {
					st.lastPain = now;
					pain = true;
				}
			}
			if (pain) {
				Say(actor, a_event->flags.any(RE::TESHitEvent::Flag::kPowerAttack, RE::TESHitEvent::Flag::kSneakAttack) ? kCrit : kPain);
			}
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	// the Pandora bandit nearest the player that is fighting it (for the gloat)
	inline RE::Actor* NearestFighter(RE::PlayerCharacter* a_player)
	{
		const auto lists = RE::ProcessLists::GetSingleton();
		if (!lists) {
			return nullptr;
		}
		const auto here = a_player->GetPosition();
		RE::Actor* best = nullptr;
		float      bestD = g_range * g_range;
		for (auto& handle : lists->highActorHandles) {
			const auto ptr = handle.get();
			const auto actor = ptr.get();
			if (!actor || actor->IsDead() || !actor->Is3DLoaded()) {
				continue;
			}
			const auto target = actor->GetActorRuntimeData().currentCombatTarget.get();
			if (!target || target.get() != static_cast<RE::Actor*>(a_player)) {
				continue;
			}
			const auto  there = actor->GetPosition();
			const float d = (there.x - here.x) * (there.x - here.x) + (there.y - here.y) * (there.y - here.y) + (there.z - here.z) * (there.z - here.z);
			if (d < bestD) {
				int speaker = -1;
				{
					const std::lock_guard guard(g_lock);
					auto&                 st = g_state[actor->GetFormID()];
					if (st.speaker == -1) {
						st.speaker = SpeakerOfLocked(actor);
					}
					speaker = st.speaker;
				}
				if (speaker >= 0) {
					best = actor;
					bestD = d;
				}
			}
		}
		return best;
	}

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
			if (!g_ready || !a_event || !a_event->actorDying) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto dying = a_event->actorDying->As<RE::Actor>();
			if (!dying) {
				return RE::BSEventNotifyControl::kContinue;
			}
			if (dying->IsPlayerRef()) {
				static Clock::time_point last{};
				if (Clock::now() - last > Seconds(5.0f)) {
					last = Clock::now();
					if (const auto fighter = NearestFighter(RE::PlayerCharacter::GetSingleton())) {
						Say(fighter, kGloat, true);
					}
				}
				return RE::BSEventNotifyControl::kContinue;
			}
			int  element = 0;
			bool first = false;
			{
				const std::lock_guard guard(g_lock);
				auto&                 st = g_state[dying->GetFormID()];
				first = !st.deathSaid;
				st.deathSaid = true;
				element = st.element;
			}
			if (first) {
				Say(dying, element == 1 ? kDeathFire : element == 2 ? kDeathShock : kDeath, true);
			}
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	// Game thread, once a second: the bandits fighting the player taunt now and then (one a pass)
	inline void Taunts()
	{
		const auto player = RE::PlayerCharacter::GetSingleton();
		const auto lists = RE::ProcessLists::GetSingleton();
		if (!g_ready || !g_on || !player || !lists || RE::UI::GetSingleton()->GameIsPaused()) {
			return;
		}
		shield::g_stage = "voices";
		const auto here = player->GetPosition();
		const auto now = Clock::now();
		for (auto& handle : lists->highActorHandles) {
			const auto ptr = handle.get();
			const auto actor = ptr.get();
			if (!actor || actor->IsDead() || !actor->Is3DLoaded()) {
				continue;
			}
			const auto target = actor->GetActorRuntimeData().currentCombatTarget.get();
			if (!target || target.get() != static_cast<RE::Actor*>(player)) {
				continue;
			}
			const auto there = actor->GetPosition();
			if ((there.x - here.x) * (there.x - here.x) + (there.y - here.y) * (there.y - here.y) > g_range * g_range) {
				continue;
			}
			bool due = false;
			{
				const std::lock_guard guard(g_lock);
				auto&                 st = g_state[actor->GetFormID()];
				if (st.speaker == -1) {
					st.speaker = SpeakerOfLocked(actor);
				}
				if (st.speaker < 0) {
					continue;
				}
				if (st.nextTaunt == Clock::time_point{}) {
					st.nextTaunt = now + Seconds(Rand(g_tauntMin * 0.3f, g_tauntMax * 0.5f));  // met already fighting (no combat event seen)
				} else if (now >= st.nextTaunt) {
					st.nextTaunt = now + Seconds(Rand(g_tauntMin, g_tauntMax));
					due = true;
				}
			}
			if (due && Say(actor, kTaunt)) {
				return;
			}
		}
	}

	inline void Start(RE::ScriptEventSourceHolder* a_holder)
	{
		if (!g_ready || !a_holder) {
			return;
		}
		a_holder->AddEventSink(CombatSink::Get());
		a_holder->AddEventSink(HitSink::Get());
		a_holder->AddEventSink(DeathSink::Get());
		static std::atomic_bool started{ false };
		if (!started.exchange(true)) {
			std::thread([]() {
				static std::atomic_bool queued{ false };
				for (;;) {
					std::this_thread::sleep_for(std::chrono::milliseconds(1000));
					if (queued.exchange(true)) {
						continue;
					}
					shield::Queue([]() {
						Taunts();
						queued = false;
					});
				}
			}).detach();
		}
		SKSE::log::info("voices: combat, hit and death listeners registered, taunts every {:.0f}-{:.0f} s within {:.0f} units", g_tauntMin, g_tauntMax, g_range);
	}

	inline bool Config(const std::string& a_key, const std::string& a_value)
	{
		const auto number = [&](float a_lo, float a_hi, float& a_out) {
			try {
				a_out = std::clamp(std::stof(a_value), a_lo, a_hi);
			} catch (...) {
			}
		};
		if (a_key == "Voices") {
			g_on = a_value.find('0') == std::string::npos;
		} else if (a_key == "VoiceGap") {
			number(0.0f, 60.0f, g_gap);
		} else if (a_key == "VoicePainGap") {
			number(0.0f, 60.0f, g_painGap);
		} else if (a_key == "VoiceTauntMin") {
			number(1.0f, 600.0f, g_tauntMin);
		} else if (a_key == "VoiceTauntMax") {
			number(1.0f, 600.0f, g_tauntMax);
		} else if (a_key == "VoiceRange") {
			number(100.0f, 20000.0f, g_range);
		} else {
			return false;
		}
		return true;
	}
}
