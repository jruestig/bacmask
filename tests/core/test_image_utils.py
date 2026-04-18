import pytest

from bacmask.utils import image_utils as iu

# ---- fit_to_widget ----------------------------------------------------------


def test_fit_identical_aspect_exact_fit():
    s, ox, oy, dw, dh = iu.fit_to_widget((100, 100), (200, 200))
    assert s == 2.0
    assert (ox, oy) == (0.0, 0.0)
    assert (dw, dh) == (200.0, 200.0)


def test_fit_letterbox_horizontal():
    # Widget wider than image aspect → horizontal bars
    s, ox, oy, dw, dh = iu.fit_to_widget((100, 100), (200, 100))
    assert s == 1.0
    assert ox == 50.0
    assert oy == 0.0
    assert (dw, dh) == (100.0, 100.0)


def test_fit_letterbox_vertical():
    s, ox, oy, dw, dh = iu.fit_to_widget((100, 100), (100, 200))
    assert s == 1.0
    assert ox == 0.0
    assert oy == 50.0


def test_fit_zero_image_returns_identity():
    s, ox, oy, dw, dh = iu.fit_to_widget((0, 0), (100, 100))
    assert s == 1.0
    assert (ox, oy, dw, dh) == (0.0, 0.0, 0.0, 0.0)


# ---- coord transforms -------------------------------------------------------


def test_display_to_image_round_trip_centered():
    img_size = (800, 600)
    widget_size = (1000, 800)
    orig = (400.5, 300.25)
    d = iu.image_to_display(orig, img_size, widget_size)
    back = iu.display_to_image(d, img_size, widget_size)
    assert back[0] == pytest.approx(orig[0])
    assert back[1] == pytest.approx(orig[1])


def test_display_to_image_corner():
    # Image origin (0, 0) → widget offset
    s, ox, oy, _, _ = iu.fit_to_widget((100, 100), (200, 100))
    assert iu.image_to_display((0, 0), (100, 100), (200, 100)) == (ox, oy)
    assert iu.display_to_image((ox, oy), (100, 100), (200, 100)) == (0.0, 0.0)


# ---- view transform ---------------------------------------------------------


def test_view_transform_identity_matches_base():
    img_size = (800, 600)
    widget_size = (1000, 800)
    p = (123.0, 456.0)
    assert iu.image_to_display_view(p, img_size, widget_size, 1.0, (0.0, 0.0)) == (
        iu.image_to_display(p, img_size, widget_size)
    )
    assert iu.display_to_image_view(p, img_size, widget_size, 1.0, (0.0, 0.0)) == (
        iu.display_to_image(p, img_size, widget_size)
    )


def test_view_transform_round_trip_non_identity():
    img_size = (800, 600)
    widget_size = (1000, 800)
    view_scale = 2.35
    view_offset = (-40.0, 73.5)
    orig = (400.5, 300.25)
    d = iu.image_to_display_view(orig, img_size, widget_size, view_scale, view_offset)
    back = iu.display_to_image_view(d, img_size, widget_size, view_scale, view_offset)
    assert back[0] == pytest.approx(orig[0])
    assert back[1] == pytest.approx(orig[1])


def test_view_transform_scale_only():
    img_size = (100, 100)
    widget_size = (200, 200)  # fit scale = 2.0
    # image (0,0) → display (0,0) regardless of view_scale when offset = (0,0)
    assert iu.image_to_display_view((0, 0), img_size, widget_size, 3.0, (0.0, 0.0)) == (0.0, 0.0)
    # image (50, 50) → display (50 * 2 * 3, 50 * 2 * 3) = (300, 300)
    got = iu.image_to_display_view((50, 50), img_size, widget_size, 3.0, (0.0, 0.0))
    assert got == pytest.approx((300.0, 300.0))


def test_view_transform_zero_total_scale_returns_origin():
    img_size = (100, 100)
    widget_size = (200, 200)
    assert iu.display_to_image_view((5, 5), img_size, widget_size, 0.0, (0.0, 0.0)) == (0.0, 0.0)


# ---- region_color -----------------------------------------------------------


def test_region_color_deterministic():
    assert iu.region_color(1) == iu.region_color(1)
    assert iu.region_color(7) == iu.region_color(7)


def test_region_color_distinct_for_adjacent_ids():
    assert iu.region_color(1) != iu.region_color(2)
    assert iu.region_color(2) != iu.region_color(3)


def test_region_color_background_is_black():
    assert iu.region_color(0) == (0, 0, 0)


def test_region_color_negative_is_black():
    assert iu.region_color(-1) == (0, 0, 0)


def test_region_color_returns_rgb_in_range():
    r, g, b = iu.region_color(42)
    assert 0 <= r <= 255
    assert 0 <= g <= 255
    assert 0 <= b <= 255
