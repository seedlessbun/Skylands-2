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
	constexpr std::int32_t kVersion = 170;  // 1.7.0

	std::atomic_bool g_held{ false };
	std::atomic_bool g_gunMode{ false };  // a Skylands gun is in the hand: the attack button is ours, the game's attack handler does not get it
	std::atomic_bool g_reloadLatch{ false };  // the reload key went down (cleared by the tick)
	std::atomic_bool g_aimHeld{ false };  // the aim button ("Left Attack/Block": right mouse by default) is down
	std::atomic_bool g_latch{ false };  // set by a button going down, cleared when Papyrus asks: a tap shorter than a poll is still seen

	bool  g_flash = true;  // a short glowing flash at the muzzle with every bullet (ini: MuzzleFlash=0 turns it off)
	int           g_startAmmo = 300;  // rounds of its ammo a player with none is given when a gun is taken up, once per run of the game (ini: StartAmmo)
	bool          g_ammoDrops = true;  // enemies that die with a gun carry some of its ammo (ini: AmmoDrops=0 turns it off)
	std::uint32_t g_reloadKey = 19;  // keyboard scan code of the reload key (ini: ReloadKey; 19 is R)
	bool          g_ammoText = true;  // short ammo messages on the screen (ini: AmmoText=0 turns them off)
	float g_aimSpread = 0.5f;  // the spread's share while fully aimed (ini: AimSpread)
	float g_aimWalk = 0.7f;   // the walking speed's share while fully aimed (ini: AimWalk)
	float g_aimForward = 30.0f;  // where the muzzle sits when fully aimed: this far ahead of the eye (ini: AimForward)
	float g_aimDown = 6.0f;      // ... this far below it (ini: AimDown)
	float g_aimRight = 0.0f;     // ... and this far to the right (ini: AimRight)
	bool  g_aimCenter = true;    // move the gun to the middle of the screen while aimed (ini: AimCenter=0 turns it off)
	float g_aimRate = 7.0f;   // how fast the aim comes up and down, in whole aims a second (ini: AimRate)
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
			if (key == "MuzzleFlash") {
				g_flash = line.substr(eq + 1).find('0') == std::string::npos;
			} else if (key == "AimSpread" || key == "AimWalk" || key == "AimRate") {
				try {
					const float v = std::stof(line.substr(eq + 1));
					(key == "AimSpread" ? g_aimSpread : key == "AimWalk" ? g_aimWalk : g_aimRate) = std::clamp(v, key == "AimRate" ? 1.0f : 0.1f, key == "AimRate" ? 30.0f : 1.0f);
				} catch (...) {
				}
			} else if (key == "AimForward" || key == "AimDown" || key == "AimRight") {
				try {
					const float v = std::stof(line.substr(eq + 1));
					(key == "AimForward" ? g_aimForward : key == "AimDown" ? g_aimDown : g_aimRight) = std::clamp(v, -60.0f, 120.0f);
				} catch (...) {
				}
			} else if (key == "ReloadKey") {
				try {
					g_reloadKey = static_cast<std::uint32_t>(std::clamp(std::stoi(line.substr(eq + 1)), 1, 255));
				} catch (...) {
				}
			} else if (key == "StartAmmo") {
				try {
					g_startAmmo = std::clamp(std::stoi(line.substr(eq + 1)), 0, 100000);
				} catch (...) {
				}
			} else if (key == "AmmoDrops") {
				g_ammoDrops = line.substr(eq + 1).find('0') == std::string::npos;
			} else if (key == "AmmoText") {
				g_ammoText = line.substr(eq + 1).find('0') == std::string::npos;
			} else if (key == "AimCenter") {
				g_aimCenter = line.substr(eq + 1).find('0') == std::string::npos;
			} else if (key == "Convergence") {
				try {
					g_convergence = (std::max)(200.0f, std::stof(line.substr(eq + 1)));
				} catch (...) {
				}
			}
		}
	}

	// Is this button event the attack button? By its user event name, or, when the name is missing (the game may not name the
	// events of controls that are switched off), by the key the player has mapped to "Right Attack/Block" on that device.
	bool IsAction(const RE::ButtonEvent* a_button, const RE::BSFixedString& a_name)
	{
		if (a_button->QUserEvent() == a_name) {
			return true;
		}
		if (!a_button->QUserEvent().empty()) {
			return false;
		}
		const auto map = RE::ControlMap::GetSingleton();
		return map && map->GetMappedKey(a_name.c_str(), a_button->GetDevice()) == a_button->GetIDCode();
	}

	bool IsAttack(const RE::ButtonEvent* a_button, const RE::UserEvents* a_events)
	{
		return IsAction(a_button, a_events->rightAttack);
	}

	// "Left Attack/Block": the aim button while a gun is in the hand
	bool IsAim(const RE::ButtonEvent* a_button, const RE::UserEvents* a_events)
	{
		return IsAction(a_button, a_events->leftAttack);
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
				if (!button) {
					continue;
				}
				if (button->GetDevice() == RE::INPUT_DEVICE::kKeyboard && button->GetIDCode() == g_reloadKey) {
					if (button->IsDown()) {
						g_reloadLatch = true;
					}
					continue;
				}
				if (IsAim(button, events)) {
					g_aimHeld = button->IsPressed();
					continue;
				}
				if (!IsAttack(button, events)) {
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
			if (g_gunMode.load() && a_event && (IsAttack(a_event, RE::UserEvents::GetSingleton()) || IsAim(a_event, RE::UserEvents::GetSingleton()))) {
				return;  // the right button fires (the plugin), the left one aims (the plugin): neither blocks, bashes nor casts
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

	// R is also "Ready Weapon" (draw or put away): while a gun is in the hand the reload key is not given to that handler, so a reload does not holster the gun
	struct ReadyHook
	{
		static void Thunk(RE::ReadyWeaponHandler* a_this, RE::ButtonEvent* a_event, RE::PlayerControlsData* a_data)
		{
			if (g_gunMode.load() && a_event && a_event->GetDevice() == RE::INPUT_DEVICE::kKeyboard && a_event->GetIDCode() == g_reloadKey) {
				return;
			}
			Original(a_this, a_event, a_data);
		}

		static bool Install()
		{
			REL::Relocation<std::uintptr_t> vtbl{ RE::VTABLE_ReadyWeaponHandler[0] };
			const std::size_t slot = REL::Module::IsAtLeast(SKSE::RUNTIME_SSE_1_7_99) ? 0x06 : 0x04;
			Original = vtbl.write_vfunc(slot, Thunk);
			SKSE::log::info("ready-weapon handler hooked (vtable slot {})", slot);
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
		int   element{ 0 };      // 0 none, 1 fire, 2 shock, 3 corrosive, 4 slag (the colour of the muzzle flash)
		int   flash{ 100 };      // the size of the muzzle flash in percent (the flash mesh's file name carries it)
		int   zoom{ 10 };        // the magnification when aimed, in tenths (13 is 1.3x)
		std::uint32_t ammo{ 0 };  // the form id (without its file) of the item this gun uses as ammo; 0: none, the reserve is unlimited
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
					case 'e': info.element = value; break;
					case 'f': info.flash = value; break;
					case 'z': info.zoom = value; break;
					case 'm': info.ammo = static_cast<std::uint32_t>(value); break;
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

	// A short glowing flash where the bullet leaves, spawned by the plugin itself (a temporary effect of our own flash mesh that the game removes after
	// its lifetime). The projectile record's own muzzle-flash feature crashed the game on the first shot (0.17.0).
	void SpawnFlash(RE::Actor* a_shooter, const RE::NiPoint3& a_at, float a_pitch, float a_heading, int a_element, int a_percent)
	{
		if (!g_flash || !a_shooter) {
			return;
		}
		static const char* const names[] = { "plain", "fire", "shock", "corrosive", "slag" };
		const auto cell = a_shooter->GetParentCell();
		if (!cell) {
			return;
		}
		RE::NiMatrix3 rotation;
		rotation.SetEulerAnglesXYZ(a_pitch, 0.0f, a_heading);
		const std::string model = std::string("Skylands\\Flash_Staff_") + names[std::clamp(a_element, 0, 4)] + "_" + std::to_string(a_percent) + ".nif";
		static std::atomic_int spawned{ 0 };
		const bool tell = spawned.fetch_add(1) < 3;
		if (tell) {
			SKSE::log::info("muzzle flash: spawning {}", model);
		}
		RE::BSTempEffectParticle::Spawn(cell, 0.06f, model.c_str(), rotation, a_at, 1.0f, 0, nullptr);
		if (tell) {
			SKSE::log::info("muzzle flash: spawned");
		}
	}

	// Launches the held gun's bullet. The player's bullets cross the crosshair (a_target null); an enemy's go at a_target's chest.
	// right, up and forward move the start in the view's own axes; spreadMult scales the gun's spread (the player's accuracy relics).
	bool Launch(RE::FormID a_shooter, RE::FormID a_targetId, float a_right, float a_up, float a_forward, float a_spreadMult, RE::NiPoint3* a_originOut = nullptr)
	{
		const auto shooter = RE::TESForm::LookupByID<RE::Actor>(a_shooter);
		GunInfo    info{};
		const auto weapon = HeldGun(shooter, info);
		if (!weapon || shooter->IsDead()) {
			return false;
		}
		const auto spell = weapon->formEnchanting;
		if (!spell->GetAVEffect() || !spell->GetAVEffect()->data.projectileBase) {
			SKSE::log::warn("gun {:08X}: its enchantment has no projectile", weapon->GetFormID());
			return false;
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
		static std::atomic_int launches{ 0 };
		const bool tell = launches.fetch_add(1) < 3;  // the first launches are told before and after, so a crash inside the game's launch shows in the log
		if (tell) {
			SKSE::log::info("launching {:08X}'s bullet (projectile {:08X}) from {:.0f} {:.0f} {:.0f}", a_shooter,
				spell->GetAVEffect()->data.projectileBase->GetFormID(), origin.x, origin.y, origin.z);
		}
		RE::Projectile::Launch(&handle, data);
		if (tell) {
			SKSE::log::info("launched");
		}
		if (a_originOut) {
			*a_originOut = origin;
		}
		// the flash sits on the muzzle itself: the bullet starts a_forward ahead of it, and the flash is moved back past that (and a little more, since
		// the mesh begins a hair in front of its origin), so there is no gap between the barrel and the flash
		const float back = a_forward + 5.0f;
		SpawnFlash(shooter, { origin.x - aim.x * back, origin.y - aim.y * back, origin.z - aim.z * back }, pitch, heading, info.element, info.flash);
		return true;
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
	// The ammo of a gun: an item of the same plugin as the gun's enchantment (the guns themselves are overrides of the main plugin's weapons), found from the
	// number in the gun's keyword. The plugin is light (FE...) while its forms fit, else an ordinary one.
	RE::TESBoundObject* AmmoOf(RE::TESObjectWEAP* a_weapon, const GunInfo& a_info)
	{
		if (!a_info.ammo || !a_weapon || !a_weapon->formEnchanting) {
			return nullptr;
		}
		const RE::FormID ench = a_weapon->formEnchanting->GetFormID();
		const RE::FormID id = (ench >> 24) == 0xFE ? ((ench & 0xFFFFF000u) | (a_info.ammo & 0xFFFu)) : ((ench & 0xFF000000u) | (a_info.ammo & 0xFFFFFFu));
		return RE::TESForm::LookupByID<RE::TESBoundObject>(id);
	}

	int CountOf(RE::TESObjectREFR* a_who, RE::TESBoundObject* a_item)
	{
		if (!a_who || !a_item) {
			return 0;
		}
		const auto counts = a_who->GetInventoryCounts();
		const auto it = counts.find(a_item);
		return it == counts.end() ? 0 : it->second;
	}

	// Ammo on the bodies of enemies: one that dies holding a Skylands gun carries some of that gun's ammo (and a body killed by the player may carry some for
	// either type), so what the player spends can be found again.
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
			static RE::FormID last = 0;
			if (!g_ammoDrops || !a_event || !a_event->actorDying) {
				return RE::BSEventNotifyControl::kContinue;
			}
			const auto dying = a_event->actorDying->As<RE::Actor>();
			if (!dying || dying->IsPlayerRef() || dying->GetFormID() == last) {
				return RE::BSEventNotifyControl::kContinue;
			}
			last = dying->GetFormID();
			static thread_local std::mt19937 rng{ std::random_device{}() };
			GunInfo    info{};
			const auto weapon = HeldGun(dying, info);
			if (const auto ammo = AmmoOf(weapon, info)) {
				const int count = std::uniform_int_distribution<int>(10, 30)(rng);
				dying->AddObjectToContainer(ammo, nullptr, count, nullptr);
				static std::atomic_int told{ 0 };
				if (told.fetch_add(1) < 4) {
					SKSE::log::info("ammo drop: {:08X} carries {} of {:08X}", dying->GetFormID(), count, ammo->GetFormID());
				}
			}
			return RE::BSEventNotifyControl::kContinue;
		}
	};

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

	// ---- the player's automatic fire -----------------------------------------------------------------------------------
	//
	// The firing loop lives here, not in a Papyrus script: a Papyrus Utility.Wait in a loop took about twice the time it was asked to (the rate
	// measured in 0.17.0 was about half the set one). A small thread asks the game thread for a tick every few milliseconds; the tick, while a
	// Skylands gun is in the hand ("gun mode"), looks at the trigger, fires rounds when they are due by the clock, counts the magazine (kept
	// per gun), reloads, sets the charge bar and plays the shot sound. The player's relics are the actor values Variable06 (fire rate),
	// Variable07 (reload speed) and Variable08 (accuracy), each a percentage; they are read at every shot.

	using Clock = std::chrono::steady_clock;

	constexpr float kChargePerShot = 100.0f;
	constexpr float kOffsetForward = 12.0f;  // where the bullet starts, ahead of the muzzle node along the aim (game units)

	struct PlayerGun
	{
		RE::FormID            weapon{ 0 };
		GunInfo               info{};
		int                   mag{ 0 };
		bool                  reloading{ false };
		Clock::time_point     nextShot{};
		Clock::time_point     reloadUntil{};
		Clock::time_point     reloadStart{};
		int                   reloadPart{ 3 };  // the next part of the reload sound to play (3: all played)
		bool                  chambered{ false };  // a reload started with rounds left keeps one in the chamber
		bool                  lowTold{ false };
		RE::TESBoundObject*   ammo{ nullptr };  // the held gun's ammo item (null: unlimited)
		Clock::time_point     dryUntil{};       // no new "out of ammo" before this
		Clock::time_point     holdStart{};
		int                   holdShots{ 0 };
		bool                  wasHeld{ false };
		std::unordered_map<RE::FormID, int> mags;  // rounds left in each gun that was put away
	};

	PlayerGun                g_gun;
	std::atomic_bool         g_tickQueued{ false };
	std::atomic_int          g_mag{ 0 };
	std::atomic_int          g_shots{ 0 };
	std::atomic_bool         g_reloading{ false };
	std::atomic_int          g_rateTenths{ 0 };      // the rate the gun is set to, relics included, in tenths of a round a second
	std::atomic_int          g_measuredTenths{ 0 };  // the rate actually fired since the trigger went down
	std::atomic_int          g_reloadMs{ 0 };
	std::atomic_int          g_spreadNowTenths{ 0 };
	std::atomic<RE::FormID>  g_shotSound{ 0 };
	std::atomic<RE::FormID>  g_reloadSound[3]{ 0, 0, 0 };  // the three parts of a reload: magazine out, magazine in, gun made ready

	// ---- aiming down sights ----------------------------------------------------------------------------------------
	//
	// While the aim button is held with a gun in the hand the view zooms (the world field of view, and the game's own setting it is read from
	// every frame), the spread narrows and walking slows; all of it eases in and out and is put back exactly when the aim ends, the gun goes
	// away or the game is left.

	struct AimState
	{
		float             blend{ 0.0f };  // 0 not aimed, 1 fully aimed
		bool              on{ false };
		float             baseFov{ 0.0f };
		float             baseWalk{ 0.0f };
		float             walkApplied{ 0.0f };  // what has been taken off the walking speed so far (put back exactly at the end)
		Clock::time_point last{};
		RE::NiPointer<RE::NiAVObject> gun;      // the first-person weapon's root node (a child of the hand's WEAPON node), moved while aimed
		RE::NiPoint3      gunBase{};            // its own local position, put back at the end
		RE::NiMatrix3     gunBaseRot{};         // ... and its own local rotation
		bool              centerTold{ false };
	};
	AimState g_aim;

	float AimFactor()  // the share of the spread now
	{
		return 1.0f + (g_aimSpread - 1.0f) * g_aim.blend;
	}

	void SetFov(float a_degrees)
	{
		if (const auto setting = RE::GetINISetting("fDefaultWorldFOV:Display")) {
			setting->data.f = a_degrees;
		}
		if (const auto camera = RE::PlayerCamera::GetSingleton()) {
			camera->GetRuntimeData2().worldFOV = a_degrees;
		}
	}

	RE::NiPoint3 MulT(const RE::NiMatrix3& m, const RE::NiPoint3& v)  // the transpose of m times v (a world offset in the node's own axes)
	{
		return { m.entry[0][0] * v.x + m.entry[1][0] * v.y + m.entry[2][0] * v.z, m.entry[0][1] * v.x + m.entry[1][1] * v.y + m.entry[2][1] * v.z,
			m.entry[0][2] * v.x + m.entry[1][2] * v.y + m.entry[2][2] * v.z };
	}

	RE::NiPoint3 Mul(const RE::NiMatrix3& m, const RE::NiPoint3& v)
	{
		return { m.entry[0][0] * v.x + m.entry[0][1] * v.y + m.entry[0][2] * v.z, m.entry[1][0] * v.x + m.entry[1][1] * v.y + m.entry[1][2] * v.z,
			m.entry[2][0] * v.x + m.entry[2][1] * v.y + m.entry[2][2] * v.z };
	}

	RE::NiMatrix3 MatMul(const RE::NiMatrix3& a, const RE::NiMatrix3& b)
	{
		RE::NiMatrix3 r{};
		for (int i = 0; i < 3; ++i) {
			for (int j = 0; j < 3; ++j) {
				r.entry[i][j] = a.entry[i][0] * b.entry[0][j] + a.entry[i][1] * b.entry[1][j] + a.entry[i][2] * b.entry[2][j];
			}
		}
		return r;
	}

	RE::NiMatrix3 Transposed(const RE::NiMatrix3& m)
	{
		RE::NiMatrix3 r{};
		for (int i = 0; i < 3; ++i) {
			for (int j = 0; j < 3; ++j) {
				r.entry[i][j] = m.entry[j][i];
			}
		}
		return r;
	}

	// The rotation by `angle` radians about the unit vector `a`
	RE::NiMatrix3 Turn(const Vec3& a, float angle)
	{
		const float c = std::cos(angle), sn = std::sin(angle), t = 1.0f - c;
		RE::NiMatrix3 r{};
		r.entry[0][0] = c + t * a.x * a.x;       r.entry[0][1] = t * a.x * a.y - sn * a.z; r.entry[0][2] = t * a.x * a.z + sn * a.y;
		r.entry[1][0] = t * a.x * a.y + sn * a.z; r.entry[1][1] = c + t * a.y * a.y;       r.entry[1][2] = t * a.y * a.z - sn * a.x;
		r.entry[2][0] = t * a.x * a.z - sn * a.y; r.entry[2][1] = t * a.y * a.z + sn * a.x; r.entry[2][2] = c + t * a.z * a.z;
		return r;
	}

	// The first-person gun is moved so its muzzle sits just below the crosshair, ahead of the eye (the hand's animation still drives the arm; only the weapon's
	// own node moves, from its place in the hand to the place in front of the camera, by blend). The muzzle's place in the weapon's own axes does not change when
	// the weapon is moved, so the node's new local position is worked out from the hand's (unmoved) transform: no step depends on the last one.
	void CenterGun(RE::PlayerCharacter* a_player, bool a_start)
	{
		const auto camera = RE::PlayerCamera::GetSingleton();
		if (!g_aimCenter || !camera || !camera->IsInFirstPerson()) {
			return;
		}
		const auto root3d = a_player->Get3D(true);
		const auto muzzle = root3d ? root3d->GetObjectByName("SkylandsMuzzle"sv) : nullptr;
		if (!muzzle) {
			return;
		}
		if (a_start || !g_aim.gun) {
			RE::NiAVObject* node = muzzle;
			for (int i = 0; i < 10 && node && node->parent; ++i, node = node->parent) {
				if (std::string_view(node->parent->name.c_str()) == "WEAPON") {
					g_aim.gun.reset(node);
					g_aim.gunBase = node->local.translate;
					g_aim.gunBaseRot = node->local.rotate;
					break;
				}
			}
			if (!g_aim.centerTold) {
				g_aim.centerTold = true;
				SKSE::log::info("aim: weapon node {} (centring the gun while aimed)", g_aim.gun ? g_aim.gun->name.c_str() : "NOT FOUND, the gun stays where it is");
			}
		}
		const auto gun = g_aim.gun.get();
		if (!gun || !gun->parent) {
			return;
		}
		// the view: the camera node itself (the eye vector is the head's, which is not quite the camera), its forward axis found as the one of its
		// three axes that points along the look direction
		RE::NiPoint3 eye{}, look{};
		a_player->GetEyeVector(eye, look, true);
		Vec3         dir = Norm({ look.x, look.y, look.z });
		RE::NiPoint3 origin = eye;
		if (const auto& cam = camera->cameraRoot) {
			origin = cam->world.translate;
			int   best = 0;
			float bestDot = 0.0f;
			for (int c = 0; c < 3; ++c) {
				const float d = cam->world.rotate.entry[0][c] * dir.x + cam->world.rotate.entry[1][c] * dir.y + cam->world.rotate.entry[2][c] * dir.z;
				if (std::fabs(d) > std::fabs(bestDot)) {
					best = c;
					bestDot = d;
				}
			}
			const float sign = bestDot < 0.0f ? -1.0f : 1.0f;
			dir = Norm({ sign * cam->world.rotate.entry[0][best], sign * cam->world.rotate.entry[1][best], sign * cam->world.rotate.entry[2][best] });
			static bool told = false;
			if (!told) {
				told = true;
				SKSE::log::info("aim: camera at {:.0f} {:.0f} {:.0f} (eye {:.0f} {:.0f} {:.0f}), forward axis {} (agreement {:.3f})", origin.x, origin.y, origin.z, eye.x, eye.y, eye.z, best,
					std::fabs(bestDot));
			}
		}
		const Vec3 right = Norm(Cross(dir, { 0.0f, 0.0f, 1.0f }));
		const Vec3 up = Cross(right, dir);
		const float b = g_aim.blend;
		const RE::NiPoint3 target{ origin.x + dir.x * g_aimForward + right.x * g_aimRight - up.x * g_aimDown,
			origin.y + dir.y * g_aimForward + right.y * g_aimRight - up.y * g_aimDown, origin.z + dir.z * g_aimForward + right.z * g_aimRight - up.z * g_aimDown };
		const auto&        parent = gun->parent->world;
		const float        ps = parent.scale > 1e-4f ? parent.scale : 1.0f;
		const float        scale = gun->world.scale > 1e-4f ? gun->world.scale : 1.0f;
		// the muzzle in the weapon's own axes (this does not change when the weapon is moved or turned)
		const RE::NiPoint3 offset{ muzzle->world.translate.x - gun->world.translate.x, muzzle->world.translate.y - gun->world.translate.y,
			muzzle->world.translate.z - gun->world.translate.z };
		const RE::NiPoint3 rel = MulT(gun->world.rotate, { offset.x / scale, offset.y / scale, offset.z / scale });
		// where the weapon would point at rest (from the hand, not from where it was last put), and the turn that makes the barrel (root to muzzle) point along the view
		const RE::NiMatrix3 baseWorld = MatMul(parent.rotate, g_aim.gunBaseRot);
		const RE::NiPoint3  barrel = Mul(baseWorld, rel);
		const Vec3          from = Norm({ barrel.x, barrel.y, barrel.z });
		const float         dot = std::clamp(from.x * dir.x + from.y * dir.y + from.z * dir.z, -1.0f, 1.0f);
		const Vec3          axis = Cross(from, dir);
		const float         axisLen = std::sqrt(axis.x * axis.x + axis.y * axis.y + axis.z * axis.z);
		RE::NiMatrix3       world = baseWorld;
		if (axisLen > 1e-5f) {
			world = MatMul(Turn({ axis.x / axisLen, axis.y / axisLen, axis.z / axisLen }, std::acos(dot) * b), baseWorld);
		}
		const RE::NiPoint3 back = Mul(world, { rel.x * scale, rel.y * scale, rel.z * scale });
		const RE::NiPoint3 rootWorld{ target.x - back.x, target.y - back.y, target.z - back.z };
		const RE::NiPoint3 local = MulT(parent.rotate, { (rootWorld.x - parent.translate.x) / ps, (rootWorld.y - parent.translate.y) / ps, (rootWorld.z - parent.translate.z) / ps });
		gun->local.translate = { g_aim.gunBase.x + (local.x - g_aim.gunBase.x) * b, g_aim.gunBase.y + (local.y - g_aim.gunBase.y) * b,
			g_aim.gunBase.z + (local.z - g_aim.gunBase.z) * b };
		gun->local.rotate = MatMul(Transposed(parent.rotate), world);
	}

	void ReleaseAim(RE::PlayerCharacter* a_player)
	{
		if (!g_aim.on) {
			return;
		}
		g_aim.on = false;
		g_aim.blend = 0.0f;
		SetFov(g_aim.baseFov);
		if (a_player && g_aim.walkApplied != 0.0f) {
			a_player->AsActorValueOwner()->ModActorValue(RE::ACTOR_VALUE_MODIFIER::kTemporary, RE::ActorValue::kSpeedMult, g_aim.walkApplied);  // walkApplied is what was taken off: give it back
		}
		g_aim.walkApplied = 0.0f;
		if (g_aim.gun) {
			g_aim.gun->local.translate = g_aim.gunBase;
			g_aim.gun->local.rotate = g_aim.gunBaseRot;
			g_aim.gun.reset();
		}
		SKSE::log::info("aim ended: field of view back to {:.1f}, walking speed back to {:.0f}", g_aim.baseFov, g_aim.baseWalk);
	}

	void UpdateAim(RE::PlayerCharacter* a_player, const GunInfo& a_info, Clock::time_point a_now)
	{
		const bool want = g_aimHeld.load() && a_info.zoom > 10;
		if (!g_aim.on && !want) {
			return;
		}
		if (!g_aim.on) {
			const auto setting = RE::GetINISetting("fDefaultWorldFOV:Display");
			const auto camera = RE::PlayerCamera::GetSingleton();
			g_aim.baseFov = setting ? setting->data.f : (camera ? camera->GetRuntimeData2().worldFOV : 65.0f);
			g_aim.baseWalk = a_player->AsActorValueOwner()->GetActorValue(RE::ActorValue::kSpeedMult);
			g_aim.walkApplied = 0.0f;
			g_aim.on = true;
			CenterGun(a_player, true);
			g_aim.last = a_now;
			SKSE::log::info("aim started: {:.1f}x from field of view {:.1f}, walking speed {:.0f}", a_info.zoom / 10.0f, g_aim.baseFov, g_aim.baseWalk);
		}
		const float dt = std::clamp(std::chrono::duration<float>(a_now - g_aim.last).count(), 0.0f, 0.1f);
		g_aim.last = a_now;
		g_aim.blend = std::clamp(g_aim.blend + (want ? 1.0f : -1.0f) * g_aimRate * dt, 0.0f, 1.0f);
		if (!want && g_aim.blend <= 0.0f) {
			ReleaseAim(a_player);
			return;
		}
		const float zoom = 1.0f + (a_info.zoom / 10.0f - 1.0f) * g_aim.blend;
		const float half = std::tan(g_aim.baseFov * 0.5f * std::numbers::pi_v<float> / 180.0f) / zoom;
		SetFov(2.0f * std::atan(half) * 180.0f / std::numbers::pi_v<float>);
		const float taken = g_aim.baseWalk * (1.0f - g_aimWalk) * g_aim.blend;  // taken off the walking speed (added back exactly by ReleaseAim)
		if (taken != g_aim.walkApplied) {
			a_player->AsActorValueOwner()->ModActorValue(RE::ACTOR_VALUE_MODIFIER::kTemporary, RE::ActorValue::kSpeedMult, g_aim.walkApplied - taken);  // more taken: negative
			g_aim.walkApplied = taken;
		}
		CenterGun(a_player, false);
	}

	// A relic bonus in percent as a divisor: 0 is 1.0, 50 is 1.5; never below 0.2
	float Relic(RE::PlayerCharacter* a_player, RE::ActorValue a_value)
	{
		const float percent = a_player->AsActorValueOwner()->GetActorValue(a_value);
		return (std::max)(0.2f, 1.0f + percent * 0.01f);
	}

	void SetBar(RE::PlayerCharacter* a_player, int a_mag)
	{
		g_mag = a_mag;
		a_player->AsActorValueOwner()->SetActorValue(RE::ActorValue::kRightItemCharge, static_cast<float>(a_mag) * kChargePerShot);
	}

	void PlaySound(RE::FormID id, const RE::NiPoint3& a_at)
	{
		if (!id) {
			return;
		}
		const auto form = RE::TESForm::LookupByID<RE::BGSSoundDescriptorForm>(id);
		const auto manager = RE::BSAudioManager::GetSingleton();
		static std::atomic_int told{ 0 };
		if (told.fetch_add(1) < 8) {
			SKSE::log::info("playing sound {:08X}: form {}, audio manager {}", id, form ? "found" : "missing", manager ? "found" : "missing");
		}
		if (!form || !manager) {
			return;
		}
		RE::BSSoundHandle handle;
		const bool built = manager->GetSoundHandle(handle, form);  // the form is itself a BSISoundDescriptor (it forwards to its soundDescriptor)
		handle.SetPosition(a_at);
		const bool played = handle.Play();
		if (told.load() <= 8) {
			SKSE::log::info("sound {:08X}: handle built {}, valid {}, play {}", id, built, handle.IsValid(), played);
		}
	}

	void PlayShot(const RE::NiPoint3& a_at) { PlaySound(g_shotSound.load(), a_at); }

	// A reload begins: its three sounds are played at fixed shares of the time it takes (the magazine out at once, the new one in at about half,
	// the gun made ready near the end).
	void AmmoText(const std::string& a_text)
	{
		if (g_ammoText) {
			RE::SendHUDMessage::ShowHUDMessage(a_text.c_str(), nullptr, true);
		}
	}

	void BeginReload(Clock::time_point a_now, int a_ms)
	{
		g_gun.reloading = true;
		g_gun.reloadStart = a_now;
		AmmoText("Reloading...");
		g_gun.reloadUntil = a_now + std::chrono::milliseconds(a_ms);
		g_gun.reloadPart = 0;
	}

	// A reload, if there is ammo for it (a_key: the player asked for it, so the answer is always given)
	bool TryReload(RE::PlayerCharacter* a_player, Clock::time_point a_now, int a_ms, bool a_key)
	{
		if (!a_key && a_now < g_gun.dryUntil) {
			return false;
		}
		if (g_gun.ammo && CountOf(a_player, g_gun.ammo) <= 0) {
			AmmoText("Out of ammo");
			g_gun.dryUntil = a_now + std::chrono::milliseconds(1500);
			return false;
		}
		BeginReload(a_now, a_ms);
		return true;
	}

	void ReloadSounds(RE::PlayerCharacter* a_player, Clock::time_point a_now)
	{
		static constexpr float share[3] = { 0.02f, 0.45f, 0.86f };
		const double total = std::chrono::duration<double>(g_gun.reloadUntil - g_gun.reloadStart).count();
		const double passed = std::chrono::duration<double>(a_now - g_gun.reloadStart).count();
		while (g_gun.reloadPart < 3 && passed >= total * share[g_gun.reloadPart]) {
			const auto id = g_reloadSound[g_gun.reloadPart].load();
			static std::atomic_int told{ 0 };
			if (told.fetch_add(1) < 6) {
				SKSE::log::info("reload sound part {}: {:08X}", g_gun.reloadPart, id);
			}
			PlaySound(id, a_player->GetPosition());
			++g_gun.reloadPart;
		}
	}

	void Tick()
	{
		const auto player = RE::PlayerCharacter::GetSingleton();
		if (!g_gunMode.load() || !player || !player->Is3DLoaded() || MenuOpen()) {
			g_gun.wasHeld = false;
			if (!g_gunMode.load() && player) {
				ReleaseAim(player);
			}
			return;
		}
		GunInfo    info{};
		const auto weapon = HeldGun(player, info);
		if (!weapon) {
			g_gun.wasHeld = false;
			ReleaseAim(player);
			return;
		}
		const auto now = Clock::now();
		if (weapon->GetFormID() != g_gun.weapon) {  // another gun than before: its numbers, and the rounds it had (a fresh one is full)
			if (g_gun.weapon) {
				g_gun.mags[g_gun.weapon] = g_gun.mag;
			}
			g_gun.weapon = weapon->GetFormID();
			g_gun.info = info;
			const auto kept = g_gun.mags.find(g_gun.weapon);
			g_gun.mag = kept != g_gun.mags.end() ? kept->second : info.clip;
			g_gun.reloading = false;
			g_gun.reloadPart = 3;
			g_gun.ammo = AmmoOf(weapon, info);
			if (g_gun.ammo && g_startAmmo > 0 && CountOf(player, g_gun.ammo) <= 0) {  // none of its ammo: a first stock, once for each kind in a run of the game
				static std::unordered_map<RE::FormID, bool> given;
				if (!given[g_gun.ammo->GetFormID()]) {
					given[g_gun.ammo->GetFormID()] = true;
					player->AddObjectToContainer(g_gun.ammo, nullptr, g_startAmmo, nullptr);
					SKSE::log::info("ammo: {} of {:08X} given to a player with none", g_startAmmo, g_gun.ammo->GetFormID());
				}
			}
			if (g_gun.mag <= 0) {
				TryReload(player, now, static_cast<int>(info.reload * 1000.0f), false);
			}
			g_gun.nextShot = now;
			g_gun.wasHeld = false;
			SetBar(player, g_gun.mag);
			SKSE::log::info("player gun {:08X}: magazine {} of {}, interval {:.3f}, reload {:.1f}, spread {:.1f}", g_gun.weapon, g_gun.mag, info.clip,
				info.interval, info.reload, info.spread);
		}
		const float rate = Relic(player, RE::ActorValue::kVariable06);
		const float quick = Relic(player, RE::ActorValue::kVariable07);
		const float accuracy = Relic(player, RE::ActorValue::kVariable08);
		const float gap = g_gun.info.interval / rate;
		g_rateTenths = static_cast<int>(10.0f / gap + 0.5f);
		g_reloadMs = static_cast<int>(g_gun.info.reload / quick * 1000.0f + 0.5f);
		UpdateAim(player, g_gun.info, now);
		g_spreadNowTenths = static_cast<int>(g_gun.info.spread / accuracy * AimFactor() * 10.0f + 0.5f);

		if (g_gun.reloading) {
			g_reloading = true;
			ReloadSounds(player, now);
			if (now >= g_gun.reloadUntil) {
				g_gun.reloading = false;
				const int want = g_gun.info.clip + (g_gun.chambered ? 1 : 0) - g_gun.mag;
				int       got = want;
				int       left = -1;
				if (g_gun.ammo) {  // the rounds come out of the player's ammo (a short stock gives a short magazine)
					got = (std::min)(want, CountOf(player, g_gun.ammo));
					if (got > 0) {
						player->RemoveItem(g_gun.ammo, got, RE::ITEM_REMOVE_REASON::kRemove, nullptr, nullptr);
					}
					left = CountOf(player, g_gun.ammo);
				}
				g_gun.mag += (std::max)(0, got);
				g_gun.chambered = false;
				g_gun.lowTold = false;
				AmmoText("Magazine " + std::to_string(g_gun.mag) + " / " + std::to_string(g_gun.info.clip) + (left >= 0 ? "   Ammo " + std::to_string(left) : std::string()));
				SetBar(player, g_gun.mag);
				g_reloading = false;
			}
			return;
		}
		g_reloading = false;
		if (g_reloadLatch.exchange(false) && g_gun.mag < g_gun.info.clip) {  // the reload key: a reload now (a round stays chambered if there is one left)
			g_gun.chambered = g_gun.mag > 0;
			g_gun.wasHeld = false;
			if (TryReload(player, now, g_reloadMs.load(), true)) {
				g_reloading = true;
				SKSE::log::info("reload key: reload started with {} of {} rounds left", g_gun.mag, g_gun.info.clip);
				ReloadSounds(player, now);
				return;
			}
			g_gun.chambered = false;
		}
		if (!g_held.load()) {
			g_gun.wasHeld = false;
			return;
		}
		if (!g_gun.wasHeld) {  // the trigger went down
			g_gun.wasHeld = true;
			g_gun.holdStart = now;
			g_gun.holdShots = 0;
			if (g_gun.nextShot > now + std::chrono::milliseconds(static_cast<int>(gap * 1000.0f))) {
				g_gun.nextShot = now;
			}
		}
		int fired = 0;
		const auto step = std::chrono::microseconds(static_cast<long long>(gap * 1000000.0f));
		while (now >= g_gun.nextShot && g_gun.mag > 0 && fired < 3) {
			RE::NiPoint3 at{};
			if (!Launch(player->GetFormID(), 0, 0.0f, 0.0f, kOffsetForward, AimFactor() / accuracy, &at)) {
				break;
			}
			PlayShot(at);
			--g_gun.mag;
			++g_gun.holdShots;
			++fired;
			++g_shots;
			g_gun.nextShot = (now - g_gun.nextShot > step * 3) ? now + step : g_gun.nextShot + step;
		}
		if (fired) {
			SetBar(player, g_gun.mag);
			if (!g_gun.lowTold && g_gun.mag > 0 && g_gun.mag * 4 <= g_gun.info.clip) {  // a quarter left
				g_gun.lowTold = true;
				AmmoText("Low ammo: " + std::to_string(g_gun.mag) + " / " + std::to_string(g_gun.info.clip));
			}
			const double seconds = std::chrono::duration<double>(now - g_gun.holdStart).count();
			g_measuredTenths = (g_gun.holdShots >= 3 && seconds >= 0.3) ? static_cast<int>((g_gun.holdShots - 1) / seconds * 10.0 + 0.5) : 0;
		}
		if (g_gun.mag <= 0 && TryReload(player, now, g_reloadMs.load(), false)) {
			g_reloading = true;
			ReloadSounds(player, now);
		}
	}

	// A thread asks for a tick a few milliseconds apart (the game thread runs it once the task queue comes round, a frame at a time; a tick still
	// waiting is not asked for again).
	void StartPump()
	{
		static std::atomic_bool started{ false };
		if (started.exchange(true)) {
			return;
		}
		std::thread([]() {
			for (;;) {
				std::this_thread::sleep_for(std::chrono::milliseconds(4));
				if (!g_gunMode.load() || g_tickQueued.exchange(true)) {
					continue;
				}
				RunOnGameThread([]() {
					Tick();
					g_tickQueued = false;
				});
			}
		}).detach();
		SKSE::log::info("automatic fire: tick thread started");
	}

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

	// The gun's base spread in tenths of a degree (before any relic bonus)
	std::int32_t GunSpreadTenths(RE::StaticFunctionTag*, RE::TESObjectWEAP* a_weapon)
	{
		GunInfo info{};
		return GunOf(a_weapon, info) ? static_cast<std::int32_t>(info.spread * 10.0f + 0.5f) : 0;
	}

	// What the player's gun is doing (the plugin fires it; Papyrus only shows it)
	std::int32_t Magazine(RE::StaticFunctionTag*) { return g_mag.load(); }
	std::int32_t ShotsFired(RE::StaticFunctionTag*) { return g_shots.load(); }
	bool         Reloading(RE::StaticFunctionTag*) { return g_reloading.load(); }
	std::int32_t RateTenths(RE::StaticFunctionTag*) { return g_rateTenths.load(); }
	std::int32_t MeasuredTenths(RE::StaticFunctionTag*) { return g_measuredTenths.load(); }
	std::int32_t ReloadMsNow(RE::StaticFunctionTag*) { return g_reloadMs.load(); }
	std::int32_t SpreadNowTenths(RE::StaticFunctionTag*) { return g_spreadNowTenths.load(); }

	// The sound the gun in the hand makes at every shot (a Sound the script picked for the gun); none to be silent
	bool SetShotSound(RE::StaticFunctionTag*, RE::TESForm* a_sound)
	{
		g_shotSound = a_sound ? a_sound->GetFormID() : 0;
		static std::atomic_int told{ 0 };
		if (told.fetch_add(1) < 6) {
			SKSE::log::info("shot sound set: {:08X}", g_shotSound.load());
		}
		return true;
	}

	// The sounds of a reload (the magazine out, a new one in, the gun made ready); none to be silent
	bool SetReloadSounds(RE::StaticFunctionTag*, RE::TESForm* a_out, RE::TESForm* a_in, RE::TESForm* a_end)
	{
		g_reloadSound[0] = a_out ? a_out->GetFormID() : 0;
		g_reloadSound[1] = a_in ? a_in->GetFormID() : 0;
		g_reloadSound[2] = a_end ? a_end->GetFormID() : 0;
		static std::atomic_int told{ 0 };
		if (told.fetch_add(1) < 6) {
			SKSE::log::info("reload sounds set: out {:08X}, in {:08X}, end {:08X}", g_reloadSound[0].load(), g_reloadSound[1].load(), g_reloadSound[2].load());
		}
		return true;
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
		a_vm->RegisterFunction("GunSpreadTenths"sv, "SkylandsNative"sv, GunSpreadTenths);
		a_vm->RegisterFunction("FireGun"sv, "SkylandsNative"sv, FireGun);
		a_vm->RegisterFunction("Magazine"sv, "SkylandsNative"sv, Magazine);
		a_vm->RegisterFunction("ShotsFired"sv, "SkylandsNative"sv, ShotsFired);
		a_vm->RegisterFunction("Reloading"sv, "SkylandsNative"sv, Reloading);
		a_vm->RegisterFunction("RateTenths"sv, "SkylandsNative"sv, RateTenths);
		a_vm->RegisterFunction("MeasuredTenths"sv, "SkylandsNative"sv, MeasuredTenths);
		a_vm->RegisterFunction("ReloadMsNow"sv, "SkylandsNative"sv, ReloadMsNow);
		a_vm->RegisterFunction("SpreadNowTenths"sv, "SkylandsNative"sv, SpreadNowTenths);
		a_vm->RegisterFunction("SetShotSound"sv, "SkylandsNative"sv, SetShotSound);
		a_vm->RegisterFunction("SetReloadSounds"sv, "SkylandsNative"sv, SetReloadSounds);
		return true;
	}

	void OnMessage(SKSE::MessagingInterface::Message* a_message)
	{
		if (a_message->type == SKSE::MessagingInterface::kDataLoaded) {
			AttackHook::Install();
			ReadyHook::Install();
			StartPump();
			if (const auto holder = RE::ScriptEventSourceHolder::GetSingleton()) {
				holder->AddEventSink(CastSink::Get());
				SKSE::log::info("enemy cast listener registered");
				holder->AddEventSink(DeathSink::Get());
				SKSE::log::info("ammo drop listener registered");
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
	.Version = { 1, 7, 0, 0 },
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
