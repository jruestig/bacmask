"""Main screen layout: toolbar + calibration on top, canvas + results side-by-side."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kivy.uix.boxlayout import BoxLayout

from bacmask.services.mask_service import MaskService
from bacmask.ui.widgets.calibration_input import CalibrationInput
from bacmask.ui.widgets.image_canvas import ImageCanvas
from bacmask.ui.widgets.results_table import ResultsTable
from bacmask.ui.widgets.toolbar import Toolbar


class MainScreen(BoxLayout):
    def __init__(
        self,
        service: MaskService,
        on_load: Callable[[], None],
        on_save: Callable[[], None],
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("orientation", "vertical")
        super().__init__(**kwargs)
        self.service = service

        self.add_widget(Toolbar(service, on_load=on_load, on_save=on_save))
        self.add_widget(CalibrationInput(service))

        body = BoxLayout(orientation="horizontal")
        self.canvas_widget = ImageCanvas(service)
        body.add_widget(self.canvas_widget)
        self.results = ResultsTable(service, size_hint_x=0.3)
        body.add_widget(self.results)
        self.add_widget(body)
