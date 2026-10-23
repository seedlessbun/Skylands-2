"""Borderlands 2's weapon shot sounds, made into WAV files Skyrim can play.

Borderlands 2's sound is Wwise (bl2/wwise.py): sound banks in Audio_Banks.pck, streamed audio in Audio_Streaming.pck. For every
(gun type, manufacturer) that Skylands has as a staff gun this finds the shot event, follows it to the audio files behind it, and decodes
each (Wwise packs its audio as Vorbis; the free command-line tool vgmstream turns it into a plain WAV, and setup downloads it into the work
folder as it does UModel; nothing from either game or the tools is shipped). The WAV is made mono, 16-bit, 44.1 kHz, because that is what
Skyrim plays as a positioned sound effect. Anything that fails is logged and that gun keeps the stand-in Skyrim sound.
"""

from __future__ import annotations

import array
import hashlib
import io
import json
import re
import struct
import subprocess
import time
import urllib.request
import wave
import zipfile
from pathlib import Path

from . import wwise

PACKS = ("WillowGame/CookedPCConsole/Audio_Banks.pck", "WillowGame/CookedPCConsole/Audio_Streaming.pck")
MANUFACTURER_NAMES = {"Bandit": ("BT", "Bandit"), "Tediore": ("Tediore",), "Maliwan": ("Maliwan",), "Hyperion": ("Hyperion",), "Dahl": ("Dahl",),
                      "Jakobs": ("Jakobs",), "Torgue": ("Torgue",), "Vladof": ("Vladof",)}
VARIANTS = 4  # audio files kept per gun type and manufacturer (the sound record picks one at random)
OUT_RATE = 44100
VGMSTREAM = ("https://github.com/vgmstream/vgmstream/releases/latest/download/vgmstream-win64.zip",
             "https://github.com/vgmstream/vgmstream-releases/releases/download/nightly/vgmstream-win64.zip")
EXE_NAMES = ("vgmstream-cli.exe", "vgmstream-cli", "test.exe")


def shot_events(kind: str, manufacturer: str) -> list[str]:
    """Borderlands 2's names (as the game's packages show them) of the events for one shot of a gun type from a manufacturer, best first."""
    out = []
    for m in MANUFACTURER_NAMES.get(manufacturer, (manufacturer,)):
        if kind == "smg":
            out += [f"Ak_Play_Wep_SMG_{m}_Shot_Short", f"Ak_Play_Wep_SMG_{m}_Shot"]
        elif kind == "assault_rifle":
            out += [f"Ak_Play_Wep_Rifle_{m}_Shot_Short", f"Ak_Play_Wep_Rifle_{m}_Shot"]
        elif kind == "pistol":
            out += [f"Ak_Play_Wep_Pistol_{m}_Shot"]
        elif kind == "shotgun":
            out += [f"Ak_Play_Wep_Shotgun_{m}_Shot"]
        elif kind == "sniper":
            out += [f"Ak_Play_Wep_Sniper_{m}_Shot", f"Ak_Play_Wep_Sniper_{m}_shot_01"]
        elif kind == "launcher":
            out += [f"Ak_Play_Wep_Rocket_Launcher_{m}_Shot"]
    return out


# ---- decoding -------------------------------------------------------------------------------------------------------------

def find_decoder(work: Path) -> list[str] | None:
    for d in (work, work / "tools", work / "vgmstream"):
        for n in EXE_NAMES:
            if (d / n).is_file():
                return [str(d / n)]
    return None


def download_decoder(work: Path, say) -> list[str] | None:
    dest = work / "vgmstream"
    for url in VGMSTREAM:
        try:
            say(f"  audio: downloading {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Skylands-setup)"})
            with urllib.request.urlopen(req, timeout=90) as r:
                blob = r.read()
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                dest.mkdir(parents=True, exist_ok=True)
                names = [n for n in z.namelist() if not n.endswith("/")]
                if not any(Path(n).name.lower().startswith("vgmstream-cli") or Path(n).name.lower() == "test.exe" for n in names):
                    raise zipfile.BadZipFile("no vgmstream-cli in the archive")
                for n in names:
                    (dest / Path(n).name).write_bytes(z.read(n))
            say(f"  audio: downloaded ({len(blob) // 1024} KB, sha256 {hashlib.sha256(blob).hexdigest()[:16]}...)")
            return find_decoder(work)
        except Exception as e:  # noqa: BLE001
            say(f"  audio: {url} failed ({type(e).__name__}: {str(e)[:100]})")
    return None


def wav_info(blob: bytes) -> tuple[int, int, int] | None:
    """(format tag, channels, bits) of a RIFF audio file, or None."""
    if blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        return None
    p = 12
    while p + 8 <= len(blob):
        tag, size = blob[p:p + 4], struct.unpack_from("<I", blob, p + 4)[0]
        if tag == b"fmt " and size >= 16:
            fmt, ch, _rate, _bps, _al, bits = struct.unpack_from("<HHIIHH", blob, p + 8)
            return fmt, ch, bits
        p += 8 + size + (size & 1)
    return None


def to_mono_wav(source: bytes, rate_out: int = OUT_RATE) -> bytes | None:
    """A PCM WAV (any channels, 16-bit) as mono 16-bit at `rate_out`, with the peak brought to about 90 percent of full scale."""
    try:
        with wave.open(io.BytesIO(source)) as w:
            ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, EOFError):
        return None
    if width != 2 or ch < 1 or not raw:
        return None
    samples = array.array("h")
    samples.frombytes(raw[:len(raw) - len(raw) % (2 * ch)])
    if struct.pack("=H", 1) != struct.pack("<H", 1):
        samples.byteswap()
    mono = [sum(samples[i:i + ch]) / ch for i in range(0, len(samples), ch)]
    if rate != rate_out and len(mono) > 1:
        out_n = max(1, round(len(mono) * rate_out / rate))
        step = (len(mono) - 1) / max(1, out_n - 1)
        resampled = []
        for i in range(out_n):
            pos = i * step
            j = int(pos)
            frac = pos - j
            nxt = mono[j + 1] if j + 1 < len(mono) else mono[j]
            resampled.append(mono[j] * (1 - frac) + nxt * frac)
        mono = resampled
    peak = max((abs(v) for v in mono), default=0)
    gain = 29000.0 / peak if peak > 0 else 1.0
    gain = min(gain, 4.0)
    out = array.array("h", [max(-32768, min(32767, round(v * gain))) for v in mono])
    if struct.pack("=H", 1) != struct.pack("<H", 1):
        out.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate_out)
        w.writeframes(out.tobytes())
    return buf.getvalue()


def decode(wem: bytes, work: Path, name: str, decoder: list[str] | None, say) -> bytes | None:
    """The mono WAV of one Wwise audio file: PCM is read directly, anything else goes through the decoder tool."""
    info = wav_info(wem)
    if info and info[0] == 1:
        return to_mono_wav(wem)
    if not decoder:
        say(f"  audio: {name}: codec {info[0] if info else 'unknown'} needs the decoder tool, which is not available")
        return None
    tmp = work / "audio" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    src, dst = tmp / f"{name}.wem", tmp / f"{name}.wav"
    src.write_bytes(wem)
    dst.unlink(missing_ok=True)
    try:
        r = subprocess.run([*decoder, "-o", str(dst), str(src)], capture_output=True, text=True, timeout=120, cwd=str(tmp))
    except (subprocess.TimeoutExpired, OSError) as e:
        say(f"  audio: {name}: the decoder failed ({type(e).__name__}: {e})")
        return None
    if r.returncode != 0 or not dst.is_file():
        say(f"  audio: {name}: the decoder returned {r.returncode}: {(r.stderr or r.stdout).strip()[-200:]}")
        return None
    return to_mono_wav(dst.read_bytes())


# ---- the pipeline ---------------------------------------------------------------------------------------------------------

def load(bl2: Path, say) -> wwise.Sounds | None:
    banks_path, stream_path = (bl2 / p for p in PACKS)
    if not banks_path.is_file():
        say(f"  audio: {banks_path} not found")
        return None
    s = wwise.Sounds()
    t0 = time.time()
    data = banks_path.read_bytes()
    pack = wwise.read_pack(data)
    say(f"  audio: Audio_Banks.pck {len(data) // 1048576} MB, layout [{pack.layout}], {len(pack.banks)} banks listed (magic match {pack.bank_score:.2f}), "
        f"{len(pack.sounds)} streamed entries (match {pack.sound_score:.2f})")
    s.add_banks(data, pack)
    if pack.sounds and pack.sound_score >= 0.9:
        s.add_streamed(data, pack)
    del data
    if stream_path.is_file():
        data = stream_path.read_bytes()
        pack = wwise.read_pack(data)
        say(f"  audio: Audio_Streaming.pck {len(data) // 1048576} MB, layout [{pack.layout}], {len(pack.sounds)} streamed files (RIFF match {pack.sound_score:.2f}), "
            f"{len(pack.banks)} banks")
        if pack.sound_score >= 0.5:
            s.add_streamed(data, pack)
        if pack.banks and pack.bank_score >= 0.9:
            s.add_banks(data, pack)
        del data
    kinds = {1: "settings", 2: "sound", 3: "action", 4: "event", 5: "random/sequence", 6: "switch", 7: "actor-mixer", 8: "bus", 9: "layer"}
    say(f"  audio: {len(s.banks)} sound banks (Wwise bank versions {sorted(s.versions)}), objects "
        + ", ".join(f"{kinds.get(k, k)} {v}" for k, v in sorted(s.counts.items())) + f"; {len(s.media_ids)} audio files known ({time.time() - t0:.0f} s)")
    return s


def extract_shot_sounds(bl2: Path, work: Path, wanted: list[tuple[str, str]], say, download: bool = True) -> dict[tuple[str, str], list[Path]]:
    """{(gun type, manufacturer): [WAV files]} for the guns in `wanted`; the files are in work/audio/wav. Never raises: a failure is logged."""
    out: dict[tuple[str, str], list[Path]] = {}
    try:
        return _extract(bl2, work, wanted, say, download, out)
    except Exception as e:  # noqa: BLE001 - a sound problem must never stop the install
        say(f"  audio: stopped by {type(e).__name__}: {str(e)[:200]}")
        return out


def _extract(bl2: Path, work: Path, wanted, say, download: bool, out: dict) -> dict:
    sounds = load(bl2, say)
    if sounds is None:
        return out
    wav_dir = work / "audio" / "wav"
    wav_dir.mkdir(parents=True, exist_ok=True)
    decoder = find_decoder(work)
    report: dict = {}
    for kind, manufacturer in sorted(set(wanted)):
        key = f"{kind}_{manufacturer}"
        chosen = None
        for event in shot_events(kind, manufacturer):
            for name, ident in wwise.event_ids(event):
                found = sounds.event_sounds(ident)
                if found:
                    chosen = (event, name, ident, found)
                    break
            if chosen:
                break
        if not chosen:
            tried = [f"{e} ({[hex(i) for _n, i in wwise.event_ids(e)][:2]})" for e in shot_events(kind, manufacturer)[:2]]
            say(f"  audio: {key}: no event found; tried {', '.join(tried)}")
            report[key] = "no event"
            continue
        event, name, ident, found = chosen
        media = []
        for obj in found:
            m = sounds.media_of(obj)
            if m is not None and m not in media:
                media.append(m)
        say(f"  audio: {key}: event {event} as '{name}' ({ident:08X}) -> {len(found)} sound objects, {len(media)} audio files {[f'{m:08X}' for m in media[:6]]}")
        files: list[Path] = []
        for m in media[:VARIANTS * 2]:
            if len(files) >= VARIANTS:
                break
            path = wav_dir / f"{key}_{m:08X}.wav"
            if not path.is_file():
                wem = sounds.audio(m)
                if wem is None:
                    say(f"  audio: {key}: audio file {m:08X} is not in the packs")
                    continue
                if decoder is None and download:
                    decoder = find_decoder(work) or download_decoder(work, say)
                    download = False
                wav = decode(wem, work, f"{key}_{m:08X}", decoder, say)
                if wav is None:
                    continue
                path.write_bytes(wav)
            files.append(path)
        if files:
            out[(kind, manufacturer)] = files
        report[key] = [p.name for p in files]
    say(f"  audio: {sum(len(v) for v in out.values())} shot sounds made for {len(out)} of {len(set(wanted))} gun type x manufacturer pairs")
    (work / "audio" / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return out


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
