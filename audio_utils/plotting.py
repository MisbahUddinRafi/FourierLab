"""
utils/plotting.py

All matplotlib figure-building lives here, kept separate from app.py
so the Streamlit page code stays readable (just "call a plot function,
st.pyplot(fig)").
"""

import numpy as np
import matplotlib.pyplot as plt


def plot_waveform(y: np.ndarray, sr: int, title: str = "Waveform"):
    fig, ax = plt.subplots(figsize=(9, 2.5))

    time = np.arange(len(y)) / sr
    ax.plot(time, y, linewidth=0.5, color="#2563eb")

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Amplitude")
    ax.set_title(title)
    ax.set_xlim(0, time[-1] if len(time) > 0 else 1)
    ax.grid(alpha=0.2)

    fig.tight_layout()
    return fig


def plot_spectrogram(
    magnitude_db: np.ndarray,
    sr: int,
    hop_length: int,
    n_fft: int,
    title: str = "Spectrogram",
    cmap: str = "magma",
):
    fig, ax = plt.subplots(figsize=(9, 4))

    n_frames = magnitude_db.shape[1]
    time_max = n_frames * hop_length / sr
    freq_max = sr / 2

    img = ax.imshow(
        magnitude_db,
        origin="lower",
        aspect="auto",
        extent=[0, time_max, 0, freq_max],
        cmap=cmap,
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_title(title)

    cbar = fig.colorbar(img, ax=ax)
    cbar.set_label("Magnitude (dB)")

    fig.tight_layout()
    return fig


def plot_phase(
    phase: np.ndarray,
    sr: int,
    hop_length: int,
    title: str = "Phase Spectrogram",
):
    fig, ax = plt.subplots(figsize=(9, 4))

    n_frames = phase.shape[1]
    time_max = n_frames * hop_length / sr
    freq_max = sr / 2

    img = ax.imshow(
        phase,
        origin="lower",
        aspect="auto",
        extent=[0, time_max, 0, freq_max],
        cmap="twilight",
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_title(title)

    cbar = fig.colorbar(img, ax=ax)
    cbar.set_label("Phase (radians)")

    fig.tight_layout()
    return fig


def plot_retention_curve(fractions, values, ylabel: str, title: str):
    """
    Line plot of a quality metric (y) vs. fraction of data retained (x).
    Used for both the MRI-style and audio-style "quality vs retention"
    analysis graphs.
    """
    fig, ax = plt.subplots(figsize=(7, 4))

    percentages = [f * 100 for f in fractions]
    ax.plot(percentages, values, marker="o", color="#dc2626")

    ax.set_xlabel("Data Retained (%)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(alpha=0.3)

    fig.tight_layout()
    return fig


def plot_mask_overlay(
    magnitude_db: np.ndarray,
    keep_mask: np.ndarray,
    sr: int,
    hop_length: int,
    title: str = "Masked Region",
):
    """
    Show the spectrogram with the masked-out region dimmed, so the
    user can see exactly which time-frequency area they selected.
    """
    fig, ax = plt.subplots(figsize=(9, 4))

    n_frames = magnitude_db.shape[1]
    time_max = n_frames * hop_length / sr
    freq_max = sr / 2

    display = magnitude_db.copy()
    # Dim (not zero) the removed region for visualization purposes only.
    display[~keep_mask] -= 40

    img = ax.imshow(
        display,
        origin="lower",
        aspect="auto",
        extent=[0, time_max, 0, freq_max],
        cmap="magma",
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_title(title)

    cbar = fig.colorbar(img, ax=ax)
    cbar.set_label("Magnitude (dB)")

    fig.tight_layout()
    return fig
