"""Area computation from label maps. See knowledge/011, 012, 017."""

from __future__ import annotations

import numpy as np


def count_pixels_per_region(label_map: np.ndarray) -> dict[int, int]:
    """Return {label_id: pixel_count} for every non-zero label."""
    if label_map.dtype != np.uint16:
        raise TypeError(f"label_map must be uint16, got {label_map.dtype}")
    ids, counts = np.unique(label_map, return_counts=True)
    return {int(i): int(c) for i, c in zip(ids, counts, strict=True) if i != 0}


def px_to_mm2(px: int, scale_mm_per_px: float | None) -> float | None:
    """Convert pixel count to mm². Returns None when scale is uncalibrated."""
    if scale_mm_per_px is None:
        return None
    return px * (scale_mm_per_px**2)
