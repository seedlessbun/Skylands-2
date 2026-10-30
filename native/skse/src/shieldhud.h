// The shield display (0.39.0), drawn into the game's own HUD movie like the ammo display (no file of ours).
//
// Mode 1 (default), over the health bar: the bar of the game is covered by a bar of ours with the same place and size. Its upper half is the shield (blue) and
// its lower half the real health (red), both from the middle outwards like the game's bars shrink, so a full shield and full health read as half blue on top, half
// red below. (The game's own bar shows shield and health added together, because the shield is a bonus on Health; ours shows them apart.) The same is done
// over the enemy bar of the game for the person in the crosshair. Mode 2 leaves the game's bars as they are and puts a thin shield bar just above each.
//
// Where the bars are is read from the game's HUD movie at run time (getBounds of the clips named in the HUD base clip, in the movie root's coordinates), because
// nothing about their size is known beforehand; what was found goes to the log (first lines) so the places can be corrected with the ini keys ShieldHudX/Y/Width/
// Height (player) and ShieldHudEnemyX/Y/Width/Height. How visible a bar is (the game fades its bars) is taken from the game's clip: its own _alpha and _visible
// and those of every parent. If a bar cannot be found or the display cannot be built it stays off and the log says so; the shield itself does not depend on it.
#pragma once

#include "PCH.h"
#include "shield.h"

namespace shieldhud
{
	using Clock = std::chrono::steady_clock;

	inline bool  g_on = true;         // ShieldHud=0 turns the display off (the plain "Shield 120 / 300" lines come back)
	inline int   g_mode = 2;          // ShieldHudMode: 1 = over the health bar, 2 = a thin bar above it (the user's choice since 0.39.2)
	inline bool  g_enemy = true;      // ShieldHudEnemy=0: no display over the enemy bar
	inline bool  g_follow = true;     // ShieldHudFollow=0: do not follow the game's fading of its bars (always shown while a shield exists)
	inline int   g_align = 0;         // ShieldHudAlign: 0 from the middle, 1 from the left, 2 from the right
	inline float g_dx = 0.0f, g_dy = 0.0f, g_w = 0.0f, g_h = 0.0f;                        // the player's bar: shift and size in HUD pixels (0 = as found)
	inline float g_edx = 0.0f, g_edy = 0.0f, g_ew = 0.0f, g_eh = 0.0f;                    // the enemy's bar
	inline bool  g_log = false;       // ShieldHudLog=1: a line about the bars every 5 seconds
inline bool  g_health = false;    // ShieldHudHealth=1 (mode 2): the game's health bar is painted over with a bar of the REAL health, because the game's own bar shows health and shield added together
inline float g_insetX = 0.09f, g_insetY = 0.28f;  // ShieldHudInsetX/Y: how much of the game's bar (its width / height) is frame and caps, left alone when painting the real health

	struct Box
	{
		double x0 = 0.0, x1 = 0.0, y0 = 0.0, y1 = 0.0;
		bool   ok = false;
		double w() const { return x1 - x0; }
		double h() const { return y1 - y0; }
		double cx() const { return 0.5 * (x0 + x1); }
		double cy() const { return 0.5 * (y0 + y1); }
	};

	inline bool Num(const RE::GFxValue& a_object, const char* a_name, double& a_out)
	{
		RE::GFxValue v;
		if (a_object.GetMember(a_name, &v) && v.IsNumber()) {
			a_out = v.GetNumber();
			return true;
		}
		return false;
	}

	// the clip's rectangle in the coordinates of a_space (the movie root); false for an empty clip (the movie answers with enormous numbers)
	inline Box BoundsOf(RE::GFxValue& a_clip, RE::GFxValue& a_space)
	{
		Box b;
		if (!a_clip.IsDisplayObject()) {
			return b;
		}
		RE::GFxValue r;
		if (!a_clip.Invoke("getBounds", &r, std::array<RE::GFxValue, 1>{ a_space }) || !r.IsObject()) {
			return b;
		}
		b.ok = Num(r, "xMin", b.x0) && Num(r, "xMax", b.x1) && Num(r, "yMin", b.y0) && Num(r, "yMax", b.y1);
		if (b.ok && !(b.w() > 0.5 && b.w() < 3000.0 && b.h() > 0.5 && b.h() < 3000.0)) {
			b.ok = false;
		}
		return b;
	}

	// how visible a clip really is: its own _alpha times every parent's, 0 when it or a parent is hidden
	inline double Shown(const RE::GFxValue& a_clip)
	{
		double       alpha = 1.0;
		RE::GFxValue cur = a_clip;
		for (int i = 0; i < 10; ++i) {
			RE::GFxValue v;
			if (cur.GetMember("_visible", &v) && v.IsBool() && !v.GetBool()) {
				return 0.0;
			}
			double a = 100.0;
			if (Num(cur, "_alpha", a)) {
				alpha *= std::clamp(a, 0.0, 100.0) / 100.0;
			}
			RE::GFxValue parent;
			if (!cur.GetMember("_parent", &parent) || !parent.IsObject()) {
				break;
			}
			cur = parent;
		}
		return alpha;
	}

	inline std::string Lower(std::string a_text)
	{
		std::transform(a_text.begin(), a_text.end(), a_text.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
		return a_text;
	}

	inline int g_logged = 0;  // lines written so far (the first ones only, unless ShieldHudLog)

	template <class... Args>
	inline void Say(fmt::format_string<Args...> a_format, Args&&... a_args)
	{
		if (g_logged < 70 || g_log) {
			++g_logged;
			SKSE::log::info("shield hud: {}", fmt::format(a_format, std::forward<Args>(a_args)...));
		}
	}

	// ---- drawing ----

	inline void Rect(RE::GFxValue& a_clip, std::uint32_t a_rgb, double a_alpha)  // a square of 100 x 100 units, scaled to size
	{
		a_clip.Invoke("beginFill", std::array<RE::GFxValue, 2>{ RE::GFxValue(static_cast<double>(a_rgb)), RE::GFxValue(a_alpha) });
		a_clip.Invoke("moveTo", std::array<RE::GFxValue, 2>{ RE::GFxValue(0.0), RE::GFxValue(0.0) });
		a_clip.Invoke("lineTo", std::array<RE::GFxValue, 2>{ RE::GFxValue(100.0), RE::GFxValue(0.0) });
		a_clip.Invoke("lineTo", std::array<RE::GFxValue, 2>{ RE::GFxValue(100.0), RE::GFxValue(100.0) });
		a_clip.Invoke("lineTo", std::array<RE::GFxValue, 2>{ RE::GFxValue(0.0), RE::GFxValue(100.0) });
		a_clip.Invoke("lineTo", std::array<RE::GFxValue, 2>{ RE::GFxValue(0.0), RE::GFxValue(0.0) });
		a_clip.Invoke("endFill");
	}

	constexpr std::uint32_t kBack = 0x0A0A0C, kHealthBack = 0x1C0808, kHealth = 0xB82020, kShield = 0x2EA3FF, kShieldLow = 0xFF9A1E, kShieldCharge = 0x8FDCFF, kFlash = 0xFFFFFF;

	// the pieces of one bar: [0] backing, [1] health, [2] shield, [3] flash when the shield breaks
	inline const char* const kPlayer[5] = { "pl_back", "pl_hp", "pl_sh", "pl_fl", "pl_hb" };
	inline const char* const kEnemy[5] = { "en_back", "en_hp", "en_sh", "en_fl", "en_hb" };

	inline bool Build(RE::GFxMovieView* a_movie)
	{
		RE::GFxValue root;
		if (!a_movie->GetVariable(&root, "_root") || !root.IsObject()) {
			return false;
		}
		RE::GFxValue clip;
		if (!root.CreateEmptyMovieClip(&clip, "SkylandsShield", 9877)) {
			return false;
		}
		const std::uint32_t colors[5] = { kBack, kHealth, kShield, kFlash, kHealthBack };
		const double        alphas[5] = { 80.0, 100.0, 100.0, 100.0, 100.0 };
		for (int set = 0; set < 2; ++set) {
			for (int i = 0; i < 5; ++i) {
				RE::GFxValue part;
				if (!clip.CreateEmptyMovieClip(&part, (set ? kEnemy : kPlayer)[i], 10 + set * 5 + i)) {
					return false;
				}
				Rect(part, colors[i], alphas[i]);
				RE::GFxValue::DisplayInfo di;
				di.SetVisible(false);
				part.SetDisplayInfo(di);
			}
		}
		RE::GFxValue check;
		const bool   ok = a_movie->GetVariable(&check, "_root.SkylandsShield.pl_sh") && check.IsObject();
		Say("built in the game's HUD movie ({})", ok ? "parts found" : "PARTS MISSING");
		return ok;
	}

	inline void Put(RE::GFxMovieView* a_movie, const std::string& a_name, bool a_visible, double a_x = 0.0, double a_y = 0.0, double a_w = 0.0, double a_h = 0.0, double a_alpha = 100.0)
	{
		RE::GFxValue v;
		if (!a_movie->GetVariable(&v, ("_root.SkylandsShield." + a_name).c_str()) || !v.IsDisplayObject()) {
			return;
		}
		RE::GFxValue::DisplayInfo di;
		di.SetVisible(a_visible);
		if (a_visible) {
			di.SetPosition(a_x, a_y);
			di.SetScale((std::max)(0.01, a_w), (std::max)(0.01, a_h));  // the part is 100 units wide: a percentage equals the width in pixels
			di.SetAlpha(std::clamp(a_alpha, 0.0, 100.0));
		}
		v.SetDisplayInfo(di);
	}

	inline void Recolor(RE::GFxMovieView* a_movie, const std::string& a_name, std::uint32_t a_rgb)
	{
		RE::GFxValue v;
		if (a_movie->GetVariable(&v, ("_root.SkylandsShield." + a_name).c_str()) && v.IsDisplayObject()) {
			v.Invoke("clear");
			Rect(v, a_rgb, 100.0);
		}
	}

	// where a bar is and how large
	struct Layout
	{
		double cx = 0.0, cy = 0.0, w = 0.0, h = 0.0;
		double alpha = 1.0;       // how visible the game's own bar is (its clip and the clips around it)
		double meterAlpha = 1.0;  // the same for the bar's fill clip itself (the game fades that one when the health is full)
		bool   ok = false;
	};

	// what is remembered of one bar between frames
	struct Bar
	{
		const char* const* names = nullptr;
		Box                full;                // the game's bar when it was full (its extent at full strength), else the widest seen
		bool               fullSeen = false;
		int                colorState = -1;     // 0 shield blue, 1 recharging, 2 low
		bool               wasBroken = false;
		Clock::time_point  flashUntil{};
		bool               shown = false;
		RE::FormID         actor = 0;
	};

	inline Bar g_player{ kPlayer }, g_enemyBar{ kEnemy };

	inline void Hide(RE::GFxMovieView* a_movie, Bar& a_bar)
	{
		if (!a_bar.shown) {
			return;
		}
		a_bar.shown = false;
		for (int i = 0; i < 5; ++i) {
			Put(a_movie, a_bar.names[i], false);
		}
	}

	inline void Draw(RE::GFxMovieView* a_movie, Bar& a_bar, const Layout& a_at, const shield::View& a_view, Clock::time_point a_now)
	{
		const double t = std::chrono::duration<double>(a_now.time_since_epoch()).count();
		const bool   over = g_mode != 2;
		a_bar.shown = true;

		// the strip the bar occupies: over the game's bar, or a thin one just above it
		const double w = a_at.w;
		const double thin = (std::max)(4.0, a_at.h * 0.4);
		const double top = over ? a_at.cy - a_at.h * 0.5 : a_at.cy - a_at.h * 0.5 - thin - 3.0;
		const double hHalf = over ? a_at.h * 0.5 : thin;
		const double left = a_at.cx - w * 0.5;
		const auto   x = [&](double a_share) {
			const double width = w * a_share;
			return g_align == 1 ? left : g_align == 2 ? left + w - width : a_at.cx - width * 0.5;
		};
		const double alpha = a_at.alpha * 100.0;

		Put(a_movie, a_bar.names[0], true, left - 1.0, top - 1.0, w + 2.0, (over ? a_at.h : thin) + 2.0, alpha * 0.8);
		if (over) {
			const double share = std::clamp<double>(a_view.health, 0.0, 1.0);
			Put(a_movie, a_bar.names[1], share > 0.002, x(share), top + hHalf, w * share, hHalf, alpha);
			Put(a_movie, a_bar.names[4], false);
		} else if (g_health) {
			// the game's own bar shows health and shield added together, so it also drops when the shield takes a hit; this paints the inside of that bar (not its frame and caps)
			// with the real health alone, in the same place and fading with it
			const double ix = a_at.w * g_insetX, iy = a_at.h * g_insetY;
			const double iw = (std::max)(4.0, a_at.w - 2.0 * ix), ih = (std::max)(2.0, a_at.h - 2.0 * iy);
			const double share = std::clamp<double>(a_view.health, 0.0, 1.0);
			const double fx = g_align == 1 ? left + ix : g_align == 2 ? left + ix + iw - iw * share : a_at.cx - iw * share * 0.5;
			const double mAlpha = a_at.meterAlpha * 100.0;
			Put(a_movie, a_bar.names[4], mAlpha > 2.0, left + ix, a_at.cy - a_at.h * 0.5 + iy, iw, ih, mAlpha);
			Put(a_movie, a_bar.names[1], mAlpha > 2.0 && share > 0.002, fx, a_at.cy - a_at.h * 0.5 + iy, iw * share, ih, mAlpha);
		} else {
			Put(a_movie, a_bar.names[1], false);
			Put(a_movie, a_bar.names[4], false);
		}

		// the shield's colour: blue, lighter while it recharges, orange and pulsing when it is low
		const int state = a_view.low ? 2 : a_view.recharging ? 1 : 0;
		if (state != a_bar.colorState) {
			a_bar.colorState = state;
			Recolor(a_movie, a_bar.names[2], state == 2 ? kShieldLow : state == 1 ? kShieldCharge : kShield);
		}
		const double pulse = state == 2 ? 70.0 + 30.0 * std::sin(t * 10.0) : state == 1 ? 80.0 + 20.0 * std::sin(t * 6.0) : 100.0;
		const double share = std::clamp<double>(a_view.shield, 0.0, 1.0);
		Put(a_movie, a_bar.names[2], share > 0.002, x(share), top, w * share, hHalf, alpha * pulse / 100.0);

		// a white flash over the shield's half when the shield breaks
		if (a_view.broken && !a_bar.wasBroken) {
			a_bar.flashUntil = a_now + std::chrono::milliseconds(400);
		}
		a_bar.wasBroken = a_view.broken;
		const double left400 = std::chrono::duration<double>(a_bar.flashUntil - a_now).count();
		if (left400 > 0.0) {
			Put(a_movie, a_bar.names[3], true, left, top, w, hHalf, alpha * std::clamp(left400 / 0.4, 0.0, 1.0) * 0.75);
		} else {
			Put(a_movie, a_bar.names[3], false);
		}
	}

	// ---- finding the game's bars ----

	inline double VanillaFraction(RE::Actor* a_actor)
	{
		const auto ao = a_actor ? a_actor->AsActorValueOwner() : nullptr;
		if (!ao) {
			return 1.0;
		}
		const float max = a_actor->GetActorValueMax(RE::ActorValue::kHealth);
		return max > 1.0f ? std::clamp<double>(ao->GetActorValue(RE::ActorValue::kHealth) / max, 0.0, 1.0) : 1.0;
	}

	// the extent the game's bar has at full strength (see Bar::full): updated when the game shows it full, and grown when it is seen wider
	inline void Remember(Bar& a_bar, const Box& a_now, double a_vanilla)
	{
		if (!a_bar.fullSeen && (!a_bar.full.ok || a_now.w() > a_bar.full.w())) {
			a_bar.full = a_now;
		}
		if (a_vanilla >= 0.995) {
			a_bar.full = a_now;
			a_bar.fullSeen = true;
		}
	}

	inline bool PlayerLayout(RE::GFxValue& a_base, RE::GFxValue& a_root, RE::PlayerCharacter* a_player, Layout& a_out, bool a_look)
	{
		RE::GFxValue health, anim;
		const bool   haveHealth = a_base.GetMember("Health", &health) && health.IsDisplayObject();
		const bool   haveAnim = a_base.GetMember("HealthMeterAnim", &anim) && anim.IsDisplayObject();
		if (!haveHealth && !haveAnim) {
			return false;
		}
		Box boxAnim, boxHealth, boxMeter;
		if (haveAnim) {
			boxAnim = BoundsOf(anim, a_root);
		}
		if (haveHealth) {
			boxHealth = BoundsOf(health, a_root);
		}
		// the bar itself, as the first log showed: HealthMeter_mc inside the health clip (286 wide); its parents also hold the penalty meter (737 wide, the bar's longest possible extent)
		RE::GFxValue meter;
		bool         haveMeter = haveAnim && anim.GetMember("HealthMeter_mc", &meter) && meter.IsDisplayObject();
		if (!haveMeter) {
			haveMeter = haveHealth && health.GetMember("HealthMeter_mc", &meter) && meter.IsDisplayObject();
		}
		if (haveMeter) {
			boxMeter = BoundsOf(meter, a_root);
		}
		if (a_look) {
			RE::GFxValue hm;
			if (a_base.GetMember("HealthMeter", &hm) && hm.IsObject()) {
				std::string names;
				hm.VisitMembers([&](const char* a_name, const RE::GFxValue&) {
					if (names.size() < 600 && a_name) {
						names += std::string(a_name) + " ";
					}
				});
				Say("player bar: the game's HealthMeter object holds [{}]", names);
			}
			double last = -1.0;
			Num(a_base, "lastHealthMeterPercent", last);
			Say("player bar: lastHealthMeterPercent {:.1f}; HealthMeter_mc {}; [{:.0f},{:.0f} - {:.0f},{:.0f}]", last, haveMeter ? "found" : "missing", boxMeter.x0, boxMeter.y0, boxMeter.x1, boxMeter.y1);
			if (haveMeter) {
				std::vector<std::string> inner;
				meter.VisitMembers([&](const char* a_name, const RE::GFxValue& a_value) {
					if (inner.size() < 20 && a_name && a_value.IsDisplayObject()) {
						inner.push_back(a_name);
					}
				});
				for (const auto& name : inner) {
					RE::GFxValue child;
					if (meter.GetMember(name.c_str(), &child)) {
						const Box b = BoundsOf(child, a_root);
						Say("player bar: HealthMeter_mc.{} [{:.0f},{:.0f} - {:.0f},{:.0f}] alpha {:.2f}", name, b.x0, b.y0, b.x1, b.y1, Shown(child));
					}
				}
			}
		}
		if (a_look) {
			Say("player bar: HealthMeterAnim {} [{:.0f},{:.0f} - {:.0f},{:.0f}] alpha {:.2f}; Health {} [{:.0f},{:.0f} - {:.0f},{:.0f}] alpha {:.2f}", haveAnim ? "found" : "missing", boxAnim.x0, boxAnim.y0, boxAnim.x1, boxAnim.y1,
				haveAnim ? Shown(anim) : -1.0, haveHealth ? "found" : "missing", boxHealth.x0, boxHealth.y0, boxHealth.x1, boxHealth.y1, haveHealth ? Shown(health) : -1.0);
			for (const char* name : { "Health", "HealthMeterAnim" }) {
				RE::GFxValue clip;
				if (!a_base.GetMember(name, &clip) || !clip.IsDisplayObject()) {
					continue;
				}
				std::vector<std::string> kids;
				clip.VisitMembers([&](const char* a_name, const RE::GFxValue& a_value) {
					if (kids.size() < 24 && a_name && a_value.IsDisplayObject()) {
						kids.push_back(a_name);
					}
				});
				for (const auto& kid : kids) {
					RE::GFxValue child;
					if (clip.GetMember(kid.c_str(), &child)) {
						const Box b = BoundsOf(child, a_root);
						Say("player bar: {}.{} [{:.0f},{:.0f} - {:.0f},{:.0f}] alpha {:.2f}", name, kid, b.x0, b.y0, b.x1, b.y1, Shown(child));
					}
				}
			}
		}
		// the bar itself: the "...MeterAnim" clip when it has the shape of a bar, else the clip that holds it
		const Box* use = nullptr;
		if (boxMeter.ok && boxMeter.w() >= 20.0 && boxMeter.h() <= 80.0) {
			use = &boxMeter;
		} else if (boxAnim.ok && boxAnim.w() >= 20.0 && boxAnim.h() <= 80.0) {
			use = &boxAnim;
		} else if (boxHealth.ok && boxHealth.w() >= 20.0) {
			use = &boxHealth;
		}
		if (!use) {
			return false;
		}
		Remember(g_player, *use, VanillaFraction(a_player));
		const Box& ref = g_player.full.ok ? g_player.full : *use;
		a_out.cx = ref.cx() + g_dx;
		a_out.cy = ref.cy() + g_dy;
		a_out.w = g_w > 0.0f ? g_w : ref.w();
		a_out.h = g_h > 0.0f ? g_h : std::clamp(ref.h(), 8.0, 20.0);
		double alpha = 1.0;
		if (haveAnim) {
			alpha = (std::min)(alpha, Shown(anim));
		}
		if (haveHealth) {
			alpha = (std::min)(alpha, Shown(health));
		}
		a_out.alpha = g_follow ? alpha : 1.0;
		a_out.meterAlpha = g_follow && haveMeter ? Shown(meter) : 1.0;
		a_out.ok = true;
		return true;
	}

	inline bool EnemyLayout(RE::GFxValue& a_base, RE::GFxValue& a_root, RE::Actor* a_actor, Layout& a_out, bool a_look)
	{
		RE::GFxValue mc;
		static int   failed = 0;
		if (!a_base.GetMember("EnemyHealth_mc", &mc) || !mc.IsDisplayObject()) {
			if (failed++ < 3) {
				Say("enemy bar: EnemyHealth_mc is not a display object");
			}
			return false;
		}
		a_out.alpha = g_follow ? Shown(mc) : 1.0;
		a_out.meterAlpha = a_out.alpha;
		const Box whole = BoundsOf(mc, a_root);
		if (!whole.ok) {
			if (failed++ < 3) {
				Say("enemy bar: EnemyHealth_mc has no extent yet (alpha {:.2f}); it is tried again while an enemy with a shield is in the crosshair", a_out.alpha);
			}
			return false;
		}
		struct Kid
		{
			std::string name;
			Box         box;
		};
		std::vector<std::string> names;
		mc.VisitMembers([&](const char* a_name, const RE::GFxValue& a_value) {
			if (names.size() < 24 && a_name && a_value.IsDisplayObject()) {
				names.push_back(a_name);
			}
		});
		std::vector<Kid> kids;
		for (const auto& name : names) {
			RE::GFxValue child;
			if (mc.GetMember(name.c_str(), &child)) {
				kids.push_back({ name, BoundsOf(child, a_root) });
			}
		}
		if (a_look) {
			Say("enemy bar: EnemyHealth_mc [{:.0f},{:.0f} - {:.0f},{:.0f}] alpha {:.2f}, {} parts", whole.x0, whole.y0, whole.x1, whole.y1, Shown(mc), kids.size());
			for (const auto& kid : kids) {
				Say("enemy bar: EnemyHealth_mc.{} [{:.0f},{:.0f} - {:.0f},{:.0f}]{}", kid.name, kid.box.x0, kid.box.y0, kid.box.x1, kid.box.y1, kid.box.ok ? "" : " (empty)");
			}
		}
		// the bar: the widest part that is shaped like one and has "meter" or "bar" in its name, else one with "bracket", else the bottom of the whole clip
		const Kid* pick = nullptr;
		for (const char* word : { "meter", "bar", "bracket" }) {
			for (const auto& kid : kids) {
				if (kid.box.ok && kid.box.w() >= 40.0 && kid.box.h() <= 60.0 && Lower(kid.name).find(word) != std::string::npos && (!pick || kid.box.w() > pick->box.w())) {
					pick = &kid;
				}
			}
			if (pick) {
				break;
			}
		}
		Box bar = whole;
		if (pick) {
			bar = pick->box;
		} else {
			bar.y0 = whole.y1 - 14.0;
		}
		Remember(g_enemyBar, bar, VanillaFraction(a_actor));
		const Box& ref = g_enemyBar.full.ok ? g_enemyBar.full : bar;
		a_out.cx = ref.cx() + g_edx;
		a_out.cy = ref.cy() + g_edy;
		a_out.w = g_ew > 0.0f ? g_ew : ref.w();
		a_out.h = g_eh > 0.0f ? g_eh : std::clamp(ref.h(), 8.0, 20.0);
		a_out.ok = true;
		return true;
	}

	// the person the game's enemy bar is about: the one in the crosshair, kept while the crosshair is on nobody (the game keeps its bar up a moment)
	inline RE::FormID g_enemyId = 0;

	inline RE::Actor* EnemyActor(RE::PlayerCharacter* a_player)
	{
		if (const auto pick = RE::CrosshairPickData::GetSingleton()) {
			if (const auto ref = pick->GetActiveTarget().get()) {
				if (const auto actor = ref->As<RE::Actor>()) {
					if (actor != a_player) {
						g_enemyId = actor->GetFormID();
					}
				}
			}
		}
		return g_enemyId ? RE::TESForm::LookupByID<RE::Actor>(g_enemyId) : nullptr;
	}

	// Game thread, at the end of every shield update (33 ms).
	inline void Frame()
	{
		static bool              broken = false, lookedPlayer = false, lookedEnemy = false, waited = false;
		static int               frame = 0;
		static Layout            player, enemy;
		static Clock::time_point lastLog{};
		if (!g_on || broken) {
			return;
		}
		const auto ui = RE::UI::GetSingleton();
		const auto playerRef = RE::PlayerCharacter::GetSingleton();
		if (!ui || !playerRef) {
			return;
		}
		RE::GPtr<RE::GFxMovieView> movie = ui->GetMovieView("HUD Menu");
		if (!movie.get()) {
			return;
		}
		RE::GFxValue base, root;
		if (!movie->GetVariable(&root, "_root") || !root.IsObject() || !movie->GetVariable(&base, "_root.HUDMovieBaseInstance") || !base.IsObject()) {
			if (!waited) {
				waited = true;
				Say("the HUD's base clip is not there yet");
			}
			return;
		}
		RE::GFxValue mine;
		if (!movie->GetVariable(&mine, "_root.SkylandsShield") || !mine.IsObject()) {
			shield::g_stage = "shield display: build";
			if (!Build(movie.get())) {
				broken = true;
				Say("could not be built; the plain shield lines stay");
				return;
			}
			g_player.shown = g_enemyBar.shown = false;
			g_player.colorState = g_enemyBar.colorState = -1;
		}
		++frame;
		const auto now = Clock::now();

		// the player's bar
		shield::g_stage = "shield display: player";
		const auto view = shield::ViewOf(playerRef->GetFormID());
		if (view.has) {
			if (frame % 3 == 1 || !player.ok) {
				player.ok = PlayerLayout(base, root, playerRef, player, !lookedPlayer);
				lookedPlayer = lookedPlayer || player.ok;  // the bar's parts are told in the log once it has been found
			}
			if (player.ok && player.alpha > 0.02) {
				Draw(movie.get(), g_player, player, view, now);
				shield::g_displayLive = true;
			} else {
				Hide(movie.get(), g_player);
			}
		} else {
			Hide(movie.get(), g_player);
		}

		// the enemy's bar
		shield::g_stage = "shield display: enemy";
		shield::View eview;
		if (g_enemy) {
			if (const auto actor = EnemyActor(playerRef)) {
				if (!actor->IsDead()) {
					eview = shield::ViewOf(actor->GetFormID());
				}
				if (eview.has && (frame % 3 == 2 || !enemy.ok || g_enemyBar.actor != actor->GetFormID())) {
					enemy.ok = EnemyLayout(base, root, actor, enemy, !lookedEnemy);
					g_enemyBar.actor = actor->GetFormID();
					lookedEnemy = lookedEnemy || enemy.ok;
				}
			}
		}
		if (eview.has && enemy.ok && enemy.alpha > 0.02) {
			Draw(movie.get(), g_enemyBar, enemy, eview, now);
		} else {
			Hide(movie.get(), g_enemyBar);
		}

		if (g_log && now - lastLog > std::chrono::seconds(5)) {
			lastLog = now;
			Say("player {} at {:.0f},{:.0f} size {:.0f} x {:.0f} alpha {:.2f} (shield {:.0f} percent, health {:.0f} percent); enemy {} (shield {:.0f} percent)", player.ok ? "bar" : "no bar", player.cx, player.cy, player.w, player.h, player.alpha, view.shield * 100.0,
				view.health * 100.0, enemy.ok ? "bar" : "no bar", eview.shield * 100.0);
		}
	}

	// the settings file: returns true when the key was one of the display's
	inline bool Config(const std::string& a_key, const std::string& a_value)
	{
		const auto number = [&](float& a_out, float a_lo, float a_hi) {
			try {
				a_out = std::clamp(std::stof(a_value), a_lo, a_hi);
			} catch (...) {
			}
		};
		if (a_key == "ShieldHud") {
			g_on = a_value.find('0') == std::string::npos;
		} else if (a_key == "ShieldHudMode") {
			g_mode = a_value.find('2') != std::string::npos ? 2 : 1;
		} else if (a_key == "ShieldHudEnemy") {
			g_enemy = a_value.find('0') == std::string::npos;
		} else if (a_key == "ShieldHudFollow") {
			g_follow = a_value.find('0') == std::string::npos;
		} else if (a_key == "ShieldHudLog") {
			g_log = a_value.find('1') != std::string::npos;
		} else if (a_key == "ShieldHudHealth") {
			g_health = a_value.find('1') != std::string::npos;
		} else if (a_key == "ShieldHudInsetX") {
			number(g_insetX, 0.0f, 0.45f);
		} else if (a_key == "ShieldHudInsetY") {
			number(g_insetY, 0.0f, 0.45f);
		} else if (a_key == "ShieldHudAlign") {
			float v = 0.0f;
			try {
				v = std::stof(a_value);
			} catch (...) {
			}
			g_align = v >= 1.5f ? 2 : v >= 0.5f ? 1 : 0;
		} else if (a_key == "ShieldHudX") {
			number(g_dx, -1280.0f, 1280.0f);
		} else if (a_key == "ShieldHudY") {
			number(g_dy, -720.0f, 720.0f);
		} else if (a_key == "ShieldHudWidth") {
			number(g_w, 0.0f, 1280.0f);
		} else if (a_key == "ShieldHudHeight") {
			number(g_h, 0.0f, 200.0f);
		} else if (a_key == "ShieldHudEnemyX") {
			number(g_edx, -1280.0f, 1280.0f);
		} else if (a_key == "ShieldHudEnemyY") {
			number(g_edy, -720.0f, 720.0f);
		} else if (a_key == "ShieldHudEnemyWidth") {
			number(g_ew, 0.0f, 1280.0f);
		} else if (a_key == "ShieldHudEnemyHeight") {
			number(g_eh, 0.0f, 200.0f);
		} else {
			return false;
		}
		return true;
	}
}
