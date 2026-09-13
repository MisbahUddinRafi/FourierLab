"""
core/reconstruction.py

"Progressive reconstruction": given the full STFT of a clip, keep only
some fraction of the frequency-domain information and reconstruct the
audio, so the user can see (and hear) how reconstruction quality
degrades as less data is retained.

Two retention strategies are provided, mirroring the MRI module's
"center k-space vs peripheral k-space" experiment:

1. LOW-FREQUENCY RETENTION (band-limiting)
   Keep only the bottom X% of frequency bins (like keeping only the
   center of k-space). Direct analogue of a low-pass filter -- you'd
   expect a muffled, bass-heavy result with the full pitch/timbre lost.

2. MAGNITUDE-ENERGY RETENTION (global thresholding)
   Keep only the time-frequency bins with the highest magnitude,
   regardless of where they sit in the spectrogram, discarding the
   rest. This is closer to how real audio compression allocates bits:
   spend them on the loudest, most perceptually important components.
"""

import numpy as np


def retain_low_frequencies(D: np.ndarray, keep_fraction: float) -> np.ndarray:
    """
    Zero out every frequency bin above the cutoff, keeping only the
    lowest `keep_fraction` of rows (frequency bins) of the STFT.

    keep_fraction : float in (0, 1]. 1.0 keeps everything (identity).
    """
    keep_fraction = float(np.clip(keep_fraction, 0.0, 1.0))

    n_freq_bins = D.shape[0]
    cutoff_bin = max(1, int(round(n_freq_bins * keep_fraction)))

    D_masked = np.zeros_like(D)
    D_masked[:cutoff_bin, :] = D[:cutoff_bin, :]

    return D_masked


def retain_top_magnitude(D: np.ndarray, keep_fraction: float) -> np.ndarray:
    """
    Keep only the top `keep_fraction` of time-frequency bins by
    magnitude (energy), across the *entire* spectrogram, zero the rest.

    keep_fraction : float in (0, 1]. 1.0 keeps everything (identity).
    """
    keep_fraction = float(np.clip(keep_fraction, 0.0, 1.0))

    magnitude = np.abs(D)

    if keep_fraction >= 1.0:
        return D.copy()

    # Find the magnitude threshold below which we discard bins.
    # np.percentile with (1 - keep_fraction)*100 gives the cutoff value
    # such that `keep_fraction` of bins are at or above it.
    flat_magnitudes = magnitude.ravel()
    percentile_cutoff = 100.0 * (1.0 - keep_fraction)
    threshold = np.percentile(flat_magnitudes, percentile_cutoff)

    keep_mask = magnitude >= threshold

    return D * keep_mask


def retention_sweep(
    D: np.ndarray,
    strategy: str,
    fractions,
):
    """
    Convenience helper: apply a retention strategy at several fractions
    in one call, used to build the "quality vs. retained data" curve.

    Returns a list of (fraction, D_masked) tuples.
    """
    if strategy == "low_frequency":
        fn = retain_low_frequencies
    elif strategy == "top_magnitude":
        fn = retain_top_magnitude
    else:
        raise ValueError(f"Unknown strategy '{strategy}'.")

    return [(frac, fn(D, frac)) for frac in fractions]
