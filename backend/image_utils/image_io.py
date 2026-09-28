"""
image_utils/image_io.py

Unified loader for all supported medical and standard image formats:
  - Standard images  : .png, .jpg, .jpeg  (via Pillow)
  - DICOM            : .dcm               (via pydicom)
  - fastMRI HDF5     : .h5                (via h5py  -- raw k-space, complex)
  - NIfTI            : .nii, .nii.gz      (via nibabel)
  - Synthetic        : Shepp-Logan phantom (generated on-the-fly)

Return convention for loaders:
  load_*  -> returns (image_array, raw_kspace | None)
    image_array : float64, [0,1]-normalised 2D spatial image
    raw_kspace  : complex128 2D array when the file already contains k-space
                  (fastMRI .h5), otherwise None (caller builds k-space via FFT)
"""

import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image

EPS = 1e-12


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def normalize_image(image: np.ndarray) -> np.ndarray:
    """Rescale a 2D float array to [0, 1]."""
    image = np.asarray(image, dtype=np.float64)
    image = image - image.min()
    return image / (image.max() + EPS)


def _center_crop_or_pad(arr: np.ndarray, size: int) -> np.ndarray:
    """Crop the larger dimension and pad the smaller dimension to reach (size, size)."""
    h, w = arr.shape

    # Crop
    if h > size:
        y0 = (h - size) // 2
        arr = arr[y0: y0 + size, :]
        h = size
    if w > size:
        x0 = (w - size) // 2
        arr = arr[:, x0: x0 + size]
        w = size

    # Pad
    pad_h = (size - h) // 2
    pad_w = (size - w) // 2
    arr = np.pad(
        arr,
        ((pad_h, size - h - pad_h), (pad_w, size - w - pad_w)),
        mode="constant",
    )
    return arr


def _resize_to_square(image: np.ndarray, size: int) -> np.ndarray:
    """Resize a 2-D float array to (size, size) using Pillow LANCZOS."""
    img_uint8 = (np.clip(normalize_image(image), 0, 1) * 255).astype(np.uint8)
    pil_img = Image.fromarray(img_uint8, mode="L")
    pil_img = pil_img.resize((size, size), Image.Resampling.LANCZOS)
    return normalize_image(np.asarray(pil_img, dtype=np.float64))


# ---------------------------------------------------------------------------
# Standard image loader (.png / .jpg / .jpeg)
# ---------------------------------------------------------------------------

def load_uploaded_image(path: str, image_size: int) -> np.ndarray:
    """Load a standard raster image, convert to grayscale, resize, normalise."""
    image = Image.open(path).convert("L")
    image = image.resize((image_size, image_size), Image.Resampling.LANCZOS)
    return normalize_image(np.asarray(image, dtype=np.float64))


# ---------------------------------------------------------------------------
# DICOM loader (.dcm)
# ---------------------------------------------------------------------------

def load_dicom(path: str, image_size: int) -> tuple:
    """
    Load a DICOM file, extract pixel data, resize, and normalise.

    Returns (image_array, None)
    - image_array : float64 [0,1] spatial image
    - None        : k-space must be built by the caller via 2D FFT
    """
    try:
        import pydicom
    except ImportError:
        raise RuntimeError(
            "pydicom is not installed. Run: pip install pydicom"
        )

    ds = pydicom.dcmread(path)
    pixel_array = ds.pixel_array.astype(np.float64)

    # Handle multi-frame DICOM (take the middle slice)
    if pixel_array.ndim == 3:
        mid = pixel_array.shape[0] // 2
        pixel_array = pixel_array[mid]

    image_array = _resize_to_square(pixel_array, image_size)
    return image_array, None          # k-space built downstream


# ---------------------------------------------------------------------------
# fastMRI HDF5 loader (.h5)
# ---------------------------------------------------------------------------

def load_h5_kspace(path: str, image_size: int) -> tuple:
    """
    Load a fastMRI-style HDF5 file that already contains raw k-space.

    The HDF5 file must have a dataset named 'kspace'.
    Format: complex float32/64 with shape  (slices, coils, rows, cols)
            or (rows, cols) for single-coil single-slice files.

    Processing:
    1.  If multi-slice/multi-coil: take the middle slice, RSS-combine coils.
    2.  Crop / pad to image_size × image_size.
    3.  Reconstruct a reference spatial image via iFFT for display.

    Returns (image_array, raw_kspace)
    - image_array : float64 [0,1] – iFFT of the loaded k-space (for display)
    - raw_kspace  : complex128 2D – the actual k-space data (used directly in
                    masking / retention without re-computing FFT)
    """
    try:
        import h5py
    except ImportError:
        raise RuntimeError(
            "h5py is not installed. Run: pip install h5py"
        )

    with h5py.File(path, "r") as f:
        if "kspace" not in f:
            available = list(f.keys())
            raise ValueError(
                f"No 'kspace' key found in {path}. "
                f"Available keys: {available}"
            )
        raw = f["kspace"][:]   # load everything into RAM

    raw = np.asarray(raw, dtype=np.complex128)

    # --- Normalise dimensions ---
    # Expected fastMRI shapes:
    #   (num_slices, num_coils, num_rows, num_cols)  full-resolution
    #   (num_slices, num_rows, num_cols)              single-coil
    #   (num_rows, num_cols)                          already 2D
    if raw.ndim == 4:
        mid_slice = raw.shape[0] // 2
        coil_slices = raw[mid_slice]          # (num_coils, rows, cols)
        # Root-Sum-of-Squares coil combination in k-space → iFFT per coil then RSS
        imgs = np.stack(
            [np.abs(np.fft.ifft2(np.fft.ifftshift(c))) for c in coil_slices]
        )
        img_rss = np.sqrt(np.sum(imgs ** 2, axis=0))
        # Re-compute a single-coil k-space representative by FFT of the RSS image
        kspace_2d = np.fft.fftshift(np.fft.fft2(img_rss))
    elif raw.ndim == 3:
        mid_slice = raw.shape[0] // 2
        kspace_2d = raw[mid_slice]            # (rows, cols)
    elif raw.ndim == 2:
        kspace_2d = raw
    else:
        raise ValueError(
            f"Unexpected k-space ndim={raw.ndim} in {path}. "
            "Expected 2, 3, or 4 dimensions."
        )

    # --- Crop / pad to square image_size × image_size ---
    # Work in k-space: centre → crop/pad → keep centred
    rows, cols = kspace_2d.shape
    if rows != cols or rows != image_size:
        # Convert to spatial, resize, convert back – ensures square
        spatial = np.abs(np.fft.ifft2(np.fft.ifftshift(kspace_2d)))
        spatial_sq = _resize_to_square(spatial, image_size)
        kspace_2d = np.fft.fftshift(np.fft.fft2(spatial_sq))

    # Reference spatial image for display
    image_array = normalize_image(
        np.abs(np.fft.ifft2(np.fft.ifftshift(kspace_2d)))
    )

    return image_array, kspace_2d


# ---------------------------------------------------------------------------
# NIfTI loader (.nii / .nii.gz)
# ---------------------------------------------------------------------------

def load_nifti(path: str, image_size: int) -> tuple:
    """
    Load a NIfTI file (Brain MRI, fMRI, etc.) and extract a 2D slice.

    For 3D/4D volumes the middle axial slice is taken.

    Returns (image_array, None)
    - image_array : float64 [0,1] spatial image
    - None        : k-space built downstream by 2D FFT
    """
    try:
        import nibabel as nib
    except ImportError:
        raise RuntimeError(
            "nibabel is not installed. Run: pip install nibabel"
        )

    img_nib = nib.load(path)
    data = np.asarray(img_nib.dataobj, dtype=np.float64)

    # Take middle slice from 3D/4D
    if data.ndim == 4:
        data = data[..., data.shape[3] // 2]     # time point
    if data.ndim == 3:
        data = data[:, :, data.shape[2] // 2]    # axial slice

    if data.ndim != 2:
        raise ValueError(
            f"Could not reduce NIfTI data to 2D (shape={data.shape})."
        )

    image_array = _resize_to_square(data, image_size)
    return image_array, None          # k-space built downstream


# ---------------------------------------------------------------------------
# Unified dispatcher
# ---------------------------------------------------------------------------

def load_medical_image(path: str, image_size: int) -> tuple:
    """
    Detect file type by extension and dispatch to the correct loader.

    Returns (image_array, raw_kspace | None)
    - image_array : float64 [0,1] normalised 2D spatial image
    - raw_kspace  : complex128 2D array  — only non-None for .h5 files
                    (all other formats return None; caller computes FFT)
    """
    suffix = Path(path).suffix.lower()

    if suffix in {".png", ".jpg", ".jpeg"}:
        return load_uploaded_image(path, image_size), None

    if suffix == ".dcm":
        return load_dicom(path, image_size)

    if suffix == ".h5":
        return load_h5_kspace(path, image_size)

    if suffix in {".nii", ".gz"}:           # .nii.gz has final suffix .gz
        return load_nifti(path, image_size)

    raise ValueError(
        f"Unsupported format '{suffix}'. "
        "Supported: .png .jpg .jpeg .dcm .h5 .nii .nii.gz"
    )


# ---------------------------------------------------------------------------
# Synthetic phantom
# ---------------------------------------------------------------------------

def create_phantom(size: int) -> np.ndarray:
    """
    Shepp-Logan-like synthetic MRI phantom: overlapping ellipses of
    different intensity, the standard test image for MRI reconstruction
    demos because it has known, controllable structure at multiple scales.
    """
    y, x = np.mgrid[-1:1:complex(size), -1:1:complex(size)]
    phantom = np.zeros((size, size))

    # amplitude, x0, y0, rx, ry, angle_degrees
    ellipses = [
        (1.00,  0.00,  0.00, 0.78, 0.95,   0),
        (-0.80, 0.00, -0.02, 0.32, 0.42,   0),
        (-0.20, 0.22,  0.00, 0.15, 0.22, -20),
        (-0.20,-0.22,  0.00, 0.15, 0.22,  20),
        ( 0.10, 0.00,  0.35, 0.10, 0.15,   0),
        ( 0.10, 0.00, -0.35, 0.10, 0.15,   0),
    ]

    for amplitude, x0, y0, rx, ry, angle in ellipses:
        theta = np.deg2rad(angle)
        xr = (x - x0) * np.cos(theta) + (y - y0) * np.sin(theta)
        yr = -(x - x0) * np.sin(theta) + (y - y0) * np.cos(theta)
        ellipse = ((xr / rx) ** 2 + (yr / ry) ** 2) <= 1
        phantom[ellipse] += amplitude

    phantom = np.clip(phantom, 0, None)
    return normalize_image(phantom)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def image_to_png_bytes(image: np.ndarray) -> bytes:
    """Convert a [0, 1]-normalised array to PNG bytes."""
    image_uint8 = (np.clip(image, 0, 1) * 255).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(image_uint8).save(buffer, format="PNG")
    return buffer.getvalue()


def image_to_base64(image: np.ndarray) -> str:
    """Convert a [0, 1]-normalised array to a base64-encoded PNG string."""
    return base64.b64encode(image_to_png_bytes(image)).decode("ascii")
