"""Contextual brush controls — appears below the toolbar when the brush is active.

Layout (left → right):
``Brush size`` label · numeric input · slider · ``Create`` · ``Add`` ·
``Subtract`` toggle.

The toggles drive ``state.brush_default_mode``. Tab cycles the modes in the
order Create → Add → Subtract → Create. There is no modifier-key override —
the toggle is the mode.
"""

from __future__ import annotations

from typing import Any

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from bacmask.config import defaults
from bacmask.services.mask_service import MaskService

PANEL_HEIGHT = 40


class BrushPanel(BoxLayout):
    def __init__(self, service: MaskService, **kwargs: Any) -> None:
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", PANEL_HEIGHT)
        kwargs.setdefault("spacing", 4)
        super().__init__(**kwargs)
        self.service = service

        # ---- size group ----------------------------------------------------
        self.add_widget(Label(text="Brush size", size_hint_x=None, width=80))
        self._size_input = TextInput(
            text=str(service.state.brush_radius_px),
            multiline=False,
            input_filter="int",
            halign="right",
            size_hint_x=None,
            width=56,
            padding=[6, 8, 6, 0],
        )
        self.add_widget(self._size_input)

        self._size_slider = Slider(
            min=defaults.BRUSH_RADIUS_MIN_PX,
            max=defaults.BRUSH_RADIUS_MAX_PX,
            value=service.state.brush_radius_px,
            step=1,
        )
        self.add_widget(self._size_slider)

        self._size_slider.bind(value=self._on_slider)
        self._size_input.bind(on_text_validate=self._on_text_validate)

        # ---- mode toggles --------------------------------------------------
        # Order matches the Tab cycle in MaskService.toggle_brush_default_mode:
        # Create → Add → Subtract.
        cur_mode = service.state.brush_default_mode
        self._mode_btns: dict[str, ToggleButton] = {}
        for mode, label, width in (
            ("create", "Create (Tab)", 140),
            ("add", "Add (Tab)", 110),
            ("subtract", "Subtract (Tab)", 140),
        ):
            btn = ToggleButton(
                text=label,
                group="bacmask_brush_mode",
                allow_no_selection=False,
                state="down" if cur_mode == mode else "normal",
                size_hint_x=None,
                width=width,
            )
            # Bind via default arg so the closure captures the mode value, not
            # the loop variable (Python late-binding gotcha).
            btn.bind(on_release=lambda *_a, m=mode: self._on_mode(m))
            self.add_widget(btn)
            self._mode_btns[mode] = btn

        service.subscribe(self._sync_from_state)

    # ---- size handlers -----------------------------------------------------

    def _on_slider(self, _inst: Any, val: float) -> None:
        v = int(val)
        if self._size_input.text != str(v):
            self._size_input.text = str(v)
        try:
            self.service.set_brush_radius(v)
        except ValueError:
            pass

    def _on_text_validate(self, _inst: Any) -> None:
        txt = self._size_input.text.strip()
        if not txt:
            return
        try:
            v = int(txt)
        except ValueError:
            return
        v = max(defaults.BRUSH_RADIUS_MIN_PX, min(defaults.BRUSH_RADIUS_MAX_PX, v))
        self._size_input.text = str(v)
        self._size_slider.value = v
        try:
            self.service.set_brush_radius(v)
        except ValueError:
            pass

    # ---- mode handlers -----------------------------------------------------

    def _on_mode(self, mode: str) -> None:
        try:
            self.service.set_brush_default_mode(mode)
        except ValueError:
            pass

    # ---- subscriber --------------------------------------------------------

    def _sync_from_state(self) -> None:
        state = self.service.state
        v = int(state.brush_radius_px)
        if int(self._size_slider.value) != v:
            self._size_slider.value = v
        if self._size_input.text != str(v):
            self._size_input.text = str(v)
        for mode, btn in self._mode_btns.items():
            want = "down" if state.brush_default_mode == mode else "normal"
            if btn.state != want:
                btn.state = want
