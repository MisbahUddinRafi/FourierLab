"""
core/metrics.py

Quantitative comparison between an original waveform and a
reconstructed one.
"""

import numpy as np

EPS = 1e-12


def _match_length(a: np.ndarray, b: np.ndarray):
    n = min(len(a), len(b))
    return a[:n], b[:n]


def snr_db(original: np.ndarray, reconstructed: np.ndarray) -> float:
    original, reconstructed = _match_length(original, reconstructed)

    signal_power = np.mean(original ** 2)
    noise_power = np.mean((original - reconstructed) ** 2)

    if noise_power < EPS:
        return float("inf")

    return 10 * np.log10((signal_power + EPS) / (noise_power + EPS))


def mse(original: np.ndarray, reconstructed: np.ndarray) -> float:
    original, reconstructed = _match_length(original, reconstructed)
    return float(np.mean((original - reconstructed) ** 2))


def spectral_convergence(mag_original: np.ndarray, mag_reconstructed: np.ndarray) -> float:
    numerator = np.linalg.norm(mag_original - mag_reconstructed, ord="fro")
    denominator = np.linalg.norm(mag_original, ord="fro") + EPS
    return float(numerator / denominator)