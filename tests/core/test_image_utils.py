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
