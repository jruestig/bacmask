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
    from bacmask.core import masking

    stored = np.asarray(svc.state.regions[1]["vertices"], dtype=np.int32)
    mask = masking.rasterize_polygon_mask(stored, svc.state.label_map.shape)
    # Every stored vertex lies on the rasterized region's boundary — no stray
    # chord vertex can survive the findContours pass.
    for x, y in stored.tolist():
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
    _draw_lasso(svc, _square())  # contour of 11x11 raster block: shoelace = 100.0
    rows = svc.compute_area_rows()
    assert len(rows) == 1
    r = rows[0]
    assert r.region_id == 1
    assert r.region_name == "region_01"
    # Shoelace of the polygon (knowledge/030), not rasterized pixel count.
    assert r.area_px == pytest.approx(100.0, abs=1e-9)
    assert r.area_mm2 is None
    assert r.scale_factor is None


def test_area_rows_calibrated(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())  # shoelace = 100.0
    svc.set_calibration(0.01)
    r = svc.compute_area_rows()[0]
    assert r.area_mm2 == pytest.approx(100.0 * 0.0001, abs=1e-12)
    assert r.scale_factor == 0.01


def test_compute_area_rows_uses_polygon_shoelace(tmp_path):
    """area_px must match polygon_area(vertices), not rasterized count.

    Drives the service directly and compares the returned area to the
    shoelace of the region's stored polygon. This is the anchor against
    regression to the old cached-``region_areas`` code path.
    """
    from bacmask.core import masking

    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    # Triangle with corners (5, 5), (25, 5), (5, 25) — shoelace = 200.0
    # before raster round-trip. After the lasso's contour-re-derivation the
    # stored polygon is the pixel-centered boundary trace of the filled
    # triangle, so we compare against its shoelace rather than 200.0.
    _draw_lasso(svc, [(5, 5), (25, 5), (5, 25)])
    stored = svc.state.regions[1]["vertices"]
    expected = masking.polygon_area(stored)
    assert expected > 0.0  # sanity: non-degenerate
    r = svc.compute_area_rows()[0]
    assert isinstance(r.area_px, float)
    assert r.area_px == pytest.approx(expected, abs=1e-9)


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


def test_export_csv_emits_lines_sibling_when_lines_present(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.set_calibration(0.01)
    svc.set_active_tool("line")
    svc.begin_line((5, 5))
    svc.commit_line((25, 5))

    areas_p = tmp_path / "out_areas.csv"
    lines_p = tmp_path / "out_lines.csv"
    svc.export_csv(areas_p)

    assert areas_p.exists()
    assert lines_p.exists()
    contents = lines_p.read_text().splitlines()
    assert contents[0] == "filename,line_id,line_name,length_px,length_mm,scale_factor"
    assert contents[1].startswith("img.png,1,line_1,20.0,")


def test_export_csv_skips_lines_sibling_when_no_lines(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())

    areas_p = tmp_path / "out_areas.csv"
    svc.export_csv(areas_p)

    assert areas_p.exists()
    assert not (tmp_path / "out_lines.csv").exists()


def test_export_csv_lines_sibling_path_for_non_areas_name(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.set_active_tool("line")
    svc.begin_line((5, 5))
    svc.commit_line((25, 5))

    chosen = tmp_path / "custom.csv"
    svc.export_csv(chosen)

    assert chosen.exists()
    assert (tmp_path / "custom_lines.csv").exists()


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


def test_save_load_round_trips_measurement_lines(tmp_path):
    """Lines drawn before save must be present after reload."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    svc.set_active_tool("line")
    svc.begin_line((5, 5))
    first = svc.commit_line((25, 5))
    svc.begin_line((10, 10))
    second = svc.commit_line((10, 30))
    assert first == 1 and second == 2

    bundle_p = tmp_path / "lines.bacmask"
    svc.save_bundle(bundle_p)

    svc2 = MaskService()
    svc2.load_bundle(bundle_p)
    assert set(svc2.state.lines) == {1, 2}
    assert svc2.state.lines[1]["p1"] == (5, 5)
    assert svc2.state.lines[1]["p2"] == (25, 5)
    assert svc2.state.lines[2]["p1"] == (10, 10)
    assert svc2.state.lines[2]["p2"] == (10, 30)
    assert svc2.state.next_line_id == 3


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


def test_set_active_tool_accepts_line():
    svc = MaskService()
    svc.set_active_tool("line")
    assert svc.state.active_tool == "line"


# ---- line measurement tool ----


def test_commit_line_creates_measurement(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    svc.begin_line((10, 10))
    svc.update_line((20, 10))
    line_id = svc.commit_line((20, 10))
    assert line_id == 1
    assert svc.state.lines == {1: {"name": "line_1", "p1": (10, 10), "p2": (20, 10)}}
    assert svc.state.active_line is None
    assert svc.state.next_line_id == 2


def test_commit_line_zero_length_discards(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    svc.begin_line((10, 10))
    assert svc.commit_line((10, 10)) is None
    assert svc.state.lines == {}
    assert svc.state.next_line_id == 1


def test_cancel_line_clears_buffer(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    svc.begin_line((10, 10))
    svc.update_line((20, 20))
    svc.cancel_line()
    assert svc.state.active_line is None
    assert svc.state.lines == {}


def test_compute_line_rows_pixel_length(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    svc.begin_line((0, 0))
    svc.commit_line((3, 4))  # 3-4-5 triangle
    rows = svc.compute_line_rows()
    assert len(rows) == 1
    assert rows[0]["line_id"] == 1
    assert rows[0]["name"] == "line_1"
    assert rows[0]["length_px"] == pytest.approx(5.0)


def test_delete_line_removes_and_clears_selection(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    svc.begin_line((0, 0))
    line_id = svc.commit_line((10, 0))
    svc.select_line(line_id)
    svc.delete_line(line_id)
    assert svc.state.lines == {}
    assert svc.state.selected_line_id is None


def test_line_id_not_reused_after_delete(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    svc.begin_line((0, 0))
    first = svc.commit_line((10, 0))
    svc.delete_line(first)
    svc.begin_line((0, 0))
    second = svc.commit_line((20, 0))
    assert second == 2


def test_load_image_clears_lines(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path, "a.png"))
    svc.begin_line((0, 0))
    svc.commit_line((10, 10))
    assert svc.state.lines
    svc.load_image(_write_image(tmp_path, "b.png"))
    assert svc.state.lines == {}
    assert svc.state.next_line_id == 1
    assert svc.state.selected_line_id is None


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


def test_toggle_brush_default_mode_cycles():
    """Order: create → add → subtract → create."""
    svc = MaskService()
    assert svc.state.brush_default_mode == "add"
    assert svc.toggle_brush_default_mode() == "subtract"
    assert svc.toggle_brush_default_mode() == "create"
    assert svc.toggle_brush_default_mode() == "add"


def test_set_brush_default_mode_create():
    svc = MaskService()
    svc.set_brush_default_mode("create")
    assert svc.state.brush_default_mode == "create"


# ---- zero-area guard ----


# ---- derived region mask (polygon is canonical, knowledge/030) ----


def test_region_polygon_populated_on_lasso_close(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    assert 1 in svc.state.regions
    assert len(svc.state.regions[1]["vertices"]) >= 3
    assert (svc.state.label_map == 1).any()


def test_region_cleared_on_delete(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.delete_region(1)
    assert 1 not in svc.state.regions
    assert (svc.state.label_map == 1).sum() == 0


def test_region_restored_on_undo(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    label_before = svc.state.label_map.copy()
    verts_before = list(svc.state.regions[1]["vertices"])
    svc.delete_region(1)
    svc.undo()
    assert 1 in svc.state.regions
    assert svc.state.regions[1]["vertices"] == verts_before
    assert np.array_equal(svc.state.label_map, label_before)


def test_area_is_overlap_inclusive(tmp_path):
    """Each region's area is its own polygon's shoelace, independent of other
    regions' coverage — overlapping pixels are counted once per region
    (knowledge/025, knowledge/030).
    """
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    # Two identical squares fully overlap. Each one's area must equal the
    # shoelace of its own polygon; the sum exceeds the union's area.
    _draw_lasso(svc, _square())
    _draw_lasso(svc, _square())
    rows = svc.compute_area_rows()
    assert len(rows) == 2
    assert rows[0].area_px == pytest.approx(rows[1].area_px, abs=1e-9)
    assert rows[0].area_px == pytest.approx(100.0, abs=1e-9)


def test_load_bundle_rebuilds_label_map(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square())
    svc.set_calibration(0.01)

    bundle_p = tmp_path / "x.bacmask"
    svc.save_bundle(bundle_p)

    svc2 = MaskService()
    svc2.load_bundle(bundle_p)
    assert 1 in svc2.state.regions
    assert np.array_equal(svc2.state.label_map, svc.state.label_map)


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


def _region_pixels(svc: MaskService, label_id: int) -> int:
    """Rasterize the canonical polygon for ``label_id`` and return its pixel count."""
    from bacmask.core import masking

    verts = np.asarray(svc.state.regions[label_id]["vertices"], dtype=np.int32)
    return int(masking.rasterize_polygon_mask(verts, svc.state.label_map.shape).sum())


def _region_mask(svc: MaskService, label_id: int) -> np.ndarray:
    from bacmask.core import masking

    verts = np.asarray(svc.state.regions[label_id]["vertices"], dtype=np.int32)
    return masking.rasterize_polygon_mask(verts, svc.state.label_map.shape)


def _run_brush(
    svc: MaskService,
    samples: list[tuple[int, int]],
    mode: str = "add",
) -> str | None:
    """Drive the service through a full brush stroke: begin → samples → end.

    Checks ``state.active_brush_stroke`` (not ``begin_brush_stroke`` return
    value) to decide whether the stroke actually started — in create mode
    ``begin_brush_stroke`` returns ``None`` for the target_id even on
    success, since the stroke isn't bound to any existing region.
    """
    svc.set_active_tool("brush")
    svc.set_brush_default_mode(mode)
    svc.begin_brush_stroke(samples[0])
    if svc.state.active_brush_stroke is None:
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
    before = _region_pixels(svc, 1)
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
    assert _region_pixels(svc, 1) < before


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
    before = _region_pixels(svc, 1)
    svc.set_brush_radius(3)

    # Press inside, drag out past the right edge — paint adds a lobe.
    result = _run_brush(svc, [(15, 15), (20, 15), (24, 15)])
    assert result == "added"
    assert _region_pixels(svc, 1) > before
    # History: original lasso + one brush command.
    assert len(svc.history) == 2


def test_brush_subtract_cuts_a_bite(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))  # region 1, 121 px
    before = _region_pixels(svc, 1)
    svc.set_brush_radius(2)

    # Subtract mode set; press inside; drag along the bottom edge.
    result = _run_brush(svc, [(13, 18), (16, 18), (18, 18)], mode="subtract")
    assert result == "subtracted"
    after = _region_pixels(svc, 1)
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


def test_brush_create_mode_commits_new_region(tmp_path):
    """Create mode: press-drag-release on empty canvas commits a new region."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    assert len(svc.state.regions) == 0
    svc.set_brush_radius(4)

    result = _run_brush(svc, [(20, 20), (25, 20), (30, 20)], mode="create")
    assert result == "created"
    assert 1 in svc.state.regions
    assert _region_mask(svc, 1).any()
    # ID monotonic — next stroke should land on 2.
    assert svc.state.next_label_id == 2


def test_brush_create_mode_ignores_existing_regions(tmp_path):
    """Create mode does not target the region under the cursor — it always
    starts a fresh one regardless of press-down location."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))  # region 1
    before_r1_verts = list(svc.state.regions[1]["vertices"])
    svc.set_brush_radius(3)

    # Press inside region 1, but in create mode → makes a new region 2 instead
    # of editing region 1.
    result = _run_brush(svc, [(15, 15), (25, 15), (35, 15)], mode="create")
    assert result == "created"
    assert 2 in svc.state.regions
    # Region 1 untouched.
    assert svc.state.regions[1]["vertices"] == before_r1_verts


def test_brush_create_mode_undo(tmp_path):
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    svc.set_brush_radius(4)
    _run_brush(svc, [(20, 20), (25, 20)], mode="create")
    assert 1 in svc.state.regions

    assert svc.undo() is True
    assert 1 not in svc.state.regions


def test_brush_create_mode_does_not_change_selection(tmp_path):
    """Selection persists across a create stroke — useful when alternating
    between create and edit on the same target."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(5, 5, 6))
    svc.select_region(1)
    svc.set_brush_radius(3)

    _run_brush(svc, [(30, 30), (35, 30)], mode="create")
    assert svc.state.selected_region_id == 1


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
    before_verts = list(svc.state.regions[1]["vertices"])
    before_map = svc.state.label_map.copy()
    svc.set_brush_radius(3)

    assert _run_brush(svc, [(15, 15), (22, 15)]) == "added"
    assert svc.undo() is True
    assert svc.state.regions[1]["vertices"] == before_verts
    assert np.array_equal(svc.state.label_map, before_map)


def test_brush_target_locked_at_press_down(tmp_path):
    """Dragging across other regions does not re-target — the press-down
    region owns the entire stroke (knowledge/026)."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(5, 10, 10))  # region 1: x=5..15
    _draw_lasso(svc, _square(25, 10, 10))  # region 2: x=25..35
    r2_verts_before = list(svc.state.regions[2]["vertices"])
    svc.set_brush_radius(2)

    # Press inside region 1, drag through the gap into region 2's territory.
    result = _run_brush(svc, [(10, 15), (20, 15), (28, 15)])
    assert result == "added"
    # Region 2's polygon is unchanged — the stroke only edits region 1.
    assert svc.state.regions[2]["vertices"] == r2_verts_before
    # Region 1 grew toward region 2.
    assert _region_mask(svc, 1)[15, 20]


def test_brush_overlap_with_neighbor_allowed(tmp_path):
    """Adding into a neighbor's pixels: both derived masks claim overlap;
    display cache shows highest id (knowledge/025)."""
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(5, 10, 10))  # region 1
    _draw_lasso(svc, _square(20, 10, 10))  # region 2
    r2_verts_before = list(svc.state.regions[2]["vertices"])
    svc.set_brush_radius(3)

    # Drag from inside region 1 into region 2's body. Add stroke.
    result = _run_brush(svc, [(10, 15), (16, 15), (22, 15)])
    assert result == "added"
    # Region 2's polygon untouched.
    assert svc.state.regions[2]["vertices"] == r2_verts_before
    # The shared pixel belongs to both derived masks.
    assert _region_mask(svc, 1)[15, 22]
    assert _region_mask(svc, 2)[15, 22]
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


def test_brush_add_reads_polygon_not_mask(tmp_path):
    """Brush add must commit against the canonical polygon (knowledge/030).

    After wave-2 the service never stores per-region masks — the target is
    rasterized on demand from ``state.regions[target]['vertices']``. This
    test pins the behavior: the committed polygon covers both the original
    target's interior (proof we saw the real polygon) and the stroke
    extension past the old right edge.
    """
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))  # region 1 at roughly (10..20, 10..20)

    svc.set_brush_radius(2)
    result = _run_brush(svc, [(18, 15), (22, 15), (25, 15)], mode="add")
    assert result == "added"

    # Rasterize the committed polygon and verify it covers the original
    # target's interior *and* the stroke extension.
    from bacmask.core import masking

    committed_mask = masking.rasterize_polygon_mask(
        np.asarray(svc.state.regions[1]["vertices"], dtype=np.int32),
        svc.state.label_map.shape,
    )
    # Pixel firmly inside the original square but outside the stroke.
    assert committed_mask[12, 12], "original target interior lost → commit dropped real polygon"
    # Pixel painted by the stroke past the old right edge (x=22, y=15).
    assert committed_mask[15, 22], "stroke extension missing from committed polygon"


# ---- bundle round-trip: brush-edited polygons (knowledge/030 regression) ----


def test_brush_edited_regions_survive_bundle_round_trip(tmp_path):
    """Polygons mutated by every brush commit path round-trip through save →
    load with vertex lists equal element-for-element.

    Polygons are canonical (knowledge/030); commands snapshot vertex lists
    only (wave-1B). The bundle stores no raster mask, so the loaded service
    must be able to re-derive every region from the polygons alone. This
    test composes a region from lasso + brush-add + brush-subtract and a
    second region from brush-create — each commit path writes a polygon
    through ``contour_vertices`` — then asserts the regions dict is exactly
    equal across the round-trip.
    """
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))

    _draw_lasso(svc, _square(10, 10, 12))  # region 1
    svc.set_brush_radius(2)
    assert _run_brush(svc, [(20, 16), (24, 16), (28, 16)], mode="add") == "added"
    assert _run_brush(svc, [(13, 18), (16, 18)], mode="subtract") == "subtracted"

    svc.set_brush_radius(3)
    assert _run_brush(svc, [(35, 35), (40, 35), (40, 40)], mode="create") == "created"
    assert set(svc.state.regions) == {1, 2}

    svc.set_calibration(0.005)

    pre_regions = {
        k: {"name": v["name"], "vertices": [list(p) for p in v["vertices"]]}
        for k, v in svc.state.regions.items()
    }
    pre_next_id = svc.state.next_label_id
    pre_label_map = svc.state.label_map.copy()

    bundle_p = tmp_path / "rt.bacmask"
    svc.save_bundle(bundle_p)

    svc2 = MaskService()
    svc2.load_bundle(bundle_p)

    assert svc2.state.regions == pre_regions
    assert svc2.state.next_label_id == pre_next_id
    assert svc2.state.scale_mm_per_px == 0.005
    # Display cache is derived from polygons; pin it so a silent JSON
    # int-coercion bug in vertices would still surface here.
    assert np.array_equal(svc2.state.label_map, pre_label_map)


def test_save_load_save_meta_is_stable_modulo_updated_at(tmp_path):
    """Save → load → save produces the same ``meta.json`` modulo
    ``updated_at`` (which the writer rewrites by design — knowledge/015).

    Pins determinism for the polygon section across a full round-trip:
    nothing in the loaded state should silently change vertex order, type,
    or value before being written back.
    """
    import json
    import zipfile

    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 10))
    svc.set_brush_radius(2)
    assert _run_brush(svc, [(18, 15), (22, 15), (25, 15)], mode="add") == "added"
    assert _run_brush(svc, [(13, 18), (15, 18)], mode="subtract") == "subtracted"
    svc.set_calibration(0.005)

    a = tmp_path / "a.bacmask"
    b = tmp_path / "b.bacmask"
    svc.save_bundle(a)

    svc2 = MaskService()
    svc2.load_bundle(a)
    svc2.save_bundle(b)

    def _meta(p):
        with zipfile.ZipFile(p, "r") as zf:
            m = json.loads(zf.read("meta.json"))
        m.pop("updated_at", None)
        return m

    assert _meta(a) == _meta(b)


def test_brush_edit_round_trip_survives_undo_redo(tmp_path):
    """Undo/redo across a brush stroke must restore the polygon
    bit-identically — and the round-tripped polygon (after redo) must save
    + load back to the same vertex list. Catches any drift in the command's
    snapshot path (wave-1B) where an undo→redo could otherwise re-rasterize
    and round vertex coordinates.
    """
    svc = MaskService()
    svc.load_image(_write_image(tmp_path))
    _draw_lasso(svc, _square(10, 10, 12))
    svc.set_brush_radius(2)
    assert _run_brush(svc, [(20, 16), (24, 16), (28, 16)], mode="add") == "added"

    after_add = [list(p) for p in svc.state.regions[1]["vertices"]]

    assert svc.undo() is True
    assert svc.redo() is True
    assert [list(p) for p in svc.state.regions[1]["vertices"]] == after_add

    bundle_p = tmp_path / "u.bacmask"
    svc.save_bundle(bundle_p)
    svc2 = MaskService()
    svc2.load_bundle(bundle_p)
    assert [list(p) for p in svc2.state.regions[1]["vertices"]] == after_add
