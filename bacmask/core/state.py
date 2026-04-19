"""Central session state — single source of truth. See knowledge/002-state-management.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from bacmask.config import defaults

Tool = Literal["lasso", "brush"]


@dataclass
class BrushStroke:
    """In-progress brush stroke buffer. See knowledge/026."""

    # Target region's label_id, or ``None`` for ``mode == "create"`` (the
    # stroke commits as a brand-new region with a fresh id).
    target_id: int | None
    mode: Literal["add", "subtract", "create"]
    # Bool mask of accumulated brush footprint in image space.
    mask: np.ndarray
    # Last image-space sample for line-sweep continuity between PointerMoves.
    last_pos: tuple[int, int]
    # Image-space bbox of the painted footprint (y0, y1, x0, x1) — half-open
    # in y/x. Maintained incrementally as samples are stamped so the commit
    # path can skip a full ``np.where(mask)`` pass on large images.
    bbox: tuple[int, int, int, int] | None = None


@dataclass
class SessionState:
    image: np.ndarray | None = None
    image_path: Path | None = None
    image_filename: str | None = None
    image_bytes: bytes | None = None
    image_ext: str | None = None
    # Display cache, painted from region_masks in ascending label order so the
    # highest label wins on overlapping pixels. See knowledge/002, 025.
    label_map: np.ndarray | None = None
    # Canonical region storage: {label_id: {"name": str, "vertices": list[[x, y]]}}.
    regions: dict[int, dict[str, Any]] = field(default_factory=dict)
    # Derived per-region bool masks, kept in sync by commands. Authoritative for
    # area and hit-testing against the target region (knowledge/025).
    region_masks: dict[int, np.ndarray] = field(default_factory=dict)
    # Cached per-region pixel count (``mask.sum()``). Kept in sync by commands
    # alongside ``region_masks`` so ``compute_area_rows`` doesn't have to re-sum
    # every HxW mask on every results-panel refresh — that was O(N·H·W) per
    # notify and dominated the perceived slowdown past ~100 regions.
    region_areas: dict[int, int] = field(default_factory=dict)
    next_label_id: int = 1
    scale_mm_per_px: float | None = None
    # During drag this holds the growing list of captured samples; ndarray once
    # committed; None when no stroke is in progress. A plain list avoids the
    # per-move O(N) reallocation a fresh ndarray would cost on every sample.
    active_lasso: np.ndarray | list[tuple[int, int]] | None = None
    selected_region_id: int | None = None
    # Active editing tool. Picking the tool is the mode (knowledge/013, 026).
    active_tool: Tool = "lasso"
    # Image-space radius for the brush stamp. Session-local (knowledge/026).
    brush_radius_px: int = defaults.BRUSH_RADIUS_DEFAULT_PX
    # Persistent default brush mode — driven by the brush-panel toggle
    # buttons. ``create`` makes press-drag-release commit a brand-new region
    # built from the painted blob; ``add``/``subtract`` edit the locked
    # target. See knowledge/026.
    brush_default_mode: Literal["add", "subtract", "create"] = "add"
    # Per-stroke buffer. None when no brush stroke is in flight.
    active_brush_stroke: BrushStroke | None = None
    dirty: bool = False
    # Monotonic counter bumped whenever `regions` or `region_masks` change.
    # Canvas watches this to gate the (expensive) overlay-texture rebuild so
    # selection / mode / calibration notifies don't trigger a full repaint.
    regions_version: int = 0

    def set_image(self, image: np.ndarray, path: Path) -> None:
        self.image = image
        self.image_path = Path(path)
        self.image_filename = Path(path).name
        self.image_bytes = None
        self.image_ext = None
        h, w = image.shape[:2]
        self.label_map = np.zeros((h, w), dtype=np.uint16)
        self.regions = {}
        self.region_masks = {}
        self.region_areas = {}
        self.next_label_id = 1
        self.active_lasso = None
        self.active_brush_stroke = None
        self.selected_region_id = None
        self.dirty = False
        self.regions_version += 1
