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


def test_save_bundle_and_export_csv(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.set_calibration(0.01)

    bundle_p = tmp_path / "out.bacmask"
    csv_p = tmp_path / "out.csv"
    svc.save_bundle(bundle_p)
    svc.export_csv(csv_p)

    assert bundle_p.exists()
    assert csv_p.exists()
    assert svc.state.dirty is False

    loaded = io_manager.load_bundle(bundle_p)
    assert loaded.meta.scale_mm_per_px == 0.01
    assert loaded.meta.image_shape == svc.state.label_map.shape
    assert 1 in loaded.meta.regions


def test_save_bundle_does_not_write_csv(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())

    bundle_p = tmp_path / "s.bacmask"
    svc.save_bundle(bundle_p)

    assert bundle_p.exists()
    # No CSV is written anywhere in tmp_path by save_bundle.
    assert list(tmp_path.glob("*.csv")) == []


def test_export_csv_does_not_clear_dirty(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    # After the lasso, the state has pending mutations.
    assert svc.state.dirty is True

    svc.export_csv(tmp_path / "a.csv")
    # Export is not a save — dirty flag is untouched by it.
    assert svc.state.dirty is True


def test_load_bundle_restores_state(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.set_calibration(0.02)

    bundle_p = tmp_path / "round.bacmask"
    svc.save_bundle(bundle_p)

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
    svc.save_bundle(bundle_p)

    svc2 = MaskService()
    svc2.load_bundle(bundle_p)
    assert svc2.state.next_label_id == 3
    lid = _draw_lasso(svc2, _square(40, 10, 5))
    assert lid == 3  # new region gets 3, not reusing 1


# ---- save / export guards ----


def test_save_bundle_without_image_raises(tmp_path):
    svc = MaskService()
    with pytest.raises(ValueError):
        svc.save_bundle(tmp_path / "x.bacmask")


def test_export_csv_without_image_raises(tmp_path):
    svc = MaskService()
    with pytest.raises(ValueError):
        svc.export_csv(tmp_path / "x.csv")


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


def test_edit_vertices_allows_overlap_with_neighbor(tmp_path):
    """Overlaps are allowed (knowledge/025). Region 2's own mask is preserved,
    and region 1's expanded mask does claim the shared pixels too. The display
    label_map shows the higher id on top (region 2) for the overlap.
    """
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, [(5, 5), (15, 5), (15, 15), (5, 15)])  # region 1
    _draw_lasso(svc, [(20, 5), (30, 5), (30, 15), (20, 15)])  # region 2
    r2_mask_before = svc.state.region_masks[2].copy()

    # Extend region 1 into region 2's range.
    svc.edit_vertices(1, [(5, 5), (25, 5), (25, 15), (5, 15)])

    # Region 2's own mask is untouched.
    assert np.array_equal(svc.state.region_masks[2], r2_mask_before)
    # Region 1's mask now claims overlapping pixels (e.g. inside both rectangles).
    assert svc.state.region_masks[1][10, 22] is np.True_ or svc.state.region_masks[1][10, 22]
    # Display cache: higher id (region 2) wins the overlap pixel.
    assert svc.state.label_map[10, 22] == 2


# ---- observers ----


def test_subscribe_fires_on_state_change(tmp_path):
    svc = MaskService()
    calls: list[str] = []
    svc.subscribe(lambda: calls.append("x"))
    svc.load_image(_write_image(tmp_path))
    assert len(calls) >= 1


# ---- edit mode ----


def test_toggle_edit_mode_flips_flag_and_notifies():
    svc = MaskService()
    assert svc.state.edit_mode is False
    calls: list[bool] = []
    svc.subscribe(lambda: calls.append(svc.state.edit_mode))

    assert svc.toggle_edit_mode() is True
    assert svc.state.edit_mode is True
    assert svc.toggle_edit_mode() is False
    assert svc.state.edit_mode is False
    assert calls == [True, False]


def test_set_edit_mode_is_idempotent():
    svc = MaskService()
    calls: list[int] = []
    svc.subscribe(lambda: calls.append(1))

    svc.set_edit_mode(False)  # already False
    svc.set_edit_mode(True)
    svc.set_edit_mode(True)  # no-op
    svc.set_edit_mode(False)
    # Only the two real transitions should have fired.
    assert sum(calls) == 2


def test_toggle_edit_mode_cancels_active_lasso(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    svc.begin_lasso((5, 5))
    svc.add_lasso_point((10, 10))
    assert svc.state.active_lasso is not None

    svc.toggle_edit_mode()
    assert svc.state.active_lasso is None


# ---- zero-area guard ----


# ---- region_masks derived state ----


def test_region_masks_populated_on_lasso_close(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    assert 1 in svc.state.region_masks
    rm = svc.state.region_masks[1]
    assert rm.dtype == bool
    assert rm.shape == svc.state.label_map.shape
    # region_masks count equals label_map count (disjoint, no overlaps yet).
    assert rm.sum() == (svc.state.label_map == 1).sum()


def test_region_masks_cleared_on_delete(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.delete_region(1)
    assert 1 not in svc.state.region_masks
    assert (svc.state.label_map == 1).sum() == 0


def test_region_masks_restored_on_undo(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    pixels = svc.state.region_masks[1].sum()
    svc.delete_region(1)
    svc.undo()
    assert 1 in svc.state.region_masks
    assert svc.state.region_masks[1].sum() == pixels


def test_area_uses_region_masks_not_label_map(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())

    # Simulate an overlap by manually extending region 1's mask to cover pixels
    # owned by a second region in the label_map. compute_area_rows must count
    # the region_mask, not the label_map — overlap-inclusive per knowledge/025.
    svc.state.region_masks[1] = np.ones_like(svc.state.label_map, dtype=bool)
    rows = svc.compute_area_rows()
    h, w = svc.state.label_map.shape
    assert rows[0].area_px == h * w


def test_load_bundle_rebuilds_region_masks(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.set_calibration(0.01)

    bundle_p = tmp_path / "x.bacmask"
    svc.save_bundle(bundle_p)

    svc2 = MaskService()
    svc2.load_bundle(bundle_p)
    assert 1 in svc2.state.region_masks
    assert svc2.state.region_masks[1].sum() == svc.state.region_masks[1].sum()


def test_close_lasso_discards_zero_area_polygon(tmp_path, caplog):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    # Three collinear points — polygon encloses no area.
    collinear = [(5, 5), (10, 5), (15, 5)]
    with caplog.at_level("WARNING", logger="bacmask.services.mask_service"):
        assert _draw_lasso(svc, collinear) is None
    assert svc.state.regions == {}
    assert svc.state.next_label_id == 1
    assert any("zero area" in rec.message for rec in caplog.records)


# ---- edit_region_stroke: add / subtract -------------------------------------


def _add_stroke_out_to_out(x_start_inside: int = 15, y: int = 14) -> list[tuple[int, int]]:
    """Stroke that starts inside the (10-20, 10-20) square, exits just past
    the right edge, loops adjacent to it, and re-enters — an 'add' stroke
    whose outside-run rasterizes to a blob 8-connected to the region."""
    return [
        (x_start_inside, y),  # inside
        (18, y),  # inside (20 is inside; 21 is outside)
        (21, y),  # first outside sample (P between idx 1 and 2)
        (25, y),
        (25, y + 2),
        (25, y + 4),
        (21, y + 4),  # last outside sample
        (18, y + 4),  # back inside (Q between idx 6 and 7)
        (15, y + 4),  # inside
    ]


def test_edit_region_stroke_add_extends_region(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    # Region 1 at (10,10)-(20,20) — 11x11 = 121 px.
    _draw_lasso(svc, _square(10, 10, 10))
    before_area = int(svc.state.region_masks[1].sum())

    samples = _add_stroke_out_to_out(15, 14)
    result = svc.edit_region_stroke(1, samples)

    assert result == "added"
    # Region 1's own mask grew.
    assert int(svc.state.region_masks[1].sum()) > before_area
    # Vertex list updated (not the original 4 square corners).
    assert svc.state.regions[1]["vertices"] != [
        [10, 10],
        [20, 10],
        [20, 20],
        [10, 20],
    ]
    # History got one edit entry (+1 to the initial lasso).
    assert len(svc.history) == 2


def test_edit_region_stroke_subtract_cuts_a_bite(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))  # 121 px
    before_area = int(svc.state.region_masks[1].sum())

    # Stroke starts outside, crosses in, loops inside, crosses back out.
    samples = [
        (5, 15),  # outside (left of region)
        (12, 15),  # inside
        (15, 15),
        (15, 18),
        (18, 18),
        (18, 15),
        (25, 15),  # outside (right of region)
    ]
    result = svc.edit_region_stroke(1, samples)

    assert result == "subtracted"
    after_area = int(svc.state.region_masks[1].sum())
    assert after_area < before_area
    assert after_area > 0  # not fully erased


def test_edit_region_stroke_no_second_crossing_discards(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))
    hist_before = len(svc.history)

    # Stroke enters the region but never exits — only one crossing.
    samples = [(5, 15), (12, 15), (14, 15), (16, 15)]
    result = svc.edit_region_stroke(1, samples)

    assert result is None
    assert len(svc.history) == hist_before
    assert svc.state.region_masks[1].sum() == 121


def test_edit_region_stroke_too_few_samples_discards(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))

    result = svc.edit_region_stroke(1, [(12, 12), (13, 13)])
    assert result is None
    assert len(svc.history) == 1  # only the original lasso


def test_edit_region_stroke_unknown_target_raises(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    with pytest.raises(KeyError):
        svc.edit_region_stroke(99, [(1, 1), (5, 5), (10, 10), (1, 1)])


def test_edit_region_stroke_undo_restores_region_mask_pixel_identically(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))
    before_mask = svc.state.region_masks[1].copy()
    before_verts = list(svc.state.regions[1]["vertices"])
    before_map = svc.state.label_map.copy()

    samples = [
        (5, 15),
        (12, 15),
        (15, 15),
        (15, 18),
        (18, 18),
        (18, 15),
        (25, 15),
    ]
    assert svc.edit_region_stroke(1, samples) == "subtracted"
    assert svc.undo() is True

    assert np.array_equal(svc.state.region_masks[1], before_mask)
    assert svc.state.regions[1]["vertices"] == before_verts
    assert np.array_equal(svc.state.label_map, before_map)


def test_edit_region_stroke_subtract_emptying_routes_to_delete(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    # Small 3x3 region at (10,10)-(12,12) — the subtract stroke's inside-run
    # traces a rectangle around all region corners, so the rasterized S fully
    # covers the region and new_mask ends up empty.
    _draw_lasso(svc, _square(10, 10, 2))
    assert 1 in svc.state.regions
    id_before = svc.state.next_label_id

    # Outside -> four inside corner samples -> outside. samples[P+1:Q+1] is
    # the four inside corners, which rasterize to the full 3x3 square mask.
    samples = [
        (5, 5),  # outside
        (10, 10),  # inside top-left — P between 0 and 1
        (12, 10),  # inside top-right
        (12, 12),  # inside bottom-right
        (10, 12),  # inside bottom-left
        (20, 20),  # outside — Q between 4 and 5
    ]
    result = svc.edit_region_stroke(1, samples)

    assert result == "deleted"
    assert 1 not in svc.state.regions
    assert 1 not in svc.state.region_masks
    # next_label_id is NOT decremented — ID 1 stays reserved (knowledge/014).
    assert svc.state.next_label_id == id_before


def test_edit_region_stroke_add_allows_overlap_with_neighbor(tmp_path):
    """An add stroke extending region 1 into region 2 does NOT clip. Both
    region_masks claim overlap pixels; display cache shows highest id."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, [(5, 10), (15, 10), (15, 20), (5, 20)])  # region 1
    _draw_lasso(svc, [(20, 10), (30, 10), (30, 20), (20, 20)])  # region 2
    r2_mask_before = svc.state.region_masks[2].copy()

    # Start inside region 1, exit to the right into region 2's pixels, loop
    # through several outside samples, re-enter region 1.
    samples = [
        (10, 15),  # inside region 1
        (14, 15),  # inside
        (22, 15),  # outside r1 (but inside r2) — P between 1 and 2
        (25, 15),
        (25, 12),
        (22, 12),
        (18, 12),
        (16, 12),  # still outside r1 (r1 ends at x=15)
        (14, 12),  # back inside r1 — Q between 7 and 8
        (10, 12),
    ]
    result = svc.edit_region_stroke(1, samples)
    assert result == "added"

    # Region 2's own mask is untouched.
    assert np.array_equal(svc.state.region_masks[2], r2_mask_before)
    # Region 1 now claims pixels overlapping region 2.
    assert svc.state.region_masks[1][14, 22]
    assert svc.state.region_masks[2][14, 22]
    # Display cache resolves to the higher label on the overlap.
    assert svc.state.label_map[14, 22] == 2


def test_edit_region_stroke_notifies_observers(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))

    calls: list[int] = []
    svc.subscribe(lambda: calls.append(1))

    samples = _add_stroke_out_to_out(15, 14)
    svc.edit_region_stroke(1, samples)
    assert sum(calls) >= 1
