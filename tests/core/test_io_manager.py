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


def _sample_regions() -> dict[int, dict]:
    return {
        1: {
            "name": "region_01",
            "vertices": [[5, 5], [10, 5], [10, 10], [5, 10]],
        },
        2: {
            "name": "region_02",
            "vertices": [[15, 12], [25, 12], [25, 18], [15, 18]],
        },
    }


# --- image load ---------------------------------------------------------------


def test_load_image_returns_numpy_array(tmp_path):
    p = _write_synthetic_image(tmp_path)
    img = iom.load_image(p)
    assert isinstance(img, np.ndarray)
    assert img.shape == (20, 30)


def test_load_image_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        iom.load_image(tmp_path / "nope.png")


# --- CSV ----------------------------------------------------------------------


def test_csv_schema_header_locked(tmp_path):
    p = tmp_path / "a.csv"
    iom.save_areas_csv(p, [])
    lines = p.read_text().splitlines()
    assert lines[0] == ("filename,region_id,region_name,area_px,area_mm2,scale_factor")


def test_csv_rows_written_in_order(tmp_path):
    # area_px is now a float (shoelace of the polygon, knowledge/030).
    rows = [
        iom.AreaRow("a.tif", 1, "region_01", 100.0, 1.0, 0.1),
        iom.AreaRow("a.tif", 2, "region_02", 250.0, None, None),
    ]
    p = tmp_path / "a_areas.csv"
    iom.save_areas_csv(p, rows)
    lines = p.read_text().splitlines()
    assert lines[1] == "a.tif,1,region_01,100.0,1.0,0.1"
    assert lines[2] == "a.tif,2,region_02,250.0,,"  # uncalibrated -> empties


def test_csv_overwrites_on_resave(tmp_path):
    p = tmp_path / "a.csv"
    iom.save_areas_csv(p, [iom.AreaRow("x.png", 1, "region_01", 5.0, None, None)])
    iom.save_areas_csv(p, [iom.AreaRow("x.png", 1, "region_01", 7.0, None, None)])
    lines = p.read_text().splitlines()
    assert len(lines) == 2  # header + 1 row (no append)
    assert lines[1].split(",")[3] == "7.0"


# --- Bundle v2 round-trip -----------------------------------------------------


def test_bundle_v2_round_trip(tmp_path):
    img_path = _write_synthetic_image(tmp_path)
    regions = _sample_regions()
    meta = iom.BundleMeta(
        source_filename=img_path.name,
        image_shape=(20, 30),
        scale_mm_per_px=0.0125,
        next_label_id=3,
        regions=regions,
    )
    bundle_path = tmp_path / "x.bacmask"
    iom.save_bundle(bundle_path, img_path, (20, 30), meta)

    loaded = iom.load_bundle(bundle_path)
    assert loaded.image.shape == (20, 30)
    assert loaded.image_ext == ".png"
    assert loaded.meta.source_filename == img_path.name
    assert loaded.meta.image_shape == (20, 30)
    assert loaded.meta.scale_mm_per_px == 0.0125
    assert loaded.meta.next_label_id == 3
    assert loaded.meta.regions[1]["name"] == "region_01"
    assert loaded.meta.regions[1]["vertices"] == [
        [5, 5],
        [10, 5],
        [10, 10],
        [5, 10],
    ]


def test_bundle_v2_does_not_write_mask_png(tmp_path):
    img_path = _write_synthetic_image(tmp_path)
    meta = iom.BundleMeta(img_path.name, (20, 30), None, 1, {})
    p = tmp_path / "x.bacmask"
    iom.save_bundle(p, img_path, (20, 30), meta)
    with zipfile.ZipFile(p, "r") as zf:
        names = set(zf.namelist())
    assert "mask.png" not in names
    assert names == {"image.png", "meta.json"}


def test_bundle_v2_meta_contains_version_and_image_shape(tmp_path):
    img_path = _write_synthetic_image(tmp_path)
    meta = iom.BundleMeta(img_path.name, (20, 30), None, 1, {})
    p = tmp_path / "x.bacmask"
    iom.save_bundle(p, img_path, (20, 30), meta)
    with zipfile.ZipFile(p, "r") as zf:
        meta_json = json.loads(zf.read("meta.json"))
    assert meta_json["bacmask_version"] == 2
    assert meta_json["image_shape"] == [20, 30]


def test_bundle_uncalibrated_preserves_null_scale(tmp_path):
    img_path = _write_synthetic_image(tmp_path)
    meta = iom.BundleMeta(img_path.name, (20, 30), None, 1, {})
    p = tmp_path / "u.bacmask"
    iom.save_bundle(p, img_path, (20, 30), meta)
    loaded = iom.load_bundle(p)
    assert loaded.meta.scale_mm_per_px is None


def test_bundle_preserves_source_bytes_exactly(tmp_path):
    img_path = _write_synthetic_image(tmp_path)
    original_bytes = img_path.read_bytes()
    meta = iom.BundleMeta(img_path.name, (20, 30), None, 1, {})
    p = tmp_path / "b.bacmask"
    iom.save_bundle(p, img_path, (20, 30), meta)
    with zipfile.ZipFile(p, "r") as zf:
        assert zf.read("image.png") == original_bytes


def test_bundle_meta_json_is_deterministic(tmp_path):
    """Keys sorted, indent=2. Save twice with identical meta (same created_at,
    different updated_at) and verify structural keys are stable & sorted."""
    img_path = _write_synthetic_image(tmp_path)
    meta = iom.BundleMeta(
        source_filename=img_path.name,
        image_shape=(20, 30),
        scale_mm_per_px=None,
        next_label_id=1,
        regions={},
        created_at="2026-04-18T00:00:00Z",
    )
    p = tmp_path / "d.bacmask"
    iom.save_bundle(p, img_path, (20, 30), meta)
    with zipfile.ZipFile(p, "r") as zf:
        text = zf.read("meta.json").decode()
    # sort_keys=True: the top-level keys appear in alphabetical order.
    parsed_keys = list(json.loads(text).keys())
    assert parsed_keys == sorted(parsed_keys)


def test_bundle_unknown_version_raises(tmp_path):
    p = tmp_path / "bad.bacmask"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("image.png", b"dummy")
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
                    "image_shape": [20, 30],
                    "next_label_id": 1,
                    "regions": {},
                    "scale_mm_per_px": None,
                }
            ),
        )
    with pytest.raises(ValueError):
        iom.load_bundle(p)


# --- v1 back-compat -----------------------------------------------------------


def _build_v1_bundle(
    tmp_path: Path,
    *,
    img_bytes: bytes,
    regions: dict[int, dict],
    scale: float | None = 0.01,
    next_label_id: int = 3,
    include_mask_png: bool = True,
) -> Path:
    """Hand-craft a v1 bundle directly via zipfile for back-compat tests."""
    p = tmp_path / "v1.bacmask"
    v1_meta = {
        "bacmask_version": 1,
        "source_filename": "legacy.png",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "scale_mm_per_px": scale,
        "next_label_id": next_label_id,
        "regions": {str(k): v for k, v in regions.items()},
    }
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("image.png", img_bytes)
        if include_mask_png:
            # A dummy (but valid) 16-bit PNG — its contents are intentionally
            # bogus; loader should ignore it entirely.
            dummy_labels = np.zeros((20, 30), dtype=np.uint16)
            dummy_labels[0, 0] = 42  # wrong — shouldn't ever surface to caller
            ok, buf = cv2.imencode(".png", dummy_labels)
            assert ok
            zf.writestr("mask.png", buf.tobytes())
        zf.writestr("meta.json", json.dumps(v1_meta, indent=2, sort_keys=True))
    return p


def test_load_v1_bundle_ignores_mask_png_and_derives_image_shape(tmp_path):
    img_path = _write_synthetic_image(tmp_path)
    img_bytes = img_path.read_bytes()
    regions = _sample_regions()
    p = _build_v1_bundle(tmp_path, img_bytes=img_bytes, regions=regions)

    loaded = iom.load_bundle(p)
    assert loaded.image.shape == (20, 30)
    # image_shape not in v1 meta -> derived from decoded image.
    assert loaded.meta.image_shape == (20, 30)
    assert loaded.meta.source_filename == "legacy.png"
    assert loaded.meta.next_label_id == 3
    assert loaded.meta.scale_mm_per_px == 0.01
    assert loaded.meta.regions[1]["vertices"] == regions[1]["vertices"]
    assert loaded.meta.regions[2]["vertices"] == regions[2]["vertices"]


def test_load_v1_bundle_without_mask_png_still_loads(tmp_path):
    """v1 without mask.png is tolerable too — we ignore mask.png regardless."""
    img_path = _write_synthetic_image(tmp_path)
    p = _build_v1_bundle(
        tmp_path,
        img_bytes=img_path.read_bytes(),
        regions=_sample_regions(),
        include_mask_png=False,
    )
    loaded = iom.load_bundle(p)
    assert 1 in loaded.meta.regions
    assert 2 in loaded.meta.regions


def test_resaving_v1_bundle_promotes_to_v2(tmp_path):
    img_path = _write_synthetic_image(tmp_path)
    v1_path = _build_v1_bundle(
        tmp_path,
        img_bytes=img_path.read_bytes(),
        regions=_sample_regions(),
    )

    loaded = iom.load_bundle(v1_path)
    # Write it back out using the normal v2 writer.
    v2_path = tmp_path / "promoted.bacmask"
    iom.save_bundle_from_bytes(
        v2_path,
        image_bytes=img_path.read_bytes(),
        image_ext=".png",
        image_shape=loaded.meta.image_shape,
        meta=loaded.meta,
    )

    with zipfile.ZipFile(v2_path, "r") as zf:
        names = set(zf.namelist())
        meta_json = json.loads(zf.read("meta.json"))
    assert "mask.png" not in names
    assert names == {"image.png", "meta.json"}
    assert meta_json["bacmask_version"] == 2
    assert meta_json["image_shape"] == [20, 30]
