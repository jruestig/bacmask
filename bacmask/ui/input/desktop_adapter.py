"""Kivy mouse + keyboard → semantic InputEvents. See knowledge/016."""

from __future__ import annotations

from collections.abc import Callable

from .events import (
    Action,
    InputEvent,
    Pan,
    PointerDown,
    PointerMove,
    PointerUp,
    Zoom,
)

# Default keybindings: (key_name_lower, frozenset_of_modifiers) -> action_name.
# Insertion order matters: when an action has multiple bindings, the *first*
# entry for that action is the canonical one used in toolbar labels ([027]).
# Override via config.yaml in a future iteration ([006]).
DEFAULT_KEYBINDINGS: dict[tuple[str, frozenset[str]], str] = {
    ("enter", frozenset()): "close_lasso",
    ("numpadenter", frozenset()): "close_lasso",
    ("escape", frozenset()): "cancel_stroke",
    ("delete", frozenset()): "delete_region",
    ("backspace", frozenset()): "delete_region",
    ("z", frozenset({"ctrl"})): "undo",
    ("y", frozenset({"ctrl"})): "redo",
    ("z", frozenset({"ctrl", "shift"})): "redo",
    ("s", frozenset({"ctrl"})): "save_bundle",
    ("e", frozenset({"ctrl"})): "export_csv",
    ("o", frozenset({"ctrl"})): "load_image",
    ("l", frozenset()): "select_lasso",
    ("b", frozenset()): "select_brush",
}

_TRACKED_MODIFIERS = ("ctrl", "shift", "alt", "meta")


def _filter_modifiers(modifiers) -> tuple[str, ...]:
    return tuple(m for m in _TRACKED_MODIFIERS if m in modifiers)


def _window_modifiers() -> tuple[str, ...]:
    """Read the live modifier set from Kivy's Window, if available.

    Returns an empty tuple when Kivy isn't initialized (tests, headless use).
    Kivy maintains ``Window.modifiers`` as the authoritative live keyboard
    state and updates it before dispatching touch events, regardless of who
    owns the ``on_key_down`` callback.
    """
    try:
        from kivy.core.window import Window  # local import: kivy may be absent in tests
    except Exception:
        return ()
    raw = getattr(Window, "modifiers", None)
    if not raw:
        return ()
    return tuple(raw)


def keybinding_for(key: str, modifiers: set[str] | frozenset[str]) -> str | None:
    mods = frozenset(_filter_modifiers(modifiers))
    return DEFAULT_KEYBINDINGS.get((key.lower(), mods))


# Display names for keys that shouldn't render via ``str.upper()``.
_KEY_DISPLAY: dict[str, str] = {
    "enter": "Enter",
    "numpadenter": "NumEnter",
    "escape": "Esc",
    "delete": "Del",
    "backspace": "Backspace",
}

# Ordered list — modifiers render in this order regardless of set iteration.
_MODIFIER_ORDER: tuple[str, ...] = ("ctrl", "shift", "alt", "meta")
_MODIFIER_DISPLAY: dict[str, str] = {
    "ctrl": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
    "meta": "Meta",
}


def label_for_action(action: str) -> str | None:
    """Render the canonical shortcut for ``action`` as a display string, e.g.
    ``"Ctrl+S"`` or ``"Del"``. Returns ``None`` if the action has no binding.

    The canonical binding is the first entry matching ``action`` in
    :data:`DEFAULT_KEYBINDINGS` — so reordering that dict controls which
    binding appears in toolbar labels ([027]).
    """
    for (key, mods), act in DEFAULT_KEYBINDINGS.items():
        if act != action:
            continue
        parts = [_MODIFIER_DISPLAY[m] for m in _MODIFIER_ORDER if m in mods]
        parts.append(_KEY_DISPLAY.get(key, key.upper() if len(key) == 1 else key.capitalize()))
        return "+".join(parts)
    return None


def button_label(action: str, base_text: str) -> str:
    """Compose ``"<base_text> (<shortcut>)"`` for buttons bound to ``action``.

    If ``action`` has no keybinding, returns ``base_text`` unchanged. Used by
    the toolbar per [027 — Toolbar Hotkey Labels](../../knowledge/027-toolbar-hotkey-labels.md).
    """
    sc = label_for_action(action)
    return f"{base_text} ({sc})" if sc else base_text


class DesktopInputAdapter:
    """Translate Kivy touch + keyboard events into :mod:`bacmask.ui.input.events`.

    The ``emit`` callback receives one :class:`InputEvent` per semantic event.
    Mouse scroll becomes :class:`Zoom`; middle-mouse drag becomes :class:`Pan`;
    keyboard combos resolve via :data:`DEFAULT_KEYBINDINGS`.
    """

    def __init__(self, emit: Callable[[InputEvent], None]) -> None:
        self._emit = emit
        # One of: None, "pointer", "pan".
        self._drag_mode: str | None = None
        self._last_pan_pos: tuple[float, float] | None = None
        # Modifier state — Kivy touches do not reliably carry modifiers, so we
        # mirror them from on_key_down/on_key_up and stamp PointerDown ourselves.
        self._modifiers: set[str] = set()

    # ---- Kivy touch events ---------------------------------------------------

    def on_touch_down(self, touch) -> bool:
        button = getattr(touch, "button", None)
        if button in ("scrollup", "scrolldown"):
            delta = 1.0 if button == "scrollup" else -1.0
            self._emit(Zoom(center=(touch.x, touch.y), delta=delta))
            return True
        if button == "middle":
            self._drag_mode = "pan"
            self._last_pan_pos = (touch.x, touch.y)
            return True
        self._drag_mode = "pointer"
        # Source modifiers in priority order:
        #   1) the touch itself (some Kivy backends populate ``touch.modifiers``)
        #   2) Kivy's Window.modifiers (authoritative — Kivy updates this from
        #      keyboard events even when our App owns the Window.on_key_down
        #      callback, which the adapter's own on_key_down would otherwise miss)
        #   3) the adapter's local mirror, if both above are empty
        touch_mods = getattr(touch, "modifiers", None)
        if touch_mods:
            mods = _filter_modifiers(touch_mods)
        else:
            win_mods = _window_modifiers()
            mods = _filter_modifiers(win_mods if win_mods else self._modifiers)
        self._emit(
            PointerDown(
                pos=(touch.x, touch.y),
                modifiers=mods,
                is_double=bool(getattr(touch, "is_double_tap", False)),
            )
        )
        return True

    def on_touch_move(self, touch) -> bool:
        if self._drag_mode == "pointer":
            self._emit(PointerMove(pos=(touch.x, touch.y)))
            return True
        if self._drag_mode == "pan":
            last = self._last_pan_pos or (touch.x, touch.y)
            dx = touch.x - last[0]
            dy = touch.y - last[1]
            self._last_pan_pos = (touch.x, touch.y)
            self._emit(Pan(delta=(dx, dy)))
            return True
        return False

    def on_touch_up(self, touch) -> bool:
        if self._drag_mode == "pointer":
            self._drag_mode = None
            self._emit(PointerUp(pos=(touch.x, touch.y)))
            return True
        if self._drag_mode == "pan":
            self._drag_mode = None
            self._last_pan_pos = None
            return True
        return False

    # ---- Kivy keyboard events ------------------------------------------------

    def on_key_down(self, keyboard, keycode, text, modifiers) -> bool:
        key_name = keycode[1] if isinstance(keycode, tuple) else str(keycode)
        self._update_modifier(key_name, pressed=True)
        action_name = keybinding_for(key_name, set(modifiers))
        if action_name is not None:
            self._emit(Action(name=action_name))
            return True
        return False

    def on_key_up(self, keyboard, keycode) -> bool:
        key_name = keycode[1] if isinstance(keycode, tuple) else str(keycode)
        self._update_modifier(key_name, pressed=False)
        return False

    def _update_modifier(self, key_name: str, pressed: bool) -> None:
        kn = key_name.lower()
        mod = None
        if kn in ("lctrl", "rctrl", "ctrl"):
            mod = "ctrl"
        elif kn in ("lshift", "rshift", "shift"):
            mod = "shift"
        elif kn in ("lalt", "ralt", "alt"):
            mod = "alt"
        elif kn in ("lmeta", "rmeta", "meta", "super"):
            mod = "meta"
        if mod is None:
            return
        if pressed:
            self._modifiers.add(mod)
        else:
            self._modifiers.discard(mod)
