"""Reversible mask-mutation commands. See knowledge/003 & 014."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from bacmask.core import masking


@dataclass
class LassoCloseCommand:
    vertices: np.ndarray
    assigned_label_id: int = field(init=False, default=0)
    _prev_next_id: int = field(init=False, default=0)

    def apply(self, state: Any) -> None:
        self._prev_next_id = state.next_label_id
        self.assigned_label_id = state.next_label_id
        masking.rasterize_polygon(state.label_map, self.vertices, self.assigned_label_id)
        state.regions[self.assigned_label_id] = {
            "name": f"region_{self.assigned_label_id:02d}",
            "vertices": np.asarray(self.vertices, dtype=np.int32).tolist(),
        }
        state.next_label_id += 1
        state.dirty = True

    def undo(self, state: Any) -> None:
        masking.erase_region(state.label_map, self.assigned_label_id)
        state.regions.pop(self.assigned_label_id, None)
        state.next_label_id = self._prev_next_id
        state.dirty = True


@dataclass
class DeleteRegionCommand:
    label_id: int
    _mask_patch: np.ndarray | None = field(init=False, default=None)
    _bbox: tuple[int, int, int, int] | None = field(init=False, default=None)
    _region_meta: dict[str, Any] | None = field(init=False, default=None)

    def apply(self, state: Any) -> None:
        mask = state.label_map == self.label_id
        if not mask.any():
            self._mask_patch = None
            self._bbox = None
        else:
            ys, xs = np.where(mask)
            y0, y1 = int(ys.min()), int(ys.max()) + 1
            x0, x1 = int(xs.min()), int(xs.max()) + 1
            self._bbox = (y0, y1, x0, x1)
            self._mask_patch = state.label_map[y0:y1, x0:x1].copy()
            state.label_map[y0:y1, x0:x1][mask[y0:y1, x0:x1]] = 0
        self._region_meta = state.regions.pop(self.label_id, None)
        state.dirty = True

    def undo(self, state: Any) -> None:
        if self._mask_patch is not None and self._bbox is not None:
            y0, y1, x0, x1 = self._bbox
            restore = self._mask_patch == self.label_id
            state.label_map[y0:y1, x0:x1][restore] = self.label_id
        if self._region_meta is not None:
            state.regions[self.label_id] = self._region_meta
        state.dirty = True


@dataclass
class VertexEditCommand:
    """Move/add/remove vertices of an existing region. Clip-policy per knowledge/021.

    The new polygon rasterizes only into pixels that are either background or
    already owned by this region — adjacent regions keep their territory.
    """

    label_id: int
    new_vertices: np.ndarray
    _old_vertices: list[list[int]] | None = field(init=False, default=None)
    _bbox: tuple[int, int, int, int] | None = field(init=False, default=None)
    _patch: np.ndarray | None = field(init=False, default=None)

    def apply(self, state: Any) -> None:
        if self.label_id not in state.regions:
            raise ValueError(f"region {self.label_id} does not exist")
        if state.label_map is None:
            raise ValueError("state.label_map is not initialized")

        new_verts = np.asarray(self.new_vertices, dtype=np.int32)
        if len(new_verts) < 3:
            raise ValueError(f"polygon needs at least 3 vertices, got {len(new_verts)}")

        h, w = state.label_map.shape
        old_verts_list = state.regions[self.label_id]["vertices"]
        old_verts = np.asarray(old_verts_list, dtype=np.int32)

        # Union bbox of old + new polygons, clamped to image.
        all_verts = np.vstack([old_verts, new_verts])
        x0 = max(0, int(all_verts[:, 0].min()))
        x1 = min(w, int(all_verts[:, 0].max()) + 1)
        y0 = max(0, int(all_verts[:, 1].min()))
        y1 = min(h, int(all_verts[:, 1].max()) + 1)
        self._bbox = (y0, y1, x0, x1)

        # Snapshot for undo (before any mutation).
        self._patch = state.label_map[y0:y1, x0:x1].copy()
        self._old_vertices = [list(v) for v in old_verts_list]

        # Rasterize new polygon into a bbox-local temp mask.
        bbox_h = y1 - y0
        bbox_w = x1 - x0
        new_mask = np.zeros((bbox_h, bbox_w), dtype=np.uint8)
        shifted = new_verts - np.array([x0, y0], dtype=np.int32)
        cv2.fillPoly(new_mask, [shifted.reshape(-1, 1, 2)], color=1)
        inside_new = new_mask.astype(bool)

        # Clip: allowed = background ∪ self (computed before mutation).
        patch_view = state.label_map[y0:y1, x0:x1]
        allowed = (patch_view == 0) | (patch_view == self.label_id)

        # Zero the old region within bbox (own pixels only), then fill.
        patch_view[patch_view == self.label_id] = 0
        patch_view[inside_new & allowed] = self.label_id

        state.regions[self.label_id]["vertices"] = new_verts.tolist()
        state.dirty = True

    def undo(self, state: Any) -> None:
        if self._bbox is None or self._patch is None or self._old_vertices is None:
            return
        y0, y1, x0, x1 = self._bbox
        state.label_map[y0:y1, x0:x1] = self._patch
        state.regions[self.label_id]["vertices"] = self._old_vertices
        state.dirty = True
