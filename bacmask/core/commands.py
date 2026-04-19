"""Reversible mask-mutation commands. See knowledge/003, 014, 026."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from bacmask.core import masking


@dataclass
class LassoCloseCommand:
    vertices: np.ndarray
    # Optional pre-rasterized region mask. When provided, apply uses it instead
    # of re-rasterizing ``vertices`` — this is the path the service takes after
    # running the largest-CC/contour cleanup, where the mask is the source of
    # truth and the vertex list is derived from it. Re-rasterizing would shift
    # the mask by up to a pixel on each edge.
    region_mask: np.ndarray | None = None
    assigned_label_id: int = field(init=False, default=0)
    _prev_next_id: int = field(init=False, default=0)

    def apply(self, state: Any) -> None:
        self._prev_next_id = state.next_label_id
        self.assigned_label_id = state.next_label_id
        if self.region_mask is not None:
            region_mask = np.asarray(self.region_mask, dtype=bool)
            if region_mask.shape != state.label_map.shape:
                raise ValueError(
                    f"region_mask shape {region_mask.shape} != label_map {state.label_map.shape}"
                )
        else:
            region_mask = masking.rasterize_polygon_mask(self.vertices, state.label_map.shape)
        state.region_masks[self.assigned_label_id] = region_mask
        # Paint into the display cache — this region is the newest, so it wins
        # on any overlapping pixels per knowledge/025.
        state.label_map[region_mask] = self.assigned_label_id
        state.regions[self.assigned_label_id] = {
            "name": f"region_{self.assigned_label_id:02d}",
            "vertices": np.asarray(self.vertices, dtype=np.int32).tolist(),
        }
        state.next_label_id += 1
        state.dirty = True
        state.regions_version += 1

    def undo(self, state: Any) -> None:
        state.region_masks.pop(self.assigned_label_id, None)
        state.regions.pop(self.assigned_label_id, None)
        # Rebuild the display cache from what's left.
        masking.repaint_label_map(state.label_map, state.region_masks)
        state.next_label_id = self._prev_next_id
        state.dirty = True
        state.regions_version += 1


@dataclass
class DeleteRegionCommand:
    label_id: int
    _region_mask: np.ndarray | None = field(init=False, default=None)
    _region_meta: dict[str, Any] | None = field(init=False, default=None)

    def apply(self, state: Any) -> None:
        self._region_mask = state.region_masks.pop(self.label_id, None)
        self._region_meta = state.regions.pop(self.label_id, None)
        # Rebuild display cache — dropping a region may expose other regions
        # underneath if they overlapped.
        masking.repaint_label_map(state.label_map, state.region_masks)
        state.dirty = True
        state.regions_version += 1

    def undo(self, state: Any) -> None:
        if self._region_mask is not None:
            state.region_masks[self.label_id] = self._region_mask
        if self._region_meta is not None:
            state.regions[self.label_id] = self._region_meta
        masking.repaint_label_map(state.label_map, state.region_masks)
        state.dirty = True
        state.regions_version += 1


@dataclass
class VertexEditCommand:
    """Replace a region's polygon with a new vertex list.

    Overlaps with other regions are allowed (knowledge/025) — we no longer clip
    at neighbors. This command is kept for direct polygon replacement; the
    brush-based add/subtract edit flow uses :class:`BrushStrokeCommand`
    (knowledge/026).
    """

    label_id: int
    new_vertices: np.ndarray
    _old_vertices: list[list[int]] | None = field(init=False, default=None)
    _old_region_mask: np.ndarray | None = field(init=False, default=None)

    def apply(self, state: Any) -> None:
        if self.label_id not in state.regions:
            raise ValueError(f"region {self.label_id} does not exist")
        if state.label_map is None:
            raise ValueError("state.label_map is not initialized")

        new_verts = np.asarray(self.new_vertices, dtype=np.int32)
        if len(new_verts) < 3:
            raise ValueError(f"polygon needs at least 3 vertices, got {len(new_verts)}")

        # Snapshot for undo (before any mutation).
        self._old_vertices = [list(v) for v in state.regions[self.label_id]["vertices"]]
        old_mask = state.region_masks.get(self.label_id)
        self._old_region_mask = old_mask.copy() if old_mask is not None else None

        new_mask = masking.rasterize_polygon_mask(new_verts, state.label_map.shape)
        state.region_masks[self.label_id] = new_mask
        masking.repaint_label_map(state.label_map, state.region_masks)

        state.regions[self.label_id]["vertices"] = new_verts.tolist()
        state.dirty = True
        state.regions_version += 1

    def undo(self, state: Any) -> None:
        if self._old_vertices is None:
            return
        if self._old_region_mask is not None:
            state.region_masks[self.label_id] = self._old_region_mask
        else:
            state.region_masks.pop(self.label_id, None)
        masking.repaint_label_map(state.label_map, state.region_masks)
        state.regions[self.label_id]["vertices"] = self._old_vertices
        state.dirty = True
        state.regions_version += 1


@dataclass
class BrushStrokeCommand:
    """Commit the result of an add/subtract brush stroke (knowledge/026).

    The service computes the post-stroke ``new_vertices`` + ``new_region_mask``
    (disc stamp accumulation, connected-component filter, contour
    re-derivation) and hands them here. This command is a simple state swap —
    it stores the pre-edit vertex list and region_mask so undo can restore
    them exactly, then repaints the display label_map.

    Overlap with other regions is allowed (knowledge/025); this command does
    not touch any region other than ``label_id``.
    """

    label_id: int
    new_vertices: np.ndarray
    new_region_mask: np.ndarray
    _old_vertices: list[list[int]] | None = field(init=False, default=None)
    _old_region_mask: np.ndarray | None = field(init=False, default=None)

    def apply(self, state: Any) -> None:
        if self.label_id not in state.regions:
            raise ValueError(f"region {self.label_id} does not exist")
        if state.label_map is None:
            raise ValueError("state.label_map is not initialized")

        new_verts = np.asarray(self.new_vertices, dtype=np.int32).reshape(-1, 2)
        new_mask = np.asarray(self.new_region_mask, dtype=bool)
        if new_mask.shape != state.label_map.shape:
            raise ValueError(
                f"new_region_mask shape {new_mask.shape} != label_map {state.label_map.shape}"
            )

        # Snapshot for undo (before any mutation). The service hands us a
        # freshly-built ``new_region_mask`` and never touches it again, so we
        # can take ownership directly — no defensive ``.copy()`` is needed,
        # which saves an HxW bool copy per brush commit on large images.
        self._old_vertices = [list(v) for v in state.regions[self.label_id]["vertices"]]
        old_mask = state.region_masks.get(self.label_id)
        self._old_region_mask = old_mask.copy() if old_mask is not None else None

        state.region_masks[self.label_id] = new_mask
        state.regions[self.label_id]["vertices"] = new_verts.tolist()
        masking.repaint_label_map(state.label_map, state.region_masks)
        state.dirty = True
        state.regions_version += 1

    def undo(self, state: Any) -> None:
        if self._old_vertices is None:
            return
        if self._old_region_mask is not None:
            state.region_masks[self.label_id] = self._old_region_mask
        else:
            state.region_masks.pop(self.label_id, None)
        if self.label_id in state.regions:
            state.regions[self.label_id]["vertices"] = self._old_vertices
        masking.repaint_label_map(state.label_map, state.region_masks)
        state.dirty = True
        state.regions_version += 1
