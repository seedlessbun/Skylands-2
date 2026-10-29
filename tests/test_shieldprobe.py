"""The shield survey (bl2shields) on a fake install with a few shield objects: it must find, dump and cross-reference them."""
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_bl2  # noqa: E402
from fake_bl2 import ObjBuilder  # noqa: E402

from skylands_setup import shieldprobe  # noqa: E402


def shield_install(root):
    fake_bl2.pandora_install(root)
    cooked = root / "WillowGame" / "CookedPCConsole"
    b = ObjBuilder()
    b.obj("D_Attributes.Shield.ShieldCapacity", "DesignerAttributeDefinition",
          b.st("BaseValue", "AttributeInitializationData", b.f("BaseValueConstant", 100.0) + b.f("BaseValueScaleConstant", 1.0)))
    b.obj("D_Attributes.Shield.ShieldRechargeRate", "DesignerAttributeDefinition",
          b.st("BaseValue", "AttributeInitializationData", b.f("BaseValueConstant", 12.0) + b.f("BaseValueScaleConstant", 1.0)))
    b.obj("GD_Shields.Name.Title_Standard", "ItemNamePartDefinition", b.s("PartName", "Shield"))
    b.obj("GD_Shields.Parts.Part_Nova", "ShieldPartDefinition", b.s("GestaltModeSkeletalMeshName", "Shield_Body_Nova")
          + b.o("ShieldCapacityAttribute", "D_Attributes.Shield.ShieldCapacity") + b.o("PrefixName", "GD_Shields.Name.Title_Standard"))
    b.obj("GD_Shields.Parts.Part_Spike", "ShieldPartDefinition", b"")
    b.obj("GD_Shields.Parts.Part_Spike:BehaviorProviderDefinition_0", "BehaviorProviderDefinition", b"")
    b.obj("GD_Shields.Parts.Part_Spike:BehaviorProviderDefinition_0:Behavior_SpikeOnHit_1", "Behavior_Explode", b.f("DamageAmount", 5.0))
    b.exports[b.paths["GD_Shields.Parts.Part_Spike"] - 1]["body"] = (
        struct.pack("<i", -1) + b.o("BehaviorProviderDefinition", "GD_Shields.Parts.Part_Spike:BehaviorProviderDefinition_0") + b.none())
    b.obj("GD_Shields.Parts.Part_Missing", "ShieldPartDefinition", b.s("GestaltModeSkeletalMeshName", "Shield_Body_Nowhere"))
    b.obj("GD_Shields.Definitions.Shield_Standard", "ShieldDefinition",
          b.st("ShieldMaxValue", "AttributeInitializationData", b.f("BaseValueConstant", 200.0) + b.f("BaseValueScaleConstant", 1.5)) +
          b.o("RechargeRate", "D_Attributes.Shield.ShieldRechargeRate") + b.s("ShieldType", "Nova"))
    b.obj("GD_Shields.Balance.Shield_Standard_Balance", "ShieldBalanceDefinition",
          b.o("InventoryDefinition", "GD_Shields.Definitions.Shield_Standard") + b.o("PartList", "GD_Shields.Parts.Part_Nova"))
    b.obj("GD_Itempools.Gear.Pool_Gear_All", "ItemPoolDefinition",
          b.arr_structs("BalancedItems", [b.o("InvBalanceDefinition", "GD_Shields.Balance.Shield_Standard_Balance") + b.f("Probability", 1.0)]))
    b.obj("GD_Itempools.Pools.Pool_Everything", "ItemPoolDefinition",
          b.arr_structs("BalancedItems", [b.o("ItmPoolDefinition", "GD_Itempools.Gear.Pool_Gear_All") + b.f("Probability", 0.2)]))
    b.obj("GD_Population_Shielded.Balance.PawnBalance_Shielded", "AIPawnBalanceDefinition",
          b.arr_structs("PlayThroughs", [b.i("PlayThrough", 1) + b.s("DisplayName", "Shielded Guy")
                                         + b.o("DefaultItemPoolIncludedLists", "GD_Itempools.Pools.Pool_Everything")]))
    b.obj("GD_Population_Plain.Balance.PawnBalance_Plain", "AIPawnBalanceDefinition",
          b.arr_structs("PlayThroughs", [b.i("PlayThrough", 1) + b.s("DisplayName", "Plain Guy")]))
    b.obj("UI_Shield.Tex.Shield_Bar", "Texture2D", b.i("SizeX", 256) + b.i("SizeY", 32))
    b.obj("Item_Shields.Mesh.GestaltDef_Shields_GestaltSkeletalMesh", "SkeletalMesh", b"")
    b.obj("Item_Shields.GestaltDef_Shields", "GestaltSkeletalMeshDefinition",
          b.o("GestaltSkeletalMesh", "Item_Shields.Mesh.GestaltDef_Shields_GestaltSkeletalMesh") +
          b.arr_structs("GestaltInfos", [b.arr_structs("Parts", [
              b.s("SkeletalMeshFragmentName", "Shield_Body_Nova") + b.i("MaterialIndex", 0) + b.i("FirstIndex", 0) + b.i("NumPrimitives", 12)])]))
    (cooked / "Startup_Shields_Fake.upk").write_bytes(b.build())


def test_shield_survey_finds_and_follows_shield_objects(tmp_path):
    bl2 = tmp_path / "bl2"
    shield_install(bl2)
    out = tmp_path / "report.txt"
    assert shieldprobe.main(["--bl2", str(bl2), "--out", str(out), "--no-audio", "--minutes", "2"]) == 0
    text = out.read_text(encoding="utf-8")
    for needle in (
        "ShieldDefinition",  # class census
        "GD_Shields.Definitions.Shield_Standard",
        "ShieldMaxValue=200.0*1.5",  # the one-line brief of an initialisation struct
        "D_Attributes.Shield.ShieldCapacity",  # followed from the part
        "Pool_Gear_All",  # a pool that holds the shield
        "indirect GD_Itempools.Pools.Pool_Everything",  # and one that holds it through another pool
        "PawnBalance_Shielded",  # an enemy that carries one
        "Shield_Bar",  # HUD art
        "GD_Shields.Parts.Part_Missing",  # part whose fragment is not in the gestalt definition
        "not a fragment of the shield gestalt",
        "part Shield_Body_Nova",
        "Behavior_SpikeOnHit_1 [Behavior_Explode]",  # the nested behaviour of a part, which no property points to
        "DamageAmount: 5.0",
        "Finished. Report written",
    ):
        assert needle in text, needle
    enemy_section = text.split("7. Which enemy types carry shields")[1].split("========")[0]
    assert "PawnBalance_Plain" not in enemy_section.split("a few of them in full")[0]


def test_shield_survey_without_shield_data_still_reports(tmp_path):
    bl2 = tmp_path / "bl2"
    fake_bl2.pandora_install(bl2)
    out = tmp_path / "report.txt"
    assert shieldprobe.main(["--bl2", str(bl2), "--out", str(out), "--no-audio", "--minutes", "1"]) == 0
    assert "Finished. Report written" in out.read_text(encoding="utf-8")


def test_shield_survey_reports_a_missing_install(tmp_path):
    out = tmp_path / "report.txt"
    assert shieldprobe.main(["--bl2", str(tmp_path / "nope"), "--out", str(out)]) == 2
    assert "not found" in out.read_text(encoding="utf-8")


def test_flash_movie_text_is_read_out_of_an_export():
    import re
    import zlib

    body = b"\x00" * 10 + b"ShieldBar_mc\x00HealthBar\x00junk"
    swf = b"CWS\x0a" + (len(body) + 8).to_bytes(4, "little") + zlib.compress(body)
    note, hits = shieldprobe.swf_strings(b"prefix" + swf + b"tail", re.compile("shield|health", re.I))
    assert hits == ["ShieldBar_mc", "HealthBar"] and "CWS" in note
    assert shieldprobe.swf_strings(b"no movie here", re.compile("x")) is None
