"""Scale-factor validation. See knowledge/017-calibration-input.md."""

from __future__ import annotations

import math


def validate_scale(scale_mm_per_px: float | None) -> float | None:
    """``None`` is valid (uncalibrated). Otherwise a positive finite float."""
    if scale_mm_per_px is None:
        return None
    if isinstance(scale_mm_per_px, bool) or not isinstance(scale_mm_per_px, (int, float)):
        raise TypeError("scale must be float or None")
    s = float(scale_mm_per_px)
    if math.isnan(s) or math.isinf(s):
        raise ValueError(f"scale must be finite, got {s}")
    if s <= 0:
        raise ValueError(f"scale must be positive, got {s}")
    return s
