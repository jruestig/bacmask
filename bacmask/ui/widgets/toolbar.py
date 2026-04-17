"""Kivy toolbar: Load / Save All / Undo / Redo / Delete Selected."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button

from bacmask.services.mask_service import MaskService


class Toolbar(BoxLayout):
    def __init__(
        self,
        service: MaskService,
        on_load: Callable[[], None],
        on_save: Callable[[], None],
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", 40)
        kwargs.setdefault("spacing", 4)
        super().__init__(**kwargs)
        self.service = service

        self.add_widget(Button(text="Load Image", on_release=lambda *_: on_load()))
        self.add_widget(Button(text="Save All", on_release=lambda *_: on_save()))
        self.add_widget(Button(text="Undo", on_release=lambda *_: service.undo()))
        self.add_widget(Button(text="Redo", on_release=lambda *_: service.redo()))
        self.add_widget(Button(text="Delete Selected", on_release=lambda *_: self._delete()))
        self.add_widget(Button(text="Cancel Lasso", on_release=lambda *_: service.cancel_lasso()))

    def _delete(self) -> None:
        sid = self.service.state.selected_region_id
        if sid is None:
            return
        try:
            self.service.delete_region(sid)
        except KeyError:
            pass
