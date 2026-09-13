"""
core/kspace_engine.py

The mathematical heart of the MRI module: the 2D Fourier relationship
between an image and its k-space (frequency-domain) representation.

WHY K-SPACE, NOT JUST "FILTER THE IMAGE"?
An MRI scanner does not photograph the body directly. It measures the
2D Fourier transform of the proton-density image, one point (or line)
of k-space at a time. The image itself only exists after an inverse
FFT is applied to whatever k-space data was actually acquired. This
module treats k-space as ACQUIRED DATA that can be partial, not as a
filter applied after the fact -- that distinction is the entire point
of the simulator.

k-space is complex-valued, exactly like the audio module's STFT:

    K(u, v) = |K(u, v)| * exp(1j * phase(u, v))

    magnitude -> contrast / how much signal at this spatial frequency
    phase     -> spatial alignment information

A real-valued grayscale image has a very "boring" phase (only 0 or pi,
because the FFT of a real signal is conjugate-symmetric). To make the
Magnitude vs. Phase tab actually demonstrate something, we optionally
stamp a smooth synthetic phase onto the image before transforming --
this mimics coil/field inhomogeneity phase effects in real MRI without
claiming to be physically exact.
"""

import numpy as np

EPS = 1e-12


def fft2_centered(image: np.ndarray) -> np.ndarray:
    """Centered 2D FFT: image (space domain) -> k-space (frequency domain)."""
    return np.fft.fftshift(np.fft.fft2(image))


def ifft2_centered(kspace: np.ndarray) -> np.ndarray:
    """Centered inverse 2D FFT: k-space -> complex image."""
    return np.fft.ifft2(np.fft.ifftshift(kspace))


def magnitude_phase(kspace: np.ndarray):
    """Split complex k-space into magnitude and phase arrays."""
    return np.abs(kspace), np.angle(kspace)


def combine_magnitude_phase(magnitude: np.ndarray, phase: np.ndarray) -> np.ndarray:
    """Rebuild complex k-space from separate magnitude and phase arrays."""
    return magnitude * np.exp(1j * phase)


def kspace_log_magnitude(kspace: np.ndarray) -> np.ndarray:
    """
    Log-scaled, [0, 1]-normalized k-space magnitude, for display only.
    k-space energy is enormously concentrated at the center; without
    log scaling, an image of raw magnitude looks like a single bright
    dot on a black background.
    """
    magnitude = np.abs(kspace)
    display = np.log1p(magnitude)
    return (display - display.min()) / (display.max() - display.min() + EPS)


def create_phase_map(shape: tuple, strength: float) -> np.ndarray:
    """
    A smooth synthetic spatial phase field, for demonstrating why phase
    matters. Intentionally simple (a low-order polynomial in x, y) --
    not a physical field-inhomogeneity model, just enough structure to
    be visually and audibly meaningful.
    """
    rows, cols = shape
    y, x = np.mgrid[-1:1:complex(rows), -1:1:complex(cols)]
    return strength * (0.7 * x + 0.3 * y + 0.25 * x * y)


def create_complex_image(magnitude_image: np.ndarray, phase_strength: float):
    """
    Turn a real-valued magnitude image into a complex image by
    attaching a synthetic phase map, mimicking the fact that real MRI
    images are inherently complex-valued before magnitude display.

    Returns (complex_image, phase_map_used).
    """
    phase = create_phase_map(magnitude_image.shape, phase_strength)
    complex_image = magnitude_image * np.exp(1j * phase)
    return complex_image, phase
