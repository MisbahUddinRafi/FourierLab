"""
audio_utils/plotting.py

All matplotlib figure-building for the Audio module.
Redesigned with high-DPI rendering, log-frequency y-axis option,
smooth interpolation, standardized dB range clipping (top_db=80),
and transparent backgrounds matching the FourierLab theme.
"""

from typing import Optional, List, Tuple
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from ui_theme import setup_mpl_style


def plot_waveform(y: np.ndarray, sr: int, title: str = "Time-Domain Waveform") -> plt.Figure:
    """
    Plots an amplitude-versus-time waveform with refined styling.
    """
    setup_mpl_style()
    fig, ax = plt.subplots(figsize=(9, 2.4))

    time = np.arange(len(y)) / sr
    ax.plot(time, y, linewidth=0.6, color="#2563eb", alpha=0.9)

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Amplitude")
    ax.set_title(title)
    ax.set_xlim(0, time[-1] if len(time) > 0 else 1)
    ax.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")

    # Clean spine aesthetics
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig


def plot_spectrogram(
    magnitude_db: np.ndarray,
    sr: int,
    hop_length: int,
    n_fft: int,
    title: str = "Spectrogram",
    cmap: str = "magma",
    freq_scale: str = "log",
    top_db: float = 80.0,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
) -> plt.Figure:
    """
    Plots an STFT magnitude spectrogram.
    Features:
    - Log-frequency y-axis option (default) matching human hearing perception.
    - Consistent dynamic range clipping (default 80 dB) to prevent blowout.
    - Smooth bilinear / gouraud interpolation for crisp visualization.
    - Explicit colorbar label with dB units.
    """
    setup_mpl_style()
    fig, ax = plt.subplots(figsize=(9, 3.8))

    n_freq_bins, n_frames = magnitude_db.shape
    time_max = n_frames * hop_length / sr
    freq_max = sr / 2

    # Standardize dB dynamic range
    if vmax is None:
        vmax = float(np.max(magnitude_db))
    if vmin is None:
        vmin = vmax - top_db

    clipped_mag = np.clip(magnitude_db, vmin, vmax)
    times = np.linspace(0, time_max, n_frames)
    freqs = np.linspace(0, freq_max, n_freq_bins)

    if freq_scale == "log":
        # Mesh plot with log frequency axis
        pcm = ax.pcolormesh(
            times, freqs, clipped_mag,
            shading="gouraud",
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
        )
        min_f = max(35.0, freqs[1] if len(freqs) > 1 else 35.0)
        ax.set_yscale("log")
        ax.set_ylim(min_f, freq_max)

        # Standard acoustic 1/3 octave tick frequencies
        candidate_ticks = [60, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
        active_ticks = [t for t in candidate_ticks if min_f <= t <= freq_max]
        if active_ticks:
            ax.set_yticks(active_ticks)
            ax.get_yaxis().set_major_formatter(
                ticker.FuncFormatter(lambda v, _: f"{int(v)} Hz" if v < 1000 else f"{int(v/1000)} kHz")
            )
    else:
        # Linear frequency axis with smooth bilinear interpolation
        pcm = ax.imshow(
            clipped_mag,
            origin="lower",
            aspect="auto",
            extent=[0, time_max, 0, freq_max],
            cmap=cmap,
            interpolation="bilinear",
            vmin=vmin,
            vmax=vmax,
        )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency")
    ax.set_title(title)

    cbar = fig.colorbar(pcm, ax=ax, pad=0.02)
    cbar.set_label("Magnitude (dB)", color="#334155")
    cbar.outline.set_edgecolor("#cbd5e1")
    cbar.ax.tick_params(labelsize=8)

    fig.tight_layout()
    return fig


def plot_phase(
    phase: np.ndarray,
    sr: int,
    hop_length: int,
    title: str = "Phase Spectrogram",
    cmap: str = "twilight",
) -> plt.Figure:
    """
    Plots an STFT phase spectrogram with smooth interpolation
    and explicit radian interval ticks [-π, 0, π].
    """
    setup_mpl_style()
    fig, ax = plt.subplots(figsize=(9, 3.8))

    n_freq_bins, n_frames = phase.shape
    time_max = n_frames * hop_length / sr
    freq_max = sr / 2

    img = ax.imshow(
        phase,
        origin="lower",
        aspect="auto",
        extent=[0, time_max, 0, freq_max],
        cmap=cmap,
        interpolation="bilinear",
        vmin=-np.pi,
        vmax=np.pi,
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_title(title)

    cbar = fig.colorbar(img, ax=ax, pad=0.02)
    cbar.set_label("Phase (radians)", color="#334155")
    cbar.set_ticks([-np.pi, -np.pi / 2, 0, np.pi / 2, np.pi])
    cbar.set_ticklabels(["-π", "-π/2", "0", "+π/2", "+π"])
    cbar.outline.set_edgecolor("#cbd5e1")
    cbar.ax.tick_params(labelsize=8)

    fig.tight_layout()
    return fig


def plot_retention_curve(fractions: List[float], values: List[float], ylabel: str, title: str) -> plt.Figure:
    """
    Line plot of quality metric vs. fraction of data retained.
    """
    setup_mpl_style()
    fig, ax = plt.subplots(figsize=(7.5, 3.6))

    percentages = [f * 100 for f in fractions]
    ax.plot(
        percentages, values,
        marker="o",
        markersize=5,
        linewidth=2,
        color="#2563eb",
        markerfacecolor="#ffffff",
        markeredgecolor="#2563eb",
        markeredgewidth=2,
        alpha=0.95,
    )

    ax.set_xlabel("Data Retained (%)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.6, color="#e2e8f0")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig


def plot_mask_overlay(
    magnitude_db: np.ndarray,
    keep_mask: np.ndarray,
    sr: int,
    hop_length: int,
    title: str = "Selected Time-Frequency Region",
    top_db: float = 80.0,
) -> plt.Figure:
    """
    Displays the spectrogram with removed regions subtly dimmed and framed
    so the user can inspect the exact masked time-frequency box.
    """
    setup_mpl_style()
    fig, ax = plt.subplots(figsize=(9, 3.8))

    n_frames = magnitude_db.shape[1]
    time_max = n_frames * hop_length / sr
    freq_max = sr / 2

    vmax = float(np.max(magnitude_db))
    vmin = vmax - top_db

    display = magnitude_db.copy()
    # Dim the excluded area by 40 dB
    display[~keep_mask] -= 40
    display_clipped = np.clip(display, vmin - 40, vmax)

    img = ax.imshow(
        display_clipped,
        origin="lower",
        aspect="auto",
        extent=[0, time_max, 0, freq_max],
        cmap="magma",
        interpolation="bilinear",
        vmin=vmin,
        vmax=vmax,
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_title(title)

    cbar = fig.colorbar(img, ax=ax, pad=0.02)
    cbar.set_label("Magnitude (dB)", color="#334155")
    cbar.outline.set_edgecolor("#cbd5e1")
    cbar.ax.tick_params(labelsize=8)

    fig.tight_layout()
    return fig
