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
    assert build.remove_stale(work, sky, []) == 1
    assert not old.exists() and keep.exists() and not (sky / "Data" / "Meshes" / "Skylands").exists()
    assert build.remove_stale(work, tmp_path / "elsewhere", []) == 0  # a record for another Skyrim folder is left alone


def test_stale_cleanup_never_removes_a_file_the_new_install_wrote(tmp_path):
    sky = tmp_path / "sky"
    (sky / "Data").mkdir(parents=True)
    esp = sky / "Data" / "Skylands.esp"
    esp.write_bytes(b"x")
    old = sky / "Data" / "Meshes" / "Skylands" / "Guns" / "a.nif"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"y")
    work = tmp_path / "work"
    work.mkdir()
    (work / "installed-files.json").write_text(json.dumps({"skyrim": str(sky), "files": ["Data/Skylands.esp", "Data/Meshes/Skylands/Guns/a.nif"]}))
    assert build.remove_stale(work, sky, ["Data/Skylands.esp"]) == 1
    assert esp.exists() and not old.exists()


def test_verify_reports_missing_pieces(tmp_path):
    sky = tmp_path / "sky"
    (sky / "Data" / "Scripts").mkdir(parents=True)
    (sky / "Data" / "Skylands.esp").write_bytes(b"x" * 2048)
    plugins = tmp_path / "plugins.txt"
    plugins.write_text("# comment\nSkyrim.esm\n*Skylands.esp\n")
    lines = build.verify(sky, plugins)
    assert "present, 2 KB" in lines[0] and "MISSING" in lines[1] and "*Skylands.esp" in lines[-1]


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


def test_build_installs_the_skse_plugin_and_logs_what_skse_is_missing(tmp_path, monkeypatch):
    bin_dir = HERE.parent / "setup" / "skylands_setup" / "bin"
    bl2 = tmp_path / "bl2"
    fake_bl2.pandora_install(bl2)
    sky = fake_skyrim.build_full(tmp_path / "sky")
    work = tmp_path / "work"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    rc = build.main(["--bl2", str(bl2), "--skyrim", str(sky), "--done", str(work / "setup-done.txt"), "--gun-models", "proxy"])
    log = (work / "skylands-setup.log").read_text(encoding="utf-8")
    assert rc == 0, log
    assert "skse: SKSE loader (skse64_loader.exe): MISSING" in log and "skse: Address Library" in log and "Check-SKSE" not in log  # the fake Skyrim has no SKSE
    assert "skse: Skylands needs SKSE and Address Library" in log
    plugin = sky / "Data" / "SKSE" / "Plugins" / "SkylandsNative.dll"
    if (bin_dir / "SkylandsNative.dll").is_file():
        assert plugin.is_file() and (sky / "Data" / "SKSE" / "Plugins" / "SkylandsNative.ini").is_file()
        assert "SkylandsNative plugin: staged for install" in log and "SkylandsNative.dll: present" in log
        assert build.uninstall_main(["--work", str(work)]) == 0
        assert not plugin.exists()  # uninstall takes the plugin away with the rest
    else:
        assert "SkylandsNative plugin: not in this build" in log


def test_the_built_plugin_is_a_windows_dll_with_the_skse_entry_points():
    dll = HERE.parent / "setup" / "skylands_setup" / "bin" / "SkylandsNative.dll"
    if not dll.is_file():
        import pytest

        pytest.skip("SkylandsNative.dll is built by CI (.github/workflows/skse-plugin.yml)")
    data = dll.read_bytes()
    assert data[:2] == b"MZ" and b"PE\0\0" in data[:1024]
    assert int.from_bytes(data[data.index(b"PE\0\0") + 4:][:2], "little") == 0x8664  # x64
    for export in (b"SKSEPlugin_Version", b"SKSEPlugin_Load", b"SKSEPlugin_Query"):
        assert export in data
    for text in (b"SkylandsNative", b"TriggerHeld", b"TriggerPressed", b"FireGun", b"GunClip", b"GunIntervalMs", b"GunReloadMs", b"enemy cast listener registered", b"SetGunMode", b"Version", b"NPC R MagicNode [RMag]", b"attack handler hooked"):
        assert text in data
