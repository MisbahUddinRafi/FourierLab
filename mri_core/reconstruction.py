"""
core/reconstruction.py

"Progressive reconstruction": simulate acquiring only a fraction of
k-space and reconstructing from that partial data, so the user can see
how image quality degrades as less data is retained. Direct analogue
of core/reconstruction.py in the audio module.

Two retention strategies:

1. CENTER-RADIUS RETENTION (undersampled acquisition)
   Keep only a disk around the k-space center, sized so it contains
   approximately `keep_fraction` of all samples. This is the classic
   MRI story: the center carries contrast/overall structure, so even
   a small central disk gives a recognizable (if blurry) image.

2. TOP-MAGNITUDE RETENTION (data-driven / compressive)
   Keep only the globally strongest-magnitude k-space samples,
   wherever they are. Closer to how compressed sensing / compression
   schemes allocate data: spend it on the highest-energy coefficients.
"""

import numpy as np


def _radius_for_fraction(shape: tuple, keep_fraction: float) -> float:
    """
    Choose a disk radius (in the same normalized units as
    masking._radius_grid, i.e. corners at ~1.41) so the disk's AREA
    is approximately `keep_fraction` of the full [-1,1]x[-1,1] square.

    Area of a disk of radius r is pi*r^2; area of the square is 4.
    Solve pi*r^2 = keep_fraction * 4  =>  r = sqrt(4*keep_fraction/pi).
    This is an approximation (the true retained fraction is checked
    and returned by the caller); it gets us close in one step instead
    of an iterative search.
    """
    keep_fraction = float(np.clip(keep_fraction, 1e-4, 1.0))
    return np.sqrt(4.0 * keep_fraction / np.pi)


def retain_center_fraction(kspace: np.ndarray, keep_fraction: float):
    """
    Keep a centered disk of k-space sized to approximately
    `keep_fraction` of all samples.

    Returns
    -------
    kspace_masked : complex 2D array
    actual_fraction : float, the TRUE fraction of samples retained
                       (may differ slightly from keep_fraction because
                       the disk doesn't perfectly tile a square grid)
    """
    from mri_core.masking import circular_region  # local import avoids a cycle at module load

    keep_fraction = float(np.clip(keep_fraction, 1e-4, 1.0))

    if keep_fraction >= 0.999:
        # A disk can only exactly cover a square at its diagonal-corner
        # radius; handle "keep everything" as an explicit special case
        # rather than relying on the area approximation below.
        return kspace.copy(), 1.0

    radius = _radius_for_fraction(kspace.shape, keep_fraction)
    region = circular_region(kspace.shape, radius)

    kspace_masked = kspace * region
    actual_fraction = float(np.count_nonzero(region)) / region.size

    return kspace_masked, actual_fraction


def retain_top_magnitude(kspace: np.ndarray, keep_fraction: float):
    """
    Keep only the top `keep_fraction` of k-space samples by magnitude,
    globally across the whole 2D array.

    Returns
    -------
    kspace_masked : complex 2D array
    actual_fraction : float, the TRUE fraction of samples retained
    """
    keep_fraction = float(np.clip(keep_fraction, 1e-4, 1.0))

    if keep_fraction >= 1.0:
        return kspace.copy(), 1.0

    magnitude = np.abs(kspace)
    threshold = np.percentile(magnitude.ravel(), 100.0 * (1.0 - keep_fraction))

    keep_mask = magnitude >= threshold
    kspace_masked = kspace * keep_mask
    actual_fraction = float(np.count_nonzero(keep_mask)) / keep_mask.size

    return kspace_masked, actual_fraction


def retention_sweep(kspace: np.ndarray, strategy: str, fractions):
    """
    Apply a retention strategy at several fractions in one call, used
    to build the "quality vs. retained data" curve.

    Returns a list of (requested_fraction, actual_fraction, kspace_masked).
    """
    if strategy == "center_radius":
        fn = retain_center_fraction
    elif strategy == "top_magnitude":
        fn = retain_top_magnitude
    else:
        raise ValueError(f"Unknown strategy '{strategy}'.")

    results = []
    for frac in fractions:
        kspace_masked, actual_fraction = fn(kspace, frac)
        results.append((frac, actual_fraction, kspace_masked))

    return results
