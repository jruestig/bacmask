"""Kivy toolbar: Load / Save / Export / Undo / Redo / Delete / Lasso / Brush + calibration.

Every button's label includes its keyboard shortcut — see [027 — Toolbar
Hotkey Labels](../../../knowledge/027-toolbar-hotkey-labels.md). Labels are
generated via :func:`bacmask.ui.input.desktop_adapter.button_label` so the
source of truth is the keybinding registry.

Calibration (mm/px + px/mm) sits at the right end of the toolbar so it's
always reachable. Brush-specific controls live in a separate
:class:`BrushPanel` row that :class:`MainScreen` reveals only when the brush
tool is active.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton

from bacmask.services.mask_service import MaskService
from bacmask.ui.input.desktop_adapter import button_label
from bacmask.ui.widgets.calibration_input import CalibrationInput

TOOLBAR_HEIGHT = 40


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

        # Tool toggles — exactly one is "down" at a time, mirroring active_tool.
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

        # Calibration sits right next to the Brush button. ``size_hint_y=1``
        # overrides the widget's standalone default so the inputs fill the
        # toolbar's full height.
        self.add_widget(CalibrationInput(service, size_hint=(None, 1), width=320))

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

    # ---- subscriber ---------------------------------------------------------

    def _refresh_tool_buttons(self) -> None:
        active = self.service.state.active_tool
        if active == "lasso":
            if self._lasso_btn.state != "down":
                self._lasso_btn.state = "down"
            if self._brush_btn.state != "normal":
                self._brush_btn.state = "normal"
        else:
            if self._brush_btn.state != "down":
                self._brush_btn.state = "down"
            if self._lasso_btn.state != "normal":
                self._lasso_btn.state = "normal"
