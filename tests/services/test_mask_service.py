from pathlib import Path

import cv2
import numpy as np
import pytest

from bacmask.core import io_manager
from bacmask.services.mask_service import MaskService


def _write_image(tmp_path: Path, name: str = "img.png") -> Path:
    arr = np.random.default_rng(0).integers(0, 255, (50, 50), dtype=np.uint8)
    p = tmp_path / name
    cv2.imwrite(str(p), arr)
    return p


def _square(x0: int = 10, y0: int = 10, size: int = 10) -> list[tuple[int, int]]:
    return [
        (x0, y0),
        (x0 + size, y0),
        (x0 + size, y0 + size),
        (x0, y0 + size),
    ]


def _draw_lasso(svc: MaskService, verts: list[tuple[int, int]]) -> int | None:
    svc.begin_lasso(verts[0])
    for v in verts[1:]:
        svc.add_lasso_point(v)
    return svc.close_lasso()


# ---- load ----


def test_load_image_populates_state(tmp_path):
    svc = MaskService()
    p = _write_image(tmp_path)
    svc.load_image(p)
    assert svc.state.image is not None
    assert svc.state.image_path == p
    assert svc.state.image_filename == "img.png"
    assert svc.state.image_bytes == p.read_bytes()
    assert svc.state.image_ext == ".png"
    assert svc.state.label_map.shape == (50, 50)
    assert svc.state.label_map.dtype == np.uint16
    assert svc.state.next_label_id == 1
    assert svc.state.regions == {}
    assert svc.state.dirty is False


# ---- lasso ----


def test_lasso_close_creates_region(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    assert _draw_lasso(svc, _square()) == 1
    assert 1 in svc.state.regions
    assert (svc.state.label_map == 1).any()
    assert svc.state.dirty is True
    assert len(svc.history) == 1


def test_close_lasso_with_too_few_points_discards(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    svc.begin_lasso((10, 10))
    svc.add_lasso_point((15, 15))
    assert svc.close_lasso() is None
    assert svc.state.regions == {}
    assert len(svc.history) == 0


def test_cancel_lasso_clears_buffer(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    svc.begin_lasso((10, 10))
    svc.add_lasso_point((15, 15))
    svc.add_lasso_point((20, 10))
    svc.cancel_lasso()
    assert svc.state.active_lasso is None
    assert svc.state.regions == {}
    assert len(svc.history) == 0


# ---- delete ----


def test_delete_region_removes_it(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.delete_region(1)
    assert 1 not in svc.state.regions
    assert (svc.state.label_map == 1).sum() == 0
    assert len(svc.history) == 2


def test_delete_missing_region_raises(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    with pytest.raises(KeyError):
        svc.delete_region(42)


# ---- undo / redo ----


def test_undo_redo_round_trips(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    snapshot = svc.state.label_map.copy()

    assert svc.undo() is True
    assert svc.state.regions == {}
    assert (svc.state.label_map == 0).all()

    assert svc.redo() is True
    assert 1 in svc.state.regions
    assert np.array_equal(svc.state.label_map, snapshot)


# ---- calibration ----


def test_set_calibration_updates_and_dirties(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    assert svc.state.dirty is False
    svc.set_calibration(0.01)
    assert svc.state.scale_mm_per_px == 0.01
    assert svc.state.dirty is True


def test_set_calibration_rejects_invalid(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    with pytest.raises(ValueError):
        svc.set_calibration(-1.0)
    assert svc.state.scale_mm_per_px is None


def test_set_calibration_accepts_none_uncalibrated(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    svc.set_calibration(0.01)
    svc.set_calibration(None)
    assert svc.state.scale_mm_per_px is None


# ---- derived: compute_area_rows ----


def test_area_rows_uncalibrated(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())  # 11x11 = 121 px
    rows = svc.compute_area_rows()
    assert len(rows) == 1
    r = rows[0]
    assert r.region_id == 1
    assert r.region_name == "region_01"
    assert r.area_px == 121
    assert r.area_mm2 is None
    assert r.scale_factor is None


def test_area_rows_calibrated(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())  # 121 px
    svc.set_calibration(0.01)
    r = svc.compute_area_rows()[0]
    assert r.area_mm2 == pytest.approx(121 * 0.0001, abs=1e-12)
    assert r.scale_factor == 0.01


# ---- save / load round-trip ----


def test_save_all_writes_bundle_and_csv(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.set_calibration(0.01)

    bundle_p = tmp_path / "out.bacmask"
    csv_p = tmp_path / "out.csv"
    svc.save_all(bundle_p, csv_p)

    assert bundle_p.exists()
    assert csv_p.exists()
    assert svc.state.dirty is False

    loaded = io_manager.load_bundle(bundle_p)
    assert np.array_equal(loaded.label_map, svc.state.label_map)
    assert loaded.meta.scale_mm_per_px == 0.01


def test_load_bundle_restores_state(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.set_calibration(0.02)

    bundle_p = tmp_path / "round.bacmask"
    csv_p = tmp_path / "round.csv"
    svc.save_all(bundle_p, csv_p)

    svc2 = MaskService()
    svc2.load_bundle(bundle_p)
    assert np.array_equal(svc2.state.label_map, svc.state.label_map)
    assert svc2.state.scale_mm_per_px == 0.02
    assert 1 in svc2.state.regions
    assert svc2.state.next_label_id == 2
    assert svc2.state.dirty is False


def test_id_stability_survives_save_load(tmp_path):
    """Deleted IDs stay reserved across a save/load round-trip."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))

    _draw_lasso(svc, _square(10, 10, 8))
    _draw_lasso(svc, _square(25, 25, 8))
    assert svc.state.next_label_id == 3
    svc.delete_region(1)
    assert svc.state.next_label_id == 3  # not decremented

    bundle_p = tmp_path / "s.bacmask"
    csv_p = tmp_path / "s.csv"
    svc.save_all(bundle_p, csv_p)

    svc2 = MaskService()
    svc2.load_bundle(bundle_p)
    assert svc2.state.next_label_id == 3
    lid = _draw_lasso(svc2, _square(40, 10, 5))
    assert lid == 3  # new region gets 3, not reusing 1


# ---- save guard ----


def test_save_all_without_image_raises(tmp_path):
    svc = MaskService()
    with pytest.raises(ValueError):
        svc.save_all(tmp_path / "x.bacmask", tmp_path / "x.csv")


# ---- selection ----


def test_select_region_sets_state(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.select_region(1)
    assert svc.state.selected_region_id == 1


def test_select_missing_region_raises(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    with pytest.raises(KeyError):
        svc.select_region(42)


def test_clear_selection(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.select_region(1)
    svc.clear_selection()
    assert svc.state.selected_region_id is None


def test_deleting_selected_region_clears_selection(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.select_region(1)
    svc.delete_region(1)
    assert svc.state.selected_region_id is None


def test_load_image_clears_selection(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.select_region(1)
    svc.load_image(_write_image(tmp_path, "img2.png"))
    assert svc.state.selected_region_id is None


# ---- vertex edit via service ----


def test_edit_vertices_moves_region(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))  # region 1 at (10,10)-(20,20)

    new_verts = [(20, 10), (30, 10), (30, 20), (20, 20)]
    svc.edit_vertices(1, new_verts)

    assert svc.state.regions[1]["vertices"] == [
        [20, 10],
        [30, 10],
        [30, 20],
        [20, 20],
    ]
    assert svc.state.label_map[10, 10] == 0  # old position cleared
    assert (svc.state.label_map == 1).any()
    assert svc.state.dirty is True


def test_edit_vertices_undo_via_history(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))
    before_map = svc.state.label_map.copy()
    before_verts = list(svc.state.regions[1]["vertices"])

    svc.edit_vertices(1, [(20, 10), (30, 10), (30, 20), (20, 20)])
    assert svc.undo() is True

    assert np.array_equal(svc.state.label_map, before_map)
    assert svc.state.regions[1]["vertices"] == before_verts


def test_edit_vertices_clip_leaves_neighbor_intact(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, [(5, 5), (15, 5), (15, 15), (5, 15)])  # region 1
    _draw_lasso(svc, [(20, 5), (30, 5), (30, 15), (20, 15)])  # region 2
    r2_pixels = (svc.state.label_map == 2).sum()

    # Extend region 1 into region 2's range.
    svc.edit_vertices(1, [(5, 5), (25, 5), (25, 15), (5, 15)])

    assert (svc.state.label_map == 2).sum() == r2_pixels
    assert svc.state.label_map[10, 22] == 2  # region 2 untouched


# ---- observers ----


def test_subscribe_fires_on_state_change(tmp_path):
    svc = MaskService()
    calls: list[str] = []
    svc.subscribe(lambda: calls.append("x"))
    svc.load_image(_write_image(tmp_path))
    assert len(calls) >= 1
