import math

import pytest

from bacmask.core import calibration


def test_accepts_positive_float():
    assert calibration.validate_scale(0.01) == 0.01


def test_accepts_none_uncalibrated():
    assert calibration.validate_scale(None) is None


def test_rejects_zero():
    with pytest.raises(ValueError):
        calibration.validate_scale(0.0)


def test_rejects_negative():
    with pytest.raises(ValueError):
        calibration.validate_scale(-0.5)


def test_rejects_nan():
    with pytest.raises(ValueError):
        calibration.validate_scale(math.nan)


def test_rejects_inf():
    with pytest.raises(ValueError):
        calibration.validate_scale(math.inf)


def test_rejects_bool():
    with pytest.raises(TypeError):
        calibration.validate_scale(True)
