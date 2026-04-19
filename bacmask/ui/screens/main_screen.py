"""Main screen layout.

Stacked vertically:
1. Toolbar — action buttons + tool toggles + inline calibration on the right.
2. Brush panel — appears beneath the toolbar only when ``active_tool == "brush"``.
3. Body — image canvas + results table side by side.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kivy.uix.boxlayout import BoxLayout

from bacmask.services.mask_service import MaskService
from bacmask.ui.widgets.brush_panel import BrushPanel
from bacmask.ui.widgets.image_canvas import ImageCanvas
from bacmask.ui.widgets.results_table import ResultsTable
from bacmask.ui.widgets.toolbar import Toolbar


class MainScreen(BoxLayout):
    def __init__(
        self,
        service: MaskService,
        on_load: Callable[[], None],
        on_save: Callable[[], None],
        on_export: Callable[[], None],
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("orientation", "vertical")
        super().__init__(**kwargs)
        self.service = service

        self.add_widget(Toolbar(service, on_load=on_load, on_save=on_save, on_export=on_export))

        # Brush panel constructed eagerly; attached to the layout only while
        # the brush tool is active. Reusing the same instance preserves the
        # user's slider/text/mode state across tool switches.
        self._brush_panel = BrushPanel(service)
        self._brush_panel_attached = False

        body = BoxLayout(orientation="horizontal")
        self.canvas_widget = ImageCanvas(service)
        body.add_widget(self.canvas_widget)
        self.results = ResultsTable(service, size_hint_x=0.3)
        body.add_widget(self.results)
        self.add_widget(body)

        self._sync_brush_panel()
        service.subscribe(self._sync_brush_panel)

    def _sync_brush_panel(self) -> None:
        want = self.service.state.active_tool == "brush"
        if want == self._brush_panel_attached:
            return
        if want:
            # Insert between the toolbar (last-added → highest index in Kivy's
            # reverse-children ordering) and the body. ``index=1`` places the
            # panel just under the toolbar.
            self.add_widget(self._brush_panel, index=1)
        else:
            self.remove_widget(self._brush_panel)
        self._brush_panel_attached = want
