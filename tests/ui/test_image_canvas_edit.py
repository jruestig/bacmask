"""Canvas edit-mode interaction: targeting, stroke dispatch, double-tap retarget."""

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


# ---- first-tap targeting ---------------------------------------------------


def test_edit_mode_first_tap_on_region_sets_target_no_stroke():
    svc = _service_with_region()
    svc.set_edit_mode(True)
    assert svc.state.selected_region_id is None

    c = _canvas(svc)
    window_pos = _widget_pos_for_image_pixel(c, (15.0, 15.0), (50, 50))
    c._on_input(PointerDown(pos=window_pos, is_double=False))

    assert svc.state.selected_region_id == 1
    # No lasso buffer started.
    assert svc.state.active_lasso is None


def test_edit_mode_first_tap_on_background_is_noop():
    svc = _service_with_region()
    svc.set_edit_mode(True)
    c = _canvas(svc)
    window_pos = _widget_pos_for_image_pixel(c, (40.0, 40.0), (50, 50))  # outside region
    c._on_input(PointerDown(pos=window_pos, is_double=False))

    assert svc.state.selected_region_id is None
    assert svc.state.active_lasso is None


# ---- double-tap retargeting ------------------------------------------------


def test_edit_mode_double_tap_on_background_clears_target():
    svc = _service_with_region()
    svc.set_edit_mode(True)
    svc.select_region(1)
    c = _canvas(svc)

    window_pos = _widget_pos_for_image_pixel(c, (40.0, 40.0), (50, 50))
    c._on_input(PointerDown(pos=window_pos, is_double=True))

    assert svc.state.selected_region_id is None


def test_edit_mode_double_tap_on_region_retargets():
    svc = _service_with_region()
    # Add a second region.
    verts2 = np.array([[30, 30], [40, 30], [40, 40], [30, 40]], dtype=np.int32)
    region_mask2 = masking.rasterize_polygon_mask(verts2, svc.state.label_map.shape)
    svc.state.region_masks[2] = region_mask2
    svc.state.regions[2] = {"name": "region_02", "vertices": verts2.tolist()}
    svc.state.next_label_id = 3
    masking.repaint_label_map(svc.state.label_map, svc.state.region_masks)

    svc.set_edit_mode(True)
    svc.select_region(1)
    c = _canvas(svc)

    window_pos = _widget_pos_for_image_pixel(c, (35.0, 35.0), (50, 50))
    c._on_input(PointerDown(pos=window_pos, is_double=True))
    assert svc.state.selected_region_id == 2


# ---- stroke dispatch -------------------------------------------------------


def test_edit_mode_press_drag_subtract_stroke_shrinks_region():
    svc = _service_with_region()
    svc.set_edit_mode(True)
    svc.select_region(1)
    before = int(svc.state.region_masks[1].sum())

    c = _canvas(svc)
    # Stroke starts outside, walks through the interior (>=3 samples between
    # the first entry and first exit so the truncated segment can form a
    # polygon), then exits. Target region is (10..20, 10..20).
    path = [(5, 15), (12, 12), (14, 17), (17, 17), (18, 12), (25, 15)]
    c._on_input(PointerDown(pos=_widget_pos_for_image_pixel(c, path[0], (50, 50))))
    for p in path[1:]:
        c._on_input(PointerMove(pos=_widget_pos_for_image_pixel(c, p, (50, 50))))
    c._on_input(PointerUp(pos=_widget_pos_for_image_pixel(c, path[-1], (50, 50))))

    after = int(svc.state.region_masks[1].sum())
    assert after < before
    assert svc.state.active_lasso is None


def test_edit_mode_press_drag_add_stroke_grows_region():
    svc = _service_with_region()
    svc.set_edit_mode(True)
    svc.select_region(1)
    before = int(svc.state.region_masks[1].sum())

    c = _canvas(svc)
    # Start inside the region, loop outside, re-enter. Add mode adds the lobe.
    path = [(15, 15), (25, 15), (27, 5), (22, 3), (17, 5), (15, 15)]
    c._on_input(PointerDown(pos=_widget_pos_for_image_pixel(c, path[0], (50, 50))))
    for p in path[1:]:
        c._on_input(PointerMove(pos=_widget_pos_for_image_pixel(c, p, (50, 50))))
    c._on_input(PointerUp(pos=_widget_pos_for_image_pixel(c, path[-1], (50, 50))))

    after = int(svc.state.region_masks[1].sum())
    assert after > before
    assert svc.state.active_lasso is None


def test_edit_mode_single_click_with_target_does_not_commit_stroke():
    svc = _service_with_region()
    svc.set_edit_mode(True)
    svc.select_region(1)
    before_mask = svc.state.region_masks[1].copy()
    before_history = len(svc.history)

    c = _canvas(svc)
    pos = _widget_pos_for_image_pixel(c, (15.0, 15.0), (50, 50))
    c._on_input(PointerDown(pos=pos, is_double=False))
    c._on_input(PointerUp(pos=pos))

    # One-sample stroke → edit_region_stroke returns None; history unchanged.
    assert len(svc.history) == before_history
    assert np.array_equal(svc.state.region_masks[1], before_mask)
    assert svc.state.active_lasso is None


# ---- non-edit-mode still works --------------------------------------------


def test_non_edit_mode_tap_on_region_still_selects():
    svc = _service_with_region()
    assert svc.state.edit_mode is False
    c = _canvas(svc)

    pos = _widget_pos_for_image_pixel(c, (15.0, 15.0), (50, 50))
    c._on_input(PointerDown(pos=pos, is_double=False))

    assert svc.state.selected_region_id == 1
    assert svc.state.active_lasso is None


def test_non_edit_mode_tap_on_background_starts_new_lasso():
    svc = _service_with_region()
    c = _canvas(svc)

    pos = _widget_pos_for_image_pixel(c, (40.0, 40.0), (50, 50))
    c._on_input(PointerDown(pos=pos, is_double=False))

    assert svc.state.active_lasso is not None
