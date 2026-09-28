# backend/music-lab/audio_ops.py
"""
music-lab/audio_ops.py

Stereo audio loading, trimming, gain, channel-matching and mixing.
Refactored from the standalone demo's main.py, but:
  - always works in stereo (2, n_samples) arrays
  - gain is expressed in dB (matching the frontend's -24..+12 dB sliders)
    instead of raw linear multipliers
  - raises HTTPException directly so route handlers stay thin
"""

from __future__ import annotations

import os
from typing import Optional

import numpy as np
import librosa
import soundfile as sf
from fastapi import HTTPException

from . import config


# ---------------------------------------------------------------
# Loading / saving
# ---------------------------------------------------------------

def load_audio_stereo(path: str, target_sr: Optional[int] = None):
    """
    Load an audio file as stereo float32, shape (2, n_samples).
    Mono sources are duplicated to both channels.
    """
    y, sr = librosa.load(path, sr=target_sr, mono=False)

    if y.ndim == 1:
        y = y[np.newaxis, :]

    y = match_channels(y, config.TARGET_CHANNELS)
    return y.astype(np.float32), sr


def save_wav(y: np.ndarray, sr: int, out_path: str) -> None:
    """
    y is expected as (channels, n_samples). soundfile wants
    (n_samples, channels), so we transpose on the way out.
    """
    sf.write(out_path, y.T, sr)


# ---------------------------------------------------------------
# Shape helpers
# ---------------------------------------------------------------

def match_channels(x: np.ndarray, target_channels: int) -> np.ndarray:
    if x.ndim == 1:
        x = x[np.newaxis, :]

    if x.shape[0] == target_channels:
        return x
    if x.shape[0] == 1 and target_channels == 2:
        return np.repeat(x, 2, axis=0)
    if x.shape[0] == 2 and target_channels == 1:
        return x.mean(axis=0, keepdims=True)

    # Fallback for anything unusual (e.g. >2 channels): average down,
    # then broadcast back up to target_channels.
    mono = x.mean(axis=0, keepdims=True)
    return match_channels(mono, target_channels)


def resample_stereo(y: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return y
    return np.stack([
        librosa.resample(ch, orig_sr=orig_sr, target_sr=target_sr)
        for ch in y
    ])


def trim(y: np.ndarray, sr: int, start_sec: float, end_sec: Optional[float]) -> np.ndarray:
    """Slice [start_sec, end_sec) out of y, shape (channels, n_samples)."""
    n = y.shape[-1]
    start_sample = max(0, int(start_sec * sr))
    end_sample = n if end_sec is None else min(n, int(end_sec * sr))

    if start_sample >= end_sample:
        raise HTTPException(
            400,
            "Start time must be before end time, and inside the audio's length.",
        )

    return y[..., start_sample:end_sample]


# ---------------------------------------------------------------
# Gain
# ---------------------------------------------------------------

def db_to_linear(gain_db: float) -> float:
    return float(10.0 ** (gain_db / 20.0))


def apply_gain_db(y: np.ndarray, gain_db: float) -> np.ndarray:
    return y * db_to_linear(gain_db)


def validate_gain_db(gain_db: float, field_name: str) -> float:
    if not (config.GAIN_DB_MIN <= gain_db <= config.GAIN_DB_MAX):
        raise HTTPException(
            400,
            f"{field_name} must be between {config.GAIN_DB_MIN} and "
            f"{config.GAIN_DB_MAX} dB (got {gain_db}).",
        )
    return gain_db


# ---------------------------------------------------------------
# Peak normalization
# ---------------------------------------------------------------

def normalize_peak(y: np.ndarray, peak: float = 0.98) -> np.ndarray:
    max_val = np.max(np.abs(y))
    if max_val < 1e-9:
        return y
    return y * (peak / max_val)


# ---------------------------------------------------------------
# Mixing
# ---------------------------------------------------------------

def mix_stereo(
    y_inst: np.ndarray,
    y_voc: np.ndarray,
    sr: int,
    instrumental_gain_db: float,
    vocal_gain_db: float,
    offset_sec: float,
) -> np.ndarray:
    """
    Mix two stereo (2, n_samples) arrays at the same sample rate.
    The shorter clip is placed starting at offset_sec on a timeline
    as long as the longer clip (or longer, if the offset pushes the
    shorter one past the longer one's end). Positive offset shifts
    the vocal later relative to the instrumental.

    Returns a peak-normalized stereo mix.
    """
    target_channels = max(y_inst.shape[0], y_voc.shape[0])
    y_inst = match_channels(y_inst, target_channels)
    y_voc = match_channels(y_voc, target_channels)

    len_inst = y_inst.shape[-1]
    len_voc = y_voc.shape[-1]
    offset_samples = max(0, int(offset_sec * sr))

    inst_gained = apply_gain_db(y_inst, instrumental_gain_db)
    voc_gained = apply_gain_db(y_voc, vocal_gain_db)

    if len_inst >= len_voc:
        total_len = max(len_inst, offset_samples + len_voc)
        base = np.zeros((target_channels, total_len), dtype=np.float32)
        base[:, :len_inst] += inst_gained

        overlay = np.zeros((target_channels, total_len), dtype=np.float32)
        overlay[:, offset_samples:offset_samples + len_voc] += voc_gained

        mixed = base + overlay
    else:
        total_len = max(len_voc, offset_samples + len_inst)
        base = np.zeros((target_channels, total_len), dtype=np.float32)
        base[:, :len_voc] += voc_gained

        overlay = np.zeros((target_channels, total_len), dtype=np.float32)
        overlay[:, offset_samples:offset_samples + len_inst] += inst_gained

        mixed = base + overlay

    return normalize_peak(mixed)


# ---------------------------------------------------------------
# Upload handling
# ---------------------------------------------------------------

def validate_upload_extension(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext}'. Allowed: "
            f"{', '.join(sorted(config.ALLOWED_EXTENSIONS))}.",
        )
    return ext


def save_upload(upload_file, dest_path: str) -> None:
    """Stream an UploadFile to disk, enforcing MAX_UPLOAD_BYTES."""
    size = 0
    with open(dest_path, "wb") as f:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > config.MAX_UPLOAD_BYTES:
                f.close()
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                raise HTTPException(
                    400,
                    f"File exceeds max upload size of "
                    f"{config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                )
            f.write(chunk)