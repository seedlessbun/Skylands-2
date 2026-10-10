import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))

from skylands_setup.skyrim import esp  # noqa: E402
from skylands_setup.skyrim.esm import read_plugin  # noqa: E402


def test_plugin_roundtrip(tmp_path):
    p = esp.Plugin("Skylands.esp", ["Skyrim.esm", "Update.esm", "Dawnguard.esm"])
    word = p.new("WOOP", "SkylandsWord_Deception").add("FULL", esp.zstr("Decepti0n")).add("TNAM", esp.zstr("Decepti0n"))
    q = p.new("QUST", "SkylandsClassQuest")
    q.add("VMAD", esp.vmad([("SkylandsClassQuest", [("Words", esp.P_OBJECT_ARRAY, [word.form_id]),
                                                     ("StarterGun", esp.P_OBJECT, 0x0001234)])], quest=True))
    big = p.new("MESG", "SkylandsClassChoice").add("DESC", b"x" * 70000 + b"\0")
    over = esp.Rec("WEAP", 0x02000801, [("EDID", esp.zstr("DLC1Crossbow")), ("DATA", b"\0" * 10)], flags=esp.REC_COMPRESSED)
    p.override(over)
    out = tmp_path / "Skylands.esp"
    out.write_bytes(p.encode())
    tes4, recs = read_plugin(out, {"WOOP", "QUST", "MESG", "WEAP"})
    assert tes4.flags & esp.FLAG_ESL
    assert [d.rstrip(b"\0") for s, d in tes4.subrecords if s == "MAST"] == [b"Skyrim.esm", b"Update.esm", b"Dawnguard.esm"]
    assert struct.unpack("<fII", tes4.first("HEDR"))[1] == 4
    assert recs["WOOP"][0].form_id == 0x03000800 and recs["WOOP"][0].edid == "SkylandsWord_Deception"
    v = recs["QUST"][0].first("VMAD")
    assert v[:6] == struct.pack("<hhH", 5, 2, 1) and v.endswith(b"\x02\x00\x00\x00\x00\x00\x00")
    assert len(recs["MESG"][0].first("DESC")) == 70001  # XXXX-sized subrecord
    assert recs["WEAP"][0].edid == "DLC1Crossbow"  # compressed override reads back
    assert big.form_id == 0x03000802
