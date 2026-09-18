"""
mri_utils/plotting.py

All matplotlib figure-building for the MRI k-space module.
Redesigned with high-DPI rendering, smooth bilinear interpolation,
consistent intensity windowing, explicit colorbar units, and
transparent backgrounds matching the FourierLab theme.
"""

from typing import Dict, List, Optional
import numpy as np
import matplotlib.pyplot as plt
from ui_theme import setup_mpl_style


def plot_kspace_magnitude(
    log_magnitude: np.ndarray,
    title: str = "k-Space Log Magnitude",
    cmap: str = "viridis",
) -> plt.Figure:
    """
    Plots centered 2D k-space log magnitude with smooth interpolation.
    """
    setup_mpl_style()
    fig, ax = plt.subplots(figsize=(4.8, 4.8))

    img = ax.imshow(
        log_magnitude,
        cmap=cmap,
        origin="lower",
        interpolation="bilinear",
    )

    ax.set_xlabel("kx (spatial frequency)", fontsize=9)
    ax.set_ylabel("ky (spatial frequency)", fontsize=9)
    ax.set_title(title)

    cbar = fig.colorbar(img, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("log |K(u,v)| (normalized)", color="#334155", fontsize=8.5)
    cbar.outline.set_edgecolor("#cbd5e1")
    cbar.ax.tick_params(labelsize=8)

    fig.tight_layout()
    return fig


def plot_phase_map(
    phase: np.ndarray,
    title: str = "Phase Map",
    cmap: str = "twilight",
) -> plt.Figure:
    """
    Plots 2D spatial or k-space phase with smooth twilight colormap
    and standardized radian ticks [-π, 0, π].
    """
    setup_mpl_style()
    fig, ax = plt.subplots(figsize=(4.8, 4.8))

    img = ax.imshow(
        phase,
        cmap=cmap,
        origin="lower",
        interpolation="bilinear",
        vmin=-np.pi,
        vmax=np.pi,
    )

    is_kspace = "k-space" in title.lower()
    ax.set_xlabel("kx" if is_kspace else "x (voxels)", fontsize=9)
    ax.set_ylabel("ky" if is_kspace else "y (voxels)", fontsize=9)
    ax.set_title(title)

    cbar = fig.colorbar(img, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Phase (radians)", color="#334155", fontsize=8.5)
    cbar.set_ticks([-np.pi, -np.pi / 2, 0, np.pi / 2, np.pi])
    cbar.set_ticklabels(["-π", "-π/2", "0", "+π/2", "+π"])
    cbar.outline.set_edgecolor("#cbd5e1")
    cbar.ax.tick_params(labelsize=8)

    fig.tight_layout()
    return fig


def plot_error_heatmap(
    error_map: np.ndarray,
    title: str = "Absolute Error Heatmap",
    vmax: Optional[float] = None,
) -> plt.Figure:
    """
    Displays spatial error difference |I_ref - I_recon| with perceptually uniform
    inferno colormap and standard intensity scaling.
    """
    setup_mpl_style()
    fig, ax = plt.subplots(figsize=(4.8, 4.8))

    if vmax is None:
        p99 = float(np.percentile(error_map, 99.5)) if error_map.size > 0 else 1.0
        vmax = max(0.2, min(1.0, p99 * 1.1))

    img = ax.imshow(
        error_map,
        cmap="inferno",
        origin="upper",
        interpolation="bilinear",
        vmin=0.0,
        vmax=vmax,
    )

    ax.set_xlabel("x (voxels)", fontsize=9)
    ax.set_ylabel("y (voxels)", fontsize=9)
    ax.set_title(title)

    cbar = fig.colorbar(img, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("|reference - reconstruction|", color="#334155", fontsize=8.5)
    cbar.outline.set_edgecolor("#cbd5e1")
    cbar.ax.tick_params(labelsize=8)

    fig.tight_layout()
    return fig


def plot_ssim_map(
    ssim_map: np.ndarray,
    title: str = "Local SSIM Structural Map",
) -> plt.Figure:
    """
    Displays the local structural similarity index across spatial windows.
    Scale is fixed to [0, 1] where 1.0 represents perfect structural match.
    """
    setup_mpl_style()
    fig, ax = plt.subplots(figsize=(4.8, 4.8))

    img = ax.imshow(
        ssim_map,
        cmap="RdYlGn",
        origin="upper",
        interpolation="bilinear",
        vmin=0.0,
        vmax=1.0,
    )

    ax.set_xlabel("x (voxels)", fontsize=9)
    ax.set_ylabel("y (voxels)", fontsize=9)
    ax.set_title(title)

    cbar = fig.colorbar(img, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("SSIM index (1.0 = exact match)", color="#334155", fontsize=8.5)
    cbar.set_ticks([0.0, 0.25, 0.5, 0.75, 1.0])
    cbar.outline.set_edgecolor("#cbd5e1")
    cbar.ax.tick_params(labelsize=8)

    fig.tight_layout()
    return fig


def plot_mask_overlay(
    log_magnitude: np.ndarray,
    keep_mask: np.ndarray,
    title: str = "Selected k-Space Sampling Region",
) -> plt.Figure:
    """
    Shows k-space with unacquired coordinates dimmed, providing immediate visual
    feedback on the k-space trajectory/subsampling geometry.
    """
    setup_mpl_style()
    fig, ax = plt.subplots(figsize=(4.8, 4.8))

    display = log_magnitude.copy()
    display[~keep_mask] *= 0.18

    img = ax.imshow(
        display,
        cmap="viridis",
        origin="lower",
        interpolation="bilinear",
    )

    ax.set_xlabel("kx (spatial frequency)", fontsize=9)
    ax.set_ylabel("ky (spatial frequency)", fontsize=9)
    ax.set_title(title)

    cbar = fig.colorbar(img, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("log |K(u,v)| (unacquired dimmed)", color="#334155", fontsize=8.5)
    cbar.outline.set_edgecolor("#cbd5e1")
    cbar.ax.tick_params(labelsize=8)

    fig.tight_layout()
    return fig


def plot_retention_curve(
    fractions: List[float],
    series: Dict[str, List[float]],
    title: str = "Reconstruction Quality vs. Data Retained",
) -> plt.Figure:
    """
    Plots metric curves versus retention fraction with polished markers,
    clean line weights, and clear legend.
    """
    setup_mpl_style()
    fig, ax = plt.subplots(figsize=(6.5, 3.8))

    percentages = [f * 100 for f in fractions]
    palette = ["#0d9488", "#2563eb", "#6366f1", "#d97706"]

    for idx, (label, values) in enumerate(series.items()):
        color = palette[idx % len(palette)]
        ax.plot(
            percentages, values,
            marker="o",
            markersize=5,
            linewidth=2,
            color=color,
            markerfacecolor="#ffffff",
            markeredgecolor=color,
            markeredgewidth=2,
            label=label,
            alpha=0.95,
        )

    ax.set_xlabel("k-Space Data Retained (%)")
    first_metric = list(series.keys())[0] if series else "Metric"
    ax.set_ylabel(first_metric)
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.6, color="#e2e8f0")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    if len(series) > 1:
        ax.legend(loc="best")

    fig.tight_layout()
    return fig
