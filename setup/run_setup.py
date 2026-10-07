"""Entry point Melty starts before the first Play (python run_setup.py build ...)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skylands_setup.__main__ import main  # noqa: E402

sys.exit(main())
