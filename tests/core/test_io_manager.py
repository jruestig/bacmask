import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from bacmask.core import io_manager as iom


def _write_synthetic_image(tmp_path: Path, name: str = "img.png") -> Path:
    arr = np.random.default_rng(0).integers(0, 255, (20, 30), dtype=np.uint8)
    p = tmp_path / name
    cv2.imwrite(str(p), arr)
    return p


def _sample_label_map() -> np.ndarray:
    m = np.zeros((20, 30), dtype=np.uint16)
    m[5:10, 5:10] = 1
    m[12:18, 15:25] = 2
    return m


# --- image load ---------------------------------------------------------------


def test_load_image_returns_numpy_array(tmp_path):
    p = _write_synthetic_image(tmp_path)
    img = iom.load_image(p)
    assert isinstance(img, np.ndarray)
    assert img.shape == (20, 30)


def test_load_image_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        iom.load_image(tmp_path / "nope.png")


# --- mask PNG round-trip ------------------------------------------------------


def test_mask_png_round_trip_is_bit_identical(tmp_path):
    m = _sample_label_map()
    p = tmp_path / "mask.png"
    iom.save_mask_png(p, m)
    loaded = iom.load_mask_png(p)
    assert loaded.dtype == np.uint16
    assert np.array_equal(loaded, m)


def test_mask_png_preserves_16bit_values(tmp_path):
    """Large label IDs must survive without 8-bit downcast."""
    m = np.zeros((5, 5), dtype=np.uint16)
    m[1, 1] = 12_345  # > 255
    m[3, 3] = 65_000  # near uint16 max
    p = tmp_path / "m.png"
    iom.save_mask_png(p, m)
    loaded = iom.load_mask_png(p)
    assert loaded[1, 1] == 12_345
    assert loaded[3, 3] == 65_000


def test_save_mask_rejects_non_uint16(tmp_path):
    with pytest.raises(TypeError):
        iom.save_mask_png(tmp_path / "m.png", np.zeros((5, 5), dtype=np.uint8))


def test_save_mask_rejects_non_2d(tmp_path):
    with pytest.raises(ValueError):
        iom.save_mask_png(tmp_path / "m.png", np.zeros((5, 5, 3), dtype=np.uint16))


def test_load_mask_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        iom.load_mask_png(tmp_path / "nope.png")


def test_load_mask_for_image_rejects_mismatch(tmp_path):
    m = _sample_label_map()
    p = tmp_path / "mask.png"
    iom.save_mask_png(p, m)
    with pytest.raises(iom.MaskDimensionMismatch) as exc_info:
        iom.load_mask_for_image(p, image_shape=(10, 10))
    assert exc_info.value.mask_shape == (20, 30)
    assert exc_info.value.image_shape == (10, 10)


def test_load_mask_for_image_accepts_match(tmp_path):
    m = _sample_label_map()
    p = tmp_path / "mask.png"
    iom.save_mask_png(p, m)
    loaded = iom.load_mask_for_image(p, image_shape=(20, 30))
    assert np.array_equal(loaded, m)


# --- CSV ----------------------------------------------------------------------


def test_csv_schema_header_locked(tmp_path):
    p = tmp_path / "a.csv"
    iom.save_areas_csv(p, [])
    lines = p.read_text().splitlines()
    assert lines[0] == ("filename,region_id,region_name,area_px,area_mm2,scale_factor")


def test_csv_rows_written_in_order(tmp_path):
    rows = [
        iom.AreaRow("a.tif", 1, "region_01", 100, 1.0, 0.1),
        iom.AreaRow("a.tif", 2, "region_02", 250, None, None),
    ]
    p = tmp_path / "a_areas.csv"
    iom.save_areas_csv(p, rows)
    lines = p.read_text().splitlines()
    assert lines[1] == "a.tif,1,region_01,100,1.0,0.1"
    assert lines[2] == "a.tif,2,region_02,250,,"  # uncalibrated -> empties


def test_csv_overwrites_on_resave(tmp_path):
    p = tmp_path / "a.csv"
    iom.save_areas_csv(p, [iom.AreaRow("x.png", 1, "region_01", 5, None, None)])
    iom.save_areas_csv(p, [iom.AreaRow("x.png", 1, "region_01", 7, None, None)])
    lines = p.read_text().splitlines()
    assert len(lines) == 2  # header + 1 row (no append)
    assert lines[1].split(",")[3] == "7"


# --- Bundle round-trip --------------------------------------------------------


def test_bundle_round_trip(tmp_path):
    img_path = _write_synthetic_image(tmp_path)
    m = _sample_label_map()
    meta = iom.BundleMeta(
        source_filename=img_path.name,
        scale_mm_per_px=0.0125,
        next_label_id=3,
        regions={
            1: {
                "name": "region_01",
                "vertices": [[5, 5], [10, 5], [10, 10], [5, 10]],
            },
            2: {
                "name": "region_02",
                "vertices": [[15, 12], [25, 12], [25, 18], [15, 18]],
            },
        },
    )
    bundle_path = tmp_path / "x.bacmask"
    iom.save_bundle(bundle_path, img_path, m, meta)

    loaded = iom.load_bundle(bundle_path)
    assert np.array_equal(loaded.label_map, m)
    assert loaded.label_map.dtype == np.uint16
    assert loaded.image.shape == (20, 30)
    assert loaded.image_ext == ".png"
    assert loaded.meta.source_filename == img_path.name
    assert loaded.meta.scale_mm_per_px == 0.0125
    assert loaded.meta.next_label_id == 3
    assert loaded.meta.regions[1]["name"] == "region_01"
    assert loaded.meta.regions[1]["vertices"] == [
        [5, 5],
        [10, 5],
        [10, 10],
        [5, 10],
    ]


def test_bundle_uncalibrated_preserves_null_scale(tmp_path):
    img_path = _write_synthetic_image(tmp_path)
    m = _sample_label_map()
    meta = iom.BundleMeta(img_path.name, None, 1, {})
    p = tmp_path / "u.bacmask"
    iom.save_bundle(p, img_path, m, meta)
    loaded = iom.load_bundle(p)
    assert loaded.meta.scale_mm_per_px is None


def test_bundle_preserves_source_bytes_exactly(tmp_path):
    img_path = _write_synthetic_image(tmp_path)
    original_bytes = img_path.read_bytes()
    m = _sample_label_map()
    meta = iom.BundleMeta(img_path.name, None, 1, {})
    p = tmp_path / "b.bacmask"
    iom.save_bundle(p, img_path, m, meta)
    with zipfile.ZipFile(p, "r") as zf:
        assert zf.read("image.png") == original_bytes


def test_bundle_unknown_version_raises(tmp_path):
    p = tmp_path / "bad.bacmask"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("image.png", b"dummy")
        zf.writestr("mask.png", b"dummy")
        zf.writestr(
            "meta.json",
            json.dumps(
                {
                    "bacmask_version": 99,
                    "source_filename": "x",
                    "next_label_id": 1,
                    "regions": {},
                    "scale_mm_per_px": None,
                }
            ),
        )
    with pytest.raises(iom.UnsupportedBundleVersion) as ei:
        iom.load_bundle(p)
    assert ei.value.version == 99


def test_bundle_missing_member_raises(tmp_path):
    p = tmp_path / "broken.bacmask"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr(
            "meta.json",
            json.dumps(
                {
                    "bacmask_version": iom.BACMASK_VERSION,
                    "source_filename": "x",
                    "next_label_id": 1,
                    "regions": {},
                    "scale_mm_per_px": None,
                }
            ),
        )
    with pytest.raises(ValueError):
        iom.load_bundle(p)
