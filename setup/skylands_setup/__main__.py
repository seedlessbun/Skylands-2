"""python -m skylands_setup <survey|build> ..."""

import sys


def skse_check(argv: list[str]) -> int:
    """python -m skylands_setup sksecheck [--skyrim DIR]: is SKSE ready for Skylands (changes nothing)."""
    from pathlib import Path

    from . import skse
    from .steam import find

    sky = Path(argv[argv.index("--skyrim") + 1]) if "--skyrim" in argv else find("skyrim")
    if not sky or not (sky / "Data" / "Skyrim.esm").is_file():
        print(f"Skyrim Special Edition not found ({sky}). Run with --skyrim \"D:\\path\\Skyrim Special Edition\".")
        return 2
    st = skse.status(sky)
    print(f"Skyrim folder: {sky}")
    for line in skse.describe(st):
        print(line)
    print(f"SkylandsNative.dll installed: {'yes' if st.plugin else 'no (the Skylands installer puts it there)'}")
    print("SKSE is READY for Skylands." if st.ready else "SKSE is NOT ready yet: do the steps above, then run this check again.")
    return 0 if st.ready else 1


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("survey", "build", "uninstall", "modelsurvey", "shootingsurvey", "sksecheck", "bl2audio", "bl2shotguns"):
        print("usage: python -m skylands_setup survey --out FILE [--bl2 DIR --skyrim DIR]")
        print("       python -m skylands_setup build --done FILE [--bl2 DIR --skyrim DIR] [--stage-only]")
        print("       python -m skylands_setup uninstall --work DIR")
        return 2
    if sys.argv[1] == "uninstall":
        from . import build

        return build.uninstall_main(sys.argv[2:])
    if sys.argv[1] == "modelsurvey":
        from . import modelsurvey

        return modelsurvey.main(sys.argv[2:])
    if sys.argv[1] == "shootingsurvey":
        from . import shootingsurvey

        return shootingsurvey.main(sys.argv[2:])
    if sys.argv[1] == "bl2audio":
        from . import audioprobe

        return audioprobe.main(sys.argv[2:])
    if sys.argv[1] == "bl2shotguns":
        from . import shotgunprobe

        return shotgunprobe.main(sys.argv[2:])
    if sys.argv[1] == "sksecheck":
        return skse_check(sys.argv[2:])
    if sys.argv[1] == "build":
        from . import build

        return build.main(sys.argv[2:])
    from . import survey

    return survey.main(sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
