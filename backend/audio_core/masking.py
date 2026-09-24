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
        raise ValueError(f"Unknown mode '{mode}', expected 'remove' or 'isolate'.")

    return keep_mask


def apply_mask(D: np.ndarray, keep_mask: np.ndarray) -> np.ndarray:
    return D * keep_mask