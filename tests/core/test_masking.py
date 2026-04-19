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


def test_polygon_area_unit_square_is_one():
    # A 1x1 axis-aligned square has enclosed area = 1 (shoelace formula).
    verts = np.array([[5, 5], [6, 5], [6, 6], [5, 6]], dtype=np.int32)
    assert masking.polygon_area(verts) == 1.0


def test_polygon_area_zero_for_collinear():
    verts = np.array([[5, 5], [10, 5], [15, 5]], dtype=np.int32)
    assert masking.polygon_area(verts) == 0.0


def test_polygon_area_zero_for_duplicate_points():
    verts = np.array([[5, 5], [5, 5], [5, 5]], dtype=np.int32)
    assert masking.polygon_area(verts) == 0.0


def test_polygon_area_zero_for_fewer_than_3_vertices():
    verts = np.array([[5, 5], [10, 10]], dtype=np.int32)
    assert masking.polygon_area(verts) == 0.0


# ---- find_boundary_crossings -----------------------------------------------


def _filled_square_mask(h: int = 30, w: int = 30) -> np.ndarray:
    """A solid-square target mask for crossing tests: (10..19, 10..19)."""
    m = np.zeros((h, w), dtype=bool)
    m[10:20, 10:20] = True
    return m


def test_find_boundary_crossings_no_crossing_returns_none():
    mask = _filled_square_mask()
    # All samples outside.
    pts = np.array([[0, 0], [1, 1], [2, 2]], dtype=np.int32)
    p, q = masking.find_boundary_crossings(pts, mask)
    assert p is None and q is None


def test_find_boundary_crossings_one_crossing_returns_p_only():
    mask = _filled_square_mask()
    # Outside -> outside -> inside: single crossing between idx 1 and 2.
    pts = np.array([[0, 0], [5, 15], [15, 15]], dtype=np.int32)
    p, q = masking.find_boundary_crossings(pts, mask)
    assert p == 1
    assert q is None


def test_find_boundary_crossings_two_crossings_returns_both():
    mask = _filled_square_mask()
    # Outside -> inside -> outside: crossings at idx 0 and idx 1.
    pts = np.array([[5, 15], [15, 15], [25, 15]], dtype=np.int32)
    p, q = masking.find_boundary_crossings(pts, mask)
    assert p == 0
    assert q == 1


def test_find_boundary_crossings_extra_crossings_ignored():
    mask = _filled_square_mask()
    # out -> in -> out -> in -> out. Should return P=0, Q=1 only.
    pts = np.array(
        [[5, 15], [15, 15], [25, 15], [15, 15], [5, 15]],
        dtype=np.int32,
    )
    p, q = masking.find_boundary_crossings(pts, mask)
    assert p == 0
    assert q == 1


def test_find_boundary_crossings_out_of_bounds_counts_as_outside():
    mask = _filled_square_mask()
    # OOB -> inside -> OOB: crossings at idx 0 and 1.
    pts = np.array([[-5, -5], [15, 15], [100, 100]], dtype=np.int32)
    p, q = masking.find_boundary_crossings(pts, mask)
    assert p == 0
    assert q == 1


# ---- largest_connected_component -------------------------------------------


def test_largest_cc_single_component_is_copy():
    m = np.zeros((10, 10), dtype=bool)
    m[2:5, 2:5] = True
    out = masking.largest_connected_component(m)
    assert np.array_equal(out, m)
    assert out is not m  # copy, not alias


def test_largest_cc_empty_mask_is_empty():
    m = np.zeros((10, 10), dtype=bool)
    out = masking.largest_connected_component(m)
    assert not out.any()


def test_largest_cc_picks_bigger_component():
    m = np.zeros((20, 20), dtype=bool)
    # Small component: 3x3 = 9 px.
    m[1:4, 1:4] = True
    # Big component: 5x5 = 25 px.
    m[10:15, 10:15] = True
    out = masking.largest_connected_component(m)
    # Only the big one survives.
    assert out[12, 12]
    assert not out[2, 2]
    assert out.sum() == 25


def test_largest_cc_tie_breaks_on_smallest_yx():
    m = np.zeros((10, 20), dtype=bool)
    # Two equal-size 2x2 components, well separated.
    # Component A at (1,1)-(2,2): first foreground pixel at (1,1).
    m[1:3, 1:3] = True
    # Component B at (5,10)-(6,11): first foreground pixel at (5,10).
    m[5:7, 10:12] = True
    out = masking.largest_connected_component(m)
    # A wins the tie (smaller (y, x)).
    assert out[1, 1]
    assert not out[5, 10]
    assert out.sum() == 4


# ---- contour_vertices ------------------------------------------------------


def test_contour_vertices_rectangle_round_trip():
    mask = np.zeros((20, 20), dtype=bool)
    mask[5:10, 5:10] = True  # 5x5 solid rect
    verts = masking.contour_vertices(mask)
    assert verts.dtype == np.int32
    # Contour should be a closed loop around the rectangle — bounded by the
    # rectangle's extents.
    assert verts[:, 0].min() == 5
    assert verts[:, 0].max() == 9
    assert verts[:, 1].min() == 5
    assert verts[:, 1].max() == 9
    # Rasterizing via cv2.fillPoly on these vertices reconstructs the square.
    rastered = masking.rasterize_polygon_mask(verts, mask.shape)
    assert np.array_equal(rastered, mask)


def test_contour_vertices_empty_mask_raises():
    mask = np.zeros((10, 10), dtype=bool)
    with pytest.raises(ValueError):
        masking.contour_vertices(mask)


# ---- rasterize_stroke_polygon ----------------------------------------------


def test_rasterize_stroke_polygon_closes_open_polyline():
    # An L-shaped open polyline; closing by last->first gives a triangle.
    samples = np.array([[5, 5], [15, 5], [15, 15]], dtype=np.int32)
    mask = masking.rasterize_stroke_polygon(samples, (20, 20))
    assert mask.dtype == bool
    # Filled triangle has some True pixels; origin corner is outside.
    assert mask.any()
    assert not mask[0, 0]


def test_rasterize_stroke_polygon_fewer_than_3_returns_empty():
    mask = masking.rasterize_stroke_polygon(
        np.array([[5, 5], [10, 10]], dtype=np.int32),
        (20, 20),
    )
    assert mask.shape == (20, 20)
    assert not mask.any()
