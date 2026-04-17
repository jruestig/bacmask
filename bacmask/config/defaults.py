"""Default configuration values. See knowledge/006-configuration-management.md."""

from __future__ import annotations

from pathlib import Path

OUTPUT_ROOT: Path = Path("output")
BUNDLES_DIR: Path = OUTPUT_ROOT / "bundles"
AREAS_DIR: Path = OUTPUT_ROOT / "areas"

LASSO_CLOSE_THRESHOLD_PX: int = 10
UNDO_HISTORY_CAP: int = 50
MASK_OVERLAY_ALPHA: float = 0.4

LOG_LEVEL: str = "INFO"
