"""0.62.2: the combat-AI crash (ammo with no projectile) and NPCs picking up Skylands loot."""
import pathlib
import struct

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_loose_loot_is_marked_no_ai_acquire_and_an_npc_pickup_is_dropped_again():
    src = (ROOT / "native/skse/src/despawn.h").read_text()
    assert "RE::TESObjectREFR::RecordFlags::kNoAIAcquire" in src and "AddChange(RE::TESForm::ChangeFlags::kFlags)" in src
    assert "if (NoAcquire(a_ref))" in src  # every loose item, at each scan, also with Despawn=0
    assert "(!g_on && !g_noPickup)" in src
    # only a pickup from the world (a reference), never an AddItem we did ourselves (the given shields, relics and guns)
    assert "a_event->oldContainer == 0" in src and "a_event->reference)" in src and "!taker->IsPlayerRef()" in src
    body = src[src.index("class DropSink"):]
    rarity_at = body.index("const int  rarity = RarityOf(base);")
    assert rarity_at < body.index("const std::lock_guard guard(g_lock);"), "RarityOf takes g_lock: call it before the guard"
    assert "shield::Queue([who, what, count, rarity]()" in body and "RE::ITEM_REMOVE_REASON::kDropping" in body
    assert 'a_key == "NoNpcPickup"' in src
    assert "NoNpcPickup=1" in (ROOT / "setup/skylands_setup/skse.py").read_text()


def test_staff_ammo_items_carry_the_bolts_projectile():
    src = (ROOT / "setup/skylands_setup/generate.py").read_text()
    assert 'struct.pack("<IIfI", ammo_proj, 0, 1.0, STAFF_AMMO_VALUE[kind])' in src
    assert 'struct.pack("<IIfI", 0, 0, 1.0, STAFF_AMMO_VALUE[kind])' not in src
