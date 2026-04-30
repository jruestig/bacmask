"""Calibration input — two synced fields: mm per pixel and pixels per mm.

Either field accepts input; the other updates automatically. Canonical storage
is ``mm_per_px`` per knowledge/017.
"""

from __future__ import annotations

from typing import Any

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from bacmask.services.mask_service import MaskService

# Tied to the toolbar's 40 px row height — labels and text inputs must use the
# same DPI-aware font size, otherwise on Windows high-DPI the default 15 sp
# text overflows fixed-pixel label boxes.
_LABEL_FONT_SIZE = sp(13)
_LABEL_WIDTH = dp(56)


class CalibrationInput(BoxLayout):
    def __init__(self, service: MaskService, **kwargs: Any) -> None:
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(30))
        kwargs.setdefault("spacing", dp(4))
        super().__init__(**kwargs)
        self.service = service

        self.add_widget(
            Label(
                text="mm/px:",
                size_hint_x=None,
                width=_LABEL_WIDTH,
                font_size=_LABEL_FONT_SIZE,
            )
        )
        self.mm_per_px = TextInput(
            multiline=False,
            write_tab=False,
            hint_text="e.g. 0.0125",
            font_size=_LABEL_FONT_SIZE,
        )
        self.mm_per_px.bind(on_text_validate=self._commit_mm_per_px)
        self.add_widget(self.mm_per_px)

        self.add_widget(
            Label(
                text="px/mm:",
                size_hint_x=None,
                width=_LABEL_WIDTH,
                font_size=_LABEL_FONT_SIZE,
            )
        )
        self.px_per_mm = TextInput(
            multiline=False,
            write_tab=False,
            hint_text="e.g. 80",
            font_size=_LABEL_FONT_SIZE,
        )
        self.px_per_mm.bind(on_text_validate=self._commit_px_per_mm)
        self.add_widget(self.px_per_mm)

        service.subscribe(self._sync_from_state)

    # ---- commits ------------------------------------------------------------

    def _commit_mm_per_px(self, *_: Any) -> None:
        text = self.mm_per_px.text.strip()
        if text == "":
            self.service.set_calibration(None)
            return
        try:
            self.service.set_calibration(float(text))
        except (ValueError, TypeError):
            pass  # leave the field as-is so the user can correct it

    def _commit_px_per_mm(self, *_: Any) -> None:
        text = self.px_per_mm.text.strip()
        if text == "":
            self.service.set_calibration(None)
            return
        try:
            v = float(text)
        except (ValueError, TypeError):
            return
        if v <= 0:
            return
        try:
            self.service.set_calibration(1.0 / v)
        except (ValueError, TypeError):
            pass

    # ---- sync from state ----------------------------------------------------

    def _sync_from_state(self) -> None:
        scale = self.service.state.scale_mm_per_px
        mm_text = "" if scale is None else _fmt(scale)
        px_text = "" if scale is None or scale == 0 else _fmt(1.0 / scale)
        # Don't overwrite the field the user is currently editing.
        if not self.mm_per_px.focus and self.mm_per_px.text != mm_text:
            self.mm_per_px.text = mm_text
        if not self.px_per_mm.focus and self.px_per_mm.text != px_text:
            self.px_per_mm.text = px_text


def _fmt(x: float) -> str:
    """Compact float format: 0.0125 → '0.0125', 80.0 → '80'."""
    return f"{x:g}"
