import dataclasses

import pytest

from bacmask.ui.input.desktop_adapter import DEFAULT_KEYBINDINGS, keybinding_for
from bacmask.ui.input.events import (
    Action,
    PointerDown,
    PointerMove,
    Zoom,
)


def test_pointer_down_default_modifiers_empty():
    e = PointerDown(pos=(10, 20))
    assert e.pos == (10, 20)
    assert e.modifiers == ()


def test_pointer_down_with_modifiers():
    e = PointerDown(pos=(10, 20), modifiers=("shift", "ctrl"))
    assert "shift" in e.modifiers
    assert "ctrl" in e.modifiers


def test_events_are_frozen():
    e = PointerMove(pos=(5, 5))
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.pos = (0, 0)


def test_action_is_named():
    assert Action(name="close_lasso").name == "close_lasso"


def test_zoom_fields():
    z = Zoom(center=(100, 100), delta=1.5)
    assert z.center == (100, 100)
    assert z.delta == 1.5


# ---- keybindings ----


def test_keybinding_enter_closes_lasso():
    assert keybinding_for("enter", set()) == "close_lasso"


def test_keybinding_escape_cancels_lasso():
    assert keybinding_for("escape", set()) == "cancel_lasso"


def test_keybinding_ctrl_z_undo():
    assert keybinding_for("z", {"ctrl"}) == "undo"


def test_keybinding_ctrl_shift_z_redo():
    assert keybinding_for("z", {"ctrl", "shift"}) == "redo"


def test_keybinding_ctrl_s_save():
    assert keybinding_for("s", {"ctrl"}) == "save_all"


def test_keybinding_unknown_returns_none():
    assert keybinding_for("q", set()) is None


def test_keybinding_filters_extraneous_modifiers():
    """Irrelevant modifiers (like 'capslock') shouldn't break a match."""
    assert keybinding_for("enter", {"capslock"}) == "close_lasso"


def test_default_keybindings_dict_shape():
    for (key, mods), action in DEFAULT_KEYBINDINGS.items():
        assert isinstance(key, str)
        assert isinstance(mods, frozenset)
        assert isinstance(action, str)
