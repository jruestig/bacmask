"""Kivy mouse + keyboard → semantic InputEvents. See knowledge/016."""

from __future__ import annotations

from collections.abc import Callable

from .events import (
    Action,
    InputEvent,
    PointerDown,
    PointerMove,
    PointerUp,
    Zoom,
)

# Default keybindings: (key_name_lower, frozenset_of_modifiers) -> action_name.
# Override via config.yaml in a future iteration ([006]).
DEFAULT_KEYBINDINGS: dict[tuple[str, frozenset[str]], str] = {
    ("enter", frozenset()): "close_lasso",
    ("numpadenter", frozenset()): "close_lasso",
    ("escape", frozenset()): "cancel_lasso",
    ("delete", frozenset()): "delete_region",
    ("backspace", frozenset()): "delete_region",
    ("z", frozenset({"ctrl"})): "undo",
    ("z", frozenset({"ctrl", "shift"})): "redo",
    ("y", frozenset({"ctrl"})): "redo",
    ("s", frozenset({"ctrl"})): "save_all",
    ("o", frozenset({"ctrl"})): "load_image",
}


def keybinding_for(key: str, modifiers: set[str] | frozenset[str]) -> str | None:
    mods = frozenset(m for m in modifiers if m in ("ctrl", "shift", "alt", "meta"))
    return DEFAULT_KEYBINDINGS.get((key.lower(), mods))


class DesktopInputAdapter:
    """Translate Kivy touch + keyboard events into :mod:`bacmask.ui.input.events`.

    The ``emit`` callback receives one :class:`InputEvent` per semantic event.
    Mouse scroll becomes :class:`Zoom`; keyboard combos resolve via
    :data:`DEFAULT_KEYBINDINGS`.
    """

    def __init__(self, emit: Callable[[InputEvent], None]) -> None:
        self._emit = emit
        self._dragging = False

    # ---- Kivy touch events ---------------------------------------------------

    def on_touch_down(self, touch) -> bool:
        button = getattr(touch, "button", None)
        if button in ("scrollup", "scrolldown"):
            delta = 1.0 if button == "scrollup" else -1.0
            self._emit(Zoom(center=(touch.x, touch.y), delta=delta))
            return True
        self._dragging = True
        self._emit(PointerDown(pos=(touch.x, touch.y)))
        return True

    def on_touch_move(self, touch) -> bool:
        if not self._dragging:
            return False
        self._emit(PointerMove(pos=(touch.x, touch.y)))
        return True

    def on_touch_up(self, touch) -> bool:
        if not self._dragging:
            return False
        self._dragging = False
        self._emit(PointerUp(pos=(touch.x, touch.y)))
        return True

    # ---- Kivy keyboard events ------------------------------------------------

    def on_key_down(self, keyboard, keycode, text, modifiers) -> bool:
        key_name = keycode[1] if isinstance(keycode, tuple) else str(keycode)
        action_name = keybinding_for(key_name, set(modifiers))
        if action_name is not None:
            self._emit(Action(name=action_name))
            return True
        return False
