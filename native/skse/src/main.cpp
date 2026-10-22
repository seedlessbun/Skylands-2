// SkylandsNative: the SKSE plugin the Skylands guns use for what plain Papyrus cannot do.
//
//   TriggerHeld / TriggerPressed   the attack button ("Right Attack/Block": keyboard, mouse or gamepad, whatever the player mapped)
//   FireBullet                     launches a spell's projectile from the right hand's magic node, aimed along the crosshair,
//                                  with a spread; no cast animation, no wind-up, no magicka
//
// Papyrus class: SkylandsNative, static functions. Data/Scripts/SkylandsNative.pex (written by the installer, scripts.native_stub)
// declares them as native; the types there must match the ones below.
// Built with CommonLibSSE-NG and Address Library, so it works on every runtime that Address Library supports.

#include "PCH.h"

namespace
{
	constexpr std::int32_t kVersion = 102;  // 1.0.2

	std::atomic_bool g_held{ false };
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
				if (!button || button->QUserEvent() != events->rightAttack) {
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

	bool TriggerHeld(RE::StaticFunctionTag*)
	{
		return g_held.load() && !MenuOpen();
	}

	bool TriggerPressed(RE::StaticFunctionTag*)
	{
		const bool pressed = g_latch.exchange(false);
		return pressed && !MenuOpen();
	}

	void Launch(RE::FormID a_shooter, RE::FormID a_spell, float a_spread, float a_right, float a_up, float a_forward)
	{
		const auto shooter = RE::TESForm::LookupByID<RE::Actor>(a_shooter);
		const auto spell = RE::TESForm::LookupByID<RE::SpellItem>(a_spell);
		if (!shooter || !spell || !spell->GetAVEffect() || !spell->GetAVEffect()->data.projectileBase) {
			SKSE::log::warn("FireBullet: no shooter, spell or projectile (shooter {:08X}, spell {:08X})", a_shooter, a_spell);
			return;
		}

		// where the player is looking: the eye (the camera in first person) and the way it points
		RE::NiPoint3 eye{}, look{};
		shooter->GetEyeVector(eye, look, true);
		const Vec3 dir = Norm({ look.x, look.y, look.z });
		const Vec3 right = Norm(Cross(dir, { 0.0f, 0.0f, 1.0f }));
		const Vec3 up = Cross(right, dir);

		// the right hand's magic node, in the first-person skeleton when the camera is first person
		const auto camera = RE::PlayerCamera::GetSingleton();
		const bool first = shooter->IsPlayerRef() && camera && camera->IsInFirstPerson();
		RE::NiPoint3 origin = eye;
		bool         onNode = false;
		if (const auto root = shooter->Get3D(first)) {
			if (const auto node = root->GetObjectByName("NPC R MagicNode [RMag]"sv)) {
				origin = node->world.translate;
				onNode = true;
			}
		}
		if (!onNode) {  // no node found: a point ahead of the eye, to the right and below it
			origin = { eye.x + dir.x * 40.0f + right.x * 14.0f, eye.y + dir.y * 40.0f + right.y * 14.0f, eye.z + dir.z * 40.0f - 12.0f };
		}
		origin.x += right.x * a_right + up.x * a_up + dir.x * a_forward;
		origin.y += right.y * a_right + up.y * a_up + dir.y * a_forward;
		origin.z += right.z * a_right + up.z * a_up + dir.z * a_forward;

		// aimed at the point the crosshair looks at some way ahead, so the bullet crosses the crosshair rather than running beside it
		const Vec3 target{ eye.x + dir.x * g_convergence, eye.y + dir.y * g_convergence, eye.z + dir.z * g_convergence };
		const Vec3 aim = Norm({ target.x - origin.x, target.y - origin.y, target.z - origin.z });
		float      pitch = -std::asin(std::clamp(aim.z, -1.0f, 1.0f));  // Skyrim's pitch is positive downwards
		float      heading = std::atan2(aim.x, aim.y);

		// the spread: a random direction inside a cone of a_spread degrees
		if (a_spread > 0.0f) {
			static thread_local std::mt19937 rng{ std::random_device{}() };
			std::uniform_real_distribution<float> unit(0.0f, 1.0f);
			const float radius = a_spread * std::numbers::pi_v<float> / 180.0f * std::sqrt(unit(rng));
			const float angle = 2.0f * std::numbers::pi_v<float> * unit(rng);
			pitch += radius * std::sin(angle);
			heading += radius * std::cos(angle);
		}

		RE::Projectile::LaunchData data(shooter, origin, { pitch, heading }, spell);
		data.castingSource = RE::MagicSystem::CastingSource::kRightHand;
		RE::ProjectileHandle handle{};
		RE::Projectile::Launch(&handle, data);
	}

	// Launched on the game's own thread, a frame later: a Papyrus call may not touch the world from the script thread.
	bool FireBullet(RE::StaticFunctionTag*, RE::Actor* a_shooter, RE::SpellItem* a_spell, float a_spread, float a_right, float a_up, float a_forward)
	{
		if (!a_shooter || !a_spell) {
			return false;
		}
		const auto shooter = a_shooter->GetFormID();
		const auto spell = a_spell->GetFormID();
		const auto task = SKSE::GetTaskInterface();
		if (!task) {
			return false;
		}
		task->AddTask([=]() { Launch(shooter, spell, a_spread, a_right, a_up, a_forward); });
		return true;
	}

	bool RegisterPapyrus(RE::BSScript::IVirtualMachine* a_vm)
	{
		a_vm->RegisterFunction("Version"sv, "SkylandsNative"sv, Version);
		a_vm->RegisterFunction("TriggerHeld"sv, "SkylandsNative"sv, TriggerHeld);
		a_vm->RegisterFunction("TriggerPressed"sv, "SkylandsNative"sv, TriggerPressed);
		a_vm->RegisterFunction("FireBullet"sv, "SkylandsNative"sv, FireBullet);
		return true;
	}

	void OnMessage(SKSE::MessagingInterface::Message* a_message)
	{
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
	.Version = { 1, 0, 2, 0 },
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
