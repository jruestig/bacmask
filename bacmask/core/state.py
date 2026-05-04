"""Central session state — single source of truth. See knowledge/002-state-management.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from bacmask.config import defaults

Tool = Literal["lasso", "brush", "line"]


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
    # Display cache, painted from the polygon set in ascending label order so
    # the highest label wins on overlapping pixels. See knowledge/002, 025, 030.
    label_map: np.ndarray | None = None
    # Canonical region storage (knowledge/030): polygons are the sole source of
    # truth — no per-region masks or cached pixel counts are stored here.
    # Shape: ``{label_id: {"name": str, "vertices": list[[x, y]]}}``.
    regions: dict[int, dict[str, Any]] = field(default_factory=dict)
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
    # Measurement lines — per-session only, not persisted in the bundle and not
    # exported to CSV. Shape: ``{line_id: {"name": str, "p1": (x, y), "p2": (x, y)}}``.
    lines: dict[int, dict[str, Any]] = field(default_factory=dict)
    next_line_id: int = 1
    # In-progress line preview during drag — ``{"p1": (x, y), "p2": (x, y)}`` or
    # ``None`` when no line is being drawn.
    active_line: dict[str, tuple[int, int]] | None = None
    selected_line_id: int | None = None
    dirty: bool = False
    # Monotonic counter bumped whenever `regions` changes. Canvas watches this
    # to gate the (expensive) overlay-texture rebuild so selection / mode /
    # calibration notifies don't trigger a full repaint.
    regions_version: int = 0
    # Counter bumped whenever ``lines`` changes (add / delete). The results
    # table uses this to skip rebuilding line rows on selection-only notifies.
    lines_version: int = 0

    def set_image(
        self,
        image: np.ndarray,
        *,
        name: str,
        origin: Path | None = None,
    ) -> None:
        """Reset session state around a freshly loaded image.

        ``name`` is the display filename (used for save-as defaults and
        bundle metadata). ``origin`` is the filesystem path the image was
        read from when applicable, or ``None`` for SAF / in-memory sources.
        """
        self.image = image
        self.image_path = origin
        self.image_filename = name
        self.image_bytes = None
        self.image_ext = None
        h, w = image.shape[:2]
        self.label_map = np.zeros((h, w), dtype=np.uint16)
        self.regions = {}
        self.next_label_id = 1
        self.active_lasso = None
        self.active_brush_stroke = None
        self.selected_region_id = None
        self.lines = {}
        self.next_line_id = 1
        self.active_line = None
        self.selected_line_id = None
        self.dirty = False
        self.regions_version += 1
        self.lines_version += 1
