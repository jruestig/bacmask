"""Canvas view-transform behavior: zoom/pan + cursor-centered zoom invariant."""

from __future__ import annotations

import os

# Kivy headless setup — must happen before importing kivy.
os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")
os.environ.setdefault("KIVY_WINDOW", "mock")
os.environ.setdefault("KIVY_GL_BACKEND", "mock")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from bacmask.services.mask_service import MaskService  # noqa: E402
from bacmask.ui.input.events import Pan, Zoom  # noqa: E402
from bacmask.ui.widgets.image_canvas import ImageCanvas  # noqa: E402
from bacmask.utils import image_utils  # noqa: E402


def _mock_service_with_image(img_w: int, img_h: int) -> MaskService:
    svc = MaskService()
    img = np.zeros((img_h, img_w, 3), dtype=np.uint8)
    svc.state.image = img
    svc.state.image_filename = "mock.png"
    svc.state.label_map = np.zeros((img_h, img_w), dtype=np.uint16)
    return svc


def _canvas(svc: MaskService, widget_w: float = 400.0, widget_h: float = 400.0) -> ImageCanvas:
    """Build an ImageCanvas without touching Kivy's Window/EventLoop.

    We exercise view-transform logic; the render path (``_repaint``) is not
    called by these tests, so we can skip ``Widget.__init__``.
    """
    c: ImageCanvas = ImageCanvas.__new__(ImageCanvas)
    c.service = svc
    c._image_texture = None
    c._overlay_texture = None
    c._last_image = svc.state.image
    c._view_scale = 1.0
    c._view_offset = (0.0, 0.0)
    # Stub the methods/attrs _apply_* and _widget_pos_to_image rely on.
    c.x = 0.0
    c.y = 0.0
    c.width = widget_w
    c.height = widget_h
    # No-op _repaint so _apply_* can call it safely.
    c._repaint = lambda: None  # type: ignore[method-assign]
    return c


def _image_under_cursor(
    canvas: ImageCanvas,
    cursor_window: tuple[float, float],
    image_size: tuple[int, int],
) -> tuple[float, float]:
    cx, cy = cursor_window
    lx = cx - canvas.x
    ly_top = canvas.height - (cy - canvas.y)
    return image_utils.display_to_image_view(
        (lx, ly_top),
        image_size,
        (canvas.width, canvas.height),
        canvas._view_scale,
        canvas._view_offset,
    )


# ---- zoom ------------------------------------------------------------------


def test_zoom_in_centered_on_cursor_keeps_image_pixel_under_cursor():
    svc = _mock_service_with_image(200, 100)
    canvas = _canvas(svc)
    cursor = (150.0, 150.0)
    before = _image_under_cursor(canvas, cursor, (200, 100))

    canvas._on_input(Zoom(center=cursor, delta=1.0))

    assert canvas._view_scale > 1.0
    after = _image_under_cursor(canvas, cursor, (200, 100))
    assert after[0] == pytest.approx(before[0])
    assert after[1] == pytest.approx(before[1])


def test_zoom_out_centered_on_cursor_keeps_image_pixel_under_cursor():
    svc = _mock_service_with_image(200, 100)
    canvas = _canvas(svc)
    # Zoom in first so we have room to zoom out.
    canvas._on_input(Zoom(center=(150.0, 150.0), delta=1.0))
    canvas._on_input(Zoom(center=(150.0, 150.0), delta=1.0))
    cursor = (180.0, 170.0)
    before = _image_under_cursor(canvas, cursor, (200, 100))

    canvas._on_input(Zoom(center=cursor, delta=-1.0))

    after = _image_under_cursor(canvas, cursor, (200, 100))
    assert after[0] == pytest.approx(before[0])
    assert after[1] == pytest.approx(before[1])


def test_zoom_clamped_to_min_and_max():
    svc = _mock_service_with_image(200, 100)
    canvas = _canvas(svc)
    for _ in range(200):
        canvas._on_input(Zoom(center=(200.0, 200.0), delta=1.0))
    assert canvas._view_scale <= 20.0 + 1e-9

    for _ in range(400):
        canvas._on_input(Zoom(center=(200.0, 200.0), delta=-1.0))
    assert canvas._view_scale >= 0.1 - 1e-9


# ---- pan -------------------------------------------------------------------


def test_pan_shifts_view_offset():
    svc = _mock_service_with_image(200, 100)
    canvas = _canvas(svc)
    before = canvas._view_offset
    canvas._on_input(Pan(delta=(12.0, 7.0)))
    # Widget Y-up delta → display top-down delta flips y.
    assert canvas._view_offset[0] == pytest.approx(before[0] + 12.0)
    assert canvas._view_offset[1] == pytest.approx(before[1] - 7.0)


def test_pan_clamped_so_image_cannot_escape():
    svc = _mock_service_with_image(200, 100)
    canvas = _canvas(svc)
    canvas._on_input(Pan(delta=(100000.0, 100000.0)))
    vox, voy = canvas._view_offset
    # Both components must be bounded — not arbitrarily large.
    assert abs(vox) < canvas.width + 10
    assert abs(voy) < canvas.height + 10


# ---- identity/round-trip ---------------------------------------------------


def test_identity_view_widget_to_image_matches_base():
    svc = _mock_service_with_image(200, 100)
    canvas = _canvas(svc)
    # Center of the widget at (200, 200). Image pixel should be (100, 50)
    # (image is letterboxed top/bottom with off_y=100; at widget Y-up 200,
    # display Y-top = 400 - 200 = 200, (200 - 100)/2 = 50).
    xy = canvas._widget_pos_to_image((200.0, 200.0), (100, 200))
    assert xy == (100, 50)


def test_round_trip_image_to_widget_under_non_identity_view():
    svc = _mock_service_with_image(200, 100)
    canvas = _canvas(svc)
    canvas._view_scale = 2.5
    canvas._view_offset = (17.0, -9.0)

    # Pick an image pixel, project to widget, project back.
    image_pt = (42, 33)
    flat = canvas._image_points_to_widget([image_pt], (200, 100))
    wx, wy = flat[0], flat[1]
    xy = canvas._widget_pos_to_image((wx, wy), (100, 200))
    assert xy == image_pt
