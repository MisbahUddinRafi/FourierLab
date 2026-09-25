# backend/music-lab/plotting.py
"""
music-lab/plotting.py

Produces JSON-serializable waveform and spectrogram data for Plotly,
reusing the STFT math from audio_core/stft_engine.py rather than
duplicating it. Stereo input is downmixed to mono for analysis
(waveform envelope + spectrogram), since a single plot per stem is
what the frontend renders.

This module is intentionally separate from audio_utils/plotting.py,
which builds matplotlib Figures for the (PNG-based) Audio Lab pages.
Music Lab renders with Plotly on the frontend, so these functions
return plain dict/array data instead.
"""

from __future__ import annotations

import numpy as np

from audio_core.stft_engine import compute_stft, magnitude_to_db, frequency_axis, time_axis
from . import config


def _to_mono(y: np.ndarray) -> np.ndarray:
    if y.ndim == 1:
        return y
    return y.mean(axis=0).astype(np.float32)


# ---------------------------------------------------------------
# Waveform (min/max envelope downsampling)
# ---------------------------------------------------------------

def build_waveform_data(y: np.ndarray, sr: int) -> dict:
    """
    Downsample to config.WAVEFORM_DOWNSAMPLE_POINTS buckets, keeping
    per-bucket min/max so transients survive downsampling (Plotly can
    render this as a filled min/max band, or just use `max` as a
    simple line).
    """
    y_mono = _to_mono(y)
    n = len(y_mono)
    duration = n / sr if sr > 0 else 0.0

    n_points = min(config.WAVEFORM_DOWNSAMPLE_POINTS, n) if n > 0 else 0

    if n_points <= 0:
        return {
            "time": [], "min": [], "max": [],
            "duration": duration, "sr": sr,
        }

    bucket_edges = np.linspace(0, n, n_points + 1).astype(int)

    mins = np.empty(n_points, dtype=np.float32)
    maxs = np.empty(n_points, dtype=np.float32)
    times = np.empty(n_points, dtype=np.float32)

    for i in range(n_points):
        start, end = bucket_edges[i], bucket_edges[i + 1]
        if end <= start:
            end = start + 1
        chunk = y_mono[start:end]
        mins[i] = chunk.min()
        maxs[i] = chunk.max()
        times[i] = ((start + end) / 2) / sr

    return {
        "time": times.tolist(),
        "min": mins.tolist(),
        "max": maxs.tolist(),
        "duration": float(duration),
        "sr": int(sr),
    }


# ---------------------------------------------------------------
# Spectrogram (STFT magnitude in dB)
# ---------------------------------------------------------------

def build_spectrogram_data(y: np.ndarray, sr: int) -> dict:
    y_mono = _to_mono(y)

    if len(y_mono) < config.SPECTROGRAM_N_FFT:
        # Too short to STFT meaningfully; pad so librosa doesn't error.
        y_mono = np.pad(y_mono, (0, config.SPECTROGRAM_N_FFT - len(y_mono)))

    D = compute_stft(
        y_mono,
        n_fft=config.SPECTROGRAM_N_FFT,
        hop_length=config.SPECTROGRAM_HOP_LENGTH,
        win_length=config.SPECTROGRAM_WIN_LENGTH,
    )
    magnitude = np.abs(D)
    mag_db = magnitude_to_db(magnitude)  # ref = max, per stft_engine.py

    n_freq_bins, n_frames = mag_db.shape

    freqs = frequency_axis(sr=sr, n_fft=config.SPECTROGRAM_N_FFT)
    times = time_axis(n_frames, sr=sr, hop_length=config.SPECTROGRAM_HOP_LENGTH)

    # Downsample time-frames if there are too many for a responsive
    # Plotly heatmap, by taking a stride (simple, fast, adequate for
    # a visual overview rather than precise analysis).
    if n_frames > config.SPECTROGRAM_MAX_FRAMES:
        stride = int(np.ceil(n_frames / config.SPECTROGRAM_MAX_FRAMES))
        mag_db = mag_db[:, ::stride]
        times = times[::stride]

    vmax = float(np.max(mag_db))
    vmin = vmax - config.SPECTROGRAM_TOP_DB
    mag_db_clipped = np.clip(mag_db, vmin, vmax)

    return {
        "time": times.tolist(),
        "freq": freqs.tolist(),
        "z": mag_db_clipped.tolist(),
        "zmin": float(vmin),
        "zmax": float(vmax),
    }


# ---------------------------------------------------------------
# Combined
# ---------------------------------------------------------------

def build_audio_visualization(y: np.ndarray, sr: int, url: str) -> dict:
    """
    Builds the full AudioVisualization dict (matches schemas.AudioVisualization)
    for one stem: player url + duration + waveform + spectrogram.
    """
    duration = y.shape[-1] / sr if sr > 0 else 0.0
    return {
        "url": url,
        "sr": int(sr),
        "duration": float(duration),
        "waveform": build_waveform_data(y, sr),
        "spectrogram": build_spectrogram_data(y, sr),
    }