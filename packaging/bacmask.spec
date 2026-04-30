# PyInstaller spec for BacMask (Windows).
#
# Build:   pyinstaller packaging/bacmask.spec
# Output:  dist/bacmask/bacmask.exe  (onefolder)
#
# This spec is authored for Windows builds. The kivy_deps.* packages only
# install on Windows, so imports are guarded so the file is at least parseable
# on other platforms (useful for linting / CI dry-runs).

from pathlib import Path
import sys

block_cipher = None

SPEC_DIR = Path(SPECPATH).resolve()
REPO_ROOT = SPEC_DIR.parent
ENTRY = str(REPO_ROOT / "main.py")
ICON = SPEC_DIR / "bacmask.ico"
VERSION_FILE = SPEC_DIR / "version_info.txt"

# Kivy runtime hooks + SDL2/GLEW native DLLs.
hookspath = []
runtime_hooks = []
kivy_dep_bins = []

try:
    from kivy.tools.packaging.pyinstaller_hooks import (
        hookspath as kivy_hookspath,
        runtime_hooks as kivy_runtime_hooks,
    )

    hookspath += list(kivy_hookspath())
    runtime_hooks += list(kivy_runtime_hooks())
except ImportError:
    pass

if sys.platform.startswith("win"):
    try:
        from kivy_deps import sdl2, glew

        kivy_dep_bins += sdl2.dep_bins + glew.dep_bins
    except ImportError:
        pass
    try:
        from kivy_deps import angle

        kivy_dep_bins += angle.dep_bins
    except ImportError:
        pass

hiddenimports = []

a = Analysis(
    [ENTRY],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=hookspath,
    hooksconfig={},
    runtime_hooks=runtime_hooks,
    excludes=[
        "tests",
        "pytest",
        "pytest_cov",
        "ruff",
        "setuptools",
        "tkinter",
        "PIL",
        "Pillow",
        "kivy.core.audio",
        "kivy.core.video",
        "kivy.core.camera",
        "kivy.core.spelling",
        "kivy.core.clipboard.clipboard_dbus",
        "kivy.core.clipboard.clipboard_xclip",
        "kivy.core.clipboard.clipboard_xsel",
        "kivy.network",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe_kwargs = dict(
    name="bacmask",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app — no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if ICON.exists():
    exe_kwargs["icon"] = str(ICON)
if VERSION_FILE.exists():
    exe_kwargs["version"] = str(VERSION_FILE)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    **exe_kwargs,
)

coll_args = [exe, a.binaries, a.zipfiles, a.datas]
for dep in kivy_dep_bins:
    coll_args.append(Tree(dep))

coll = COLLECT(
    *coll_args,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="bacmask",
)
