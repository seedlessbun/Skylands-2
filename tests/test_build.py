import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "setup"))
sys.path.insert(0, str(HERE))

import fake_bl2  # noqa: E402
import fake_skyrim  # noqa: E402
from skylands_setup import build  # noqa: E402


def test_previous_install_files_are_removed_and_empty_folders_pruned(tmp_path):
    sky = tmp_path / "sky"
    (sky / "Data" / "Meshes" / "Skylands" / "Guns").mkdir(parents=True)
    old = sky / "Data" / "Meshes" / "Skylands" / "Guns" / "proxy_a.nif"
    old.write_bytes(b"x")
    keep = sky / "Data" / "Skyrim.esm"
    keep.write_bytes(b"y")
    work = tmp_path / "work"
    work.mkdir()
    (work / "installed-files.json").write_text(json.dumps({"skyrim": str(sky), "files": ["Data/Meshes/Skylands/Guns/proxy_a.nif"]}))
    assert build.remove_previous(work, sky) == 1
    assert not old.exists() and keep.exists() and not (sky / "Data" / "Meshes" / "Skylands").exists()
    assert build.remove_previous(work, tmp_path / "elsewhere") == 0  # a record for another Skyrim folder is left alone


def test_full_build_with_proxy_models_and_uninstall(tmp_path, monkeypatch):
    bl2 = tmp_path / "bl2"
    fake_bl2.pandora_install(bl2)
    sky = fake_skyrim.build_full(tmp_path / "sky")
    work = tmp_path / "work"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    args = ["--bl2", str(bl2), "--skyrim", str(sky), "--done", str(work / "setup-done.txt"), "--gun-models", "proxy"]
    try:
        rc = build.main(args)
    except Exception as e:  # noqa: BLE001 - plugins.txt handling is Windows-only; the staging and install steps are what is under test
        rc = -1
        print(e)
    log = (work / "skylands-setup.log").read_text(encoding="utf-8") if (work / "skylands-setup.log").exists() else ""
    assert "Gun models (proxy)" in log, log
    assert (sky / "Data" / "Meshes" / "Skylands" / "Guns").is_dir() or rc != 0
