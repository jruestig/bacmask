"""High-level mask-editing orchestration.

The UI calls only methods here — never core commands or io_manager directly.
Owns a SessionState and a history stack; exposes intent-based actions and
notifies subscribers on every state change.

See knowledge/001 (separation), 002 (state), 003 (commands), 014 (lasso),
026 (brush).
"""

from __future__ import annotations

import logging
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from bacmask.config import defaults
from bacmask.core import area, calibration, io_manager, masking
from bacmask.core.commands import (
    BrushStrokeCommand,
    DeleteRegionCommand,
    LassoCloseCommand,
    VertexEditCommand,
)
from bacmask.core.history import UndoRedoStack
from bacmask.core.state import BrushStroke, SessionState, Tool

log = logging.getLogger(__name__)


def _disc_bbox(cx: int, cy: int, r: int, h: int, w: int) -> tuple[int, int, int, int]:
    """Half-open (y0, y1, x0, x1) bbox of a disc clipped to image bounds."""
    y0 = max(0, cy - r)
    y1 = min(h, cy + r + 1)
    x0 = max(0, cx - r)
    x1 = min(w, cx + r + 1)
    return y0, y1, x0, x1


def _segment_bbox(
    a: tuple[int, int],
    b: tuple[int, int],
    r: int,
    h: int,
    w: int,
) -> tuple[int, int, int, int]:
    """Half-open bbox of a swept disc along segment ``a → b``, clipped to image."""
    ax, ay = a
    bx, by = b
    y0 = max(0, min(ay, by) - r)
    y1 = min(h, max(ay, by) + r + 1)
    x0 = max(0, min(ax, bx) - r)
    x1 = min(w, max(ax, bx) + r + 1)
    return y0, y1, x0, x1


def _expand_bbox(
    a: tuple[int, int, int, int] | None,
    b: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """Union of two half-open bboxes; ``None`` means take ``b`` as-is."""
    if a is None:
        return b
    return (
        min(a[0], b[0]),
        max(a[1], b[1]),
        min(a[2], b[2]),
        max(a[3], b[3]),
    )


def _any_outside_bbox(
    mask: np.ndarray,
    y0: int,
    y1: int,
    x0: int,
    x1: int,
) -> bool:
    """True iff any True pixel of ``mask`` lies outside the rectangle [y0:y1, x0:x1].

    Used by the brush commit fast-path to decide whether a subtract that
    emptied the stroke bbox actually emptied the entire region. Avoids a full
    ``mask.any()`` scan when the bbox already covers most of the image: each
    side strip is at most one row/column tall, so the total work is O(H + W)
    in the worst case (and short-circuits on the first hit).
    """
    h, w = mask.shape
    if y0 > 0 and mask[:y0, :].any():
        return True
    if y1 < h and mask[y1:, :].any():
        return True
    if x0 > 0 and mask[y0:y1, :x0].any():
        return True
    if x1 < w and mask[y0:y1, x1:].any():
        return True
    return False


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
        self.state.active_brush_stroke = None
        self.state.selected_region_id = None
        self.state.dirty = False
        self.state.regions_version += 1
        self.history.clear()
        self._active_lasso = []
        self._notify()

    # ---- tool selection -----------------------------------------------------

    def set_active_tool(self, tool: Tool) -> None:
        """Set the active editing tool. In-flight strokes are not cancelled —
        per knowledge/026, a started stroke completes on its own terms; the
        switch lands on the next press-down.
        """
        if tool not in ("lasso", "brush"):
            raise ValueError(f"unknown tool: {tool!r}")
        if self.state.active_tool == tool:
            return
        self.state.active_tool = tool
        self._notify()

    def set_brush_radius(self, radius: int) -> None:
        r = int(radius)
        lo, hi = defaults.BRUSH_RADIUS_MIN_PX, defaults.BRUSH_RADIUS_MAX_PX
        if not (lo <= r <= hi):
            raise ValueError(f"brush radius {r} out of range [{lo}, {hi}]")
        if self.state.brush_radius_px == r:
            return
        self.state.brush_radius_px = r
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
        """Commit the in-progress lasso. Returns label_id or None if discarded.

        The stored polygon is re-derived from the rasterized stroke: the raw
        path is filled (``cv2.fillPoly`` even-odd), reduced to its largest
        connected component (same deterministic tiebreak as the brush edit
        commit, knowledge/026), and its outer contour becomes the canonical
        vertex list. This kills the "random chord on release" artifact — the
        user's release point and any self-intersecting scribble lobes no
        longer leak into the stored shape.
        """

        def _discard() -> None:
            self._active_lasso = []
            self.state.active_lasso = None
            self._notify()

        if len(self._active_lasso) < 3:
            _discard()
            return None
        if self.state.label_map is None:
            _discard()
            return None
        raw_verts = np.asarray(self._active_lasso, dtype=np.int32)
        if masking.polygon_area(raw_verts) <= 0.0:
            log.warning(
                "lasso discarded: polygon with %d vertices encloses zero area",
                len(raw_verts),
            )
            _discard()
            return None

        image_shape = self.state.label_map.shape
        raw_mask = masking.rasterize_polygon_mask(raw_verts, image_shape)
        clean_mask = masking.largest_connected_component(raw_mask)
        if not clean_mask.any():
            _discard()
            return None
        clean_verts = masking.contour_vertices(clean_mask)
        if len(clean_verts) < 3:
            _discard()
            return None

        cmd = LassoCloseCommand(clean_verts, region_mask=clean_mask)
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

    # ---- brush stroke (knowledge/026) ---------------------------------------

    def begin_brush_stroke(
        self,
        pos: tuple[int, int],
        modifiers: Sequence[str] = (),
    ) -> int | None:
        """Begin a brush stroke at image-space ``pos``.

        Resolves the target region from the press-down pixel via ``label_map``
        (highest-id wins on overlap). Modifier keys decide add vs. subtract:
        no modifier or ``shift`` → add; ``ctrl`` → subtract (Ctrl wins over
        Shift).

        Returns the locked target label_id, or ``None`` if the press-down hit
        background (no-op, no history). On success, ``selected_region_id`` is
        also set to the target.
        """
        if self.state.label_map is None:
            return None
        ix, iy = int(pos[0]), int(pos[1])
        h, w = self.state.label_map.shape
        if not (0 <= ix < w and 0 <= iy < h):
            return None
        target = int(self.state.label_map[iy, ix])
        if target == 0 or target not in self.state.regions:
            return None

        mods = {m.lower() for m in modifiers}
        mode = "subtract" if "ctrl" in mods else "add"

        r = self.state.brush_radius_px
        stroke_mask = np.zeros((h, w), dtype=bool)
        masking.stamp_brush_disc(stroke_mask, (ix, iy), r)
        self.state.active_brush_stroke = BrushStroke(
            target_id=target,
            mode=mode,
            mask=stroke_mask,
            last_pos=(ix, iy),
            bbox=_disc_bbox(ix, iy, r, h, w),
        )
        if self.state.selected_region_id != target:
            self.state.selected_region_id = target
        self._notify()
        return target

    def add_brush_sample(self, pos: tuple[int, int]) -> None:
        """Add a pointer sample to the in-progress brush stroke.

        Sweeps a disc along the segment from the last sample to ``pos`` so
        fast cursor moves leave no gaps (knowledge/026 step 3). Updates the
        stroke bbox in lockstep so the commit path can skip a full
        ``np.where`` pass on the stroke mask.
        """
        stroke = self.state.active_brush_stroke
        if stroke is None:
            return
        ix, iy = int(pos[0]), int(pos[1])
        r = self.state.brush_radius_px
        prev = stroke.last_pos
        masking.stamp_brush_segment(stroke.mask, prev, (ix, iy), r)
        stroke.last_pos = (ix, iy)
        h, w = stroke.mask.shape
        stroke.bbox = _expand_bbox(stroke.bbox, _segment_bbox(prev, (ix, iy), r, h, w))
        self._notify()

    def cancel_brush_stroke(self) -> None:
        if self.state.active_brush_stroke is None:
            return
        self.state.active_brush_stroke = None
        self._notify()

    def end_brush_stroke(self) -> str | None:
        """Commit the in-progress brush stroke.

        Returns one of:
        * ``"added"`` — add stroke committed.
        * ``"subtracted"`` — subtract stroke committed.
        * ``"deleted"`` — subtract emptied the region; routed via DeleteRegionCommand.
        * ``None`` — discarded silently (no intersection or no-op).

        The connected-component pass and contour re-derivation are restricted
        to the bounding box of the post-edit mask — for a small region in a
        large image this is the difference between operating on a few hundred
        pixels and a few million. The full-image mask is only built (in place
        from the target snapshot) when something actually changes.
        """
        stroke = self.state.active_brush_stroke
        if stroke is None:
            return None
        # Always clear the stroke buffer at the start of commit — even on
        # discard paths there must be no leftover ghost.
        self.state.active_brush_stroke = None

        target_id = stroke.target_id
        if target_id not in self.state.regions:
            self._notify()
            return None
        target_mask = self.state.region_masks.get(target_id)
        if target_mask is None:
            self._notify()
            return None

        s_mask = stroke.mask
        # Stroke bbox is tracked incrementally during sampling — no full
        # ``np.where(s_mask)`` pass needed at commit time, which is a sizeable
        # win on large images.
        if stroke.bbox is None:
            self._notify()
            return None
        sy0, sy1, sx0, sx1 = stroke.bbox
        if sy0 >= sy1 or sx0 >= sx1:
            self._notify()
            return None

        target_crop = target_mask[sy0:sy1, sx0:sx1]
        s_crop = s_mask[sy0:sy1, sx0:sx1]
        if not s_crop.any():
            self._notify()
            return None

        # No-op detection on the crop (cheap):
        #   add      → no painted pixel lay outside the target
        #   subtract → brush never touched any target pixel
        if stroke.mode == "add":
            if not (s_crop & ~target_crop).any():
                self._notify()
                return None
        else:
            if not (s_crop & target_crop).any():
                self._notify()
                return None

        # Apply the boolean op in place on a copy of the target mask, but only
        # within the stroke bbox — the rest of the mask is identical to the
        # target by construction.
        new_mask = target_mask.copy()
        if stroke.mode == "add":
            np.bitwise_or(target_crop, s_crop, out=new_mask[sy0:sy1, sx0:sx1])
        else:
            np.logical_and(target_crop, ~s_crop, out=new_mask[sy0:sy1, sx0:sx1])

        # Subtract emptied the region → route via DeleteRegionCommand so the
        # undo path + monotonic-id behavior are unified with explicit delete.
        # Cheap check: subtract result is bounded by target, so only the bbox
        # needs inspecting.
        if stroke.mode == "subtract" and not new_mask[sy0:sy1, sx0:sx1].any():
            # The subtract emptied the stroke bbox; need to confirm nothing
            # else remains outside the bbox. Outside the bbox new_mask equals
            # target_mask, so an "empty" outcome requires target outside bbox
            # to also be empty — i.e. target was entirely inside the bbox.
            if not _any_outside_bbox(target_mask, sy0, sy1, sx0, sx1):
                cmd = DeleteRegionCommand(label_id=target_id)
                self.history.push(cmd, self.state)
                if self.state.selected_region_id == target_id:
                    self.state.selected_region_id = None
                self._notify()
                return "deleted"

        # Bbox of the post-edit mask. For subtract this is ⊆ target's bbox;
        # for add it's union(target_bbox, stroke_bbox). Computing it via
        # np.where on the full mask is one more O(HxW) pass — acceptable, and
        # the CC / contour ops on the resulting crop are tiny by comparison.
        n_ys, n_xs = np.where(new_mask)
        if len(n_ys) == 0:
            # Defensive — handled by the subtract branch above, but covers add
            # edge cases too.
            self._notify()
            return None
        ny0, ny1 = int(n_ys.min()), int(n_ys.max()) + 1
        nx0, nx1 = int(n_xs.min()), int(n_xs.max()) + 1

        crop = new_mask[ny0:ny1, nx0:nx1]
        filtered_crop = masking.largest_connected_component(crop)
        if not filtered_crop.any():
            self._notify()
            return None
        crop_verts = masking.contour_vertices(filtered_crop)
        if len(crop_verts) < 3:
            self._notify()
            return None

        # Paste the filtered CC back into the full mask. Outside the new-mask
        # bbox there is nothing (by definition of bbox), so a fresh zero mask
        # + bbox paste is exact.
        filtered = np.zeros_like(new_mask)
        filtered[ny0:ny1, nx0:nx1] = filtered_crop
        # Translate vertex coords from crop-space back to image-space.
        new_vertices = crop_verts + np.array([nx0, ny0], dtype=np.int32)

        edit_cmd = BrushStrokeCommand(
            label_id=target_id,
            new_vertices=new_vertices,
            new_region_mask=filtered,
        )
        self.history.push(edit_cmd, self.state)
        self._notify()
        return "added" if stroke.mode == "add" else "subtracted"

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
