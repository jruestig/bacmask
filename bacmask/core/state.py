"""Central session state — single source of truth. See knowledge/002-state-management.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


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
    next_label_id: int = 1
    scale_mm_per_px: float | None = None
    # During drag this holds the growing list of captured samples; ndarray once
    # committed; None when no stroke is in progress. A plain list avoids the
    # per-move O(N) reallocation a fresh ndarray would cost on every sample.
    active_lasso: np.ndarray | list[tuple[int, int]] | None = None
    selected_region_id: int | None = None
    edit_mode: bool = False
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
        self.next_label_id = 1
        self.active_lasso = None
        self.selected_region_id = None
        self.dirty = False
        self.regions_version += 1
