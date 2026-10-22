import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "setup"))

from skylands_setup import skse  # noqa: E402


def fake_exe(path: Path, version: tuple[int, int, int, int]) -> None:
    """A file that has a version resource block somewhere inside it, as a Windows executable does."""
    ms, ls = (version[0] << 16) | version[1], (version[2] << 16) | version[3]
    block = struct.pack("<IIIIIIIIIIIII", 0xFEEF04BD, 0x00010000, ms, ls, ms, ls, 0x3F, 0, 4, 1, 0, 0, 0)
    path.write_bytes(b"MZ" + b"\0" * 300 + b"\xbd\x04\xef\x00" + block + b"\0" * 200)  # a near miss first, then the real block


def test_exe_version_reads_the_fixed_file_info(tmp_path):
    fake_exe(tmp_path / "SkyrimSE.exe", (1, 6, 1170, 0))
    assert skse.exe_version(tmp_path / "SkyrimSE.exe") == (1, 6, 1170, 0)
    assert skse.exe_version(tmp_path / "missing.exe") is None


def test_status_names_what_is_missing(tmp_path):
    fake_exe(tmp_path / "SkyrimSE.exe", (1, 6, 1170, 0))
    st = skse.status(tmp_path)
    assert not st.ready and not st.loader and st.skse_dll is None and st.address_library is None
    text = "\n".join(skse.describe(st))
    assert "1.6.1170.0" in text and "skse64_loader.exe" in text and "skse64_1_6_1170.dll" in text and "MISSING" in text
    assert skse.SKSE_DOWNLOAD in text and skse.ADDRESS_LIBRARY in text and "skse64_loader.exe (not Steam's Play button" in text


def test_status_is_ready_with_skse_for_this_runtime_and_address_library(tmp_path):
    fake_exe(tmp_path / "SkyrimSE.exe", (1, 6, 1170, 0))
    (tmp_path / "skse64_loader.exe").write_bytes(b"MZ")
    (tmp_path / "skse64_1_6_1170.dll").write_bytes(b"MZ")
    plugins = tmp_path / "Data" / "SKSE" / "Plugins"
    plugins.mkdir(parents=True)
    (plugins / "versionlib-1-6-1170-0.bin").write_bytes(b"\0")
    st = skse.status(tmp_path)
    assert st.ready and st.skse_dll == "skse64_1_6_1170.dll" and st.address_library == "versionlib-1-6-1170-0.bin" and not st.plugin
    assert not any("MISSING" in line for line in skse.describe(st))


def test_skse_for_another_runtime_is_not_ready(tmp_path):
    fake_exe(tmp_path / "SkyrimSE.exe", (1, 6, 1170, 0))
    (tmp_path / "skse64_loader.exe").write_bytes(b"MZ")
    (tmp_path / "skse64_1_5_97.dll").write_bytes(b"MZ")
    st = skse.status(tmp_path)
    assert not st.ready and st.skse_dll is None and st.skse_dlls == ["skse64_1_5_97.dll"]
    assert "found for another version: skse64_1_5_97.dll" in "\n".join(skse.describe(st))


def test_stage_plugin_copies_the_dll_and_writes_the_settings(tmp_path):
    bin_dir, stage = tmp_path / "bin", tmp_path / "stage"
    bin_dir.mkdir()
    assert skse.stage_plugin(stage, bin_dir) is None  # no DLL built yet
    (bin_dir / skse.PLUGIN_DLL).write_bytes(b"MZ\x90")
    assert skse.stage_plugin(stage, bin_dir) == "Data/SKSE/Plugins/SkylandsNative.dll"
    assert (stage / "Data" / "SKSE" / "Plugins" / "SkylandsNative.dll").read_bytes() == b"MZ\x90"
    assert "Convergence=3000" in (stage / "Data" / "SKSE" / "Plugins" / "SkylandsNative.ini").read_text()
