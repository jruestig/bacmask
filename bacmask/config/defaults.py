"""Default configuration values. See knowledge/006-configuration-management.md."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME: str = "BacMask"


def _default_output_root() -> Path:
    """Resolve the writable output root.

    Precedence: ``BACMASK_OUTPUT_ROOT`` env var > installed build
    user-data dir > repo-local ``output/`` for dev runs.
    """
    override = os.environ.get("BACMASK_OUTPUT_ROOT")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        if sys.platform.startswith("win"):
            base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            return Path(base) / APP_NAME
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / APP_NAME
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
        return base / APP_NAME
    return Path("output")


OUTPUT_ROOT: Path = _default_output_root()
BUNDLES_DIR: Path = OUTPUT_ROOT / "bundles"
AREAS_DIR: Path = OUTPUT_ROOT / "areas"

LASSO_CLOSE_THRESHOLD_PX: int = 10
UNDO_HISTORY_CAP: int = 50
MASK_OVERLAY_ALPHA: float = 0.4

BRUSH_RADIUS_DEFAULT_PX: int = 8
BRUSH_RADIUS_MIN_PX: int = 1
BRUSH_RADIUS_MAX_PX: int = 100

LOG_LEVEL: str = "INFO"
