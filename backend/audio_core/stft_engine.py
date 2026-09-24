"""
core/stft_engine.py

This is the mathematical heart of the audio module: computing the
Short-Time Fourier Transform (STFT) and its inverse (ISTFT).

WHY AN STFT AND NOT A SINGLE FFT?
A plain FFT of an entire audio clip tells you *which* frequencies are
present overall, but destroys *when* they occurred. The STFT slides a
short analysis window across the signal, takes an FFT of each window,
and stacks the results side by side. The result, `D`, is a 2D complex
matrix:

    D[frequency_bin, time_frame] = complex number

Just like MRI k-space, every entry in `D` has:
    - a MAGNITUDE  |D|      -> "how much energy at this freq/time"
    - a PHASE      angle(D) -> "what part of the wave cycle it's in"

We rely on librosa for the actual FFT math (allowed: this project's
restriction is "no black-box ML", not "no FFT libraries" -- that
restriction only applies to your separate DFT/FFT coursework offline).
"""

import numpy as np
import librosa


DEFAULT_N_FFT = 2048
DEFAULT_HOP_LENGTH = 512
DEFAULT_WIN_LENGTH = 2048


def compute_stft(
    y: np.ndarray,
    n_fft: int = DEFAULT_N_FFT,
    hop_length: int = DEFAULT_HOP_LENGTH,
    win_length: int = DEFAULT_WIN_LENGTH,
) -> np.ndarray:
    D = librosa.stft(
        y,
        n_fft=n_fft,
        hop_length=hop_length,
        win_length=win_length,
        window="hann",
    )
    return D


def compute_istft(
    D: np.ndarray,
    hop_length: int = DEFAULT_HOP_LENGTH,
    win_length: int = DEFAULT_WIN_LENGTH,
    length: int | None = None,
) -> np.ndarray:
    y = librosa.istft(
        D,
        hop_length=hop_length,
        win_length=win_length,
        window="hann",
        length=length,
    )
    return y


def magnitude_phase(D: np.ndarray):
    magnitude = np.abs(D)
    phase = np.angle(D)
    return magnitude, phase


def combine_magnitude_phase(magnitude: np.ndarray, phase: np.ndarray) -> np.ndarray:
    return magnitude * np.exp(1j * phase)


def magnitude_to_db(magnitude: np.ndarray, ref: float | None = None) -> np.ndarray:
    ref_value = ref if ref is not None else np.max(magnitude) + 1e-12
    return librosa.amplitude_to_db(magnitude, ref=ref_value)


def frequency_axis(sr: int, n_fft: int = DEFAULT_N_FFT) -> np.ndarray:
    return librosa.fft_frequencies(sr=sr, n_fft=n_fft)


def time_axis(n_frames: int, sr: int, hop_length: int = DEFAULT_HOP_LENGTH) -> np.ndarray:
    return librosa.frames_to_time(np.arange(n_frames), sr=sr, hop_length=hop_length)