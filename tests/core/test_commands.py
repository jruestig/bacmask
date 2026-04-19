import numpy as np
import pytest

from bacmask.core.commands import (
    BrushStrokeCommand,
    DeleteRegionCommand,
    LassoCloseCommand,
)
from bacmask.core.state import SessionState


def _state(h: int = 50, w: int = 50) -> SessionState:
    s = SessionState()
    s.image = np.zeros((h, w, 3), dtype=np.uint8)
    s.image_filename = "synthetic.png"
    s.label_map = np.zeros((h, w), dtype=np.uint16)
    return s


def _square_verts(x0: int = 10, y0: int = 10, size: int = 10) -> np.ndarray:
    return np.array(
        [[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size]],
        dtype=np.int32,
    )


# ---- LassoCloseCommand -------------------------------------------------------


def test_lasso_close_assigns_id_and_fills_interior():
    s = _state()
    cmd = LassoCloseCommand(_square_verts())
    cmd.apply(s)

    assert cmd.assigned_label_id == 1
    assert (s.label_map == 1).sum() > 0
    assert s.regions[1]["name"] == "region_01"
    assert s.next_label_id == 2
    assert s.dirty is True


def test_lasso_close_undo_restores_state():
    s = _state()
    cmd = LassoCloseCommand(_square_verts())
    cmd.apply(s)
    cmd.undo(s)

    assert (s.label_map == 1).sum() == 0
    assert 1 not in s.regions
    assert s.next_label_id == 1


def test_lasso_close_undo_then_apply_is_bit_identical():
    s = _state()
    cmd = LassoCloseCommand(_square_verts())
    cmd.apply(s)
    snapshot = s.label_map.copy()
    cmd.undo(s)
    cmd.apply(s)
    assert np.array_equal(s.label_map, snapshot)
    assert s.next_label_id == 2


# ---- DeleteRegionCommand -----------------------------------------------------


def test_delete_region_removes_pixels_and_metadata():
    s = _state()
    LassoCloseCommand(_square_verts()).apply(s)
    assert 1 in s.regions

    DeleteRegionCommand(label_id=1).apply(s)
    assert (s.label_map == 1).sum() == 0
    assert 1 not in s.regions


def test_delete_region_undo_restores_pixels():
    s = _state()
    LassoCloseCommand(_square_verts()).apply(s)
    before = s.label_map.copy()

    delete = DeleteRegionCommand(label_id=1)
    delete.apply(s)
    delete.undo(s)

    assert np.array_equal(s.label_map, before)
    assert 1 in s.regions


def test_deleted_id_is_not_reused_by_next_lasso():
    s = _state()
    LassoCloseCommand(_square_verts()).apply(s)
    DeleteRegionCommand(label_id=1).apply(s)

    second = LassoCloseCommand(_square_verts(25, 25, 10))
    second.apply(s)
    assert second.assigned_label_id == 2
    assert 1 not in s.regions


# ---- BrushStrokeCommand -------------------------------------------------------


def test_brush_stroke_command_swaps_vertices():
    s = _state()
    LassoCloseCommand(_square_verts(10, 10, 10)).apply(s)  # region 1

    new_verts = np.array([[10, 10], [25, 10], [25, 20], [10, 20]], dtype=np.int32)

    cmd = BrushStrokeCommand(label_id=1, new_vertices=new_verts)
    cmd.apply(s)

    assert s.regions[1]["vertices"] == new_verts.tolist()
    assert (s.label_map == 1).any()
    # Region extends further right now.
    ys, xs = np.where(s.label_map == 1)
    assert int(xs.max()) == 25
    assert s.dirty is True


def test_brush_stroke_command_undo_restores_state():
    s = _state()
    LassoCloseCommand(_square_verts(10, 10, 10)).apply(s)
    before_map = s.label_map.copy()
    before_verts = list(s.regions[1]["vertices"])

    new_verts = np.array([[10, 10], [25, 10], [25, 20], [10, 20]], dtype=np.int32)
    cmd = BrushStrokeCommand(label_id=1, new_vertices=new_verts)
    cmd.apply(s)
    cmd.undo(s)

    assert np.array_equal(s.label_map, before_map)
    assert s.regions[1]["vertices"] == before_verts


def test_brush_stroke_command_apply_undo_apply_is_byte_identical():
    s = _state()
    LassoCloseCommand(_square_verts(10, 10, 10)).apply(s)

    new_verts = np.array([[10, 10], [25, 10], [25, 20], [10, 20]], dtype=np.int32)
    cmd = BrushStrokeCommand(label_id=1, new_vertices=new_verts)
    cmd.apply(s)
    after_map = s.label_map.copy()
    after_verts = list(s.regions[1]["vertices"])
    cmd.undo(s)
    cmd.apply(s)

    assert np.array_equal(s.label_map, after_map)
    assert s.regions[1]["vertices"] == after_verts


def test_brush_stroke_command_rejects_unknown_label():
    s = _state()
    new_verts = np.array([[1, 1], [5, 1], [5, 5]], dtype=np.int32)
    with pytest.raises(ValueError):
        BrushStrokeCommand(
            label_id=99,
            new_vertices=new_verts,
        ).apply(s)


def test_brush_stroke_command_rejects_fewer_than_3_vertices():
    s = _state()
    LassoCloseCommand(_square_verts(10, 10, 10)).apply(s)
    with pytest.raises(ValueError):
        BrushStrokeCommand(
            label_id=1,
            new_vertices=np.array([[10, 10], [15, 10]], dtype=np.int32),
        ).apply(s)
