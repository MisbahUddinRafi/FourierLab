"""
core/metrics.py

Quantitative comparison between an original waveform and a
reconstructed one, matching the spec's "SNR-based reconstruction
quality analysis".
"""

import numpy as np

EPS = 1e-12


def _match_length(a: np.ndarray, b: np.ndarray):
    """STFT/ISTFT round-trips can differ by a handful of samples;
    trim both signals to the shorter length before comparing."""
    n = min(len(a), len(b))
    return a[:n], b[:n]


def snr_db(original: np.ndarray, reconstructed: np.ndarray) -> float:
    """
    Signal-to-Noise Ratio in decibels.

    SNR = 10 * log10( signal_power / noise_power )

    where "noise" is defined as (original - reconstructed), i.e.
    everything reconstruction failed to reproduce. Higher is better;
    a perfect reconstruction gives +inf dB.
    """
    original, reconstructed = _match_length(original, reconstructed)

    signal_power = np.mean(original ** 2)
    noise_power = np.mean((original - reconstructed) ** 2)

    if noise_power < EPS:
        return float("inf")

    return 10 * np.log10((signal_power + EPS) / (noise_power + EPS))


def mse(original: np.ndarray, reconstructed: np.ndarray) -> float:
    """Mean squared error between two waveforms."""
    original, reconstructed = _match_length(original, reconstructed)
    return float(np.mean((original - reconstructed) ** 2))


def spectral_convergence(mag_original: np.ndarray, mag_reconstructed: np.ndarray) -> float:
    """
    A frequency-domain quality metric: normalized Frobenius-norm
    distance between two magnitude spectrograms. 0 = identical.
    Useful because it measures error directly in the domain we've
    been manipulating, rather than only in the time domain.
    """
    numerator = np.linalg.norm(mag_original - mag_reconstructed, ord="fro")
    denominator = np.linalg.norm(mag_original, ord="fro") + EPS
    return float(numerator / denominator)
