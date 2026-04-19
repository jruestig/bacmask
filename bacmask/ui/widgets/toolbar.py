"""Kivy toolbar: Load / Save / Export / Undo / Redo / Delete / Lasso / Brush.

Every button's label includes its keyboard shortcut — see [027 — Toolbar
Hotkey Labels](../../../knowledge/027-toolbar-hotkey-labels.md). Labels are
generated via :func:`bacmask.ui.input.desktop_adapter.button_label` so the
source of truth is the keybinding registry; rebinding a key updates the label
automatically.

When the brush tool is active a contextual sub-section appears inline at the
right end of the toolbar with the brush radius slider and numeric input — same
height as the rest of the toolbar buttons. Hidden when the lasso is active.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

from bacmask.config import defaults
from bacmask.services.mask_service import MaskService
from bacmask.ui.input.desktop_adapter import button_label

TOOLBAR_HEIGHT = 40
SECTION_DIVIDER_WIDTH = 2
SECTION_DIVIDER_COLOR = (0.35, 0.35, 0.35, 1.0)


class Toolbar(BoxLayout):
    def __init__(
        self,
        service: MaskService,
        on_load: Callable[[], None],
        on_save: Callable[[], None],
        on_export: Callable[[], None],
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", TOOLBAR_HEIGHT)
        kwargs.setdefault("spacing", 4)
        super().__init__(**kwargs)
        self.service = service

        # ---- main section ---------------------------------------------------
        self.add_widget(
            Button(
                text=button_label("load_image", "Load Image"),
                on_release=lambda *_: on_load(),
            )
        )
        self.add_widget(
            Button(
                text=button_label("save_bundle", "Save"),
                on_release=lambda *_: on_save(),
            )
        )
        self.add_widget(
            Button(
                text=button_label("export_csv", "Export CSV"),
                on_release=lambda *_: on_export(),
            )
        )
        self.add_widget(
            Button(
                text=button_label("undo", "Undo"),
                on_release=lambda *_: service.undo(),
            )
        )
        self.add_widget(
            Button(
                text=button_label("redo", "Redo"),
                on_release=lambda *_: service.redo(),
            )
        )
        self.add_widget(
            Button(
                text=button_label("delete_region", "Delete Selected"),
                on_release=lambda *_: self._delete(),
            )
        )

        # ---- tool toggles ---------------------------------------------------
        # Exactly one is "down" at a time, mirroring active_tool.
        self._lasso_btn = ToggleButton(
            text=button_label("select_lasso", "Lasso"),
            group="bacmask_tool",
            allow_no_selection=False,
            state="down" if service.state.active_tool == "lasso" else "normal",
        )
        self._lasso_btn.bind(on_release=lambda *_: self._on_lasso_button())
        self.add_widget(self._lasso_btn)

        self._brush_btn = ToggleButton(
            text=button_label("select_brush", "Brush"),
            group="bacmask_tool",
            allow_no_selection=False,
            state="down" if service.state.active_tool == "brush" else "normal",
        )
        self._brush_btn.bind(on_release=lambda *_: self._on_brush_button())
        self.add_widget(self._brush_btn)

        # ---- brush context section -----------------------------------------
        self._brush_section = self._build_brush_section()
        self._brush_section_visible = False
        # Render initial state.
        self._refresh_tool_buttons()
        service.subscribe(self._refresh_tool_buttons)

    # ---- delete -------------------------------------------------------------

    def _delete(self) -> None:
        sid = self.service.state.selected_region_id
        if sid is None:
            return
        try:
            self.service.delete_region(sid)
        except KeyError:
            pass

    # ---- tool buttons -------------------------------------------------------

    def _on_lasso_button(self) -> None:
        self.service.set_active_tool("lasso")

    def _on_brush_button(self) -> None:
        self.service.set_active_tool("brush")

    # ---- brush context UI ---------------------------------------------------

    def _build_brush_section(self) -> BoxLayout:
        """Inline brush-controls section. Same height as toolbar buttons."""
        section = BoxLayout(
            orientation="horizontal",
            size_hint_x=None,
            width=320,
            spacing=4,
        )

        # Subtle vertical divider so the contextual section reads as a separate
        # group, not as more main buttons. Plain colored Widget keeps the
        # toolbar dependency-free of extra graphics.
        from kivy.graphics import Color, Rectangle

        divider = Widget(size_hint_x=None, width=SECTION_DIVIDER_WIDTH)
        with divider.canvas:
            Color(*SECTION_DIVIDER_COLOR)
            divider._rect = Rectangle(pos=divider.pos, size=divider.size)

        def _sync_div(*_a: Any) -> None:
            divider._rect.pos = divider.pos
            divider._rect.size = divider.size

        divider.bind(pos=_sync_div, size=_sync_div)
        section.add_widget(divider)

        section.add_widget(Label(text="Brush size", size_hint_x=None, width=80))

        radius_input = TextInput(
            text=str(self.service.state.brush_radius_px),
            multiline=False,
            input_filter="int",
            halign="right",
            size_hint_x=None,
            width=48,
            padding=[6, 8, 6, 0],
        )
        section.add_widget(radius_input)
        self._brush_radius_input = radius_input

        radius_slider = Slider(
            min=defaults.BRUSH_RADIUS_MIN_PX,
            max=defaults.BRUSH_RADIUS_MAX_PX,
            value=self.service.state.brush_radius_px,
            step=1,
        )
        section.add_widget(radius_slider)
        self._brush_radius_slider = radius_slider

        # Two-way binding: slider drag ↔ numeric input ↔ service.
        def _on_slider(_inst: Any, val: float) -> None:
            v = int(val)
            if radius_input.text != str(v):
                radius_input.text = str(v)
            try:
                self.service.set_brush_radius(v)
            except ValueError:
                pass

        def _on_text_validate(_inst: Any) -> None:
            txt = radius_input.text.strip()
            if not txt:
                return
            try:
                v = int(txt)
            except ValueError:
                return
            v = max(defaults.BRUSH_RADIUS_MIN_PX, min(defaults.BRUSH_RADIUS_MAX_PX, v))
            radius_input.text = str(v)
            radius_slider.value = v
            try:
                self.service.set_brush_radius(v)
            except ValueError:
                pass

        radius_slider.bind(value=_on_slider)
        radius_input.bind(on_text_validate=_on_text_validate)

        return section

    def _set_brush_section_visible(self, visible: bool) -> None:
        if visible == self._brush_section_visible:
            # Keep slider in sync with state even when already visible.
            self._sync_brush_controls_from_state()
            return
        if visible:
            self.add_widget(self._brush_section)
            self._sync_brush_controls_from_state()
        else:
            self.remove_widget(self._brush_section)
        self._brush_section_visible = visible

    def _sync_brush_controls_from_state(self) -> None:
        v = int(self.service.state.brush_radius_px)
        if int(self._brush_radius_slider.value) != v:
            self._brush_radius_slider.value = v
        if self._brush_radius_input.text != str(v):
            self._brush_radius_input.text = str(v)

    # ---- subscriber ---------------------------------------------------------

    def _refresh_tool_buttons(self) -> None:
        active = self.service.state.active_tool
        if active == "lasso":
            if self._lasso_btn.state != "down":
                self._lasso_btn.state = "down"
            if self._brush_btn.state != "normal":
                self._brush_btn.state = "normal"
            self._set_brush_section_visible(False)
        else:
            if self._brush_btn.state != "down":
                self._brush_btn.state = "down"
            if self._lasso_btn.state != "normal":
                self._lasso_btn.state = "normal"
            self._set_brush_section_visible(True)
