"""python -m skylands_setup <survey|build> ..."""

import sys


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("survey", "build"):
        print("usage: python -m skylands_setup survey --out FILE [--bl2 DIR --skyrim DIR]")
        print("       python -m skylands_setup build --done FILE [--bl2 DIR --skyrim DIR] [--stage-only]")
        return 2
    if sys.argv[1] == "build":
        from . import build

        return build.main(sys.argv[2:])
    from . import survey

    return survey.main(sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
