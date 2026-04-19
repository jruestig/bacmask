"""Semantic input events — vocabulary shared between UI widgets and services.

Widgets consume these, not raw Kivy events. See knowledge/016-input-abstraction.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PointerDown:
    pos: tuple[float, float]
    modifiers: tuple[str, ...] = ()
    is_double: bool = False


@dataclass(frozen=True)
class PointerMove:
    pos: tuple[float, float]


@dataclass(frozen=True)
class PointerUp:
    pos: tuple[float, float]


@dataclass(frozen=True)
class Zoom:
    center: tuple[float, float]
    delta: float


@dataclass(frozen=True)
class Pan:
    delta: tuple[float, float]


@dataclass(frozen=True)
class Action:
    name: str


InputEvent = PointerDown | PointerMove | PointerUp | Zoom | Pan | Action
