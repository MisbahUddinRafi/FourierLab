"""
core/masking.py

Lets the user carve out a rectangular time-frequency region of the
spectrogram and either REMOVE it (notch it out) or ISOLATE it (keep
only that region, zero everything else).

This is the audio equivalent of the MRI module's "center / outer /
custom" k-space masking -- same idea (zero out chosen region of a
frequency-domain representation), different domain (1D STFT bins over
time, instead of 2D k-space over spatial frequency).

IMPORTANT DESIGN CHOICE: we mask the COMPLEX STFT directly (not just
the magnitude), and we always keep phase attached to whatever
magnitude survives. Zeroing a complex bin zeroes both its magnitude
and its (now meaningless) phase together, which is the physically
correct way to "remove" a time-frequency region.
"""

import numpy as np

from audio_core.stft_engine import frequency_axis, time_axis


def build_time_freq_mask(
    shape: tuple,
    sr: int,
    n_fft: int,
    hop_length: int,
    freq_range_hz: tuple,
    time_range_sec: tuple,
    mode: str = "remove",
) -> np.ndarray:
    """
    Build a boolean keep-mask of the given STFT shape.

    Parameters
    ----------
    shape : (n_freq_bins, n_frames) -- shape of the STFT matrix D
    freq_range_hz : (f_min, f_max) region boundaries in Hz
    time_range_sec : (t_min, t_max) region boundaries in seconds
    mode : "remove"  -> everything EXCEPT the region is kept (region -> 0)
           "isolate" -> ONLY the region is kept (everything else -> 0)

    Returns
    -------
    keep_mask : boolean 2D array, True = keep this bin, False = zero it out
    """
    n_freq_bins, n_frames = shape

    freqs = frequency_axis(sr=sr, n_fft=n_fft)          # length n_freq_bins
    times = time_axis(n_frames, sr=sr, hop_length=hop_length)  # length n_frames

    f_min, f_max = freq_range_hz
    t_min, t_max = time_range_sec

    freq_in_region = (freqs >= f_min) & (freqs <= f_max)      # 1D, length n_freq_bins
    time_in_region = (times >= t_min) & (times <= t_max)      # 1D, length n_frames

    # Outer product turns two 1D boolean vectors into a 2D region mask.
    region = np.outer(freq_in_region, time_in_region)

    if mode == "remove":
        keep_mask = ~region
    elif mode == "isolate":
        keep_mask = region
    else:
        raise ValueError(f"Unknown mode '{mode}', expected 'remove' or 'isolate'.")

    return keep_mask


def apply_mask(D: np.ndarray, keep_mask: np.ndarray) -> np.ndarray:
    """
    Zero out every complex STFT bin where keep_mask is False.
    """
    return D * keep_mask
