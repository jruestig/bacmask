"""I/O for images, .bacmask bundles, and sibling CSV.

The public surface has two layers:

* **Source carriers** (:class:`ImageSource`, :class:`BundleSource`) — frozen
  dataclasses holding the encoded bytes plus the metadata the rest of the
  system needs (extension, display name, optional filesystem origin).
  Construct via the ``from_path`` / ``from_bytes`` / ``from_stream``
  classmethods.
* **Pure decoders** (:func:`decode_image`, :func:`open_bundle`) — operate on
  source carriers, never touch the filesystem.

Path-based wrappers (:func:`load_image`, :func:`load_bundle`) are kept as
convenience shims over the decoders so existing call sites keep working.
The split lets Android (SAF), in-memory tests, and zipfile-member loads use
the same decode path as the desktop filesystem.

Write side: :func:`save_bundle_from_bytes` and :func:`save_areas_csv` accept
either a filesystem path or a writable binary stream — ``zipfile`` and
``csv`` both work file-object-natively.

See knowledge/011 (CSV), 015 (bundle), 024 (mask export deferred),
025 (polygons canonical).
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

import cv2
import numpy as np

BACMASK_VERSION = 2
BACMASK_VERSION_V1 = 1

CSV_HEADER = [
    "filename",
    "region_id",
    "region_name",
    "area_px",
    "area_mm2",
    "scale_factor",
]


class UnsupportedBundleVersion(Exception):
    def __init__(self, version: Any) -> None:
        super().__init__(f"unsupported bacmask_version: {version!r}")
        self.version = version


# ---- source carriers ---------------------------------------------------------


def _normalize_ext(ext: str) -> str:
    """Lowercase, ensure leading dot, fall back to ``.bin``."""
    if not ext:
        return ".bin"
    e = ext.lower()
    return e if e.startswith(".") else "." + e


@dataclass(frozen=True)
class ImageSource:
    """Encoded image bytes ready for decoding.

    Decoupled from the filesystem so loading works with SAF URIs, network
    streams, fixtures, or zipfile members. Construct via the ``from_*``
    classmethods.

    Attributes:
        data: Raw encoded file bytes (e.g. PNG/TIFF/JPEG container).
        ext: Lowercase extension with leading dot (``.png``, ``.tif``...).
        name: Display filename — used as ``BundleMeta.source_filename``.
        origin: Filesystem path the source was read from, or ``None`` if it
            came from memory / a stream. Used by the UI to default the
            Save-As dialog to the source's directory.
    """

    data: bytes
    ext: str
    name: str
    origin: Path | None = None

    @classmethod
    def from_path(cls, path: Path | str) -> ImageSource:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(p)
        return cls(
            data=p.read_bytes(),
            ext=_normalize_ext(p.suffix),
            name=p.name,
            origin=p,
        )

    @classmethod
    def from_bytes(cls, data: bytes, *, ext: str, name: str) -> ImageSource:
        return cls(data=data, ext=_normalize_ext(ext), name=name, origin=None)

    @classmethod
    def from_stream(cls, fp: BinaryIO, *, ext: str, name: str) -> ImageSource:
        return cls.from_bytes(fp.read(), ext=ext, name=name)


@dataclass(frozen=True)
class BundleSource:
    """Encoded ``.bacmask`` ZIP bytes ready for parsing.

    The full archive is materialized into memory because :class:`zipfile.ZipFile`
    needs a seekable input and SAF file descriptors aren't always cheaply
    seekable. Bundles are small (image bytes + tiny JSON), so eager-read keeps
    the loader uniform across desktop and Android.
    """

    data: bytes
    name: str
    origin: Path | None = None

    @classmethod
    def from_path(cls, path: Path | str) -> BundleSource:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(p)
        return cls(data=p.read_bytes(), name=p.name, origin=p)

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str) -> BundleSource:
        return cls(data=data, name=name, origin=None)

    @classmethod
    def from_stream(cls, fp: BinaryIO, *, name: str) -> BundleSource:
        return cls.from_bytes(fp.read(), name=name)


# ---- image decoding ----------------------------------------------------------


def decode_image(source: ImageSource) -> np.ndarray:
    """Decode an :class:`ImageSource` into a NumPy array.

    Color images come back as BGR (cv2 convention); bit depth and channel
    count are preserved. Raises :class:`ValueError` if the bytes can't be
    decoded as an image.
    """
    img = cv2.imdecode(np.frombuffer(source.data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"could not decode image: {source.name}")
    return img


def load_image(path: Path | str) -> np.ndarray:
    """Convenience: read + decode an image from a filesystem path.

    Equivalent to ``decode_image(ImageSource.from_path(path))``. Kept as a
    thin shim so existing path-based call sites and tests don't need to
    change.
    """
    return decode_image(ImageSource.from_path(path))


# ---- CSV ---------------------------------------------------------------------


@dataclass
class AreaRow:
    filename: str
    region_id: int
    region_name: str
    area_px: float  # polygon shoelace area in px² (knowledge/030)
    area_mm2: float | None  # None -> empty cell (uncalibrated)
    scale_factor: float | None  # None -> empty cell (uncalibrated)


def save_areas_csv(target: Path | str | BinaryIO, rows: list[AreaRow]) -> None:
    """Write the areas CSV.

    ``target`` is either a filesystem path or a writable binary stream. The
    stream form lets the Android save path hand a SAF-provided file
    descriptor straight in without an intermediate file.
    """
    if isinstance(target, (str, Path)):
        with open(target, "w", newline="") as f:
            _write_csv_rows(f, rows)
        return
    text = io.TextIOWrapper(target, encoding="utf-8", newline="", write_through=True)
    try:
        _write_csv_rows(text, rows)
        text.flush()
    finally:
        text.detach()


def _write_csv_rows(f: Any, rows: list[AreaRow]) -> None:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(CSV_HEADER)
    for r in rows:
        w.writerow(
            [
                r.filename,
                r.region_id,
                r.region_name,
                r.area_px,
                "" if r.area_mm2 is None else str(r.area_mm2),
                "" if r.scale_factor is None else str(r.scale_factor),
            ]
        )


# ---- .bacmask bundle ---------------------------------------------------------


@dataclass
class BundleMeta:
    source_filename: str
    image_shape: tuple[int, int]
    scale_mm_per_px: float | None
    next_label_id: int
    regions: dict[int, dict[str, Any]]
    # Measurement lines (knowledge/017 calibration helper). Persisted alongside
    # regions so a reloaded bundle restores the exact session — including the
    # mm/px reference lines the user drew. Schema per line:
    # ``{"name": str, "p1": [x, y], "p2": [x, y]}``. Empty dict when none.
    lines: dict[int, dict[str, Any]] = field(default_factory=dict)
    next_line_id: int = 1
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class BundleContents:
    image: np.ndarray
    image_ext: str  # ".tif", ".png", ... (with leading dot)
    image_bytes: bytes  # raw encoded source bytes — re-bundled verbatim on save
    meta: BundleMeta


def save_bundle_from_bytes(
    target: Path | str | BinaryIO,
    *,
    image_bytes: bytes,
    image_ext: str,
    image_shape: tuple[int, int],
    meta: BundleMeta,
) -> None:
    """Write a v2 ``.bacmask`` ZIP given raw source-image bytes and extension.

    ``target`` is either a filesystem path or a writable binary stream.
    ``zipfile.ZipFile`` accepts both natively, so the same writer covers
    desktop disk writes and SAF-mediated Android writes without branching.

    v2 bundles contain only ``image.<ext>`` and ``meta.json``. Raster masks
    are not stored; polygons in ``meta.regions`` are canonical (knowledge/015,
    knowledge/025). Raster export is a separate, deferred operation
    (knowledge/024).
    """
    ext = _normalize_ext(image_ext)

    h, w = image_shape
    now_iso = _utcnow_iso()
    meta_json = {
        "bacmask_version": BACMASK_VERSION,
        "source_filename": meta.source_filename,
        "image_shape": [int(h), int(w)],
        "created_at": meta.created_at or now_iso,
        "updated_at": now_iso,
        "scale_mm_per_px": meta.scale_mm_per_px,
        "next_label_id": meta.next_label_id,
        "regions": {
            str(k): {"name": v["name"], "vertices": v["vertices"]} for k, v in meta.regions.items()
        },
        "next_line_id": meta.next_line_id,
        "lines": {
            str(k): {
                "name": v["name"],
                "p1": [int(v["p1"][0]), int(v["p1"][1])],
                "p2": [int(v["p2"][0]), int(v["p2"][1])],
            }
            for k, v in meta.lines.items()
        },
    }

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"image{ext}", image_bytes)
        zf.writestr("meta.json", json.dumps(meta_json, indent=2, sort_keys=True))


def save_bundle(
    bundle_path: Path | str,
    source_image_path: Path | str,
    image_shape: tuple[int, int],
    meta: BundleMeta,
) -> None:
    """Convenience wrapper: read source bytes from disk, delegate to save_bundle_from_bytes."""
    src = Path(source_image_path)
    if not src.exists():
        raise FileNotFoundError(src)
    save_bundle_from_bytes(
        bundle_path,
        image_bytes=src.read_bytes(),
        image_ext=src.suffix.lower() or ".bin",
        image_shape=image_shape,
        meta=meta,
    )


def open_bundle(source: BundleSource) -> BundleContents:
    """Parse a :class:`BundleSource` into :class:`BundleContents`.

    Accepts both v1 and v2 bundles. v1 bundles: ignore ``mask.png`` (polygons
    are authoritative), derive ``image_shape`` from the decoded image. v2
    bundles: ``image_shape`` is read from ``meta.json`` directly.
    """
    with zipfile.ZipFile(io.BytesIO(source.data), "r") as zf:
        names = zf.namelist()
        image_name = next((n for n in names if n.startswith("image.")), None)
        if image_name is None:
            raise ValueError(f"bundle missing image.*: {source.name}")
        if "meta.json" not in names:
            raise ValueError(f"bundle missing meta.json: {source.name}")

        image_bytes = zf.read(image_name)
        meta_bytes = zf.read("meta.json")

    meta_json = json.loads(meta_bytes)
    version = meta_json.get("bacmask_version")
    if version not in (BACMASK_VERSION_V1, BACMASK_VERSION):
        raise UnsupportedBundleVersion(version)

    image_arr = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image_arr is None:
        raise ValueError(f"bundle image could not be decoded: {image_name}")

    raw_shape = meta_json.get("image_shape")
    if raw_shape is not None:
        image_shape = (int(raw_shape[0]), int(raw_shape[1]))
    else:
        # v1 fallback: derive from the decoded image.
        image_shape = (int(image_arr.shape[0]), int(image_arr.shape[1]))

    raw_lines = meta_json.get("lines") or {}
    lines: dict[int, dict[str, Any]] = {}
    for k, v in raw_lines.items():
        p1 = v["p1"]
        p2 = v["p2"]
        lines[int(k)] = {
            "name": v["name"],
            "p1": (int(p1[0]), int(p1[1])),
            "p2": (int(p2[0]), int(p2[1])),
        }
    next_line_id = int(meta_json.get("next_line_id", max(lines, default=0) + 1))

    meta = BundleMeta(
        source_filename=meta_json["source_filename"],
        image_shape=image_shape,
        scale_mm_per_px=meta_json.get("scale_mm_per_px"),
        next_label_id=meta_json["next_label_id"],
        regions={int(k): v for k, v in meta_json.get("regions", {}).items()},
        lines=lines,
        next_line_id=next_line_id,
        created_at=meta_json.get("created_at"),
        updated_at=meta_json.get("updated_at"),
    )
    return BundleContents(
        image=image_arr,
        image_ext=Path(image_name).suffix,
        image_bytes=image_bytes,
        meta=meta,
    )


def load_bundle(bundle_path: Path | str) -> BundleContents:
    """Convenience: read + parse a ``.bacmask`` bundle from a filesystem path.

    Equivalent to ``open_bundle(BundleSource.from_path(path))``.
    """
    return open_bundle(BundleSource.from_path(bundle_path))


# ---- helpers -----------------------------------------------------------------


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
