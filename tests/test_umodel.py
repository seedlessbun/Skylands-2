import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

from skylands_setup.bl2 import umodel  # noqa: E402
from skylands_setup.bl2.index import Index  # noqa: E402
import test_gunparts  # noqa: E402


def test_umodel_source_exports_and_reads(tmp_path):
    test_gunparts.build_install(tmp_path / "bl2")
    ix = Index(tmp_path / "bl2")
    log = []
    src = umodel.UModelSource(ix, log.append, [sys.executable, str(HERE / "fake_umodel.py")], tmp_path / "work")
    built = {"parts": {"Body": "GD_Weap_Pistol.Body.Pistol_Body_A", "Barrel": "GD_Weap_Pistol.Barrel.Pistol_Barrel_A"}}
    parts = src.gun_parts({"type": "pistol"}, built)
    assert parts is not None and len(parts) == 2, log
    assert src.stats["exported"] == 2 and src.stats["meshes"] == 2 and src.stats["textured"] >= 1, (src.stats, log)
    barrel = parts[1]
    assert sum(p[1] for p in barrel.positions) / len(barrel.positions) > 30  # socket offset and orientation as in the native method
    tex = src.take_textures()
    assert tex and all(v[:4] == b"DDS " for v in tex.values())


def test_umodel_failure_is_reported_not_raised(tmp_path):
    test_gunparts.build_install(tmp_path / "bl2")
    ix = Index(tmp_path / "bl2")
    log = []
    src = umodel.UModelSource(ix, log.append, [sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"], tmp_path / "work")
    assert src.gun_parts({"type": "pistol"}, {"parts": {"Body": "GD_Weap_Pistol.Body.Pistol_Body_A"}}) is None
    assert src.stats["export_failed"] >= 1 and any("failed" in m for m in log)


def test_find_exe_prefers_an_env_path(tmp_path, monkeypatch):
    exe = tmp_path / "mine.exe"
    exe.write_bytes(b"x")
    monkeypatch.setenv("SKYLANDS_UMODEL", str(exe))
    assert umodel.find_exe(tmp_path / "work", print) == [str(exe)]
    monkeypatch.delenv("SKYLANDS_UMODEL")
    assert umodel.find_exe(tmp_path / "work", print) is None
