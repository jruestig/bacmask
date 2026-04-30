"""Kivy App subclass. Ties service + UI + file dialogs + keyboard."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from bacmask.core.state import SessionState
from bacmask.services.mask_service import MaskService
from bacmask.ui.input.desktop_adapter import keybinding_for
from bacmask.ui.screens.main_screen import MainScreen


class BacMaskApp(App):
    title = "BacMask"

    def __init__(self, initial_path: Path | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._initial_path = initial_path
        self._last_save_dir: Path | None = None
        self._last_export_dir: Path | None = None
        self._open_modal_count: int = 0

    def build(self) -> MainScreen:
        self.service = MaskService()
        self.screen = MainScreen(
            self.service,
            on_load=self._open_load_dialog,
            on_save=self._save_bundle,
            on_export=self._export_csv,
        )
        Window.bind(on_key_down=self._on_key_down)
        if self._initial_path is not None:
            self._load_path(self._initial_path)
        return self.screen

    def _load_path(self, path: Path) -> None:
        try:
            if path.suffix.lower() == ".bacmask":
                self.service.load_bundle(path)
            else:
                self.service.load_image(path)
        except Exception as e:
            _popup(f"Failed to load: {e}", title="Error")

    # ---- keyboard -----------------------------------------------------------

    def _on_key_down(
        self,
        window: Any,
        key: int,
        scancode: int,
        codepoint: str | None,
        modifiers: list[str],
    ) -> bool:
        # Let any open modal (Save As, Load, etc.) own keyboard input — we
        # don't want global shortcuts to fire while a dialog is up.
        if self._open_modal_count > 0:
            return False
        # Let the focused TextInput own its keys (backspace, delete, ctrl+z, etc.).
        if _text_input_focused(self.screen):
            return False
        key_name = _kivy_key_name(key)
        if key_name is None:
            return False
        action = keybinding_for(key_name, set(modifiers))
        if action is None:
            return False
        return self._run_action(action)

    def _run_action(self, action: str) -> bool:
        svc = self.service
        if action == "close_lasso":
            svc.close_lasso()
        elif action == "cancel_stroke":
            if svc.state.active_brush_stroke is not None:
                svc.cancel_brush_stroke()
            else:
                svc.cancel_lasso()
        elif action == "undo":
            svc.undo()
        elif action == "redo":
            svc.redo()
        elif action == "delete_region":
            sid = svc.state.selected_region_id
            if sid is not None:
                try:
                    svc.delete_region(sid)
                except KeyError:
                    pass
        elif action == "save_bundle":
            self._save_bundle()
        elif action == "export_csv":
            self._export_csv()
        elif action == "select_lasso":
            svc.set_active_tool("lasso")
        elif action == "select_brush":
            svc.set_active_tool("brush")
        elif action == "toggle_brush_mode":
            svc.toggle_brush_default_mode()
        elif action == "load_image":
            self._open_load_dialog()
        elif action in ("pan_left", "pan_right", "pan_up", "pan_down"):
            self.screen.canvas_widget.pan_by_action(action)
        else:
            return False
        return True

    # ---- load / save dialogs ------------------------------------------------

    def _open_new_folder_dialog(self, parent_dir: Path, chooser: FileChooserListView) -> None:
        """Prompt for a folder name, create it under ``parent_dir``, navigate into it."""
        box = BoxLayout(orientation="vertical", spacing=6, padding=6)
        box.add_widget(
            Label(
                text=f"Create folder in:\n{parent_dir}",
                size_hint_y=None,
                height=48,
            )
        )
        name_input = TextInput(
            multiline=False,
            write_tab=False,
            size_hint_y=None,
            height=34,
        )
        box.add_widget(name_input)

        btn_box = BoxLayout(size_hint_y=None, height=34, spacing=4)
        ok = Button(text="Create")
        cancel = Button(text="Cancel")
        btn_box.add_widget(ok)
        btn_box.add_widget(cancel)
        box.add_widget(btn_box)

        popup = Popup(title="New Folder", content=box, size_hint=(0.5, 0.4))
        self._track_modal(popup)
        popup.bind(on_open=lambda *_: setattr(name_input, "focus", True))

        def do_create(*_: Any) -> None:
            name = name_input.text.strip()
            if not name or "/" in name or "\\" in name:
                _popup("Invalid folder name.", title="New Folder")
                return
            new_dir = parent_dir / name
            try:
                new_dir.mkdir(parents=False, exist_ok=False)
            except FileExistsError:
                _popup(f"Already exists:\n{new_dir}", title="New Folder")
                return
            except Exception as e:
                _popup(f"Failed: {e}", title="New Folder")
                return
            popup.dismiss()
            chooser.path = str(new_dir)

        ok.bind(on_release=do_create)
        cancel.bind(on_release=lambda *_: popup.dismiss())
        name_input.bind(on_text_validate=do_create)
        popup.open()

    def _track_modal(self, popup: Popup) -> None:
        """Suppress global key shortcuts while ``popup`` is open."""

        def _on_open(*_: Any) -> None:
            self._open_modal_count += 1

        def _on_dismiss(*_: Any) -> None:
            self._open_modal_count = max(0, self._open_modal_count - 1)

        popup.bind(on_open=_on_open, on_dismiss=_on_dismiss)

    def _open_load_dialog(self) -> None:
        start_path = str(Path.cwd())
        chooser = FileChooserListView(
            path=start_path,
            filters=[
                "*.png",
                "*.PNG",
                "*.jpg",
                "*.JPG",
                "*.jpeg",
                "*.tif",
                "*.TIF",
                "*.tiff",
                "*.TIFF",
                "*.bmp",
                "*.bacmask",
            ],
        )
        box = BoxLayout(orientation="vertical")
        box.add_widget(_make_path_bar(chooser))
        box.add_widget(chooser)

        btn_box = BoxLayout(size_hint_y=None, height=34, spacing=4)
        ok = Button(text="Load")
        cancel = Button(text="Cancel")
        btn_box.add_widget(ok)
        btn_box.add_widget(cancel)
        box.add_widget(btn_box)

        popup = Popup(title="Load Image / Bundle", content=box, size_hint=(0.9, 0.9))
        self._track_modal(popup)

        def do_load(*_: Any) -> None:
            if not chooser.selection:
                popup.dismiss()
                return
            path = Path(chooser.selection[0])
            try:
                if path.suffix.lower() == ".bacmask":
                    self.service.load_bundle(path)
                else:
                    self.service.load_image(path)
            except Exception as e:
                _popup(f"Failed to load: {e}", title="Error")
            popup.dismiss()

        def on_submit(_chooser: Any, selection: list[str], _touch: Any) -> None:
            # Kivy fires ``on_submit`` on double-click (and on Enter while a
            # file is highlighted). Route it through the same load path as the
            # Load button — see knowledge/028.
            if selection:
                do_load()

        chooser.bind(on_submit=on_submit)
        ok.bind(on_release=do_load)
        cancel.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def _save_bundle(self) -> None:
        state = self.service.state
        if state.image_filename is None:
            _popup("No image loaded.", title="Save")
            return

        stem = Path(state.image_filename).stem
        start_dir = self._last_save_dir or _image_dir(state) or Path.cwd()

        def do_save(out_path: Path) -> None:
            if out_path.suffix.lower() != ".bacmask":
                out_path = out_path.with_suffix(".bacmask")
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                self.service.save_bundle(out_path)
                self._last_save_dir = out_path.parent
                _popup(f"Saved:\n{out_path}", title="Saved")
            except Exception as e:
                _popup(f"Save failed: {e}", title="Error")

        self._open_save_as_dialog(
            title="Save Bundle As",
            start_dir=start_dir,
            default_filename=f"{stem}.bacmask",
            on_confirm=do_save,
        )

    def _export_csv(self) -> None:
        state = self.service.state
        if state.image_filename is None:
            _popup("No image loaded.", title="Export")
            return

        stem = Path(state.image_filename).stem
        start_dir = self._last_export_dir or _image_dir(state) or Path.cwd()

        def do_export(out_path: Path) -> None:
            if out_path.suffix.lower() != ".csv":
                out_path = out_path.with_suffix(".csv")
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                self.service.export_csv(out_path)
                self._last_export_dir = out_path.parent
                _popup(f"Exported:\n{out_path}", title="Exported")
            except Exception as e:
                _popup(f"Export failed: {e}", title="Error")

        self._open_save_as_dialog(
            title="Export CSV As",
            start_dir=start_dir,
            default_filename=f"{stem}_areas.csv",
            on_confirm=do_export,
        )

    def _open_save_as_dialog(
        self,
        title: str,
        start_dir: Path,
        default_filename: str,
        on_confirm: Callable[[Path], None],
    ) -> None:
        if not start_dir.is_dir():
            start_dir = Path.cwd()
        chooser = FileChooserListView(path=str(start_dir), dirselect=False)

        box = BoxLayout(orientation="vertical")
        box.add_widget(_make_path_bar(chooser))
        box.add_widget(chooser)

        name_row = BoxLayout(size_hint_y=None, height=34, spacing=4)
        name_row.add_widget(Label(text="Filename:", size_hint_x=None, width=80))
        name_input = TextInput(
            text=default_filename,
            multiline=False,
            write_tab=False,
        )
        name_row.add_widget(name_input)
        box.add_widget(name_row)

        btn_box = BoxLayout(size_hint_y=None, height=34, spacing=4)
        new_folder = Button(text="New Folder")
        ok = Button(text="Save")
        cancel = Button(text="Cancel")
        btn_box.add_widget(new_folder)
        btn_box.add_widget(ok)
        btn_box.add_widget(cancel)
        box.add_widget(btn_box)

        popup = Popup(title=title, content=box, size_hint=(0.9, 0.9))
        self._track_modal(popup)

        def open_new_folder(*_: Any) -> None:
            self._open_new_folder_dialog(Path(chooser.path), chooser)

        new_folder.bind(on_release=open_new_folder)

        def _focus_name(*_: Any) -> None:
            name_input.focus = True

        popup.bind(on_open=_focus_name)

        def _sync_name_from_selection(*_: Any) -> None:
            if chooser.selection:
                sel = Path(chooser.selection[0])
                if sel.is_file():
                    name_input.text = sel.name

        chooser.bind(selection=_sync_name_from_selection)

        def do_confirm(*_: Any) -> None:
            name = name_input.text.strip()
            if not name:
                return
            out_path = Path(chooser.path) / name
            popup.dismiss()
            on_confirm(out_path)

        ok.bind(on_release=do_confirm)
        cancel.bind(on_release=lambda *_: popup.dismiss())
        popup.open()


# ---- helpers ---------------------------------------------------------------

# Minimal Kivy key-code → name mapping. Extend as needed.
_SPECIAL_KEYS: dict[int, str] = {
    9: "tab",
    13: "enter",
    271: "numpadenter",
    27: "escape",
    127: "delete",
    8: "backspace",
    273: "up",
    274: "down",
    275: "right",
    276: "left",
}


def _kivy_key_name(key: int) -> str | None:
    if key in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[key]
    if 97 <= key <= 122:  # a-z
        return chr(key)
    return None


def _text_input_focused(root: Any) -> bool:
    """True if any TextInput descendant of ``root`` currently has focus."""

    def walk(w: Any) -> bool:
        if isinstance(w, TextInput) and w.focus:
            return True
        for child in getattr(w, "children", ()):
            if walk(child):
                return True
        return False

    return walk(root)


def _image_dir(state: SessionState) -> Path | None:
    """Directory of the loaded image, if any — used as the default Save-As dir."""
    p = state.image_path
    if p is None:
        return None
    parent = Path(p).parent
    return parent if parent.is_dir() else None


def _popup(text: str, title: str = "BacMask") -> None:
    Popup(title=title, content=Label(text=text), size_hint=(0.6, 0.35)).open()


def _make_path_bar(chooser: FileChooserListView) -> ScrollView:
    """Breadcrumb bar above ``chooser`` — click a segment to jump there."""
    scroll = ScrollView(
        size_hint_y=None,
        height=30,
        do_scroll_x=True,
        do_scroll_y=False,
        bar_width=4,
    )
    bar = BoxLayout(
        orientation="horizontal",
        size_hint_x=None,
        spacing=2,
        padding=(4, 0),
    )
    bar.bind(minimum_width=bar.setter("width"))
    scroll.add_widget(bar)

    def rebuild(*_: Any) -> None:
        bar.clear_widgets()
        p = Path(chooser.path)
        parts = [p, *p.parents]
        parts.reverse()
        for i, seg in enumerate(parts):
            label = seg.name or str(seg)  # root → "/" or drive letter
            btn = Button(
                text=label,
                size_hint=(None, 1),
                padding=(8, 0),
            )
            btn.texture_update()
            btn.width = max(40, btn.texture_size[0] + 16)
            btn.bind(on_release=lambda _b, target=str(seg): _set_chooser_path(chooser, target))
            bar.add_widget(btn)
            if i < len(parts) - 1:
                sep = Label(text="/", size_hint=(None, 1), width=12)
                bar.add_widget(sep)

    chooser.bind(path=rebuild)
    rebuild()
    return scroll


def _set_chooser_path(chooser: FileChooserListView, target: str) -> None:
    if Path(target).is_dir():
        chooser.path = target


def main(initial_path: Path | None = None) -> None:
    BacMaskApp(initial_path=initial_path).run()
