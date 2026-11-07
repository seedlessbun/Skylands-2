// Toss (1.29.0): items dropped by enemies get a small kick up and out, so they land around the body instead of inside it (the user's request).
//
// A dropped reference (a Badass's guaranteed items, a body's shield or relic, the Hunter script's gun drops via the native TossDrop) is queued here.
// A thread asks the game thread every 100 ms while anything waits; once the item's 3D is loaded (up to 2.5 s) the plugin finds the first rigid body in it
// and sets its linear velocity (under the havok world's write lock): DropTossUp units/s up and DropTossOut units/s in a random direction.
// Ini: DropToss (1 on, 0 off), DropTossUp, DropTossOut.
#pragma once

#include "PCH.h"
#include <atomic>
#include <chrono>
#include <mutex>
#include <random>
#include <thread>
#include <vector>

namespace toss
{
	inline bool  g_on = true;
	inline float g_up = 420.0f;   // game units per second (1.29.1: was 260, items still stuck in bodies)
	inline float g_out = 150.0f;  // game units per second, sideways (was 90)

	struct Waiting
	{
		RE::ObjectRefHandle                   ref;
		std::chrono::steady_clock::time_point due;
		int                                   tries = 0;
		int                                   kicks = 0;   // 1.29.1: an item that barely moved after the first kick (caught in the body) gets one more, harder
		RE::NiPoint3                          at{};        // where it was at the last kick
	};
	inline std::mutex           g_lock;
	inline std::vector<Waiting> g_waiting;
	inline std::atomic_int      g_tossed{ 0 }, g_missed{ 0 };

	inline RE::bhkRigidBody* BodyIn(RE::NiAVObject* a_object, int a_depth = 0)
	{
		if (!a_object || a_depth > 8) {
			return nullptr;
		}
		if (const auto co = a_object->collisionObject.get()) {
			if (const auto nco = netimmerse_cast<RE::bhkNiCollisionObject*>(co); nco && nco->body) {
				if (const auto rb = netimmerse_cast<RE::bhkRigidBody*>(nco->body.get())) {
					return rb;
				}
			}
		}
		if (const auto node = a_object->AsNode()) {
			for (auto& child : node->GetChildren()) {
				if (const auto rb = BodyIn(child.get(), a_depth + 1)) {
					return rb;
				}
			}
		}
		return nullptr;
	}

	// game thread: true when done with this item (tossed, or given up)
	inline bool Kick(Waiting& a_w)
	{
		const auto ptr = a_w.ref.get();
		const auto ref = ptr.get();
		if (!ref || ref->IsDisabled() || ref->IsDeleted()) {
			return true;
		}
		if (a_w.kicks > 0) {
			const auto  now = ref->GetPosition();
			const float moved = now.GetDistance(a_w.at);
			if (moved >= 30.0f || a_w.kicks >= 2) {
				return true;
			}
			static std::atomic_int again{ 0 };
			if (again.fetch_add(1) < 12) {
				SKSE::log::info("toss: {:08X} moved only {:.0f} units after its kick: kicked again, harder", ref->GetFormID(), moved);
			}
		}
		const auto root = ref->Get3D();
		const auto cell = ref->GetParentCell();
		const auto body = root ? BodyIn(root) : nullptr;
		const auto world = cell ? cell->GetbhkWorld() : nullptr;
		if (!body || !world) {
			if (++a_w.tries >= 25) {
				if (g_missed.fetch_add(1) < 10) {
					SKSE::log::info("toss: {:08X} had no {} after 2.5 s: left where it fell", ref->GetFormID(), !root ? "3D" : !body ? "rigid body" : "physics world");
				}
				return true;
			}
			a_w.due = std::chrono::steady_clock::now() + std::chrono::milliseconds(100);
			return false;
		}
		static thread_local std::mt19937 rng{ std::random_device{}() };
		const float angle = std::uniform_real_distribution<float>(0.0f, 6.2831853f)(rng);
		const float harder = a_w.kicks > 0 ? 1.4f : 1.0f;
		const float out = harder * g_out * std::uniform_real_distribution<float>(0.6f, 1.2f)(rng);
		const float up = harder * g_up * std::uniform_real_distribution<float>(0.85f, 1.15f)(rng);
		const float s = RE::bhkWorld::GetWorldScale();  // game units -> havok units
		{
			RE::BSWriteLockGuard guard(world->worldLock);
			body->SetLinearVelocity(RE::hkVector4(std::cos(angle) * out * s, std::sin(angle) * out * s, up * s, 0.0f));
		}
		if (g_tossed.fetch_add(1) < 12) {
			const auto base = ref->GetBaseObject();
			const char* name = base ? base->GetName() : nullptr;
			SKSE::log::info("toss: {:08X} \"{}\" kicked {:.0f} up, {:.0f} out (after {} tries)", ref->GetFormID(), name ? name : "?", up, out, a_w.tries);
		}
		// look again in 0.45 s: an item caught in the body's collision has hardly moved
		a_w.at = ref->GetPosition();
		++a_w.kicks;
		a_w.due = std::chrono::steady_clock::now() + std::chrono::milliseconds(450);
		return false;
	}

	inline void Frame()
	{
		std::vector<Waiting> now;
		{
			const std::lock_guard guard(g_lock);
			const auto            t = std::chrono::steady_clock::now();
			for (auto it = g_waiting.begin(); it != g_waiting.end();) {
				if (t >= it->due) {
					now.push_back(*it);
					it = g_waiting.erase(it);
				} else {
					++it;
				}
			}
		}
		std::vector<Waiting> again;
		for (auto& w : now) {
			if (!Kick(w)) {
				again.push_back(w);
			}
		}
		if (!again.empty()) {
			const std::lock_guard guard(g_lock);
			g_waiting.insert(g_waiting.end(), again.begin(), again.end());
		}
	}

	inline void Start()
	{
		static std::atomic_bool started{ false };
		if (started.exchange(true)) {
			return;
		}
		std::thread([]() {
			static std::atomic_bool queued{ false };
			for (;;) {
				std::this_thread::sleep_for(std::chrono::milliseconds(100));
				bool any = false;
				{
					const std::lock_guard guard(g_lock);
					any = !g_waiting.empty();
				}
				if (!any || queued.exchange(true)) {
					continue;
				}
				if (const auto task = SKSE::GetTaskInterface()) {
					task->AddTask([]() {
						Frame();
						queued = false;
					});
				} else {
					queued = false;
				}
			}
		}).detach();
	}

	// any thread: a freshly dropped item; kicked once its 3D is up
	inline void Toss(RE::TESObjectREFR* a_ref)
	{
		if (!g_on || !a_ref) {
			return;
		}
		Start();
		const std::lock_guard guard(g_lock);
		if (g_waiting.size() < 64) {
			g_waiting.push_back({ a_ref->GetHandle(), std::chrono::steady_clock::now() + std::chrono::milliseconds(150), 0 });
		}
	}

	inline void Toss(const RE::ObjectRefHandle& a_handle)
	{
		if (const auto ptr = a_handle.get()) {
			Toss(ptr.get());
		}
	}

	inline bool Config(const std::string& a_key, const std::string& a_value)
	{
		float v = 0.0f;
		if (a_key != "DropToss" && a_key != "DropTossUp" && a_key != "DropTossOut") {
			return false;
		}
		try {
			v = std::stof(a_value);
		} catch (...) {
			return true;
		}
		if (a_key == "DropToss") {
			g_on = v != 0.0f;
		} else if (a_key == "DropTossUp") {
			g_up = std::clamp(v, 0.0f, 2000.0f);
		} else {
			g_out = std::clamp(v, 0.0f, 2000.0f);
		}
		return true;
	}
}
