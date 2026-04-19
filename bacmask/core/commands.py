"""Reversible mask-mutation commands. See knowledge/003, 014, 026, 030.

Commands only ever touch the canonical polygon store (``state.regions``) and
the derived display cache (``state.label_map``). Per-region bool masks and
cached area counts are **not** stored in state (knowledge/030); commands
therefore snapshot vertex lists only, which is O(V) memory per command
regardless of image resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from bacmask.core import masking


def _union_bbox(
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


@dataclass
class LassoCloseCommand:
    """Commit a closed lasso polygon as a brand-new region.

    The service runs the raw scribble through the raster → largest-CC →
    contour cleanup pipeline and hands us the cleaned vertex list. We simply
    append it to ``state.regions`` with a fresh monotonic id and paint it
    into the display cache inside its own vertex bbox. Because the new
    region always has the highest id, painting last inside the bbox is
    correct — no full repaint needed.
    """

    vertices: np.ndarray
    assigned_label_id: int = field(init=False, default=0)
    _prev_next_id: int = field(init=False, default=0)

    def apply(self, state: Any) -> None:
        if state.label_map is None:
            raise ValueError("state.label_map is not initialized")
        self._prev_next_id = state.next_label_id
        self.assigned_label_id = state.next_label_id
        verts = np.asarray(self.vertices, dtype=np.int32).reshape(-1, 2)
        state.regions[self.assigned_label_id] = {
            "name": f"region_{self.assigned_label_id:02d}",
            "vertices": verts.tolist(),
        }
        # Highest id so far → painting the polygon inside its own vertex
        # bbox is sufficient; pixels it does not cover retain whatever label
        # was already there (knowledge/025 newest-on-top).
        bbox = masking.vertices_bbox(verts, state.label_map.shape)
        if bbox is not None:
            y0, _y1, x0, _x1 = bbox
            pts = verts.copy()
            pts[:, 0] -= x0
            pts[:, 1] -= y0
            sub = state.label_map[bbox[0] : bbox[1], bbox[2] : bbox[3]]
            cv2.fillPoly(sub, [pts.reshape(-1, 1, 2)], color=int(self.assigned_label_id))
        state.next_label_id += 1
        state.dirty = True
        state.regions_version += 1

    def undo(self, state: Any) -> None:
        meta = state.regions.pop(self.assigned_label_id, None)
        # Repaint the removed region's bbox from the remaining polygon set so
        # any label that was hidden underneath the popped polygon reappears.
        if meta is not None and state.label_map is not None:
            verts = np.asarray(meta["vertices"], dtype=np.int32).reshape(-1, 2)
            bbox = masking.vertices_bbox(verts, state.label_map.shape)
            if bbox is not None:
                masking.paint_label_map_bbox(state.label_map, state.regions, bbox)
        state.next_label_id = self._prev_next_id
        state.dirty = True
        state.regions_version += 1


@dataclass
class DeleteRegionCommand:
    """Drop a region from the canonical store. ID is not re-used (knowledge/014)."""

    label_id: int
    _name: str | None = field(init=False, default=None)
    _vertices: list[list[int]] | None = field(init=False, default=None)

    def apply(self, state: Any) -> None:
        meta = state.regions.pop(self.label_id, None)
        if meta is None:
            state.dirty = True
            state.regions_version += 1
            return
        self._name = meta["name"]
        self._vertices = [list(v) for v in meta["vertices"]]
        if state.label_map is not None:
            verts = np.asarray(self._vertices, dtype=np.int32).reshape(-1, 2)
            bbox = masking.vertices_bbox(verts, state.label_map.shape)
            if bbox is not None:
                masking.paint_label_map_bbox(state.label_map, state.regions, bbox)
        state.dirty = True
        state.regions_version += 1

    def undo(self, state: Any) -> None:
        if self._vertices is None or self._name is None:
            return
        state.regions[self.label_id] = {
            "name": self._name,
            "vertices": [list(v) for v in self._vertices],
        }
        if state.label_map is not None:
            verts = np.asarray(self._vertices, dtype=np.int32).reshape(-1, 2)
            bbox = masking.vertices_bbox(verts, state.label_map.shape)
            if bbox is not None:
                masking.paint_label_map_bbox(state.label_map, state.regions, bbox)
        state.dirty = True
        state.regions_version += 1


@dataclass
class VertexEditCommand:
    """Replace a region's polygon with a new vertex list.

    Kept as a thin compatibility shim for the ``MaskService.edit_vertices``
    entrypoint — wave 2 step 2 deletes both. The body is now identical to
    :class:`BrushStrokeCommand` minus the target-shape-mismatch guard.
    """

    label_id: int
    new_vertices: np.ndarray
    _old_vertices: list[list[int]] | None = field(init=False, default=None)

    def apply(self, state: Any) -> None:
        if self.label_id not in state.regions:
            raise ValueError(f"region {self.label_id} does not exist")
        if state.label_map is None:
            raise ValueError("state.label_map is not initialized")

        new_verts = np.asarray(self.new_vertices, dtype=np.int32).reshape(-1, 2)
        if len(new_verts) < 3:
            raise ValueError(f"polygon needs at least 3 vertices, got {len(new_verts)}")

        self._old_vertices = [list(v) for v in state.regions[self.label_id]["vertices"]]
        old_verts = np.asarray(self._old_vertices, dtype=np.int32).reshape(-1, 2)
        state.regions[self.label_id]["vertices"] = new_verts.tolist()
        bbox = _union_bbox(
            masking.vertices_bbox(old_verts, state.label_map.shape),
            masking.vertices_bbox(new_verts, state.label_map.shape),
        )
        if bbox is not None:
            masking.paint_label_map_bbox(state.label_map, state.regions, bbox)
        state.dirty = True
        state.regions_version += 1

    def undo(self, state: Any) -> None:
        if self._old_vertices is None or self.label_id not in state.regions:
            return
        current = np.asarray(state.regions[self.label_id]["vertices"], dtype=np.int32).reshape(
            -1, 2
        )
        old_verts = np.asarray(self._old_vertices, dtype=np.int32).reshape(-1, 2)
        state.regions[self.label_id]["vertices"] = [list(v) for v in self._old_vertices]
        if state.label_map is not None:
            bbox = _union_bbox(
                masking.vertices_bbox(current, state.label_map.shape),
                masking.vertices_bbox(old_verts, state.label_map.shape),
            )
            if bbox is not None:
                masking.paint_label_map_bbox(state.label_map, state.regions, bbox)
        state.dirty = True
        state.regions_version += 1


@dataclass
class BrushStrokeCommand:
    """Commit the result of an add/subtract brush stroke (knowledge/026, 030).

    The service computes the post-stroke ``new_vertices`` (disc stamp
    accumulation, connected-component filter, contour re-derivation on a
    bbox-local scratch buffer) and hands them here. This command is a plain
    vertex swap — snapshots the pre-edit vertex list so undo can restore it
    exactly, then repaints the label_map inside the union of old and new
    vertex bboxes.

    Overlap with other regions is allowed (knowledge/025); this command does
    not touch any region other than ``label_id``.
    """

    label_id: int
    new_vertices: np.ndarray
    _old_vertices: list[list[int]] | None = field(init=False, default=None)

    def apply(self, state: Any) -> None:
        if self.label_id not in state.regions:
            raise ValueError(f"region {self.label_id} does not exist")
        if state.label_map is None:
            raise ValueError("state.label_map is not initialized")

        new_verts = np.asarray(self.new_vertices, dtype=np.int32).reshape(-1, 2)
        if len(new_verts) < 3:
            raise ValueError(f"polygon needs at least 3 vertices, got {len(new_verts)}")

        self._old_vertices = [list(v) for v in state.regions[self.label_id]["vertices"]]
        old_verts = np.asarray(self._old_vertices, dtype=np.int32).reshape(-1, 2)

        state.regions[self.label_id]["vertices"] = new_verts.tolist()
        bbox = _union_bbox(
            masking.vertices_bbox(old_verts, state.label_map.shape),
            masking.vertices_bbox(new_verts, state.label_map.shape),
        )
        if bbox is not None:
            masking.paint_label_map_bbox(state.label_map, state.regions, bbox)
        state.dirty = True
        state.regions_version += 1

    def undo(self, state: Any) -> None:
        if self._old_vertices is None:
            return
        if self.label_id not in state.regions:
            return
        current = np.asarray(state.regions[self.label_id]["vertices"], dtype=np.int32).reshape(
            -1, 2
        )
        old_verts = np.asarray(self._old_vertices, dtype=np.int32).reshape(-1, 2)
        state.regions[self.label_id]["vertices"] = [list(v) for v in self._old_vertices]
        if state.label_map is not None:
            bbox = _union_bbox(
                masking.vertices_bbox(current, state.label_map.shape),
                masking.vertices_bbox(old_verts, state.label_map.shape),
            )
            if bbox is not None:
                masking.paint_label_map_bbox(state.label_map, state.regions, bbox)
        state.dirty = True
        state.regions_version += 1
