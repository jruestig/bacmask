"""Kivy results table: scrollable list of region_id | name | area_px | area_mm².

Measurement lines are appended below the regions section as a separate group:
``L<id> | name | length_px | <blank>``. Lines are persisted in the bundle's
meta.json and exported to a sibling ``<stem>_lines.csv`` next to the areas
CSV; here in the panel the mm² column stays empty for line rows because they
report length, not area.
"""

from __future__ import annotations

from typing import Any

from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from bacmask.services.mask_service import MaskService


class ResultsTable(BoxLayout):
    def __init__(self, service: MaskService, **kwargs: Any) -> None:
        kwargs.setdefault("orientation", "vertical")
        super().__init__(**kwargs)
        self.service = service
        # Gate the (relatively expensive) row rebuild on the same
        # ``regions_version`` counter the canvas uses for its overlay texture.
        # Brush-stroke notifies fire many times per second but never bump
        # ``regions_version`` until commit — without this gate we'd rebuild
        # every Label on every PointerMove. Selection changes also need a
        # repaint (background tint), so we track that separately.
        self._last_regions_version: int = -1
        self._last_lines_version: int = -1
        self._last_selected: int | None = None
        self._last_selected_line: int | None = None
        self._last_scale: float | None = None

        # Per-region row widgets, keyed by region id. Refresh diffs against
        # this dict and adds/removes/mutates widgets in place — the previous
        # implementation did ``clear_widgets()`` + N fresh widget creations
        # per notify, which costs O(N) widget lifecycle churn per edit and
        # dominated the perceived slowdown past ~100 regions.
        self._rows: dict[int, _Row] = {}
        self._line_rows: dict[int, _LineRow] = {}

        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=24)
        for text in ("ID", "Name", "px", "mm²"):
            header.add_widget(Label(text=text, bold=True))
        self.add_widget(header)

        self.rows_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=1)
        self.rows_box.bind(minimum_height=self.rows_box.setter("height"))

        scroll = ScrollView()
        scroll.add_widget(self.rows_box)
        self.add_widget(scroll)

        service.subscribe(self._on_state_changed)

    def _on_state_changed(self) -> None:
        state = self.service.state
        if (
            state.regions_version == self._last_regions_version
            and state.lines_version == self._last_lines_version
            and state.selected_region_id == self._last_selected
            and state.selected_line_id == self._last_selected_line
            and state.scale_mm_per_px == self._last_scale
        ):
            return
        version_changed = state.regions_version != self._last_regions_version
        lines_changed = state.lines_version != self._last_lines_version
        selection_changed = state.selected_region_id != self._last_selected
        line_selection_changed = state.selected_line_id != self._last_selected_line
        scale_changed = state.scale_mm_per_px != self._last_scale
        self._last_regions_version = state.regions_version
        self._last_lines_version = state.lines_version
        self._last_selected = state.selected_region_id
        self._last_selected_line = state.selected_line_id
        self._last_scale = state.scale_mm_per_px

        if version_changed or scale_changed:
            self._refresh_rows()
        if lines_changed:
            self._refresh_line_rows()
        if selection_changed:
            self._refresh_selection()
        if line_selection_changed:
            self._refresh_line_selection()

    # ---- incremental refresh ------------------------------------------------

    def _refresh_rows(self) -> None:
        """Sync rows to the current region set.

        Adds widgets for newly-created ids (new regions always have the highest
        id, so the append order matches the existing sort), removes widgets for
        deleted ids, and mutates Label text for any row whose data changed.
        Only rows that actually differ pay a widget update cost.
        """
        selected = self.service.state.selected_region_id
        rows_data = self.service.compute_area_rows()
        current_ids = {r.region_id for r in rows_data}

        # Remove rows for deleted ids (iterate a list copy — we mutate the dict).
        for stale_id in [rid for rid in self._rows if rid not in current_ids]:
            self.rows_box.remove_widget(self._rows.pop(stale_id))

        # Add/update rows in id order so the box layout stays sorted.
        for row in rows_data:
            widget = self._rows.get(row.region_id)
            mm2_text = "" if row.area_mm2 is None else f"{row.area_mm2:.4f}"
            if widget is None:
                widget = _Row(row.region_id, self.service)
                widget.set_cells(row.region_name, row.area_px, mm2_text)
                widget.set_selected(row.region_id == selected)
                self._rows[row.region_id] = widget
                self.rows_box.add_widget(widget)
            else:
                widget.set_cells(row.region_name, row.area_px, mm2_text)
                widget.set_selected(row.region_id == selected)

    def _refresh_selection(self) -> None:
        """Update just the background tints — no widget churn, no label rebuild.

        Fires on selection-only notifies (clicks in the canvas, arrow-key nav).
        """
        selected = self.service.state.selected_region_id
        for region_id, widget in self._rows.items():
            widget.set_selected(region_id == selected)

    def _refresh_line_rows(self) -> None:
        """Sync line rows below the regions block. Same diff-and-mutate strategy
        as :meth:`_refresh_rows` so existing widgets aren't torn down on every
        line add or delete.
        """
        selected_line = self.service.state.selected_line_id
        rows_data = self.service.compute_line_rows()
        current_ids = {row["line_id"] for row in rows_data}

        for stale_id in [lid for lid in self._line_rows if lid not in current_ids]:
            self.rows_box.remove_widget(self._line_rows.pop(stale_id))

        for row in rows_data:
            line_id = row["line_id"]
            widget = self._line_rows.get(line_id)
            length_text = f"{row['length_px']:.1f}"
            if widget is None:
                widget = _LineRow(line_id, self.service)
                widget.set_cells(row["name"], length_text)
                widget.set_selected(line_id == selected_line)
                self._line_rows[line_id] = widget
                self.rows_box.add_widget(widget)
            else:
                widget.set_cells(row["name"], length_text)
                widget.set_selected(line_id == selected_line)

    def _refresh_line_selection(self) -> None:
        selected = self.service.state.selected_line_id
        for line_id, widget in self._line_rows.items():
            widget.set_selected(line_id == selected)


_SELECTED_BG = (0.2, 0.3, 0.4, 1.0)
_UNSELECTED_BG = (0.0, 0.0, 0.0, 0.0)


class _Row(BoxLayout):
    def __init__(self, region_id: int, service: MaskService, **kwargs: Any) -> None:
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", 24)
        super().__init__(**kwargs)
        self.region_id = region_id
        self.service = service

        with self.canvas.before:
            self._bg_color = Color(*_UNSELECTED_BG)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_bg, size=self._sync_bg)

        # Labels retained as attributes so refresh just mutates ``.text``
        # instead of tearing down and recreating the widget tree.
        self._id_label = Label(text=str(region_id))
        self._name_label = Label(text="")
        self._px_label = Label(text="")
        self._mm2_label = Label(text="")
        self.add_widget(self._id_label)
        self.add_widget(self._name_label)
        self.add_widget(self._px_label)
        self.add_widget(self._mm2_label)

    def set_cells(self, name: str, area_px: int, mm2_text: str) -> None:
        """Mutate label text in place — no-op if unchanged so Kivy's texture
        cache stays warm across brush strokes that don't actually move pixels.
        """
        px_text = str(area_px)
        if self._name_label.text != name:
            self._name_label.text = name
        if self._px_label.text != px_text:
            self._px_label.text = px_text
        if self._mm2_label.text != mm2_text:
            self._mm2_label.text = mm2_text

    def set_selected(self, selected: bool) -> None:
        rgba = _SELECTED_BG if selected else _UNSELECTED_BG
        if tuple(self._bg_color.rgba) != rgba:
            self._bg_color.rgba = rgba

    def _sync_bg(self, *_: Any) -> None:
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def on_touch_down(self, touch) -> bool:
        if self.collide_point(*touch.pos):
            try:
                self.service.select_region(self.region_id)
            except KeyError:
                pass
            self.service.clear_line_selection()
            return True
        return False


class _LineRow(BoxLayout):
    def __init__(self, line_id: int, service: MaskService, **kwargs: Any) -> None:
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", 24)
        super().__init__(**kwargs)
        self.line_id = line_id
        self.service = service

        with self.canvas.before:
            self._bg_color = Color(*_UNSELECTED_BG)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_bg, size=self._sync_bg)

        self._id_label = Label(text=f"L{line_id}")
        self._name_label = Label(text="")
        self._px_label = Label(text="")
        self._mm2_label = Label(text="")
        self.add_widget(self._id_label)
        self.add_widget(self._name_label)
        self.add_widget(self._px_label)
        self.add_widget(self._mm2_label)

    def set_cells(self, name: str, length_text: str) -> None:
        if self._name_label.text != name:
            self._name_label.text = name
        if self._px_label.text != length_text:
            self._px_label.text = length_text

    def set_selected(self, selected: bool) -> None:
        rgba = _SELECTED_BG if selected else _UNSELECTED_BG
        if tuple(self._bg_color.rgba) != rgba:
            self._bg_color.rgba = rgba

    def _sync_bg(self, *_: Any) -> None:
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def on_touch_down(self, touch) -> bool:
        if self.collide_point(*touch.pos):
            try:
                self.service.select_line(self.line_id)
            except KeyError:
                pass
            self.service.clear_selection()
            return True
        return False
