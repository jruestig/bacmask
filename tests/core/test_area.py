import numpy as np
import pytest

from bacmask.core import area


def test_count_pixels_filled_square_100x100():
    m = np.zeros((200, 200), dtype=np.uint16)
    m[50:150, 50:150] = 1
    assert area.count_pixels_per_region(m) == {1: 10_000}


def test_count_pixels_two_disjoint_regions():
    m = np.zeros((200, 200), dtype=np.uint16)
    m[10:20, 10:20] = 1
    m[100:150, 100:150] = 2
    assert area.count_pixels_per_region(m) == {1: 100, 2: 2_500}


def test_count_pixels_ignores_background():
    m = np.zeros((10, 10), dtype=np.uint16)
    assert area.count_pixels_per_region(m) == {}


def test_count_pixels_rejects_wrong_dtype():
    m = np.zeros((10, 10), dtype=np.uint8)
    with pytest.raises(TypeError):
        area.count_pixels_per_region(m)


def test_px_to_mm2_known_conversion():
    # 10 000 px at 0.01 mm/px → 1.0 mm²
    assert area.px_to_mm2(10_000, 0.01) == pytest.approx(1.0, abs=1e-9)


def test_px_to_mm2_uncalibrated_returns_none():
    assert area.px_to_mm2(1234, None) is None
