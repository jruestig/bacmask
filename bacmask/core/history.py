"""Bounded undo/redo stack. See knowledge/003-undo-redo-commands.md."""

from __future__ import annotations

from collections import deque
from typing import Any, Protocol

from bacmask.config import defaults


class Command(Protocol):
    def apply(self, state: Any) -> None: ...
    def undo(self, state: Any) -> None: ...


class UndoRedoStack:
    def __init__(self, cap: int = defaults.UNDO_HISTORY_CAP) -> None:
        self._undo: deque[Command] = deque(maxlen=cap)
        self._redo: list[Command] = []

    def push(self, cmd: Command, state: Any) -> None:
        cmd.apply(state)
        self._undo.append(cmd)
        self._redo.clear()

    def undo(self, state: Any) -> bool:
        if not self._undo:
            return False
        cmd = self._undo.pop()
        cmd.undo(state)
        self._redo.append(cmd)
        return True

    def redo(self, state: Any) -> bool:
        if not self._redo:
            return False
        cmd = self._redo.pop()
        cmd.apply(state)
        self._undo.append(cmd)
        return True

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def __len__(self) -> int:
        return len(self._undo)
