"""Kivy image canvas: image texture + mask overlay + lasso preview.

Renders the full-resolution image fit-to-widget (letterboxed), overlays the
colored label map, and draws the in-progress lasso polyline.
See knowledge/004 (perf), 014 (lasso), 016 (input).
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from kivy.graphics import Color, Line, Rectangle
from kivy.graphics.texture import Texture
from kivy.uix.widget import Widget

from bacmask.services.mask_service import MaskService
from bacmask.ui.input.desktop_adapter import DesktopInputAdapter
from bacmask.ui.input.events import (
    Action,
    InputEvent,
    PointerDown,
    PointerMove,
    PointerUp,
)
from bacmask.utils import image_utils

OVERLAY_ALPHA = 0.45
SELECTED_OUTLINE_COLOR = (0.0, 1.0, 1.0, 1.0)  # cyan
LASSO_PREVIEW_COLOR = (1.0, 1.0, 0.0, 1.0)  # yellow


class ImageCanvas(Widget):
    def __init__(self, service: MaskService, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.service = service
        self._image_texture: Texture | None = None
        self._overlay_texture: Texture | None = None
        self._last_image: np.ndarray | None = None
        self._input = DesktopInputAdapter(emit=self._on_input)

        service.subscribe(self._on_state_changed)
        self.bind(size=lambda *a: self._repaint(), pos=lambda *a: self._repaint())

    # ---- state change handling ---------------------------------------------

    def _on_state_changed(self) -> None:
        # Image texture rebuilds only when the image object actually changes
        # (rare — on load_image / load_bundle).
        if self.service.state.image is not self._last_image:
            self._rebuild_image_texture()
            self._last_image = self.service.state.image
        # Overlay texture rebuilds whenever label_map could have changed
        # (everything except in-progress lasso drag).
        if self.service.state.active_lasso is None:
            self._rebuild_overlay_texture()
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
        if lm is None or not regions:
            self._overlay_texture = None
            return
        h, w = lm.shape
        max_id_in_map = int(lm.max())
        lut_size = max(max_id_in_map, max(regions.keys(), default=0)) + 1
        lut = np.zeros((lut_size, 4), dtype=np.uint8)
        alpha = int(255 * OVERLAY_ALPHA)
        for lid in regions:
            r, g, b = image_utils.region_color(lid)
            lut[lid] = (r, g, b, alpha)
        rgba = lut[lm]

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

        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(
                texture=self._image_texture,
                pos=(self.x + off_x, self.y + off_y),
                size=(disp_w, disp_h),
            )
            if self._overlay_texture is not None:
                Color(1, 1, 1, 1)
                Rectangle(
                    texture=self._overlay_texture,
                    pos=(self.x + off_x, self.y + off_y),
                    size=(disp_w, disp_h),
                )

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
                pts = self._image_points_to_widget(
                    lasso.tolist() if isinstance(lasso, np.ndarray) else lasso,
                    (img_w, img_h),
                )
                Color(*LASSO_PREVIEW_COLOR)
                Line(points=pts, width=1.2)

    def _image_points_to_widget(
        self,
        pts: list,
        image_size: tuple[int, int],
    ) -> list[float]:
        """Map a list of image-space (x, y) points to a flat widget-space [x, y, ...] list.

        Flips Y because image origin is top-left, widget (Kivy) origin is bottom-left.
        """
        img_w, img_h = image_size
        out: list[float] = []
        for px, py in pts:
            wx, wy = image_utils.image_to_display(
                (float(px), float(py)),
                (img_w, img_h),
                (self.width, self.height),
            )
            out.extend([self.x + wx, self.y + self.height - wy])
        return out

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
            xy = self._widget_pos_to_image(event.pos, (img_h, img_w))
            if xy is None:
                return
            hit = self._region_at(xy)
            if hit is not None:
                self.service.select_region(hit)
                return
            self.service.clear_selection()
            self.service.begin_lasso(xy)
        elif isinstance(event, PointerMove):
            if self.service.state.active_lasso is None:
                return
            xy = self._widget_pos_to_image(event.pos, (img_h, img_w))
            if xy is None:
                return
            self.service.add_lasso_point(xy)
        elif isinstance(event, PointerUp):
            if self.service.state.active_lasso is not None:
                self.service.close_lasso()
        elif isinstance(event, Action):
            self._handle_action(event.name)

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
        elif name == "cancel_lasso":
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

    def _widget_pos_to_image(
        self,
        window_pos: tuple[float, float],
        image_shape: tuple[int, int],
    ) -> tuple[int, int] | None:
        img_h, img_w = image_shape
        wx, wy = window_pos
        lx = wx - self.x
        ly_from_top = self.height - (wy - self.y)
        ix, iy = image_utils.display_to_image(
            (lx, ly_from_top), (img_w, img_h), (self.width, self.height)
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
