import dataclasses
from types import SimpleNamespace

import pytest

from bacmask.ui.input.desktop_adapter import (
    DEFAULT_KEYBINDINGS,
    DesktopInputAdapter,
    button_label,
    keybinding_for,
    label_for_action,
)
from bacmask.ui.input.events import (
    Action,
    Pan,
    PointerDown,
    PointerMove,
    PointerUp,
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


def test_keybinding_escape_cancels_stroke():
    assert keybinding_for("escape", set()) == "cancel_stroke"


def test_keybinding_l_selects_lasso():
    assert keybinding_for("l", set()) == "select_lasso"


def test_keybinding_b_selects_brush():
    assert keybinding_for("b", set()) == "select_brush"


def test_keybinding_e_alone_unbound():
    """`e` alone was previously toggle_edit_mode (knowledge/026 supersedes 023);
    it is now intentionally unbound to keep discoverability honest."""
    assert keybinding_for("e", set()) is None


def test_keybinding_ctrl_z_undo():
    assert keybinding_for("z", {"ctrl"}) == "undo"


def test_keybinding_ctrl_shift_z_redo():
    assert keybinding_for("z", {"ctrl", "shift"}) == "redo"


def test_keybinding_ctrl_s_save_bundle():
    assert keybinding_for("s", {"ctrl"}) == "save_bundle"


def test_keybinding_ctrl_e_export_csv():
    assert keybinding_for("e", {"ctrl"}) == "export_csv"


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


# ---- label_for_action / button_label (knowledge/027) ----


def test_label_for_action_save_is_ctrl_s():
    assert label_for_action("save_bundle") == "Ctrl+S"


def test_label_for_action_undo_is_ctrl_z():
    assert label_for_action("undo") == "Ctrl+Z"


def test_label_for_action_redo_prefers_ctrl_y_over_ctrl_shift_z():
    """Redo has two bindings (Ctrl+Y and Ctrl+Shift+Z). The canonical binding
    is the first one listed in DEFAULT_KEYBINDINGS — Ctrl+Y — because it's
    shorter and more common. Reordering the dict controls this."""
    assert label_for_action("redo") == "Ctrl+Y"


def test_label_for_action_delete_prefers_del_over_backspace():
    assert label_for_action("delete_region") == "Del"


def test_label_for_action_escape_renders_as_esc():
    assert label_for_action("cancel_stroke") == "Esc"


def test_label_for_action_enter_renders_as_enter():
    assert label_for_action("close_lasso") == "Enter"


def test_label_for_action_bare_letter_uppercased():
    assert label_for_action("select_brush") == "B"


def test_label_for_action_unknown_returns_none():
    assert label_for_action("not_a_real_action") is None


def test_button_label_composes_base_with_shortcut():
    assert button_label("save_bundle", "Save") == "Save (Ctrl+S)"


def test_button_label_no_shortcut_returns_base_unchanged():
    assert button_label("unbound_action", "Whatever") == "Whatever"


# ---- DesktopInputAdapter emissions ----


def _touch(x: float, y: float, button: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(x=x, y=y, pos=(x, y), button=button)


def test_adapter_left_drag_emits_pointer_sequence():
    events = []
    adapter = DesktopInputAdapter(emit=events.append)
    assert adapter.on_touch_down(_touch(5, 5, button="left")) is True
    assert adapter.on_touch_move(_touch(10, 12, button="left")) is True
    assert adapter.on_touch_up(_touch(10, 12, button="left")) is True
    kinds = [type(e) for e in events]
    assert kinds == [PointerDown, PointerMove, PointerUp]
    assert events[0].pos == (5, 5)
    assert events[1].pos == (10, 12)
    assert events[2].pos == (10, 12)


def test_adapter_scroll_emits_zoom_up_and_down():
    events = []
    adapter = DesktopInputAdapter(emit=events.append)
    adapter.on_touch_down(_touch(40, 60, button="scrollup"))
    adapter.on_touch_down(_touch(40, 60, button="scrolldown"))
    zooms = [e for e in events if isinstance(e, Zoom)]
    assert len(zooms) == 2
    assert zooms[0].center == (40, 60)
    assert zooms[0].delta > 0
    assert zooms[1].delta < 0


def test_adapter_middle_drag_emits_pan():
    events = []
    adapter = DesktopInputAdapter(emit=events.append)
    adapter.on_touch_down(_touch(100, 100, button="middle"))
    adapter.on_touch_move(_touch(115, 90, button="middle"))
    adapter.on_touch_move(_touch(115, 80, button="middle"))
    adapter.on_touch_up(_touch(115, 80, button="middle"))
    pans = [e for e in events if isinstance(e, Pan)]
    assert len(pans) == 2
    assert pans[0].delta == pytest.approx((15, -10))
    assert pans[1].delta == pytest.approx((0, -10))
    # Middle-drag must not emit PointerDown/Move/Up.
    assert not any(isinstance(e, (PointerDown, PointerMove, PointerUp)) for e in events)


def test_adapter_middle_drag_does_not_interfere_with_later_left_drag():
    events = []
    adapter = DesktopInputAdapter(emit=events.append)
    adapter.on_touch_down(_touch(0, 0, button="middle"))
    adapter.on_touch_move(_touch(5, 5, button="middle"))
    adapter.on_touch_up(_touch(5, 5, button="middle"))
    events.clear()
    adapter.on_touch_down(_touch(10, 10, button="left"))
    adapter.on_touch_move(_touch(12, 12, button="left"))
    adapter.on_touch_up(_touch(12, 12, button="left"))
    kinds = [type(e) for e in events]
    assert kinds == [PointerDown, PointerMove, PointerUp]
