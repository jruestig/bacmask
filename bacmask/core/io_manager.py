"""I/O for images, .bacmask bundles, and sibling CSV.

See knowledge/011 (CSV), 015 (bundle), 024 (mask export deferred),
025 (polygons canonical).
"""

from __future__ import annotations

import csv
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


# ---- image I/O ---------------------------------------------------------------


def load_image(path: Path | str) -> np.ndarray:
    """Load an image preserving bit depth and channel count.

    Color images come back as BGR (cv2 convention). Caller converts if needed.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    # Read via np.fromfile + imdecode so Windows paths with non-ASCII
    # characters (umlauts, accents) work — cv2.imread uses ANSI APIs.
    buf = np.fromfile(str(p), dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"could not decode image: {p}")
    return img


# ---- CSV ---------------------------------------------------------------------


@dataclass
class AreaRow:
    filename: str
    region_id: int
    region_name: str
    area_px: float  # polygon shoelace area in px² (knowledge/030)
    area_mm2: float | None  # None -> empty cell (uncalibrated)
    scale_factor: float | None  # None -> empty cell (uncalibrated)


def save_areas_csv(path: Path | str, rows: list[AreaRow]) -> None:
    with open(path, "w", newline="") as f:
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
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class BundleContents:
    image: np.ndarray
    image_ext: str  # ".tif", ".png", ... (with leading dot)
    meta: BundleMeta


def save_bundle_from_bytes(
    bundle_path: Path | str,
    *,
    image_bytes: bytes,
    image_ext: str,
    image_shape: tuple[int, int],
    meta: BundleMeta,
) -> None:
    """Write a v2 .bacmask ZIP given raw source-image bytes and extension.

    v2 bundles contain only ``image.<ext>`` and ``meta.json``. Raster masks
    are not stored; polygons in ``meta.regions`` are canonical (knowledge/015,
    knowledge/025). Raster export is a separate, deferred operation
    (knowledge/024).
    """
    ext = image_ext.lower() if image_ext else ".bin"
    if not ext.startswith("."):
        ext = "." + ext

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
    }

    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
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


def load_bundle(bundle_path: Path | str) -> BundleContents:
    """Load a .bacmask bundle. Accepts both v1 and v2.

    v1 bundles: ignore ``mask.png`` (polygons are authoritative), derive
    ``image_shape`` from the decoded image. v2 bundles: ``image_shape`` is
    read from ``meta.json`` directly.
    """
    p = Path(bundle_path)
    if not p.exists():
        raise FileNotFoundError(p)

    with zipfile.ZipFile(p, "r") as zf:
        names = zf.namelist()
        image_name = next((n for n in names if n.startswith("image.")), None)
        if image_name is None:
            raise ValueError(f"bundle missing image.*: {p}")
        if "meta.json" not in names:
            raise ValueError(f"bundle missing meta.json: {p}")

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

    meta = BundleMeta(
        source_filename=meta_json["source_filename"],
        image_shape=image_shape,
        scale_mm_per_px=meta_json.get("scale_mm_per_px"),
        next_label_id=meta_json["next_label_id"],
        regions={int(k): v for k, v in meta_json.get("regions", {}).items()},
        created_at=meta_json.get("created_at"),
        updated_at=meta_json.get("updated_at"),
    )
    return BundleContents(
        image=image_arr,
        image_ext=Path(image_name).suffix,
        meta=meta,
    )


# ---- helpers -----------------------------------------------------------------


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
