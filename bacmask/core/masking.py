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


def rasterize_polygon_mask(
    vertices: np.ndarray,
    image_shape: tuple[int, int],
) -> np.ndarray:
    """Return an ``(H, W)`` bool mask with ``True`` inside the polygon.

    Uses the same ``cv2.fillPoly`` even-odd rule as :func:`rasterize_polygon`,
    just producing a binary mask instead of painting into a uint16 label map.
    Suitable for per-region ``region_masks`` entries (knowledge/002, 025).
    """
    h, w = image_shape
    mask = np.zeros((h, w), dtype=np.uint8)
    pts = np.asarray(vertices, dtype=np.int32).reshape(-1, 1, 2)
    cv2.fillPoly(mask, [pts], color=1)
    return mask.astype(bool)


def repaint_label_map(
    label_map: np.ndarray,
    region_masks: dict[int, np.ndarray],
) -> None:
    """Overwrite ``label_map`` (in place) from ``region_masks``.

    Paints each region in ascending ``label_id`` order so the highest id wins
    on any overlapping pixel — this matches the newest-on-top display rule in
    knowledge/025. ``label_map`` is zeroed first.
    """
    if label_map.dtype != np.uint16:
        raise TypeError(f"label_map must be uint16, got {label_map.dtype}")
    label_map.fill(0)
    for label_id in sorted(region_masks):
        if not (0 < label_id <= _UINT16_MAX):
            raise ValueError(f"label_id {label_id} out of uint16 range")
        label_map[region_masks[label_id]] = label_id


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


# ---- region-edit stroke helpers (knowledge/023) ------------------------------


def find_boundary_crossings(
    samples: np.ndarray,
    target_mask: np.ndarray,
) -> tuple[int | None, int | None]:
    """Return ``(P, Q)`` — the indices of the first two boundary crossings.

    A crossing between samples ``i`` and ``i+1`` is defined as
    ``target_mask[samples[i]] != target_mask[samples[i+1]]`` (in-region vs
    outside). ``P`` is the first such index, ``Q`` the second. Either may be
    ``None`` when not found. Samples outside the image bounds count as
    outside-region.

    See knowledge/023, step 2.
    """
    pts = np.asarray(samples, dtype=np.int64).reshape(-1, 2)
    if len(pts) < 2:
        return None, None
    h, w = target_mask.shape
    xs = pts[:, 0]
    ys = pts[:, 1]
    in_bounds = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
    inside = np.zeros(len(pts), dtype=bool)
    if in_bounds.any():
        inside[in_bounds] = target_mask[ys[in_bounds], xs[in_bounds]]

    p: int | None = None
    q: int | None = None
    for i in range(len(pts) - 1):
        if inside[i] != inside[i + 1]:
            if p is None:
                p = i
            else:
                q = i
                break
    return p, q


def rasterize_stroke_polygon(
    samples: np.ndarray,
    image_shape: tuple[int, int],
) -> np.ndarray:
    """Close an open polyline by a straight segment and rasterize to a bool mask.

    The stroke ``samples`` (list of ``(x, y)`` points) is interpreted as an
    open polyline; a line from the last point to the first closes it into a
    polygon, which is then filled using ``cv2.fillPoly`` (even-odd rule) into
    an ``(H, W)`` bool mask.

    Returns an all-False mask if fewer than 3 samples are supplied.
    See knowledge/023, step 3.
    """
    h, w = image_shape
    pts = np.asarray(samples, dtype=np.int32).reshape(-1, 2)
    mask = np.zeros((h, w), dtype=np.uint8)
    if len(pts) < 3:
        return mask.astype(bool)
    cv2.fillPoly(mask, [pts.reshape(-1, 1, 2)], color=1)
    return mask.astype(bool)


def largest_connected_component(mask: np.ndarray) -> np.ndarray:
    """Return a bool mask of the largest 8-connected foreground component.

    Ties (multiple components of equal pixel count) are broken by picking the
    component that contains the smallest ``(y, x)`` pixel in raster-scan order
    — i.e. the first foreground pixel encountered when walking row-major.
    This matches knowledge/023's deterministic tiebreak.

    For an empty mask, returns an all-False copy. For a single-component
    input, returns a copy of the input.
    """
    m = np.asarray(mask, dtype=bool)
    if not m.any():
        return m.copy()
    num_labels, labels = cv2.connectedComponents(m.astype(np.uint8), connectivity=8)
    if num_labels <= 2:
        # Background + one component.
        return m.copy()

    # Pixel counts per label (skip background = 0).
    counts = np.bincount(labels.ravel())
    counts[0] = 0  # ignore background
    max_count = counts.max()
    candidates = np.flatnonzero(counts == max_count)
    if len(candidates) == 1:
        winner = int(candidates[0])
    else:
        # Tie: pick the component at the smallest (y, x) foreground pixel
        # in raster-scan order — among only the tied candidates.
        flat_labels = labels.ravel()
        candidate_set = {int(c) for c in candidates}
        winner = None
        for idx in np.flatnonzero(flat_labels > 0):
            lbl = int(flat_labels[idx])
            if lbl in candidate_set:
                winner = lbl
                break
        if winner is None:  # pragma: no cover — unreachable
            winner = int(candidates[0])
    return labels == winner


def contour_vertices(mask: np.ndarray) -> np.ndarray:
    """Return the outermost contour of ``mask`` as an ``(N, 2)`` int32 array.

    Uses ``cv2.findContours`` with ``RETR_EXTERNAL`` and ``CHAIN_APPROX_NONE``
    so every boundary pixel becomes a vertex (no simplification). If multiple
    external contours are found, the one with the most points is returned —
    after the multi-piece filter in knowledge/023 step 7 this should not
    happen, but we still pick deterministically.

    Raises ``ValueError`` on an empty mask (no boundary to trace).
    """
    m = np.asarray(mask, dtype=bool)
    if not m.any():
        raise ValueError("cannot derive contour from empty mask")
    contours, _ = cv2.findContours(
        m.astype(np.uint8),
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_NONE,
    )
    if not contours:  # pragma: no cover — defensive
        raise ValueError("no contour found in non-empty mask")
    # Largest by vertex count (matches "outermost after largest-CC" rule).
    contour = max(contours, key=len)
    return contour[:, 0, :].astype(np.int32)
