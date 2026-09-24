import numpy as np

from audio_core.stft_engine import frequency_axis, time_axis


def build_time_freq_mask(
    shape: tuple,
    sr: int,
    n_fft: int,
    hop_length: int,
    freq_range_hz: tuple,
    time_range_sec: tuple,
    mode: str = "remove",
) -> np.ndarray:
    """
    Build a keep-mask for one rectangular time-frequency region.

    mode="remove":
        Keep everything except the selected region.

    mode="isolate":
        Keep only the selected region.

    This function is kept for backward compatibility with the
    original single-region masking implementation.
    """
    n_freq_bins, n_frames = shape

    freqs = frequency_axis(sr=sr, n_fft=n_fft)
    times = time_axis(n_frames, sr=sr, hop_length=hop_length)

    f_min, f_max = freq_range_hz
    t_min, t_max = time_range_sec

    freq_in_region = (freqs >= f_min) & (freqs <= f_max)
    time_in_region = (times >= t_min) & (times <= t_max)

    region = np.outer(freq_in_region, time_in_region)

    if mode == "remove":
        keep_mask = ~region
    elif mode == "isolate":
        keep_mask = region
    else:
        raise ValueError(
            f"Unknown mode '{mode}', expected 'remove' or 'isolate'."
        )

    return keep_mask


def build_region_mask(
    shape: tuple,
    sr: int,
    n_fft: int,
    hop_length: int,
    freq_range_hz: tuple,
    time_range_sec: tuple,
) -> np.ndarray:
    """
    Build a boolean mask representing the selected rectangular region.

    True  = inside the region
    False = outside the region
    """
    n_freq_bins, n_frames = shape

    freqs = frequency_axis(sr=sr, n_fft=n_fft)
    times = time_axis(n_frames, sr=sr, hop_length=hop_length)

    f_min, f_max = freq_range_hz
    t_min, t_max = time_range_sec

    freq_in_region = (freqs >= f_min) & (freqs <= f_max)
    time_in_region = (times >= t_min) & (times <= t_max)

    return np.outer(freq_in_region, time_in_region)


def build_multi_region_mask(
    shape: tuple,
    sr: int,
    n_fft: int,
    hop_length: int,
    regions: list,
) -> np.ndarray:
    """
    Build one final keep-mask from multiple time-frequency regions.

    Region rules:

        Remove + Remove   -> Remove
        Remove + Isolate  -> Remove
        Isolate + Remove  -> Remove
        Isolate + Isolate -> Isolate

    Therefore Remove always has priority over Isolate.

    If there are enabled isolate regions:
        Start by keeping the union of all isolate regions.

    If there are no enabled isolate regions:
        Start by keeping the entire spectrogram.

    Then remove the union of all enabled remove regions.

    Disabled regions are completely ignored.
    """

    # Start with no regions selected.
    isolate_mask = np.zeros(shape, dtype=bool)
    remove_mask = np.zeros(shape, dtype=bool)

    has_enabled_isolate = False

    for region in regions:
        # Disabled regions do not participate in the final mask.
        if not region.get("enabled", True):
            continue

        mode = region.get("mode", "remove")

        region_mask = build_region_mask(
            shape=shape,
            sr=sr,
            n_fft=n_fft,
            hop_length=hop_length,
            freq_range_hz=(
                region["freq_min"],
                region["freq_max"],
            ),
            time_range_sec=(
                region["time_min"],
                region["time_max"],
            ),
        )

        if mode == "remove":
            # Union of all remove regions.
            remove_mask |= region_mask

        elif mode == "isolate":
            # Union of all isolate regions.
            isolate_mask |= region_mask
            has_enabled_isolate = True

        else:
            raise ValueError(
                f"Unknown region mode '{mode}', "
                "expected 'remove' or 'isolate'."
            )

    # If at least one isolate region exists,
    # only the union of isolate regions is initially kept.
    #
    # Otherwise, everything is initially kept.
    if has_enabled_isolate:
        keep_mask = isolate_mask.copy()
    else:
        keep_mask = np.ones(shape, dtype=bool)

    # Remove always has priority over isolate.
    keep_mask &= ~remove_mask

    return keep_mask


def apply_mask(D: np.ndarray, keep_mask: np.ndarray) -> np.ndarray:
    """
    Apply a boolean keep-mask to an STFT matrix.
    """
    return D * keep_mask