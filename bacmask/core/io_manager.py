"""I/O for images, mask PNGs, .bacmask bundles, and sibling CSV.

See knowledge/011 (CSV), 012 (PNG), 015 (bundle), 018 (dim mismatch).
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

BACMASK_VERSION = 1

CSV_HEADER = [
    "filename",
    "region_id",
    "region_name",
    "area_px",
    "area_mm2",
    "scale_factor",
]


class MaskDimensionMismatch(Exception):
    def __init__(self, mask_shape: tuple[int, ...], image_shape: tuple[int, ...]) -> None:
        super().__init__(f"mask shape {mask_shape} does not match image shape {image_shape}")
        self.mask_shape = mask_shape
        self.image_shape = image_shape


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
    img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"could not decode image: {p}")
    return img


# ---- mask PNG I/O ------------------------------------------------------------


def save_mask_png(path: Path | str, label_map: np.ndarray) -> None:
    if label_map.dtype != np.uint16:
        raise TypeError(f"label_map must be uint16, got {label_map.dtype}")
    if label_map.ndim != 2:
        raise ValueError(f"label_map must be 2-D, got shape {label_map.shape}")
    ok = cv2.imwrite(str(path), label_map)
    if not ok:
        raise OSError(f"failed to write mask PNG to {path}")


def load_mask_png(path: Path | str) -> np.ndarray:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    arr = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
    if arr is None:
        raise ValueError(f"could not decode mask PNG: {p}")
    if arr.dtype != np.uint16:
        raise ValueError(f"mask PNG is not 16-bit grayscale (got {arr.dtype})")
    if arr.ndim != 2:
        raise ValueError(f"mask PNG must be 2-D, got shape {arr.shape}")
    return arr


def load_mask_for_image(mask_path: Path | str, image_shape: tuple[int, int]) -> np.ndarray:
    """Load a mask and validate it matches ``image_shape``.

    Raises :class:`MaskDimensionMismatch` when shapes differ. Callers in the
    service layer decide whether to prompt + resize (non-default) or reject
    (default). See knowledge/018.
    """
    arr = load_mask_png(mask_path)
    if arr.shape != image_shape:
        raise MaskDimensionMismatch(arr.shape, image_shape)
    return arr


# ---- CSV ---------------------------------------------------------------------


@dataclass
class AreaRow:
    filename: str
    region_id: int
    region_name: str
    area_px: int
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
    scale_mm_per_px: float | None
    next_label_id: int
    regions: dict[int, dict[str, Any]]
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class BundleContents:
    image: np.ndarray
    image_ext: str  # ".tif", ".png", ... (with leading dot)
    label_map: np.ndarray
    meta: BundleMeta


def save_bundle_from_bytes(
    bundle_path: Path | str,
    *,
    image_bytes: bytes,
    image_ext: str,
    label_map: np.ndarray,
    meta: BundleMeta,
) -> None:
    """Write a .bacmask ZIP given raw source-image bytes and extension."""
    if label_map.dtype != np.uint16:
        raise TypeError(f"label_map must be uint16, got {label_map.dtype}")

    ext = image_ext.lower() if image_ext else ".bin"
    if not ext.startswith("."):
        ext = "." + ext

    now_iso = _utcnow_iso()
    meta_json = {
        "bacmask_version": BACMASK_VERSION,
        "source_filename": meta.source_filename,
        "created_at": meta.created_at or now_iso,
        "updated_at": now_iso,
        "scale_mm_per_px": meta.scale_mm_per_px,
        "next_label_id": meta.next_label_id,
        "regions": {
            str(k): {"name": v["name"], "vertices": v["vertices"]} for k, v in meta.regions.items()
        },
    }

    ok, mask_buf = cv2.imencode(".png", label_map)
    if not ok:
        raise OSError("failed to encode mask PNG")

    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"image{ext}", image_bytes)
        zf.writestr("mask.png", mask_buf.tobytes())
        zf.writestr("meta.json", json.dumps(meta_json, indent=2, sort_keys=True))


def save_bundle(
    bundle_path: Path | str,
    source_image_path: Path | str,
    label_map: np.ndarray,
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
        label_map=label_map,
        meta=meta,
    )


def load_bundle(bundle_path: Path | str) -> BundleContents:
    p = Path(bundle_path)
    if not p.exists():
        raise FileNotFoundError(p)

    with zipfile.ZipFile(p, "r") as zf:
        names = zf.namelist()
        image_name = next((n for n in names if n.startswith("image.")), None)
        if image_name is None:
            raise ValueError(f"bundle missing image.*: {p}")
        if "mask.png" not in names:
            raise ValueError(f"bundle missing mask.png: {p}")
        if "meta.json" not in names:
            raise ValueError(f"bundle missing meta.json: {p}")

        image_bytes = zf.read(image_name)
        mask_bytes = zf.read("mask.png")
        meta_bytes = zf.read("meta.json")

    meta_json = json.loads(meta_bytes)
    version = meta_json.get("bacmask_version")
    if version != BACMASK_VERSION:
        raise UnsupportedBundleVersion(version)

    image_arr = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image_arr is None:
        raise ValueError(f"bundle image could not be decoded: {image_name}")

    mask_arr = cv2.imdecode(np.frombuffer(mask_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if mask_arr is None:
        raise ValueError("bundle mask.png could not be decoded")
    if mask_arr.dtype != np.uint16:
        raise ValueError(f"bundle mask is not 16-bit grayscale (got {mask_arr.dtype})")

    meta = BundleMeta(
        source_filename=meta_json["source_filename"],
        scale_mm_per_px=meta_json.get("scale_mm_per_px"),
        next_label_id=meta_json["next_label_id"],
        regions={int(k): v for k, v in meta_json.get("regions", {}).items()},
        created_at=meta_json.get("created_at"),
        updated_at=meta_json.get("updated_at"),
    )
    return BundleContents(
        image=image_arr,
        image_ext=Path(image_name).suffix,
        label_map=mask_arr,
        meta=meta,
    )


# ---- helpers -----------------------------------------------------------------


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
