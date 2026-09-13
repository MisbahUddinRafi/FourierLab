"""
utils/image_io.py

Getting an input image into the app (upload or synthetic phantom) and
getting a result back out (PNG download).
"""

import io

import numpy as np
from PIL import Image

EPS = 1e-12


def normalize_image(image: np.ndarray) -> np.ndarray:
    """Rescale an array to [0, 1]."""
    image = np.asarray(image, dtype=np.float64)
    image = image - image.min()
    return image / (image.max() + EPS)


def load_uploaded_image(uploaded_file, image_size: int) -> np.ndarray:
    """Load an uploaded image, convert to grayscale, resize to a square, normalize to [0, 1]."""
    image = Image.open(uploaded_file).convert("L")
    image = image.resize((image_size, image_size), Image.Resampling.LANCZOS)
    return normalize_image(np.asarray(image, dtype=np.float64))


def create_phantom(size: int) -> np.ndarray:
    """
    A simple Shepp-Logan-like synthetic MRI phantom: a handful of
    overlapping ellipses of different intensity, which is the
    standard synthetic test image for MRI reconstruction demos
    because it has known, controllable structure at multiple scales.
    """
    y, x = np.mgrid[-1:1:complex(size), -1:1:complex(size)]
    phantom = np.zeros((size, size))

    # amplitude, x0, y0, rx, ry, angle_degrees
    ellipses = [
        (1.00, 0.00, 0.00, 0.78, 0.95, 0),
        (-0.80, 0.00, -0.02, 0.32, 0.42, 0),
        (-0.20, 0.22, 0.00, 0.15, 0.22, -20),
        (-0.20, -0.22, 0.00, 0.15, 0.22, 20),
        (0.10, 0.00, 0.35, 0.10, 0.15, 0),
        (0.10, 0.00, -0.35, 0.10, 0.15, 0),
    ]

    for amplitude, x0, y0, rx, ry, angle in ellipses:
        theta = np.deg2rad(angle)
        xr = (x - x0) * np.cos(theta) + (y - y0) * np.sin(theta)
        yr = -(x - x0) * np.sin(theta) + (y - y0) * np.cos(theta)
        ellipse = ((xr / rx) ** 2 + (yr / ry) ** 2) <= 1
        phantom[ellipse] += amplitude

    phantom = np.clip(phantom, 0, None)
    return normalize_image(phantom)


def image_to_png_bytes(image: np.ndarray) -> bytes:
    """Convert a [0, 1]-normalized array to PNG bytes for a download button."""
    image_uint8 = (np.clip(image, 0, 1) * 255).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(image_uint8).save(buffer, format="PNG")
    return buffer.getvalue()
