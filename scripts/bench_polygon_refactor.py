"""Wave-0 benchmark harness for the 030 polygon-refactor.

Headless (no Kivy window). Drives MaskService through the paths that 030
changes — load, lasso add, undo/redo, brush commit, area rows, save, export —
and prints each step's wall-clock in milliseconds. Re-run post-refactor to
fill the delta column in ``knowledge/030-polygons-are-mask-truth.md``.

Usage: ``uv run python scripts/bench_polygon_refactor.py``
"""

from __future__ import annotations

import random
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from bacmask.services.mask_service import MaskService

REPO_ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIR = REPO_ROOT / "images"
PREFERRED = IMAGES_DIR / "20251112093808947.tif"
SEED = 1234


def pick_fixture() -> Path:
    if PREFERRED.exists():
        return PREFERRED
    tiffs = sorted(IMAGES_DIR.glob("*.tif")) + sorted(IMAGES_DIR.glob("*.tiff"))
    if not tiffs:
        print("no TIFF fixture found in images/", file=sys.stderr)
        sys.exit(2)
    tiffs.sort(key=lambda p: p.stat().st_size)
    return tiffs[0]


def synth_lassos(h: int, w: int, n: int) -> list[list[tuple[int, int]]]:
    """N small circular-ish lassos scattered across the image."""
    rng = random.Random(SEED)
    out: list[list[tuple[int, int]]] = []
    r = max(20, min(h, w) // 40)
    for _ in range(n):
        cx = rng.randint(r + 5, w - r - 5)
        cy = rng.randint(r + 5, h - r - 5)
        pts = []
        for i in range(32):
            theta = 2.0 * np.pi * i / 32
            pts.append((int(cx + r * np.cos(theta)), int(cy + r * np.sin(theta))))
        out.append(pts)
    return out


class Timer:
    def __init__(self) -> None:
        self.rows: list[tuple[str, float]] = []

    def run(self, name: str, fn) -> None:
        t0 = time.perf_counter()
        fn()
        dt_ms = (time.perf_counter() - t0) * 1000.0
        self.rows.append((name, dt_ms))
        print(f"{name}: {dt_ms:.2f} ms")


def main() -> int:
    fixture = pick_fixture()
    svc = MaskService()
    timer = Timer()

    timer.run("load_image", lambda: svc.load_image(fixture))
    h, w = svc.state.image.shape[:2]
    print(f"fixture: {fixture} ({h}x{w})")

    lassos = synth_lassos(h, w, 10)

    def _add_lassos() -> None:
        for pts in lassos:
            svc.begin_lasso(pts[0])
            for p in pts[1:]:
                svc.add_lasso_point(p)
            svc.close_lasso()

    timer.run("lasso_add_x10", _add_lassos)

    def _undo5() -> None:
        for _ in range(5):
            svc.undo()

    def _redo5() -> None:
        for _ in range(5):
            svc.redo()

    timer.run("undo_x5", _undo5)
    timer.run("redo_x5", _redo5)

    # Brush add on the first remaining region: stamp a horizontal streak through
    # a point just outside its boundary so the stroke actually changes things.
    target_id = min(svc.state.regions)
    verts = np.asarray(svc.state.regions[target_id]["vertices"], dtype=np.int32)
    cx = int(verts[:, 0].mean())
    cy = int(verts[:, 1].mean())
    svc.select_region(target_id)
    svc.set_brush_default_mode("add")
    svc.set_brush_radius(6)

    def _brush_stroke() -> None:
        svc.begin_brush_stroke((cx, cy))
        for dx in range(-20, 21, 4):
            svc.add_brush_sample((cx + dx, cy))
        svc.end_brush_stroke()

    timer.run("brush_add_stroke", _brush_stroke)

    timer.run("compute_area_rows", lambda: svc.compute_area_rows())

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bundle = tmp_path / "bench.bacmask"
        csv = tmp_path / "bench_areas.csv"
        timer.run("save_bundle", lambda: svc.save_bundle(bundle))
        timer.run("export_csv", lambda: svc.export_csv(csv))

    print()
    print("| Step | Baseline (ms) |")
    print("|---|---:|")
    for name, ms in timer.rows:
        print(f"| {name} | {ms:.2f} |")

    return 0


if __name__ == "__main__":
    sys.exit(main())
