"""Start KentoGo from the source folder, without relying on the installed package.

uv installs KentoGo in .venv as an "editable" package, which is found through a
.pth file. On some Macs that file gets the "hidden" flag, and Python 3.12 then
ignores it, so "python -m kentogo.app" cannot find the package. This script
adds the src folder to the search path itself, so it always works.

Usage:
    uv run python run.py [GAMES_FOLDER] [options]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kentogo.app import main  # noqa: E402  (the path must be set before this import)

if __name__ == "__main__":
    main()
