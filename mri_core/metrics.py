"""
core/metrics.py

Quantitative reconstruction-quality metrics for the MRI module, as
required by the spec: MSE, PSNR, SSIM, and an error heatmap.

All functions assume both images are already normalized to [0, 1] and
the same shape.
"""

import numpy as np
from scipy.ndimage import gaussian_filter

EPS = 1e-12


def mse_metric(reference: np.ndarray, reconstruction: np.ndarray) -> float:
    """Mean squared error. Lower is better; 0 = identical images."""
    return float(np.mean((reference - reconstruction) ** 2))


def psnr_metric(reference: np.ndarray, reconstruction: np.ndarray, data_range: float = 1.0) -> float:
    """
    Peak Signal-to-Noise Ratio in decibels. Higher is better.

    PSNR = 10 * log10( data_range^2 / MSE )

    A logarithmic measure derived from MSE; because it's logarithmic,
    it's more forgiving of small errors and more sensitive to whether
    ANY large error exists than raw MSE is.
    """
    mse = mse_metric(reference, reconstruction)
    if mse < EPS:
        return float("inf")
    return 10 * np.log10((data_range ** 2) / mse)


def ssim_metric(
    reference: np.ndarray,
    reconstruction: np.ndarray,
    data_range: float = 1.0,
    sigma: float = 1.5,
    k1: float = 0.01,
    k2: float = 0.03,
):
    """
    Structural Similarity Index (SSIM), computed with a Gaussian
    sliding window (the standard Wang et al. 2004 formulation).

    Unlike MSE/PSNR, which compare pixels independently, SSIM compares
    local LUMINANCE, CONTRAST, and STRUCTURE -- it penalizes a blurry
    or structurally distorted reconstruction even if its average pixel
    error happens to be small, which is exactly the failure mode
    aggressive k-space undersampling produces.

    Returns
    -------
    score : float in [-1, 1], where 1.0 = identical images.
    ssim_map : 2D array, the same score computed locally at every
               pixel -- useful as a spatial "where did structure break
               down" visualization, a level of detail plain MSE/PSNR
               don't offer.
    """
    C1 = (k1 * data_range) ** 2
    C2 = (k2 * data_range) ** 2

    mu1 = gaussian_filter(reference, sigma)
    mu2 = gaussian_filter(reconstruction, sigma)

    mu1_sq, mu2_sq, mu1_mu2 = mu1 ** 2, mu2 ** 2, mu1 * mu2

    sigma1_sq = gaussian_filter(reference ** 2, sigma) - mu1_sq
    sigma2_sq = gaussian_filter(reconstruction ** 2, sigma) - mu2_sq
    sigma12 = gaussian_filter(reference * reconstruction, sigma) - mu1_mu2

    numerator = (2 * mu1_mu2 + C1) * (2 * sigma12 + C2)
    denominator = (mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2)

    ssim_map = numerator / (denominator + EPS)

    return float(np.mean(ssim_map)), ssim_map


def error_heatmap(reference: np.ndarray, reconstruction: np.ndarray) -> np.ndarray:
    """Pixelwise absolute error map (not normalized -- caller decides display scaling)."""
    return np.abs(reference - reconstruction)
