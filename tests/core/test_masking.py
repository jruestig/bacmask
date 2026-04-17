import numpy as np
import pytest

from bacmask.core import masking


def test_rasterize_axis_aligned_rectangle_fills_interior():
    m = np.zeros((30, 30), dtype=np.uint16)
    # Rectangle (5,5)-(15,15). Pixel centers (x+0.5, y+0.5) fall inside for x,y in 5..14.
    verts = np.array([[5, 5], [15, 5], [15, 15], [5, 15]], dtype=np.int32)
    masking.rasterize_polygon(m, verts, label_id=7)

    # Center of rectangle must be filled; far corners empty.
    assert m[10, 10] == 7
    assert m[2, 2] == 0
    assert m[20, 20] == 0


def test_rasterize_axis_aligned_rectangle_pixel_count():
    """Pins cv2.fillPoly's rasterization convention: endpoints are inclusive on both axes.
    A rectangle from (5,5) to (15,15) fills an 11×11 block (121 px), not 10×10.
    """
    m = np.zeros((30, 30), dtype=np.uint16)
    verts = np.array([[5, 5], [15, 5], [15, 15], [5, 15]], dtype=np.int32)
    masking.rasterize_polygon(m, verts, label_id=7)
    assert (m == 7).sum() == 121


def test_rasterize_rejects_wrong_dtype():
    m = np.zeros((10, 10), dtype=np.uint8)
    verts = np.array([[0, 0], [5, 0], [5, 5]], dtype=np.int32)
    with pytest.raises(TypeError):
        masking.rasterize_polygon(m, verts, label_id=1)


def test_rasterize_rejects_zero_label_id():
    m = np.zeros((10, 10), dtype=np.uint16)
    verts = np.array([[0, 0], [5, 0], [5, 5]], dtype=np.int32)
    with pytest.raises(ValueError):
        masking.rasterize_polygon(m, verts, label_id=0)


def test_erase_region_clears_only_matching_label():
    m = np.zeros((20, 20), dtype=np.uint16)
    m[5:10, 5:10] = 4
    m[15:18, 15:18] = 5
    masking.erase_region(m, label_id=4)
    assert (m == 4).sum() == 0
    assert (m == 5).sum() == 9
