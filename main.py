"""BacMask entry point. Bootstraps logging + launches the Kivy app."""

import sys
from pathlib import Path

from bacmask.ui.app import main
from bacmask.utils.logger import setup_logging


def _initial_path() -> Path | None:
    """Return argv[1] as a Path if it exists, else None.

    Used for Windows double-click via the ``.bacmask`` file association,
    and for the ``bacmask <path>`` CLI shortcut.
    """
    if len(sys.argv) < 2:
        return None
    p = Path(sys.argv[1])
    return p if p.exists() else None


if __name__ == "__main__":
    setup_logging()
    main(initial_path=_initial_path())
