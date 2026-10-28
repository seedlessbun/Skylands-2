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
	constexpr std::int32_t kVersion = 280;  // 1.14.4

	std::atomic_bool g_held{ false };
	std::atomic_bool g_gunMode{ false };  // a Skylands gun is in the hand: the attack button is ours, the game's attack handler does not get it
	std::atomic_bool g_reloadLatch{ false };  // the reload key went down (cleared by the tick)
	std::atomic_bool g_aimHeld{ false };  // the aim button ("Left Attack/Block": right mouse by default) is down
	std::atomic_bool g_latch{ false };  // set by a button going down, cleared when Papyrus asks: a tap shorter than a poll is still seen

	bool  g_flash = true;  // a short glowing flash at the muzzle with every bullet (ini: MuzzleFlash=0 turns it off)
	std::atomic<const char*> g_stage{ "start" };  // where the plugin last was (told by the crash handler)
	bool          g_aimPredict = true;   // the aimed gun is placed from the player's own position and angles of this frame, not the camera's of the last (ini: AimPredict=0 turns it off)
	int           g_reloadMouse = -1;    // a mouse button (3, 4, 5, ... the side buttons) as the reload key as well; -1 none (ini: ReloadMouse)
	bool          g_hud = true;          // the Borderlands-style ammo display, drawn into the game's HUD (ini: Hud=0 turns it off and brings the plain messages back)
	std::atomic_bool g_hudLive{ false };  // the display has been drawn at least once: the plain messages stay quiet
	std::atomic_bool g_hudShow{ false };  // a gun is in the hand and the game is running: the display is shown
	float         g_hudRight = 70.0f;    // the display's right edge, this far from the right of the 1280 x 720 HUD (ini: HudRight)
	float         g_hudBottom = 80.0f;   // ... and its bottom line, this far from the bottom (ini: HudBottom)
	int           g_startAmmo = 300;  // rounds of its ammo a player with none is given when a gun is taken up, once per run of the game (ini: StartAmmo)
	bool          g_ammoDrops = true;  // enemies that die with a gun carry some of its ammo (ini: AmmoDrops=0 turns it off)
	std::uint32_t g_reloadKey = 47;  // keyboard scan code of the reload key (ini: ReloadKey; 19 is R)
	bool          g_ammoText = true;  // short ammo messages on the screen (ini: AmmoText=0 turns them off)
	float g_aimSpread = 0.5f;  // the spread's share while fully aimed (ini: AimSpread)
	float g_aimWalk = 0.7f;   // the walking speed's share while fully aimed (ini: AimWalk)
	float g_aimForward = 33.0f;  // where the muzzle sits when fully aimed: this far ahead of the eye (ini: AimForward)
	float g_aimDown = 6.5f;      // ... this far below it (ini: AimDown)
	float g_aimRight = 0.0f;     // ... and this far to the right (ini: AimRight)
	bool  g_aimCenter = true;    // move the gun to the middle of the screen while aimed (ini: AimCenter=0 turns it off)
	float g_aimRate = 7.0f;   // how fast the aim comes up and down, in whole aims a second (ini: AimRate)
	float g_convergence = 3000.0f;  // how far ahead the bullets are aimed to cross the crosshair (game units)
	float g_recoilPitch = 0.55f;   // degrees the view kicks up with a shot at the reference fire rate (ini: RecoilPitch; 0 = no recoil)
	float g_recoilYaw = 0.22f;     // ... and at most this far sideways, either way (ini: RecoilYaw)
	float g_recoilRecover = 0.6f;  // the share of the kick the view comes back down by once the shooting stops (ini: RecoilRecover)
	float g_recoilAim = 0.6f;      // the kick's share while fully aimed (ini: RecoilAim)
	float g_recoilGun = 1.0f;      // how far the aimed gun model jerks back with a shot, in units, at the reference rate (ini: RecoilGun)
	bool  g_hideHands = true;      // the arms are hidden while fully aimed, so only the gun is in front of the view (ini: HideHands=0 turns it off)
	bool  g_fxRocket = true;       // a rocket's exhaust trail and the back-blast of its launcher (ini: Rockets=0 turns them off)
	bool  g_fxCasing = true;       // shell casings fly out of the gun (ini: Casings=0 turns them off)
	float g_sway = 1.0f;           // the aimed gun's sway (breathing, walking, turning) as a multiple of the default; 0 = none (ini: Sway)

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
			} else if (key == "AimPredict") {
				g_aimPredict = line.substr(eq + 1).find('0') == std::string::npos;
			} else if (key == "ReloadMouse") {
				try {
					g_reloadMouse = std::clamp(std::stoi(line.substr(eq + 1)), -1, 9);
				} catch (...) {
				}
			} else if (key == "Hud") {
				g_hud = line.substr(eq + 1).find('0') == std::string::npos;
			} else if (key == "HudRight" || key == "HudBottom") {
				try {
					(key == "HudRight" ? g_hudRight : g_hudBottom) = std::clamp(std::stof(line.substr(eq + 1)), 0.0f, 600.0f);
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
			} else if (key == "RecoilPitch" || key == "RecoilYaw" || key == "RecoilRecover" || key == "RecoilAim" || key == "RecoilGun" || key == "Sway") {
				try {
					const float v = std::clamp(std::stof(line.substr(eq + 1)), 0.0f, key == "RecoilRecover" || key == "RecoilAim" ? 1.0f : 10.0f);
					(key == "RecoilPitch" ? g_recoilPitch : key == "RecoilYaw" ? g_recoilYaw : key == "RecoilRecover" ? g_recoilRecover : key == "RecoilAim" ? g_recoilAim : key == "RecoilGun" ? g_recoilGun : g_sway) = v;
				} catch (...) {
				}
			} else if (key == "HideHands" || key == "Casings" || key == "Rockets") {
				const bool on = line.substr(eq + 1).find('0') == std::string::npos;
				(key == "HideHands" ? g_hideHands : key == "Casings" ? g_fxCasing : g_fxRocket) = on;
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
				if ((button->GetDevice() == RE::INPUT_DEVICE::kKeyboard && button->GetIDCode() == g_reloadKey) ||
					(g_reloadMouse >= 0 && button->GetDevice() == RE::INPUT_DEVICE::kMouse &&
						(static_cast<int>(button->GetIDCode()) == g_reloadMouse || static_cast<int>(button->GetIDCode()) == 256 + g_reloadMouse))) {
					if (button->IsDown()) {
						g_reloadLatch = true;
					}
					continue;
				}
				if (button->GetDevice() != RE::INPUT_DEVICE::kKeyboard && button->IsDown()) {  // what the mouse and pad buttons send (the first thirty), to see which code a side button has
					static std::atomic_int told{ 0 };
					if (told.fetch_add(1) < 30) {
						SKSE::log::info("button down: device {} code {} event name '{}'", static_cast<int>(button->GetDevice()), static_cast<int>(button->GetIDCode()), button->QUserEvent().c_str());
					}
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
		std::uint32_t sndOwn{ 0 }, sndVanilla{ 0 };  // the shot sound: this plugin's record (local id, 0 none) and the vanilla stand-in (full id, 0 none); an enemy's shots are played from these
		int   pellets{ 1 };      // bullets in one shot (a shotgun's pellets)
		int   trail{ 0 };        // a rocket's exhaust look: 0 none (not a rocket), 1 flame and thin smoke, 2 heavy smoke, 3 sparks
		int   zoom{ 10 };        // the magnification when aimed, in tenths (13 is 1.3x)
		int   rarity{ 0 };       // 1 common ... 6 e-tech (the colour of its name on the display)
		std::uint32_t ammo{ 0 };  // the form id (without its file) of the item this gun uses as ammo; 0: none, the reserve is unlimited
	};

	std::vector<std::uint32_t> g_ammoLocals;  // the form ids (without the file) of every ammo item of the set, read from the SkylandsAmmos_ keyword of a gun
	RE::FormID                 g_ammoEnch = 0;  // the enchantment of a gun it was read from: it tells which file the ammo items are in

	// a record of this plugin from its local id, given the id of another record of it (the gun's enchantment): the plugin may or may not be a light one
	RE::FormID ResolveLocal(RE::FormID a_sibling, std::uint32_t a_local)
	{
		return (a_sibling >> 24) == 0xFE ? ((a_sibling & 0xFFFFF000u) | (a_local & 0xFFFu)) : ((a_sibling & 0xFF000000u) | (a_local & 0xFFFFFFu));
	}

	void PlaySound(RE::FormID id, const RE::NiPoint3& a_at);  // below

	std::mutex                                     g_gunLock;
	std::unordered_map<RE::FormID, GunInfo>        g_guns;

	// The numbers of a gun weapon from its keywords; false when it is not a Skylands staff gun.
	RE::FormID ShotSoundOf(RE::TESObjectWEAP* a_weapon, const GunInfo& a_info)
	{
		if (a_info.sndOwn && a_weapon && a_weapon->formEnchanting) {
			return ResolveLocal(a_weapon->formEnchanting->GetFormID(), a_info.sndOwn);
		}
		return a_info.sndVanilla;
	}

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
			if (edid.starts_with("SkylandsAmmos_") && g_ammoLocals.empty() && a_weapon->formEnchanting) {
				std::size_t at = 14;
				while (at < edid.size()) {
					const auto end = edid.find('_', at);
					const std::string_view part = edid.substr(at, end == std::string_view::npos ? std::string_view::npos : end - at);
					if (!part.empty()) {
						g_ammoLocals.push_back(static_cast<std::uint32_t>(std::strtoul(std::string(part).c_str(), nullptr, 10)));
					}
					if (end == std::string_view::npos) {
						break;
					}
					at = end + 1;
				}
				g_ammoEnch = a_weapon->formEnchanting->GetFormID();
				SKSE::log::info("ammo set: {} items read from {}", g_ammoLocals.size(), edid);
			}
			if (names.size() < 300) {
				names += std::string(edid) + " ";
			}
			if (edid.starts_with("SkylandsRarity_")) {
				const std::string_view r = edid.substr(15);
				info.rarity = r == "common" ? 1 : r == "uncommon" ? 2 : r == "rare" ? 3 : r == "epic" ? 4 : r == "legendary" ? 5 : r == "etech" ? 6 : 0;
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
					case 'p': info.pellets = std::clamp(value, 1, 24); break;
					case 'o': info.sndOwn = static_cast<std::uint32_t>(value); break;
					case 'v': info.sndVanilla = static_cast<std::uint32_t>(value); break;
					case 't': info.trail = std::clamp(value, 0, 3); break;
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
	// The player's flash follows the gun: it is spawned again every tick for a short while (each one living about a frame) at the muzzle node's place of that tick.
	struct FlashFollow
	{
		std::chrono::steady_clock::time_point until{};
		int                                   element{ 0 }, percent{ 100 };
	} g_flashFollow;

	void SpawnFlash(RE::Actor* a_shooter, const RE::NiPoint3& a_at, float a_pitch, float a_heading, int a_element, int a_percent, float a_life = 0.06f)
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
		RE::BSTempEffectParticle::Spawn(cell, a_life, model.c_str(), rotation, a_at, 1.0f, 0, nullptr);
		if (tell) {
			SKSE::log::info("muzzle flash: spawned");
		}
	}

	void EmitShotFx(RE::PlayerCharacter* a_player, int a_trail);
	void TrackRocket(const RE::ProjectileHandle& a_handle, const RE::NiPoint3& a_from, int a_trail);

	// Launches the held gun's bullet. The player's bullets cross the crosshair (a_target null); an enemy's go at a_target's chest.
	// right, up and forward move the start in the view's own axes; spreadMult scales the gun's spread (the player's accuracy relics).
	bool Launch(RE::FormID a_shooter, RE::FormID a_targetId, float a_right, float a_up, float a_forward, float a_spreadMult, RE::NiPoint3* a_originOut = nullptr, int a_pellets = -1)
	{
		g_stage = "launch";
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

		// the spread: a random direction inside a cone (an enemy's is twice the player's); a shotgun's pellets each take their own direction in it
		const float spread = info.spread * (npc ? 2.0f : (std::max)(0.0f, a_spreadMult));  // relics may tighten the player's spread
		static std::atomic_int launches{ 0 };
		const bool tell = launches.fetch_add(1) < 3;  // the first launches are told before and after, so a crash inside the game's launch shows in the log
		static thread_local std::mt19937 rng{ std::random_device{}() };
		std::uniform_real_distribution<float> unit(0.0f, 1.0f);
		for (int pellet = 0; pellet < (a_pellets > 0 ? a_pellets : (std::max)(1, info.pellets)); ++pellet) {
			float aimPitch = pitch, aimHeading = heading;
			if (spread > 0.0f) {
				const float radius = spread * std::numbers::pi_v<float> / 180.0f * std::sqrt(unit(rng));
				const float angle = 2.0f * std::numbers::pi_v<float> * unit(rng);
				aimPitch += radius * std::sin(angle);
				aimHeading += radius * std::cos(angle);
			}
			RE::Projectile::LaunchData data(shooter, origin, { aimPitch, aimHeading }, spell);
			data.castingSource = RE::MagicSystem::CastingSource::kRightHand;
			RE::ProjectileHandle handle{};
			if (tell && pellet == 0) {
				SKSE::log::info("launching {:08X}'s bullet (projectile {:08X}) from {:.0f} {:.0f} {:.0f}, {} pellet(s)", a_shooter,
					spell->GetAVEffect()->data.projectileBase->GetFormID(), origin.x, origin.y, origin.z, info.pellets);
			}
			RE::Projectile::Launch(&handle, data);
			if (tell && pellet == 0) {
				SKSE::log::info("launched");
			}
			if (info.trail > 0) {
				TrackRocket(handle, origin, info.trail);
			}
		}
		if (npc && a_pellets < 0) {  // an enemy's shot is heard (the player's is played by the tick)
			PlaySound(ShotSoundOf(weapon, info), origin);
		}
		if (a_originOut) {
			*a_originOut = origin;
		}
		// the flash sits on the muzzle itself: the bullet starts a_forward ahead of it, and the flash is moved back past that (and a little more, since
		// the mesh begins a hair in front of its origin), so there is no gap between the barrel and the flash
		if (npc) {
			const float back = a_forward + 5.0f;
			SpawnFlash(shooter, { origin.x - aim.x * back, origin.y - aim.y * back, origin.z - aim.z * back }, pitch, heading, info.element, info.flash);
		} else {  // the player's flash is drawn by FollowFlash from the next tick on, glued to the muzzle node
			g_flashFollow = { std::chrono::steady_clock::now() + std::chrono::milliseconds(60), info.element, info.flash };
			EmitShotFx(RE::PlayerCharacter::GetSingleton(), info.trail);
		}
		return true;
	}

	// While the player's flash is alive: a flash of about one frame at the muzzle node's place now, along the barrel (muzzle minus breech), 15% of the barrel's length
	// away from where it used to sit (it sat a little inside the barrel's end).
	void FollowFlash(RE::PlayerCharacter* a_player, std::chrono::steady_clock::time_point a_now)
	{
		if (!g_flash || a_now >= g_flashFollow.until) {
			return;
		}
		g_stage = "muzzle flash follow";
		const auto camera = RE::PlayerCamera::GetSingleton();
		const auto root = a_player->Get3D(camera && camera->IsInFirstPerson());
		const auto muzzle = root ? root->GetObjectByName("SkylandsMuzzle"sv) : nullptr;
		if (!muzzle) {
			return;
		}
		Vec3  dir{ 0.0f, 1.0f, 0.0f };
		float length = 50.0f;
		if (const auto breech = root->GetObjectByName("SkylandsBreech"sv)) {
			const Vec3 d{ muzzle->world.translate.x - breech->world.translate.x, muzzle->world.translate.y - breech->world.translate.y, muzzle->world.translate.z - breech->world.translate.z };
			length = std::sqrt(d.x * d.x + d.y * d.y + d.z * d.z);
			dir = Norm(d);
		} else {
			RE::NiPoint3 eye{}, look{};
			a_player->GetEyeVector(eye, look, true);
			dir = Norm({ look.x, look.y, look.z });
		}
		const float push = 0.15f * length - 5.0f;
		const RE::NiPoint3 at{ muzzle->world.translate.x + dir.x * push, muzzle->world.translate.y + dir.y * push, muzzle->world.translate.z + dir.z * push };
		SpawnFlash(a_player, at, -std::asin(std::clamp(dir.z, -1.0f, 1.0f)), std::atan2(dir.x, dir.y), g_flashFollow.element, g_flashFollow.percent, 0.03f);
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
			g_stage = "death event";
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
			std::vector<std::pair<RE::FormID, int>> loot;  // what the body will carry: the ammo of its gun, and sometimes a few of any other kind
			if (const auto ammo = AmmoOf(weapon, info)) {
				loot.emplace_back(ammo->GetFormID(), std::uniform_int_distribution<int>(10, 30)(rng));
			}
			const auto race = dying->GetRace();
			if (!g_ammoLocals.empty() && race && race->HasKeywordString("ActorTypeNPC") && std::uniform_int_distribution<int>(1, 100)(rng) <= (weapon ? 30 : 60)) {
				const std::uint32_t local = g_ammoLocals[std::uniform_int_distribution<std::size_t>(0, g_ammoLocals.size() - 1)(rng)];
				const RE::FormID    id = (g_ammoEnch >> 24) == 0xFE ? ((g_ammoEnch & 0xFFFFF000u) | (local & 0xFFFu)) : ((g_ammoEnch & 0xFF000000u) | (local & 0xFFFFFFu));
				loot.emplace_back(id, std::uniform_int_distribution<int>(6, 20)(rng));
			}
			if (!loot.empty()) {
				// not inside the death event (changing a body's pack while the game is still killing it is a known way to crash): a moment later, from the game thread,
				// looking the body up again
				const RE::FormID body = dying->GetFormID();
				std::thread([body, loot]() {
					std::this_thread::sleep_for(std::chrono::milliseconds(800));
					RunOnGameThread([body, loot]() {
						g_stage = "ammo drop";
						const auto actor = RE::TESForm::LookupByID<RE::Actor>(body);
						if (!actor || !actor->IsDead()) {
							return;
						}
						for (const auto& [item, count] : loot) {
							const auto what = RE::TESForm::LookupByID<RE::TESBoundObject>(item);
							if (!what) {
								continue;
							}
							actor->AddObjectToContainer(what, nullptr, count, nullptr);
							static std::atomic_int told{ 0 };
							if (told.fetch_add(1) < 6) {
								SKSE::log::info("ammo drop: {:08X} carries {} of {:08X}", body, count, item);
							}
						}
					});
				}).detach();
			}
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	// The game reports a two-handed (staff-type) weapon in BOTH hand slots of an actor whose pack holds ONE copy; that is not what makes the second gun
	// people see on an enemy (unequipping it did not hold). Looked at from the model instead: every copy of the gun's mesh in the actor's 3D is found by its
	// SkylandsMuzzle node and the chain of nodes up to the actor is logged; a copy that hangs under the LEFT hand is hidden.
	void CollectNamed(RE::NiAVObject* a_obj, std::string_view a_name, std::vector<RE::NiAVObject*>& a_out, int a_depth = 0)
	{
		if (!a_obj || a_depth > 80 || a_out.size() > 8) {
			return;
		}
		if (const char* n = a_obj->name.c_str(); n && a_name == n) {
			a_out.push_back(a_obj);
		}
		if (const auto node = a_obj->AsNode()) {
			for (auto& child : node->GetChildren()) {
				CollectNamed(child.get(), a_name, a_out, a_depth + 1);
			}
		}
	}

	void OneGunOnly(RE::FormID a_actorId)
	{
		static std::mutex                                                   lock;
		static std::unordered_map<RE::FormID, std::chrono::steady_clock::time_point> last;
		{
			const std::lock_guard guard(lock);
			const auto            now = std::chrono::steady_clock::now();
			auto&                 at  = last[a_actorId];
			if (now - at < std::chrono::seconds(3)) {
				return;
			}
			at = now;
		}
		RunOnGameThread([a_actorId]() {
			const auto who = RE::TESForm::LookupByID<RE::Actor>(a_actorId);
			if (!who || who->IsDead() || !who->Is3DLoaded()) {
				return;
			}
			const auto root = who->Get3D(false);
			if (!root) {
				return;
			}
			std::vector<RE::NiAVObject*> muzzles;
			CollectNamed(root, "SkylandsMuzzle"sv, muzzles);
			static std::atomic_int told{ 0 };
			const bool             tell = told.fetch_add(1) < 16;
			if (tell) {
				const auto right = who->GetEquippedObject(false);
				const auto left  = who->GetEquippedObject(true);
				SKSE::log::info("enemy {:08X}: hands hold {:08X} (right) and {:08X} (left); {} gun model(s) in its 3D", a_actorId,
					right ? right->GetFormID() : 0, left ? left->GetFormID() : 0, muzzles.size());
			}
			for (const auto muzzle : muzzles) {
				std::string  chain;
				RE::NiAVObject* weaponRoot = nullptr;  // the node just below the hand's attach point
				bool         underLeft     = false;
				RE::NiAVObject* previous   = muzzle;
				for (auto up = muzzle->parent; up; previous = up, up = up->parent) {
					const std::string name = up->name.c_str() ? up->name.c_str() : "";
					chain += (chain.empty() ? "" : " < ") + name;
					if (name.find("L Hand") != std::string::npos || name == "SHIELD") {
						underLeft = true;
						if (!weaponRoot) {
							weaponRoot = previous;
						}
					}
					if (name.find("R Hand") != std::string::npos || name == "WEAPON") {
						break;
					}
					if (chain.size() > 600) {
						break;
					}
				}
				if (tell) {
					SKSE::log::info("  gun model under {}: {}", underLeft ? "the LEFT hand" : "another node", chain.substr(0, 400));
				}
				if (underLeft && weaponRoot && !weaponRoot->GetFlags().any(RE::NiAVObject::Flag::kHidden)) {
					weaponRoot->SetAppCulled(true);
					if (tell) {
						SKSE::log::info("  hid the left-hand copy ({})", weaponRoot->name.c_str() ? weaponRoot->name.c_str() : "?");
					}
				}
			}
		});
	}

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
			g_stage = "enemy cast event";
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
			if (!ours) {
				return RE::BSEventNotifyControl::kContinue;
			}
			OneGunOnly(actor->GetFormID());
			const RE::FormID shooter = actor->GetFormID();
			{  // the game's own cast sends the first bullet: its sound is played here, at the actor's chest height a little ahead
				RE::NiPoint3 at = actor->GetPosition();
				at.z += actor->GetHeight() * 0.8f;
				PlaySound(ShotSoundOf(weapon, info), at);
			}
			if (info.pellets > 1) {  // the game's own cast sent one pellet: the rest of the shot's pellets follow it at once
				const int rest = info.pellets - 1;
				RunOnGameThread([shooter, rest]() {
					const auto who = RE::TESForm::LookupByID<RE::Actor>(shooter);
					if (!who || who->IsDead() || !who->Is3DLoaded()) {
						return;
					}
					const auto target = who->GetActorRuntimeData().currentCombatTarget.get();
					Launch(shooter, target ? target->GetFormID() : 0, 0.0f, 0.0f, 0.0f, 1.0f, nullptr, rest);
				});
			}
			if (info.burst < 2) {
				return RE::BSEventNotifyControl::kContinue;
			}
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
		std::string           name;                 // the gun's name and the colour of its rarity, shown for a moment when it is taken up
		const char*           rarityColor{ "#FFFFFF" };
		Clock::time_point     nameUntil{};
		int                   reserve{ -1 };        // rounds of its ammo in the pack (-1: no ammo item, unlimited), looked at about once a second
		Clock::time_point     reserveAt{};
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
		float             gunBaseScale{ 1.0f };
		RE::NiPointer<RE::NiNode> hand;         // where the weapon node belongs (the hand's WEAPON node); while aimed it hangs under the first-person root instead
		RE::NiPointer<RE::NiNode> root;
		RE::NiPoint3      startT{};             // the gun's place and turn in the root's axes when the aim began
		RE::NiMatrix3     startRot{};
		bool              centerTold{ false };
		std::vector<RE::NiPointer<RE::NiAVObject>> hidden;  // the arm geometry switched off while aimed (switched on again when the aim ends)
		struct View
		{
			bool         have{ false }, haveRest{ false };
			RE::NiPoint3 camSeen{}, lastActor{}, offset{}, rest{ 0.0f, 0.0f, 120.0f };  // rest: where the camera node sits against the player's position
		} view;
	};
	AimState g_aim;

	float AimFactor()  // the share of the spread now
	{
		return 1.0f + (g_aimSpread - 1.0f) * g_aim.blend;
	}

	// ---- recoil and sway ------------------------------------------------------------------------------------------------
	// Every shot kicks the view up (and a little sideways): the kick is applied to the player's angles within a few hundredths of a second, and
	// once the shooting has stopped part of it (RecoilRecover) is given back, so the aim ends up a little higher. The aimed gun model jerks
	// back with each shot, and sways: breathing when still, a bob when walking, and a lag behind turns of the view.
	struct KickState
	{
		float                pendPitch{ 0.0f }, pendYaw{ 0.0f }, owedPitch{ 0.0f }, gunBack{ 0.0f };  // degrees waiting to be applied, degrees to give back, units
		float                swayRight{ 0.0f }, swayUp{ 0.0f }, turnYaw{ 0.0f }, turnPitch{ 0.0f }, speed{ 0.0f }, phase{ 0.0f }, lastYaw{ 0.0f }, lastPitch{ 0.0f };
		float                clock{ 0.0f };
		RE::NiPoint3         lastPos{};
		bool                 have{ false }, told{ false };
		Clock::time_point    lastShot{}, lastFrame{};
	} g_kick;

	void ResetKick()
	{
		g_kick.pendPitch = g_kick.pendYaw = g_kick.owedPitch = g_kick.gunBack = 0.0f;
		g_kick.swayRight = g_kick.swayUp = g_kick.turnYaw = g_kick.turnPitch = g_kick.speed = 0.0f;
		g_kick.have = false;
	}

	float Rand01()
	{
		static std::uint32_t s = 2463534242u;
		s ^= s << 13;
		s ^= s >> 17;
		s ^= s << 5;
		return static_cast<float>(s & 0xFFFFFF) / 16777216.0f;
	}

	void AddKick(const GunInfo& a_info, Clock::time_point a_now)
	{
		const float rateF = std::clamp(std::sqrt(a_info.interval / 0.12f), 0.7f, 1.6f);  // a slower gun kicks harder
		const float aim = 1.0f - (1.0f - g_recoilAim) * g_aim.blend;
		const float p = g_recoilPitch * rateF * aim * (0.85f + 0.3f * Rand01());
		g_kick.pendPitch += p;
		g_kick.pendYaw += (Rand01() * 2.0f - 1.0f) * g_recoilYaw * aim;
		g_kick.owedPitch += p * g_recoilRecover;
		g_kick.gunBack = (std::min)(g_kick.gunBack + g_recoilGun * rateF, g_recoilGun * 3.0f);
		g_kick.lastShot = a_now;
	}

	// once a frame, from the tick: applies the kick to the view, gives part of it back, and works out the sway offsets (to the right, up) the aimed gun gets
	void RecoilFrame(RE::PlayerCharacter* a_player, Clock::time_point a_now)
	{
		g_stage = "recoil and sway";
		constexpr float rad = std::numbers::pi_v<float> / 180.0f;
		const float     dt = g_kick.have ? std::clamp(std::chrono::duration<float>(a_now - g_kick.lastFrame).count(), 0.001f, 0.1f) : 0.016f;
		g_kick.lastFrame = a_now;
		float x = a_player->GetAngleX(), z = a_player->GetAngleZ();
		const RE::NiPoint3 pos = a_player->GetPosition();
		float dx = 0.0f, dz = 0.0f;
		const float a = 1.0f - std::exp(-dt / 0.035f);
		dx -= g_kick.pendPitch * a * rad;  // pitch is positive downwards: a kick up lowers it
		dz += g_kick.pendYaw * a * rad;
		g_kick.pendPitch -= g_kick.pendPitch * a;
		g_kick.pendYaw -= g_kick.pendYaw * a;
		if (a_now - g_kick.lastShot > std::chrono::milliseconds(120) && g_kick.owedPitch > 0.0f) {
			const float back = g_kick.owedPitch * (1.0f - std::exp(-dt / 0.2f));
			g_kick.owedPitch -= back;
			dx += back * rad;
		}
		if (g_kick.have && (dx != 0.0f || dz != 0.0f)) {
			const float nx = std::clamp(x + dx, -1.45f, 1.45f);
			float       nz = std::fmod(z + dz, 2.0f * std::numbers::pi_v<float>);
			if (nz < 0.0f) {
				nz += 2.0f * std::numbers::pi_v<float>;
			}
			a_player->data.angle.x = nx;
			a_player->data.angle.z = nz;
			if (!g_kick.told) {
				g_kick.told = true;
				SKSE::log::info("recoil: first kick moved the view pitch {:.3f} -> {:.3f}, heading {:.3f} -> {:.3f} (radians)", x, nx, z, nz);
			}
			x = nx;
			z = nz;
		}
		g_kick.gunBack *= std::exp(-dt / 0.07f);
		// sway
		if (g_kick.have) {
			const float walked = std::sqrt((pos.x - g_kick.lastPos.x) * (pos.x - g_kick.lastPos.x) + (pos.y - g_kick.lastPos.y) * (pos.y - g_kick.lastPos.y)) / dt;
			g_kick.speed += (std::clamp(walked / 400.0f, 0.0f, 1.0f) - g_kick.speed) * (1.0f - std::exp(-dt / 0.15f));
			float dyaw = z - g_kick.lastYaw;
			if (dyaw > std::numbers::pi_v<float>) {
				dyaw -= 2.0f * std::numbers::pi_v<float>;
			} else if (dyaw < -std::numbers::pi_v<float>) {
				dyaw += 2.0f * std::numbers::pi_v<float>;
			}
			const float follow = 1.0f - std::exp(-dt / 0.09f);  // the view's turning speed, smoothed: the gun lags behind it
			g_kick.turnYaw += (std::clamp(dyaw / dt, -8.0f, 8.0f) - g_kick.turnYaw) * follow;
			g_kick.turnPitch += (std::clamp((x - g_kick.lastPitch) / dt, -8.0f, 8.0f) - g_kick.turnPitch) * follow;
		}
		g_kick.lastPos = pos;
		g_kick.lastYaw = z;
		g_kick.lastPitch = x;
		g_kick.have = true;
		g_kick.clock += dt;
		g_kick.phase += dt * (5.5f + 2.5f * g_kick.speed);
		const float t = g_kick.clock;
		const float still = 1.0f - g_kick.speed;
		float       right = std::sin(t * 0.85f) * 0.10f * still + std::sin(g_kick.phase) * 0.30f * g_kick.speed + g_kick.turnYaw * 0.35f;  // turning right: the gun trails to the left
		float       up = std::sin(t * 1.55f + 0.7f) * 0.13f * still - std::fabs(std::sin(g_kick.phase)) * 0.45f * g_kick.speed + g_kick.turnPitch * 0.35f;
		right = std::clamp(right, -1.5f, 1.5f) * g_sway;
		up = std::clamp(up, -1.5f, 1.5f) * g_sway;
		g_kick.swayRight = right;
		g_kick.swayUp = up;
	}

	// ---- shell casings -------------------------------------------------------------------------------------------------
	// Small temporary effects of our own mesh, moved by the plugin: each lives a few hundredths of a second and is spawned again at its new place every
	// 33 ms, so a casing flies in an arc. Nothing is placed in the world (no references, nothing in a save).
	struct Fx
	{
		int          kind{ 0 };  // 0 casing, 1 smoke, 2 flame
		int          look{ 0 };  // the rocket look (0 to 2) for smoke and flame
		RE::NiPoint3 pos{};
		Vec3         vel{ 0.0f, 0.0f, 0.0f };
		float        age{ 0.0f }, life{ 0.6f }, next{ 0.0f }, spin{ 0.0f }, tilt{ 0.0f }, size{ 1.0f };
	};
	std::vector<Fx> g_fx;
	struct Rocket
	{
		RE::ProjectileHandle handle;
		RE::NiPoint3         last{};
		int                  trail{ 1 };
		float                age{ 0.0f }, emit{ 0.0f };
	};
	std::vector<Rocket> g_rockets;

	void TrackRocket(const RE::ProjectileHandle& a_handle, const RE::NiPoint3& a_from, int a_trail)
	{
		if (!g_fxRocket || !a_handle.get() || g_rockets.size() > 24) {
			return;
		}
		g_rockets.push_back({ a_handle, a_from, a_trail, 0.0f, 0.0f });
	}

	float Rand01();

	// the barrel's frame of the player's gun: the muzzle, the direction of the barrel, its top and its side (false when the gun has no marker nodes)
	bool BarrelFrame(RE::PlayerCharacter* a_player, RE::NiPoint3& a_muzzle, RE::NiPoint3& a_breech, Vec3& a_dir, Vec3& a_up, Vec3& a_right, float& a_length)
	{
		const auto camera = RE::PlayerCamera::GetSingleton();
		const auto root = a_player->Get3D(camera && camera->IsInFirstPerson());
		if (!root) {
			return false;
		}
		const auto muzzle = root->GetObjectByName("SkylandsMuzzle"sv);
		const auto breech = root->GetObjectByName("SkylandsBreech"sv);
		const auto top = root->GetObjectByName("SkylandsTop"sv);
		if (!muzzle || !breech || !top) {
			return false;
		}
		a_muzzle = muzzle->world.translate;
		a_breech = breech->world.translate;
		const Vec3 d{ a_muzzle.x - a_breech.x, a_muzzle.y - a_breech.y, a_muzzle.z - a_breech.z };
		a_length = std::sqrt(d.x * d.x + d.y * d.y + d.z * d.z);
		a_dir = Norm(d);
		const Vec3 u{ top->world.translate.x - a_muzzle.x, top->world.translate.y - a_muzzle.y, top->world.translate.z - a_muzzle.z };
		const float k = u.x * a_dir.x + u.y * a_dir.y + u.z * a_dir.z;
		a_up = Norm({ u.x - a_dir.x * k, u.y - a_dir.y * k, u.z - a_dir.z * k });
		a_right = Cross(a_dir, a_up);
		return true;
	}

	// per shot, for the player's gun: a casing out of the ejection side of the receiver
	void EmitShotFx(RE::PlayerCharacter* a_player, int a_trail)
	{
		if (!a_player || g_fx.size() >= 70) {
			return;
		}
		RE::NiPoint3 muzzle{}, breech{};
		Vec3         dir{}, up{}, right{};
		float        length = 0.0f;
		if (!BarrelFrame(a_player, muzzle, breech, dir, up, right, length)) {
			return;
		}
		if (a_trail > 0) {  // a launcher: no casing; a cloud of back-blast smoke instead
			if (!g_fxRocket) {
				return;
			}
			for (int i = 0; i < 5; ++i) {
				Fx p;
				p.kind = 1;
				p.look = a_trail - 1;
				p.pos = { breech.x + dir.x * length * 0.1f, breech.y + dir.y * length * 0.1f, breech.z + dir.z * length * 0.1f };
				p.vel = { -dir.x * (40.0f + Rand01() * 50.0f) + (Rand01() - 0.5f) * 40.0f, -dir.y * (40.0f + Rand01() * 50.0f) + (Rand01() - 0.5f) * 40.0f,
					-dir.z * (40.0f + Rand01() * 50.0f) + 10.0f + Rand01() * 30.0f };
				p.life = 0.9f;
				p.size = 1.4f;
				g_fx.push_back(p);
			}
			return;
		}
		if (!g_fxCasing) {
			return;
		}
		Fx f;
		f.pos = { breech.x + dir.x * length * 0.35f + up.x * 1.5f + right.x * 2.0f, breech.y + dir.y * length * 0.35f + up.y * 1.5f + right.y * 2.0f,
			breech.z + dir.z * length * 0.35f + up.z * 1.5f + right.z * 2.0f };
		const float sideways = 70.0f + Rand01() * 30.0f, lift = 55.0f + Rand01() * 35.0f, back = 5.0f + Rand01() * 20.0f;
		f.vel = { right.x * sideways + up.x * lift - dir.x * back, right.y * sideways + up.y * lift - dir.y * back, right.z * sideways + up.z * lift - dir.z * back };
		f.spin = Rand01() * 6.28f;
		f.tilt = Rand01() * 6.28f;
		g_fx.push_back(f);
	}

	// every tick: the drawing of every live casing
	void FxFrame(RE::PlayerCharacter* a_player, Clock::time_point a_now)
	{
		static Clock::time_point last{};
		const float dt = last.time_since_epoch().count() == 0 ? 0.016f : std::clamp(std::chrono::duration<float>(a_now - last).count(), 0.001f, 0.1f);
		last = a_now;
		if (!a_player || MenuOpen()) {
			return;
		}
		const auto cell = a_player->GetParentCell();
		if (!cell) {
			g_fx.clear();
			return;
		}
		g_stage = "effects";
		// the rockets in flight: an exhaust of flame and smoke is left behind them every few hundredths of a second, as long as the game still holds the projectile
		for (auto it = g_rockets.begin(); it != g_rockets.end();) {
			it->age += dt;
			const auto p = it->handle.get();
			if (!p || p->IsDeleted() || p->IsDisabled() || it->age > 12.0f) {
				it = g_rockets.erase(it);
				continue;
			}
			const RE::NiPoint3 now = p->GetPosition();
			it->emit -= dt;
			if (it->emit <= 0.0f && g_fx.size() < 120) {
				it->emit = 0.03f;
				const Vec3 away = Norm({ it->last.x - now.x, it->last.y - now.y, it->last.z - now.z });
				Fx flame;
				flame.kind = 2;
				flame.look = it->trail - 1;
				flame.pos = now;
				flame.life = it->trail == 3 ? 0.18f : 0.28f;
				flame.size = 1.4f;
				flame.spin = Rand01() * 6.28f;
				g_fx.push_back(flame);
				if (it->trail != 3 || Rand01() < 0.3f) {
					Fx smoke;
					smoke.kind = 1;
					smoke.look = it->trail - 1;
					smoke.pos = { now.x + away.x * 8.0f, now.y + away.y * 8.0f, now.z + away.z * 8.0f };
					smoke.vel = { (Rand01() - 0.5f) * 14.0f, (Rand01() - 0.5f) * 14.0f, 8.0f + Rand01() * 10.0f };
					smoke.life = it->trail == 2 ? 1.6f : 0.9f;
					smoke.size = it->trail == 2 ? 1.5f : 0.9f;
					g_fx.push_back(smoke);
				}
			}
			it->last = now;
			++it;
		}
		static const char* const smokes[] = { "Skylands\\Fx_Smoke_0.nif", "Skylands\\Fx_Smoke_1.nif", "Skylands\\Fx_Smoke_2.nif" };
		static const char* const flames[] = { "Skylands\\Fx_Flame_0.nif", "Skylands\\Fx_Flame_1.nif", "Skylands\\Fx_Flame_2.nif" };
		for (auto it = g_fx.begin(); it != g_fx.end();) {
			Fx& f = *it;
			f.age += dt;
			if (f.age > f.life) {
				it = g_fx.erase(it);
				continue;
			}
			const char* mesh = "Skylands\\Fx_Casing.nif";
			float       scale = 1.0f, step = 0.033f;
			if (f.kind == 0) {
				f.vel.z -= 1300.0f * dt;  // thrown out, falls
				f.spin += 24.0f * dt;
			} else if (f.kind == 1) {  // smoke: slows, rises a little, swells and fades through three strengths
				const float drag = std::exp(-1.6f * dt);
				f.vel = { f.vel.x * drag, f.vel.y * drag, f.vel.z * drag };
				const float share = f.age / f.life;
				mesh = smokes[std::clamp(static_cast<int>(share * 3.0f), 0, 2)];
				scale = f.size * (1.0f + share * 2.2f);
				step = 0.06f;
			} else {  // flame: shrinks as it ages
				mesh = flames[std::clamp(f.look, 0, 2)];
				scale = f.size * (1.0f - 0.7f * f.age / f.life);
				step = 0.04f;
			}
			f.pos = { f.pos.x + f.vel.x * dt, f.pos.y + f.vel.y * dt, f.pos.z + f.vel.z * dt };
			if (f.age >= f.next) {
				f.next = f.age + step;
				RE::NiMatrix3 rotation;
				rotation.SetEulerAnglesXYZ(f.spin, f.tilt, 0.0f);
				RE::BSTempEffectParticle::Spawn(cell, 0.07f, mesh, rotation, f.pos, scale, 0, nullptr);
			}
			++it;
		}
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

	// The aimed gun hangs under the first-person skeleton's ROOT instead of the hand's weapon node (the arm's own animation lags and sways behind the view, and a
	// gun in the hand followed it), and is held straight in front of the view: its barrel along the view, its top up, its muzzle a little ahead of the eye and below
	// the crosshair (ini AimForward / AimDown / AimRight). The three reference nodes of the mesh (SkylandsMuzzle, SkylandsBreech, SkylandsTop) say which way the
	// gun's own barrel and top run; they are constant in the weapon's own axes whatever its place.
	void ShowHands()
	{
		for (auto& g : g_aim.hidden) {
			if (g) {
				g->SetAppCulled(false);
			}
		}
		g_aim.hidden.clear();
	}

	// Everything drawn under the first-person root except the gun itself (the arms, gloves and sleeves) is switched off, so the gun floats alone in front of the view.
	void HideHands(RE::NiNode* a_root, RE::NiAVObject* a_gun)
	{
		std::vector<RE::NiNode*> stack{ a_root };
		while (!stack.empty() && g_aim.hidden.size() < 64) {
			const auto node = stack.back();
			stack.pop_back();
			for (auto& child : node->GetChildren()) {
				if (!child || child.get() == a_gun) {
					continue;
				}
				if (const auto n = child->AsNode()) {
					stack.push_back(n);
				} else if (!child->GetFlags().any(RE::NiAVObject::Flag::kHidden)) {
					child->SetAppCulled(true);
					g_aim.hidden.emplace_back(child.get());
				}
			}
		}
	}

	void RestoreGun()
	{
		g_stage = "aim: gun back to the hand";
		ShowHands();
		if (!g_aim.gun) {
			return;
		}
		if (g_aim.root && g_aim.hand && g_aim.gun->parent == g_aim.root.get()) {
			RE::NiPointer<RE::NiAVObject> keep{ g_aim.gun };
			g_aim.root->DetachChild2(g_aim.gun.get());
			g_aim.hand->AttachChild(keep.get(), true);
		}
		g_aim.gun->local.translate = g_aim.gunBase;
		g_aim.gun->local.rotate = g_aim.gunBaseRot;
		g_aim.gun->local.scale = g_aim.gunBaseScale;
		g_aim.gun.reset();
		g_aim.hand.reset();
		g_aim.root.reset();
	}

	void CenterGun(RE::PlayerCharacter* a_player, bool a_start)
	{
		g_stage = a_start ? "aim: gun moved under the root" : "aim: gun placed";
		const auto camera = RE::PlayerCamera::GetSingleton();
		if (!g_aimCenter || !camera || !camera->IsInFirstPerson()) {
			return;
		}
		const auto root3d = a_player->Get3D(true);
		const auto rootNode = root3d ? root3d->AsNode() : nullptr;
		const auto muzzle = root3d ? root3d->GetObjectByName("SkylandsMuzzle"sv) : nullptr;
		if (!rootNode || !muzzle) {
			return;
		}
		if (a_start || !g_aim.gun) {
			RE::NiAVObject* node = muzzle;
			for (int i = 0; i < 10 && node && node->parent; ++i, node = node->parent) {
				if (std::string_view(node->parent->name.c_str()) == "WEAPON") {
					g_aim.gun.reset(node);
					g_aim.hand.reset(node->parent);
					g_aim.root.reset(rootNode);
					g_aim.gunBase = node->local.translate;
					g_aim.gunBaseRot = node->local.rotate;
					g_aim.gunBaseScale = node->local.scale;
					break;
				}
			}
			if (g_aim.gun) {  // where the gun is now, in the root's axes; then it is moved under the root
				const float rs = rootNode->world.scale > 1e-4f ? rootNode->world.scale : 1.0f;
				const RE::NiPoint3 d{ g_aim.gun->world.translate.x - rootNode->world.translate.x, g_aim.gun->world.translate.y - rootNode->world.translate.y,
					g_aim.gun->world.translate.z - rootNode->world.translate.z };
				g_aim.startT = MulT(rootNode->world.rotate, { d.x / rs, d.y / rs, d.z / rs });
				g_aim.startRot = MatMul(Transposed(rootNode->world.rotate), g_aim.gun->world.rotate);
				const float scaleNow = g_aim.gun->world.scale / rs;
				RE::NiPointer<RE::NiAVObject> keep{ g_aim.gun };
				g_aim.hand->DetachChild2(keep.get());
				rootNode->AttachChild(keep.get(), true);
				g_aim.gun->local.translate = g_aim.startT;
				g_aim.gun->local.rotate = g_aim.startRot;
				g_aim.gun->local.scale = scaleNow;
			}
			if (!g_aim.centerTold) {
				g_aim.centerTold = true;
				SKSE::log::info("aim: weapon node {} {}", g_aim.gun ? g_aim.gun->name.c_str() : "NOT FOUND",
					g_aim.gun ? "(held in front of the view under the first-person root while aimed)" : "(the gun stays where it is)");
			}
			return;  // the first frame only moves the node; its world transform is up to date after the game's next update
		}
		const auto gun = g_aim.gun.get();
		if (!gun || g_aim.root.get() != rootNode) {  // the first-person skeleton is not the one the aim began with (a new 3D): the gun goes back to the hand it came from
			if (g_aim.gun) {
				SKSE::log::info("aim: the first-person 3D changed during the aim; the gun is put back");
				RestoreGun();
			}
			return;
		}
		if (gun->parent != rootNode) {
			return;
		}
		// the view: the camera node itself, its forward axis found as the one of its three axes that points along the look direction
		RE::NiPoint3 eye{}, look{};
		a_player->GetEyeVector(eye, look, true);
		Vec3         dir = Norm({ look.x, look.y, look.z });
		RE::NiPoint3 origin = eye;
		const RE::NiPoint3 actorNow = a_player->GetPosition();
		if (const auto& cam = camera->cameraRoot) {
			origin = cam->world.translate;
			// The camera node is worked out late in the frame, after the plugin's tick: what it holds here is the last frame's. The player's own position and angles are this
			// frame's. So the view is taken as the player's position now plus the camera's offset from the player that was measured when a new camera frame arrived, and the
			// direction from the player's angles now.
			if (g_aimPredict) {
				// The camera node lags the player while moving (measured: about 30 units at a run, actor and first-person root are always equal). Its distance above the player is
				// constant, so that is measured while the player stands still, and the view is the player's position of this frame plus it.
				auto&              vp = g_aim.view;
				const RE::NiPoint3  camT = cam->world.translate;
				const float         flat = std::fabs(actorNow.x - vp.lastActor.x) + std::fabs(actorNow.y - vp.lastActor.y);
				const float         vertical = std::fabs(actorNow.z - vp.lastActor.z);
				if (!vp.haveRest) {  // the first frame of an aim: the eye's height now (standing, crouched, on a mount ...), no sideways offset known yet
					vp.rest = { 0.0f, 0.0f, camT.z - actorNow.z };
					vp.haveRest = true;
				} else {
					if (vertical < 0.5f) {  // the eye's height follows a crouch or a stand at once, on the move or not (a jump or a fall keeps the last one)
						vp.rest.z = camT.z - actorNow.z;
					}
					if (flat < 0.25f && vertical < 0.5f) {  // sideways the camera only lags while the player moves: measured when the player stands still
						vp.rest.x = camT.x - actorNow.x;
						vp.rest.y = camT.y - actorNow.y;
					}
				}
				vp.camSeen = camT;
				vp.lastActor = actorNow;
				vp.have = true;
				const RE::NiPoint3& rest = vp.rest;
				origin = { actorNow.x + rest.x, actorNow.y + rest.y, actorNow.z + rest.z };
			}
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
			if (g_aimPredict) {  // the direction of this frame, from the player's angles (pitch is positive downwards, heading from north)
				const float h = a_player->GetAngleZ(), pch = a_player->GetAngleX();
				dir = Norm({ std::sin(h) * std::cos(pch), std::cos(h) * std::cos(pch), -std::sin(pch) });
			}
			// what the game's own numbers say, every tenth of a second for the first minute of aiming: this is how the next fix is chosen
			static std::chrono::steady_clock::time_point lastNote{};
			static int notes = 0;
			const auto nowT = std::chrono::steady_clock::now();
			if (notes < 600 && nowT - lastNote > std::chrono::milliseconds(100)) {
				lastNote = nowT;
				++notes;
				const Vec3 camDir = Norm({ sign * cam->world.rotate.entry[0][best], sign * cam->world.rotate.entry[1][best], sign * cam->world.rotate.entry[2][best] });
				SKSE::log::info("aim view: actor {:.1f} {:.1f} {:.1f} | root {:.1f} {:.1f} {:.1f} | camera {:.1f} {:.1f} {:.1f} | used {:.1f} {:.1f} {:.1f} | forward dot {:.4f}", actorNow.x, actorNow.y, actorNow.z,
					rootNode->world.translate.x, rootNode->world.translate.y, rootNode->world.translate.z, cam->world.translate.x, cam->world.translate.y, cam->world.translate.z, origin.x, origin.y, origin.z,
					dir.x * camDir.x + dir.y * camDir.y + dir.z * camDir.z);
			}
		}
		const Vec3 right = Norm(Cross(dir, { 0.0f, 0.0f, 1.0f }));
		const Vec3 up = Cross(right, dir);
		const float b = g_aim.blend;
		const float fwd = g_aimForward - g_kick.gunBack;  // the shot jerks the gun back ...
		const float side = g_aimRight - g_kick.swayRight;  // ... the sway moves it (turning right: the gun lags to the left)
		const float low = g_aimDown - g_kick.swayUp - g_kick.gunBack * 0.15f;  // ... and a little up
		const RE::NiPoint3 target{ origin.x + dir.x * fwd + right.x * side - up.x * low, origin.y + dir.y * fwd + right.y * side - up.y * low,
			origin.z + dir.z * fwd + right.z * side - up.z * low };
		const float scale = gun->world.scale > 1e-4f ? gun->world.scale : 1.0f;
		const auto& gw = gun->world;
		// the muzzle in the weapon's own axes, and its barrel and top directions there
		const RE::NiPoint3 offset{ muzzle->world.translate.x - gw.translate.x, muzzle->world.translate.y - gw.translate.y, muzzle->world.translate.z - gw.translate.z };
		const RE::NiPoint3 rel = MulT(gw.rotate, { offset.x / scale, offset.y / scale, offset.z / scale });
		RE::NiMatrix3      want = gw.rotate;  // the turn the gun should have in the world (kept as it is when the mesh lacks the reference nodes)
		const auto breech = root3d->GetObjectByName("SkylandsBreech"sv);
		const auto top = root3d->GetObjectByName("SkylandsTop"sv);
		if (breech && top) {
			const RE::NiPoint3 bw{ muzzle->world.translate.x - breech->world.translate.x, muzzle->world.translate.y - breech->world.translate.y, muzzle->world.translate.z - breech->world.translate.z };
			const RE::NiPoint3 uw{ top->world.translate.x - muzzle->world.translate.x, top->world.translate.y - muzzle->world.translate.y, top->world.translate.z - muzzle->world.translate.z };
			const RE::NiPoint3 bl = MulT(gw.rotate, bw), ul = MulT(gw.rotate, uw);  // in the weapon's axes
			const Vec3 bn = Norm({ bl.x, bl.y, bl.z });
			const float k = ul.x * bn.x + ul.y * bn.y + ul.z * bn.z;
			const Vec3 un = Norm({ ul.x - bn.x * k, ul.y - bn.y * k, ul.z - bn.z * k });
			const Vec3 cn = Cross(bn, un);
			const Vec3 cw = Cross(dir, up);  // = right
			// W takes (barrel, top, side) of the weapon to (view forward, view up, view right): its columns are the targets, so W = [F U R] [b u c]^T
			const float F[3] = { dir.x, dir.y, dir.z }, U[3] = { up.x, up.y, up.z }, R[3] = { cw.x, cw.y, cw.z };
			const float B[3] = { bn.x, bn.y, bn.z }, T[3] = { un.x, un.y, un.z }, C[3] = { cn.x, cn.y, cn.z };
			for (int i = 0; i < 3; ++i) {
				for (int j = 0; j < 3; ++j) {
					want.entry[i][j] = F[i] * B[j] + U[i] * T[j] + R[i] * C[j];
				}
			}
		}
		const RE::NiPoint3 back = Mul(want, { rel.x * scale, rel.y * scale, rel.z * scale });
		const RE::NiPoint3 rootWorld{ target.x - back.x, target.y - back.y, target.z - back.z };
		const auto&        rn = rootNode->world;
		const float        rs = rn.scale > 1e-4f ? rn.scale : 1.0f;
		const RE::NiPoint3 tl = MulT(rn.rotate, { (rootWorld.x - rn.translate.x) / rs, (rootWorld.y - rn.translate.y) / rs, (rootWorld.z - rn.translate.z) / rs });
		const RE::NiMatrix3 rl = MatMul(Transposed(rn.rotate), want);
		gun->local.translate = { g_aim.startT.x + (tl.x - g_aim.startT.x) * b, g_aim.startT.y + (tl.y - g_aim.startT.y) * b, g_aim.startT.z + (tl.z - g_aim.startT.z) * b };
		// turned from where it began to the held turn by `b` of the way (about the axis of the turn between them)
		const RE::NiMatrix3 delta = MatMul(rl, Transposed(g_aim.startRot));
		const float         cosA = std::clamp((delta.entry[0][0] + delta.entry[1][1] + delta.entry[2][2] - 1.0f) * 0.5f, -1.0f, 1.0f);
		const float         ang = std::acos(cosA);
		const Vec3          axis = Norm({ delta.entry[2][1] - delta.entry[1][2], delta.entry[0][2] - delta.entry[2][0], delta.entry[1][0] - delta.entry[0][1] });
		gun->local.rotate = ang > 1e-4f ? MatMul(Turn(axis, ang * b), g_aim.startRot) : g_aim.startRot;
		g_stage = "aim: hands";
		if (g_hideHands && b >= 0.4f && g_aim.hidden.empty()) {
			HideHands(rootNode, gun);
			SKSE::log::info("aim: {} arm parts hidden", g_aim.hidden.size());
		} else if ((!g_hideHands || b < 0.4f) && !g_aim.hidden.empty()) {
			ShowHands();
		}
		// the gun's world transform is worked out now, from the root and the camera as they are at this moment, so that what is drawn is not a frame behind the view
		RE::NiUpdateData update{};
		gun->UpdateDownwardPass(update, 0);
		static bool told = false;
		if (!told) {
			told = true;
			SKSE::log::info("aim: gun held at {:.0f} {:.0f} {:.0f} (camera {:.0f} {:.0f} {:.0f}), turn {:.1f} degrees from the hand's", target.x, target.y, target.z, origin.x, origin.y, origin.z,
				ang * 180.0f / std::numbers::pi_v<float>);
		}
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
		RestoreGun();
		SKSE::log::info("aim ended: field of view back to {:.1f}, walking speed back to {:.0f}", g_aim.baseFov, g_aim.baseWalk);
	}

	void UpdateAim(RE::PlayerCharacter* a_player, const GunInfo& a_info, Clock::time_point a_now)
	{
		g_stage = "aim";
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
			g_aim.view = {};
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
		if (g_ammoText && !g_hudLive.load()) {  // the display says all of this once it is up
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

	// ---- the display -----------------------------------------------------------------------------------------------
	//
	// Drawn into the game's own HUD movie from here (no file of ours): a movie clip "SkylandsHUD" holding text fields and a bar, made with the movie's
	// ActionScript calls (createTextField, the drawing calls) and found again by its path at every update, so a reloaded HUD (a loaded game) simply makes a
	// new one. Bottom right: the name of the gun in the colour of its rarity for a moment when it is taken up, the magazine large with the clip and the stock
	// beside it, a bar that fills while a reload runs, and a short word (LOW AMMO, RELOAD, NO AMMO) that flashes.

	std::string HtmlEscape(const std::string& a_text)
	{
		std::string out;
		for (const char c : a_text) {
			out += c == '&' ? "&amp;" : c == '<' ? "&lt;" : c == '>' ? "&gt;" : std::string(1, c);
		}
		return out;
	}

	void HudRect(RE::GFxValue& a_clip, double a_rgb, double a_alpha, double a_w, double a_h)
	{
		a_clip.Invoke("beginFill", std::array<RE::GFxValue, 2>{ RE::GFxValue(a_rgb), RE::GFxValue(a_alpha) });
		a_clip.Invoke("moveTo", std::array<RE::GFxValue, 2>{ RE::GFxValue(0.0), RE::GFxValue(0.0) });
		a_clip.Invoke("lineTo", std::array<RE::GFxValue, 2>{ RE::GFxValue(a_w), RE::GFxValue(0.0) });
		a_clip.Invoke("lineTo", std::array<RE::GFxValue, 2>{ RE::GFxValue(a_w), RE::GFxValue(a_h) });
		a_clip.Invoke("lineTo", std::array<RE::GFxValue, 2>{ RE::GFxValue(0.0), RE::GFxValue(a_h) });
		a_clip.Invoke("lineTo", std::array<RE::GFxValue, 2>{ RE::GFxValue(0.0), RE::GFxValue(0.0) });
		a_clip.Invoke("endFill");
	}

	bool HudBuild(RE::GFxMovieView* a_movie)
	{
		RE::GFxValue root;
		if (!a_movie->GetVariable(&root, "_root") || !root.IsObject()) {
			return false;
		}
		RE::GFxValue clip;
		if (!root.CreateEmptyMovieClip(&clip, "SkylandsHUD", 9876)) {
			return false;
		}
		RE::GFxValue::DisplayInfo place;
		place.SetPosition(1280.0 - g_hudRight, 720.0 - g_hudBottom);
		place.SetVisible(false);
		clip.SetDisplayInfo(place);
		const auto field = [&](const char* a_name, double a_depth, double a_x, double a_y, double a_w, double a_h) {
			RE::GFxValue result;
			clip.Invoke("createTextField", &result,
				std::array<RE::GFxValue, 6>{ RE::GFxValue(a_name), RE::GFxValue(a_depth), RE::GFxValue(a_x), RE::GFxValue(a_y), RE::GFxValue(a_w), RE::GFxValue(a_h) });
			RE::GFxValue tf;
			if (clip.GetMember(a_name, &tf) && tf.IsObject()) {
				tf.SetMember("html", RE::GFxValue(true));
				tf.SetMember("selectable", RE::GFxValue(false));
				tf.SetMember("multiline", RE::GFxValue(false));
				tf.SetMember("wordWrap", RE::GFxValue(false));
			}
		};
		field("tfName", 1, -420.0, -64.0, 420.0, 26.0);
		field("tfAmmo", 2, -360.0, -42.0, 360.0, 58.0);
		field("tfWarn", 3, -260.0, 26.0, 260.0, 22.0);
		RE::GFxValue bg, fill;
		clip.CreateEmptyMovieClip(&bg, "barBg", 20);
		HudRect(bg, 0x000000, 60.0, 190.0, 6.0);
		RE::GFxValue::DisplayInfo at;
		at.SetPosition(-190.0, 20.0);
		bg.SetDisplayInfo(at);
		clip.CreateEmptyMovieClip(&fill, "barFill", 21);
		HudRect(fill, 0xFFB428, 100.0, 190.0, 6.0);
		fill.SetDisplayInfo(at);
		RE::GFxValue check;
		const bool ok = a_movie->GetVariable(&check, "_root.SkylandsHUD.tfAmmo") && check.IsObject();
		SKSE::log::info("hud: built in the game's HUD movie ({})", ok ? "text fields found" : "TEXT FIELDS MISSING");
		return ok;
	}

	void HudSet(RE::GFxMovieView* a_movie, const char* a_path, double a_alpha, bool a_visible)
	{
		RE::GFxValue v;
		if (a_movie->GetVariable(&v, a_path) && v.IsObject()) {
			RE::GFxValue::DisplayInfo di;
			di.SetAlpha(a_alpha);
			di.SetVisible(a_visible);
			v.SetDisplayInfo(di);
		}
	}

	void HudText(RE::GFxMovieView* a_movie, const char* a_path, const std::string& a_html, std::string& a_last)
	{
		if (a_html == a_last) {
			return;
		}
		RE::GFxValue v;
		if (a_movie->GetVariable(&v, a_path) && v.IsObject()) {
			v.SetTextHTML(a_html.c_str());
			a_last = a_html;
		}
	}

	// The game's own enchantment charge meters (what showed the magazine before the display) are hidden while a gun is up. Their names are found among the members of the
	// HUD's base clip (anything with "charge" or "enchant" in its name), and told in the log with the other member names, so a wrong guess can be corrected.
	std::vector<std::string> g_meters;
	bool                     g_metersHidden = false, g_metersLooked = false;

	void HudMeters(RE::GFxMovieView* a_movie, bool a_hide)
	{
		if (!g_metersLooked) {
			g_metersLooked = true;
			RE::GFxValue base;
			if (a_movie->GetVariable(&base, "_root.HUDMovieBaseInstance") && base.IsObject()) {
				std::string all;
				base.VisitMembers([&](const char* a_name, const RE::GFxValue&) {
					std::string name = a_name ? a_name : "";
					std::string low = name;
					std::transform(low.begin(), low.end(), low.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
					// only the meters themselves: "RightChargeMeter" and "LeftChargeMeter" (their "...Anim" partners are not things on the screen, and asking one to be
					// hidden crashed the game in 0.23.1)
					// the on-screen clips are the "...MeterAnim" ones (like HealthMeterAnim); the plain "...Meter" members are helper objects, not display objects (0.23.2 hid
					// those and the bar stayed). Every candidate is checked to be a display object before it is touched.
					if (low.find("charge") != std::string::npos && low.size() >= 9 && low.compare(low.size() - 9, 9, "meteranim") == 0) {
						g_meters.push_back(name);
					}
					if (all.size() < 1500) {
						all += name + " ";
					}
				});
				SKSE::log::info("hud: the game's HUD base clip holds [{}]; charge meter clips: {}", all, g_meters.size());
			} else {
				SKSE::log::info("hud: the game's HUD base clip was not found");
			}
		}
		if (g_meters.empty() || (!a_hide && !g_metersHidden)) {
			return;
		}
		for (const auto& name : g_meters) {
			RE::GFxValue v;
			const bool found = a_movie->GetVariable(&v, ("_root.HUDMovieBaseInstance." + name).c_str());
			static std::atomic_int told{ 0 };
			if (told.fetch_add(1) < 4) {
				SKSE::log::info("hud: {} found {}, display object {}", name, found, found && v.IsDisplayObject());
			}
			if (found && v.IsDisplayObject()) {
				RE::GFxValue::DisplayInfo di;
				di.SetVisible(!a_hide);
				v.SetDisplayInfo(di);
			}
		}
		g_metersHidden = a_hide;
	}

	void HudFrame(Clock::time_point a_now)
	{
		static Clock::time_point next{};
		static bool              broken = false, shownLast = false;
		static std::string       lastAmmo, lastName, lastWarn;
		if (!g_hud || broken || a_now < next) {
			return;
		}
		next = a_now + std::chrono::milliseconds(33);
		const auto ui = RE::UI::GetSingleton();
		RE::GPtr<RE::GFxMovieView> movie;
		if (ui) {
			movie = ui->GetMovieView("HUD Menu");
		}
		if (!movie.get()) {
			return;
		}
		RE::GFxValue clip;
		if (!movie->GetVariable(&clip, "_root.SkylandsHUD") || !clip.IsObject()) {
			if (!g_hudShow.load()) {
				return;
			}
			if (!HudBuild(movie.get())) {
				broken = true;  // the plain messages carry on
				SKSE::log::info("hud: could not be built; the plain ammo messages stay");
				return;
			}
			lastAmmo.clear();
			lastName.clear();
			lastWarn.clear();
			shownLast = false;
			if (!movie->GetVariable(&clip, "_root.SkylandsHUD")) {
				return;
			}
		}
		const bool show = g_hudShow.load() && !g_gun.name.empty();
		HudMeters(movie.get(), show);
		if (!show) {
			if (shownLast) {
				shownLast = false;
				RE::GFxValue::DisplayInfo di;
				di.SetVisible(false);
				clip.SetDisplayInfo(di);
			}
			return;
		}
		if (!shownLast) {
			shownLast = true;
			RE::GFxValue::DisplayInfo di;
			di.SetVisible(true);
			clip.SetDisplayInfo(di);
		}
		const double t = std::chrono::duration<double>(a_now.time_since_epoch()).count();
		const int    clipSize = g_gun.info.clip, mag = g_gun.mag;
		if (g_gun.ammo && a_now >= g_gun.reserveAt) {
			g_gun.reserve = CountOf(RE::PlayerCharacter::GetSingleton(), g_gun.ammo);
			g_gun.reserveAt = a_now + std::chrono::milliseconds(1000);
		}
		const bool low = mag > 0 && mag * 4 <= clipSize;
		const bool empty = mag <= 0;
		const bool reloading = g_gun.reloading;
		// the magazine, large; the clip and the stock beside it
		const char* magColor = empty ? "#FF3C28" : low ? "#FF6A28" : "#FFB428";
		std::string ammo = std::string("<p align=\"right\"><font face=\"$EverywhereBoldFont\" size=\"46\" color=\"") + magColor + "\">" + std::to_string((std::max)(0, mag)) +
			"</font><font face=\"$EverywhereBoldFont\" size=\"22\" color=\"#D2D2D2\"> / " + std::to_string(clipSize) + "</font>";
		if (g_gun.reserve >= 0) {
			ammo += std::string("<font face=\"$EverywhereBoldFont\" size=\"22\" color=\"#8A8A8A\">  |  </font><font face=\"$EverywhereBoldFont\" size=\"26\" color=\"") +
				(g_gun.reserve == 0 ? "#FF3C28" : "#8CD2FF") + "\">" + std::to_string(g_gun.reserve) + "</font>";
		}
		ammo += "</p>";
		HudText(movie.get(), "_root.SkylandsHUD.tfAmmo", ammo, lastAmmo);
		// a short word that flashes
		const char* word = reloading ? "RELOADING" : empty ? (g_gun.reserve == 0 ? "NO AMMO" : "RELOAD") : low ? "LOW AMMO" : "";
		const std::string warn = *word ? std::string("<p align=\"right\"><font face=\"$EverywhereBoldFont\" size=\"18\" color=\"") + (reloading ? "#FFB428" : "#FF3C28") + "\">" + word + "</font></p>" : "";
		HudText(movie.get(), "_root.SkylandsHUD.tfWarn", warn, lastWarn);
		const bool flashing = (low || empty) && !reloading;
		const double pulse = flashing ? 60.0 + 40.0 * std::sin(t * 9.0) : 100.0;
		HudSet(movie.get(), "_root.SkylandsHUD.tfAmmo", pulse, true);
		HudSet(movie.get(), "_root.SkylandsHUD.tfWarn", flashing ? pulse : 100.0, *word != 0);
		// the reload bar
		if (reloading) {
			const double total = (std::max)(0.05, std::chrono::duration<double>(g_gun.reloadUntil - g_gun.reloadStart).count());
			const double done = std::clamp(std::chrono::duration<double>(a_now - g_gun.reloadStart).count() / total, 0.0, 1.0);
			RE::GFxValue fill;
			if (movie->GetVariable(&fill, "_root.SkylandsHUD.barFill") && fill.IsObject()) {
				RE::GFxValue::DisplayInfo di;
				di.SetScale((std::max)(1.0, done * 100.0), 100.0);
				di.SetVisible(true);
				fill.SetDisplayInfo(di);
			}
			HudSet(movie.get(), "_root.SkylandsHUD.barBg", 100.0, true);
		} else {
			HudSet(movie.get(), "_root.SkylandsHUD.barBg", 100.0, false);
			HudSet(movie.get(), "_root.SkylandsHUD.barFill", 100.0, false);
		}
		// the name of the gun in the colour of its rarity, for a moment after it is taken up, fading at the end
		const double left = std::chrono::duration<double>(g_gun.nameUntil - a_now).count();
		if (left > 0.0) {
			const std::string name = std::string("<p align=\"right\"><font face=\"$EverywhereBoldFont\" size=\"21\" color=\"") + g_gun.rarityColor + "\">" + HtmlEscape(g_gun.name) + "</font></p>";
			HudText(movie.get(), "_root.SkylandsHUD.tfName", name, lastName);
			HudSet(movie.get(), "_root.SkylandsHUD.tfName", left < 1.2 ? left / 1.2 * 100.0 : 100.0, true);
		} else {
			HudSet(movie.get(), "_root.SkylandsHUD.tfName", 0.0, false);
		}
		g_hudLive = true;
	}

	void TickGun();

	void Tick()
	{
		g_stage = "tick: gun";
		TickGun();
		g_stage = "tick: effects";
		FxFrame(RE::PlayerCharacter::GetSingleton(), Clock::now());
		g_stage = "tick: hud";
		HudFrame(Clock::now());
		g_stage = "tick: done";
	}

	void TickGun()
	{
		g_hudShow = false;
		const bool tapped = g_latch.exchange(false);  // the trigger went down since the last tick (even if it is already up again)
		const auto player = RE::PlayerCharacter::GetSingleton();
		if (!g_gunMode.load() || !player || !player->Is3DLoaded() || MenuOpen()) {
			g_gun.wasHeld = false;
			ResetKick();
			if (player) {  // gun put away, menu open, 3D gone: the aim ends and the gun goes back to the hand
				ReleaseAim(player);
			}
			return;
		}
		GunInfo    info{};
		const auto weapon = HeldGun(player, info);
		if (!weapon) {
			g_gun.wasHeld = false;
			ResetKick();
			ReleaseAim(player);
			return;
		}
		const auto now = Clock::now();
		g_hudShow = true;
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
			g_gun.name = weapon->GetName() ? weapon->GetName() : "";
			static const char* const colors[] = { "#FFFFFF", "#FFFFFF", "#3CDC5A", "#3C8CFF", "#B450FF", "#FF9628", "#FF3DB8" };
			g_gun.rarityColor = colors[std::clamp(info.rarity, 0, 6)];
			g_gun.nameUntil = now + std::chrono::milliseconds(4500);
			g_gun.reserveAt = now;
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
		RecoilFrame(player, now);
		UpdateAim(player, g_gun.info, now);
		FollowFlash(player, now);
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
					g_gun.reserve = left;
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
		const bool held = g_held.load();
		if (!held && !tapped) {
			g_gun.wasHeld = false;
			return;
		}
		if (!g_gun.wasHeld) {  // the trigger went down
			g_gun.wasHeld = true;
			g_gun.holdStart = now;
			g_gun.holdShots = 0;
			// A pull never starts with a backlog: rounds "owed" from a pause shorter than three intervals used to come out all at once (two or three
			// bullets from one tap). The gun's cooldown still holds: a pull before the last shot's interval is over waits for it.
			if (g_gun.nextShot < now) {
				g_gun.nextShot = now;
			}
		}
		int fired = 0;
		const auto step = std::chrono::microseconds(static_cast<long long>(gap * 1000000.0f));
		const int most = held ? 3 : 1;  // a tap already over by this tick is one round
		while (now >= g_gun.nextShot && g_gun.mag > 0 && fired < most) {
			RE::NiPoint3 at{};
			if (!Launch(player->GetFormID(), 0, 0.0f, 0.0f, kOffsetForward, AimFactor() / accuracy, &at)) {
				break;
			}
			{
				// The gun's own sound from its keywords first (the script's hand-over can be missing: a ghost script object, a load without the hook);
				// the script's sound is the fallback.
				RE::FormID sid = ShotSoundOf(weapon, g_gun.info);
				if (!sid) {
					sid = g_shotSound.load();
				}
				static int told = 0;
				if (told < 6) {
					++told;
					SKSE::log::info("player shot sound: own {:08X} (keywords), script {:08X}, playing {:08X}", ShotSoundOf(weapon, g_gun.info), g_shotSound.load(), sid);
				}
				PlaySound(sid, at);
			}
			AddKick(g_gun.info, now);
			--g_gun.mag;
			++g_gun.holdShots;
			++fired;
			++g_shots;
			g_gun.nextShot = (now - g_gun.nextShot > step * 3) ? now + step : g_gun.nextShot + step;
		}
		if (!held) {  // the tap is spent
			g_gun.wasHeld = false;
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

	// When the game crashes inside or after this plugin's code, the plugin says where: the exception, the address (module and offset) and the last stage the plugin
	// marked. The previous filter (a crash logger, if one is installed) is called afterwards, so nothing else is lost.
	LPTOP_LEVEL_EXCEPTION_FILTER g_previousFilter = nullptr;

	LONG WINAPI CrashFilter(EXCEPTION_POINTERS* a_info)
	{
		static std::atomic_bool once{ false };
		if (a_info && a_info->ExceptionRecord && !once.exchange(true)) {
			const auto  code = a_info->ExceptionRecord->ExceptionCode;
			const void* at = a_info->ExceptionRecord->ExceptionAddress;
			HMODULE     module = nullptr;
			char        name[MAX_PATH]{};
			if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, static_cast<LPCSTR>(at), &module) && module) {
				GetModuleFileNameA(module, name, MAX_PATH);
			}
			const auto offset = reinterpret_cast<std::uintptr_t>(at) - reinterpret_cast<std::uintptr_t>(module);
			SKSE::log::critical("CRASH: exception {:08X} at {} in {} (+{:X}); the plugin's last stage: {}", static_cast<unsigned>(code), at, name[0] ? name : "unknown module", offset, g_stage.load());
			if (const auto logger = spdlog::default_logger()) {
				logger->flush();
			}
		}
		return g_previousFilter ? g_previousFilter(a_info) : EXCEPTION_CONTINUE_SEARCH;
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
	.Version = { 1, 14, 0, 0 },
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
	g_previousFilter = SetUnhandledExceptionFilter(CrashFilter);
	SKSE::GetPapyrusInterface()->Register(RegisterPapyrus);
	SKSE::GetMessagingInterface()->RegisterListener(OnMessage);
	return true;
}
