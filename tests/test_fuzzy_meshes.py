"""The fuzzy mesh search must only map names of the same gun type (0.33.0 put a pistol's magazine on a shotgun)."""
from pathlib import Path
from types import SimpleNamespace as N

from skylands_setup.bl2 import gunparts, upk


class _Pkg:
    def __init__(self, names):
        self._by_name = {n: [i + 1] for i, n in enumerate(names)}
        self._names = list(names)

    def _indexes(self):
        pass

    def obj_class(self, i):
        return "SkeletalMesh"

    def path_of(self, i):
        return f"Weap.X.{self._names[i - 1]}"


def _run(monkeypatch, tmp_path, names, left):
    f = tmp_path / "a.upk"
    f.write_bytes(b"x")
    monkeypatch.setattr(upk, "read_name_set", lambda p: set(names))
    src = gunparts.Bl2Source.__new__(gunparts.Bl2Source)
    src.log = lambda m, force=False: None
    src.ix = N(files=[f], groups={}, errors={}, package=lambda p: _Pkg(names))
    src.mesh_index = {}
    src._fuzzy_meshes(left)
    return src.mesh_index


def test_same_type_other_prefix_is_found(monkeypatch, tmp_path):
    got = _run(monkeypatch, tmp_path, ["shotgun_body_bandit"], {"sg_body_bandit"})
    assert set(got) == {"sg_body_bandit"}


def test_other_gun_types_are_never_mapped(monkeypatch, tmp_path):
    got = _run(monkeypatch, tmp_path, ["pistol_body_bandit", "ar_body_bandit", "smg_body_bandit", "launcher_body_bandit"],
               {"sg_body_bandit", "sr_body_bandit"})
    assert got == {}


def test_shotgun_survey_runs_on_a_fake_install(tmp_path):
    import fake_bl2
    from skylands_setup import shotgunprobe

    bl2 = tmp_path / "bl2"
    fake_bl2.pandora_install(bl2)
    cooked = bl2 / "WillowGame" / "CookedPCConsole"
    fake_bl2.level_package_importing(cooked / "Weap_Shotgun_Test.upk", ["SG_Body_Bandit", "shotgun_body_x"])
    out = tmp_path / "report.txt"
    assert shotgunprobe.main(["--bl2", str(bl2), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "Weap_Shotgun_Test.upk" in text and "sg_body_bandit" in text and "Report written" in text
