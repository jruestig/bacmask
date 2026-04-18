"""Image helpers: coord transforms (fit-to-widget) and deterministic region palette.

Used by the image canvas widget to map between widget pixel coords and
full-resolution image coords, and to color-code region overlays.
"""

from __future__ import annotations

import colorsys


def fit_to_widget(
    image_size: tuple[int, int],
    widget_size: tuple[int, int],
) -> tuple[float, float, float, float, float]:
    """Compute uniform-scale letterbox fit of ``image_size`` inside ``widget_size``.

    Returns ``(scale, offset_x, offset_y, displayed_w, displayed_h)``.
    The image is centered within the widget along the short axis.
    """
    w, h = image_size
    W, H = widget_size
    if w <= 0 or h <= 0 or W <= 0 or H <= 0:
        return 1.0, 0.0, 0.0, 0.0, 0.0
    s = min(W / w, H / h)
    disp_w = s * w
    disp_h = s * h
    off_x = (W - disp_w) / 2
    off_y = (H - disp_h) / 2
    return s, off_x, off_y, disp_w, disp_h


def display_to_image(
    display_xy: tuple[float, float],
    image_size: tuple[int, int],
    widget_size: tuple[int, int],
) -> tuple[float, float]:
    """Map a widget-space point to full-resolution image-space point."""
    dx, dy = display_xy
    s, off_x, off_y, _, _ = fit_to_widget(image_size, widget_size)
    if s == 0:
        return 0.0, 0.0
    return (dx - off_x) / s, (dy - off_y) / s


def image_to_display(
    image_xy: tuple[float, float],
    image_size: tuple[int, int],
    widget_size: tuple[int, int],
) -> tuple[float, float]:
    """Map a full-resolution image-space point to widget-space point."""
    ix, iy = image_xy
    s, off_x, off_y, _, _ = fit_to_widget(image_size, widget_size)
    return ix * s + off_x, iy * s + off_y


def display_to_image_view(
    display_xy: tuple[float, float],
    image_size: tuple[int, int],
    widget_size: tuple[int, int],
    view_scale: float,
    view_offset: tuple[float, float],
) -> tuple[float, float]:
    """Map a display-space point to image-space, accounting for a view transform.

    ``view_scale`` multiplies the fit-to-widget base scale. ``view_offset`` is a
    translation in display-space pixels (top-down Y, matching :func:`image_to_display`).
    Together they define the view: ``display = fit_base(image) * view_scale + view_offset``.
    """
    dx, dy = display_xy
    vox, voy = view_offset
    s, off_x, off_y, _, _ = fit_to_widget(image_size, widget_size)
    total = s * view_scale
    if total == 0:
        return 0.0, 0.0
    return (dx - off_x - vox) / total, (dy - off_y - voy) / total


def image_to_display_view(
    image_xy: tuple[float, float],
    image_size: tuple[int, int],
    widget_size: tuple[int, int],
    view_scale: float,
    view_offset: tuple[float, float],
) -> tuple[float, float]:
    """Map an image-space point to display-space, accounting for a view transform.

    Inverse of :func:`display_to_image_view`.
    """
    ix, iy = image_xy
    vox, voy = view_offset
    s, off_x, off_y, _, _ = fit_to_widget(image_size, widget_size)
    total = s * view_scale
    return ix * total + off_x + vox, iy * total + off_y + voy


# Deterministic palette using golden-ratio hue spacing — adjacent IDs are
# perceptually distinct, and any label_id >= 1 maps to a stable color.
_GOLDEN_RATIO_CONJUGATE = 0.618033988749895


def region_color(label_id: int) -> tuple[int, int, int]:
    """Deterministic RGB triple (0-255) for a label id.

    ``label_id == 0`` (background) maps to black. Positive IDs distribute around
    the hue wheel by the golden ratio for visually distinct sequential colors.
    """
    if label_id <= 0:
        return (0, 0, 0)
    hue = ((label_id - 1) * _GOLDEN_RATIO_CONJUGATE) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 0.95)
    return int(r * 255), int(g * 255), int(b * 255)
