"""Borderlands 2's enemy voices (battle dialog, `Ak_Play_VOBD_<speaker>_<line>`): read from a language's voice pack, the language-free sound pack of the same folder,
and the streamed audio of both (docs/badass-roadmap.md 1.1c). Used by the badass survey (`bl2badass --voice`) and the installer (voices of the Pandora bandits)."""

from __future__ import annotations

from pathlib import Path


class VoiceSet:
    """One language's voices: its bank pack, its streamed audio, and the language-free bank pack of the same folder (which can hold the sound objects the
    voice events lead to: the first voice survey loaded each pack on its own and found the base game's events but no sounds behind them)."""

    def __init__(self, lang_banks: Path) -> None:
        from . import wwise

        self.lang_banks = lang_banks
        self.dir = lang_banks.parent
        self.sfx_dir = self.dir.parent
        self.snd = wwise.Sounds()
        self.stream_index: dict[int, tuple[Path, int, int]] = {}
        self.files: list[str] = []

    def load(self, ctx=None) -> None:
        from . import wwise

        stem = self.lang_banks.name.replace("Audio_Banks", "Audio_Streaming")
        sfx_banks = self.sfx_dir / self.lang_banks.name
        for f, kind in ((self.lang_banks, "banks"), (sfx_banks, "banks"), (self.dir / stem, "stream"), (self.sfx_dir / stem, "stream")):
            if not f.is_file():
                continue
            data = f.read_bytes()
            pack = wwise.read_pack(data)
            if kind == "banks":
                self.snd.add_banks(data, pack)
            for e in pack.sounds:
                self.stream_index.setdefault(e.id, (f, e.offset, e.size))
            self.snd.media_ids.update(e.id for e in pack.sounds)
            self.files.append(f"{f.name} ({len(data) // 1048576} MB, {len(pack.banks)} banks, {len(pack.sounds)} streamed)")
            del data

    def audio(self, media: int) -> bytes | None:
        got = self.snd.audio(media)
        if got:
            return got
        where = self.stream_index.get(media)
        if not where:
            return None
        f, off, size = where
        with f.open("rb") as h:
            h.seek(off)
            return h.read(size)
