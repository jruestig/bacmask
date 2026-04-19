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


def repaint_label_map_bbox(
    label_map: np.ndarray,
    region_masks: dict[int, np.ndarray],
    bbox: tuple[int, int, int, int],
) -> None:
    """Like :func:`repaint_label_map` but restricted to a ``(y0, y1, x0, x1)``
    half-open sub-rectangle. Only regions whose mask intersects the bbox are
    repainted; other pixels of ``label_map`` are left untouched. This is the
    fast path used by commands after an incremental edit — full repaint costs
    O(N·H·W); bbox repaint costs O(N·Δy·Δx) for the affected window only.
    """
    if label_map.dtype != np.uint16:
        raise TypeError(f"label_map must be uint16, got {label_map.dtype}")
    y0, y1, x0, x1 = bbox
    if y0 >= y1 or x0 >= x1:
        return
    sub = label_map[y0:y1, x0:x1]
    sub.fill(0)
    for label_id in sorted(region_masks):
        if not (0 < label_id <= _UINT16_MAX):
            raise ValueError(f"label_id {label_id} out of uint16 range")
        region_sub = region_masks[label_id][y0:y1, x0:x1]
        if region_sub.any():
            sub[region_sub] = label_id


def paint_label_map_bbox(
    label_map: np.ndarray,
    regions: dict[int, dict],
    bbox: tuple[int, int, int, int],
) -> None:
    """Repaint a sub-rectangle of ``label_map`` from polygon ``regions``.

    Zeroes the half-open ``(y0, y1, x0, x1)`` window of ``label_map`` and
    paints each polygon whose vertex bbox intersects the window, in ascending
    ``label_id`` order so the highest id wins on overlap (knowledge/025).
    ``regions`` is the canonical ``{label_id: {"name": str,
    "vertices": list[[x, y]]}}`` dict from :class:`SessionState`. The polygon
    set is the sole source of truth here — no ``region_masks`` are consulted
    (knowledge/030).
    """
    if label_map.dtype != np.uint16:
        raise TypeError(f"label_map must be uint16, got {label_map.dtype}")
    y0, y1, x0, x1 = bbox
    if y0 >= y1 or x0 >= x1:
        return
    sub = label_map[y0:y1, x0:x1]
    sub.fill(0)
    for label_id in sorted(regions):
        if not (0 < label_id <= _UINT16_MAX):
            raise ValueError(f"label_id {label_id} out of uint16 range")
        verts = np.asarray(regions[label_id]["vertices"], dtype=np.int32).reshape(-1, 2)
        if len(verts) == 0:
            continue
        vx0 = int(verts[:, 0].min())
        vx1 = int(verts[:, 0].max()) + 1
        vy0 = int(verts[:, 1].min())
        vy1 = int(verts[:, 1].max()) + 1
        if vx1 <= x0 or vx0 >= x1 or vy1 <= y0 or vy0 >= y1:
            continue
        # Translate into sub-window coordinates so cv2.fillPoly writes directly
        # into the sliced view without clipping to the full label_map frame.
        pts = verts.copy()
        pts[:, 0] -= x0
        pts[:, 1] -= y0
        cv2.fillPoly(sub, [pts.reshape(-1, 1, 2)], color=int(label_id))


def vertices_bbox(
    vertices: np.ndarray,
    image_shape: tuple[int, int],
    pad: int = 1,
) -> tuple[int, int, int, int] | None:
    """Return a clipped ``(y0, y1, x0, x1)`` half-open bbox covering ``vertices``.

    The polygon rasterization via ``cv2.fillPoly`` stays within the vertex
    bbox (inclusive). We return a half-open bbox padded by ``pad`` to
    tolerate rounding when the polygon is re-derived from a cleaned contour.
    Returns ``None`` for an empty vertex list.
    """
    verts = np.asarray(vertices, dtype=np.int32).reshape(-1, 2)
    if len(verts) == 0:
        return None
    h, w = image_shape
    x0 = int(verts[:, 0].min()) - pad
    x1 = int(verts[:, 0].max()) + 1 + pad
    y0 = int(verts[:, 1].min()) - pad
    y1 = int(verts[:, 1].max()) + 1 + pad
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(w, x1)
    y1 = min(h, y1)
    if y0 >= y1 or x0 >= x1:
        return None
    return y0, y1, x0, x1


def union_bbox(
    a: tuple[int, int, int, int] | None,
    b: tuple[int, int, int, int] | None,
) -> tuple[int, int, int, int] | None:
    """Half-open bbox union. ``None`` inputs are treated as empty."""
    if a is None:
        return b
    if b is None:
        return a
    return (
        min(a[0], b[0]),
        max(a[1], b[1]),
        min(a[2], b[2]),
        max(a[3], b[3]),
    )


def mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Half-open ``(y0, y1, x0, x1)`` bbox of a bool mask's True pixels.

    Returns ``None`` for an all-False mask. O(H+W) via axis reductions —
    cheap relative to rewriting the mask.
    """
    m = np.asarray(mask, dtype=bool)
    if not m.any():
        return None
    rows = np.any(m, axis=1)
    cols = np.any(m, axis=0)
    y0 = int(np.argmax(rows))
    y1 = int(len(rows) - np.argmax(rows[::-1]))
    x0 = int(np.argmax(cols))
    x1 = int(len(cols) - np.argmax(cols[::-1]))
    return y0, y1, x0, x1


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


# ---- brush stamp helpers (knowledge/026) -------------------------------------


def stamp_brush_disc(
    mask: np.ndarray,
    center: tuple[int, int],
    radius: int,
) -> np.ndarray:
    """Paint a filled disc of ``radius`` centered at ``center`` into ``mask`` (in place).

    Operates in image space. Out-of-bounds extents are clipped silently.
    Returns the same mask for chaining.
    """
    if mask.dtype != bool:
        raise TypeError(f"mask must be bool, got {mask.dtype}")
    if radius < 1:
        return mask
    cx, cy = int(center[0]), int(center[1])
    h, w = mask.shape
    # Bounding box of the disc, clipped to image.
    x0 = max(0, cx - radius)
    x1 = min(w, cx + radius + 1)
    y0 = max(0, cy - radius)
    y1 = min(h, cy + radius + 1)
    if x0 >= x1 or y0 >= y1:
        return mask
    ys, xs = np.ogrid[y0:y1, x0:x1]
    disc = (xs - cx) ** 2 + (ys - cy) ** 2 <= radius * radius
    mask[y0:y1, x0:x1] |= disc
    return mask


def stamp_brush_segment(
    mask: np.ndarray,
    start: tuple[int, int],
    end: tuple[int, int],
    radius: int,
) -> np.ndarray:
    """Sweep a disc of ``radius`` along the segment ``start → end`` into ``mask``.

    Uses ``cv2.line`` with ``thickness = 2 * radius + 1`` so successive
    pointer samples leave no gaps at fast cursor speeds (knowledge/026 step 3).
    Endpoints are also stamped as discs to round the line caps.
    """
    if mask.dtype != bool:
        raise TypeError(f"mask must be bool, got {mask.dtype}")
    if radius < 1:
        return mask
    u8 = mask.view(np.uint8)
    x0, y0 = int(start[0]), int(start[1])
    x1, y1 = int(end[0]), int(end[1])
    cv2.line(
        u8,
        (x0, y0),
        (x1, y1),
        color=1,
        thickness=2 * radius + 1,
        lineType=cv2.LINE_8,
    )
    # Round caps via discs at both endpoints (cv2.line already does butt caps
    # on uint8 of width thickness — the disc adds the rounded ends).
    stamp_brush_disc(mask, (x0, y0), radius)
    stamp_brush_disc(mask, (x1, y1), radius)
    return mask


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
