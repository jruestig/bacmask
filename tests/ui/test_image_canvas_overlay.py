"""Overlay compositor regression snapshot.

Drives ``ImageCanvas._update_overlay`` with two overlapping polygon regions
and pins the SHA-1 of the resulting RGBA buffer. This is the guardrail for
knowledge/030's "rebuild overlay from polygons" refactor: same polygons +
same paint order must land the same bytes on the texture regardless of how
the compositor discovers what to paint.
"""

from __future__ import annotations

import hashlib
import os

os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")
os.environ.setdefault("KIVY_WINDOW", "mock")
os.environ.setdefault("KIVY_GL_BACKEND", "mock")

import numpy as np  # noqa: E402

from bacmask.core import masking  # noqa: E402
from bacmask.services.mask_service import MaskService  # noqa: E402
from bacmask.ui.widgets.image_canvas import ImageCanvas  # noqa: E402

# Pinned hash captured on the pre-rewrite (mask-diff) compositor with the
# fixture below. See the module docstring.
OVERLAY_SNAPSHOT_SHA1 = "2292d1929f3d56b2508e9c71c2a53961c0e1c90d"


def _canvas_for(svc: MaskService) -> ImageCanvas:
    """Build an ImageCanvas without touching Kivy's Window/EventLoop."""
    c: ImageCanvas = ImageCanvas.__new__(ImageCanvas)
    c.service = svc
    c._image_texture = None
    c._overlay_texture = None
    c._last_image = svc.state.image
    c._last_regions_version = -1
    c._overlay_acc_rgb = None
    c._overlay_acc_a = None
    c._overlay_rgba_buf = None
    c._last_pointer_pos = None
    c._view_scale = 1.0
    c._view_offset = (0.0, 0.0)
    c.x = 0.0
    c.y = 0.0
    c.width = 400.0
    c.height = 400.0
    c._repaint = lambda: None  # type: ignore[method-assign]
    # Skip the GPU upload — the mock GL backend segfaults on Texture.create
    # here. The RGBA buffer the compositor fills is what we hash.
    c._blit_overlay_texture = lambda *_a, **_kw: None  # type: ignore[method-assign]
    # Pre-rewrite diff machinery attribute — harmless once gone.
    c._overlay_tracked = {}
    return c


def _service_with_two_overlapping_regions() -> MaskService:
    """200x200 gray image with two overlapping square regions.

    - id=1 square at (50, 50)..(100, 100)
    - id=2 square at (80, 80)..(130, 130)

    Overlap window is (80, 80)..(100, 100). Higher id wins visually there.
    """
    svc = MaskService()
    img = np.full((200, 200, 3), 128, dtype=np.uint8)
    svc.state.image = img
    svc.state.image_filename = "snapshot.png"
    svc.state.label_map = np.zeros((200, 200), dtype=np.uint16)

    verts1 = np.array([[50, 50], [100, 50], [100, 100], [50, 100]], dtype=np.int32)
    verts2 = np.array([[80, 80], [130, 80], [130, 130], [80, 130]], dtype=np.int32)

    mask1 = masking.rasterize_polygon_mask(verts1, (200, 200))
    mask2 = masking.rasterize_polygon_mask(verts2, (200, 200))

    svc.state.regions[1] = {"name": "region_01", "vertices": verts1.tolist()}
    svc.state.regions[2] = {"name": "region_02", "vertices": verts2.tolist()}
    svc.state.region_masks[1] = mask1
    svc.state.region_masks[2] = mask2
    svc.state.region_areas[1] = int(mask1.sum())
    svc.state.region_areas[2] = int(mask2.sum())
    svc.state.next_label_id = 3
    svc.state.regions_version = 1
    masking.repaint_label_map(svc.state.label_map, svc.state.region_masks)
    return svc


def test_overlay_rgba_buffer_hash_is_stable():
    svc = _service_with_two_overlapping_regions()
    c = _canvas_for(svc)

    # Drive the same code path the state subscriber does.
    c._update_overlay()

    rgba = c._overlay_rgba_buf
    assert rgba is not None, "compositor must allocate and fill the RGBA buffer"
    assert rgba.shape == (200, 200, 4)
    assert rgba.dtype == np.uint8

    digest = hashlib.sha1(rgba.tobytes()).hexdigest()
    assert digest == OVERLAY_SNAPSHOT_SHA1, (
        f"overlay RGBA snapshot drifted: expected {OVERLAY_SNAPSHOT_SHA1}, got {digest}. "
        "If the palette, alpha, or paint order changed intentionally, recompute the "
        "pinned hash and update this test."
    )


def test_overlay_respects_newest_on_top():
    """Sanity check complementing the hash: the id=2 color must land on the
    overlap pixels (highest id wins per knowledge/025).
    """
    svc = _service_with_two_overlapping_regions()
    c = _canvas_for(svc)
    c._update_overlay()

    from bacmask.utils import image_utils

    color2 = image_utils.region_color(2)
    rgba = c._overlay_rgba_buf
    assert rgba is not None

    # Pick a pixel inside the overlap window: (90, 90).
    px_r, px_g, px_b, px_a = rgba[90, 90].tolist()
    assert px_a > 0, "overlap pixel must be painted"
    # The blended RGB should be closer to region 2's color than region 1's.
    color1 = image_utils.region_color(1)
    d1 = (px_r - color1[0]) ** 2 + (px_g - color1[1]) ** 2 + (px_b - color1[2]) ** 2
    d2 = (px_r - color2[0]) ** 2 + (px_g - color2[1]) ** 2 + (px_b - color2[2]) ** 2
    assert d2 < d1, "overlap pixel must match the highest-id region's color"
