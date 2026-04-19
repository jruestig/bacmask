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


def test_close_lasso_stores_raster_derived_contour(tmp_path):
    """Stored vertices come from ``cv2.findContours`` on the rasterized mask —
    not from the raw user scribble. This kills the "random connection on
    release" artifact: any implicit chord from last-point-to-first-point is
    dissolved by going through the raster, so the stored polygon is always a
    clean simple closed curve tracing the filled region's actual boundary.
    """
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    # A reasonable outline that *doesn't* return exactly to the start — this
    # is the realistic "user released away from start" case. Before the
    # cleanup, the implicit chord (last → first) introduced a diagonal edge
    # that could sit inside the drawn shape.
    raw_verts = [(10, 10), (30, 10), (30, 30), (12, 30), (12, 15)]
    _draw_lasso(svc, raw_verts)
    mask = svc.state.region_masks[1]
    # Every stored vertex lies on the rasterized region's boundary — no stray
    # chord vertex can survive the findContours pass.
    for x, y in svc.state.regions[1]["vertices"]:
        assert mask[y, x], f"stored vertex ({x}, {y}) is not on the mask"


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


# ---- tool selection (knowledge/026) ----


def test_default_active_tool_is_lasso():
    svc = MaskService()
    assert svc.state.active_tool == "lasso"


def test_set_active_tool_brush_notifies():
    svc = MaskService()
    calls: list[str] = []
    svc.subscribe(lambda: calls.append(svc.state.active_tool))
    svc.set_active_tool("brush")
    assert svc.state.active_tool == "brush"
    assert calls[-1] == "brush"


def test_set_active_tool_idempotent():
    svc = MaskService()
    calls: list[int] = []
    svc.subscribe(lambda: calls.append(1))
    svc.set_active_tool("lasso")  # already lasso
    svc.set_active_tool("brush")
    svc.set_active_tool("brush")  # no-op
    svc.set_active_tool("lasso")
    assert sum(calls) == 2


def test_set_active_tool_rejects_unknown():
    svc = MaskService()
    with pytest.raises(ValueError):
        svc.set_active_tool("foo")  # type: ignore[arg-type]


def test_set_brush_radius_clamps_and_validates():
    svc = MaskService()
    svc.set_brush_radius(15)
    assert svc.state.brush_radius_px == 15
    with pytest.raises(ValueError):
        svc.set_brush_radius(0)
    with pytest.raises(ValueError):
        svc.set_brush_radius(101)


def test_default_brush_mode_is_add():
    svc = MaskService()
    assert svc.state.brush_default_mode == "add"


def test_set_brush_default_mode_subtract():
    svc = MaskService()
    svc.set_brush_default_mode("subtract")
    assert svc.state.brush_default_mode == "subtract"


def test_set_brush_default_mode_rejects_unknown():
    svc = MaskService()
    with pytest.raises(ValueError):
        svc.set_brush_default_mode("erase")


def test_brush_default_mode_drives_unmodified_stroke(tmp_path):
    """No modifier + default subtract → stroke is subtract."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))
    svc.set_brush_default_mode("subtract")

    svc.begin_brush_stroke((15, 15))
    assert svc.state.active_brush_stroke.mode == "subtract"


def test_toggle_brush_default_mode_flips():
    svc = MaskService()
    assert svc.state.brush_default_mode == "add"
    assert svc.toggle_brush_default_mode() == "subtract"
    assert svc.state.brush_default_mode == "subtract"
    assert svc.toggle_brush_default_mode() == "add"
    assert svc.state.brush_default_mode == "add"


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


# ---- brush stroke: add / subtract (knowledge/026) ---------------------------


def _run_brush(
    svc: MaskService,
    samples: list[tuple[int, int]],
    mode: str = "add",
) -> str | None:
    """Drive the service through a full brush stroke: begin → samples → end."""
    svc.set_active_tool("brush")
    svc.set_brush_default_mode(mode)
    target = svc.begin_brush_stroke(samples[0])
    if target is None:
        return None
    for p in samples[1:]:
        svc.add_brush_sample(p)
    return svc.end_brush_stroke()


def test_begin_brush_stroke_on_background_is_noop_without_selection(tmp_path):
    """No selected region + press on background → no stroke."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))
    svc.clear_selection()
    history_before = len(svc.history)

    target = svc.begin_brush_stroke((40, 40))  # background
    assert target is None
    assert svc.state.active_brush_stroke is None
    assert len(svc.history) == history_before


def test_begin_brush_stroke_off_region_uses_selected_target(tmp_path):
    """When a region is selected, pressing off it locks the stroke to the
    selection — required so a subtract can carve into the boundary from the
    empty pixels next to it."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))
    svc.select_region(1)

    target = svc.begin_brush_stroke((40, 40))  # background pixel
    assert target == 1
    assert svc.state.active_brush_stroke is not None
    assert svc.state.active_brush_stroke.target_id == 1


def test_brush_subtract_from_outside_carves_into_region(tmp_path):
    """End-to-end: with subtract mode set + region selected, a stroke that
    begins on background and drags into the region carves out a bite from
    the boundary."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))  # region 1, 121 px
    svc.select_region(1)
    before = int(svc.state.region_masks[1].sum())
    svc.set_brush_radius(3)
    svc.set_brush_default_mode("subtract")

    # Press starts well outside the region (x=2), drags right through the
    # left boundary (x=10) into the interior. With the selection lock the
    # stroke targets region 1 even though press-down is on background.
    svc.set_active_tool("brush")
    target = svc.begin_brush_stroke((2, 15))
    assert target == 1
    for x in (5, 8, 12, 15):
        svc.add_brush_sample((x, 15))
    result = svc.end_brush_stroke()
    assert result == "subtracted"
    assert int(svc.state.region_masks[1].sum()) < before


def test_begin_brush_stroke_press_on_other_region_retargets(tmp_path):
    """Pressing on a different existing region switches the lock to it."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(5, 5, 8))  # region 1
    _draw_lasso(svc, _square(30, 30, 8))  # region 2
    svc.select_region(1)

    target = svc.begin_brush_stroke((33, 33))  # press on region 2
    assert target == 2
    assert svc.state.active_brush_stroke.target_id == 2
    assert svc.state.selected_region_id == 2


def test_begin_brush_stroke_locks_target_and_selects_it(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))
    svc.clear_selection()

    target = svc.begin_brush_stroke((15, 15))
    assert target == 1
    assert svc.state.selected_region_id == 1
    assert svc.state.active_brush_stroke is not None
    assert svc.state.active_brush_stroke.mode == "add"


def test_begin_brush_stroke_uses_default_mode(tmp_path):
    """Mode comes from state.brush_default_mode — no modifier override."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))
    svc.set_brush_default_mode("subtract")

    svc.begin_brush_stroke((15, 15))
    assert svc.state.active_brush_stroke.mode == "subtract"


def test_brush_add_extends_region(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))  # region 1, 121 px
    before = int(svc.state.region_masks[1].sum())
    svc.set_brush_radius(3)

    # Press inside, drag out past the right edge — paint adds a lobe.
    result = _run_brush(svc, [(15, 15), (20, 15), (24, 15)])
    assert result == "added"
    assert int(svc.state.region_masks[1].sum()) > before
    # History: original lasso + one brush command.
    assert len(svc.history) == 2


def test_brush_subtract_cuts_a_bite(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))  # region 1, 121 px
    before = int(svc.state.region_masks[1].sum())
    svc.set_brush_radius(2)

    # Subtract mode set; press inside; drag along the bottom edge.
    result = _run_brush(svc, [(13, 18), (16, 18), (18, 18)], mode="subtract")
    assert result == "subtracted"
    after = int(svc.state.region_masks[1].sum())
    assert after < before
    assert after > 0  # not fully erased


def test_brush_subtract_emptying_routes_to_delete(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    # Small 3x3 region at (10,10)-(12,12). A radius-3 disc centered inside
    # paints over the entire region.
    _draw_lasso(svc, _square(10, 10, 2))
    assert 1 in svc.state.regions
    id_before = svc.state.next_label_id
    svc.set_brush_radius(5)

    result = _run_brush(svc, [(11, 11)], mode="subtract")
    assert result == "deleted"
    assert 1 not in svc.state.regions
    assert 1 not in svc.state.region_masks
    # ID 1 stays reserved — monotonic IDs (knowledge/014).
    assert svc.state.next_label_id == id_before


def test_brush_no_intersection_is_discarded(tmp_path):
    """An add stroke that paints only background outside the target region's
    influence (no intersection with the region after the OR) is a no-op.

    With add mode, ``new_mask = target | S`` — if ``S`` doesn't change the
    target's pixels at all (because ``S`` is empty), the result equals the
    target and no command is committed.
    """
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))
    history_before = len(svc.history)

    # Begin stroke on the region (so we have a valid target), then never add
    # any other samples. The stamped disc covers a few pixels of the region
    # itself, which means new_mask == target after OR (no growth) — discarded.
    svc.set_brush_radius(1)
    svc.set_active_tool("brush")
    svc.begin_brush_stroke((15, 15))
    result = svc.end_brush_stroke()
    assert result is None
    assert len(svc.history) == history_before


def test_cancel_brush_stroke_discards_no_history(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))
    history_before = len(svc.history)

    svc.set_active_tool("brush")
    svc.begin_brush_stroke((15, 15))
    svc.add_brush_sample((20, 15))
    svc.cancel_brush_stroke()
    assert svc.state.active_brush_stroke is None
    assert len(svc.history) == history_before


def test_brush_add_undo_restores_state_pixel_identically(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))
    before_mask = svc.state.region_masks[1].copy()
    before_verts = list(svc.state.regions[1]["vertices"])
    before_map = svc.state.label_map.copy()
    svc.set_brush_radius(3)

    assert _run_brush(svc, [(15, 15), (22, 15)]) == "added"
    assert svc.undo() is True
    assert np.array_equal(svc.state.region_masks[1], before_mask)
    assert svc.state.regions[1]["vertices"] == before_verts
    assert np.array_equal(svc.state.label_map, before_map)


def test_brush_target_locked_at_press_down(tmp_path):
    """Dragging across other regions does not re-target — the press-down
    region owns the entire stroke (knowledge/026)."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(5, 10, 10))  # region 1: x=5..15
    _draw_lasso(svc, _square(25, 10, 10))  # region 2: x=25..35
    r2_before = svc.state.region_masks[2].copy()
    svc.set_brush_radius(2)

    # Press inside region 1, drag through the gap into region 2's territory.
    result = _run_brush(svc, [(10, 15), (20, 15), (28, 15)])
    assert result == "added"
    # Region 2's own mask is unchanged — the stroke only edits region 1.
    assert np.array_equal(svc.state.region_masks[2], r2_before)
    # Region 1 grew toward region 2.
    assert svc.state.region_masks[1][15, 20]


def test_brush_overlap_with_neighbor_allowed(tmp_path):
    """Adding into a neighbor's pixels: both region_masks claim overlap;
    display cache shows highest id (knowledge/025)."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(5, 10, 10))  # region 1
    _draw_lasso(svc, _square(20, 10, 10))  # region 2
    r2_before = svc.state.region_masks[2].copy()
    svc.set_brush_radius(3)

    # Drag from inside region 1 into region 2's body. Add stroke.
    result = _run_brush(svc, [(10, 15), (16, 15), (22, 15)])
    assert result == "added"
    # Region 2 untouched.
    assert np.array_equal(svc.state.region_masks[2], r2_before)
    # The shared pixel belongs to both region_masks.
    assert svc.state.region_masks[1][15, 22]
    assert svc.state.region_masks[2][15, 22]
    # Display: higher id wins.
    assert svc.state.label_map[15, 22] == 2


def test_end_brush_stroke_with_no_active_returns_none(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    assert svc.end_brush_stroke() is None


def test_brush_notifies_observers(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))
    svc.set_brush_radius(3)

    calls: list[int] = []
    svc.subscribe(lambda: calls.append(1))
    _run_brush(svc, [(15, 15), (22, 15)])
    assert sum(calls) >= 1
