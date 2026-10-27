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
