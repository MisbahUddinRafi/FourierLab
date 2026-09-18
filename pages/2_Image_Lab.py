"""
pages/2_Image_Lab.py

FourierLab -- MRI k-Space Reconstruction Module
Educational 2D Fourier Transform and spatial-frequency workbench.
Redesigned with refined scientific UI, grouped sidebar controls,
flowchart ribbons, card containers, and interactive sweeps.
"""

from datetime import datetime
from pathlib import Path

import numpy as np
import streamlit as st

from mri_core.kspace_engine import (
    fft2_centered,
    ifft2_centered,
    magnitude_phase,
    combine_magnitude_phase,
    kspace_log_magnitude,
    create_complex_image,
)
from mri_core.masking import build_kspace_mask, apply_mask
from mri_core.reconstruction import (
    retain_center_fraction,
    retain_top_magnitude,
    retention_sweep,
)
from mri_core.metrics import mse_metric, psnr_metric, ssim_metric, error_heatmap

from mri_utils.image_io import (
    load_uploaded_image,
    create_phantom,
    normalize_image,
    image_to_png_bytes,
)
from mri_utils.plotting import (
    plot_kspace_magnitude,
    plot_phase_map,
    plot_error_heatmap,
    plot_ssim_map,
    plot_mask_overlay,
    plot_retention_curve,
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
    page_title="Image Lab | FourierLab",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()

# ============================================================
# SAMPLE / SAVED-RESULT GALLERY FOLDERS
# ============================================================

APP_ROOT = Path(__file__).resolve().parent.parent
IMAGE_SAMPLES_DIR = APP_ROOT / "assets" / "images" / "samples"
IMAGE_SAVED_DIR = APP_ROOT / "assets" / "images" / "saved"
IMAGE_SAVED_DIR.mkdir(parents=True, exist_ok=True)


def save_image_result(image_array: np.ndarray, label: str) -> Path:
    """Write a reconstructed image into the saved-results gallery folder."""
    filename = f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = IMAGE_SAVED_DIR / filename
    with open(path, "wb") as f:
        f.write(image_to_png_bytes(image_array))
    return path


# ============================================================
# SIDEBAR -- GROUPED CONTROLS
# ============================================================

render_logo("sidebar")

st.sidebar.markdown(
    """
    <div style="font-size: 0.75rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;">
        1. Input Image Source
    </div>
    """,
    unsafe_allow_html=True,
)

input_mode = st.sidebar.radio(
    "Input source",
    ["Synthetic MRI phantom", "Use a sample / saved result", "Upload an image"],
    label_visibility="collapsed",
)

image_size = st.sidebar.select_slider(
    "Simulation resolution (N x N)",
    options=[128, 160, 192, 256],
    value=160,
    help="Higher resolution yields sharper details but increases 2D FFT calculation time.",
)

uploaded_file = None
gallery_choice = None

if input_mode == "Upload an image":
    uploaded_file = st.sidebar.file_uploader("Upload MRI/medical image", type=["png", "jpg", "jpeg"])
elif input_mode == "Use a sample / saved result":
    # Support both png and jpg sample images
    gallery_files = (
        sorted(IMAGE_SAMPLES_DIR.glob("*.png"))
        + sorted(IMAGE_SAMPLES_DIR.glob("*.jpg"))
        + sorted(IMAGE_SAVED_DIR.glob("*.png"))
    )
    if not gallery_files:
        st.sidebar.warning("No sample/saved images found in assets/images/samples/.")
    else:
        gallery_choice = st.sidebar.selectbox(
            "Choose reference image",
            gallery_files,
            format_func=lambda p: f"{'📁 ' if p.parent.name == 'samples' else '💾 '}{p.stem} ({p.parent.name})",
        )

st.sidebar.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
st.sidebar.markdown(
    """
    <div style="font-size: 0.75rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;">
        2. Synthetic Phase Control
    </div>
    """,
    unsafe_allow_html=True,
)

phase_strength = st.sidebar.slider(
    "Phase strength",
    min_value=0.0,
    max_value=2.0,
    value=0.6,
    step=0.05,
    help="Natural grayscale images have 0 or pi phase. This injects smooth spatial phase variation so complex k-space phase properties can be investigated.",
)

# ============================================================
# LOAD INPUT IMAGE & COMPUTE K-SPACE
# ============================================================

if input_mode == "Upload an image":
    if uploaded_file is None:
        render_logo("header", subtitle="Magnetic Resonance 2D k-Space Reconstruction Explorer")
        render_pipeline_flowchart("image")
        st.info("👋 Upload an image from the sidebar to begin analysis.")
        st.stop()
    magnitude_image = load_uploaded_image(uploaded_file, image_size)
elif input_mode == "Use a sample / saved result":
    if gallery_choice is None:
        render_logo("header", subtitle="Magnetic Resonance 2D k-Space Reconstruction Explorer")
        render_pipeline_flowchart("image")
        st.info("👋 Select an image from the sidebar gallery to begin analysis.")
        st.stop()
    magnitude_image = load_uploaded_image(str(gallery_choice), image_size)
else:
    magnitude_image = create_phantom(image_size)

# Sidebar metadata badge
st.sidebar.markdown(
    f"""
    <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 10px; margin-top: 10px; font-size: 0.78rem; color: #cbd5e1;">
        <div style="font-weight: 600; color: #2dd4bf; margin-bottom: 4px;">Active Image Matrix</div>
        <div>Dimensions: <strong>{image_size} &times; {image_size}</strong> ({image_size*image_size:,} voxels)</div>
        <div>Phase Variation: <strong>{phase_strength:.2f} rad</strong></div>
    </div>
    """,
    unsafe_allow_html=True,
)

complex_image, phase_map = create_complex_image(magnitude_image, phase_strength)
full_kspace = fft2_centered(complex_image)
full_kspace_log_mag = kspace_log_magnitude(full_kspace)

# ============================================================
# HEADER & WORKFLOW RIBBON
# ============================================================

render_logo("header", subtitle="Magnetic Resonance 2D k-Space Reconstruction Explorer")
render_pipeline_flowchart("image")
render_quick_start("Inspect input image & k-space", "Mask spatial frequencies & compare phase", "Run progressive retention & evaluate SSIM")

# ============================================================
# TABS
# ============================================================

tabs = st.tabs(
    [
        "📊 Overview",
        "⚖️ k-Space Analysis",
        "✂️ Frequency-Domain Masking",
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
            <h3 style="margin: 0; color: #0f172a;">Image Formation Pipeline</h3>
            <span style="font-size: 0.8rem; background: #ccfbf1; color: #0f766e; padding: 2px 10px; border-radius: 9999px; font-weight: 600;">
                Full Acquisition (100% k-Space)
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
            <div class="plot-container">
                <div style="font-weight: 600; font-size: 0.85rem; color: #334155; margin-bottom: 4px; text-align: center;">Original Spatial Image I(x,y)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.image(magnitude_image, clamp=True, use_container_width=True)

    with col2:
        st.markdown(
            """
            <div class="plot-container">
                <div style="font-weight: 600; font-size: 0.85rem; color: #334155; margin-bottom: 4px; text-align: center;">Full k-Space (2D FFT)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.pyplot(plot_kspace_magnitude(full_kspace_log_mag, "k-Space Log Magnitude"), use_container_width=True)

    with col3:
        sanity_recon = normalize_image(np.abs(ifft2_centered(full_kspace)))
        st.markdown(
            """
            <div class="plot-container">
                <div style="font-weight: 600; font-size: 0.85rem; color: #334155; margin-bottom: 4px; text-align: center;">Reconstructed Image (iFFT2)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.image(sanity_recon, clamp=True, use_container_width=True)

    st.markdown(
        """
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #0d9488; border-radius: 8px; padding: 12px; font-size: 0.86rem; color: #334155; line-height: 1.5; margin-top: 10px;">
            <strong>Fundamental Principle:</strong> In Magnetic Resonance Imaging (MRI), data is acquired directly in the spatial-frequency domain (k-space) via magnetic field gradients.
            With 100% of k-space collected, the inverse 2D Fast Fourier Transform recovers an exact reconstruction.
            The center of k-space encodes low spatial frequencies (gross anatomy and bulk tissue contrast); outer k-space encodes high spatial frequencies (edges, fine boundaries, and resolution).
        </div>
        """,
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------
# TAB 2 -- K-SPACE ANALYSIS (magnitude vs phase)
# ------------------------------------------------------------

with tabs[1]:
    st.markdown("### Magnitude vs. Phase in 2D Images")
    st.markdown(
        r"""
        Every k-space sample is complex: $K(u,v) = |K(u,v)|\,e^{j\phi(u,v)}$.
        Try modifying the **Phase strength** slider in the sidebar to observe how spatial phase structure interacts with k-space representation.
        """
    )

    col1, col2 = st.columns(2)
    with col1:
        st.pyplot(plot_kspace_magnitude(full_kspace_log_mag, "k-Space Magnitude |K(u,v)|"), use_container_width=True)
    with col2:
        kspace_phase = np.angle(full_kspace)
        st.pyplot(plot_phase_map(kspace_phase, "k-Space Phase φ(u,v)"), use_container_width=True)

    st.markdown("#### Isolated Reconstruction: Magnitude-Only vs. Phase-Only")
    st.caption(
        "Magnitude-only reconstruction sets phase to zero. "
        "Phase-only reconstruction flattens magnitude to a constant value. "
        "Observe which component preserves identifiable anatomical shape:"
    )

    magnitude, phase = magnitude_phase(full_kspace)
    magnitude_only_kspace = combine_magnitude_phase(magnitude, np.zeros_like(phase))
    phase_only_kspace = combine_magnitude_phase(np.ones_like(magnitude), phase)

    magnitude_only_img = normalize_image(np.abs(ifft2_centered(magnitude_only_kspace)))
    phase_only_img = normalize_image(np.abs(ifft2_centered(phase_only_kspace)))

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
            <div class="lab-card lab-card-image">
                <div style="font-weight: 700; color: #0f172a; margin-bottom: 4px;">🖼️ Magnitude-Only Reconstruction</div>
                <div style="font-size: 0.8rem; color: #64748b; margin-bottom: 8px;">Phase zeroed &bull; Structural shapes and edges collapse into fuzzy noise</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.image(magnitude_only_img, clamp=True, use_container_width=True)

    with col2:
        st.markdown(
            """
            <div class="lab-card lab-card-image">
                <div style="font-weight: 700; color: #0f172a; margin-bottom: 4px;">🖼️ Phase-Only Reconstruction</div>
                <div style="font-size: 0.8rem; color: #64748b; margin-bottom: 8px;">Magnitude flattened &bull; Edge boundaries and recognizable anatomy survive!</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.image(phase_only_img, clamp=True, use_container_width=True)

    st.markdown(
        """
        <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-left: 4px solid #2563eb; border-radius: 8px; padding: 12px; font-size: 0.86rem; color: #1e3a8a; line-height: 1.5; margin-top: 10px;">
            🔍 <strong>The Phase Primacy Discovery:</strong> In 2D images, phase carries the essential structural edges and geometric contours, whereas magnitude carries broad contrast.
            This is the exact mathematical inverse of 1D audio perception (where magnitude governs speech/pitch intelligibility and phase is largely inaudible).
        </div>
        """,
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------
# TAB 3 -- FREQUENCY-DOMAIN MASKING
# ------------------------------------------------------------

with tabs[2]:
    st.markdown("### Frequency-Domain Masking")
    st.markdown(
        "Select a geometric region in k-space to either **isolate** (bandpass acquisition) or **remove** (bandstop filtering)."
    )

    col1, col2, col3 = st.columns([1.2, 1.2, 1.6])

    with col1:
        mask_type = st.selectbox("Region type", ["center", "outer", "custom"], format_func=str.title)
    with col2:
        mask_mode = st.radio(
            "Acquisition Mode",
            ["isolate", "remove"],
            format_func=lambda m: "🎯 Isolate Region" if m == "isolate" else "❌ Remove Region",
            help="'isolate' keeps only the selected region; 'remove' zeroes out the selected region.",
        )
    with col3:
        radius, kx_range, ky_range = 0.25, (-0.4, 0.4), (-0.4, 0.4)
        if mask_type in ("center", "outer"):
            radius = st.slider(
                "Region radius (normalized)",
                min_value=0.05,
                max_value=1.0,
                value=0.25,
                step=0.01,
            )
        else:
            kx_range = st.slider("kx range", -1.4, 1.4, (-0.4, 0.4), step=0.05)
            ky_range = st.slider("ky range", -1.4, 1.4, (-0.4, 0.4), step=0.05)

    keep_mask = build_kspace_mask(
        full_kspace.shape, mask_type, mask_mode,
        radius=radius, kx_range=kx_range, ky_range=ky_range,
    )

    masked_kspace = apply_mask(full_kspace, keep_mask)
    masked_recon = normalize_image(np.abs(ifft2_centered(masked_kspace)))
    retained_pct = 100 * keep_mask.mean()

    st.pyplot(
        plot_mask_overlay(
            full_kspace_log_mag, keep_mask,
            title=f"{mask_type.title()} Region ({mask_mode.title()} -- {retained_pct:.1f}% Retained)",
        ),
        use_container_width=True,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            """
            <div class="plot-container">
                <div style="font-weight: 600; font-size: 0.82rem; color: #334155; margin-bottom: 2px; text-align: center;">Original Reference</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.image(magnitude_image, clamp=True, use_container_width=True)

    with col2:
        st.markdown(
            """
            <div class="plot-container">
                <div style="font-weight: 600; font-size: 0.82rem; color: #334155; margin-bottom: 2px; text-align: center;">Masked Reconstruction</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.image(masked_recon, clamp=True, use_container_width=True)

    with col3:
        st.markdown(
            """
            <div class="plot-container">
                <div style="font-weight: 600; font-size: 0.82rem; color: #334155; margin-bottom: 2px; text-align: center;">Absolute Spatial Error</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        err_map = error_heatmap(magnitude_image, masked_recon)
        st.pyplot(plot_error_heatmap(err_map, "Absolute Error"), use_container_width=True)

    m_psnr = psnr_metric(magnitude_image, masked_recon)
    m_ssim, _ = ssim_metric(magnitude_image, masked_recon)

    col1, col2, col3 = st.columns(3)
    col1.metric("k-Space Retained", f"{retained_pct:.1f}%")
    col2.metric("Peak SNR (PSNR)", f"{m_psnr:.2f} dB" if np.isfinite(m_psnr) else "∞ dB")
    col3.metric("Structural Similarity (SSIM)", f"{m_ssim:.4f}")

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.download_button(
            "⬇️ Download Masked Reconstruction (PNG)",
            data=image_to_png_bytes(masked_recon),
            file_name="mri_masked_reconstruction.png",
            mime="image/png",
            use_container_width=True,
        )
    with col_d2:
        if st.button("💾 Save Reconstruction to Gallery", key="save_masked_image", use_container_width=True):
            saved_path = save_image_result(masked_recon, f"masked_{mask_type}_{mask_mode}")
            st.success(f"Saved: assets/images/saved/{saved_path.name}")

    if mask_type == "center":
        st.info("💡 **Center Masking:** Isolating the center retains low frequencies (overall contrast and bulk tissue geometry survives, but fine detail is blurred). Removing the center collapses contrast while preserving sharp boundary outlines.")
    elif mask_type == "outer":
        st.info("💡 **Outer Masking:** Isolating outer k-space acts as a high-pass edge detector. Removing outer k-space creates classical Gibbs ringing and low-pass smoothing.")
    else:
        st.info("💡 **Custom Rectangles:** Probes directional frequency anisotropy. Filtering along kx impacts vertical edge resolution; filtering along ky impacts horizontal edge resolution.")

# ------------------------------------------------------------
# TAB 4 -- PROGRESSIVE RECONSTRUCTION
# ------------------------------------------------------------

with tabs[3]:
    st.markdown("### Progressive k-Space Acquisition")
    st.markdown(
        """
        Simulate accelerated MRI scanning by acquiring only a reduced subset of k-space samples.
        Compare concentric center-out trajectory against compressive sparse top-magnitude retention.
        """
    )

    col1, col2 = st.columns([1.5, 1.5])
    with col1:
        strategy = st.selectbox(
            "Retention strategy",
            ["center_radius", "top_magnitude"],
            format_func=lambda s: {
                "center_radius": "Center-radius retention (clinical undersampled acquisition)",
                "top_magnitude": "Top-magnitude retention (compressive sensing / sparse energy)",
            }[s],
        )
    with col2:
        keep_fraction = st.slider("Target Fraction Retained", 0.01, 1.0, 0.25, step=0.01, format="%.2f")

    if strategy == "center_radius":
        kspace_retained, actual_fraction = retain_center_fraction(full_kspace, keep_fraction)
    else:
        kspace_retained, actual_fraction = retain_top_magnitude(full_kspace, keep_fraction)

    retained_recon = normalize_image(np.abs(ifft2_centered(kspace_retained)))
    retained_log_mag = kspace_log_magnitude(kspace_retained)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            """
            <div class="plot-container">
                <div style="font-weight: 600; font-size: 0.82rem; color: #334155; margin-bottom: 2px; text-align: center;">Retained k-Space Samples</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.pyplot(plot_kspace_magnitude(retained_log_mag, f"Retained k-Space ({actual_fraction*100:.1f}%)"), use_container_width=True)

    with col2:
        st.markdown(
            """
            <div class="plot-container">
                <div style="font-weight: 600; font-size: 0.82rem; color: #334155; margin-bottom: 2px; text-align: center;">Reconstructed Image</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.image(retained_recon, clamp=True, use_container_width=True)

    with col3:
        st.markdown(
            """
            <div class="plot-container">
                <div style="font-weight: 600; font-size: 0.82rem; color: #334155; margin-bottom: 2px; text-align: center;">Absolute Error Heatmap</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        err_map = error_heatmap(magnitude_image, retained_recon)
        st.pyplot(plot_error_heatmap(err_map, "Absolute Error"), use_container_width=True)

    p_psnr = psnr_metric(magnitude_image, retained_recon)
    p_ssim, _ = ssim_metric(magnitude_image, retained_recon)

    col1, col2, col3 = st.columns(3)
    col1.metric("Actual Data Retained", f"{actual_fraction*100:.1f}%")
    col2.metric("Peak SNR (PSNR)", f"{p_psnr:.2f} dB" if np.isfinite(p_psnr) else "∞ dB")
    col3.metric("Structural Similarity (SSIM)", f"{p_ssim:.4f}")

    if st.button("💾 Save Reconstruction to Gallery", key="save_retained_image", use_container_width=True):
        saved_path = save_image_result(retained_recon, f"retained_{strategy}_{int(actual_fraction*100)}pct")
        st.success(f"Saved: assets/images/saved/{saved_path.name}")

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    st.markdown("#### Quality vs. Retention Sweep Analysis")
    st.caption("Evaluate PSNR and SSIM across progressively increasing acquisition percentages.")

    if st.button("🚀 Run Progressive Acquisition Sweep", use_container_width=True):
        fractions = [0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
        progress_bar = st.progress(0, text="Starting k-space retention sweep...")

        sweep_results = retention_sweep(full_kspace, strategy, fractions)

        actual_fracs, psnr_values, ssim_values = [], [], []
        for idx, (_, actual_frac, kspace_variant) in enumerate(sweep_results):
            recon_variant = normalize_image(np.abs(ifft2_centered(kspace_variant)))
            p = psnr_metric(magnitude_image, recon_variant)
            s, _ = ssim_metric(magnitude_image, recon_variant)
            actual_fracs.append(actual_frac)
            psnr_values.append(min(p, 60.0) if np.isfinite(p) else 60.0)
            ssim_values.append(s)
            pct = int((idx + 1) / len(sweep_results) * 100)
            progress_bar.progress(pct, text=f"Acquiring {actual_frac*100:.1f}% k-space...")

        progress_bar.empty()

        col1, col2 = st.columns(2)
        with col1:
            st.pyplot(
                plot_retention_curve(actual_fracs, {"PSNR (dB)": psnr_values}, title=f"PSNR vs. Retention ({strategy})"),
                use_container_width=True,
            )
        with col2:
            st.pyplot(
                plot_retention_curve(actual_fracs, {"SSIM Index": ssim_values}, title=f"SSIM vs. Retention ({strategy})"),
                use_container_width=True,
            )

# ------------------------------------------------------------
# TAB 5 -- METRICS
# ------------------------------------------------------------

with tabs[4]:
    st.markdown("### Quantitative Fidelity & Structural Analysis")
    st.markdown("Evaluating reconstruction fidelity between the **Reference Image** and the **Masked Result**.")

    m_mse = mse_metric(magnitude_image, masked_recon)
    m_psnr = psnr_metric(magnitude_image, masked_recon)
    m_ssim, m_ssim_map = ssim_metric(magnitude_image, masked_recon)

    col1, col2, col3 = st.columns(3)
    col1.metric(
        label="Mean Squared Error (MSE)",
        value=f"{m_mse:.6f}",
        help="Lower is better (0 = identical). Average squared pixel difference across the image matrix.",
    )
    col2.metric(
        label="Peak Signal-to-Noise Ratio (PSNR)",
        value=f"{m_psnr:.2f} dB" if np.isfinite(m_psnr) else "∞ dB",
        help="Higher is better. Logarithmic ratio between maximum signal power and noise MSE.",
    )
    col3.metric(
        label="Structural Similarity Index (SSIM)",
        value=f"{m_ssim:.4f}",
        help="Scale [0, 1]. Evaluates luminance, contrast, and structural correlation in sliding Gaussian windows.",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.pyplot(
            plot_error_heatmap(error_heatmap(magnitude_image, masked_recon), "Absolute Error Heatmap |I - I'|"),
            use_container_width=True,
        )
    with col2:
        st.pyplot(plot_ssim_map(m_ssim_map, "Local SSIM Structural Map"), use_container_width=True)

    st.markdown(
        """
        <div class="lab-card lab-card-neutral" style="margin-top: 1.25rem;">
            <div style="font-size: 0.9rem; font-weight: 700; color: #0f172a; margin-bottom: 6px;">Metric Interpretations in Medical Imaging:</div>
            <ul style="color: #475569; font-size: 0.85rem; line-height: 1.6; margin-bottom: 0;">
                <li><strong>MSE (Mean Squared Error):</strong> Pixel-wise squared Euclidean distance. Sensitive to bulk intensity scaling but blind to spatial structure.</li>
                <li><strong>PSNR:</strong> Standard decibel compression benchmark: $10 \\log_{10}(1 / \\text{MSE})$. In medical imaging, values $>30\\text{ dB}$ represent acceptable diagnostic quality.</li>
                <li><strong>SSIM vs Local Map:</strong> Models human visual system perception. Notice how blurring (undersampled outer k-space) sharply drops SSIM around edge contours while barely perturbing uniform flat tissue regions.</li>
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
    "FourierLab MRI Module &bull; Educational 2D k-Space Signal Processing Workbench &bull; "
    "Calculations executed via NumPy and SciPy."
)
