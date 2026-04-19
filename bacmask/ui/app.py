"""Kivy App subclass. Ties service + UI + file dialogs + keyboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from bacmask.config import defaults
from bacmask.services.mask_service import MaskService
from bacmask.ui.input.desktop_adapter import keybinding_for
from bacmask.ui.screens.main_screen import MainScreen


class BacMaskApp(App):
    title = "BacMask"

    def __init__(self, initial_path: Path | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._initial_path = initial_path

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
        else:
            return False
        return True

    # ---- load / save dialogs ------------------------------------------------

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
        box.add_widget(chooser)

        btn_box = BoxLayout(size_hint_y=None, height=34, spacing=4)
        ok = Button(text="Load")
        cancel = Button(text="Cancel")
        btn_box.add_widget(ok)
        btn_box.add_widget(cancel)
        box.add_widget(btn_box)

        popup = Popup(title="Load Image / Bundle", content=box, size_hint=(0.9, 0.9))

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
        defaults.BUNDLES_DIR.mkdir(parents=True, exist_ok=True)
        bundle_path = defaults.BUNDLES_DIR / f"{stem}.bacmask"

        try:
            self.service.save_bundle(bundle_path)
            _popup(f"Saved:\n{bundle_path}", title="Saved")
        except Exception as e:
            _popup(f"Save failed: {e}", title="Error")

    def _export_csv(self) -> None:
        state = self.service.state
        if state.image_filename is None:
            _popup("No image loaded.", title="Export")
            return

        stem = Path(state.image_filename).stem
        defaults.AREAS_DIR.mkdir(parents=True, exist_ok=True)
        csv_path = defaults.AREAS_DIR / f"{stem}_areas.csv"

        try:
            self.service.export_csv(csv_path)
            _popup(f"Exported:\n{csv_path}", title="Exported")
        except Exception as e:
            _popup(f"Export failed: {e}", title="Error")


# ---- helpers ---------------------------------------------------------------

# Minimal Kivy key-code → name mapping. Extend as needed.
_SPECIAL_KEYS: dict[int, str] = {
    9: "tab",
    13: "enter",
    271: "numpadenter",
    27: "escape",
    127: "delete",
    8: "backspace",
}


def _kivy_key_name(key: int) -> str | None:
    if key in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[key]
    if 97 <= key <= 122:  # a-z
        return chr(key)
    return None


def _text_input_focused(root: Any) -> bool:
    """True if any TextInput descendant of ``root`` currently has focus."""
    from kivy.uix.textinput import TextInput

    def walk(w: Any) -> bool:
        if isinstance(w, TextInput) and w.focus:
            return True
        for child in getattr(w, "children", ()):
            if walk(child):
                return True
        return False

    return walk(root)


def _popup(text: str, title: str = "BacMask") -> None:
    Popup(title=title, content=Label(text=text), size_hint=(0.6, 0.35)).open()


def main(initial_path: Path | None = None) -> None:
    BacMaskApp(initial_path=initial_path).run()
