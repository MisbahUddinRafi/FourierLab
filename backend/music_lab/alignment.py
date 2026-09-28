# backend/music-lab/alignment.py
"""
music-lab/alignment.py

Suggests a time offset to align a vocal track with an instrumental
track, using cross-correlation of their amplitude envelopes. This
powers the "Suggested offset" readout in the Mix tab.

Approach:
  1. Downmix both stereo signals to mono.
  2. Resample both to a low working sample rate (alignment doesn't
     need full audio resolution, and this keeps the FFT cheap).
  3. Compute the onset/amplitude envelope of each (rectified +
     smoothed), rather than correlating raw waveforms directly --
     raw-waveform cross-correlation is dominated by phase/timbre and
     is a poor predictor of *musical* alignment, whereas envelope
     correlation lines up transients (attacks, syllables, drum hits).
  4. Cross-correlate the two envelopes via FFT (much faster than a
     direct O(n^2) correlation for long tracks).
  5. The lag at the correlation peak is the suggested offset.

Sign convention (matches audio_ops.mix_stereo / the frontend's
"Offset to apply (s)" field): a positive offset means the vocal
should start LATER relative to the instrumental.
"""

from __future__ import annotations

import numpy as np
import librosa

ALIGNMENT_WORKING_SR = 4000
ENVELOPE_SMOOTH_WINDOW = 15  # samples, at ALIGNMENT_WORKING_SR

# Cap on how far we'll search for alignment in either direction.
MAX_SEARCH_SEC = 30.0


def _to_mono(y: np.ndarray) -> np.ndarray:
    if y.ndim == 1:
        return y
    return y.mean(axis=0)


def _amplitude_envelope(y_mono: np.ndarray) -> np.ndarray:
    rectified = np.abs(y_mono)
    if ENVELOPE_SMOOTH_WINDOW > 1:
        kernel = np.ones(ENVELOPE_SMOOTH_WINDOW, dtype=np.float32) / ENVELOPE_SMOOTH_WINDOW
        rectified = np.convolve(rectified, kernel, mode="same")
    # Zero-mean so correlation isn't dominated by DC/overall loudness
    return rectified - np.mean(rectified)


def suggest_offset_sec(
    y_inst: np.ndarray,
    sr_inst: int,
    y_voc: np.ndarray,
    sr_voc: int,
) -> tuple[float, float]:
    """
    Returns (suggested_offset_sec, confidence in [0, 1]).

    suggested_offset_sec > 0  => vocal should start later
    suggested_offset_sec < 0  => vocal should start earlier
    """
    inst_mono = _to_mono(y_inst)
    voc_mono = _to_mono(y_voc)

    inst_ds = librosa.resample(inst_mono, orig_sr=sr_inst, target_sr=ALIGNMENT_WORKING_SR)
    voc_ds = librosa.resample(voc_mono, orig_sr=sr_voc, target_sr=ALIGNMENT_WORKING_SR)

    env_inst = _amplitude_envelope(inst_ds)
    env_voc = _amplitude_envelope(voc_ds)

    if len(env_inst) < 2 or len(env_voc) < 2:
        return 0.0, 0.0

    # FFT-based cross-correlation, full mode.
    n = len(env_inst) + len(env_voc) - 1
    fft_size = 1 << (n - 1).bit_length()  # next power of 2

    fft_inst = np.fft.rfft(env_inst, n=fft_size)
    fft_voc = np.fft.rfft(env_voc, n=fft_size)

    # correlate(inst, voc): positive lag means voc lags behind inst,
    # i.e. voc should be shifted later -> positive offset.
    corr = np.fft.irfft(fft_inst * np.conj(fft_voc), n=fft_size)

    # Rearrange so index 0 is the most-negative lag.
    max_lag_samples = len(env_voc) - 1
    corr = np.concatenate((corr[-max_lag_samples:], corr[:len(env_inst)]))
    lags = np.arange(-max_lag_samples, len(env_inst))

    # Restrict search window to +/- MAX_SEARCH_SEC.
    max_search_samples = int(MAX_SEARCH_SEC * ALIGNMENT_WORKING_SR)
    in_range = (lags >= -max_search_samples) & (lags <= max_search_samples)

    if not np.any(in_range):
        return 0.0, 0.0

    corr_r = corr[in_range]
    lags_r = lags[in_range]

    peak_idx = int(np.argmax(corr_r))
    peak_lag_samples = lags_r[peak_idx]
    peak_value = corr_r[peak_idx]

    offset_sec = float(peak_lag_samples / ALIGNMENT_WORKING_SR)

    # Confidence: how much the peak stands out from the rest of the
    # correlation curve, normalized to [0, 1].
    corr_std = np.std(corr_r) + 1e-9
    corr_mean = np.mean(corr_r)
    z_score = (peak_value - corr_mean) / corr_std
    confidence = float(np.clip(z_score / 10.0, 0.0, 1.0))

    return offset_sec, confidence