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


def build_polygon_mask(
    shape: tuple,
    sr: int,
    n_fft: int,
    hop_length: int,
    vertices: list,
) -> np.ndarray:
    """
    Build a boolean mask for an arbitrary polygon region.
    vertices: list of [time_sec, freq_hz] pairs (at least 3).
    Uses ray-casting point-in-polygon test.
    True = inside the polygon.
    """
    n_freq_bins, n_frames = shape

    freqs = frequency_axis(sr=sr, n_fft=n_fft)
    times = time_axis(n_frames, sr=sr, hop_length=hop_length)

    # Extract polygon edges as arrays for vectorized testing
    vx = np.array([v[0] for v in vertices], dtype=np.float64)  # time coords
    vy = np.array([v[1] for v in vertices], dtype=np.float64)  # freq coords

    n_verts = len(vx)

    # Build 2D grid: rows=freq bins, cols=time frames
    # T[i,j] = time of frame j, F[i,j] = freq of bin i
    T, F = np.meshgrid(times, freqs)  # both shape (n_freq_bins, n_frames)

    inside = np.zeros((n_freq_bins, n_frames), dtype=bool)

    # Vectorized ray-casting: for each edge (vi -> vj),
    # count how many edges cross the ray cast rightward from each point
    j = n_verts - 1
    for i in range(n_verts):
        xi, yi = vx[i], vy[i]
        xj, yj = vx[j], vy[j]

        # Condition 1: one vertex above, one below the test point (freq axis)
        cond1 = ((vy[i] > F) != (vy[j] > F))

        # Condition 2: test point is left of the edge crossing
        # x_intersect = xj + (F - yj) / (yi - yj) * (xi - xj)
        dy = yi - yj
        # Avoid division by zero — where dy==0, cond1 is already False
        safe_dy = np.where(dy == 0, 1.0, dy)
        x_intersect = xj + (F - yj) / safe_dy * (xi - xj)
        cond2 = T < x_intersect

        inside ^= (cond1 & cond2)
        j = i

    return inside

def build_multi_region_mask(
    shape: tuple,
    sr: int,
    n_fft: int,
    hop_length: int,
    regions: list,
) -> np.ndarray:
    """
    Build one final keep-mask from multiple polygon regions.

    Rules:
        - Union of all enabled isolate regions = base keep (if any isolate exists)
        - If no isolate regions: keep everything
        - Then subtract union of all enabled remove regions
        - Remove always has priority over isolate
    """
    isolate_mask = np.zeros(shape, dtype=bool)
    remove_mask  = np.zeros(shape, dtype=bool)
    has_enabled_isolate = False

    for region in regions:
        if not region.get("enabled", True):
            continue

        mode = region.get("mode", "remove")

        # Support both polygon (vertices) and legacy rect regions
        vertices = region.get("vertices", None)

        if vertices is not None and len(vertices) >= 3:
            region_mask = build_polygon_mask(
                shape=shape,
                sr=sr,
                n_fft=n_fft,
                hop_length=hop_length,
                vertices=vertices,
            )
        else:
            # Fallback to rect for legacy regions
            region_mask = build_region_mask(
                shape=shape,
                sr=sr,
                n_fft=n_fft,
                hop_length=hop_length,
                freq_range_hz=(region["freq_min"], region["freq_max"]),
                time_range_sec=(region["time_min"], region["time_max"]),
            )

        if mode == "remove":
            remove_mask |= region_mask
        elif mode == "isolate":
            isolate_mask |= region_mask
            has_enabled_isolate = True
        else:
            raise ValueError(f"Unknown region mode '{mode}'.")

    if has_enabled_isolate:
        keep_mask = isolate_mask.copy()
    else:
        keep_mask = np.ones(shape, dtype=bool)

    keep_mask &= ~remove_mask
    return keep_mask

def apply_mask(D: np.ndarray, keep_mask: np.ndarray) -> np.ndarray:
    """
    Apply a boolean keep-mask to an STFT matrix.
    """
    return D * keep_mask