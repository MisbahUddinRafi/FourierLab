"""
core/reconstruction.py

Two retention strategies, mirroring the MRI module's
"center k-space vs peripheral k-space" experiment:

1. LOW-FREQUENCY RETENTION (band-limiting)
2. MAGNITUDE-ENERGY RETENTION (global thresholding)
"""

import numpy as np


def retain_low_frequencies(D: np.ndarray, keep_fraction: float) -> np.ndarray:
    keep_fraction = float(np.clip(keep_fraction, 0.0, 1.0))

    n_freq_bins = D.shape[0]
    cutoff_bin = max(1, int(round(n_freq_bins * keep_fraction)))

    D_masked = np.zeros_like(D)
    D_masked[:cutoff_bin, :] = D[:cutoff_bin, :]

    return D_masked


def retain_top_magnitude(D: np.ndarray, keep_fraction: float) -> np.ndarray:
    keep_fraction = float(np.clip(keep_fraction, 0.0, 1.0))

    magnitude = np.abs(D)

    if keep_fraction >= 1.0:
        return D.copy()

    flat_magnitudes = magnitude.ravel()
    percentile_cutoff = 100.0 * (1.0 - keep_fraction)
    threshold = np.percentile(flat_magnitudes, percentile_cutoff)

    keep_mask = magnitude >= threshold

    return D * keep_mask


def retention_sweep(D: np.ndarray, strategy: str, fractions):
    if strategy == "low_frequency":
        fn = retain_low_frequencies
    elif strategy == "top_magnitude":
        fn = retain_top_magnitude
    else:
        raise ValueError(f"Unknown strategy '{strategy}'.")

    return [(frac, fn(D, frac)) for frac in fractions]