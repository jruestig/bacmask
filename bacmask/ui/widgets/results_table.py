"""Kivy results table: scrollable list of region_id | name | area_px | area_mm²."""

from __future__ import annotations

from typing import Any

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from bacmask.services.mask_service import MaskService


class ResultsTable(BoxLayout):
    def __init__(self, service: MaskService, **kwargs: Any) -> None:
        kwargs.setdefault("orientation", "vertical")
        super().__init__(**kwargs)
        self.service = service

        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=24)
        for text in ("ID", "Name", "px", "mm²"):
            header.add_widget(Label(text=text, bold=True))
        self.add_widget(header)

        self.rows_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=1)
        self.rows_box.bind(minimum_height=self.rows_box.setter("height"))

        scroll = ScrollView()
        scroll.add_widget(self.rows_box)
        self.add_widget(scroll)

        service.subscribe(self._refresh)

    def _refresh(self) -> None:
        self.rows_box.clear_widgets()
        selected = self.service.state.selected_region_id
        for row in self.service.compute_area_rows():
            bg = (0.2, 0.3, 0.4, 1) if row.region_id == selected else (0, 0, 0, 0)
            box = _Row(row.region_id, self.service, bg=bg)
            box.add_widget(Label(text=str(row.region_id)))
            box.add_widget(Label(text=row.region_name))
            box.add_widget(Label(text=str(row.area_px)))
            mm2_text = "" if row.area_mm2 is None else f"{row.area_mm2:.4f}"
            box.add_widget(Label(text=mm2_text))
            self.rows_box.add_widget(box)


class _Row(BoxLayout):
    def __init__(self, region_id: int, service: MaskService, bg, **kwargs: Any) -> None:
        from kivy.graphics import Color, Rectangle  # local import to avoid top-level dep

        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", 24)
        super().__init__(**kwargs)
        self.region_id = region_id
        self.service = service

        with self.canvas.before:
            Color(*bg)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_bg, size=self._sync_bg)

    def _sync_bg(self, *_: Any) -> None:
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def on_touch_down(self, touch) -> bool:
        if self.collide_point(*touch.pos):
            try:
                self.service.select_region(self.region_id)
            except KeyError:
                pass
            return True
        return False
