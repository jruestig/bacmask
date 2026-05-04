"""Kivy image canvas: image texture + mask overlay + lasso/brush preview.

Renders the full-resolution image fit-to-widget (letterboxed), overlays the
colored label map, draws the in-progress lasso polyline or brush stamp ghost,
and a brush cursor circle when the brush tool is active.
See knowledge/004 (perf), 014 (lasso), 016 (input), 026 (brush).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import cv2
import numpy as np
from kivy.graphics import (
    Color,
    Ellipse,
    Line,
    Rectangle,
    StencilPop,
    StencilPush,
    StencilUnUse,
    StencilUse,
)
from kivy.graphics.texture import Texture
from kivy.uix.widget import Widget

from bacmask.core import masking
from bacmask.services.mask_service import MaskService
from bacmask.ui.input.desktop_adapter import DesktopInputAdapter
from bacmask.ui.input.events import (
    Action,
    InputEvent,
    Pan,
    PointerDown,
    PointerMove,
    PointerUp,
    Zoom,
)
from bacmask.utils import image_utils

OVERLAY_ALPHA = 0.45
SELECTED_OUTLINE_COLOR = (0.0, 1.0, 1.0, 1.0)  # cyan
LASSO_PREVIEW_COLOR = (1.0, 1.0, 0.0, 1.0)  # yellow
BRUSH_ADD_COLOR = (0.2, 1.0, 0.2)  # green RGB (alpha applied per use)
BRUSH_SUBTRACT_COLOR = (1.0, 0.2, 0.2)  # red RGB
BRUSH_CREATE_COLOR = (0.3, 0.6, 1.0)  # blue RGB (new region preview)
LINE_COLOR = (1.0, 0.6, 0.0, 1.0)  # orange — committed measurement line
LINE_PREVIEW_COLOR = (1.0, 0.85, 0.0, 1.0)  # amber — in-progress line preview
LINE_SELECTED_COLOR = SELECTED_OUTLINE_COLOR
LINE_WIDTH = 1.4


def _brush_color_for(mode: str) -> tuple[float, float, float]:
    if mode == "subtract":
        return BRUSH_SUBTRACT_COLOR
    if mode == "create":
        return BRUSH_CREATE_COLOR
    return BRUSH_ADD_COLOR


BRUSH_GHOST_ALPHA = 0.55
BRUSH_CURSOR_ALPHA = 0.95

ZOOM_STEP = 1.2
VIEW_SCALE_MIN = 0.1
VIEW_SCALE_MAX = 20.0
# Fraction of the fit-displayed image that must remain visible in either axis.
PAN_KEEP_VISIBLE_FRAC = 0.1

# Minimap navigator — see knowledge/031.
MINIMAP_MAX = 220.0  # widget-px: max extent along either axis
MINIMAP_MARGIN = 12.0
MINIMAP_BG_COLOR = (0.05, 0.05, 0.05, 0.55)
MINIMAP_BORDER_COLOR = (1.0, 1.0, 1.0, 0.7)
MINIMAP_VIEWPORT_COLOR = SELECTED_OUTLINE_COLOR

# Arrow-key pan step is 10% of the canvas short side, clamped to this range.
PAN_STEP_MIN = 40.0
PAN_STEP_MAX = 120.0
PAN_STEP_FRAC = 0.10


def _vertex_bbox_clipped(
    vertices: np.ndarray,
    h: int,
    w: int,
) -> tuple[int, int, int, int] | None:
    """Half-open ``(y0, y1, x0, x1)`` bbox of ``vertices`` clipped to ``(h, w)``.

    Returns ``None`` when the bbox degenerates (empty vertices or the bbox
    falls entirely outside the image).
    """
    if len(vertices) == 0:
        return None
    x0 = max(0, int(vertices[:, 0].min()))
    x1 = min(w, int(vertices[:, 0].max()) + 1)
    y0 = max(0, int(vertices[:, 1].min()))
    y1 = min(h, int(vertices[:, 1].max()) + 1)
    if x0 >= x1 or y0 >= y1:
        return None
    return y0, y1, x0, x1


class ImageCanvas(Widget):
    def __init__(
        self,
        service: MaskService,
        *,
        on_action: Callable[[str], bool] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.service = service
        # Canvas is a pure translator — Action events route up to the app's
        # single dispatcher. ``None`` is allowed so tests can build the widget
        # without wiring; in that case Action events are silently dropped.
        self._on_action: Callable[[str], bool] | None = on_action
        self._image_texture: Texture | None = None
        self._overlay_texture: Texture | None = None
        self._last_image: np.ndarray | None = None
        # -1 forces overlay rebuild on the first state notification even when
        # `regions_version` is still 0 (e.g. bundle loaded into a fresh state).
        self._last_regions_version: int = -1
        # Edge-detection for brush-stroke end. When the active stroke
        # transitions non-None → None (commit, cancel, or subtract-empties-
        # delete), the canvas-local preview points get cleared as a state
        # effect — not as a side-effect of which key was pressed.
        self._last_brush_stroke_active: bool = False
        # Rendering cache: float32 alpha-over accumulators (RGB + A) plus the
        # uint8 RGBA buffer uploaded to the GPU. Populated on every
        # ``regions_version`` bump by walking ``state.regions`` (polygons are
        # the only truth — see knowledge/030). No mask-diff snapshot; the
        # accumulator is rebuilt from scratch per bump.
        self._overlay_acc_rgb: np.ndarray | None = None
        self._overlay_acc_a: np.ndarray | None = None
        self._overlay_rgba_buf: np.ndarray | None = None
        # Brush preview path in image-space coords. Source of truth for the
        # in-progress stroke's visible footprint — drawn as a single Kivy Line
        # with rounded caps/joints, which is far cheaper than re-blitting a
        # full-image RGBA texture per PointerMove.
        self._brush_preview_pts: list[tuple[int, int]] = []
        self._input = DesktopInputAdapter(emit=self._on_input)
        # Last pointer position seen on this canvas (window-space). Used for
        # the brush cursor circle while the brush tool is active.
        self._last_pointer_pos: tuple[float, float] | None = None

        # UI-local view transform (not persisted, not in SessionState).
        # view_offset is in display-space (top-down Y) pixels.
        self._view_scale: float = 1.0
        self._view_offset: tuple[float, float] = (0.0, 0.0)

        # True while a PointerDown landed inside the minimap and the gesture
        # has not yet ended. Drives viewport re-centering on subsequent moves.
        self._minimap_drag: bool = False

        service.subscribe(self._on_state_changed)
        self.bind(size=lambda *a: self._repaint(), pos=lambda *a: self._repaint())

    # ---- state change handling ---------------------------------------------

    def _on_state_changed(self) -> None:
        # Image texture rebuilds only when the image object actually changes
        # (rare — on load_image / load_bundle). Also reset view transform
        # because the old pan/zoom is meaningless for a new image.
        state = self.service.state
        if state.image is not self._last_image:
            self._rebuild_image_texture()
            self._last_image = state.image
            self._view_scale = 1.0
            self._view_offset = (0.0, 0.0)
            # New image dimensions → drop the overlay accumulators so the
            # next update allocates at the correct shape and re-composites
            # from a clean slate.
            self._overlay_reset()
            self._last_regions_version = -1
        # Overlay texture only rebuilds when regions actually change. Selection
        # / tool / calibration notifies skip this (and the per-frame lasso /
        # brush drag notifies too — they don't touch regions_version).
        if state.regions_version != self._last_regions_version:
            self._update_overlay()
            self._last_regions_version = state.regions_version
        stroke_active_now = state.active_brush_stroke is not None
        if self._last_brush_stroke_active and not stroke_active_now:
            self._brush_preview_pts = []
        self._last_brush_stroke_active = stroke_active_now
        self._repaint()

    def _rebuild_image_texture(self) -> None:
        img = self.service.state.image
        if img is None:
            self._image_texture = None
            return
        rgb = _to_rgb_uint8(img)
        h, w = rgb.shape[:2]
        tex = Texture.create(size=(w, h), colorfmt="rgb")
        tex.blit_buffer(rgb.tobytes(), colorfmt="rgb", bufferfmt="ubyte")
        tex.flip_vertical()
        self._image_texture = tex

    def _overlay_reset(self) -> None:
        """Drop all overlay buffers. Next ``_update_overlay`` rebuilds from scratch."""
        self._overlay_acc_rgb = None
        self._overlay_acc_a = None
        self._overlay_rgba_buf = None
        self._overlay_texture = None

    def _update_overlay(self) -> None:
        """Rebuild the overlay RGBA buffer + ``label_map`` from the polygon set.

        Walks ``state.regions`` in ascending ``label_id`` order — highest id
        lands last and wins visually on overlapping pixels (knowledge/025).
        For each polygon we:

        1. Compute its vertex bbox.
        2. ``cv2.fillPoly`` a bool mask inside that bbox.
        3. Alpha-over the region's color into ``_overlay_acc_rgb`` /
           ``_overlay_acc_a`` restricted to that bbox.
        4. ``cv2.fillPoly`` the label id into ``state.label_map`` (also bbox-
           local via :func:`masking.paint_label_map_bbox`).

        The old implementation kept a ``_overlay_tracked`` snapshot of
        per-region masks and did added/removed/changed diffs against it. That
        machinery (and the per-region mask store it hung off of) is gone —
        polygons are canonical (knowledge/030), so the overlay is a pure
        projection of ``state.regions``.
        """
        lm = self.service.state.label_map
        regions = self.service.state.regions
        if lm is None or not regions:
            self._overlay_reset()
            # Even with no regions, zero the label_map so stale click-hits
            # from a previous session can't resolve to a removed region.
            if lm is not None:
                lm.fill(0)
            return
        h, w = lm.shape

        # Fresh accumulators every rebuild — no cross-call state. At N<=1000
        # regions on a 4 MP image this allocates ~50 MB + negligible per-call
        # dominated by the polygon fills themselves (knowledge/030 perf).
        self._overlay_acc_rgb = np.zeros((h, w, 3), dtype=np.float32)
        self._overlay_acc_a = np.zeros((h, w), dtype=np.float32)
        if self._overlay_rgba_buf is None or self._overlay_rgba_buf.shape[:2] != (h, w):
            self._overlay_rgba_buf = np.zeros((h, w, 4), dtype=np.uint8)
        else:
            self._overlay_rgba_buf.fill(0)

        # Paint the label_map from polygons too — same walk, same bbox clip.
        # Full-image bbox so every region is considered; the helper skips
        # polygons whose vertex bbox lies outside its sub-window, which for a
        # whole-image window is everyone.
        masking.paint_label_map_bbox(lm, regions, (0, h, 0, w))

        for lid in sorted(regions):
            verts = np.asarray(regions[lid].get("vertices", []), dtype=np.int32).reshape(-1, 2)
            if len(verts) < 3:
                continue
            bbox = _vertex_bbox_clipped(verts, h, w)
            if bbox is None:
                continue
            self._composite_polygon_bbox(lid, verts, bbox)

        # Buffer the full-image RGBA and upload once. Partial-bbox rebuilds
        # are no longer worth the bookkeeping now that the accumulator is
        # rebuilt whole every bump.
        self._rebuild_rgba_bbox((0, h, 0, w))
        self._blit_overlay_texture(h, w)

    def _composite_polygon_bbox(
        self,
        label_id: int,
        vertices: np.ndarray,
        bbox: tuple[int, int, int, int],
    ) -> None:
        """Alpha-over this polygon's color onto the accumulator within ``bbox``.

        ``vertices`` is the full-image (x, y) int32 vertex array. We rasterize
        a bool sub-mask covering the bbox window via ``cv2.fillPoly`` and
        apply straight-alpha "over" blend (source over destination) inside
        the polygon footprint. Caller passes ``label_id`` so the color table
        lookup matches the pre-rewrite palette.
        """
        y0, y1, x0, x1 = bbox
        acc_rgb = self._overlay_acc_rgb
        acc_a = self._overlay_acc_a
        assert acc_rgb is not None and acc_a is not None
        bh = y1 - y0
        bw = x1 - x0
        if bh <= 0 or bw <= 0:
            return
        sub_raster = np.zeros((bh, bw), dtype=np.uint8)
        pts = vertices.copy()
        pts[:, 0] -= x0
        pts[:, 1] -= y0
        cv2.fillPoly(sub_raster, [pts.reshape(-1, 1, 2)], color=1)
        sub_mask = sub_raster.astype(bool)
        if not sub_mask.any():
            return
        sub_rgb = acc_rgb[y0:y1, x0:x1]
        sub_a = acc_a[y0:y1, x0:x1]
        r, g, b = image_utils.region_color(label_id)
        src_rgb = np.array([r, g, b], dtype=np.float32) / 255.0
        a_src = float(OVERLAY_ALPHA)
        one_minus = 1.0 - a_src
        dst_a = sub_a[sub_mask]
        out_a = a_src + dst_a * one_minus
        weight_dst = (dst_a * one_minus / out_a)[:, None]
        weight_src = (a_src / out_a)[:, None]
        sub_rgb[sub_mask] = src_rgb[None, :] * weight_src + sub_rgb[sub_mask] * weight_dst
        sub_a[sub_mask] = out_a

    def _rebuild_rgba_bbox(self, bbox: tuple[int, int, int, int]) -> None:
        """Convert float32 accumulators → uint8 RGBA within ``bbox``."""
        y0, y1, x0, x1 = bbox
        acc_rgb = self._overlay_acc_rgb
        acc_a = self._overlay_acc_a
        rgba = self._overlay_rgba_buf
        assert acc_rgb is not None and acc_a is not None and rgba is not None
        rgba[y0:y1, x0:x1, :3] = np.clip(acc_rgb[y0:y1, x0:x1] * 255.0, 0, 255).astype(np.uint8)
        rgba[y0:y1, x0:x1, 3] = np.clip(acc_a[y0:y1, x0:x1] * 255.0, 0, 255).astype(np.uint8)

    def _blit_overlay_texture(self, h: int, w: int) -> None:
        """Upload the RGBA buffer to the GPU. Allocates a new ``Texture`` only
        when the buffer shape changes — otherwise reuses the existing texture
        via ``blit_buffer``.
        """
        rgba = self._overlay_rgba_buf
        assert rgba is not None
        tex = self._overlay_texture
        if tex is None or tex.size != (w, h):
            tex = Texture.create(size=(w, h), colorfmt="rgba")
            tex.flip_vertical()
            self._overlay_texture = tex
        tex.blit_buffer(rgba.tobytes(), colorfmt="rgba", bufferfmt="ubyte")

    def _repaint(self) -> None:
        self.canvas.clear()
        img = self.service.state.image
        if img is None or self._image_texture is None:
            return

        img_h, img_w = img.shape[:2]
        _, off_x, off_y, disp_w, disp_h = image_utils.fit_to_widget(
            image_size=(img_w, img_h),
            widget_size=(self.width, self.height),
        )
        vs = self._view_scale
        vox, voy = self._view_offset
        # View-transformed rectangle in display (top-down) space.
        tx = off_x + vox
        ty_top = off_y + voy
        tw = disp_w * vs
        th = disp_h * vs
        # Convert top-down Y to Kivy Y-up for Rectangle pos.
        kivy_pos_y = self.y + (self.height - ty_top - th)

        # Stencil only caps the canvas at its TOP edge — this protects the
        # toolbar + calibration above from zoomed-image overflow. Horizontal
        # overflow (into the results panel on the right) and downward overflow
        # are intentionally allowed, matching the pre-stencil behavior the
        # user prefers.
        stencil_margin = max(self.width, self.height) * 10 + 1000
        stencil_pos = (self.x - stencil_margin, self.y - stencil_margin)
        stencil_size = (self.width + 2 * stencil_margin, self.height + stencil_margin)

        with self.canvas:
            StencilPush()
            Rectangle(pos=stencil_pos, size=stencil_size)
            StencilUse()

            Color(1, 1, 1, 1)
            Rectangle(
                texture=self._image_texture,
                pos=(self.x + tx, kivy_pos_y),
                size=(tw, th),
            )
            if self._overlay_texture is not None:
                Color(1, 1, 1, 1)
                Rectangle(
                    texture=self._overlay_texture,
                    pos=(self.x + tx, kivy_pos_y),
                    size=(tw, th),
                )

            # Brush-stroke ghost preview — drawn as a single Kivy Line with
            # rounded caps/joints. One draw call per move beats re-blitting an
            # HxW RGBA texture every PointerMove for large images.
            stroke = self.service.state.active_brush_stroke
            if stroke is not None and self._brush_preview_pts:
                self._draw_brush_preview(stroke.mode, (img_w, img_h))

            # Selected region outline (from stored polygon vertices)
            sid = self.service.state.selected_region_id
            if sid is not None and sid in self.service.state.regions:
                verts = self.service.state.regions[sid].get("vertices", [])
                if len(verts) >= 2:
                    pts = self._image_points_to_widget(verts, (img_w, img_h))
                    Color(*SELECTED_OUTLINE_COLOR)
                    Line(points=pts, width=1.5, close=True)

            # Committed measurement lines
            lines = self.service.state.lines
            if lines:
                selected_line = self.service.state.selected_line_id
                for lid, meta in sorted(lines.items()):
                    pts = self._image_points_to_widget([meta["p1"], meta["p2"]], (img_w, img_h))
                    if not pts:
                        continue
                    Color(*(LINE_SELECTED_COLOR if lid == selected_line else LINE_COLOR))
                    Line(points=pts, width=LINE_WIDTH)

            # In-progress line preview
            active_line = self.service.state.active_line
            if active_line is not None:
                pts = self._image_points_to_widget(
                    [active_line["p1"], active_line["p2"]], (img_w, img_h)
                )
                if pts:
                    Color(*LINE_PREVIEW_COLOR)
                    Line(points=pts, width=LINE_WIDTH)

            # In-progress lasso polyline preview
            lasso = self.service.state.active_lasso
            if lasso is not None and len(lasso) >= 2:
                pts = self._image_points_to_widget(lasso, (img_w, img_h))
                Color(*LASSO_PREVIEW_COLOR)
                Line(points=pts, width=1.2)
            # Dashed closing chord: cursor → lasso start. Previews the snap-close
            # chord that cv2.fillPoly applies implicitly on release.
            if lasso is not None and len(lasso) >= 1 and self._last_pointer_pos is not None:
                start_pts = self._image_points_to_widget([lasso[0]], (img_w, img_h))
                if start_pts:
                    sx, sy = start_pts[0], start_pts[1]
                    cx, cy = self._last_pointer_pos
                    Color(*LASSO_PREVIEW_COLOR)
                    Line(
                        points=[sx, sy, cx, cy],
                        width=1.0,
                        dash_length=6,
                        dash_offset=4,
                    )

            # Brush cursor circle — render only while the brush is active and
            # we have a known pointer position on this canvas.
            if self.service.state.active_tool == "brush" and self._last_pointer_pos is not None:
                self._draw_brush_cursor((img_w, img_h))

            StencilUnUse()
            Rectangle(pos=stencil_pos, size=stencil_size)
            StencilPop()

            # Minimap is drawn *after* the stencil pop so the corner overlay
            # is never clipped by the stencil that protects the toolbar edge.
            self._draw_minimap((img_w, img_h))

    def _draw_brush_preview(
        self,
        mode: str,
        image_size: tuple[int, int],
    ) -> None:
        """Draw the in-progress brush stroke as a single rounded polyline.

        Coordinates come from ``self._brush_preview_pts`` (image-space). Width
        is the brush diameter mapped to widget pixels. One Line draw call,
        regardless of stroke length — orders of magnitude cheaper than rebuilding
        a full-image RGBA texture per PointerMove.
        """
        if not self._brush_preview_pts:
            return
        img_w, img_h = image_size
        s, _ox, _oy, _, _ = image_utils.fit_to_widget((img_w, img_h), (self.width, self.height))
        radius_widget = self.service.state.brush_radius_px * s * self._view_scale
        if radius_widget < 0.5:
            return
        rgb = _brush_color_for(mode)
        Color(rgb[0], rgb[1], rgb[2], BRUSH_GHOST_ALPHA)
        if len(self._brush_preview_pts) == 1:
            ix, iy = self._brush_preview_pts[0]
            wpts = self._image_points_to_widget([(ix, iy)], image_size)
            wx, wy = wpts[0], wpts[1]
            Ellipse(
                pos=(wx - radius_widget, wy - radius_widget),
                size=(radius_widget * 2, radius_widget * 2),
            )
            return
        flat = self._image_points_to_widget(self._brush_preview_pts, image_size)
        # Kivy ``Line.width`` controls the visual half-thickness in pixels; the
        # rendered stroke is roughly 2*width wide. ``radius_widget`` therefore
        # produces a polyline whose footprint matches the disc stamp on the
        # underlying mask (diameter = 2*r).
        Line(
            points=flat,
            width=max(1.0, radius_widget),
            cap="round",
            joint="round",
        )

    def _draw_brush_cursor(self, image_size: tuple[int, int]) -> None:
        """Draw a circle outline at the pointer matching brush_radius_px (image-space)."""
        if self._last_pointer_pos is None:
            return
        img_w, img_h = image_size
        s, _ox, _oy, _, _ = image_utils.fit_to_widget((img_w, img_h), (self.width, self.height))
        radius_px_widget = self.service.state.brush_radius_px * s * self._view_scale
        if radius_px_widget < 1:
            return
        wx, wy = self._last_pointer_pos
        stroke = self.service.state.active_brush_stroke
        if stroke is not None:
            mode = stroke.mode
        else:
            mode = self.service.state.brush_default_mode
        rgb = _brush_color_for(mode)
        Color(rgb[0], rgb[1], rgb[2], BRUSH_CURSOR_ALPHA)
        Line(
            circle=(wx, wy, radius_px_widget),
            width=1.2,
        )

    def _image_points_to_widget(
        self,
        pts,
        image_size: tuple[int, int],
    ) -> list[float]:
        """Map image-space ``(x, y)`` points to a flat widget-space [x, y, ...] list.

        Accepts any iterable of (x, y) pairs (list of tuples, ndarray, etc.).
        Flips Y (image top-left → Kivy bottom-left) and applies the view transform.
        Vectorized with numpy so long lasso strokes don't pay a Python-loop cost
        per PointerMove.
        """
        img_w, img_h = image_size
        s, off_x, off_y, _, _ = image_utils.fit_to_widget((img_w, img_h), (self.width, self.height))
        total = s * self._view_scale
        vox, voy = self._view_offset
        arr = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
        if arr.size == 0:
            return []
        xs = arr[:, 0] * total + off_x + vox + self.x
        ys_top = arr[:, 1] * total + off_y + voy
        ys = self.y + self.height - ys_top
        out = np.empty(arr.shape[0] * 2, dtype=np.float32)
        out[0::2] = xs
        out[1::2] = ys
        return out.tolist()

    # ---- minimap navigator (knowledge/031) ---------------------------------

    def _minimap_rect(
        self,
        image_size: tuple[int, int],
    ) -> tuple[float, float, float, float] | None:
        """Return ``(x_left, y_bottom, mm_w, mm_h)`` in widget Y-up coords, or ``None``.

        Returns ``None`` when not zoomed in or when the image is missing —
        the minimap is hidden in those cases (see knowledge/031).
        """
        if self._view_scale <= 1.0 + 1e-6:
            return None
        img_w, img_h = image_size
        if img_w <= 0 or img_h <= 0:
            return None
        scale = min(MINIMAP_MAX / img_w, MINIMAP_MAX / img_h)
        mm_w = img_w * scale
        mm_h = img_h * scale
        if mm_w >= self.width - 2 * MINIMAP_MARGIN or mm_h >= self.height - 2 * MINIMAP_MARGIN:
            # Canvas too small — hide minimap rather than cover the whole view.
            return None
        x_left = self.x + self.width - MINIMAP_MARGIN - mm_w
        y_top = self.y + self.height - MINIMAP_MARGIN
        y_bot = y_top - mm_h
        return x_left, y_bot, mm_w, mm_h

    def _draw_minimap(self, image_size: tuple[int, int]) -> None:
        rect = self._minimap_rect(image_size)
        if rect is None or self._image_texture is None:
            return
        x_left, y_bot, mm_w, mm_h = rect
        img_w, img_h = image_size

        Color(*MINIMAP_BG_COLOR)
        Rectangle(pos=(x_left - 2, y_bot - 2), size=(mm_w + 4, mm_h + 4))

        Color(1, 1, 1, 1)
        Rectangle(texture=self._image_texture, pos=(x_left, y_bot), size=(mm_w, mm_h))

        if self._overlay_texture is not None:
            Color(1, 1, 1, 1)
            Rectangle(texture=self._overlay_texture, pos=(x_left, y_bot), size=(mm_w, mm_h))

        Color(*MINIMAP_BORDER_COLOR)
        Line(rectangle=(x_left, y_bot, mm_w, mm_h), width=1.0)

        # Viewport rectangle — image-space bbox of what's currently visible.
        tl = image_utils.display_to_image_view(
            (0.0, 0.0),
            (img_w, img_h),
            (self.width, self.height),
            self._view_scale,
            self._view_offset,
        )
        br = image_utils.display_to_image_view(
            (float(self.width), float(self.height)),
            (img_w, img_h),
            (self.width, self.height),
            self._view_scale,
            self._view_offset,
        )
        scale = mm_w / img_w
        ix0 = max(0.0, min(float(img_w), tl[0]))
        iy0 = max(0.0, min(float(img_h), tl[1]))
        ix1 = max(0.0, min(float(img_w), br[0]))
        iy1 = max(0.0, min(float(img_h), br[1]))
        if ix1 <= ix0 or iy1 <= iy0:
            return
        y_top = y_bot + mm_h
        vp_x = x_left + ix0 * scale
        vp_w = (ix1 - ix0) * scale
        vp_h = (iy1 - iy0) * scale
        vp_y_top = y_top - iy0 * scale
        vp_y_bot = vp_y_top - vp_h
        Color(*MINIMAP_VIEWPORT_COLOR)
        Line(rectangle=(vp_x, vp_y_bot, vp_w, vp_h), width=1.4)

    def _minimap_hit(self, window_pos: tuple[float, float], image_size: tuple[int, int]) -> bool:
        rect = self._minimap_rect(image_size)
        if rect is None:
            return False
        x_left, y_bot, mm_w, mm_h = rect
        wx, wy = window_pos
        return x_left <= wx <= x_left + mm_w and y_bot <= wy <= y_bot + mm_h

    def _minimap_center_on(
        self,
        window_pos: tuple[float, float],
        image_size: tuple[int, int],
    ) -> None:
        """Re-center the viewport on the image pixel under ``window_pos`` in the minimap."""
        rect = self._minimap_rect(image_size)
        if rect is None:
            return
        x_left, y_bot, mm_w, mm_h = rect
        img_w, img_h = image_size
        scale = mm_w / img_w
        y_top = y_bot + mm_h
        wx, wy = window_pos
        ix = (wx - x_left) / scale
        iy = (y_top - wy) / scale
        ix = max(0.0, min(float(img_w), ix))
        iy = max(0.0, min(float(img_h), iy))

        s, off_x, off_y, _, _ = image_utils.fit_to_widget((img_w, img_h), (self.width, self.height))
        total = s * self._view_scale
        new_vox = self.width / 2 - ix * total - off_x
        new_voy = self.height / 2 - iy * total - off_y
        self._view_offset = self._clamp_offset((new_vox, new_voy), image_size)
        self._repaint()

    # ---- public pan (keyboard arrows, knowledge/031) -----------------------

    def pan_by_action(self, action: str) -> None:
        """Pan the viewport by a fixed step in response to an arrow-key action."""
        img = self.service.state.image
        if img is None:
            return
        img_h, img_w = img.shape[:2]
        short = min(self.width, self.height)
        if short <= 0:
            return
        step = max(PAN_STEP_MIN, min(PAN_STEP_MAX, short * PAN_STEP_FRAC))
        if action == "pan_left":
            delta = (step, 0.0)
        elif action == "pan_right":
            delta = (-step, 0.0)
        elif action == "pan_up":
            delta = (0.0, -step)
        elif action == "pan_down":
            delta = (0.0, step)
        else:
            return
        self._apply_pan(delta, (img_w, img_h))

    # ---- input -------------------------------------------------------------

    def on_touch_down(self, touch) -> bool:
        if not self.collide_point(*touch.pos):
            return False
        img = self.service.state.image
        if img is not None:
            img_h, img_w = img.shape[:2]
            if self._minimap_hit(touch.pos, (img_w, img_h)):
                self._minimap_drag = True
                self._minimap_center_on(touch.pos, (img_w, img_h))
                touch.grab(self)
                return True
        return self._input.on_touch_down(touch)

    def on_touch_move(self, touch) -> bool:
        if self._minimap_drag:
            img = self.service.state.image
            if img is not None:
                img_h, img_w = img.shape[:2]
                self._minimap_center_on(touch.pos, (img_w, img_h))
            return True
        return self._input.on_touch_move(touch)

    def on_touch_up(self, touch) -> bool:
        if self._minimap_drag:
            self._minimap_drag = False
            if touch.grab_current is self:
                touch.ungrab(self)
            return True
        return self._input.on_touch_up(touch)

    def _on_input(self, event: InputEvent) -> None:
        img = self.service.state.image
        if img is None:
            return
        img_h, img_w = img.shape[:2]
        if isinstance(event, PointerDown):
            self._last_pointer_pos = event.pos
            xy = self._widget_pos_to_image(event.pos, (img_h, img_w))
            if xy is None:
                return
            tool = self.service.state.active_tool
            if tool == "brush":
                self._on_brush_pointer_down(xy)
            elif tool == "line":
                self._on_line_pointer_down(xy)
            else:
                self._on_lasso_pointer_down(xy)
        elif isinstance(event, PointerMove):
            self._last_pointer_pos = event.pos
            xy = self._widget_pos_to_image(event.pos, (img_h, img_w))
            if xy is None:
                self._repaint()
                return
            if self.service.state.active_brush_stroke is not None:
                # Append to canvas-local preview (image-space) BEFORE the
                # service notify so _repaint sees the new segment.
                self._brush_preview_pts.append(xy)
                self.service.add_brush_sample(xy)
            elif self.service.state.active_lasso is not None:
                self.service.add_lasso_point(xy)
            elif self.service.state.active_line is not None:
                self.service.update_line(xy)
            else:
                # Just refresh the cursor circle position.
                self._repaint()
        elif isinstance(event, PointerUp):
            xy = self._widget_pos_to_image(event.pos, (img_h, img_w))
            self._on_pointer_up(xy)
        elif isinstance(event, Zoom):
            self._apply_zoom(event.center, event.delta, (img_w, img_h))
        elif isinstance(event, Pan):
            self._apply_pan(event.delta, (img_w, img_h))
        elif isinstance(event, Action):
            if self._on_action is not None:
                self._on_action(event.name)

    # ---- per-tool pointer handlers -----------------------------------------

    def _on_lasso_pointer_down(self, xy: tuple[int, int]) -> None:
        """Lasso tool: tap on mask selects; tap on bg starts a new-region lasso."""
        hit = self._region_at(xy)
        if hit is not None:
            self.service.select_region(hit)
            return
        self.service.clear_selection()
        self.service.begin_lasso(xy)

    def _on_brush_pointer_down(self, xy: tuple[int, int]) -> None:
        """Brush tool: press-down resolves a target via the selection lock."""
        target = self.service.begin_brush_stroke(xy)
        if target is None:
            # No region under cursor and no selection → no-op.
            return
        self._brush_preview_pts = [xy]

    def _on_line_pointer_down(self, xy: tuple[int, int]) -> None:
        """Line tool: press-down anchors p1; drag updates p2; release commits."""
        self.service.clear_selection()
        self.service.clear_line_selection()
        self.service.begin_line(xy)

    def _on_pointer_up(self, xy: tuple[int, int] | None) -> None:
        svc = self.service
        if svc.state.active_brush_stroke is not None:
            # ``end_brush_stroke`` flips ``state.active_brush_stroke`` to None;
            # the canvas's state subscription clears ``_brush_preview_pts`` on
            # that transition (see ``_on_state_changed``).
            svc.end_brush_stroke()
            return
        if svc.state.active_lasso is not None:
            svc.close_lasso()
            return
        if svc.state.active_line is not None:
            # Fall back to the last known endpoint if the release landed
            # outside the image — discard happens when both endpoints match.
            end = xy if xy is not None else svc.state.active_line["p2"]
            svc.commit_line(end)

    # ---- view transform -----------------------------------------------------

    def _apply_zoom(
        self,
        center: tuple[float, float],
        delta: float,
        image_size: tuple[int, int],
    ) -> None:
        """Zoom at ``center`` (window-space, Y-up) so the image pixel under it stays put."""
        img_w, img_h = image_size
        # Convert cursor to display-space (top-down, widget-local).
        cx, cy = center
        lx = cx - self.x
        ly_top = self.height - (cy - self.y)

        factor = ZOOM_STEP if delta > 0 else 1.0 / ZOOM_STEP
        new_scale = max(VIEW_SCALE_MIN, min(VIEW_SCALE_MAX, self._view_scale * factor))
        if new_scale == self._view_scale:
            return

        # Pixel under cursor before zoom.
        ix, iy = image_utils.display_to_image_view(
            (lx, ly_top),
            (img_w, img_h),
            (self.width, self.height),
            self._view_scale,
            self._view_offset,
        )
        # Solve for new offset so the same image pixel maps to the same display point.
        # display = image * s * new_scale + off_fit + new_offset
        s, off_x, off_y, _, _ = image_utils.fit_to_widget((img_w, img_h), (self.width, self.height))
        new_vox = lx - ix * s * new_scale - off_x
        new_voy = ly_top - iy * s * new_scale - off_y
        self._view_scale = new_scale
        self._view_offset = self._clamp_offset((new_vox, new_voy), image_size)
        self._repaint()

    def _apply_pan(
        self,
        delta: tuple[float, float],
        image_size: tuple[int, int],
    ) -> None:
        """Apply a pan delta given in widget-space Y-up pixels."""
        dx, dy = delta
        # Widget Y-up delta → display top-down delta flips y.
        vox, voy = self._view_offset
        self._view_offset = self._clamp_offset((vox + dx, voy - dy), image_size)
        self._repaint()

    def _clamp_offset(
        self,
        offset: tuple[float, float],
        image_size: tuple[int, int],
    ) -> tuple[float, float]:
        """Clamp the offset so the image can never be more than (1 - keep_frac) off-screen."""
        img_w, img_h = image_size
        s, _off_x, _off_y, disp_w, disp_h = image_utils.fit_to_widget(
            (img_w, img_h), (self.width, self.height)
        )
        if disp_w <= 0 or disp_h <= 0:
            return offset
        vs = self._view_scale
        tw = disp_w * vs
        th = disp_h * vs
        keep_w = max(1.0, tw * PAN_KEEP_VISIBLE_FRAC)
        keep_h = max(1.0, th * PAN_KEEP_VISIBLE_FRAC)
        # In display (top-down) space, the image rectangle spans
        # [off_fit + vox, off_fit + vox + tw] in x, similarly in y.
        # We need at least `keep_w` of it to overlap [0, widget_w].
        off_x_fit = _off_x
        off_y_fit = _off_y
        vox_min = keep_w - off_x_fit - tw
        vox_max = self.width - off_x_fit - keep_w
        voy_min = keep_h - off_y_fit - th
        voy_max = self.height - off_y_fit - keep_h
        vox, voy = offset
        # When the allowed range is invalid (negative because the widget is smaller
        # than keep_w), center on 0 to avoid snapping surprises.
        if vox_min <= vox_max:
            vox = min(vox_max, max(vox_min, vox))
        if voy_min <= voy_max:
            voy = min(voy_max, max(voy_min, voy))
        return vox, voy

    def _region_at(self, xy: tuple[int, int]) -> int | None:
        lm = self.service.state.label_map
        if lm is None:
            return None
        ix, iy = xy
        label = int(lm[iy, ix])
        if label == 0 or label not in self.service.state.regions:
            return None
        return label

    def _widget_pos_to_image(
        self,
        window_pos: tuple[float, float],
        image_shape: tuple[int, int],
    ) -> tuple[int, int] | None:
        img_h, img_w = image_shape
        wx, wy = window_pos
        lx = wx - self.x
        ly_from_top = self.height - (wy - self.y)
        ix, iy = image_utils.display_to_image_view(
            (lx, ly_from_top),
            (img_w, img_h),
            (self.width, self.height),
            self._view_scale,
            self._view_offset,
        )
        if 0 <= ix < img_w and 0 <= iy < img_h:
            return int(ix), int(iy)
        return None


def _to_rgb_uint8(img: np.ndarray) -> np.ndarray:
    """Convert cv2-style image (gray / BGR / BGRA, any dtype) to HxWx3 RGB uint8."""
    if img.dtype != np.uint8:
        if img.dtype == np.uint16:
            img = (img / 257).astype(np.uint8)
        else:
            img = np.clip(img, 0, 255).astype(np.uint8)
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
