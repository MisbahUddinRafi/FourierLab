"""
utils/plotting.py

All matplotlib figure-building for the MRI module, kept separate from
app.py so the Streamlit page code stays readable.
"""

import numpy as np
import matplotlib.pyplot as plt


def plot_kspace_magnitude(log_magnitude: np.ndarray, title: str = "k-Space Magnitude"):
    fig, ax = plt.subplots(figsize=(5, 5))
    img = ax.imshow(log_magnitude, cmap="viridis", origin="lower")
    ax.set_xlabel("kx")
    ax.set_ylabel("ky")
    ax.set_title(title)
    fig.colorbar(img, ax=ax, label="log magnitude (normalized)")
    fig.tight_layout()
    return fig


def plot_phase_map(phase: np.ndarray, title: str = "Phase"):
    fig, ax = plt.subplots(figsize=(5, 5))
    img = ax.imshow(phase, cmap="twilight", origin="lower")
    ax.set_xlabel("kx" if "k-Space" in title else "x")
    ax.set_ylabel("ky" if "k-Space" in title else "y")
    ax.set_title(title)
    fig.colorbar(img, ax=ax, label="radians")
    fig.tight_layout()
    return fig


def plot_error_heatmap(error_map: np.ndarray, title: str = "Absolute Error"):
    fig, ax = plt.subplots(figsize=(5, 5))
    img = ax.imshow(error_map, cmap="inferno", origin="upper")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_title(title)
    fig.colorbar(img, ax=ax, label="|reference - reconstruction|")
    fig.tight_layout()
    return fig


def plot_ssim_map(ssim_map: np.ndarray, title: str = "Local SSIM"):
    fig, ax = plt.subplots(figsize=(5, 5))
    img = ax.imshow(ssim_map, cmap="RdYlGn", origin="upper", vmin=0, vmax=1)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_title(title)
    fig.colorbar(img, ax=ax, label="local SSIM (1 = perfect)")
    fig.tight_layout()
    return fig


def plot_mask_overlay(log_magnitude: np.ndarray, keep_mask: np.ndarray, title: str = "Selected k-Space Region"):
    """Dim the removed region so the user can see exactly what was masked out."""
    fig, ax = plt.subplots(figsize=(5, 5))
    display = log_magnitude.copy()
    display[~keep_mask] *= 0.15
    img = ax.imshow(display, cmap="viridis", origin="lower")
    ax.set_xlabel("kx")
    ax.set_ylabel("ky")
    ax.set_title(title)
    fig.colorbar(img, ax=ax, label="log magnitude (normalized)")
    fig.tight_layout()
    return fig


def plot_retention_curve(fractions, series: dict, title: str = "Reconstruction Quality vs. Data Retained"):
    """
    series : dict of {label: list_of_values}, all aligned to `fractions`.
    Plots one line per series (e.g. PSNR and SSIM together, on twin axes
    when their scales differ wildly -- kept simple here as one axis per
    call, composed twice in app.py when both metrics are wanted).
    """
    fig, ax = plt.subplots(figsize=(7, 4))
    percentages = [f * 100 for f in fractions]

    for label, values in series.items():
        ax.plot(percentages, values, marker="o", label=label)

    ax.set_xlabel("k-Space Data Retained (%)")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    return fig
