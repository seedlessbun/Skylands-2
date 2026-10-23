// SkylandsNative: the SKSE plugin the Skylands guns use for what plain Papyrus cannot do.
//
//   TriggerHeld / TriggerPressed   the attack button ("Right Attack/Block": keyboard, mouse or gamepad, whatever the player mapped)
//   GunClip / GunIntervalMs / GunReloadMs / FireGun   a Skylands staff gun's numbers (from its keywords) and its bullet, launched from the gun's muzzle
//                                  along the crosshair; no cast animation, no wind-up, no magicka. Enemies: the burst after the game's cast
//
// Papyrus class: SkylandsNative, static functions. Data/Scripts/SkylandsNative.pex (written by the installer, scripts.native_stub)
// declares them as native; the types there must match the ones below.
// Built with CommonLibSSE-NG and Address Library, so it works on every runtime that Address Library supports.

#include "PCH.h"

namespace
{
	constexpr std::int32_t kVersion = 120;  // 1.2.0

	std::atomic_bool g_held{ false };
	std::atomic_bool g_gunMode{ false };  // a Skylands gun is in the hand: the attack button is ours, the game's attack handler does not get it
	std::atomic_bool g_latch{ false };  // set by a button going down, cleared when Papyrus asks: a tap shorter than a poll is still seen

	float g_convergence = 3000.0f;  // how far ahead the bullets are aimed to cross the crosshair (game units)

	struct Vec3
	{
		float x, y, z;
	};

	Vec3 Norm(Vec3 v)
	{
		const float n = std::sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
		return n > 1e-6f ? Vec3{ v.x / n, v.y / n, v.z / n } : Vec3{ 0.0f, 1.0f, 0.0f };
	}

	Vec3 Cross(Vec3 a, Vec3 b)
	{
		return { a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x };
	}

	void LoadConfig()
	{
		std::ifstream f("Data/SKSE/Plugins/SkylandsNative.ini");
		std::string   line;
		while (std::getline(f, line)) {
			const auto eq = line.find('=');
			if (eq == std::string::npos || line.starts_with(';') || line.starts_with('[')) {
				continue;
			}
			std::string key = line.substr(0, eq);
			std::erase_if(key, [](unsigned char c) { return std::isspace(c); });
			if (key == "Convergence") {
				try {
					g_convergence = (std::max)(200.0f, std::stof(line.substr(eq + 1)));
				} catch (...) {
				}
			}
		}
	}

	// Is this button event the attack button? By its user event name, or, when the name is missing (the game may not name the
	// events of controls that are switched off), by the key the player has mapped to "Right Attack/Block" on that device.
	bool IsAttack(const RE::ButtonEvent* a_button, const RE::UserEvents* a_events)
	{
		if (a_button->QUserEvent() == a_events->rightAttack) {
			return true;
		}
		if (!a_button->QUserEvent().empty()) {
			return false;
		}
		const auto map = RE::ControlMap::GetSingleton();
		return map && map->GetMappedKey(a_events->rightAttack.c_str(), a_button->GetDevice()) == a_button->GetIDCode();
	}

	// The attack button, from the game's own input events.
	class InputSink : public RE::BSTEventSink<RE::InputEvent*>
	{
	public:
		static InputSink* Get()
		{
			static InputSink sink;
			return std::addressof(sink);
		}

		RE::BSEventNotifyControl ProcessEvent(RE::InputEvent* const* a_event, RE::BSTEventSource<RE::InputEvent*>*) override
		{
			if (!a_event) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto events = RE::UserEvents::GetSingleton();
			for (auto e = *a_event; e; e = e->next) {
				if (e->GetEventType() != RE::INPUT_EVENT_TYPE::kButton) {
					continue;
				}
				const auto button = e->AsButtonEvent();
				if (!button || !IsAttack(button, events)) {
					continue;
				}
				if (button->IsPressed()) {
					g_held = true;
					if (button->IsDown()) {
						g_latch = true;
					}
				} else {
					g_held = false;
				}
			}
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	// The game's own attack handler (right and left attack/block). While a Skylands gun is in the hand it is not given the right attack
	// button, so the staff plays no attack or cast animation; block (left) and everything else go through untouched. The vtable
	// slot of ProcessButton is 4, and 6 from Skyrim 1.7.99 on (the base class gained two virtual functions: CommonLibSSE-NG's
	// PlayerInputHandler says so).
	struct AttackHook
	{
		static void Thunk(RE::AttackBlockHandler* a_this, RE::ButtonEvent* a_event, RE::PlayerControlsData* a_data)
		{
			if (g_gunMode.load() && a_event && IsAttack(a_event, RE::UserEvents::GetSingleton())) {
				return;
			}
			Original(a_this, a_event, a_data);
		}

		static bool Install()
		{
			REL::Relocation<std::uintptr_t> vtbl{ RE::VTABLE_AttackBlockHandler[0] };
			const std::size_t slot = REL::Module::IsAtLeast(SKSE::RUNTIME_SSE_1_7_99) ? 0x06 : 0x04;
			Original = vtbl.write_vfunc(slot, Thunk);
			SKSE::log::info("attack handler hooked (vtable slot {})", slot);
			return true;
		}

		static inline REL::Relocation<decltype(Thunk)> Original;
	};

	bool MenuOpen()
	{
		const auto ui = RE::UI::GetSingleton();
		return ui && ui->GameIsPaused();
	}

	// ---- Papyrus ----------------------------------------------------------------------------------------------------

	std::int32_t Version(RE::StaticFunctionTag*)
	{
		return kVersion;
	}

	// Papyrus: a Skylands gun is in the hand (true) or not (false); the plugin starts with false, so a saved game cannot keep it on
	bool SetGunMode(RE::StaticFunctionTag*, bool a_on)
	{
		g_gunMode = a_on;
		SKSE::log::info("gun mode {}", a_on ? "on" : "off");
		return true;
	}

	bool TriggerHeld(RE::StaticFunctionTag*)
	{
		return g_held.load() && !MenuOpen();
	}

	bool TriggerPressed(RE::StaticFunctionTag*)
	{
		const bool pressed = g_latch.exchange(false);
		return pressed && !MenuOpen();
	}

	// ---- guns ----------------------------------------------------------------------------------------------------------
	//
	// A Skylands staff gun is a staff weapon whose enchantment is the bullet (a fire-and-forget aimed effect with the Borderlands
	// projectile) and whose keywords carry its numbers in an editor id: SkylandsGun_c30_i100_r2000_s20_b3 = magazine 30, a round
	// every 100 ms, reload 2000 ms, spread 2.0 degrees, 3 rounds a burst (enemies). The same weapon serves the player (this plugin
	// fires it from the attack button) and enemies (the game casts the enchantment, this plugin adds the rest of the burst).

	struct GunInfo
	{
		int   clip{ 0 };
		float interval{ 0.1f };  // seconds
		float reload{ 2.0f };    // seconds
		float spread{ 2.0f };    // degrees
		int   burst{ 1 };        // rounds per burst of an enemy
	};

	std::mutex                                     g_gunLock;
	std::unordered_map<RE::FormID, GunInfo>        g_guns;

	// The numbers of a gun weapon from its keywords; false when it is not a Skylands staff gun.
	bool GunOf(RE::TESObjectWEAP* a_weapon, GunInfo& a_out)
	{
		if (!a_weapon) {
			return false;
		}
		const std::lock_guard lock(g_gunLock);
		if (const auto it = g_guns.find(a_weapon->GetFormID()); it != g_guns.end()) {
			a_out = it->second;
			return it->second.clip > 0;
		}
		GunInfo info{};
		int     seen = 0;
		std::string names;
		a_weapon->ForEachKeyword([&](RE::BGSKeyword* a_keyword) {
			// the member, not the virtual GetFormEditorID (a vtable slot that moved between runtimes would read garbage)
			const std::string_view edid = a_keyword && a_keyword->formEditorID.c_str() ? a_keyword->formEditorID.c_str() : "";
			++seen;
			if (names.size() < 300) {
				names += std::string(edid) + " ";
			}
			constexpr std::string_view prefix = "SkylandsGun_";
			if (edid.starts_with(prefix)) {
				std::string_view rest = edid.substr(prefix.size());
				while (!rest.empty()) {
					const auto cut = rest.find('_');
					const std::string_view part = rest.substr(0, cut);
					rest = cut == std::string_view::npos ? std::string_view{} : rest.substr(cut + 1);
					if (part.size() < 2) {
						continue;
					}
					int value = 0;
					std::from_chars(part.data() + 1, part.data() + part.size(), value);
					switch (part[0]) {
					case 'c': info.clip = value; break;
					case 'i': info.interval = (std::max)(0.02f, value / 1000.0f); break;
					case 'r': info.reload = value / 1000.0f; break;
					case 's': info.spread = value / 10.0f; break;
					case 'b': info.burst = (std::max)(1, value); break;
					default: break;
					}
				}
			}
			return RE::BSContainer::ForEachResult::kContinue;
		});
		static int told = 0;
		if (told < 12 && (info.clip > 0 || told < 4)) {  // the first weapons looked at are told: how many keywords, which, and what was read
			++told;
			SKSE::log::info("gun check {:08X}: {} keywords [{}] -> clip {}, interval {:.3f}, reload {:.1f}, spread {:.1f}, burst {}", a_weapon->GetFormID(), seen,
				names, info.clip, info.interval, info.reload, info.spread, info.burst);
		}
		g_guns[a_weapon->GetFormID()] = info;
		a_out = info;
		return info.clip > 0;
	}

	// The gun in an actor's hands (right hand first, then left): the weapon, and its numbers.
	RE::TESObjectWEAP* HeldGun(RE::Actor* a_actor, GunInfo& a_out)
	{
		if (!a_actor) {
			return nullptr;
		}
		for (const bool left : { false, true }) {
			const auto weapon = a_actor->GetEquippedObject(left) ? a_actor->GetEquippedObject(left)->As<RE::TESObjectWEAP>() : nullptr;
			if (weapon && weapon->formEnchanting && GunOf(weapon, a_out)) {
				return weapon;
			}
		}
		return nullptr;
	}

	// Launches the held gun's bullet. The player's bullets cross the crosshair (a_target null); an enemy's go at a_target's chest.
	// a_spread is in degrees; right, up and forward move the start in the view's own axes.
	void Launch(RE::FormID a_shooter, RE::FormID a_targetId, float a_right, float a_up, float a_forward, float a_spreadMult)
	{
		const auto shooter = RE::TESForm::LookupByID<RE::Actor>(a_shooter);
		GunInfo    info{};
		const auto weapon = HeldGun(shooter, info);
		if (!weapon || shooter->IsDead()) {
			return;
		}
		const auto spell = weapon->formEnchanting;
		if (!spell->GetAVEffect() || !spell->GetAVEffect()->data.projectileBase) {
			SKSE::log::warn("gun {:08X}: its enchantment has no projectile", weapon->GetFormID());
			return;
		}
		const auto target = a_targetId ? RE::TESForm::LookupByID<RE::Actor>(a_targetId) : nullptr;
		const bool npc = !shooter->IsPlayerRef();

		// where the shooter is looking: the eye (the camera in first person) and the way it points
		RE::NiPoint3 eye{}, look{};
		shooter->GetEyeVector(eye, look, true);
		Vec3 dir = Norm({ look.x, look.y, look.z });
		if (npc) {
			eye = shooter->GetPosition();
			eye.z += shooter->GetHeight() * 0.85f;
		}
		const Vec3 right = Norm(Cross(dir, { 0.0f, 0.0f, 1.0f }));
		const Vec3 up = Cross(right, dir);

		// where the bullet starts: the muzzle node of the equipped gun's own mesh (the installer's gun meshes hold an empty node,
		// SkylandsMuzzle, at the end of the barrel), else the right hand's magic node, else a point ahead of the eye
		const auto camera = RE::PlayerCamera::GetSingleton();
		const bool first = !npc && camera && camera->IsInFirstPerson();
		RE::NiPoint3 origin = eye;
		const char*  found = "none";
		if (const auto root = shooter->Get3D(first)) {
			if (const auto node = root->GetObjectByName("SkylandsMuzzle"sv)) {
				origin = node->world.translate;
				found = "muzzle";
			} else if (const auto hand = root->GetObjectByName("NPC R MagicNode [RMag]"sv)) {
				origin = hand->world.translate;
				found = "hand";
			}
		}
		if (std::string_view(found) == "none") {  // no node found: a point ahead of the eye, to the right and below it
			origin = { eye.x + dir.x * 40.0f + right.x * 14.0f, eye.y + dir.y * 40.0f + right.y * 14.0f, eye.z + dir.z * 40.0f - 12.0f };
		}
		static std::string_view lastFound[2];
		if (lastFound[npc] != found) {  // said once, and again when it changes
			lastFound[npc] = found;
			SKSE::log::info("bullet origin ({}): {} ({}), {} person", npc ? "enemy" : "player", found,
				std::string_view(found) == "muzzle" ? "the gun's own muzzle node" : "no muzzle node in the equipped weapon's 3D", first ? "first" : "third");
		}
		origin.x += right.x * a_right + up.x * a_up + dir.x * a_forward;
		origin.y += right.y * a_right + up.y * a_up + dir.y * a_forward;
		origin.z += right.z * a_right + up.z * a_up + dir.z * a_forward;

		// aimed at the point the crosshair looks at some way ahead, so the bullet crosses the crosshair rather than running beside it;
		// an enemy aims at the chest of its target
		Vec3 point{ eye.x + dir.x * g_convergence, eye.y + dir.y * g_convergence, eye.z + dir.z * g_convergence };
		if (target) {
			const auto at = target->GetPosition();
			point = { at.x, at.y, at.z + target->GetHeight() * 0.7f };
		}
		const Vec3 aim = Norm({ point.x - origin.x, point.y - origin.y, point.z - origin.z });
		float      pitch = -std::asin(std::clamp(aim.z, -1.0f, 1.0f));  // Skyrim's pitch is positive downwards
		float      heading = std::atan2(aim.x, aim.y);

		// the spread: a random direction inside a cone (an enemy's is twice the player's)
		const float spread = info.spread * (npc ? 2.0f : (std::max)(0.0f, a_spreadMult));  // relics may tighten the player's spread
		if (spread > 0.0f) {
			static thread_local std::mt19937 rng{ std::random_device{}() };
			std::uniform_real_distribution<float> unit(0.0f, 1.0f);
			const float radius = spread * std::numbers::pi_v<float> / 180.0f * std::sqrt(unit(rng));
			const float angle = 2.0f * std::numbers::pi_v<float> * unit(rng);
			pitch += radius * std::sin(angle);
			heading += radius * std::cos(angle);
		}

		RE::Projectile::LaunchData data(shooter, origin, { pitch, heading }, spell);
		data.castingSource = RE::MagicSystem::CastingSource::kRightHand;
		RE::ProjectileHandle handle{};
		RE::Projectile::Launch(&handle, data);
	}

	void RunOnGameThread(std::function<void()> a_work)
	{
		if (const auto task = SKSE::GetTaskInterface()) {
			task->AddTask(std::move(a_work));
		}
	}

	// ---- enemies ---------------------------------------------------------------------------------------------------------
	//
	// An enemy with a Skylands gun in its hands casts the gun's enchantment the way it casts any staff: the game launches the
	// first bullet. The rest of the burst is ours: it is started from the cast event, spaced by the gun's interval, from the gun's
	// muzzle, at the enemy's combat target. The gun's magazine is not counted for enemies.
	class CastSink : public RE::BSTEventSink<RE::TESSpellCastEvent>
	{
	public:
		static CastSink* Get()
		{
			static CastSink sink;
			return std::addressof(sink);
		}

		RE::BSEventNotifyControl ProcessEvent(const RE::TESSpellCastEvent* a_event, RE::BSTEventSource<RE::TESSpellCastEvent>*) override
		{
			if (!a_event || !a_event->object) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto actor = skyrim_cast<RE::Actor*>(a_event->object.get());
			if (!actor || actor->IsPlayerRef()) {
				return RE::BSEventNotifyControl::kContinue;
			}
			GunInfo    info{};
			const auto weapon = HeldGun(actor, info);
			if (!weapon) {
				return RE::BSEventNotifyControl::kContinue;
			}
			static std::atomic_int logged{ 0 };
			const bool ours = weapon->formEnchanting->GetFormID() == a_event->spell;
			if (logged.fetch_add(1) < 8) {  // the first few casts of enemies holding a gun are told, to see what the game sends
				SKSE::log::info("enemy {:08X} cast {:08X} holding gun {:08X} (its enchantment {:08X}): {}", actor->GetFormID(), a_event->spell,
					weapon->GetFormID(), weapon->formEnchanting->GetFormID(), ours ? "a burst of " + std::to_string(info.burst) : "not the gun's own cast"s);
			}
			if (!ours || info.burst < 2) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const RE::FormID shooter = actor->GetFormID();
			const int        more = info.burst - 1;
			const auto       gap = std::chrono::milliseconds(static_cast<int>(info.interval * 1000.0f));
			std::thread([shooter, more, gap]() {
				for (int i = 0; i < more; ++i) {
					std::this_thread::sleep_for(gap);
					RunOnGameThread([shooter]() {
						const auto who = RE::TESForm::LookupByID<RE::Actor>(shooter);
						if (!who || who->IsDead() || !who->Is3DLoaded()) {
							return;
						}
						const auto target = who->GetActorRuntimeData().currentCombatTarget.get();
						Launch(shooter, target ? target->GetFormID() : 0, 0.0f, 0.0f, 0.0f, 1.0f);
					});
				}
			}).detach();
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	// ---- Papyrus (continued) ---------------------------------------------------------------------------------------------

	// The gun weapon's numbers, as plain integers (a Papyrus call with no string parameter: 0.15.1 read its numbers by a key string and the
	// script always got 0). GunClip is 0 for a weapon that is no Skylands staff gun, so GunClip(w) > 0 is "is it a gun".
	std::int32_t GunClip(RE::StaticFunctionTag*, RE::TESObjectWEAP* a_weapon)
	{
		GunInfo info{};
		const bool ok = GunOf(a_weapon, info);
		static std::atomic_int told{ 0 };
		if (told.fetch_add(1) < 6) {  // the first answers are told
			SKSE::log::info("GunClip({:08X}) = {}", a_weapon ? a_weapon->GetFormID() : 0u, ok ? info.clip : 0);
		}
		return ok ? info.clip : 0;
	}

	// Milliseconds between two rounds of an automatic gun
	std::int32_t GunIntervalMs(RE::StaticFunctionTag*, RE::TESObjectWEAP* a_weapon)
	{
		GunInfo info{};
		return GunOf(a_weapon, info) ? static_cast<std::int32_t>(info.interval * 1000.0f + 0.5f) : 0;
	}

	// Milliseconds a reload takes
	std::int32_t GunReloadMs(RE::StaticFunctionTag*, RE::TESObjectWEAP* a_weapon)
	{
		GunInfo info{};
		return GunOf(a_weapon, info) ? static_cast<std::int32_t>(info.reload * 1000.0f + 0.5f) : 0;
	}

	// The player's shot: launched on the game's own thread, a frame later (a Papyrus call may not touch the world from the script thread).
	bool FireGun(RE::StaticFunctionTag*, RE::Actor* a_shooter, float a_right, float a_up, float a_forward, float a_spreadMult)
	{
		if (!a_shooter) {
			return false;
		}
		const auto shooter = a_shooter->GetFormID();
		RunOnGameThread([=]() { Launch(shooter, 0, a_right, a_up, a_forward, a_spreadMult); });
		return true;
	}

	bool RegisterPapyrus(RE::BSScript::IVirtualMachine* a_vm)
	{
		a_vm->RegisterFunction("Version"sv, "SkylandsNative"sv, Version);
		a_vm->RegisterFunction("SetGunMode"sv, "SkylandsNative"sv, SetGunMode);
		a_vm->RegisterFunction("TriggerHeld"sv, "SkylandsNative"sv, TriggerHeld);
		a_vm->RegisterFunction("TriggerPressed"sv, "SkylandsNative"sv, TriggerPressed);
		a_vm->RegisterFunction("GunClip"sv, "SkylandsNative"sv, GunClip);
		a_vm->RegisterFunction("GunIntervalMs"sv, "SkylandsNative"sv, GunIntervalMs);
		a_vm->RegisterFunction("GunReloadMs"sv, "SkylandsNative"sv, GunReloadMs);
		a_vm->RegisterFunction("FireGun"sv, "SkylandsNative"sv, FireGun);
		return true;
	}

	void OnMessage(SKSE::MessagingInterface::Message* a_message)
	{
		if (a_message->type == SKSE::MessagingInterface::kDataLoaded) {
			AttackHook::Install();
			if (const auto holder = RE::ScriptEventSourceHolder::GetSingleton()) {
				holder->AddEventSink(CastSink::Get());
				SKSE::log::info("enemy cast listener registered");
			}
		}
		if (a_message->type == SKSE::MessagingInterface::kInputLoaded) {
			if (const auto input = RE::BSInputDeviceManager::GetSingleton()) {
				input->AddEventSink(InputSink::Get());
				SKSE::log::info("attack button listener registered");
			}
		}
	}

	void StartLog()
	{
		auto path = SKSE::log::log_directory();
		if (!path) {
			return;
		}
		*path /= "SkylandsNative.log";
		auto sink = std::make_shared<spdlog::sinks::basic_file_sink_mt>(path->string(), true);
		auto log = std::make_shared<spdlog::logger>("SkylandsNative", std::move(sink));
		log->set_level(spdlog::level::info);
		log->flush_on(spdlog::level::info);
		spdlog::set_default_logger(std::move(log));
	}
}

SKSEPluginInfo(
	.Version = { 1, 2, 0, 0 },
	.Name = "SkylandsNative"sv,
	.Author = "Skylands"sv)

SKSE_PLUGIN_LOAD(const SKSE::LoadInterface* a_skse)
{
	SKSE::Init(a_skse);
	StartLog();
	SKSE::log::info("SkylandsNative {} loading", kVersion);
	SKSE::log::info("Skyrim runtime {} ({})", REL::Module::get().version().string("."),
		REL::Module::IsVR() ? "VR" : REL::Module::IsAE() ? "Anniversary Edition lineage" : "Special Edition");
	LoadConfig();
	SKSE::GetPapyrusInterface()->Register(RegisterPapyrus);
	SKSE::GetMessagingInterface()->RegisterListener(OnMessage);
	return true;
}
