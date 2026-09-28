"""
routes/image_routes.py

FastAPI router for /api/image endpoints.
"""

import base64
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from image_core.kspace_engine import (
    fft2_centered,
    ifft2_centered,
    magnitude_phase,
    combine_magnitude_phase,
    kspace_log_magnitude,
    create_complex_image,
)
from image_core.masking import build_kspace_mask, apply_mask
from image_core.reconstruction import (
    retain_center_fraction,
    retain_top_magnitude,
    retention_sweep,
)
from image_core.metrics import mse_metric, psnr_metric, ssim_metric, error_heatmap
from image_utils.image_io import (
    load_medical_image,
    create_phantom,
    normalize_image,
    image_to_base64,
)
from image_utils.plotting import (
    kspace_magnitude_base64,
    phase_map_base64,
    error_heatmap_base64,
    ssim_map_base64,
    mask_overlay_base64,
)

router = APIRouter()

BASE_DIR   = Path(__file__).resolve().parent.parent
IMAGE_ROOT = BASE_DIR / "assets" / "images"
SAMPLES_DIR = IMAGE_ROOT / "samples"
SAVED_DIR   = IMAGE_ROOT / "saved"
UPLOADS_DIR = IMAGE_ROOT / "_uploads"

for d in [SAMPLES_DIR, SAVED_DIR, UPLOADS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".dcm", ".h5", ".nii", ".gz"}
SWEEP_FRACTIONS    = [0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0]

# -------------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------------

def _is_raw_kspace_source(source: str) -> bool:
    """Return True when the source file already contains raw k-space (.h5)."""
    return Path(source).suffix.lower() == ".h5"


def _build_full_kspace(img: np.ndarray, raw_kspace, phase_strength: float):
    if raw_kspace is not None:
        full_kspace = raw_kspace.astype(np.complex128)
        phase_map   = np.zeros_like(img, dtype=np.float64)
        return img, full_kspace, phase_map

    complex_image, phase_map = create_complex_image(img, phase_strength)
    full_kspace = fft2_centered(complex_image)
    return img, full_kspace, phase_map


def resolve_source(source: str, resolution: int):
    if source == "synthetic_phantom":
        return create_phantom(resolution), None

    path = (IMAGE_ROOT / source).resolve()
    if IMAGE_ROOT.resolve() not in path.parents:
        raise HTTPException(400, "Invalid source path.")
    if not path.is_file():
        raise HTTPException(404, f"Image source not found: {source}")

    try:
        return load_medical_image(str(path), resolution)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(400, f"Could not load image: {exc}")


def sanitize_val(val: float, default=None):
    return float(val) if np.isfinite(val) else default


def _center_energy(kspace: np.ndarray) -> float:
    rows, cols = kspace.shape
    cy, cx = rows // 2, cols // 2
    r_core = max(2, int(0.15 * min(rows, cols)))
    y, x = np.ogrid[:rows, :cols]
    center_disk = ((x - cx) ** 2 + (y - cy) ** 2) <= r_core ** 2
    total = float(np.sum(np.abs(kspace) ** 2)) + 1e-12
    center = float(np.sum(np.abs(kspace[center_disk]) ** 2))
    return round((center / total) * 100.0, 1)


# -------------------------------------------------------------------------
# Pydantic models
# -------------------------------------------------------------------------

class ImageAnalyzeRequest(BaseModel):
    source: str
    resolution: int   = 160
    phase_strength: float = 0.6


class ImageComponentRequest(BaseModel):
    source: str
    resolution: int   = 160
    phase_strength: float = 0.6
    mode: str = "both"


class ImageMaskRequest(BaseModel):
    source: str
    resolution: int   = 160
    phase_strength: float = 0.6
    mask_type: str = "center"
    mode: str      = "isolate"
    radius: float  = 0.25
    kx_min: float  = -0.4
    kx_max: float  =  0.4
    ky_min: float  = -0.4
    ky_max: float  =  0.4


class ImageRetainRequest(BaseModel):
    source: str
    resolution: int   = 160
    phase_strength: float = 0.6
    strategy: str = "center_radius"
    fraction: float = 0.25


class ImageSweepRequest(BaseModel):
    source: str
    resolution: int   = 160
    phase_strength: float = 0.6
    strategy: str = "center_radius"


class ImageSaveRequest(BaseModel):
    image_base64: str
    label: str = "result"


# -------------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------------

@router.get("/library")
def get_library():
    samples = sorted(
        p.name for p in SAMPLES_DIR.glob("*")
        if p.suffix.lower() in ALLOWED_EXTENSIONS
    )
    saved = sorted(
        p.name for p in SAVED_DIR.glob("*")
        if p.suffix.lower() in ALLOWED_EXTENSIONS
    )
    return {"samples": samples, "saved": saved}


@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    filename = file.filename or ""
    if filename.endswith(".nii.gz"):
        ext = ".gz"
    else:
        ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext}'. "
            f"Allowed: PNG · JPG · JPEG · DCM · H5 · NII · NII.GZ"
        )

    dest = UPLOADS_DIR / f"{uuid.uuid4().hex}{ext}"
    dest.write_bytes(await file.read())

    try:
        img_array, _ = load_medical_image(str(dest), 160)
        preview_b64 = image_to_base64(img_array)
    except RuntimeError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(exc))
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not decode file: {exc}")

    return {
        "source":      f"_uploads/{dest.name}",
        "filename":    filename,
        "format":      ext.lstrip(".").upper(),
        "is_kspace":   ext == ".h5",
        "preview_b64": preview_b64,
    }


@router.post("/analyze")
def analyze_image(req: ImageAnalyzeRequest):
    img, raw_kspace = resolve_source(req.source, req.resolution)
    img, full_kspace, phase_map = _build_full_kspace(img, raw_kspace, req.phase_strength)

    kspace_log_mag = kspace_log_magnitude(full_kspace)
    kspace_phase   = np.angle(full_kspace)
    sanity_recon   = normalize_image(np.abs(ifft2_centered(full_kspace)))
    is_raw_kspace  = raw_kspace is not None

    return {
        "resolution":         req.resolution,
        "phase_strength":     req.phase_strength,
        "is_raw_kspace":      is_raw_kspace,
        "original_b64":       image_to_base64(img),
        "kspace_mag_b64":     kspace_magnitude_base64(kspace_log_mag),
        "recon_b64":          image_to_base64(sanity_recon),
        "phase_map_b64":      phase_map_base64(phase_map),
        "kspace_phase_b64":   phase_map_base64(kspace_phase),
        "center_energy_pct":  _center_energy(full_kspace),
    }


@router.post("/component")
def reconstruct_components(req: ImageComponentRequest):
    img, raw_kspace = resolve_source(req.source, req.resolution)
    _, full_kspace, _ = _build_full_kspace(img, raw_kspace, req.phase_strength)

    magnitude, phase = magnitude_phase(full_kspace)

    mag_only_img   = normalize_image(np.abs(ifft2_centered(
        combine_magnitude_phase(magnitude, np.zeros_like(phase)))))
    phase_only_img = normalize_image(np.abs(ifft2_centered(
        combine_magnitude_phase(np.ones_like(magnitude), phase))))

    return {
        "magnitude_only_b64": image_to_base64(mag_only_img),
        "phase_only_b64":     image_to_base64(phase_only_img),
    }


@router.post("/mask")
def mask_image(req: ImageMaskRequest):
    img, raw_kspace = resolve_source(req.source, req.resolution)
    _, full_kspace, _ = _build_full_kspace(img, raw_kspace, req.phase_strength)
    kspace_log_mag    = kspace_log_magnitude(full_kspace)

    if req.mask_type not in {"center", "outer", "custom"}:
        raise HTTPException(400, f"Invalid mask_type '{req.mask_type}'.")
    if req.mode not in {"isolate", "remove"}:
        raise HTTPException(400, f"Invalid mode '{req.mode}'.")

    keep_mask    = build_kspace_mask(
        full_kspace.shape, req.mask_type, req.mode,
        radius=req.radius,
        kx_range=(req.kx_min, req.kx_max),
        ky_range=(req.ky_min, req.ky_max),
    )
    masked_ks    = apply_mask(full_kspace, keep_mask)
    masked_recon = normalize_image(np.abs(ifft2_centered(masked_ks)))
    retained_pct = float(100.0 * np.mean(keep_mask))

    m_mse        = mse_metric(img, masked_recon)
    m_psnr       = psnr_metric(img, masked_recon)
    m_ssim, m_ssim_map = ssim_metric(img, masked_recon)
    err_map      = error_heatmap(img, masked_recon)

    return {
        "mask_overlay_b64":  mask_overlay_base64(kspace_log_mag, keep_mask),
        "recon_b64":         image_to_base64(masked_recon),
        "error_heatmap_b64": error_heatmap_base64(err_map),
        "ssim_map_b64":      ssim_map_base64(m_ssim_map),
        "retained_pct":      round(retained_pct, 1),
        "mse":               sanitize_val(m_mse),
        "psnr":              sanitize_val(m_psnr),
        "ssim":              sanitize_val(m_ssim),
        "error_max":         sanitize_val(float(err_map.max()), 0.0),
    }


@router.post("/retain")
def retain_image(req: ImageRetainRequest):
    img, raw_kspace = resolve_source(req.source, req.resolution)
    _, full_kspace, _ = _build_full_kspace(img, raw_kspace, req.phase_strength)

    if req.strategy == "center_radius":
        kspace_ret, actual_frac = retain_center_fraction(full_kspace, req.fraction)
    elif req.strategy == "top_magnitude":
        kspace_ret, actual_frac = retain_top_magnitude(full_kspace, req.fraction)
    else:
        raise HTTPException(400, f"Unknown strategy '{req.strategy}'.")

    retained_recon = normalize_image(np.abs(ifft2_centered(kspace_ret)))
    retained_log   = kspace_log_magnitude(kspace_ret)
    err_map        = error_heatmap(img, retained_recon)

    m_mse          = mse_metric(img, retained_recon)
    m_psnr         = psnr_metric(img, retained_recon)
    m_ssim, m_ssim_map = ssim_metric(img, retained_recon)

    return {
        "retained_kspace_b64": kspace_magnitude_base64(retained_log),
        "recon_b64":           image_to_base64(retained_recon),
        "error_heatmap_b64":   error_heatmap_base64(err_map),
        "ssim_map_b64":        ssim_map_base64(m_ssim_map),
        "actual_fraction":     round(float(actual_frac), 4),
        "actual_pct":          round(float(actual_frac) * 100.0, 1),
        "mse":                 sanitize_val(m_mse),
        "psnr":                sanitize_val(m_psnr),
        "ssim":                sanitize_val(m_ssim),
        "error_max":           sanitize_val(float(err_map.max()), 0.0),
    }


@router.post("/sweep")
def sweep_image(req: ImageSweepRequest):
    img, raw_kspace = resolve_source(req.source, req.resolution)
    _, full_kspace, _ = _build_full_kspace(img, raw_kspace, req.phase_strength)

    sweep_results = retention_sweep(full_kspace, req.strategy, SWEEP_FRACTIONS)
    actual_fractions, psnr_values, ssim_values = [], [], []

    for _, actual_frac, ks_variant in sweep_results:
        recon_v = normalize_image(np.abs(ifft2_centered(ks_variant)))
        p = psnr_metric(img, recon_v)
        s, _ = ssim_metric(img, recon_v)
        actual_fractions.append(round(float(actual_frac), 4))
        psnr_values.append(round(min(float(p), 60.0) if np.isfinite(p) else 60.0, 2))
        ssim_values.append(round(float(s), 4))

    return {
        "fractions":         SWEEP_FRACTIONS,
        "actual_fractions":  actual_fractions,
        "psnr":              psnr_values,
        "ssim":              ssim_values,
    }


@router.post("/save")
def save_image_result(req: ImageSaveRequest):
    raw_b64 = req.image_base64
    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]

    try:
        image_bytes = base64.b64decode(raw_b64)
    except Exception as exc:
        raise HTTPException(400, f"Invalid base64 image data: {exc}")

    safe_label = "".join(c for c in req.label if c.isalnum() or c in "_-")[:60] or "result"
    filename   = f"{safe_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    (SAVED_DIR / filename).write_bytes(image_bytes)
    return {"filename": filename}
