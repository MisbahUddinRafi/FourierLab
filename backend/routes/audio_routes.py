import base64
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from audio_core.stft_engine import (
    compute_stft,
    compute_istft,
    magnitude_phase,
    combine_magnitude_phase,
    magnitude_to_db,
    frequency_axis,
    time_axis,
)
from audio_core.masking import build_time_freq_mask, apply_mask
from audio_core.reconstruction import (
    retain_low_frequencies,
    retain_top_magnitude,
    retention_sweep,
)
from audio_core.metrics import snr_db, mse, spectral_convergence
from audio_utils.audio_io import load_audio, waveform_to_wav_bytes

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
AUDIO_ROOT = BASE_DIR / "assets" / "audio"
SAMPLES_DIR = AUDIO_ROOT / "samples"
SAVED_DIR = AUDIO_ROOT / "saved"
UPLOADS_DIR = AUDIO_ROOT / "_uploads"

for d in [SAMPLES_DIR, SAVED_DIR, UPLOADS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".mp4"}
SWEEP_FRACTIONS = [0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0]


def resolve_source(source: str) -> Path:
    path = (AUDIO_ROOT / source).resolve()
    if AUDIO_ROOT.resolve() not in path.parents:
        raise HTTPException(400, "Invalid source path.")
    if not path.is_file():
        raise HTTPException(404, f"Audio source not found: {source}")
    return path


def sanitize_metric(value: float):
    value = float(value)
    return value if np.isfinite(value) else None


def waveform_envelope(y: np.ndarray, sr: int, n_buckets: int = 1200):
    """
    Downsample a waveform for plotting by taking the min and max of
    each time bucket, so peaks aren't lost the way plain stride-based
    downsampling would lose them -- the same technique real audio
    editors use for their waveform view.
    """
    n = len(y)
    if n == 0:
        return {"time": [], "min": [], "max": []}

    bucket_size = max(1, n // n_buckets)
    n_full = n // bucket_size
    trimmed = y[: n_full * bucket_size].reshape(n_full, bucket_size)

    mins = trimmed.min(axis=1)
    maxs = trimmed.max(axis=1)
    centers = (np.arange(n_full) * bucket_size + bucket_size / 2) / sr

    return {
        "time": np.round(centers, 4).tolist(),
        "min": np.round(mins, 4).tolist(),
        "max": np.round(maxs, 4).tolist(),
    }


class AnalyzeRequest(BaseModel):
    source: str
    sr: int = 22050
    n_fft: int = 2048
    hop_length: int = 512


class ComponentRequest(AnalyzeRequest):
    mode: str  # "magnitude_only" | "phase_only"


class MaskRequest(AnalyzeRequest):
    freq_min: float
    freq_max: float
    time_min: float
    time_max: float
    mode: str  # "remove" | "isolate"


class RetainRequest(AnalyzeRequest):
    strategy: str  # "low_frequency" | "top_magnitude"
    fraction: float


class SweepRequest(AnalyzeRequest):
    strategy: str


class SaveRequest(BaseModel):
    audio_base64: str
    label: str = "result"


@router.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    dest = UPLOADS_DIR / f"{uuid.uuid4().hex}{ext}"
    dest.write_bytes(await file.read())

    try:
        y, sr = load_audio(str(dest), target_sr=None, mono=True)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            400,
            f"Could not decode this file. MP3/MP4/M4A need ffmpeg installed and on PATH. ({exc})",
        )

    return {"source": f"_uploads/{dest.name}", "sr": sr, "duration": round(len(y) / sr, 3)}


@router.get("/library")
def get_library():
    samples = sorted(p.name for p in SAMPLES_DIR.glob("*") if p.suffix.lower() in ALLOWED_EXTENSIONS)
    saved = sorted(p.name for p in SAVED_DIR.glob("*") if p.suffix.lower() in ALLOWED_EXTENSIONS)
    return {"samples": samples, "saved": saved}


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    path = resolve_source(req.source)
    y, sr = load_audio(str(path), target_sr=req.sr, mono=True)

    D = compute_stft(y, n_fft=req.n_fft, hop_length=req.hop_length, win_length=req.n_fft)
    magnitude, phase = magnitude_phase(D)
    magnitude_db = magnitude_to_db(magnitude)

    freqs = frequency_axis(sr=sr, n_fft=req.n_fft)
    times = time_axis(D.shape[1], sr=sr, hop_length=req.hop_length)

    return {
        "sr": sr,
        "duration": round(len(y) / sr, 3),
        "waveform": waveform_envelope(y, sr),
        "freqs": np.round(freqs, 1).tolist(),
        "times": np.round(times, 4).tolist(),
        "magnitude_db": np.round(magnitude_db, 1).tolist(),
        "phase": np.round(phase, 3).tolist(),
    }


@router.post("/component")
def reconstruct_component(req: ComponentRequest):
    path = resolve_source(req.source)
    y, sr = load_audio(str(path), target_sr=req.sr, mono=True)
    D = compute_stft(y, n_fft=req.n_fft, hop_length=req.hop_length, win_length=req.n_fft)
    magnitude, phase = magnitude_phase(D)

    if req.mode == "magnitude_only":
        D_variant = combine_magnitude_phase(magnitude, np.zeros_like(phase))
    elif req.mode == "phase_only":
        D_variant = combine_magnitude_phase(np.ones_like(magnitude), phase)
    else:
        raise HTTPException(400, "mode must be 'magnitude_only' or 'phase_only'")

    y_variant = compute_istft(D_variant, req.hop_length, req.n_fft, length=len(y))
    audio_b64 = base64.b64encode(waveform_to_wav_bytes(y_variant, sr)).decode("ascii")
    return {"audio_base64": audio_b64}


@router.post("/mask")
def mask_audio(req: MaskRequest):
    path = resolve_source(req.source)
    y, sr = load_audio(str(path), target_sr=req.sr, mono=True)
    D = compute_stft(y, n_fft=req.n_fft, hop_length=req.hop_length, win_length=req.n_fft)

    keep_mask = build_time_freq_mask(
        D.shape, sr, req.n_fft, req.hop_length,
        freq_range_hz=(req.freq_min, req.freq_max),
        time_range_sec=(req.time_min, req.time_max),
        mode=req.mode,
    )
    D_masked = apply_mask(D, keep_mask)
    y_masked = compute_istft(D_masked, req.hop_length, req.n_fft, length=len(y))

    magnitude_full, _ = magnitude_phase(D)
    magnitude_db_masked = magnitude_to_db(np.abs(D_masked), ref=np.max(magnitude_full) + 1e-12)

    audio_b64 = base64.b64encode(waveform_to_wav_bytes(y_masked, sr)).decode("ascii")
    return {
        "audio_base64": audio_b64,
        "magnitude_db": np.round(magnitude_db_masked, 1).tolist(),
        "snr_db": sanitize_metric(snr_db(y, y_masked)),
        "mse": sanitize_metric(mse(y, y_masked)),
        "spectral_convergence": sanitize_metric(spectral_convergence(magnitude_full, np.abs(D_masked))),
    }


@router.post("/retain")
def retain_audio(req: RetainRequest):
    path = resolve_source(req.source)
    y, sr = load_audio(str(path), target_sr=req.sr, mono=True)
    D = compute_stft(y, n_fft=req.n_fft, hop_length=req.hop_length, win_length=req.n_fft)

    if req.strategy == "low_frequency":
        D_retained = retain_low_frequencies(D, req.fraction)
    elif req.strategy == "top_magnitude":
        D_retained = retain_top_magnitude(D, req.fraction)
    else:
        raise HTTPException(400, "strategy must be 'low_frequency' or 'top_magnitude'")

    y_retained = compute_istft(D_retained, req.hop_length, req.n_fft, length=len(y))
    magnitude_full, _ = magnitude_phase(D)
    magnitude_db_retained = magnitude_to_db(np.abs(D_retained), ref=np.max(magnitude_full) + 1e-12)

    audio_b64 = base64.b64encode(waveform_to_wav_bytes(y_retained, sr)).decode("ascii")
    return {
        "audio_base64": audio_b64,
        "magnitude_db": np.round(magnitude_db_retained, 1).tolist(),
        "snr_db": sanitize_metric(snr_db(y, y_retained)),
    }


@router.post("/sweep")
def sweep_audio(req: SweepRequest):
    path = resolve_source(req.source)
    y, sr = load_audio(str(path), target_sr=req.sr, mono=True)
    D = compute_stft(y, n_fft=req.n_fft, hop_length=req.hop_length, win_length=req.n_fft)

    results = retention_sweep(D, req.strategy, SWEEP_FRACTIONS)
    snr_values = []
    for _, D_variant in results:
        y_variant = compute_istft(D_variant, req.hop_length, req.n_fft, length=len(y))
        snr_values.append(sanitize_metric(snr_db(y, y_variant)))

    return {"fractions": SWEEP_FRACTIONS, "snr_db": snr_values}


@router.post("/save")
def save_result(req: SaveRequest):
    audio_bytes = base64.b64decode(req.audio_base64)
    safe_label = "".join(c for c in req.label if c.isalnum() or c in "_-")[:60] or "result"
    filename = f"{safe_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    (SAVED_DIR / filename).write_bytes(audio_bytes)
    return {"filename": filename}