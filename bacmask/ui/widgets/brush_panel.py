"""Contextual brush controls — appears below the toolbar when the brush is active.

Layout (left → right):
``Brush size`` label · numeric input · slider · ``Add`` toggle · ``Subtract``
toggle.

The toggles drive ``state.brush_default_mode``. Tab flips between them. There
is no modifier-key override — the toggle is the mode.
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
        self._add_btn = ToggleButton(
            text="Add (Tab)",
            group="bacmask_brush_mode",
            allow_no_selection=False,
            state="down" if service.state.brush_default_mode == "add" else "normal",
            size_hint_x=None,
            width=120,
        )
        self._add_btn.bind(on_release=lambda *_: self._on_mode("add"))
        self.add_widget(self._add_btn)

        self._sub_btn = ToggleButton(
            text="Subtract (Tab)",
            group="bacmask_brush_mode",
            allow_no_selection=False,
            state="down" if service.state.brush_default_mode == "subtract" else "normal",
            size_hint_x=None,
            width=140,
        )
        self._sub_btn.bind(on_release=lambda *_: self._on_mode("subtract"))
        self.add_widget(self._sub_btn)

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
        if state.brush_default_mode == "add":
            if self._add_btn.state != "down":
                self._add_btn.state = "down"
            if self._sub_btn.state != "normal":
                self._sub_btn.state = "normal"
        else:
            if self._sub_btn.state != "down":
                self._sub_btn.state = "down"
            if self._add_btn.state != "normal":
                self._add_btn.state = "normal"
