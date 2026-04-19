"""Kivy image canvas: image texture + mask overlay + lasso/brush preview.

Renders the full-resolution image fit-to-widget (letterboxed), overlays the
colored label map, draws the in-progress lasso polyline or brush stamp ghost,
and a brush cursor circle when the brush tool is active.
See knowledge/004 (perf), 014 (lasso), 016 (input), 026 (brush).
"""

from __future__ import annotations

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
BRUSH_GHOST_ALPHA = 0.55
BRUSH_CURSOR_ALPHA = 0.95

ZOOM_STEP = 1.2
VIEW_SCALE_MIN = 0.1
VIEW_SCALE_MAX = 20.0
# Fraction of the fit-displayed image that must remain visible in either axis.
PAN_KEEP_VISIBLE_FRAC = 0.1


class ImageCanvas(Widget):
    def __init__(self, service: MaskService, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.service = service
        self._image_texture: Texture | None = None
        self._overlay_texture: Texture | None = None
        self._last_image: np.ndarray | None = None
        # -1 forces overlay rebuild on the first state notification even when
        # `regions_version` is still 0 (e.g. bundle loaded into a fresh state).
        self._last_regions_version: int = -1
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
            # Force overlay rebuild at the new image dimensions.
            self._last_regions_version = -1
        # Overlay texture only rebuilds when regions actually change. Selection
        # / tool / calibration notifies skip this (and the per-frame lasso /
        # brush drag notifies too — they don't touch regions_version).
        if state.regions_version != self._last_regions_version:
            self._rebuild_overlay_texture()
            self._last_regions_version = state.regions_version
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

    def _rebuild_overlay_texture(self) -> None:
        lm = self.service.state.label_map
        regions = self.service.state.regions
        region_masks = self.service.state.region_masks
        if lm is None or not regions:
            self._overlay_texture = None
            return
        h, w = lm.shape

        # Alpha-over composite each region's color layer in ascending label order
        # (oldest first). Overlap pixels blend both colors so the old region stays
        # visible under the new one. See knowledge/025.
        acc_rgb = np.zeros((h, w, 3), dtype=np.float32)
        acc_a = np.zeros((h, w), dtype=np.float32)
        a_src = float(OVERLAY_ALPHA)
        one_minus = 1.0 - a_src
        for lid in sorted(region_masks):
            if lid not in regions:
                continue
            mask = region_masks[lid]
            if not mask.any():
                continue
            r, g, b = image_utils.region_color(lid)
            src_rgb = np.array([r, g, b], dtype=np.float32) / 255.0

            dst_a = acc_a[mask]
            out_a = a_src + dst_a * one_minus
            # out_a is strictly > 0 here since a_src > 0.
            weight_dst = (dst_a * one_minus / out_a)[:, None]
            weight_src = (a_src / out_a)[:, None]
            acc_rgb[mask] = src_rgb[None, :] * weight_src + acc_rgb[mask] * weight_dst
            acc_a[mask] = out_a

        rgba = np.empty((h, w, 4), dtype=np.uint8)
        rgba[..., :3] = np.clip(acc_rgb * 255.0, 0, 255).astype(np.uint8)
        rgba[..., 3] = np.clip(acc_a * 255.0, 0, 255).astype(np.uint8)

        tex = Texture.create(size=(w, h), colorfmt="rgba")
        tex.blit_buffer(rgba.tobytes(), colorfmt="rgba", bufferfmt="ubyte")
        tex.flip_vertical()
        self._overlay_texture = tex

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
        rgb = BRUSH_ADD_COLOR if mode == "add" else BRUSH_SUBTRACT_COLOR
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
            rgb = BRUSH_ADD_COLOR if stroke.mode == "add" else BRUSH_SUBTRACT_COLOR
        else:
            rgb = BRUSH_ADD_COLOR
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

    # ---- input -------------------------------------------------------------

    def on_touch_down(self, touch) -> bool:
        if not self.collide_point(*touch.pos):
            return False
        return self._input.on_touch_down(touch)

    def on_touch_move(self, touch) -> bool:
        return self._input.on_touch_move(touch)

    def on_touch_up(self, touch) -> bool:
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
            else:
                # Just refresh the cursor circle position.
                self._repaint()
        elif isinstance(event, PointerUp):
            self._on_pointer_up()
        elif isinstance(event, Zoom):
            self._apply_zoom(event.center, event.delta, (img_w, img_h))
        elif isinstance(event, Pan):
            self._apply_pan(event.delta, (img_w, img_h))
        elif isinstance(event, Action):
            self._handle_action(event.name)

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
            self._brush_preview_pts = []
            return
        self._brush_preview_pts = [xy]

    def _on_pointer_up(self) -> None:
        svc = self.service
        if svc.state.active_brush_stroke is not None:
            svc.end_brush_stroke()
            self._brush_preview_pts = []
            return
        if svc.state.active_lasso is not None:
            svc.close_lasso()

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

    def _handle_action(self, name: str) -> None:
        svc = self.service
        if name == "close_lasso":
            svc.close_lasso()
        elif name == "cancel_stroke":
            # Whichever stroke is in flight, discard it. No history entry.
            if svc.state.active_brush_stroke is not None:
                svc.cancel_brush_stroke()
                self._brush_preview_pts = []
            else:
                svc.cancel_lasso()
        elif name == "undo":
            svc.undo()
        elif name == "redo":
            svc.redo()
        elif name == "delete_region":
            sid = svc.state.selected_region_id
            if sid is not None:
                try:
                    svc.delete_region(sid)
                except KeyError:
                    pass
        elif name == "select_lasso":
            svc.set_active_tool("lasso")
        elif name == "select_brush":
            svc.set_active_tool("brush")
        elif name == "toggle_brush_mode":
            svc.toggle_brush_default_mode()

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
