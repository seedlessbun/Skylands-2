"""Runs game.py's logic against the fake SDK and world in fake_sdk.py (Python logic only)."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mod"))
sys.path.insert(0, str(HERE))

import fake_sdk  # noqa: E402
import fake_skyrim  # noqa: E402


@pytest.fixture(scope="module")
def game(tmp_path_factory):
    settings = tmp_path_factory.mktemp("settings")
    sky = fake_skyrim.build(tmp_path_factory.mktemp("sky"))
    fake_sdk.install(str(settings))
    import os
    os.environ["SKYLANDS_SKYRIM_DIR"] = str(sky)
    for m in [m for m in sys.modules if m.startswith("skylands")]:
        del sys.modules[m]
    g = importlib.import_module("skylands.game")
    g._load_skyrim()
    assert g.RULES is not None, g.LOAD_ERROR
    return g


def tick(g, n=1, dt=0.1):
    for _ in range(n):
        g.on_tick(None, NS(DeltaTime=dt))


def test_opening_and_race(game):
    w = fake_sdk.make_world()
    game.on_load()
    game.on_possess()
    tick(game, 30)
    box = fake_sdk.SHOWN[-1]
    assert box.title == "Hey, you."
    assert "finally awake" in box.message
    box.on_exit(box)
    races = fake_sdk.SHOWN[-1]
    assert races.title == "Choose your race" and races.prevent_cancelling
    nord = next(b for b in races.buttons if b.name == "Nord")
    assert "Two-Handed +10" in nord.tip
    races.on_select(races, nord)
    assert game.STATE["race"] == "NordRace"
    assert game.RULES.skill_level(game.STATE, "AVTwoHanded") == 25
    game.on_save()
    assert game.progress.value["race"] == "NordRace"
    w.pc.Pawn.calls.clear()


def test_shout_pushes_only_in_front(game):
    w = fake_sdk.make_world()
    game.STATE.setdefault("race", "NordRace")
    tick(game, 1)
    game.shout()
    assert [c[0] for c in w.front.calls] == ["TakeDamage", "AddVelocity"]
    assert w.behind.calls == [] and w.far.calls == []
    push = w.front.calls[1][1]["NewVelocity"]
    assert push.X > 0 and push.Z > 0
    assert any(c[0] == "Camera" for c in w.pc.calls)
    game.shout()  # still cooling down
    assert len(w.front.calls) == 2
    tick(game, 1, dt=60)
    assert any(t == "Unrelenting Force" and m == "ready" for t, m in game._messages + fake_sdk.HUD)


def test_damage_out_scaled_and_xp(game):
    w = fake_sdk.make_world()
    game.STATE["skills"]["AVOneHanded"]["level"] = 65  # +20% pistol damage
    seen = {}
    args = NS(Damage=100.0, DamageType=fake_sdk.FakeObj("WillowDmgSource_Pistol"), InstigatedBy=w.pc)
    before = game.STATE["skills"]["AVOneHanded"]["xp"]
    target = w.front
    target.bWasLastDamageACriticalHit = False
    res = game.enemy_damage(target, args, None, lambda a: seen.setdefault("dmg", a.Damage))
    assert res is game.Block
    assert seen["dmg"] == pytest.approx(120.0)
    assert game.STATE["skills"]["AVOneHanded"]["xp"] > before
    other = NS(Damage=100.0, DamageType=args.DamageType, InstigatedBy=fake_sdk.FakeObj("AI"))
    assert game.enemy_damage(target, other, None, lambda a: None) is None


def test_damage_in_reduced(game):
    w = fake_sdk.make_world()
    game.STATE["skills"]["AVBlock"]["level"] = 65  # -10% with shield up
    seen = {}
    res = game.player_damage(w.me, NS(Damage=50.0), None, lambda a: seen.setdefault("dmg", a.Damage))
    assert res is game.Block and seen["dmg"] == pytest.approx(45.0)


def test_menus_and_perks(game):
    fake_sdk.make_world()
    game.STATE["points"] = 1
    game.show_skills_menu()
    menu = fake_sdk.SHOWN[-1]
    assert len(menu.buttons) == 18 and "Perk points: 1" in menu.title
    oh = next(b for b in menu.buttons if b.name.startswith("One-Handed"))
    menu.on_select(menu, oh)
    perks = fake_sdk.SHOWN[-1]
    armsman = next(b for b in perks.buttons if "Armsman" in b.name)
    assert armsman.name.startswith("+")
    perks.on_select(perks, armsman)
    assert 0x000BABE4 in game.STATE["perks"] and game.STATE["points"] == 0
    back = fake_sdk.SHOWN[-1]
    back.on_select(back, next(b for b in back.buttons if b.name == "Back"))
    assert len(fake_sdk.SHOWN[-1].buttons) == 18


def test_money_pickup_and_vendor(game):
    w = fake_sdk.make_world()
    game.STATE["skills"]["AVPickpocket"]["level"] = 35  # +10%
    game._last["money"] = None
    tick(game, 1)
    w.pri.money += 200
    tick(game, 1)
    assert w.pri.money == 100 + 200 + 20
    tick(game, 3)
    assert w.pri.money == 320  # no double counting
    game.vendor_buy_pre(None, NS(WPC=w.pc))
    w.pri.money -= 100
    game.vendor_buy_post(None, NS(WPC=w.pc))
    assert w.pri.money >= 220


def test_ticks_survive_injury_and_regen(game):
    w = fake_sdk.make_world()
    game.STATE["skills"]["AVRestoration"]["level"] = 100
    w.me.hp = 100.0
    tick(game, 20)
    assert w.me.hp > 100.0
    w.me.injured = True
    tick(game, 2)
    assert not any("Error" in str(x) for x in fake_sdk.LOG)
