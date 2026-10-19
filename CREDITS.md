# Skylands credits

- **Skylands** setup program, design sheets and tools: seedlessbun, built with Claude Code (AI-assisted).
- **CPython 3.13** (Python Software Foundation, PSF License) from python-build-standalone (Astral), bundled
  unchanged to run the setup; its license files ship in `python/`.
- **lzokay** by Jack Andersen (MIT), compiled into `skylands_lzo.dll` to read Borderlands 2's packages.
- **Borderlands 2** by Gearbox Software / 2K. **The Elder Scrolls V: Skyrim Special Edition** by Bethesda
  Game Studios. No files from either game are included: the setup reads the player's own installs.
- Borderlands 2 object paths were checked against the OpenBLCMM BL2 data pack (BLCM); techniques from the
  universal-modder field notes. Scripts verified with Champollion (MIT); meshes with nifly (GPL-3.0, test
  only, not shipped).
- **UModel / UE Viewer** by Konstantin Nosov (Gildor), used only by the optional "umodel" gun-model method: setup
  downloads it from its author's site into the player's work folder at install time (or uses a copy the player
  puts there). It is not part of the Skylands download. It reads Borderlands 2's meshes and textures on the player's PC.
