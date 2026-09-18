"""
pages/1_Audio_Lab.py

FourierLab -- Audio Spectrogram Module
Educational Short-Time Fourier Transform (STFT) exploration workbench.
Redesigned with refined scientific UI, grouped sidebar controls,
flowchart ribbons, log-frequency spectrograms, and interactive sweeps.
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
from ui_theme import (
    apply_theme,
    render_logo,
    render_pipeline_flowchart,
    render_quick_start,
)

# ============================================================
# PAGE CONFIGURATION & THEME
# ============================================================

st.set_page_config(
    page_title="Audio Lab | FourierLab",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()

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
# SIDEBAR -- GROUPED CONTROLS
# ============================================================

render_logo("sidebar")

st.sidebar.markdown(
    """
    <div style="font-size: 0.75rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;">
        1. Audio Source
    </div>
    """,
    unsafe_allow_html=True,
)

source_choice = st.sidebar.radio(
    "Audio source",
    ["Use a sample / saved result", "Upload my own"],
    label_visibility="collapsed",
)

audio_source = None

if source_choice == "Upload my own":
    audio_source = st.sidebar.file_uploader(
        "Upload audio file",
        type=["wav", "mp3", "flac", "ogg", "m4a"],
        help="Upload a mono or stereo audio file.",
    )
else:
    # Samples and previously-saved results both show up here
    gallery_files = sorted(AUDIO_SAMPLES_DIR.glob("*.wav")) + sorted(AUDIO_SAVED_DIR.glob("*.wav"))
    if not gallery_files:
        st.sidebar.warning("No sample/saved audio found in assets/audio/samples/.")
    else:
        picked = st.sidebar.selectbox(
            "Choose audio clip",
            gallery_files,
            format_func=lambda p: f"{'📁 ' if p.parent.name == 'samples' else '💾 '}{p.stem} ({p.parent.name})",
        )
        audio_source = str(picked)

st.sidebar.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
st.sidebar.markdown(
    """
    <div style="font-size: 0.75rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;">
        2. STFT Transform Settings
    </div>
    """,
    unsafe_allow_html=True,
)

target_sr = st.sidebar.selectbox(
    "Analysis sample rate (Hz)",
    options=[16000, 22050, 44100],
    index=1,
    help="Audio is resampled to this rate before analysis. Lower = faster computation.",
)

n_fft = st.sidebar.select_slider(
    "FFT window size (n_fft)",
    options=[512, 1024, 2048, 4096],
    value=2048,
    help="Larger window = better frequency resolution, worse time resolution (Heisenberg-Gabor limit).",
)

hop_length = st.sidebar.select_slider(
    "Hop length (overlap step)",
    options=[128, 256, 512, 1024],
    value=512,
    help="Step size between analysis frames. Smaller = smoother time resolution.",
)

win_length = n_fft

st.sidebar.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
st.sidebar.markdown(
    """
    <div style="font-size: 0.75rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;">
        3. Spectrogram Display
    </div>
    """,
    unsafe_allow_html=True,
)

freq_scale_mode = st.sidebar.selectbox(
    "Frequency scale",
    options=["log", "linear"],
    format_func=lambda s: "Log-frequency (perceptual hearing)" if s == "log" else "Linear frequency (standard FFT)",
    help="Log scale matches human auditory pitch perception and expands low-to-mid voice & musical harmonics.",
)

# ============================================================
# LOAD AUDIO & COMPUTE STFT
# ============================================================

if audio_source is None:
    render_logo("header", subtitle="Short-Time Fourier Transform (STFT) Analysis")
    render_pipeline_flowchart("audio")
    st.info("👋 Upload an audio file or select a clip from the sidebar to begin analysis.")
    st.stop()

y, sr = load_audio(audio_source, target_sr=target_sr, mono=True)
duration = len(y) / sr

# Sidebar metadata badge
st.sidebar.markdown(
    f"""
    <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 10px; margin-top: 10px; font-size: 0.78rem; color: #cbd5e1;">
        <div style="font-weight: 600; color: #38bdf8; margin-bottom: 4px;">Active Audio Signal</div>
        <div>Duration: <strong>{duration:.2f} s</strong> ({len(y):,} samples)</div>
        <div>Sample Rate: <strong>{sr} Hz</strong> (Nyquist: {sr//2} Hz)</div>
    </div>
    """,
    unsafe_allow_html=True,
)

D_full = compute_stft(y, n_fft=n_fft, hop_length=hop_length, win_length=win_length)
magnitude_full, phase_full = magnitude_phase(D_full)
magnitude_db_full = magnitude_to_db(magnitude_full)
n_freq_bins, n_frames = D_full.shape

# ============================================================
# HEADER & WORKFLOW RIBBON
# ============================================================

render_logo("header", subtitle="Time-Frequency Short-Time Fourier Transform (STFT) Explorer")
render_pipeline_flowchart("audio")
render_quick_start("Inspect waveform & log spectrogram", "Mask time-frequency regions", "Run retention sweeps & analyze SNR")

# ============================================================
# TABS
# ============================================================

tabs = st.tabs(
    [
        "📊 Overview",
        "⚖️ Magnitude vs. Phase",
        "✂️ Time-Frequency Masking",
        "📈 Progressive Reconstruction",
        "🔬 Metrics & Analysis",
    ]
)

# ------------------------------------------------------------
# TAB 1 -- OVERVIEW
# ------------------------------------------------------------

with tabs[0]:
    st.markdown(
        """
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
            <h3 style="margin: 0; color: #0f172a;">Signal Overview</h3>
            <span style="font-size: 0.8rem; background: #e0e7ff; color: #3730a3; padding: 2px 10px; border-radius: 9999px; font-weight: 600;">
                STFT Matrix: {0} bins &times; {1} frames
            </span>
        </div>
        """.format(n_freq_bins, n_frames),
        unsafe_allow_html=True,
    )

    col_audio, col_info = st.columns([2, 1])
    with col_audio:
        st.audio(waveform_to_wav_bytes(y, sr), format="audio/wav")
    with col_info:
        st.markdown(
            f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 12px; font-size: 0.82rem; color: #475569;">
                <div>Resolution: <strong>{sr / n_fft:.1f} Hz/bin</strong></div>
                <div>Frame Step: <strong>{hop_length / sr * 1000:.1f} ms</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    st.pyplot(plot_waveform(y, sr, title=f"Time-Domain Waveform ({duration:.2f} s)"), use_container_width=True)

    st.pyplot(
        plot_spectrogram(
            magnitude_db_full, sr, hop_length, n_fft,
            title=f"STFT Magnitude Spectrogram ({freq_scale_mode.title()} Frequency Axis)",
            freq_scale=freq_scale_mode,
        ),
        use_container_width=True,
    )

    st.markdown(
        """
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #6366f1; border-radius: 8px; padding: 12px; font-size: 0.86rem; color: #334155; line-height: 1.5; margin-top: 10px;">
            <strong>Frequency-Domain Interpretation:</strong> The STFT spectrogram is the audio counterpart of MRI k-space.
            Horizontal energy bands represent sustained musical pitches or harmonic overtones; sharp vertical streaks represent transient percussive events.
            The log-frequency scale visualizes lower acoustic formants with high clarity matching the human cochlea.
        </div>
        """,
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------
# TAB 2 -- MAGNITUDE VS. PHASE
# ------------------------------------------------------------

with tabs[1]:
    st.markdown("### Magnitude vs. Phase Reconstruction")
    st.markdown(
        r"""
        Every STFT bin is a complex value $D(f,t) = |D(f,t)| \, e^{j\phi(f,t)}$.
        The **magnitude** $|D|$ governs spectral energy and loudness; the **phase** $\phi$ encodes temporal alignment and interference.
        In audio perception, magnitude carries the overwhelming majority of timbre and intelligible content.
        """
    )

    col1, col2 = st.columns(2)
    with col1:
        st.pyplot(
            plot_spectrogram(
                magnitude_db_full, sr, hop_length, n_fft,
                title="Magnitude Spectrogram |D(f,t)| (dB)",
                freq_scale=freq_scale_mode,
            ),
            use_container_width=True,
        )
    with col2:
        st.pyplot(
            plot_phase(phase_full, sr, hop_length, title="Phase Spectrogram φ(f,t)"),
            use_container_width=True,
        )

    st.markdown("#### Diagnostic Reconstruction: Isolated Magnitude vs. Phase")
    st.caption(
        r"Magnitude-only reconstruction zeroes out phase ($\phi = 0$). "
        r"Phase-only reconstruction flattens magnitude ($|D| = 1$). "
        "Listen to hear which component dominates acoustic perception:"
    )

    magnitude_only_D = combine_magnitude_phase(magnitude_full, np.zeros_like(phase_full))
    phase_only_D = combine_magnitude_phase(np.ones_like(magnitude_full), phase_full)

    magnitude_only_y = compute_istft(magnitude_only_D, hop_length, win_length, length=len(y))
    phase_only_y = compute_istft(phase_only_D, hop_length, win_length, length=len(y))

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
            <div class="lab-card lab-card-audio">
                <div style="font-weight: 700; color: #0f172a; margin-bottom: 4px;">🔊 Magnitude-Only Reconstruction</div>
                <div style="font-size: 0.8rem; color: #64748b; margin-bottom: 8px;">Phase zeroed &bull; Timbre and melody remain clear, slight smearing</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.audio(waveform_to_wav_bytes(magnitude_only_y, sr), format="audio/wav")

    with col2:
        st.markdown(
            """
            <div class="lab-card lab-card-audio">
                <div style="font-weight: 700; color: #0f172a; margin-bottom: 4px;">🔊 Phase-Only Reconstruction</div>
                <div style="font-size: 0.8rem; color: #64748b; margin-bottom: 8px;">Magnitude flattened &bull; Sounds like harsh static/whisper noise</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.audio(waveform_to_wav_bytes(phase_only_y, sr), format="audio/wav")

    st.info(
        "💡 **Key Discovery:** In audio, human perception is overwhelmingly driven by magnitude. "
        "Notice how different this is from the Image Lab, where *phase* carries structural shape and edges!"
    )

# ------------------------------------------------------------
# TAB 3 -- TIME-FREQUENCY MASKING
# ------------------------------------------------------------

with tabs[2]:
    st.markdown("### Time-Frequency Masking")
    st.markdown(
        "Select a bounding rectangle in the time-frequency plane to either **remove** (notch filter) or **isolate** (band-pass filter)."
    )

    col1, col2, col3 = st.columns([1.5, 1.5, 1])

    with col1:
        freq_range = st.slider(
            "Frequency Range (Hz)",
            min_value=0,
            max_value=int(sr / 2),
            value=(0, int(sr / 4)),
            step=50,
        )

    with col2:
        time_range = st.slider(
            "Time Interval (s)",
            min_value=0.0,
            max_value=float(duration),
            value=(0.0, float(duration)),
            step=0.05,
        )

    with col3:
        mask_mode = st.radio(
            "Action Mode",
            ["remove", "isolate"],
            format_func=lambda m: "❌ Remove Region" if m == "remove" else "🎯 Isolate Region",
            help="'remove' zeroes the selected area; 'isolate' zeroes out everything outside it.",
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
        plot_mask_overlay(
            magnitude_db_full, keep_mask, sr, hop_length,
            title=f"Selected Region ({mask_mode.title()}) -- Dimmed Area Removed",
        ),
        use_container_width=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Original Audio**")
        st.audio(waveform_to_wav_bytes(y, sr), format="audio/wav")

    with col2:
        st.markdown(f"**Masked Reconstruction ({mask_mode.title()})**")
        st.audio(waveform_to_wav_bytes(y_masked, sr), format="audio/wav")

    col_m1, col_m2 = st.columns([1, 2])
    with col_m1:
        masked_snr = snr_db(y, y_masked)
        st.metric("Signal-to-Noise Ratio (SNR)", f"{masked_snr:.2f} dB" if np.isfinite(masked_snr) else "∞ dB")
    with col_m2:
        st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
        if st.button("💾 Save masked reconstruction to gallery", key="save_masked_audio", use_container_width=True):
            saved_path = save_audio_result(y_masked, sr, f"masked_{mask_mode}")
            st.success(f"Saved: assets/audio/saved/{saved_path.name}")

# ------------------------------------------------------------
# TAB 4 -- PROGRESSIVE RECONSTRUCTION
# ------------------------------------------------------------

with tabs[3]:
    st.markdown("### Progressive Reconstruction")
    st.markdown(
        """
        Simulate data compression and band-limiting by retaining only a specific fraction of frequency bins.
        This mirrors undersampled MRI acquisition: see how perceptual audio quality changes as data is progressively truncated.
        """
    )

    col1, col2 = st.columns([1.5, 1.5])
    with col1:
        strategy = st.selectbox(
            "Retention strategy",
            ["low_frequency", "top_magnitude"],
            format_func=lambda s: {
                "low_frequency": "Low-frequency retention (band-limiting, mirrors k-space center)",
                "top_magnitude": "Top-magnitude retention (compressive sensing / sparse energy)",
            }[s],
        )
    with col2:
        keep_fraction = st.slider(
            "Fraction of data retained",
            min_value=0.01,
            max_value=1.0,
            value=0.30,
            step=0.01,
            format="%.2f",
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
            title=f"Retained Spectrogram ({keep_fraction * 100:.0f}% Kept -- {strategy.replace('_', ' ').title()})",
            freq_scale=freq_scale_mode,
        ),
        use_container_width=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Original Reference**")
        st.audio(waveform_to_wav_bytes(y, sr), format="audio/wav")
    with col2:
        st.markdown(f"**Reconstructed ({keep_fraction * 100:.0f}% Data Retained)**")
        st.audio(waveform_to_wav_bytes(y_retained, sr), format="audio/wav")

    col_ret_m, col_ret_b = st.columns([1, 2])
    with col_ret_m:
        retained_snr = snr_db(y, y_retained)
        st.metric("Reconstruction SNR", f"{retained_snr:.2f} dB" if np.isfinite(retained_snr) else "∞ dB")
    with col_ret_b:
        st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
        if st.button("💾 Save reconstruction to gallery", key="save_retained_audio", use_container_width=True):
            saved_path = save_audio_result(y_retained, sr, f"retained_{strategy}_{int(keep_fraction*100)}pct")
            st.success(f"Saved: assets/audio/saved/{saved_path.name}")

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    st.markdown("#### Quality vs. Data Retention Sweep")
    st.caption("Compute reconstruction SNR across multiple retention fractions to evaluate compression efficiency.")

    if st.button("🚀 Run Retention Sweep Analysis", use_container_width=True):
        fractions = [0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90, 1.0]
        progress_bar = st.progress(0, text="Starting retention sweep...")

        sweep_results = retention_sweep(D_full, strategy, fractions)
        snr_values = []

        for idx, (frac, D_variant) in enumerate(sweep_results):
            y_variant = compute_istft(D_variant, hop_length, win_length, length=len(y))
            snr_values.append(snr_db(y, y_variant))
            pct = int((idx + 1) / len(sweep_results) * 100)
            progress_bar.progress(pct, text=f"Evaluating retention fraction: {int(frac*100)}%...")

        progress_bar.empty()

        finite_max = max([v for v in snr_values if np.isfinite(v)], default=60.0)
        snr_plot_values = [v if np.isfinite(v) else finite_max * 1.1 for v in snr_values]

        st.pyplot(
            plot_retention_curve(
                fractions, snr_plot_values,
                ylabel="SNR (dB)",
                title=f"Reconstruction Quality vs. Data Retained ({strategy.replace('_', ' ').title()})",
            ),
            use_container_width=True,
        )

# ------------------------------------------------------------
# TAB 5 -- METRICS
# ------------------------------------------------------------

with tabs[4]:
    st.markdown("### Quantitative Fidelity Metrics")
    st.markdown("Evaluating mathematical fidelity between the **Original Reference** and current **Masked Audio**.")

    m_snr = snr_db(y, y_masked)
    m_mse = mse(y, y_masked)
    m_spec_conv = spectral_convergence(magnitude_full, np.abs(D_masked))

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label="Signal-to-Noise Ratio (SNR)",
            value=f"{m_snr:.2f} dB" if np.isfinite(m_snr) else "∞ dB",
            help="Higher is better. Measures relative signal strength versus residual error in decibels.",
        )
    with col2:
        st.metric(
            label="Mean Squared Error (MSE)",
            value=f"{m_mse:.6f}",
            help="Lower is better (0 = identical). Average squared sample-by-sample difference in time domain.",
        )
    with col3:
        st.metric(
            label="Spectral Convergence",
            value=f"{m_spec_conv:.4f}",
            help="Lower is better (0 = identical). Measures normalized Frobenius norm error in magnitude spectrogram.",
        )

    st.markdown(
        """
        <div class="lab-card lab-card-neutral" style="margin-top: 1.25rem;">
            <div style="font-size: 0.9rem; font-weight: 700; color: #0f172a; margin-bottom: 6px;">Metric Interpretations:</div>
            <ul style="color: #475569; font-size: 0.85rem; line-height: 1.6; margin-bottom: 0;">
                <li><strong>SNR (Signal-to-Noise Ratio):</strong> Standard acoustic benchmark. Above 20 dB indicates high perceptual fidelity; below 5 dB indicates severe attenuation or distortion.</li>
                <li><strong>MSE (Mean Squared Error):</strong> Quantifies sample-level divergence in the time domain, strictly penalizing large temporal phase misalignments.</li>
                <li><strong>Spectral Convergence:</strong> Direct frequency-domain evaluation: $\\| |D| - |D'| \\|_F / \\| |D| \\|_F$. Insensitive to inaudible phase shifts, reflecting true spectral envelope retention.</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ============================================================
# FOOTER
# ============================================================

st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
st.divider()
st.caption(
    "FourierLab Audio Module &bull; Educational STFT/iSTFT Signal Processing Workbench &bull; "
    "Calculations executed via NumPy, SciPy, and Librosa."
)
