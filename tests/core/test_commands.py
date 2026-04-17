import numpy as np
import pytest

from bacmask.core.commands import (
    DeleteRegionCommand,
    LassoCloseCommand,
    VertexEditCommand,
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


# ---- VertexEditCommand -------------------------------------------------------


def test_vertex_edit_moves_pixels_same_id():
    s = _state()
    LassoCloseCommand(_square_verts(10, 10, 10)).apply(s)
    # Shift rectangle right by 5.
    new_verts = np.array([[15, 10], [25, 10], [25, 20], [15, 20]], dtype=np.int32)
    VertexEditCommand(label_id=1, new_vertices=new_verts).apply(s)

    assert s.label_map[10, 10] == 0  # old corner now background
    ys, xs = np.where(s.label_map == 1)
    assert int(xs.min()) == 15
    assert int(xs.max()) == 25


def test_vertex_edit_updates_region_vertices():
    s = _state()
    LassoCloseCommand(_square_verts()).apply(s)
    new_verts = np.array([[15, 10], [25, 10], [25, 20], [15, 20]], dtype=np.int32)
    VertexEditCommand(label_id=1, new_vertices=new_verts).apply(s)
    assert s.regions[1]["vertices"] == [
        [15, 10],
        [25, 10],
        [25, 20],
        [15, 20],
    ]


def test_vertex_edit_undo_restores_pixels_and_vertices():
    s = _state()
    LassoCloseCommand(_square_verts()).apply(s)
    before_map = s.label_map.copy()
    before_verts = list(s.regions[1]["vertices"])

    new_verts = np.array([[15, 10], [25, 10], [25, 20], [15, 20]], dtype=np.int32)
    cmd = VertexEditCommand(label_id=1, new_vertices=new_verts)
    cmd.apply(s)
    cmd.undo(s)

    assert np.array_equal(s.label_map, before_map)
    assert s.regions[1]["vertices"] == before_verts


def test_vertex_edit_apply_undo_apply_is_idempotent():
    s = _state()
    LassoCloseCommand(_square_verts()).apply(s)
    new_verts = np.array([[15, 10], [25, 10], [25, 20], [15, 20]], dtype=np.int32)
    cmd = VertexEditCommand(label_id=1, new_vertices=new_verts)
    cmd.apply(s)
    after_map = s.label_map.copy()
    after_verts = list(s.regions[1]["vertices"])
    cmd.undo(s)
    cmd.apply(s)

    assert np.array_equal(s.label_map, after_map)
    assert s.regions[1]["vertices"] == after_verts


def test_vertex_edit_clips_around_adjacent_region():
    """New polygon crosses into region 2's territory; region 2 must be untouched."""
    s = _state(h=50, w=50)
    LassoCloseCommand(np.array([[5, 5], [15, 5], [15, 15], [5, 15]], dtype=np.int32)).apply(
        s
    )  # region 1
    LassoCloseCommand(np.array([[20, 5], [30, 5], [30, 15], [20, 15]], dtype=np.int32)).apply(
        s
    )  # region 2

    region2_pixels_before = (s.label_map == 2).sum()
    pixel_22_10_before = s.label_map[10, 22]  # inside region 2

    # Edit region 1 to extend into region 2's column range.
    new_verts = np.array([[5, 5], [25, 5], [25, 15], [5, 15]], dtype=np.int32)
    VertexEditCommand(label_id=1, new_vertices=new_verts).apply(s)

    # Region 2 intact (clip policy).
    assert (s.label_map == 2).sum() == region2_pixels_before
    assert s.label_map[10, 22] == pixel_22_10_before == 2
    # Background between the two regions now owned by region 1.
    assert s.label_map[10, 18] == 1


def test_vertex_edit_clip_is_reversible():
    s = _state(h=50, w=50)
    LassoCloseCommand(np.array([[5, 5], [15, 5], [15, 15], [5, 15]], dtype=np.int32)).apply(s)
    LassoCloseCommand(np.array([[20, 5], [30, 5], [30, 15], [20, 15]], dtype=np.int32)).apply(s)
    before = s.label_map.copy()

    new_verts = np.array([[5, 5], [25, 5], [25, 15], [5, 15]], dtype=np.int32)
    cmd = VertexEditCommand(label_id=1, new_vertices=new_verts)
    cmd.apply(s)
    cmd.undo(s)

    assert np.array_equal(s.label_map, before)


def test_vertex_edit_rejects_fewer_than_3_vertices():
    s = _state()
    LassoCloseCommand(_square_verts()).apply(s)
    with pytest.raises(ValueError):
        VertexEditCommand(
            label_id=1,
            new_vertices=np.array([[10, 10], [20, 10]], dtype=np.int32),
        ).apply(s)


def test_vertex_edit_rejects_unknown_label():
    s = _state()
    with pytest.raises(ValueError):
        VertexEditCommand(
            label_id=42,
            new_vertices=np.array([[10, 10], [20, 10], [20, 20]], dtype=np.int32),
        ).apply(s)


def test_vertex_edit_shape_change_no_other_region():
    """Edit that changes shape significantly (triangle → pentagon) with no collisions."""
    s = _state()
    LassoCloseCommand(_square_verts(5, 5, 10)).apply(s)
    new_verts = np.array([[5, 5], [15, 5], [18, 10], [15, 15], [5, 15]], dtype=np.int32)
    VertexEditCommand(label_id=1, new_vertices=new_verts).apply(s)
    # Pentagon extends to x=18 now.
    ys, xs = np.where(s.label_map == 1)
    assert int(xs.max()) >= 17
