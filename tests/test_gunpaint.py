"""0.63.0: guns painted from Borderlands 2's own material (masks x the instance's shadow/midtone/highlight colours, pattern)."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))

from skylands_setup.bl2 import gunmesh, gunpaint  # noqa: E402
from skylands_setup.skyrim import dxt  # noqa: E402


class FakeIx:
    def __init__(self, props):
        self.p = props

    def props(self, path):
        return self.p.get(path)


def arr(*items):
    return {"type": "Array", "items": list(items)}


def ix_with(pattern=False):
    return FakeIx({
        "Mat.Child": {"Parent": "Mat.Master", "VectorParameterValues": arr({"ParameterName": "p_AColorMidtone", "ParameterValue": [1.0, 0.0, 0.0, 1.0]})},
        "Mat.Master": {"TextureParameterValues": arr({"ParameterName": "p_Masks", "ParameterValue": "Weap_SMG.Tex.Weap_SMG_Comp"},
                                                     {"ParameterName": "p_Diffuse", "ParameterValue": "Common.Weap_AssaultSubSniper_Comp"},
                                                     *([{"ParameterName": "p_Pattern", "ParameterValue": "Pat.Stripes"}] if pattern else [])),
                       "VectorParameterValues": arr({"ParameterName": "p_AColorMidtone", "ParameterValue": [0.0, 1.0, 0.0, 1.0]},
                                                    {"ParameterName": "p_BColorMidtone", "ParameterValue": [0.0, 0.0, 1.0, 1.0]},
                                                    {"ParameterName": "p_DColor", "ParameterValue": [1.0, 1.0, 1.0, 1.0]},
                                                    {"ParameterName": "p_PatternChannelScale", "ParameterValue": [1.0, 0.0, 0.0, 0.0]},
                                                    {"ParameterName": "p_PatternColor", "ParameterValue": [1.0, 1.0, 1.0, 1.0]})},
    })


def images(side):
    """Masks: left half region A (red), right half region B (green); shading: SMG channel (green) at mid grey."""
    masks = bytearray(side * side * 3)
    shade = bytearray(side * side * 3)
    for y in range(side):
        for x in range(side):
            o = (y * side + x) * 3
            masks[o if x < side // 2 else o + 1] = 255
            shade[o + 1] = 128
    return bytes(masks), bytes(shade)


def test_the_child_colour_wins_and_regions_take_their_midtone():
    p = gunpaint.material_params(ix_with(), "Mat.Child")
    assert p["vector"]["p_acolormidtone"] == [1.0, 0.0, 0.0, 1.0] and p["vector"]["p_bcolormidtone"] == [0.0, 0.0, 1.0, 1.0]
    assert p["texture"]["p_masks"] == "Weap_SMG.Tex.Weap_SMG_Comp"
    S = gunpaint.SIDE
    masks, shade = images(S)
    painter = gunpaint.Painter(ix_with(), None, print)
    painter._image = lambda path, side: (side, side, masks if "Weap_SMG" in path else shade)
    dds, note = painter.paint("Mat.Child", "smg")
    assert "channel G" in note
    w, h, rgb = dxt.decode(dds)
    assert (w, h) == (S, S)
    left = rgb[(S // 2 * S + 10) * 3:(S // 2 * S + 10) * 3 + 3]
    right = rgb[(S // 2 * S + S - 10) * 3:(S // 2 * S + S - 10) * 3 + 3]
    assert left[0] > 200 and left[1] < 40 and left[2] < 40, left  # region A: the child's red midtone
    assert right[2] > 200 and right[0] < 40 and right[1] < 40, right  # region B: blue
    assert painter.paint("Mat.Child", "rocket_launcher_of_doom") is None  # unknown gun type: no paint, the old colour stays


def test_a_pattern_darkens_only_its_regions():
    S = gunpaint.SIDE
    masks, shade = images(S)
    stripes = bytes(255 if (x // 16) % 2 else 0 for y in range(256) for x in range(256) for _ in range(3))
    painter = gunpaint.Painter(ix_with(pattern=True), None, print)
    painter._image = lambda path, side: (side, side, stripes) if "Pat" in path else (side, side, masks if "Weap_SMG" in path else shade)
    dds, note = painter.paint("Mat.Child", "smg")
    assert "pattern Stripes" in note
    _w, _h, rgb = dxt.decode(dds)
    row = S // 2
    reds = {rgb[(row * S + x) * 3] > 128 for x in range(0, S // 2, 4)}
    assert reds == {True, False}  # region A striped
    blues = {rgb[(row * S + x) * 3 + 2] > 200 for x in range(S // 2 + 8, S, 4)}
    assert blues == {True}  # region B untouched (its pattern scale is 0)


def test_fast_dxt1_keeps_colours_close():
    S = 64
    rgb = bytes(v for y in range(S) for x in range(S) for v in ((x * 4) % 256, (y * 4) % 256, 128))
    _w, _h, back = dxt.decode(gunpaint.encode_fast(S, S, rgb))
    err = sum(abs(a - b) for a, b in zip(rgb, back)) / len(rgb)
    assert err < 12, err


def test_skinned_vertex_uvs_come_after_the_position_first():
    import struct
    # 44-byte element: 16 bytes of tangents/influences that read as small halves, position at 16, the real UVs (0.1..0.9) at 28
    n = 64
    data = bytearray()
    for i in range(n):
        data += struct.pack("<8e", 0.01 * i, -0.02 * i, 0.3, -0.4, 0.05 * (i % 7), 0.2, -0.1, 0.15)
        data += struct.pack("<3f", float(i), 2.0 * i, 3.0)
        data += struct.pack("<2e", 0.1 + 0.8 * i / n, 0.9 - 0.8 * i / n) + b"\0" * 12
    uv = gunmesh.element_uvs(bytes(data), 0, 44, n, 16)
    assert uv and abs(uv[0][0] - 0.1) < 0.01 and abs(uv[-1][1] - (0.9 - 0.8 * 63 / 64)) < 0.01, uv[:3]
