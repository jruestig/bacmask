"""Canvas brush-tool interaction: targeting, stroke dispatch, modifier resolution."""

from __future__ import annotations

import os

os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")
os.environ.setdefault("KIVY_WINDOW", "mock")
os.environ.setdefault("KIVY_GL_BACKEND", "mock")

import numpy as np  # noqa: E402

from bacmask.core import masking  # noqa: E402
from bacmask.services.mask_service import MaskService  # noqa: E402
from bacmask.ui.input.events import PointerDown, PointerMove, PointerUp  # noqa: E402
from bacmask.ui.widgets.image_canvas import ImageCanvas  # noqa: E402


def _service_with_region(img_w: int = 50, img_h: int = 50) -> MaskService:
    svc = MaskService()
    img = np.zeros((img_h, img_w, 3), dtype=np.uint8)
    svc.state.image = img
    svc.state.image_filename = "mock.png"
    svc.state.label_map = np.zeros((img_h, img_w), dtype=np.uint16)
    # Pre-populate a square region at (10..20, 10..20) via direct state setup.
    verts = np.array([[10, 10], [20, 10], [20, 20], [10, 20]], dtype=np.int32)
    region_mask = masking.rasterize_polygon_mask(verts, (img_h, img_w))
    svc.state.region_masks[1] = region_mask
    svc.state.region_areas[1] = int(region_mask.sum())
    svc.state.regions[1] = {"name": "region_01", "vertices": verts.tolist()}
    svc.state.next_label_id = 2
    masking.repaint_label_map(svc.state.label_map, svc.state.region_masks)
    return svc


def _canvas(svc: MaskService, widget_w: float = 400.0, widget_h: float = 400.0) -> ImageCanvas:
    c: ImageCanvas = ImageCanvas.__new__(ImageCanvas)
    c.service = svc
    c._image_texture = None
    c._overlay_texture = None
    c._last_image = svc.state.image
    c._last_regions_version = -1
    c._ghost_texture = None
    c._ghost_signature = None
    c._last_pointer_pos = None
    c._view_scale = 1.0
    c._view_offset = (0.0, 0.0)
    c.x = 0.0
    c.y = 0.0
    c.width = widget_w
    c.height = widget_h
    c._repaint = lambda: None  # type: ignore[method-assign]
    return c


def _widget_pos_for_image_pixel(
    canvas: ImageCanvas,
    image_xy: tuple[float, float],
    image_size: tuple[int, int],
) -> tuple[float, float]:
    """Given an image pixel (x, y), compute the Kivy window-space (x, y) that
    maps back to it via the canvas' coord functions."""
    from bacmask.utils import image_utils

    wx, wy = image_utils.image_to_display_view(
        (float(image_xy[0]), float(image_xy[1])),
        image_size,
        (canvas.width, canvas.height),
        canvas._view_scale,
        canvas._view_offset,
    )
    # canvas._widget_pos_to_image flips Y — invert that here.
    return canvas.x + wx, canvas.y + canvas.height - wy


# ---- lasso tool: tap behavior ----------------------------------------------


def test_lasso_tool_tap_on_region_selects():
    svc = _service_with_region()
    assert svc.state.active_tool == "lasso"
    c = _canvas(svc)

    pos = _widget_pos_for_image_pixel(c, (15.0, 15.0), (50, 50))
    c._on_input(PointerDown(pos=pos, is_double=False))

    assert svc.state.selected_region_id == 1
    assert svc.state.active_lasso is None


def test_lasso_tool_tap_on_background_starts_new_lasso():
    svc = _service_with_region()
    c = _canvas(svc)

    pos = _widget_pos_for_image_pixel(c, (40.0, 40.0), (50, 50))
    c._on_input(PointerDown(pos=pos, is_double=False))

    assert svc.state.active_lasso is not None


# ---- brush tool: targeting -------------------------------------------------


def test_brush_press_on_background_without_selection_is_noop():
    svc = _service_with_region()
    svc.set_active_tool("brush")
    svc.clear_selection()
    c = _canvas(svc)
    pos = _widget_pos_for_image_pixel(c, (40.0, 40.0), (50, 50))
    c._on_input(PointerDown(pos=pos, is_double=False))
    assert svc.state.active_brush_stroke is None


def test_brush_press_on_region_begins_stroke_and_selects():
    svc = _service_with_region()
    svc.set_active_tool("brush")
    c = _canvas(svc)
    pos = _widget_pos_for_image_pixel(c, (15.0, 15.0), (50, 50))
    c._on_input(PointerDown(pos=pos, is_double=False))
    assert svc.state.active_brush_stroke is not None
    assert svc.state.active_brush_stroke.target_id == 1
    assert svc.state.active_brush_stroke.mode == "add"
    assert svc.state.selected_region_id == 1


def test_brush_press_with_subtract_mode():
    svc = _service_with_region()
    svc.set_active_tool("brush")
    svc.set_brush_default_mode("subtract")
    c = _canvas(svc)
    pos = _widget_pos_for_image_pixel(c, (15.0, 15.0), (50, 50))
    c._on_input(PointerDown(pos=pos, is_double=False))
    assert svc.state.active_brush_stroke.mode == "subtract"


def test_brush_drag_release_grows_region():
    svc = _service_with_region()
    svc.set_active_tool("brush")
    svc.set_brush_radius(3)
    before = int(svc.state.region_masks[1].sum())

    c = _canvas(svc)
    # Press inside the (10..20, 10..20) square; drag out past the right edge.
    path = [(15, 15), (20, 15), (24, 15)]
    c._on_input(
        PointerDown(
            pos=_widget_pos_for_image_pixel(c, path[0], (50, 50)),
            is_double=False,
        )
    )
    for p in path[1:]:
        c._on_input(PointerMove(pos=_widget_pos_for_image_pixel(c, p, (50, 50))))
    c._on_input(PointerUp(pos=_widget_pos_for_image_pixel(c, path[-1], (50, 50))))

    assert svc.state.active_brush_stroke is None
    assert int(svc.state.region_masks[1].sum()) > before


def test_brush_subtract_drag_release_shrinks_region():
    svc = _service_with_region()
    svc.set_active_tool("brush")
    svc.set_brush_radius(2)
    svc.set_brush_default_mode("subtract")
    before = int(svc.state.region_masks[1].sum())

    c = _canvas(svc)
    path = [(13, 18), (16, 18), (18, 18)]
    c._on_input(
        PointerDown(
            pos=_widget_pos_for_image_pixel(c, path[0], (50, 50)),
            is_double=False,
        )
    )
    for p in path[1:]:
        c._on_input(PointerMove(pos=_widget_pos_for_image_pixel(c, p, (50, 50))))
    c._on_input(PointerUp(pos=_widget_pos_for_image_pixel(c, path[-1], (50, 50))))

    after = int(svc.state.region_masks[1].sum())
    assert after < before
