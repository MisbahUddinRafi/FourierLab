"""
core/masking.py

Frequency-domain masking of k-space: center, outer, and custom
rectangular regions, each either ISOLATED (kept, everything else
zeroed) or REMOVED (zeroed, everything else kept).

This is the direct counterpart of the audio module's
`build_time_freq_mask`: same idea (carve a region out of a
frequency-domain representation), different geometry (a 2D disk
around the k-space center instead of a 1D frequency band).

Why a disk for "center"/"outer" instead of a square?
k-space energy falls off radially from the origin (DC component), not
per-axis, so a circular boundary is the natural way to separate
"low spatial frequency" from "high spatial frequency" content.
"""

import numpy as np


def _radius_grid(shape: tuple) -> np.ndarray:
    """
    Distance from the k-space center for every pixel, normalized so
    that the grid spans roughly [-1, 1] on each axis (corners of a
    square k-space are then at distance sqrt(2) ~= 1.41).
    """
    rows, cols = shape
    y, x = np.mgrid[-1:1:complex(rows), -1:1:complex(cols)]
    return np.sqrt(x ** 2 + y ** 2)


def circular_region(shape: tuple, radius: float) -> np.ndarray:
    """Boolean disk mask: True where distance-from-center <= radius."""
    return _radius_grid(shape) <= radius


def rectangular_region(shape: tuple, kx_range: tuple, ky_range: tuple) -> np.ndarray:
    """
    Boolean rectangular mask in normalized k-space coordinates, each
    axis spanning roughly [-1, 1] (0 = center / DC component).

    kx_range, ky_range : (min, max) tuples in that normalized range.
    """
    rows, cols = shape
    y, x = np.mgrid[-1:1:complex(rows), -1:1:complex(cols)]

    kx_min, kx_max = kx_range
    ky_min, ky_max = ky_range

    return (x >= kx_min) & (x <= kx_max) & (y >= ky_min) & (y <= ky_max)


def build_kspace_mask(
    shape: tuple,
    mask_type: str,
    mode: str,
    radius: float = 0.3,
    kx_range: tuple = (-1.0, 1.0),
    ky_range: tuple = (-1.0, 1.0),
) -> np.ndarray:
    """
    Build a boolean keep-mask over k-space.

    mask_type : "center"  -> a disk around the origin
                "outer"   -> everything outside a disk around the origin
                "custom"  -> a user-specified rectangle
    mode      : "isolate" -> keep ONLY the region, zero everything else
                "remove"  -> zero the region, keep everything else

    Returns
    -------
    keep_mask : boolean 2D array, True = keep this k-space sample.
    """
    if mask_type == "center":
        region = circular_region(shape, radius)
    elif mask_type == "outer":
        region = ~circular_region(shape, radius)
    elif mask_type == "custom":
        region = rectangular_region(shape, kx_range, ky_range)
    else:
        raise ValueError(f"Unknown mask_type '{mask_type}'.")

    if mode == "isolate":
        keep_mask = region
    elif mode == "remove":
        keep_mask = ~region
    else:
        raise ValueError(f"Unknown mode '{mode}', expected 'isolate' or 'remove'.")

    return keep_mask


def apply_mask(kspace: np.ndarray, keep_mask: np.ndarray) -> np.ndarray:
    """Zero out every k-space sample where keep_mask is False."""
    return kspace * keep_mask
