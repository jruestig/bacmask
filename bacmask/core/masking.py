"""Polygon rasterization onto uint16 label maps. See knowledge/014-lasso-tool.md."""

from __future__ import annotations

import cv2
import numpy as np

_UINT16_MAX = np.iinfo(np.uint16).max


def rasterize_polygon(
    label_map: np.ndarray,
    vertices: np.ndarray,
    label_id: int,
) -> np.ndarray:
    """Fill the polygon into ``label_map`` with ``label_id`` (in place).

    vertices: (N, 2) array of (x, y) points.
    Uses cv2.fillPoly (even-odd rule).
    """
    if label_map.dtype != np.uint16:
        raise TypeError(f"label_map must be uint16, got {label_map.dtype}")
    if not (0 < label_id <= _UINT16_MAX):
        raise ValueError(f"label_id {label_id} out of uint16 range")
    pts = np.asarray(vertices, dtype=np.int32).reshape(-1, 1, 2)
    cv2.fillPoly(label_map, [pts], color=int(label_id))
    return label_map


def erase_region(label_map: np.ndarray, label_id: int) -> np.ndarray:
    """Zero all pixels equal to ``label_id`` (in place)."""
    label_map[label_map == label_id] = 0
    return label_map


def polygon_area(vertices: np.ndarray) -> float:
    """Return the polygon's enclosed area in square pixels (shoelace / cv2).

    Uses ``cv2.contourArea`` — the mathematical enclosed area via the shoelace
    formula. Returns ``0.0`` for degenerate inputs (fewer than 3 vertices,
    collinear points, duplicate points). This is independent of rasterization
    quirks: ``cv2.fillPoly`` of a collinear polygon still fills boundary pixels
    along the line, but the enclosed area is zero and the lasso should be
    discarded. See knowledge/014 edge-case handling.
    """
    verts = np.asarray(vertices, dtype=np.int32).reshape(-1, 2)
    if len(verts) < 3:
        return 0.0
    return float(cv2.contourArea(verts))
