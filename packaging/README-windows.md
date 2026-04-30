# Windows packaging

Build a onefolder distribution of BacMask for Windows using PyInstaller.
The resulting `dist/bacmask/` directory is self-contained — ship it zipped
or wrap it with an Inno Setup installer (separate step, not included yet).

## Prerequisites (on a Windows host or `windows-latest` CI runner)

```powershell
python -m pip install --upgrade pip
python -m pip install .
python -m pip install pyinstaller "kivy_deps.sdl2" "kivy_deps.glew"
# Optional — only needed if users hit GL driver issues:
python -m pip install "kivy_deps.angle"
```

> PyInstaller does **not** cross-compile. You must run the build on Windows.
> For reproducible builds, use GitHub Actions `runs-on: windows-latest`.

## Build

From the repo root:

```powershell
pyinstaller packaging\bacmask.spec
```

Outputs `dist\bacmask\bacmask.exe` plus its sibling DLLs and data files.

### Wrap into an installer (Inno Setup)

Install Inno Setup 6 (<https://jrsoftware.org/isdl.php>), then from the repo root:

```powershell
iscc packaging\installer.iss
```

Outputs `dist\bacmask-setup-<ver>.exe`. By default the installer is per-user
(no admin prompt); users can opt into a machine-wide install via the privilege
dialog. Two optional tasks are exposed in the wizard:

- **Desktop shortcut** — off by default.
- **Associate `.bacmask` files** — off by default. Double-click opens the
  bundle via `bacmask.exe <path>` (argv handled in `main.py`).

The installer does **not** delete `%LOCALAPPDATA%\BacMask` on uninstall —
user bundles/CSVs are treated as user work, not install artifacts.

## Smoke test

1. Run `dist\bacmask\bacmask.exe` on a machine without Python installed.
2. Load an image, trace a lasso, **Save** (`Ctrl+S`), **Export** (`Ctrl+E`).
3. Verify outputs appear under `%LOCALAPPDATA%\BacMask\bundles\` and
   `%LOCALAPPDATA%\BacMask\areas\`.
4. Confirm no console window opens.

## Paths

Installed builds write to a user-writable location, never `Program Files`:

| Platform | Output root |
|----------|-------------|
| Windows  | `%LOCALAPPDATA%\BacMask` |
| macOS    | `~/Library/Application Support/BacMask` |
| Linux    | `$XDG_DATA_HOME/BacMask` (or `~/.local/share/BacMask`) |
| Dev run  | `./output` (repo-local) |

Override with `BACMASK_OUTPUT_ROOT=<path>` (env var wins in all modes).

## Icon

Drop a multi-size `.ico` at `packaging/bacmask.ico` and rebuild — the spec
picks it up automatically. A plain 256×256 PNG won't do; use an `.ico`
container with 16/32/48/256 px entries.

## Versioning

The version lives in three files that must stay in lockstep:

1. `pyproject.toml` → `[project] version`
2. `packaging/version_info.txt` → `filevers`, `prodvers`, `FileVersion`, `ProductVersion`
3. `packaging/installer.iss` → `#define MyAppVersion`

Use the bump script — never edit by hand:

```bash
uv run scripts/bump_version.py 0.0.6           # edits the three files
uv run scripts/bump_version.py 0.0.6 --tag     # edits + commit + tag v0.0.6 + push
```

The script validates the input as `MAJOR.MINOR.PATCH` and refuses to write
unless every regex matches the expected number of times — so a renamed key
won't silently leave a file out of sync. With `--tag`, it stages exactly the
three version files, commits as `chore: bump version to X.Y.Z`, tags
`vX.Y.Z`, and pushes both `master` and the tag. The tag push triggers
`windows-build` → `softprops/action-gh-release` publishes the installer to
the matching GitHub Release.

## Known gaps (deferred)

- No code signing — users will see SmartScreen warnings on first run.
- No dedicated document icon for `.bacmask` — association uses the exe icon
  at index 0.

## Building on CI

`.github/workflows/windows-build.yml` runs the build on `windows-latest`.

- **Manual build:** Actions tab → *windows-build* → *Run workflow*. Artifact
  `bacmask-setup-<ver>.exe` attaches to the run (download requires GitHub
  login + repo read).
- **Release build:** push a tag matching `v*` (e.g.
  `uv run scripts/bump_version.py 0.0.6 --tag`). The workflow uploads the
  installer to the matching GitHub Release; on a public repo the asset is
  anonymously downloadable at
  `https://github.com/<owner>/<repo>/releases/download/v<ver>/bacmask-setup-<ver>.exe`.

The workflow declares `permissions: contents: write` so the default
`GITHUB_TOKEN` can publish Releases without a PAT.

## CI knobs that matter (lessons learned)

The workflow has a few non-obvious choices — don't strip them without
understanding why they're there:

- **`KIVY_GL_BACKEND=mock`** on the PyInstaller build step. Without it, the
  analysis phase imports `kivy.core.window`, which eagerly initializes a
  Window. The runner has only `GDI Generic` OpenGL 1.1, Kivy hits its `[GL]
  Minimum required OpenGL version (2.0) NOT found!` check and `sys.exit()`s,
  hanging PyInstaller indefinitely. The mock backend skips real GL/SDL2 init
  during the build; runtime still uses `glew_sdl2` on the user's GPU.
- **`actions/cache@v4` on `build/`** keyed by spec + lockfile. Cold
  PyInstaller analysis on this stack is ~15 min; warm reuse is ~3-5 min.
- **No onefolder upload-artifact.** The installer already contains it, and
  uploading the raw onefolder zips thousands of small Kivy files serially —
  was the source of multiple 30-min job timeouts.
- **`sys.setrecursionlimit(5000)`** in `bacmask.spec`. PyInstaller's
  modulegraph walk exceeds the 1000 default on Kivy + numpy + cv2 stacks.

## Spec hookup (lessons learned)

`packaging/bacmask.spec` uses Kivy's official helper to declare which
subsystems to include:

```python
from kivy.tools.packaging.pyinstaller_hooks import get_deps_minimal

deps = get_deps_minimal(
    image=True, text=True, window=True, clipboard=True,
    video=False, audio=False, camera=False, spelling=False,
)
```

This is the only reliable way to get the compiled image providers
(`_img_sdl2.cp312-win_amd64.pyd` etc.) bundled. Earlier hand-rolled
`excludes` like `kivy.core.audio` interacted with Kivy's hook and produced
a build with **only `text` and `window`** under `_internal/kivy/core/` —
the app launched, then died at `[CRITICAL] App: Unable to get any Image
provider, abort.` Diagnose by listing `_internal\kivy\core\` on the install:
expected subdirs are `clipboard`, `image`, `text`, `window`.

Note: `gl` is not a valid `get_deps_minimal` flag — passing it raises
`KeyError`.

## Troubleshooting on a Windows install

The shipped exe is `console=False`, so any traceback dies invisibly. To
debug:

1. **Kivy log** — written even with no console:
   `%USERPROFILE%\.kivy\logs\kivy_<date>_*.txt`. Newest file. Look at the
   tail.
2. **Bump Kivy log to debug** — names the actual `ImportError` per
   "ignored" provider:
   ```cmd
   set KIVY_LOG_LEVEL=debug
   "C:\Users\<name>\AppData\Local\Programs\BacMask\bacmask.exe"
   ```
3. **Inspect the install layout**:
   ```cmd
   dir "C:\Users\<name>\AppData\Local\Programs\BacMask\_internal\kivy\core"
   dir "C:\Users\<name>\AppData\Local\Programs\BacMask\_internal" | findstr /i "SDL2"
   ```
4. **Console rebuild** — if the Kivy log is empty (process died before Kivy
   started, e.g. missing MSVC runtime), flip `console=False` → `console=True`
   in `bacmask.spec`, rebuild, run from `cmd.exe`. Traceback prints directly.
5. **Windows Event Viewer** — `eventvwr.msc` → *Windows Logs* →
   *Application*. Filter on `Application Error` / `bacmask.exe`. Catches
   DLL-load failures, access violations.

### Known runtime gotchas

- **`ModuleNotFoundError: No module named 'win32timezone'`.** Kivy's
  `filechooser.is_hidden` defers `import win32timezone` until the first
  directory listing on Windows — PyInstaller can't see deferred imports
  inside function bodies. Fix is two-part and already applied: install
  `pywin32` in the workflow's deps step, and add `win32timezone` to
  `hiddenimports` in `bacmask.spec`. Symptom is a traceback that ends in
  `kivy/uix/filechooser.py` line ~180; the file picker works on dev
  machines because Kivy or its deps pull pywin32 in transitively there.
- **Non-ASCII image paths.** `cv2.imread()` on Windows uses ANSI Win32 file
  APIs and returns `None` for any path containing umlauts/accents/CJK — even
  on German Windows installs with paths like `Bilder\Größe.png`. Use
  `np.fromfile(p) → cv2.imdecode` instead. Already applied in
  `bacmask/core/io_manager.py:load_image` and the bundle reader.
- **Same-version reinstall.** Inno Setup uses `ignoreversion` on `[Files]`
  so files do overwrite, but Kivy log files cached under `%USERPROFILE%\.kivy\logs`
  are not touched. If diagnosing, look at the **newest** log, not
  `kivy_<date>.txt` from a previous run.
- **`GITHUB_TOKEN` 403 on Release create.** The workflow declares
  `permissions: contents: write` at the top level. If a fork or downstream
  repo strips this, `softprops/action-gh-release` fails with `403 Resource
  not accessible by integration`. Fix is the workflow header, not a PAT.
