"""
Fourier_Lab.py

Homepage for FourierLab -- Academic Signal Processing Demonstration Project.
Demonstrates frequency-domain masking, magnitude/phase analysis, and progressive
reconstruction symmetrically across 2D MRI k-space and audio STFT spectrograms.
"""

import streamlit as st
from ui_theme import apply_theme, render_logo, render_pipeline_flowchart

# ============================================================
# PAGE CONFIGURATION & THEME
# ============================================================

st.set_page_config(
    page_title="FourierLab | Signal Processing Workbench",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()

# ============================================================
# SIDEBAR
# ============================================================

render_logo("sidebar")

st.sidebar.markdown(
    """
    <div style="padding: 4px 0 16px 0; color: #94a3b8; font-size: 0.84rem; line-height: 1.5;">
        <p style="margin-bottom: 8px;"><strong style="color:#f1f5f9;">FourierLab</strong> is an interactive signal-processing laboratory designed to demonstrate frequency-domain information theory.</p>
        <p style="margin-bottom: 0;">Select a module below or from the sidebar menu to begin:</p>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    st.sidebar.page_link("pages/2_Image_Lab.py", label="Image Lab (MRI k-Space)", icon="🧠")
    st.sidebar.page_link("pages/1_Audio_Lab.py", label="Audio Lab (STFT)", icon="🎧")
except Exception:
    pass

st.sidebar.divider()
st.sidebar.caption("University Signal Processing Demonstration Project")

# ============================================================
# HEADER
# ============================================================

render_logo("header", subtitle="Exploring Frequency-Domain Information Through MRI and Audio Signals")

st.markdown(
    """
    <div style="color: #334155; font-size: 1.05rem; line-height: 1.6; margin-bottom: 1.25rem;">
        FourierLab investigates one core question across two contrasting physical domains:
        <strong>what does the frequency-domain representation of a signal actually contain, and what happens when we remove, isolate, or alter parts of it?</strong>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# PIPELINE FLOWCHART
# ============================================================

render_pipeline_flowchart("home")

# ============================================================
# MODULE SELECTION CARDS
# ============================================================

st.markdown(
    """
    <div style="font-size: 0.9rem; font-weight: 700; color: #0f172a; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.75rem;">
        Interactive Laboratory Modules
    </div>
    """,
    unsafe_allow_html=True,
)

col_img, col_aud = st.columns(2)

with col_img:
    st.markdown(
        """
        <div class="lab-card lab-card-image">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                <div style="font-size: 1.25rem; font-weight: 700; color: #0f172a;">🧠 Image Lab</div>
                <span style="font-size: 0.75rem; background: #f0fdfa; color: #0d9488; border: 1px solid #99f6e4; padding: 2px 8px; border-radius: 9999px; font-weight: 600;">2D Spatial Frequency</span>
            </div>
            <p style="color: #475569; font-size: 0.88rem; line-height: 1.5; margin-bottom: 12px;">
                Simulate magnetic resonance k-space acquisition. Explore center vs. outer frequency masking, observe the surprising visual predominance of phase over magnitude, test progressive acquisition sweeps, and evaluate structural similarity (SSIM).
            </p>
            <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; font-size: 0.75rem;">
                <span style="background:#f1f5f9; color:#475569; padding: 2px 8px; border-radius: 4px;">Shepp-Logan Phantom</span>
                <span style="background:#f1f5f9; color:#475569; padding: 2px 8px; border-radius: 4px;">k-Space Masking</span>
                <span style="background:#f1f5f9; color:#475569; padding: 2px 8px; border-radius: 4px;">PSNR & SSIM</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    try:
        st.page_link("pages/2_Image_Lab.py", label="Launch Image Lab (MRI)", icon="🧠", use_container_width=True)
    except Exception:
        st.info("Open Image Lab from the sidebar.")

with col_aud:
    st.markdown(
        """
        <div class="lab-card lab-card-audio">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                <div style="font-size: 1.25rem; font-weight: 700; color: #0f172a;">🎧 Audio Lab</div>
                <span style="font-size: 0.75rem; background: #eef2ff; color: #6366f1; border: 1px solid #c7d2fe; padding: 2px 8px; border-radius: 9999px; font-weight: 600;">Time-Frequency STFT</span>
            </div>
            <p style="color: #475569; font-size: 0.88rem; line-height: 1.5; margin-bottom: 12px;">
                Deconstruct acoustic audio signals into time-frequency bins with Short-Time Fourier Transforms. Isolate frequency bands, listen to magnitude-only vs. phase-only reconstructions, perform progressive retention, and analyze SNR metrics.
            </p>
            <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; font-size: 0.75rem;">
                <span style="background:#f1f5f9; color:#475569; padding: 2px 8px; border-radius: 4px;">Log Spectrogram</span>
                <span style="background:#f1f5f9; color:#475569; padding: 2px 8px; border-radius: 4px;">Time-Freq Masking</span>
                <span style="background:#f1f5f9; color:#475569; padding: 2px 8px; border-radius: 4px;">SNR & Spectral Conv</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    try:
        st.page_link("pages/1_Audio_Lab.py", label="Launch Audio Lab (STFT)", icon="🎧", use_container_width=True)
    except Exception:
        st.info("Open Audio Lab from the sidebar.")

st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

# ============================================================
# CONCEPTUAL SYMMETRY MATRIX
# ============================================================

st.markdown(
    r"""
    <div class="lab-card lab-card-neutral">
        <div style="font-size: 0.95rem; font-weight: 700; color: #0f172a; margin-bottom: 0.75rem; display: flex; align-items: center; gap: 8px;">
            <span>⚖️ Symmetrical Concepts Across Domains</span>
        </div>
        <p style="color: #475569; font-size: 0.86rem; margin-bottom: 1rem;">
            Both modules implement identical mathematical principles applied to different signal geometries:
        </p>
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse; font-size: 0.85rem; text-align: left;">
                <thead>
                    <tr style="background-color: #f1f5f9; border-bottom: 2px solid #cbd5e1; color: #1e293b;">
                        <th style="padding: 8px 12px; font-weight: 600;">Operation / Concept</th>
                        <th style="padding: 8px 12px; font-weight: 600; color: #0d9488;">🧠 Image Lab (MRI k-Space)</th>
                        <th style="padding: 8px 12px; font-weight: 600; color: #6366f1;">🎧 Audio Lab (STFT)</th>
                    </tr>
                </thead>
                <tbody style="color: #334155;">
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 8px 12px; font-weight: 600;">Frequency-Domain Data</td>
                        <td style="padding: 8px 12px;">2D spatial frequency k-space $K(u,v)$</td>
                        <td style="padding: 8px 12px;">2D time-frequency spectrogram $D(f,t)$</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0; background: #fafafa;">
                        <td style="padding: 8px 12px; font-weight: 600;">Low-Frequency Region</td>
                        <td style="padding: 8px 12px;">k-space center (radius $r$)</td>
                        <td style="padding: 8px 12px;">Base frequency band ($0 \dots f_c$)</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 8px 12px; font-weight: 600;">Masking / Filtering</td>
                        <td style="padding: 8px 12px;">Center, outer, or custom 2D bounding boxes</td>
                        <td style="padding: 8px 12px;">Time-frequency rectangular bounding boxes</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0; background: #fafafa;">
                        <td style="padding: 8px 12px; font-weight: 600;">Progressive Retention</td>
                        <td style="padding: 8px 12px;">Center-radius vs. top-magnitude retention</td>
                        <td style="padding: 8px 12px;">Low-frequency cutoff vs. top-magnitude retention</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 8px 12px; font-weight: 600;">Magnitude Carries</td>
                        <td style="padding: 8px 12px;">Overall contrast and luminance</td>
                        <td style="padding: 8px 12px;">Loudness and spectral envelope (highly audible)</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0; background: #fafafa;">
                        <td style="padding: 8px 12px; font-weight: 600;">Phase Carries</td>
                        <td style="padding: 8px 12px;"><strong>Crucial spatial structure & edges</strong></td>
                        <td style="padding: 8px 12px;">Waveform alignment & timing (subtly audible)</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 12px; font-weight: 600;">Fidelity Metrics</td>
                        <td style="padding: 8px 12px;">MSE, PSNR (dB), SSIM index</td>
                        <td style="padding: 8px 12px;">SNR (dB), MSE, Spectral Convergence</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# FOOTER
# ============================================================

st.caption(
    "FourierLab &bull; Academic Signal Processing Exploration &bull; "
    "Designed with modern Streamlit, NumPy, SciPy, Librosa, and Matplotlib."
)
