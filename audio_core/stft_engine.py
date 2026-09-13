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


# Sensible defaults for speech/music at typical sample rates.
DEFAULT_N_FFT = 2048
DEFAULT_HOP_LENGTH = 512
DEFAULT_WIN_LENGTH = 2048


def compute_stft(
    y: np.ndarray,
    n_fft: int = DEFAULT_N_FFT,
    hop_length: int = DEFAULT_HOP_LENGTH,
    win_length: int = DEFAULT_WIN_LENGTH,
) -> np.ndarray:
    """
    Compute the complex STFT of a mono audio signal.

    Parameters
    ----------
    y : 1D float array, the audio waveform (values roughly in [-1, 1])
    n_fft : FFT window size (frequency resolution knob)
    hop_length : samples between successive frames (time resolution knob)
    win_length : length of the analysis window (<= n_fft)

    Returns
    -------
    D : complex 2D array, shape (n_fft // 2 + 1, n_frames)
        Row index  -> frequency bin (low frequencies first)
        Column index -> time frame
    """
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
    """
    Invert a complex STFT matrix back into a time-domain waveform.

    `length`, when given, trims/pads the output to match the original
    signal length exactly (STFT/ISTFT can shift length by a few samples
    otherwise, which would break sample-by-sample comparison).
    """
    y = librosa.istft(
        D,
        hop_length=hop_length,
        win_length=win_length,
        window="hann",
        length=length,
    )
    return y


def magnitude_phase(D: np.ndarray):
    """
    Split a complex STFT into magnitude and phase.

    D = magnitude * exp(1j * phase)   <-- polar form of a complex number

    Returns
    -------
    magnitude : 2D float array, same shape as D. Always >= 0.
    phase     : 2D float array, same shape as D. Angle in radians, (-pi, pi].
    """
    magnitude = np.abs(D)
    phase = np.angle(D)
    return magnitude, phase


def combine_magnitude_phase(magnitude: np.ndarray, phase: np.ndarray) -> np.ndarray:
    """
    Rebuild a complex STFT matrix from separate magnitude and phase arrays.
    Inverse operation of `magnitude_phase`.
    """
    return magnitude * np.exp(1j * phase)


def magnitude_to_db(magnitude: np.ndarray, ref: float | None = None) -> np.ndarray:
    """
    Convert a linear magnitude spectrogram to decibels for display.
    Human hearing (and typical spectrogram plots) is logarithmic, so a
    raw linear-magnitude image looks almost entirely black except for a
    few bright pixels. dB scaling spreads out the detail.
    """
    ref_value = ref if ref is not None else np.max(magnitude) + 1e-12
    return librosa.amplitude_to_db(magnitude, ref=ref_value)


def frequency_axis(sr: int, n_fft: int = DEFAULT_N_FFT) -> np.ndarray:
    """Center frequency (Hz) of every STFT frequency bin (row of D)."""
    return librosa.fft_frequencies(sr=sr, n_fft=n_fft)


def time_axis(n_frames: int, sr: int, hop_length: int = DEFAULT_HOP_LENGTH) -> np.ndarray:
    """Center time (seconds) of every STFT frame (column of D)."""
    return librosa.frames_to_time(np.arange(n_frames), sr=sr, hop_length=hop_length)
