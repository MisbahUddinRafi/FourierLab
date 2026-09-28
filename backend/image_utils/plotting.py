"""
image_utils/plotting.py

Rendering utilities for MRI k-space and reconstructed images.
Converts 2D spatial and frequency-domain arrays into base64-encoded
PNG data with appropriate colormaps (Viridis for k-space log-magnitude,
Twilight for phase, Inferno for error heatmap, RdYlGn for SSIM map).
"""

import base64
import io
import os
import numpy as np
from PIL import Image

# Ensure writable MPL config dir to prevent warnings
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

try:
    import matplotlib
    import matplotlib.cm as cm

    def get_colormap(name: str):
        if hasattr(matplotlib, "colormaps"):
            return matplotlib.colormaps[name]
        elif hasattr(cm, "get_cmap"):
            return cm.get_cmap(name)
        raise RuntimeError("No colormap accessor found in matplotlib")
except Exception:
    get_colormap = None


_FALLBACK_STOPS = {
    "viridis":  ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"],
    "inferno":  ["#000004", "#420a68", "#932667", "#dd513a", "#fca50a", "#fcffa4"],
    "RdYlGn":   ["#a50026", "#f46d43", "#fee08b", "#a6d96a", "#006837"],
    "twilight": ["#e2d9e2", "#6a7fc0", "#2f1437", "#c47a68", "#e2d9e2"],
}


def _fallback_cmap(name):
    stops = _FALLBACK_STOPS.get(name, _FALLBACK_STOPS["viridis"])
    pts = np.array([[int(s[i:i+2], 16) for i in (1, 3, 5)] for s in stops], float)
    xs = np.linspace(0, 1, len(pts))

    def cmap(v):
        v = np.asarray(v)
        rgb = np.stack([np.interp(v, xs, pts[:, c]) for c in range(3)], axis=-1)
        a = np.full(v.shape + (1,), 255.0)
        return np.concatenate([rgb, a], axis=-1) / 255.0
    return cmap


def array_to_colormap_png_bytes(
    array: np.ndarray,
    cmap_name: str = "viridis",
    vmin: float = None,
    vmax: float = None,
) -> bytes:
    """Map a 2D float array through a colormap and encode as PNG bytes."""
    arr = np.asarray(array, dtype=np.float64)
    if vmin is None:
        vmin = float(np.nanmin(arr))
    if vmax is None:
        vmax = float(np.nanmax(arr))
    denom = vmax - vmin if abs(vmax - vmin) > 1e-12 else 1.0
    norm_arr = np.clip((arr - vmin) / denom, 0.0, 1.0)

    cmap = get_colormap(cmap_name) if get_colormap is not None else _fallback_cmap(cmap_name)
    rgba = (cmap(norm_arr) * 255).astype(np.uint8)
    img = Image.fromarray(rgba)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def array_to_colormap_base64(
    array: np.ndarray,
    cmap_name: str = "viridis",
    vmin: float = None,
    vmax: float = None,
) -> str:
    """Map a 2D float array through a colormap and return base64 PNG data."""
    return base64.b64encode(
        array_to_colormap_png_bytes(array, cmap_name, vmin, vmax)
    ).decode("ascii")


def kspace_magnitude_base64(log_magnitude: np.ndarray) -> str:
    """Log-magnitude k-space in Viridis colormap."""
    return array_to_colormap_base64(log_magnitude, "viridis", 0.0, 1.0)


def phase_map_base64(phase: np.ndarray) -> str:
    """Spatial or k-space phase in Twilight colormap in [-pi, pi]."""
    return array_to_colormap_base64(phase, "twilight", -np.pi, np.pi)


def error_heatmap_base64(error_map: np.ndarray) -> str:
    """Pixelwise error heatmap in Inferno colormap."""
    return array_to_colormap_base64(error_map, "inferno", 0.0, None)


def ssim_map_base64(ssim_map: np.ndarray) -> str:
    """Local SSIM map in RdYlGn colormap from 0 (red) to 1 (green)."""
    return array_to_colormap_base64(ssim_map, "RdYlGn", 0.0, 1.0)


def mask_overlay_base64(log_magnitude: np.ndarray, keep_mask: np.ndarray) -> str:
    """
    Dim unselected samples by 0.15 to clearly highlight the kept region
    against the full k-space magnitude spectrum.
    """
    display = log_magnitude.copy()
    display[~keep_mask] *= 0.15
    return array_to_colormap_base64(display, "viridis", 0.0, 1.0)