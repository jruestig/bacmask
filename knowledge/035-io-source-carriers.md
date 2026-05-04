---
id: 035
title: I/O Source Carriers (Path-Free Decode)
tags: [architecture, core]
created: 2026-05-04
status: accepted
related: [008, 011, 015, 020]
---

# I/O Source Carriers

Decouple decode logic from byte acquisition. Same code path serve desktop filesystem, Android SAF, in-memory tests, zipfile members.

## Decision

Two layer in `bacmask/core/io_manager.py`:

1. **Source carriers** — frozen dataclass hold encoded bytes + metadata.
   - `ImageSource(data, ext, name, origin)`
   - `BundleSource(data, name, origin)`
   - Factories: `from_path(p)`, `from_bytes(b, …)`, `from_stream(fp, …)`.
   - `origin: Path | None` — `None` when not from disk (SAF / memory).
2. **Pure decoders** — take carrier, never touch filesystem.
   - `decode_image(src) -> np.ndarray`
   - `open_bundle(src) -> BundleContents`

Path wrapper kept for desktop convenience:
- `load_image(p) = decode_image(ImageSource.from_path(p))`
- `load_bundle(p) = open_bundle(BundleSource.from_path(p))`

Write side: `save_bundle_from_bytes` + `save_areas_csv` accept `Path | str | BinaryIO`. `zipfile` and `csv` already file-object native.

## Why

Android SAF return content URI / file descriptor / `InputStream` — not `Path`. `Path.exists()` lie, `open(path)` fail. Pre-refactor `io_manager` Path-only at top of every loader. Pre-refactor service ALSO read file twice (`load_image` then `read_bytes`), and re-open zip after `load_bundle` to recover image bytes.

Source carriers solve both:
- One read, bytes carried in dataclass.
- SAF wrapper become 3 lines: open fd → read → `ImageSource.from_bytes`.
- Tests use `BytesIO` → no `tmp_path`, no disk.

## Pre-refactor smell

```python
# mask_service.load_image — DOUBLE READ
img = io_manager.load_image(p)         # decode (reads file once)
self.state.image_bytes = p.read_bytes()  # reads again

# mask_service.load_bundle — DOUBLE ZIP OPEN
bundle = io_manager.load_bundle(p)              # opens zip
with zipfile.ZipFile(p, "r") as zf:             # opens zip AGAIN
    self.state.image_bytes = zf.read(...)
```

Post-refactor: `BundleContents` carry `image_bytes`. Single open, single read.

## Service layer

`MaskService` get canonical source-based methods + path shims:

```python
svc.load_image_source(src: ImageSource)   # canonical
svc.load_image(path)                       # shim
svc.load_bundle_source(src: BundleSource) # canonical
svc.load_bundle(path)                      # shim
```

Desktop UI keep using path methods. Future Android UI build source from SAF stream:

```python
fd = plyer.filechooser.open_file(...)
with open(fd, "rb") as fp:
    svc.load_image_source(ImageSource.from_stream(fp, ext=".png", name="x.png"))
```

## State coupling fix

`SessionState.set_image(image, *, name, origin)` — was `(image, path: Path)`. Now `origin` optional. `image_filename` come from explicit `name` arg, not derived from required path.

## Tests

`tests/core/test_io_manager.py` add 10 new tests:
- `from_path` / `from_bytes` / `from_stream` factory normalize ext.
- `decode_image` from `BytesIO` source — proves filesystem-free decode.
- Bundle round-trip via `BytesIO` — proves stream-only save + load.
- `BundleContents.image_bytes` carry verbatim source bytes.
- `save_areas_csv` to `BytesIO`.

Total `pytest`: 215 → 225, all pass.

## What stay Path

- `BACMASK_OUTPUT_ROOT` in `config/defaults.py` — not relevant to load.
- `io_manager.save_bundle(bundle_path, source_image_path, …)` legacy convenience — unused by service after refactor; kept for back-compat with `tests/core/test_io_manager.py` round-trip helpers.

## Why not protocol / ABC

Considered `BinaryStorage` protocol with `read_bytes()` method. Rejected — three classmethod factories simpler, dataclass equality free, no method dispatch, no inheritance. Carrier is data, not behavior.

## Why not `Path | bytes | BinaryIO` union

Considered single `load_image(source: Path | bytes | BinaryIO)`. Rejected — caller must pass `ext` and `name` separately when not Path; signature gets ugly. Carrier hold those together — one arg, no positional mismatch risk.

## Related

- [008 — Directory Layout](008-directory-layout.md) — `io_manager.py` shape.
- [011 — CSV for Area Output](011-csv-for-area-output.md) — `save_areas_csv` accept stream.
- [015 — .bacmask Bundle](015-bacmask-bundle.md) — `BundleContents.image_bytes`, `save_bundle_from_bytes` accept stream.
- [020 — Platform Scope](020-platform-scope.md) — Android-readiness hook now load-bearing.
