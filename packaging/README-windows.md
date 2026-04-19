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

Outputs `dist\bacmask-setup-0.0.1.exe`. By default the installer is per-user
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

Bump the version in three places in lockstep:

1. `pyproject.toml` → `[project] version`
2. `packaging/version_info.txt` → `filevers`, `prodvers`, `FileVersion`, `ProductVersion`
3. `packaging/installer.iss` → `#define MyAppVersion`

## Known gaps (deferred)

- No code signing — users will see SmartScreen warnings on first run.
- No dedicated document icon for `.bacmask` — association uses the exe icon
  at index 0.

## Building on CI

`.github/workflows/windows-build.yml` runs the build on `windows-latest`.

- **Manual build:** Actions tab → *windows-build* → *Run workflow*. Artifacts
  (`bacmask-setup-<ver>.exe` and the onefolder dist) attach to the run.
- **Release build:** push a tag matching `v*` (e.g. `git tag v0.0.1 && git
  push origin v0.0.1`). The installer is also uploaded to a GitHub Release
  for that tag.
