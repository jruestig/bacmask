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
    label_map: np.ndarray | None = None
    regions: dict[int, dict[str, Any]] = field(default_factory=dict)
    next_label_id: int = 1
    scale_mm_per_px: float | None = None
    active_lasso: np.ndarray | None = None
    selected_region_id: int | None = None
    edit_mode: bool = False
    dirty: bool = False

    def set_image(self, image: np.ndarray, path: Path) -> None:
        self.image = image
        self.image_path = Path(path)
        self.image_filename = Path(path).name
        self.image_bytes = None
        self.image_ext = None
        h, w = image.shape[:2]
        self.label_map = np.zeros((h, w), dtype=np.uint16)
        self.regions = {}
        self.next_label_id = 1
        self.active_lasso = None
        self.selected_region_id = None
        self.dirty = False
