"""Kivy toolbar: Data menu / Undo / Redo / Delete / Lasso / Brush + calibration.

Load, Save, and Export CSV are grouped under a single ``Data`` dropdown to
keep the top row compact. Every action button's label still includes its
keyboard shortcut — see
[027 — Toolbar Hotkey Labels](../../../knowledge/027-toolbar-hotkey-labels.md).
Labels are generated via :func:`bacmask.ui.input.desktop_adapter.button_label`
so the source of truth is the keybinding registry.

Calibration (mm/px + px/mm) sits at the right end of the toolbar so it's
always reachable. Brush-specific controls live in a separate
:class:`BrushPanel` row that :class:`MainScreen` reveals only when the brush
tool is active.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.togglebutton import ToggleButton

from bacmask.services.mask_service import MaskService
from bacmask.ui.input.desktop_adapter import button_label
from bacmask.ui.widgets.calibration_input import CalibrationInput

TOOLBAR_HEIGHT = 40
DATA_MENU_ITEM_HEIGHT = 40
DATA_MENU_WIDTH = 200


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

        self._data_menu = self._build_data_menu(on_load, on_save, on_export)
        data_btn = Button(text="Data", size_hint_x=None, width=dp(DATA_MENU_WIDTH))
        data_btn.bind(on_release=self._data_menu.open)
        self._data_menu.bind(
            on_select=lambda _instance, action: self._dispatch_data_action(
                action, on_load, on_save, on_export
            )
        )
        self.add_widget(data_btn)
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

        self._line_btn = ToggleButton(
            text=button_label("select_line", "Line"),
            group="bacmask_tool",
            allow_no_selection=False,
            state="down" if service.state.active_tool == "line" else "normal",
        )
        self._line_btn.bind(on_release=lambda *_: self._on_line_button())
        self.add_widget(self._line_btn)

        # Calibration sits right next to the Brush button. ``size_hint_y=1``
        # overrides the widget's standalone default so the inputs fill the
        # toolbar's full height.
        self.add_widget(CalibrationInput(service, size_hint=(None, 1), width=dp(300)))

        service.subscribe(self._refresh_tool_buttons)

    # ---- data menu ----------------------------------------------------------

    def _build_data_menu(
        self,
        on_load: Callable[[], None],
        on_save: Callable[[], None],
        on_export: Callable[[], None],
    ) -> DropDown:
        menu = DropDown(auto_width=False, width=dp(DATA_MENU_WIDTH))
        for action, text in (
            ("load_image", "Load Image"),
            ("save_bundle", "Save"),
            ("export_csv", "Export CSV"),
        ):
            item = Button(
                text=button_label(action, text),
                size_hint_y=None,
                height=dp(DATA_MENU_ITEM_HEIGHT),
            )
            item.bind(on_release=lambda btn, a=action: menu.select(a))
            menu.add_widget(item)
        return menu

    @staticmethod
    def _dispatch_data_action(
        action: str,
        on_load: Callable[[], None],
        on_save: Callable[[], None],
        on_export: Callable[[], None],
    ) -> None:
        if action == "load_image":
            on_load()
        elif action == "save_bundle":
            on_save()
        elif action == "export_csv":
            on_export()

    # ---- delete -------------------------------------------------------------

    def _delete(self) -> None:
        # Mirrors the Del/Backspace key handler in ``app._run_action`` — line
        # selection wins because it requires an explicit results-panel click,
        # while a region selection can linger from a prior canvas tap.
        line_id = self.service.state.selected_line_id
        if line_id is not None:
            try:
                self.service.delete_line(line_id)
            except KeyError:
                pass
            return
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

    def _on_line_button(self) -> None:
        self.service.set_active_tool("line")

    # ---- subscriber ---------------------------------------------------------

    def _refresh_tool_buttons(self) -> None:
        active = self.service.state.active_tool
        for tool, btn in (
            ("lasso", self._lasso_btn),
            ("brush", self._brush_btn),
            ("line", self._line_btn),
        ):
            wanted = "down" if active == tool else "normal"
            if btn.state != wanted:
                btn.state = wanted
