"""High-level mask-editing orchestration.

The UI calls only methods here — never core commands or io_manager directly.
Owns a SessionState and a history stack; exposes intent-based actions and
notifies subscribers on every state change.

See knowledge/001 (separation), 002 (state), 003 (commands), 014 (lasso).
"""

from __future__ import annotations

import logging
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from bacmask.core import area, calibration, io_manager, masking
from bacmask.core.commands import (
    DeleteRegionCommand,
    LassoCloseCommand,
    VertexEditCommand,
)
from bacmask.core.history import UndoRedoStack
from bacmask.core.state import SessionState

log = logging.getLogger(__name__)


class MaskService:
    def __init__(
        self,
        state: SessionState | None = None,
        history: UndoRedoStack | None = None,
    ) -> None:
        self.state = state if state is not None else SessionState()
        self.history = history if history is not None else UndoRedoStack()
        self._listeners: list[Callable[[], None]] = []
        self._active_lasso: list[tuple[int, int]] = []

    # ---- observer hook ------------------------------------------------------

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def _notify(self) -> None:
        for listener in self._listeners:
            listener()

    # ---- loading ------------------------------------------------------------

    def load_image(self, path: Path | str) -> None:
        p = Path(path)
        img = io_manager.load_image(p)
        self.state.set_image(img, p)
        self.state.image_bytes = p.read_bytes()
        self.state.image_ext = p.suffix.lower() or ".bin"
        self.history.clear()
        self._active_lasso = []
        self._notify()

    def load_bundle(self, path: Path | str) -> None:
        p = Path(path)
        bundle = io_manager.load_bundle(p)
        self.state.image = bundle.image
        self.state.image_path = None
        self.state.image_filename = bundle.meta.source_filename
        with zipfile.ZipFile(p, "r") as zf:
            self.state.image_bytes = zf.read(f"image{bundle.image_ext}")
        self.state.image_ext = bundle.image_ext
        self.state.label_map = bundle.label_map
        self.state.regions = {int(k): v for k, v in bundle.meta.regions.items()}
        self.state.next_label_id = bundle.meta.next_label_id
        self.state.scale_mm_per_px = bundle.meta.scale_mm_per_px
        self.state.active_lasso = None
        self.state.dirty = False
        self.history.clear()
        self._active_lasso = []
        self._notify()

    # ---- lasso --------------------------------------------------------------

    def begin_lasso(self, pos: tuple[int, int]) -> None:
        self._active_lasso = [pos]
        self.state.active_lasso = np.asarray(self._active_lasso, dtype=np.int32)
        self._notify()

    def add_lasso_point(self, pos: tuple[int, int]) -> None:
        self._active_lasso.append(pos)
        self.state.active_lasso = np.asarray(self._active_lasso, dtype=np.int32)
        self._notify()

    def cancel_lasso(self) -> None:
        self._active_lasso = []
        self.state.active_lasso = None
        self._notify()

    def close_lasso(self) -> int | None:
        """Commit the in-progress lasso. Returns label_id or None if discarded."""
        if len(self._active_lasso) < 3:
            self._active_lasso = []
            self.state.active_lasso = None
            self._notify()
            return None
        verts = np.asarray(self._active_lasso, dtype=np.int32)
        enclosed_area = masking.polygon_area(verts)
        if enclosed_area <= 0.0:
            log.warning(
                "lasso discarded: polygon with %d vertices encloses zero area",
                len(verts),
            )
            self._active_lasso = []
            self.state.active_lasso = None
            self._notify()
            return None
        cmd = LassoCloseCommand(verts)
        self.history.push(cmd, self.state)
        self._active_lasso = []
        self.state.active_lasso = None
        self._notify()
        return cmd.assigned_label_id

    # ---- vertex edit --------------------------------------------------------

    def edit_vertices(
        self,
        label_id: int,
        new_vertices: Sequence[tuple[int, int]] | np.ndarray,
    ) -> None:
        verts = np.asarray(new_vertices, dtype=np.int32)
        cmd = VertexEditCommand(label_id=label_id, new_vertices=verts)
        self.history.push(cmd, self.state)
        self._notify()

    # ---- delete -------------------------------------------------------------

    def delete_region(self, label_id: int) -> None:
        if label_id not in self.state.regions:
            raise KeyError(f"region {label_id} does not exist")
        cmd = DeleteRegionCommand(label_id=label_id)
        self.history.push(cmd, self.state)
        if self.state.selected_region_id == label_id:
            self.state.selected_region_id = None
        self._notify()

    # ---- selection ----------------------------------------------------------

    def select_region(self, label_id: int) -> None:
        if label_id not in self.state.regions:
            raise KeyError(f"region {label_id} does not exist")
        if self.state.selected_region_id != label_id:
            self.state.selected_region_id = label_id
            self._notify()

    def clear_selection(self) -> None:
        if self.state.selected_region_id is not None:
            self.state.selected_region_id = None
            self._notify()

    # ---- undo / redo --------------------------------------------------------

    def undo(self) -> bool:
        ok = self.history.undo(self.state)
        if ok:
            self._notify()
        return ok

    def redo(self) -> bool:
        ok = self.history.redo(self.state)
        if ok:
            self._notify()
        return ok

    # ---- edit mode ----------------------------------------------------------

    def toggle_edit_mode(self) -> bool:
        """Flip the edit-mode flag. Returns the new value."""
        self.state.edit_mode = not self.state.edit_mode
        # Any in-progress lasso is ambiguous across a mode flip.
        self._active_lasso = []
        self.state.active_lasso = None
        self._notify()
        return self.state.edit_mode

    def set_edit_mode(self, enabled: bool) -> None:
        if self.state.edit_mode == enabled:
            return
        self.state.edit_mode = enabled
        self._active_lasso = []
        self.state.active_lasso = None
        self._notify()

    # ---- calibration --------------------------------------------------------

    def set_calibration(self, scale_mm_per_px: float | None) -> None:
        validated = calibration.validate_scale(scale_mm_per_px)
        if validated != self.state.scale_mm_per_px:
            self.state.scale_mm_per_px = validated
            self.state.dirty = True
            self._notify()

    # ---- derived ------------------------------------------------------------

    def compute_area_rows(self) -> list[io_manager.AreaRow]:
        if self.state.label_map is None or self.state.image_filename is None:
            return []
        counts = area.count_pixels_per_region(self.state.label_map)
        scale = self.state.scale_mm_per_px
        rows: list[io_manager.AreaRow] = []
        for label_id, meta in sorted(self.state.regions.items()):
            px = counts.get(label_id, 0)
            rows.append(
                io_manager.AreaRow(
                    filename=self.state.image_filename,
                    region_id=label_id,
                    region_name=meta["name"],
                    area_px=px,
                    area_mm2=area.px_to_mm2(px, scale),
                    scale_factor=scale,
                )
            )
        return rows

    # ---- save / export ------------------------------------------------------

    def save_bundle(self, bundle_path: Path | str) -> None:
        """Write the ``.bacmask`` bundle only. No CSV; no mask sidecar."""
        if (
            self.state.label_map is None
            or self.state.image_bytes is None
            or self.state.image_ext is None
        ):
            raise ValueError("no image loaded")
        meta = io_manager.BundleMeta(
            source_filename=self.state.image_filename or "unknown",
            scale_mm_per_px=self.state.scale_mm_per_px,
            next_label_id=self.state.next_label_id,
            regions=dict(self.state.regions),
        )
        io_manager.save_bundle_from_bytes(
            bundle_path,
            image_bytes=self.state.image_bytes,
            image_ext=self.state.image_ext,
            label_map=self.state.label_map,
            meta=meta,
        )
        self.state.dirty = False
        self._notify()

    def export_csv(self, csv_path: Path | str) -> None:
        """Write the sibling areas CSV. Independent of saving the bundle."""
        if self.state.label_map is None:
            raise ValueError("no image loaded")
        io_manager.save_areas_csv(csv_path, self.compute_area_rows())
