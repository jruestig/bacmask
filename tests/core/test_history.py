from bacmask.core.history import UndoRedoStack


class RecordingCmd:
    """Pure-Python command for exercising the stack."""

    def __init__(self, token: str) -> None:
        self.token = token

    def apply(self, state: dict) -> None:
        state["log"].append(f"apply:{self.token}")

    def undo(self, state: dict) -> None:
        state["log"].append(f"undo:{self.token}")


def test_push_applies_and_records():
    stack = UndoRedoStack()
    state = {"log": []}
    stack.push(RecordingCmd("a"), state)
    assert state["log"] == ["apply:a"]
    assert len(stack) == 1


def test_undo_then_redo_round_trips():
    stack = UndoRedoStack()
    state = {"log": []}
    stack.push(RecordingCmd("a"), state)
    assert stack.undo(state) is True
    assert stack.redo(state) is True
    assert state["log"] == ["apply:a", "undo:a", "apply:a"]


def test_undo_empty_returns_false():
    assert UndoRedoStack().undo({"log": []}) is False


def test_pushing_after_undo_clears_redo():
    stack = UndoRedoStack()
    state = {"log": []}
    stack.push(RecordingCmd("a"), state)
    stack.undo(state)
    stack.push(RecordingCmd("b"), state)
    assert stack.redo(state) is False


def test_cap_drops_oldest():
    stack = UndoRedoStack(cap=3)
    state = {"log": []}
    for t in ("a", "b", "c", "d"):
        stack.push(RecordingCmd(t), state)
    assert len(stack) == 3
    for _ in range(3):
        assert stack.undo(state) is True
    assert state["log"] == [
        "apply:a",
        "apply:b",
        "apply:c",
        "apply:d",
        "undo:d",
        "undo:c",
        "undo:b",
    ]


def test_clear_empties_both_stacks():
    stack = UndoRedoStack()
    state = {"log": []}
    stack.push(RecordingCmd("a"), state)
    stack.undo(state)
    stack.clear()
    assert stack.undo(state) is False
    assert stack.redo(state) is False
