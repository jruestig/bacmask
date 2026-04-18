"""Kivy toolbar: Load / Save / Export / Undo / Redo / Delete / Edit."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton

from bacmask.services.mask_service import MaskService


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
        kwargs.setdefault("height", 40)
        kwargs.setdefault("spacing", 4)
        super().__init__(**kwargs)
        self.service = service

        self.add_widget(Button(text="Load Image", on_release=lambda *_: on_load()))
        self.add_widget(Button(text="Save", on_release=lambda *_: on_save()))
        self.add_widget(Button(text="Export CSV", on_release=lambda *_: on_export()))
        self.add_widget(Button(text="Undo", on_release=lambda *_: service.undo()))
        self.add_widget(Button(text="Redo", on_release=lambda *_: service.redo()))
        self.add_widget(Button(text="Delete Selected", on_release=lambda *_: self._delete()))
        self.add_widget(Button(text="Cancel Lasso", on_release=lambda *_: service.cancel_lasso()))

        self._edit_btn = ToggleButton(text="Edit", state="normal")
        self._edit_btn.bind(on_release=lambda *_: self._on_edit_button())
        self.add_widget(self._edit_btn)
        service.subscribe(self._refresh_edit_button)

    def _delete(self) -> None:
        sid = self.service.state.selected_region_id
        if sid is None:
            return
        try:
            self.service.delete_region(sid)
        except KeyError:
            pass

    def _on_edit_button(self) -> None:
        # ToggleButton already flipped its visual state — align service to the
        # button's new state so state.edit_mode is the source of truth.
        self.service.set_edit_mode(self._edit_btn.state == "down")

    def _refresh_edit_button(self) -> None:
        desired = "down" if self.service.state.edit_mode else "normal"
        if self._edit_btn.state != desired:
            self._edit_btn.state = desired
