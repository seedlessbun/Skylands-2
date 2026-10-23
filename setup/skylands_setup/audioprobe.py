"""python -m skylands_setup bl2audio [--bl2 DIR] [--out FILE]: what sound Borderlands 2 has and where (changes nothing).

Written before any Borderlands audio is used, because the way BL2 stores its weapon sounds (Wwise banks and streamed .wem files, or
Unreal sound cues and waves inside its packages) has to be seen on a real install first. The report lists the audio files outside the
packages, and for the packages the object classes and names that look like sound, with the weapon ones picked out.
"""

from __future__ import annotations

import re
import struct
import sys
import time
from collections import Counter
from pathlib import Path

from . import steam
from .bl2 import upk

AUDIO_EXT = {".pck", ".bnk", ".wem", ".fsb", ".fev", ".xwm", ".ogg", ".wav", ".mp3", ".at9", ".xma", ".bik", ".sab", ".sbc", ".awc", ".snd"}
SOUND_CLASS = re.compile(r"(?i)^(ak\w*|wwise\w*|fmod\w*|sound\w*|audio\w*)$")
WEAPON_WORD = re.compile(r"(?i)(weap|gun|pistol|smg|shotgun|sniper|rocket|launcher|rifle|reload|fire|shot|bullet|eridian|jakobs|maliwan|hyperion|vladof|dahl|bandit|tediore|torgue)")
SOUND_NAME = re.compile(r"(?i)^(ak|wwise|fmod|snd_|sound|audio|sfx|sc_|sw_|aud)|(_?(ak|snd|sfx|sound|audio)_)|(\.|_)(wem|bnk|wav|ogg)$")


def package_report(path: Path, out: list[str], budget: dict) -> None:
    """Class names of every export that looks like sound, from a full read of the package's export table (cheap: no object data)."""
    data, h = upk._names_image(path.read_bytes())  # noqa: SLF001 - the survey reads the same table the index does
    names = [n.decode("cp1252", errors="replace") for n in upk._name_table(data, h["name_offset"], h["name_count"])]  # noqa: SLF001
    sound = [n for n in names if SOUND_NAME.search(n)]
    classes = Counter(n for n in names if SOUND_CLASS.match(n))
    if not sound and not classes:
        return
    budget["packages"] += 1
    weapon = [n for n in sound if WEAPON_WORD.search(n)]
    out.append(f"{path.name}: {len(names)} names, {len(sound)} sound-looking, {len(weapon)} of those weapon-looking; classes {dict(classes)}")
    for n in weapon[:12]:
        out.append(f"    {n}")


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="skylands bl2audio")
    ap.add_argument("--bl2")
    ap.add_argument("--out", default="BL2-Audio-Report.txt")
    a = ap.parse_args(argv)
    bl2 = Path(a.bl2) if a.bl2 else steam.find("bl2")
    out_path = Path(a.out)
    lines = [f"skylands bl2audio 1  {time.strftime('%Y-%m-%d %H:%M:%S')}"]

    def say(msg: str) -> None:
        print(msg, flush=True)
        lines.append(msg)

    def save() -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not bl2 or not bl2.is_dir():
        say(f"Borderlands 2 not found ({bl2}). Run with --bl2 \"D:\\path\\Borderlands 2\".")
        save()
        return 2
    say(f"Borderlands 2 folder: {bl2}")
    ext_count: Counter = Counter()
    ext_size: Counter = Counter()
    audio_files: list[tuple[int, Path]] = []
    dirs: Counter = Counter()
    for p in bl2.rglob("*"):
        if not p.is_file():
            continue
        e = p.suffix.lower()
        size = p.stat().st_size
        ext_count[e] += 1
        ext_size[e] += size
        if e in AUDIO_EXT:
            audio_files.append((size, p))
            dirs[str(p.parent.relative_to(bl2))] += 1
    say("")
    say("File types (count, MB):")
    for e, c in ext_count.most_common(25):
        say(f"  {e or '(none)':8} {c:6}  {ext_size[e] / 1e6:10.1f}")
    say("")
    say(f"Audio-looking files outside the packages: {len(audio_files)} in {len(dirs)} folders")
    for d, c in dirs.most_common(20):
        say(f"  {d}: {c}")
    for size, p in sorted(audio_files, reverse=True)[:30]:
        say(f"  {size / 1e6:9.2f} MB  {p.relative_to(bl2)}")
    for e in (".bnk", ".wem", ".pck"):
        sample = [p for _s, p in audio_files if p.suffix.lower() == e][:5]
        for p in sample:
            try:
                head = p.read_bytes()[:16]
            except OSError:
                continue
            say(f"  first bytes of {p.name}: {head.hex(' ')}  {struct.unpack_from('<4s', head)[0]!r}")
    say("")
    say("Packages with sound-looking names:")
    budget = {"packages": 0}
    t0 = time.time()
    upks = sorted(bl2.rglob("*.upk"))
    for i, p in enumerate(upks):
        try:
            package_report(p, lines, budget)
        except Exception as e:  # noqa: BLE001 - a package that does not read is part of the report
            lines.append(f"{p.name}: could not be read ({type(e).__name__}: {e})")
        if i % 100 == 0:
            print(f"  {i}/{len(upks)} packages", flush=True)
    say(f"{budget['packages']} of {len(upks)} packages have sound-looking names ({time.time() - t0:.0f} s)")
    save()
    say("")
    say(f"Report written to {out_path}. Send it to Claude.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
