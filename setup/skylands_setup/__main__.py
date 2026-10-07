"""python -m skylands_setup <survey|build> ..."""

import sys


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("survey",):
        print("usage: python -m skylands_setup survey --bl2 DIR --skyrim DIR --out FILE")
        return 2
    from . import survey

    return survey.main(sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
