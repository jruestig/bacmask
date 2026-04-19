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
        h, w = bundle.image.shape[:2]
        self.state.regions = {int(k): v for k, v in bundle.meta.regions.items()}
        # Polygons are canonical — rasterize each into a per-region bool mask
        # and paint the display cache from them. The mask inside the bundle (if
        # any, for v1 bundles) is ignored. See knowledge/015, 025.
        self.state.region_masks = {
            label_id: masking.rasterize_polygon_mask(meta["vertices"], (h, w))
            for label_id, meta in self.state.regions.items()
        }
        self.state.label_map = np.zeros((h, w), dtype=np.uint16)
        masking.repaint_label_map(self.state.label_map, self.state.region_masks)
        self.state.next_label_id = bundle.meta.next_label_id
        self.state.scale_mm_per_px = bundle.meta.scale_mm_per_px
        self.state.active_lasso = None
        self.state.selected_region_id = None
        self.state.dirty = False
        self.state.regions_version += 1
        self.history.clear()
        self._active_lasso = []
        self._notify()

    # ---- lasso --------------------------------------------------------------

    def begin_lasso(self, pos: tuple[int, int]) -> None:
        self._active_lasso = [pos]
        # Expose the *same* list reference: consumers (canvas preview) iterate
        # the live buffer. Avoids allocating a fresh ndarray on every sample,
        # which was O(N) per move and dominated long-stroke cost.
        self.state.active_lasso = self._active_lasso
        self._notify()

    def add_lasso_point(self, pos: tuple[int, int]) -> None:
        self._active_lasso.append(pos)
        # state.active_lasso already points at this same list — no reassign.
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

    # ---- region edit stroke (add / subtract) --------------------------------

    def edit_region_stroke(
        self,
        target_id: int,
        samples: Sequence[tuple[int, int]] | np.ndarray,
    ) -> str | None:
        """Apply an add/subtract stroke to ``target_id``.

        Implements the algorithm in knowledge/023: detect add vs. subtract
        from the press-down sample, find the first two boundary crossings,
        truncate + close the open polyline, rasterize into a mask ``S``, then
        ``target | S`` (add) or ``target & ~S`` (subtract). Multi-piece
        results are filtered to the largest connected component (deterministic
        tiebreak on smallest ``(y, x)`` pixel). Empty result routes through
        :class:`DeleteRegionCommand` so the region is removed cleanly.

        Returns one of:

        * ``"added"`` — an add stroke was committed.
        * ``"subtracted"`` — a subtract stroke was committed.
        * ``"deleted"`` — the subtract emptied the region; delete was applied.
        * ``None`` — the stroke was discarded silently.
        """
        # Local imports — the top-of-file import block is reserved for another
        # concurrent refactor (knowledge/023 integration note).
        from bacmask.core.commands import DeleteRegionCommand, RegionEditCommand

        if target_id not in self.state.regions:
            raise KeyError(f"region {target_id} does not exist")
        if self.state.label_map is None:
            raise ValueError("state.label_map is not initialized")

        pts = np.asarray(samples, dtype=np.int32).reshape(-1, 2)
        if len(pts) < 3:
            return None

        image_shape = self.state.label_map.shape
        h, w = image_shape
        target_mask = self.state.region_masks.get(target_id)
        if target_mask is None:
            target_mask = np.zeros(image_shape, dtype=bool)

        # Mode from the press-down sample. Out-of-bounds => outside.
        x0, y0 = int(pts[0, 0]), int(pts[0, 1])
        if 0 <= x0 < w and 0 <= y0 < h and bool(target_mask[y0, x0]):
            mode = "add"
        else:
            mode = "subtract"

        p, q = masking.find_boundary_crossings(pts, target_mask)
        if p is None or q is None:
            return None

        # Samples[P+1 : Q+1] — from the first sample on the other side through
        # the first sample back on the origin side (inclusive).
        segment = pts[p + 1 : q + 1]
        if len(segment) < 3:
            return None

        s_mask = masking.rasterize_stroke_polygon(segment, image_shape)
        if not s_mask.any():
            return None

        if mode == "add":
            new_mask = target_mask | s_mask
        else:
            new_mask = target_mask & ~s_mask

        # Bitwise no-op => discard.
        if np.array_equal(new_mask, target_mask):
            return None

        # Empty result => route through DeleteRegionCommand so the existing
        # undo path + monotonic-id behavior apply uniformly.
        if not new_mask.any():
            cmd = DeleteRegionCommand(label_id=target_id)
            self.history.push(cmd, self.state)
            if self.state.selected_region_id == target_id:
                self.state.selected_region_id = None
            self._notify()
            return "deleted"

        # Keep the largest connected component (deterministic tiebreak).
        filtered = masking.largest_connected_component(new_mask)
        new_vertices = masking.contour_vertices(filtered)
        if len(new_vertices) < 3:
            # Contour too small to form a polygon — discard silently.
            return None

        edit_cmd = RegionEditCommand(
            label_id=target_id,
            new_vertices=new_vertices,
            new_region_mask=filtered,
        )
        self.history.push(edit_cmd, self.state)
        self._notify()
        return "added" if mode == "add" else "subtracted"

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
        """Per-region area rows. Counts each region's own pixels (region_masks),
        so overlapping pixels are counted once per region (knowledge/025).
        """
        if self.state.image_filename is None or not self.state.regions:
            return []
        scale = self.state.scale_mm_per_px
        rows: list[io_manager.AreaRow] = []
        for label_id, meta in sorted(self.state.regions.items()):
            region_mask = self.state.region_masks.get(label_id)
            px = int(region_mask.sum()) if region_mask is not None else 0
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
            self.state.image is None
            or self.state.image_bytes is None
            or self.state.image_ext is None
        ):
            raise ValueError("no image loaded")
        image_shape = (int(self.state.image.shape[0]), int(self.state.image.shape[1]))
        meta = io_manager.BundleMeta(
            source_filename=self.state.image_filename or "unknown",
            image_shape=image_shape,
            scale_mm_per_px=self.state.scale_mm_per_px,
            next_label_id=self.state.next_label_id,
            regions=dict(self.state.regions),
        )
        io_manager.save_bundle_from_bytes(
            bundle_path,
            image_bytes=self.state.image_bytes,
            image_ext=self.state.image_ext,
            image_shape=image_shape,
            meta=meta,
        )
        self.state.dirty = False
        self._notify()

    def export_csv(self, csv_path: Path | str) -> None:
        """Write the sibling areas CSV. Independent of saving the bundle."""
        if self.state.label_map is None:
            raise ValueError("no image loaded")
        io_manager.save_areas_csv(csv_path, self.compute_area_rows())
