"""Config loader. MVP: returns defaults. YAML file support deferred (would add PyYAML dep)."""

from __future__ import annotations

from typing import Any

from bacmask.config import defaults


def load_config() -> dict[str, Any]:
    return {
        "output_root": defaults.OUTPUT_ROOT,
        "bundles_dir": defaults.BUNDLES_DIR,
        "areas_dir": defaults.AREAS_DIR,
        "lasso_close_threshold_px": defaults.LASSO_CLOSE_THRESHOLD_PX,
        "undo_history_cap": defaults.UNDO_HISTORY_CAP,
        "mask_overlay_alpha": defaults.MASK_OVERLAY_ALPHA,
        "log_level": defaults.LOG_LEVEL,
    }
