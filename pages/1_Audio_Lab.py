"""
app.py

FourierLab -- Audio Module
Streamlit front-end tying together core/ (DSP logic) and utils/ (I/O +
plotting). Run with:

    streamlit run app.py
"""

from datetime import datetime
from pathlib import Path

import numpy as np
import streamlit as st

from audio_core.stft_engine import (
    compute_stft,
    compute_istft,
    magnitude_phase,
    combine_magnitude_phase,
    magnitude_to_db,
    frequency_axis,
)
from audio_core.masking import build_time_freq_mask, apply_mask
from audio_core.reconstruction import (
    retain_low_frequencies,
    retain_top_magnitude,
    retention_sweep,
)
from audio_core.metrics import snr_db, mse, spectral_convergence

from audio_utils.audio_io import load_audio, waveform_to_wav_bytes
from audio_utils.plotting import (
    plot_waveform,
    plot_spectrogram,
    plot_phase,
    plot_retention_curve,
    plot_mask_overlay,
)


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="FourierLab - Audio Spectrogram Lab",
    page_icon="🎧",
    layout="wide",
)

st.title("FourierLab: Audio Frequency-Domain Explorer")

st.markdown(
    """
    **Explore audio through its Short-Time Fourier Transform (STFT).**

    Just like the MRI module treats k-space as measurement data you can
    selectively acquire, this module treats the spectrogram as
    frequency-domain data you can mask, threshold, and partially
    reconstruct from -- while listening to the result.
    """
)


# ============================================================
# SAMPLE / SAVED-RESULT GALLERY FOLDERS
# ============================================================

APP_ROOT = Path(__file__).resolve().parent.parent
AUDIO_SAMPLES_DIR = APP_ROOT / "assets" / "audio" / "samples"
AUDIO_SAVED_DIR = APP_ROOT / "assets" / "audio" / "saved"
AUDIO_SAVED_DIR.mkdir(parents=True, exist_ok=True)


def save_audio_result(y_arr: np.ndarray, sr_val: int, label: str) -> Path:
    """Write a reconstructed waveform into the saved-results gallery folder."""
    filename = f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    path = AUDIO_SAVED_DIR / filename
    with open(path, "wb") as f:
        f.write(waveform_to_wav_bytes(y_arr, sr_val))
    return path


# ============================================================
# SIDEBAR -- GLOBAL CONTROLS
# ============================================================

st.sidebar.header("Audio & STFT Settings")

source_choice = st.sidebar.radio(
    "Audio source",
    ["Upload my own", "Use a sample / saved result"],
)

audio_source = None

if source_choice == "Upload my own":
    audio_source = st.sidebar.file_uploader(
        "Upload an audio clip",
        type=["wav", "mp3", "flac", "ogg", "m4a"],
    )
else:
    # Samples and previously-saved results both show up here, so users
    # can chain experiments (e.g. re-mask something they saved earlier).
    gallery_files = sorted(AUDIO_SAMPLES_DIR.glob("*.wav")) + sorted(AUDIO_SAVED_DIR.glob("*.wav"))
    if not gallery_files:
        st.sidebar.warning("No sample/saved audio found. Add .wav files to assets/audio/samples/.")
    else:
        picked = st.sidebar.selectbox(
            "Choose a clip",
            gallery_files,
            format_func=lambda p: f"{p.stem}  ({'sample' if p.parent.name == 'samples' else 'saved'})",
        )
        audio_source = str(picked)

target_sr = st.sidebar.selectbox(
    "Analysis sample rate (Hz)",
    options=[16000, 22050, 44100],
    index=1,
    help="Audio is resampled to this rate before analysis. Lower = faster, less high-frequency detail.",
)

st.sidebar.subheader("STFT Parameters")

n_fft = st.sidebar.select_slider(
    "FFT window size (n_fft)",
    options=[512, 1024, 2048, 4096],
    value=2048,
    help="Larger = better frequency resolution, worse time resolution.",
)

hop_length = st.sidebar.select_slider(
    "Hop length",
    options=[128, 256, 512, 1024],
    value=512,
    help="Samples between analysis frames. Smaller = smoother time resolution, more computation.",
)

win_length = n_fft  # keep it simple: analysis window == FFT size


# ============================================================
# LOAD AUDIO
# ============================================================

if audio_source is None:
    st.info("Upload an audio file, or choose a sample, from the sidebar to begin.")
    st.stop()

y, sr = load_audio(audio_source, target_sr=target_sr, mono=True)
duration = len(y) / sr

st.sidebar.success(f"Loaded: {duration:.2f}s @ {sr} Hz")


# ============================================================
# COMPUTE FULL STFT (shared across all tabs)
# ============================================================

D_full = compute_stft(y, n_fft=n_fft, hop_length=hop_length, win_length=win_length)
magnitude_full, phase_full = magnitude_phase(D_full)
magnitude_db_full = magnitude_to_db(magnitude_full)

n_freq_bins, n_frames = D_full.shape
freqs = frequency_axis(sr=sr, n_fft=n_fft)


# ============================================================
# TABS
# ============================================================

tabs = st.tabs(
    [
        "Overview",
        "Spectrogram Analysis",
        "Time-Frequency Masking",
        "Progressive Reconstruction",
        "Metrics",
    ]
)


# ------------------------------------------------------------
# TAB 1 -- OVERVIEW
# ------------------------------------------------------------

with tabs[0]:

    st.header("Signal Overview")

    st.audio(waveform_to_wav_bytes(y, sr), format="audio/wav")

    st.pyplot(plot_waveform(y, sr, title="Time-Domain Waveform"), use_container_width=True)

    st.pyplot(
        plot_spectrogram(
            magnitude_db_full, sr, hop_length, n_fft,
            title="STFT Magnitude Spectrogram (dB)",
        ),
        use_container_width=True,
    )

    st.info(
        """
        The spectrogram is the audio equivalent of MRI k-space: it is a
        2D frequency-domain representation (frequency vs. time here,
        instead of spatial frequency vs. spatial frequency). Bright
        horizontal bands are sustained tones or harmonics; vertical
        streaks are transient, percussive events.
        """
    )


# ------------------------------------------------------------
# TAB 2 -- SPECTROGRAM ANALYSIS (magnitude vs phase)
# ------------------------------------------------------------

with tabs[1]:

    st.header("Magnitude vs. Phase")

    st.markdown(
        r"""
        Every STFT bin is a complex number
        $D(f,t) = |D(f,t)| \, e^{j\phi(f,t)}$.
        The **magnitude** tells you how much energy is present; the
        **phase** tells you the timing/alignment of that energy. Human
        hearing is far more sensitive to magnitude than to phase, but
        phase is still required to reconstruct an exact waveform.
        """
    )

    col1, col2 = st.columns(2)

    with col1:
        st.pyplot(
            plot_spectrogram(
                magnitude_db_full, sr, hop_length, n_fft,
                title="Magnitude Spectrogram (dB)",
            ),
            use_container_width=True,
        )

    with col2:
        st.pyplot(
            plot_phase(phase_full, sr, hop_length, title="Phase Spectrogram"),
            use_container_width=True,
        )

    st.subheader("Reconstruct from magnitude-only vs. phase-only")

    st.caption(
        "To isolate magnitude's contribution, phase is replaced with all "
        "zeros. To isolate phase's contribution, magnitude is flattened "
        "to a constant. Neither is a realistic signal -- this is a "
        "diagnostic, not a usable reconstruction."
    )

    magnitude_only_D = combine_magnitude_phase(magnitude_full, np.zeros_like(phase_full))
    phase_only_D = combine_magnitude_phase(np.ones_like(magnitude_full), phase_full)

    magnitude_only_y = compute_istft(magnitude_only_D, hop_length, win_length, length=len(y))
    phase_only_y = compute_istft(phase_only_D, hop_length, win_length, length=len(y))

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Magnitude-only** (phase discarded)")
        st.audio(waveform_to_wav_bytes(magnitude_only_y, sr), format="audio/wav")

    with col2:
        st.write("**Phase-only** (magnitude flattened)")
        st.audio(waveform_to_wav_bytes(phase_only_y, sr), format="audio/wav")


# ------------------------------------------------------------
# TAB 3 -- TIME-FREQUENCY MASKING
# ------------------------------------------------------------

with tabs[2]:

    st.header("Time-Frequency Masking")

    st.markdown(
        "Select a rectangular region of the spectrogram and either "
        "**remove** it or **isolate** it, then reconstruct the audio."
    )

    col1, col2 = st.columns(2)

    with col1:
        freq_range = st.slider(
            "Frequency range (Hz)",
            min_value=0,
            max_value=int(sr / 2),
            value=(0, int(sr / 4)),
        )

    with col2:
        time_range = st.slider(
            "Time range (s)",
            min_value=0.0,
            max_value=float(duration),
            value=(0.0, float(duration)),
        )

    mask_mode = st.radio(
        "Mask mode",
        ["remove", "isolate"],
        horizontal=True,
        help="'remove' zeroes out the selected region; 'isolate' keeps only the selected region.",
    )

    keep_mask = build_time_freq_mask(
        shape=D_full.shape,
        sr=sr,
        n_fft=n_fft,
        hop_length=hop_length,
        freq_range_hz=freq_range,
        time_range_sec=time_range,
        mode=mask_mode,
    )

    D_masked = apply_mask(D_full, keep_mask)
    y_masked = compute_istft(D_masked, hop_length, win_length, length=len(y))

    st.pyplot(
        plot_mask_overlay(magnitude_db_full, keep_mask, sr, hop_length, title="Selected Region (dimmed = removed)"),
        use_container_width=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Original**")
        st.audio(waveform_to_wav_bytes(y, sr), format="audio/wav")

    with col2:
        st.write("**Masked reconstruction**")
        st.audio(waveform_to_wav_bytes(y_masked, sr), format="audio/wav")

    masked_snr = snr_db(y, y_masked)
    st.metric("SNR after masking", f"{masked_snr:.2f} dB" if np.isfinite(masked_snr) else "∞")

    if st.button("💾 Save masked reconstruction to gallery", key="save_masked_audio"):
        saved_path = save_audio_result(y_masked, sr, f"masked_{mask_mode}")
        st.success(f"Saved to assets/audio/saved/{saved_path.name}")


# ------------------------------------------------------------
# TAB 4 -- PROGRESSIVE RECONSTRUCTION
# ------------------------------------------------------------

with tabs[3]:

    st.header("Progressive Reconstruction")

    st.markdown(
        """
        Keep only a fraction of the frequency-domain information and
        reconstruct. This mirrors the MRI module's "acquisition
        percentage" experiments: less retained data generally means
        worse reconstruction, but *how* it degrades depends on
        *which* data you keep.
        """
    )

    strategy = st.selectbox(
        "Retention strategy",
        ["low_frequency", "top_magnitude"],
        format_func=lambda s: {
            "low_frequency": "Low-frequency retention (band-limit, like keeping k-space center)",
            "top_magnitude": "Top-magnitude retention (keep loudest bins anywhere)",
        }[s],
    )

    keep_fraction = st.slider(
        "Fraction of data retained",
        min_value=0.01,
        max_value=1.0,
        value=0.30,
        step=0.01,
    )

    if strategy == "low_frequency":
        D_retained = retain_low_frequencies(D_full, keep_fraction)
    else:
        D_retained = retain_top_magnitude(D_full, keep_fraction)

    y_retained = compute_istft(D_retained, hop_length, win_length, length=len(y))
    magnitude_retained_db = magnitude_to_db(np.abs(D_retained), ref=np.max(magnitude_full) + 1e-12)

    st.pyplot(
        plot_spectrogram(
            magnitude_retained_db, sr, hop_length, n_fft,
            title=f"Retained Spectrogram ({keep_fraction * 100:.0f}% kept)",
        ),
        use_container_width=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Original**")
        st.audio(waveform_to_wav_bytes(y, sr), format="audio/wav")

    with col2:
        st.write(f"**Reconstructed ({keep_fraction * 100:.0f}% retained)**")
        st.audio(waveform_to_wav_bytes(y_retained, sr), format="audio/wav")

    retained_snr = snr_db(y, y_retained)
    st.metric("SNR", f"{retained_snr:.2f} dB" if np.isfinite(retained_snr) else "∞")

    if st.button("💾 Save reconstruction to gallery", key="save_retained_audio"):
        saved_path = save_audio_result(y_retained, sr, f"retained_{strategy}_{int(keep_fraction*100)}pct")
        st.success(f"Saved to assets/audio/saved/{saved_path.name}")

    st.divider()
    st.subheader("Quality vs. Retention Curve")

    if st.button("Run retention sweep (may take a few seconds)"):

        fractions = [0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0]

        sweep_results = retention_sweep(D_full, strategy, fractions)

        snr_values = []
        for frac, D_variant in sweep_results:
            y_variant = compute_istft(D_variant, hop_length, win_length, length=len(y))
            snr_values.append(snr_db(y, y_variant))

        # Cap infinite SNR for plotting purposes.
        finite_max = max([v for v in snr_values if np.isfinite(v)], default=60)
        snr_plot_values = [v if np.isfinite(v) else finite_max * 1.1 for v in snr_values]

        st.pyplot(
            plot_retention_curve(
                fractions, snr_plot_values,
                ylabel="SNR (dB)",
                title=f"Reconstruction Quality vs. Data Retained ({strategy})",
            ),
            use_container_width=True,
        )


# ------------------------------------------------------------
# TAB 5 -- METRICS
# ------------------------------------------------------------

with tabs[4]:

    st.header("Quantitative Comparison")

    st.markdown("Compare the **original** signal against the **masked** result from the Masking tab.")

    m_snr = snr_db(y, y_masked)
    m_mse = mse(y, y_masked)
    m_spec_conv = spectral_convergence(magnitude_full, np.abs(D_masked))

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("SNR", f"{m_snr:.2f} dB" if np.isfinite(m_snr) else "∞")

    with col2:
        st.metric("MSE", f"{m_mse:.6f}")

    with col3:
        st.metric("Spectral Convergence", f"{m_spec_conv:.4f}")

    st.markdown(
        """
        **SNR (Signal-to-Noise Ratio)** -- higher is better; measures
        how much of the original waveform survives, in decibels.

        **MSE (Mean Squared Error)** -- lower is better; average
        squared sample-by-sample difference in the time domain.

        **Spectral Convergence** -- lower is better (0 = identical);
        measures error directly in the magnitude-spectrogram domain,
        which is where we've actually been making changes.
        """
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()
st.caption(
    "FourierLab Audio Module -- educational STFT/ISTFT signal processing demo. "
    "Not intended for production audio engineering use."
)
