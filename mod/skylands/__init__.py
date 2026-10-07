"""Skylands: Borderlands 2 played as Skyrim's Dragonborn.

In the game (Willow2 Mod Manager) this registers the mod. Outside the game (tests, tools)
only the pure modules (skyrim/, progression, sheet_data) are imported.
"""

try:
    import unrealsdk  # noqa: F401
except ImportError:
    unrealsdk = None

if unrealsdk is not None:
    from . import game  # noqa: F401
